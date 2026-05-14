// ═══════════════════════════════════════════
// LENS BOT — Google Lens upload + AI Mode prompt generation
// Replaces Gemini bot for image-based prompt generation
// DOM selectors verified May 14 2026
// ═══════════════════════════════════════════

const LSEL = {
  // Google Lens overlay (google.com/?olud)
  dropZone:      'div.BH9rn',
  uploadLink:    'span.DV7the[role="button"]',
  // Google Search AI Mode
  aiModeTab:     'span[jsname="KliEFc"]',
  askAnything:   'textarea.ITIRGe[placeholder="Ask anything"]',
  askAnythingFB: 'textarea[placeholder="Ask anything"]',
  // AI Mode response
  responseBox:   'div.zkL70c',
  copyBtn:       'button[aria-label="Copy text"]',
  goodBtn:       'button[aria-label="Good response"]',
  badBtn:        'button[aria-label="Bad response"]',
  moreBtn:       'button[aria-label="More options"]',
};

const STORAGE_KEY = 'mc_lens_pending';
const TAG = '[Mr.Creative][Lens]';
const SERVER = 'http://localhost:5000';

const log  = (...a) => { MC.log(TAG, ...a); console.log(TAG, ...a); };
const warn = (...a) => { MC.log(TAG, '[WARN]', ...a); console.warn(TAG, ...a); };

// Register lens capability
try {
  chrome.runtime.sendMessage({ type: 'ADD_CAPABILITY', capability: 'lens' });
} catch (e) {}


// ── Detect which phase we're in ──
function detectPhase() {
  const url = location.href;
  // Phase 1: Google Lens overlay (triggered by ?olud param or lens.google.com)
  if (url.includes('?olud') || url.includes('&olud') || location.hostname === 'lens.google.com') {
    return 'upload';
  }
  // Phase 2: Google Search results (after Lens upload) or AI Mode
  if (url.includes('google.com/search')) {
    return 'aimode';
  }
  return 'idle';
}


// ═══════════════════════════════════════════
// PHASE 1: UPLOAD IMAGE TO GOOGLE LENS
// ═══════════════════════════════════════════

async function phase1_upload(job) {
  const { image_url, image_filename, job_id, prompt_text } = job;
  log('Phase 1: uploading image to Google Lens');

  await MC.sendStatus(job_id, 'navigating', 'Opening Google Lens...');

  // Wait for the drop zone to appear
  let dropZone = null;
  for (let i = 0; i < 30; i++) {
    dropZone = document.querySelector(LSEL.dropZone);
    if (dropZone && dropZone.offsetHeight > 0) break;
    await MC.sleep(1000);
  }
  if (!dropZone) throw new Error('Google Lens drop zone not found');
  log('Drop zone found');

  // Fetch the image from Flask
  await MC.sendStatus(job_id, 'entering_prompt', 'Fetching product image...');
  const resp = await fetch(image_url);
  if (!resp.ok) throw new Error('Failed to fetch image: ' + resp.status);
  const blob = await resp.blob();
  const file = new File([blob], image_filename || 'product.jpg', { type: blob.type || 'image/jpeg' });
  log('Image fetched:', file.size, 'bytes');

  // Save job state to storage BEFORE upload (navigation will destroy this context)
  await new Promise(r => chrome.storage.local.set({
    [STORAGE_KEY]: {
      job_id,
      prompt_text,
      image_url,
      phase: 'waiting_aimode',
      timestamp: Date.now(),
    }
  }, r));
  log('Job state saved to storage');

  // Drag-and-drop onto the Lens zone
  await MC.sendStatus(job_id, 'entering_prompt', 'Uploading image to Google Lens...');
  const dt = new DataTransfer();
  dt.items.add(file);

  dropZone.dispatchEvent(new DragEvent('dragenter', { bubbles: true, cancelable: true, dataTransfer: dt }));
  await MC.sleep(200);
  dropZone.dispatchEvent(new DragEvent('dragover',  { bubbles: true, cancelable: true, dataTransfer: dt }));
  await MC.sleep(200);
  dropZone.dispatchEvent(new DragEvent('drop',      { bubbles: true, cancelable: true, dataTransfer: dt }));
  log('Drag-and-drop dispatched');

  // Wait a bit to see if the page reacts
  await MC.sleep(3000);

  // Check if page navigated (the drop might trigger navigation to search results)
  // If still on the same page, try the fallback: click "upload a file" + MutationObserver
  if (document.querySelector(LSEL.dropZone)) {
    log('Drop zone still visible — trying click upload fallback');
    await fallback_clickUpload(file, job_id);
  }

  // Page should navigate to google.com/search — Phase 2 picks up from storage
  log('Phase 1 complete — waiting for redirect to search results');
}


