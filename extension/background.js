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

// ══ FLOW PASTE + SUBMIT: single debugger session for paste and click ══
chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg.type === 'FLOW_PASTE' && sender.tab) {
    (async () => {
      const tabId = sender.tab.id;
      const target = { tabId };
      try {
        // 1. Write text to clipboard via MAIN world
        await chrome.scripting.executeScript({
          target: { tabId },
          world: 'MAIN',
          func: (text) => navigator.clipboard.writeText(text),
          args: [msg.text]
        });
        console.log('[MC-BG] Clipboard written');
        await new Promise(r => setTimeout(r, 500));

        // 2. Attach debugger once
        await chrome.debugger.attach(target, '1.3');

        // 3. Ctrl+V to paste
        await chrome.debugger.sendCommand(target, 'Input.dispatchKeyEvent', {
          type: 'keyDown', modifiers: 2, key: 'v', code: 'KeyV',
          windowsVirtualKeyCode: 86, nativeVirtualKeyCode: 86
        });
        await new Promise(r => setTimeout(r, 100));
        await chrome.debugger.sendCommand(target, 'Input.dispatchKeyEvent', {
          type: 'keyUp', modifiers: 2, key: 'v', code: 'KeyV',
          windowsVirtualKeyCode: 86, nativeVirtualKeyCode: 86
        });
        console.log('[MC-BG] Ctrl+V done');

        // 4. If submit requested, click via MAIN world (fresh position, no debugger)
        if (msg.doSubmit) {
          // Detach debugger FIRST (before clicking)
          try { await chrome.debugger.detach(target); } catch(_) {}
          console.log('[MC-BG] Debugger detached after paste');

          await new Promise(r => setTimeout(r, 2000 + Math.random() * 1000));

          // Click submit button from page context using multiple approaches
          const [clickResult] = await chrome.scripting.executeScript({
            target: { tabId },
            world: 'MAIN',
            func: () => {
              // Approach 1: Find and click the arrow_forward button with full event chain
              const btns = document.querySelectorAll('button');
              let submitBtn = null;
              for (const b of btns) {
                const icon = b.querySelector('i');
                if (icon && icon.textContent.trim() === 'arrow_forward') {
                  submitBtn = b;
                  break;
                }
              }
              if (!submitBtn) return 'not_found';

              // Dispatch full trusted-like event chain
              submitBtn.dispatchEvent(new PointerEvent('pointerdown', { bubbles: true, cancelable: true, pointerId: 1, pointerType: 'mouse' }));
              submitBtn.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, cancelable: true, button: 0 }));
              submitBtn.dispatchEvent(new PointerEvent('pointerup', { bubbles: true, cancelable: true, pointerId: 1, pointerType: 'mouse' }));
              submitBtn.dispatchEvent(new MouseEvent('mouseup', { bubbles: true, cancelable: true, button: 0 }));
              submitBtn.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, button: 0 }));
              submitBtn.click();

              // Approach 2: Also try Enter on the editor
              const editor = document.querySelector('div[data-slate-editor="true"]');
              if (editor) {
                editor.focus();
                editor.dispatchEvent(new KeyboardEvent('keydown', {
                  key: 'Enter', code: 'Enter', keyCode: 13, which: 13,
                  bubbles: true, cancelable: true
                }));
              }

              return 'clicked';
            }
          });
          console.log('[MC-BG] Submit click result:', clickResult?.result);
          sendResponse({ ok: true, submitClicked: clickResult?.result });
          return;
        }

        // 5. Detach
        await new Promise(r => setTimeout(r, 300));
        try { await chrome.debugger.detach(target); } catch(_) {}
        sendResponse({ ok: true });
      } catch (e) {
        console.error('[MC-BG] FLOW_PASTE error:', e.message);
        try { await chrome.debugger.detach(target); } catch(_) {}
        sendResponse({ ok: false, error: e.message });
      }
    })();
    return true;
  }
});

