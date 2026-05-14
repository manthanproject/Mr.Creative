const SERVER = 'http://localhost:5000';
let polling = false;
let pollInterval = null;
let profileId = null;

// ── Get or create persistent profile ID ──
async function getProfileId() {
    const data = await chrome.storage.local.get('profileId');
    if (!data.profileId) {
        const id = 'profile_' + Date.now() + '_' + Math.random().toString(36).substring(2, 8);
        await chrome.storage.local.set({ profileId: id });
        return id;
    }
    return data.profileId;
}

// ── Detect which Google account is logged in ──
async function detectAccount() {
    try {
        // Check Pomelli tabs
        let tabs = await chrome.tabs.query({ url: ['https://labs.google.com/pomelli/*', 'https://labs.google.com/u/*/pomelli/*'] });
        if (tabs.length === 0) {
            tabs = await chrome.tabs.query({ url: 'https://labs.google/*' });
        }
        if (tabs.length > 0) {
            const result = await chrome.scripting.executeScript({
                target: { tabId: tabs[0].id },
                func: () => {
                    const img = document.querySelector('img[aria-label*="Google Account"], header img[src*="googleusercontent"]');
                    if (img) return img.getAttribute('aria-label') || img.alt || 'detected';
                    const btn = document.querySelector('[data-email]');
                    if (btn) return btn.getAttribute('data-email');
                    return document.title || 'unknown';
                }
            });
            return result?.[0]?.result || 'unknown';
        }
    } catch (e) {}
    return 'unknown';
}

// ── Detect what this profile can do ──
async function detectCapabilities() {
    const caps = ['campaign', 'photoshoot', 'gemini'];
    try {
        const data = await chrome.storage.local.get('extraCapabilities');
        if (data.extraCapabilities && Array.isArray(data.extraCapabilities)) {
            for (const c of data.extraCapabilities) {
                if (!caps.includes(c)) caps.push(c);
            }
        }
    } catch (e) {}
    return caps;
}

// ── Register this profile with the server ──
async function registerWithServer() {
    profileId = await getProfileId();
    const account = await detectAccount();
    const capabilities = await detectCapabilities();

    try {
        const res = await fetch(`${SERVER}/api/ext/register`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ profile_id: profileId, account, capabilities })
        });
        const data = await res.json();
        console.log('[MC-BG] Registered:', { profileId, account, capabilities });
    } catch (e) {
        console.warn('[MC-BG] Registration failed (server offline?):', e.message);
    }
}

// ── Start polling for commands ──
function startPolling() {
    if (polling) return;
    polling = true;
    pollInterval = setInterval(checkForCommand, 3000);
    chrome.alarms.create('mc_keepalive', { periodInMinutes: 0.4 });
    checkForCommand();  // immediate
    console.log('[MC-BG] Polling started (interval + alarm keepalive)');
}

function stopPolling() {
    polling = false;
    if (pollInterval) { clearInterval(pollInterval); pollInterval = null; }
    chrome.alarms.clear('mc_keepalive');
    console.log('[MC-BG] Polling stopped');
}

// ── Keepalive alarm: restart setInterval if worker just woke up ──
chrome.alarms.onAlarm.addListener((alarm) => {
    if (alarm.name === 'mc_keepalive') {
        if (polling && pollInterval === null) {
            // Worker was asleep; setInterval was lost. Restart it.
            pollInterval = setInterval(checkForCommand, 3000);
            console.log('[MC-BG] Worker woke — restarted interval polling');
        }
        checkForCommand();
    }
});

// ── Check server for pending command (profile-aware) ──
async function checkForCommand() {
    if (!profileId) profileId = await getProfileId();
    try {
        const res = await fetch(`${SERVER}/api/ext/command?profile_id=${profileId}`);
        if (!res.ok || res.status === 204) return;
        const cmd = await res.json();
        if (!cmd || !cmd.job_id) return;
        console.log('[MC-BG] Received command:', cmd.job_type, cmd.job_id);
        // For flow jobs: only accept if this profile has flow_active (Flow tab open)
        if (cmd.job_type === 'flow' || cmd.job_type === 'aplus') {
            const data = await chrome.storage.local.get('extraCapabilities');
            const extras = data.extraCapabilities || [];
            if (!extras.includes('flow_active')) {
                console.log('[MC-BG] No flow_active capability, skipping flow job');
                try {
                    await fetch(SERVER + '/api/ext/submit', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify(cmd)
                    });
                } catch(e) {}
                return;
            }
        }
        await dispatchJob(cmd);
    } catch (e) {
        console.error('[MC-BG] checkForCommand error:', e.message || e);
    }
}