async function fallback_clickUpload(file, job_id) {
  // Watch for dynamically created <input type="file">
  const inputPromise = new Promise((resolve) => {
    const observer = new MutationObserver((mutations) => {
      for (const m of mutations) {
        for (const node of m.addedNodes) {
          if (node.nodeType !== 1) continue;
          const input = node.tagName === 'INPUT' && node.type === 'file'
            ? node
            : node.querySelector?.('input[type="file"]');
          if (input) {
            observer.disconnect();
            resolve(input);
            return;
          }
        }
      }
    });
    observer.observe(document.body, { childList: true, subtree: true });
    // Timeout after 10s
    setTimeout(() => { observer.disconnect(); resolve(null); }, 10000);
  });

  // Click "upload a file"
  const uploadLink = document.querySelector(LSEL.uploadLink);
  if (uploadLink) {
    MC.click(uploadLink);
    log('Clicked "upload a file" link');
  }

  const input = await inputPromise;
  if (input) {
    log('File input found! Injecting file');
    const dt = new DataTransfer();
    dt.items.add(file);
    input.files = dt.files;
    input.dispatchEvent(new Event('change', { bubbles: true }));
    await MC.sleep(2000);
  } else {
    warn('No file input appeared after clicking upload — drag-and-drop might have worked');
  }
}


// ═══════════════════════════════════════════
// PHASE 2: AI MODE INTERACTION
// ═══════════════════════════════════════════