// ══ FLOW CLICK: debugger trusted mouse click ══
chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg.type === 'FLOW_CLICK' && sender.tab) {
    (async () => {
      const tabId = sender.tab.id;
      const target = { tabId };
      try {
        await chrome.debugger.attach(target, '1.3');
        await chrome.debugger.sendCommand(target, 'Input.dispatchMouseEvent', {
          type: 'mousePressed', x: msg.x, y: msg.y,
          button: 'left', clickCount: 1
        });
        await new Promise(r => setTimeout(r, 50));
        await chrome.debugger.sendCommand(target, 'Input.dispatchMouseEvent', {
          type: 'mouseReleased', x: msg.x, y: msg.y,
          button: 'left', clickCount: 1
        });
        console.log('[MC-BG] Trusted click at', msg.x, msg.y);
        await new Promise(r => setTimeout(r, 300));
        try { await chrome.debugger.detach(target); } catch(_) {}
        sendResponse({ ok: true });
      } catch (e) {
        console.error('[MC-BG] FLOW_CLICK error:', e.message);
        try { await chrome.debugger.detach(target); } catch(_) {}
        sendResponse({ ok: false, error: e.message });
      }
    })();
    return true;
  }
});

// ── Relay lens results from content script to Flask ──
chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
    if (msg.type === 'LENS_RESULT' && msg.result) {
        fetch(`${SERVER}/api/ext/lens-result`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                job_id: msg.job_id,
                result: msg.result,
                status: 'success'
            })
        }).then(() => console.log('[MC-BG] Lens result relayed to server'))
          .catch(e => console.error('[MC-BG] Failed to relay lens result:', e));
        sendResponse({ ok: true });
        return true;
    }
});

// ══ LENS FILE UPLOAD: debugger-based file chooser interception ══
// Like Selenium: save image to disk → trusted click → intercept file chooser → provide file
chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg.type === 'LENS_FILE_UPLOAD' && sender.tab) {
    (async () => {
      const tabId = sender.tab.id;
      const target = { tabId };
      try {
        console.log('[MC-BG] LENS_FILE_UPLOAD: starting');

        // 1. Save image to Downloads via data URI
        const dataUrl = `data:${msg.mimeType};base64,${msg.base64}`;
        const downloadId = await new Promise((resolve, reject) => {
          chrome.downloads.download({
            url: dataUrl,
            filename: 'mc_lens_temp.jpg',
            conflictAction: 'overwrite',
            saveAs: false,
          }, id => {
            if (chrome.runtime.lastError) reject(new Error(chrome.runtime.lastError.message));
            else resolve(id);
          });
        });
        console.log('[MC-BG] Download started, id:', downloadId);

        // Wait for download to complete
        const filePath = await new Promise((resolve, reject) => {
          const timeout = setTimeout(() => reject(new Error('Download timeout')), 15000);
          chrome.downloads.onChanged.addListener(function listener(delta) {
            if (delta.id === downloadId && delta.state) {
              if (delta.state.current === 'complete') {
                chrome.downloads.onChanged.removeListener(listener);
                clearTimeout(timeout);
                chrome.downloads.search({ id: downloadId }, items => {
                  resolve(items[0].filename);
                });
              } else if (delta.state.current === 'interrupted') {
                chrome.downloads.onChanged.removeListener(listener);
                clearTimeout(timeout);
                reject(new Error('Download interrupted'));
              }
            }
          });
        });
        console.log('[MC-BG] Image saved to:', filePath);

        // 2. Attach debugger
        await chrome.debugger.attach(target, '1.3');
        console.log('[MC-BG] Debugger attached');

        // 3. Trusted drag-and-drop onto the drop zone
        const dragData = {
          items: [{ mimeType: msg.mimeType || 'image/jpeg', data: '' }],
          files: [filePath],
          dragOperationsMask: 1
        };
        const x = msg.buttonX;
        const y = msg.buttonY;

        await chrome.debugger.sendCommand(target, 'Input.dispatchDragEvent', {
          type: 'dragEnter', x, y, data: dragData, modifiers: 0
        });
        await new Promise(r => setTimeout(r, 200));
        await chrome.debugger.sendCommand(target, 'Input.dispatchDragEvent', {
          type: 'dragOver', x, y, data: dragData, modifiers: 0
        });
        await new Promise(r => setTimeout(r, 200));
        await chrome.debugger.sendCommand(target, 'Input.dispatchDragEvent', {
          type: 'drop', x, y, data: dragData, modifiers: 0
        });
        console.log('[MC-BG] Trusted drag-and-drop dispatched with file:', filePath);

        // 7. Detach debugger after a delay
        setTimeout(async () => {
          try { await chrome.debugger.detach(target); } catch(_) {}
          // Clean up temp file
          try { chrome.downloads.removeFile(downloadId); chrome.downloads.erase({ id: downloadId }); } catch(_) {}
        }, 5000);

        sendResponse({ ok: true, filePath });
      } catch (e) {
        console.error('[MC-BG] LENS_FILE_UPLOAD error:', e.message);
        try { await chrome.debugger.detach(target); } catch(_) {}
        sendResponse({ ok: false, error: e.message });
      }
    })();
    return true; // async sendResponse
  }
});