// ── Build landing URL preserving any /u/N/ prefix from an existing tab URL ──
function buildLandingUrl(jobType, existingTabUrl) {
    let prefix = '';
    if (existingTabUrl) {
        const m = existingTabUrl.match(/^https:\/\/labs\.google\.com(\/u\/\d+)?\//);
        if (m && m[1]) prefix = m[1];
    }
    switch (jobType) {
        case 'campaign':   return `https://labs.google.com${prefix}/pomelli/campaigns`;
        case 'photoshoot': return `https://labs.google.com${prefix}/pomelli/photoshoot`;
        case 'flow': case 'aplus': return 'https://labs.google/fx/tools/flow';
        default: return `https://labs.google.com${prefix}/pomelli/campaigns`;
    }
}

// ── Send the job to a tab + ACK ──
async function sendJobToTab(tab, job) {
    for (let attempt = 1; attempt <= 3; attempt++) {
        try {
            await chrome.tabs.sendMessage(tab.id, { type: 'RUN_JOB', job });
            console.log('[MC-BG] Job dispatched to tab', tab.id, 'attempt', attempt);
            await fetch(`${SERVER}/api/ext/ack`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ job_id: job.job_id, profile_id: profileId })
            });
            return;  // success
        } catch (e) {
            console.warn(`[MC-BG] Dispatch attempt ${attempt}/3 failed:`, e.message);
            if (attempt < 3) await new Promise(r => setTimeout(r, 5000));
        }
    }
    console.error('[MC-BG] All dispatch attempts failed for', job.job_id);
    // Put job back on server so content script can pick it up
    try {
        await fetch(SERVER + '/api/ext/submit', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(job)
        });
        console.log('[MC-BG] Job returned to server for content script pickup');
    } catch (e2) {}
}

// ── Dispatch job to the right tab ──
async function dispatchJob(job) {
    // ── Gemini jobs go to gemini.google.com ──
    if (job.job_type === 'gemini') {
        let tabs = await chrome.tabs.query({ url: 'https://gemini.google.com/*' });
        let tab;
        if (tabs.length > 0) {
            tab = tabs[0];
            await chrome.tabs.update(tab.id, { active: true });
        } else {
            tab = await chrome.tabs.create({ url: 'https://gemini.google.com/app' });
            await waitForTabLoad(tab.id);
            await new Promise(r => setTimeout(r, 5000));
        }
        await sendJobToTab(tab, job);
        return;
    }



    // Query both URL patterns (with and without /u/N/ prefix)
    const queries = [];
    if (job.job_type === 'flow' || job.job_type === 'aplus') {
        queries.push('https://labs.google/fx/tools/flow*');
    } else {
        queries.push('https://labs.google.com/pomelli/*');
        queries.push('https://labs.google.com/u/*/pomelli/*');
    }

    let tabs = [];
    for (const q of queries) {
        const found = await chrome.tabs.query({ url: q });
        tabs.push(...found);
    }

    let tab;
    if (tabs.length > 0) {
        tab = tabs[0];
        const targetUrl = buildLandingUrl(job.job_type, tab.url);
        await chrome.tabs.update(tab.id, { active: true });

        // If tab is on a sub-page (e.g. /campaigns/b-xxx), navigate to landing first
        if (tab.url && tab.url !== targetUrl && tab.url !== targetUrl + '/') {
            console.log('[MC-BG] Tab on sub-page, navigating to landing:', targetUrl);
            await chrome.tabs.update(tab.id, { url: targetUrl });
            await waitForTabLoad(tab.id);
            await new Promise(r => setTimeout(r, 10000));  // Angular bootstrap + content script init
        }
    } else {
        const targetUrl = buildLandingUrl(job.job_type, null);
        tab = await chrome.tabs.create({ url: targetUrl });
        await waitForTabLoad(tab.id);
        await new Promise(r => setTimeout(r, 10000));
    }

    await sendJobToTab(tab, job);
}

function getTargetUrl(jobType) {
    switch (jobType) {
        case 'campaign': return 'https://labs.google.com/pomelli/campaigns';
    case 'gemini': return 'https://gemini.google.com/app';
        case 'photoshoot': return 'https://labs.google.com/pomelli/photoshoot';
        case 'flow': case 'aplus': return 'https://labs.google/fx/tools/flow';
        case 'gemini': return 'https://gemini.google.com/app';
        default: return 'https://labs.google.com/pomelli/campaigns';
    }
}

function waitForTabLoad(tabId) {
    return new Promise(resolve => {
        chrome.tabs.onUpdated.addListener(function listener(id, info) {
            if (id === tabId && info.status === 'complete') {
                chrome.tabs.onUpdated.removeListener(listener);
                resolve();
            }
        });
    });
}

