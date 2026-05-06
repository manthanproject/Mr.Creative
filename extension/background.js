// ═══════════════════════════════════════════
// Mr.Creative Extension — Background Service Worker
// Polls Flask server for commands, dispatches to content scripts
// ═══════════════════════════════════════════

const SERVER = 'http://localhost:5000';
let polling = false;
let pollInterval = null;

// ── Start polling for commands ──
function startPolling() {
  if (polling) return;
  polling = true;
  pollInterval = setInterval(checkForCommand, 3000);
  console.log('[MC-BG] Polling started');
}

function stopPolling() {
  polling = false;
  if (pollInterval) clearInterval(pollInterval);
  console.log('[MC-BG] Polling stopped');
}

// ── Check server for pending command ──
async function checkForCommand() {
  try {
    const res = await fetch(`${SERVER}/api/ext/command`);
    if (!res.ok) return;

    const cmd = await res.json();
    if (!cmd || !cmd.job_id) return;

    console.log('[MC-BG] Received command:', cmd.job_type, cmd.job_id);
    await dispatchJob(cmd);
  } catch (e) {
    // Server not running — silently retry
  }
}

// ── Dispatch job to the right tab ──
async function dispatchJob(job) {
  const targetUrl = getTargetUrl(job.job_type);

  // Find existing tab or create new one
  const tabs = await chrome.tabs.query({ url: targetUrl + '*' });
  let tab;

  if (tabs.length > 0) {
    tab = tabs[0];
    await chrome.tabs.update(tab.id, { active: true });
    // Navigate if needed
    if (job.job_type === 'campaign' && !tab.url.includes('/campaigns')) {
      await chrome.tabs.update(tab.id, { url: targetUrl });
      await waitForTabLoad(tab.id);
    }
  } else {
    tab = await chrome.tabs.create({ url: targetUrl });
    await waitForTabLoad(tab.id);
    // Extra wait for Angular bootstrap
    await new Promise(r => setTimeout(r, 10000));
  }

  // Send job to content script
  try {
    await chrome.tabs.sendMessage(tab.id, { type: 'RUN_JOB', job });
    console.log('[MC-BG] Job dispatched to tab', tab.id);

    // Acknowledge to server
    await fetch(`${SERVER}/api/ext/ack`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ job_id: job.job_id })
    });
  } catch (e) {
    console.error('[MC-BG] Failed to dispatch:', e);
    // Content script might not be loaded yet — retry
    await new Promise(r => setTimeout(r, 5000));
    try {
      await chrome.tabs.sendMessage(tab.id, { type: 'RUN_JOB', job });
    } catch (e2) {
      console.error('[MC-BG] Retry failed:', e2);
    }
  }
}

// ── Get target URL for job type ──
function getTargetUrl(jobType) {
  switch (jobType) {
    case 'campaign': return 'https://labs.google.com/pomelli/campaigns';
    case 'photoshoot': return 'https://labs.google.com/pomelli/photoshoot';
    case 'flow':
    case 'aplus': return 'https://labs.google/fx/tools/flow';
    default: return 'https://labs.google.com/pomelli/campaigns';
  }
}

// ── Wait for tab to finish loading ──
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
  if (msg.type === 'START_POLLING') {
    startPolling();
    sendResponse({ polling: true });
  } else if (msg.type === 'STOP_POLLING') {
    stopPolling();
    sendResponse({ polling: false });
  } else if (msg.type === 'GET_STATUS') {
    sendResponse({ polling });
  }
  return true;
});

// Auto-start polling
startPolling();
console.log('[MC-BG] Mr.Creative background worker loaded');