// ── Auto-start ──
registerWithServer();
startPolling();

// Re-register every 60s to survive server restarts
setInterval(() => { registerWithServer(); }, 60000);
console.log('[MC-BG] Mr.Creative background worker loaded');

// ══ OVERRIDE showOpenFilePicker in page MAIN world (bypasses CSP) ══
chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg.type === 'OVERRIDE_PICKER' && sender.tab) {
    chrome.scripting.executeScript({
      target: { tabId: sender.tab.id },
      world: 'MAIN',
      func: (b64, fileName, mimeType) => {
        window.__mcPickerData = { base64: b64, fileName, mimeType };
        console.log('[Mr.Creative] Picker data loaded:', fileName, b64.length, 'chars');
      },
      args: [msg.base64, msg.fileName, msg.mimeType]
    }).then(() => sendResponse({ ok: true }))
      .catch(e => sendResponse({ ok: false, error: e.message }));
    return true;
  }
});

// ══ TRUSTED CLICK via chrome.debugger (provides user activation) ══
chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg.type === 'TRUSTED_CLICK' && sender.tab) {
    (async () => {
      const tabId = sender.tab.id;
      const target = { tabId };
      try {
        await chrome.debugger.attach(target, '1.3');
        await chrome.debugger.sendCommand(target, 'Input.dispatchMouseEvent', {
          type: 'mousePressed', x: msg.x, y: msg.y, button: 'left', clickCount: 1
        });
        await chrome.debugger.sendCommand(target, 'Input.dispatchMouseEvent', {
          type: 'mouseReleased', x: msg.x, y: msg.y, button: 'left', clickCount: 1
        });
        console.log('[MC-BG] Trusted click dispatched at', msg.x, msg.y);
        // Detach after a delay so the click event propagates
        setTimeout(async () => {
          try { await chrome.debugger.detach(target); } catch(_) {}
        }, 3000);
        sendResponse({ ok: true });
      } catch (e) {
        console.error('[MC-BG] Trusted click error:', e.message);
        try { await chrome.debugger.detach(target); } catch(_) {}
        sendResponse({ ok: false, error: e.message });
      }
    })();
    return true;
  }
});