// ── Handle messages from popup ──
chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
    if (msg.type === 'START_POLLING') { startPolling(); sendResponse({ polling: true }); }
    else if (msg.type === 'STOP_POLLING') { stopPolling(); sendResponse({ polling: false }); }
    else if (msg.type === 'GET_STATUS') { sendResponse({ polling, profileId }); }
    return true;
});

// ── Handle capability registration from content scripts ──
chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
    if (msg.type === 'ADD_CAPABILITY' && msg.capability) {
        (async () => {
            // Persist to storage so it survives service worker restarts
            const data = await chrome.storage.local.get('extraCapabilities');
            const extras = data.extraCapabilities || [];
            if (!extras.includes(msg.capability)) {
                extras.push(msg.capability);
                await chrome.storage.local.set({ extraCapabilities: extras });
            }
            // Re-register with server
            profileId = profileId || await getProfileId();
            const account = await detectAccount();
            const capabilities = await detectCapabilities();
            try {
                await fetch(`${SERVER}/api/ext/register`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ profile_id: profileId, account, capabilities })
                });
                console.log('[MC-BG] Re-registered with capability:', msg.capability, capabilities);
            } catch (e) {}
        })();
        sendResponse({ ok: true });
        return true;
    }
});

// ── Relay gemini results from content script to Flask ──
chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
    if (msg.type === 'GEMINI_RESULT' && msg.result) {
        fetch(`${SERVER}/api/ext/gemini-result`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                job_id: msg.job_id,
                prompt_type: msg.prompt_type,
                result: msg.result,
                status: 'success'
            })
        }).then(() => console.log('[MC-BG] Gemini result relayed to server'))
          .catch(e => console.error('[MC-BG] Failed to relay gemini result:', e));
        sendResponse({ ok: true });
        return true;
    }
});

// ── Auto-start ──
registerWithServer();
startPolling();

// Re-register every 60s to survive server restarts
setInterval(() => { registerWithServer(); }, 60000);
console.log('[MC-BG] Mr.Creative background worker loaded');

// ── Debugger-based file upload (trusted mouse click + file chooser) ──
chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg.type === 'DEBUGGER_UPLOAD' && sender.tab) {
    (async () => {
      const tabId = sender.tab.id;
      const target = { tabId };
      try {
        // Attach debugger
        await chrome.debugger.attach(target, '1.3');
        console.log('[MC-BG] Debugger attached to tab', tabId);

        // Enable file chooser interception
        await chrome.debugger.sendCommand(target, 'Page.setInterceptFileChooserDialog', { enabled: true });

        // Listen for file chooser event
        const fileChooserPromise = new Promise((resolve) => {
          const listener = (source, method, params) => {
            if (source.tabId === tabId && method === 'Page.fileChooserOpened') {
              chrome.debugger.onEvent.removeListener(listener);
              resolve(params);
            }
          };
          chrome.debugger.onEvent.addListener(listener);
          // Timeout after 10s
          setTimeout(() => { chrome.debugger.onEvent.removeListener(listener); resolve(null); }, 10000);
        });

        // Trusted mouse click at the Upload files button coordinates
        await chrome.debugger.sendCommand(target, 'Input.dispatchMouseEvent', {
          type: 'mousePressed', x: msg.x, y: msg.y, button: 'left', clickCount: 1
        });
        await chrome.debugger.sendCommand(target, 'Input.dispatchMouseEvent', {
          type: 'mouseReleased', x: msg.x, y: msg.y, button: 'left', clickCount: 1
        });
        console.log('[MC-BG] Trusted click dispatched at', msg.x, msg.y);

        // Wait for file chooser
        const chooser = await fileChooserPromise;
        if (chooser) {
          console.log('[MC-BG] File chooser opened, injecting file');
          await chrome.debugger.sendCommand(target, 'DOM.setFileInputFiles', {
            files: [],  // Clear first
            backendNodeId: chooser.backendNodeId
          });
          // Alternative: use Page.handleFileChooser for newer Chrome
          try {
            await chrome.debugger.sendCommand(target, 'Page.handleFileChooser', {
              action: 'accept',
              files: [msg.fileName]
            });
          } catch(e) {
            console.log('[MC-BG] handleFileChooser fallback needed');
          }
        } else {
          console.log('[MC-BG] File chooser did not open');
        }

        // Detach debugger
        await chrome.debugger.detach(target);
        sendResponse({ success: true, chooserOpened: !!chooser });
      } catch (e) {
        console.error('[MC-BG] Debugger upload error:', e.message);
        try { await chrome.debugger.detach(target); } catch(_) {}
        sendResponse({ success: false, error: e.message });
      }
    })();
    return true; // async response
  }
});
