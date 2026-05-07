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
        let tabs = await chrome.tabs.query({ url: 'https://labs.google.com/pomelli/*' });
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
    const caps = [];
    const pomelliTabs = await chrome.tabs.query({ url: 'https://labs.google.com/pomelli/*' });
    const flowTabs = await chrome.tabs.query({ url: 'https://labs.google/fx/*' });

    // If tabs exist or URLs are accessible, add capabilities
    caps.push('campaign', 'photoshoot');  // Pomelli is always accessible
    caps.push('flow');  // Flow too

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
        await dispatchJob(cmd);
    } catch (e) {}
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
    try {
        await chrome.tabs.sendMessage(tab.id, { type: 'RUN_JOB', job });
        console.log('[MC-BG] Job dispatched to tab', tab.id);
        await fetch(`${SERVER}/api/ext/ack`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ job_id: job.job_id, profile_id: profileId })
        });
    } catch (e) {
        console.error('[MC-BG] Dispatch failed, retrying...', e);
        await new Promise(r => setTimeout(r, 5000));
        try { await chrome.tabs.sendMessage(tab.id, { type: 'RUN_JOB', job }); } catch (e2) {}
    }
}

// ── Dispatch job to the right tab ──
async function dispatchJob(job) {
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
            await new Promise(r => setTimeout(r, 5000));  // Angular bootstrap
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
        case 'photoshoot': return 'https://labs.google.com/pomelli/photoshoot';
        case 'flow': case 'aplus': return 'https://labs.google/fx/tools/flow';
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

// ── Auto-start ──
registerWithServer();
startPolling();
console.log('[MC-BG] Mr.Creative background worker loaded');