// ══ TRUSTED PASTE via chrome.debugger (Ctrl+V with user activation) ══
chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg.type === 'TRUSTED_PASTE' && sender.tab) {
    (async () => {
      const tabId = sender.tab.id;
      const target = { tabId };
      try {
        await chrome.debugger.attach(target, '1.3');
        // Ctrl+V keydown
        await chrome.debugger.sendCommand(target, 'Input.dispatchKeyEvent', {
          type: 'keyDown',
          modifiers: 2,
          key: 'v',
          code: 'KeyV',
          windowsVirtualKeyCode: 86,
          nativeVirtualKeyCode: 86
        });
        // Ctrl+V keyup
        await chrome.debugger.sendCommand(target, 'Input.dispatchKeyEvent', {
          type: 'keyUp',
          modifiers: 2,
          key: 'v',
          code: 'KeyV',
          windowsVirtualKeyCode: 86,
          nativeVirtualKeyCode: 86
        });
        console.log('[MC-BG] Trusted Ctrl+V dispatched');
        setTimeout(async () => {
          try { await chrome.debugger.detach(target); } catch(_) {}
        }, 3000);
        sendResponse({ ok: true });
      } catch (e) {
        console.error('[MC-BG] Trusted paste error:', e.message);
        try { await chrome.debugger.detach(target); } catch(_) {}
        sendResponse({ ok: false, error: e.message });
      }
    })();
    return true;
  }
});

// ══ CLIPBOARD PASTE: focus tab → write image to clipboard → Ctrl+V ══
chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg.type === 'CLIPBOARD_PASTE' && sender.tab) {
    (async () => {
      const tabId = sender.tab.id;
      const target = { tabId };
      try {
        // 1. Focus the tab (required for clipboard API)
        await chrome.tabs.update(tabId, { active: true });
        await new Promise(r => setTimeout(r, 500));
        console.log('[MC-BG] Tab focused');

        // 2. Write image to clipboard in MAIN world
        await chrome.scripting.executeScript({
          target: { tabId },
          world: 'MAIN',
          func: async (b64, mimeType) => {
            // Convert base64 to PNG blob (clipboard requires PNG)
            const binary = atob(b64);
            const bytes = new Uint8Array(binary.length);
            for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
            const origBlob = new Blob([bytes], { type: mimeType });

            // Convert to PNG
            const bmp = await createImageBitmap(origBlob);
            const canvas = new OffscreenCanvas(bmp.width, bmp.height);
            const ctx = canvas.getContext('2d');
            ctx.drawImage(bmp, 0, 0);
            const pngBlob = await canvas.convertToBlob({ type: 'image/png' });

            // Focus the editor first
            const editor = document.querySelector('div.ql-editor.textarea');
            if (editor) editor.focus();

            // Write to clipboard
            const item = new ClipboardItem({ 'image/png': pngBlob });
            await navigator.clipboard.write([item]);
            console.log('[Mr.Creative] Image written to clipboard:', pngBlob.size, 'bytes');
          },
          args: [msg.base64, msg.mimeType]
        });
        console.log('[MC-BG] Clipboard write done');

        // 3. Small delay then Ctrl+V via debugger
        await new Promise(r => setTimeout(r, 300));
        await chrome.debugger.attach(target, '1.3');
        await chrome.debugger.sendCommand(target, 'Input.dispatchKeyEvent', {
          type: 'keyDown', modifiers: 2, key: 'v', code: 'KeyV',
          windowsVirtualKeyCode: 86, nativeVirtualKeyCode: 86
        });
        await chrome.debugger.sendCommand(target, 'Input.dispatchKeyEvent', {
          type: 'keyUp', modifiers: 2, key: 'v', code: 'KeyV',
          windowsVirtualKeyCode: 86, nativeVirtualKeyCode: 86
        });
        console.log('[MC-BG] Ctrl+V dispatched');
        setTimeout(async () => {
          try { await chrome.debugger.detach(target); } catch(_) {}
        }, 3000);
        sendResponse({ ok: true });
      } catch (e) {
        console.error('[MC-BG] Clipboard paste error:', e.message);
        try { await chrome.debugger.detach(target); } catch(_) {}
        sendResponse({ ok: false, error: e.message });
      }
    })();
    return true;
  }
});