async function phase2_aimode(pendingJob) {
  const { job_id, prompt_text } = pendingJob;
  log('Phase 2: AI Mode interaction for job', job_id);

  await MC.sendStatus(job_id, 'generating', 'Search results loaded...');

  // Wait for page to fully load
  await MC.sleep(3000);

  // Step 1: Click on AI Mode tab if not already in AI Mode
  const aiTab = document.querySelector(LSEL.aiModeTab);
  if (aiTab && aiTab.offsetHeight > 0) {
    log('Found AI Mode tab — clicking');
    MC.click(aiTab);
    await MC.sleep(3000);
  } else {
    log('AI Mode tab not found — might already be in AI Mode or need to scroll');
    // Try scrolling down to find it
    window.scrollTo(0, document.body.scrollHeight);
    await MC.sleep(2000);
    const aiTab2 = document.querySelector(LSEL.aiModeTab);
    if (aiTab2 && aiTab2.offsetHeight > 0) {
      MC.click(aiTab2);
      await MC.sleep(3000);
    }
  }

  // Step 2: Find "Ask anything" textarea
  await MC.sendStatus(job_id, 'generating', 'Finding AI Mode input...');
  let textarea = null;
  for (let i = 0; i < 20; i++) {
    textarea = document.querySelector(LSEL.askAnything) ||
               document.querySelector(LSEL.askAnythingFB);
    if (textarea && textarea.offsetHeight > 0) break;
    await MC.sleep(1000);
  }
  if (!textarea) throw new Error('AI Mode textarea not found');
  log('Textarea found');

  // Step 3: Type the mega-prompt
  await MC.sendStatus(job_id, 'entering_prompt', 'Typing prompt...');
  textarea.scrollIntoView({ block: 'center' });
  await MC.sleep(500);
  textarea.focus();
  await MC.sleep(300);
  textarea.value = prompt_text;
  textarea.dispatchEvent(new Event('input', { bubbles: true }));
  textarea.dispatchEvent(new Event('change', { bubbles: true }));
  await MC.sleep(500);

  // Verify text was entered
  if (textarea.value.length < 20) {
    warn('Value set failed, trying keyboard simulation');
    textarea.focus();
    // Fallback: insert via execCommand
    document.execCommand('insertText', false, prompt_text);
    await MC.sleep(500);
  }
  log('Prompt entered, length:', textarea.value.length);

  // Step 4: Find and click submit/send button
  await MC.sendStatus(job_id, 'generating', 'Submitting prompt...');
  let submitted = false;

  // Try pressing Enter (Google AI Mode submits on Enter)
  textarea.dispatchEvent(new KeyboardEvent('keydown', {
    key: 'Enter', code: 'Enter', keyCode: 13, which: 13,
    bubbles: true, cancelable: true
  }));
  await MC.sleep(500);

  // Also look for a send/submit button near the textarea
  const sendBtn = textarea.closest('div')?.querySelector('button[aria-label*="Send"], button[aria-label*="Search"], button[aria-label*="submit"]') ||
                  document.querySelector('button[aria-label="Send"]');
  if (sendBtn && sendBtn.offsetHeight > 0) {
    MC.click(sendBtn);
    submitted = true;
    log('Clicked send button');
  } else {
    // Try finding any nearby button that could be submit
    const parent = textarea.closest('div.esoFne') || textarea.parentElement;
    if (parent) {
      const btns = parent.querySelectorAll('button');
      for (const btn of btns) {
        if (btn.offsetHeight > 0 && !btn.getAttribute('aria-label')?.includes('microphone')) {
          MC.click(btn);
          submitted = true;
          log('Clicked nearby button');
          break;
        }
      }
    }
  }

  if (!submitted) {
    // Last resort: press Enter via KeyboardEvent on the textarea
    textarea.focus();
    textarea.dispatchEvent(new KeyboardEvent('keydown', {
      key: 'Enter', code: 'Enter', keyCode: 13, which: 13,
      bubbles: true
    }));
    textarea.dispatchEvent(new KeyboardEvent('keypress', {
      key: 'Enter', code: 'Enter', keyCode: 13, which: 13,
      bubbles: true
    }));
    textarea.dispatchEvent(new KeyboardEvent('keyup', {
      key: 'Enter', code: 'Enter', keyCode: 13, which: 13,
      bubbles: true
    }));
    log('Dispatched Enter key events');
  }

  // Step 5: Wait for response to complete
  await MC.sendStatus(job_id, 'generating', 'Waiting for AI Mode response...');
  await waitForResponse(job_id);

  // Step 6: Extract response text
  await MC.sendStatus(job_id, 'downloading', 'Extracting prompts...');
  const result = extractResponse();
  log('Response extracted:', result.length, 'chars');

  // Step 7: Send result to Flask via background.js
  chrome.runtime.sendMessage({
    type: 'LENS_RESULT',
    job_id: job_id,
    result: result
  });

  // Clear pending job from storage
  chrome.storage.local.remove(STORAGE_KEY);

  await MC.sendStatus(job_id, 'complete', 'Prompts generated successfully');
  log('Phase 2 complete!');
}


async function waitForResponse(job_id, timeout = 180000) {
  // Wait for the Copy button to appear — signals response is fully generated
  await MC.sleep(5000); // Initial wait for response to start
  const start = Date.now();

  while (Date.now() - start < timeout) {
    // Check for Copy button (appears after response is complete)
    const copyBtn = document.querySelector(LSEL.copyBtn);
    if (copyBtn && copyBtn.offsetHeight > 0) {
      // Also check that the response box has substantial content
      const responseBoxes = document.querySelectorAll(LSEL.responseBox);
      const lastBox = responseBoxes[responseBoxes.length - 1];
      if (lastBox && lastBox.textContent.trim().length > 100) {
        log('Response complete — Copy button visible, content length:', lastBox.textContent.trim().length);
        await MC.sleep(2000); // Extra buffer for any final rendering
        return;
      }
    }

    // Also check for Good/Bad response buttons as completion signal
    const goodBtn = document.querySelector(LSEL.goodBtn);
    if (goodBtn && goodBtn.offsetHeight > 0) {
      log('Response complete — feedback buttons visible');
      await MC.sleep(2000);
      return;
    }

    // Update status
    if (Date.now() - start > 30000) {
      await MC.sendStatus(job_id, 'generating', 'Still generating prompts...');
    }

    await MC.sleep(3000);
  }

  warn('Response timeout — extracting whatever is available');
}


function extractResponse() {
  // Try to get code block content first (the ===PROMPT=== formatted response)
  const codeBlocks = document.querySelectorAll('code, pre, .code-container');
  for (const block of codeBlocks) {
    const text = block.textContent.trim();
    if (text.length > 100 && text.includes('===PROMPT===')) {
      log('Found code block with ===PROMPT=== markers');
      return text;
    }
  }

  // Try response container
  const responseBoxes = document.querySelectorAll(LSEL.responseBox);
  if (responseBoxes.length > 0) {
    const lastBox = responseBoxes[responseBoxes.length - 1];
    const text = lastBox.textContent.trim();
    if (text.length > 100) {
      log('Extracted from response container, length:', text.length);
      return text;
    }
  }

  // Fallback: look for any large text block near the action buttons
  const copyBtn = document.querySelector(LSEL.copyBtn);
  if (copyBtn) {
    // Walk up to find the response container
    let parent = copyBtn.closest('div.zkL70c') || copyBtn.closest('[class*="response"]');
    if (parent) {
      const text = parent.textContent.trim();
      if (text.length > 100) return text;
    }
  }

  throw new Error('No response text found in AI Mode');
}


// ═══════════════════════════════════════════
// DIRECT POLLER — Picks up lens jobs from Flask
// ═══════════════════════════════════════════

(async function lensPoller() {
  let busy = false;

  async function check() {
    if (busy) return;

    const phase = detectPhase();

    // Phase 2: Check storage for pending job (cross-page state)
    if (phase === 'aimode') {
      try {
        const data = await new Promise(r => chrome.storage.local.get(STORAGE_KEY, r));
        const pending = data[STORAGE_KEY];
        if (pending && pending.phase === 'waiting_aimode') {
          // Check freshness (expire after 5 minutes)
          if (Date.now() - pending.timestamp > 300000) {
            log('Pending job expired, clearing');
            chrome.storage.local.remove(STORAGE_KEY);
            return;
          }
          busy = true;
          log('Found pending job in storage:', pending.job_id);
          try {
            await phase2_aimode(pending);
          } catch (e) {
            log('Phase 2 error:', e.message);
            await MC.sendStatus(pending.job_id, 'error', 'AI Mode failed: ' + e.message);
            chrome.storage.local.remove(STORAGE_KEY);
          }
          busy = false;
          return;
        }
      } catch (e) {}
    }

    // Phase 1: Poll Flask for new lens jobs
    if (phase === 'upload') {
      try {
        const res = await fetch(SERVER + '/api/ext/pending-for-tab?type=lens');
        if (!res.ok || res.status === 204) return;
        const job = await res.json();
        if (!job || !job.job_id || job.job_type !== 'lens') return;
        busy = true;
        log('Direct poll: picked up lens job', job.job_id);
        try {
          // Ack the job
          const pid = await new Promise(r =>
            chrome.storage.local.get('profileId', d => r(d.profileId || 'lens_direct')));
          await fetch(SERVER + '/api/ext/ack', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ job_id: job.job_id, profile_id: pid })
          });
          await phase1_upload(job);
        } catch (e) {
          log('Phase 1 error:', e.message);
          await MC.sendStatus(job.job_id, 'error', 'Lens upload failed: ' + e.message);
          chrome.storage.local.remove(STORAGE_KEY);
        }
        busy = false;
      } catch (e) { busy = false; }
    }
  }

  setInterval(check, 3000);
  setTimeout(check, 2000);
  log('Lens bot loaded, phase:', detectPhase());
})();


// ── Handle RUN_JOB messages from background.js ──
chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg.type === 'RUN_JOB' && msg.job && msg.job.job_type === 'lens') {
    const phase = detectPhase();
    if (phase === 'upload') {
      phase1_upload(msg.job).catch(e => {
        log('RUN_JOB Phase 1 error:', e.message);
        MC.sendStatus(msg.job.job_id, 'error', 'Lens upload failed: ' + e.message);
      });
    }
    sendResponse({ ok: true });
  }
  return true;
});
