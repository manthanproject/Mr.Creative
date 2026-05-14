/**
 * Mr.Creative — Flow Bot (Content Script)
 * Runs on: https://labs.google/fx/tools/flow*
 *
 * Complete pipeline:
 *   1. Open settings → set 1x count + aspect ratio
 *   2. Upload reference image (first prompt) / select from asset library (prompts 2-N)
 *   3. Type prompt → submit → wait for generation
 *   4. After all prompts: open each image edit view → download → back
 *   5. Signal completion with download count to Flask
 *
 * Relies on utils.js (MC.log, MC.sendStatus, MC.sleep, MC.SERVER)
 */

(function () {
  'use strict';

  // ── CONSTANTS ────────────────────────────────────────────────────────────
  const TAG       = '[Mr.Creative][Flow]';
  const POLL      = 400;           // ms between DOM checks
  const GEN_TIMEOUT  = 180_000;    // 3 min max per image generation
  const DL_TIMEOUT   = 90_000;     // 1.5 min max per download (upscale)
  const REF_TIMEOUT  = 45_000;     // 45s max for ref image processing
  const ELEM_TIMEOUT = 12_000;     // 12s max to find a DOM element

  const humanDelay = () => MC.sleep(2000 + Math.random() * 3000);

  // ── LOGGING ──────────────────────────────────────────────────────────────
  const log  = (...a) => { MC.log(TAG, ...a); console.log(TAG, ...a); };
  const warn = (...a) => { MC.log(TAG, '[WARN]', ...a); console.warn(TAG, ...a); };
  const err  = (...a) => { MC.log(TAG, '[ERR]', ...a);  console.error(TAG, ...a); };

  // ── DOM UTILITIES ────────────────────────────────────────────────────────

  /** querySelector with fallback list */
  function $(sels, ctx = document) {
    if (typeof sels === 'string') sels = [sels];
    for (const s of sels) { try { const e = ctx.querySelector(s); if (e) return e; } catch(_){} }
    return null;
  }

  /** querySelectorAll with fallback list, returns flat array */
  function $$(sels, ctx = document) {
    if (typeof sels === 'string') sels = [sels];
    const out = [];
    for (const s of sels) { try { ctx.querySelectorAll(s).forEach(e => out.push(e)); } catch(_){} }
    return out;
  }

  /** Find the first element whose trimmed textContent includes `text` (case-insensitive) */
  function findByText(text, tags = 'button,div,span,a,label,li,p', ctx = document) {
    const low = text.toLowerCase();
    for (const el of ctx.querySelectorAll(tags)) {
      // Only check direct / shallow text to avoid matching deep nested containers
      const t = el.textContent.trim().toLowerCase();
      if (t === low || (t.length < low.length + 30 && t.includes(low))) return el;
    }
    return null;
  }

  /** Poll until finderFn() returns truthy, then return it */
  async function waitFor(finderFn, timeout = ELEM_TIMEOUT, label = '?') {
    const t0 = Date.now();
    while (Date.now() - t0 < timeout) {
      const el = finderFn();
      if (el) return el;
      await MC.sleep(POLL);
    }
    throw new Error(`Timeout (${(timeout / 1000).toFixed(0)}s) waiting for: ${label}`);
  }

  /** Scroll into view + click + dispatch MouseEvent */
  async function click(el) {
    el.scrollIntoView({ behavior: 'instant', block: 'center' });
    await MC.sleep(150 + Math.random() * 200);
    el.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }));
    el.dispatchEvent(new MouseEvent('mouseup',   { bubbles: true }));
    el.dispatchEvent(new MouseEvent('click',     { bubbles: true }));
  }

  /** Type text into input/textarea/contenteditable */
  async function typeText(el, text) {
    el.focus();
    await MC.sleep(100);

    if (el.tagName === 'TEXTAREA' || el.tagName === 'INPUT') {
      // Native input
      const nativeSetter = Object.getOwnPropertyDescriptor(
        window.HTMLTextAreaElement.prototype, 'value'
      )?.set || Object.getOwnPropertyDescriptor(
        window.HTMLInputElement.prototype, 'value'
      )?.set;
      if (nativeSetter) nativeSetter.call(el, text);
      else el.value = text;
      el.dispatchEvent(new Event('input', { bubbles: true }));
      el.dispatchEvent(new Event('change', { bubbles: true }));
    } else {
      // contenteditable — use execCommand for React compat
      el.focus();
      document.execCommand('selectAll', false, null);
      document.execCommand('delete', false, null);
      document.execCommand('insertText', false, text);
    }
    await MC.sleep(100);
  }

  /** Fetch image URL → File object */
  async function urlToFile(url, filename = 'reference.png') {
    const resp = await fetch(url);
    if (!resp.ok) throw new Error(`Fetch failed: ${resp.status} ${url}`);
    const blob = await resp.blob();
    return new File([blob], filename, { type: blob.type || 'image/png' });
  }

  // ── PAGE DETECTION ───────────────────────────────────────────────────────

  const isProjectPage = () => /\/flow\/project\/[^/]+\/?$/.test(location.pathname);
  const isEditPage    = () => /\/flow\/project\/[^/]+\/edit\//.test(location.pathname);
  const isDashboard   = () => /\/flow\/?$/.test(location.pathname) && !location.pathname.includes('/project/');

  // ── ELEMENT FINDERS (try multiple strategies) ────────────────────────────

  function findPromptBar() {
    return $([
      'textarea[placeholder*="want to create"]',
      'textarea[placeholder*="want to change"]',
      'input[placeholder*="want to create"]',
      'input[placeholder*="want to change"]',
      'div[contenteditable="true"][data-placeholder]',
      '[role="textbox"]',
      'div[contenteditable="true"]',
    ]);
  }

  function findSubmitBtn() {
    // The circular arrow button at the far right of the prompt bar
    return $([
      'button[aria-label*="Create" i]',
      'button[aria-label*="Submit" i]',
      'button[aria-label*="Send" i]',
      'button[aria-label*="Generate" i]',
      'button[type="submit"]',
    ]) || (() => {
      // Fallback: last button inside the bottom bar that contains the prompt
      const bar = findPromptBar()?.closest('form, [class*="bar"], [class*="prompt"], [class*="input"], [class*="composer"]');
      if (!bar) return null;
      const btns = bar.querySelectorAll('button');
      // The submit is the rightmost / last button
      for (let i = btns.length - 1; i >= 0; i--) {
        // Skip the + button (has "add" or tiny size)
        const lbl = (btns[i].getAttribute('aria-label') || btns[i].textContent || '').toLowerCase();
        if (lbl.includes('add') || lbl === '+') continue;
        return btns[i];
      }
      return null;
    })();
  }

  function findPlusBtn() {
    // The + button left of the prompt bar
    return $([
      'button[aria-label*="Add" i]',
      'button[aria-label*="reference" i]',
      'button[aria-label*="attach" i]',
      'button[aria-label*="upload" i]',
    ]) || (() => {
      const bar = findPromptBar()?.closest('form, [class*="bar"], [class*="prompt"], [class*="input"], [class*="composer"]');
      if (!bar) return null;
      const btns = bar.querySelectorAll('button');
      for (const b of btns) {
        const t = b.textContent.trim();
        if (t === '+' || t === '\uFF0B') return b;          // + or fullwidth +
        if (b.querySelector('svg') && b === btns[0]) return b; // first icon button
      }
      return null;
    })();
  }

  function findSettingsArea() {
    // Click on "Nano Banana" / count area to open the settings popup
    return findByText('Nano Banana')
        || findByText('x4')
        || findByText('x3')
        || findByText('x2')
        || findByText('1x');
  }

  function findDownloadBtn() {
    return $([
      'button[aria-label*="ownload" i]',
      'a[aria-label*="ownload" i]',
      'button[title*="ownload" i]',
    ]) || (() => {
      // In the edit view toolbar (top-right area), the download icon (arrow-down)
      const btns = $$('header button, [class*="toolbar"] button, [class*="action"] button');
      for (const b of btns) {
        const svg = b.querySelector('svg');
        if (!svg) continue;
        // download icon usually has an arrow-down path
        const paths = svg.querySelectorAll('path');
        for (const p of paths) {
          const d = (p.getAttribute('d') || '').toLowerCase();
          if (d.includes('m') && (d.includes('v') || d.includes('l')) && b.offsetWidth < 60) return b;
        }
      }
      return null;
    })();
  }

  function findBackBtn() {
    return $([
      'button[aria-label*="ack" i]',
      'a[aria-label*="ack" i]',
      'button[aria-label*="eturn" i]',
    ]) || (() => {
      // First button in the header / top-left area — usually the back arrow
      const topBtns = $$('header button, [class*="toolbar"] button:first-child, [class*="header"] button');
      return topBtns[0] || null;
    })();
  }

  // ── FLOW BOT ACTIONS ────────────────────────────────────────────────────

  /** Step 1 — Open settings popup, set count to 1x (and optional aspect ratio) */
  async function setSettings(count = 1, aspectRatio) {
    log('Setting count →', count, aspectRatio ? `aspect → ${aspectRatio}` : '');

    // Open the settings popup
    const area = await waitFor(findSettingsArea, ELEM_TIMEOUT, 'settings area');
    await click(area);
    await MC.sleep(800);

    // --- Count ---
    const countLabel = count === 1 ? '1x' : `x${count}`;
    const countBtn = await waitFor(() => {
      // In the popup, find buttons labelled 1x / x2 / x3 / x4
      const btns = $$('button');
      for (const b of btns) {
        const t = b.textContent.trim();
        if (t === countLabel) return b;
      }
      return null;
    }, 5000, `count button "${countLabel}"`);
    await click(countBtn);
    log(`Count set to ${countLabel}`);
    await MC.sleep(300);

    // --- Aspect ratio ---
    if (aspectRatio) {
      const arBtn = findByText(aspectRatio, 'button');
      if (arBtn) { await click(arBtn); log(`Aspect ratio set to ${aspectRatio}`); }
      else warn(`Aspect ratio button "${aspectRatio}" not found, skipping`);
      await MC.sleep(300);
    }

    // Close popup by clicking the prompt bar area
    const pb = findPromptBar();
    if (pb) pb.click();
    else document.body.click();
    await MC.sleep(600);
    log('Settings done');
  }

  // ────────────────────────────────────────────────────────────────────────

  /** Step 2a — First prompt: upload reference image via file input */
  async function uploadRefImage(imageUrl) {
    log('Uploading reference image:', imageUrl.substring(0, 80));

    // Click +
    const plus = await waitFor(findPlusBtn, ELEM_TIMEOUT, '+ button');
    await click(plus);
    await MC.sleep(1000);

    // The asset library popup opens. Click "Upload image"
    const uploadBtn = await waitFor(
      () => findByText('Upload image', 'button,div,span,a,label'),
      5000, '"Upload image" button'
    );

    // Prepare to intercept the <input type="file"> that the button triggers
    const fileInputP = waitForFileInput();

    await click(uploadBtn);
    log('Clicked Upload image — waiting for file input');

    const fileInput = await fileInputP;

    // Fetch the image and inject
    const file = await urlToFile(imageUrl, 'product.png');
    const dt = new DataTransfer();
    dt.items.add(file);
    fileInput.files = dt.files;
    fileInput.dispatchEvent(new Event('change', { bubbles: true }));
    fileInput.dispatchEvent(new Event('input',  { bubbles: true }));
    log('File injected via DataTransfer');

    // Wait for asset library to close / ref image to process
    await MC.sleep(2000);
    await waitForRefProcessed();
    log('Reference image uploaded & processed');
  }

  /** Wait for an <input type="file"> to appear in the DOM (max 10 s) */
  function waitForFileInput() {
    return new Promise((resolve, reject) => {
      // Check existing
      const existing = document.querySelector('input[type="file"]');
      if (existing) return resolve(existing);

      const to = setTimeout(() => { obs.disconnect(); reject(new Error('file input not found')); }, 10_000);
      const obs = new MutationObserver(() => {
        const fi = document.querySelector('input[type="file"]');
        if (fi) { obs.disconnect(); clearTimeout(to); resolve(fi); }
      });
      obs.observe(document.body, { childList: true, subtree: true });
    });
  }

  // ────────────────────────────────────────────────────────────────────────

  /** Step 2b — Subsequent prompts: select first asset (the original product image) */
  async function selectRefFromLibrary() {
    log('Selecting reference from asset library');

    // Click +
    const plus = await waitFor(findPlusBtn, ELEM_TIMEOUT, '+ button');
    await click(plus);
    await MC.sleep(1200);

    // The asset library popup lists assets. The FIRST item is always the original upload.
    // Find clickable image/thumbnail items (not the "Upload image" button)
    const firstAsset = await waitFor(() => {
      // Strategy 1: img tags inside the popup that aren't tiny icons
      const imgs = $$('img');
      for (const img of imgs) {
        if (img.naturalWidth < 20 || img.width < 20) continue;
        // Must be inside a popup / overlay, not the gallery behind
        const parent = img.closest('[role="dialog"], [class*="modal"], [class*="popover"], [class*="overlay"], [class*="panel"], [class*="asset"], [class*="library"]');
        if (!parent) continue;
        // Return the clickable wrapper
        return img.closest('button, [role="option"], [role="listitem"], li, a, [class*="item"]') || img;
      }
      // Strategy 2: list items that are NOT "Upload image"
      const items = $$('[role="option"], [role="listitem"], li');
      for (const it of items) {
        if (it.textContent.toLowerCase().includes('upload image')) continue;
        if (it.querySelector('img')) return it;
      }
      return null;
    }, 8000, 'first asset in library');

    await click(firstAsset);
    log('Clicked first asset');
    await MC.sleep(1500);
    await waitForRefProcessed();
    log('Reference image selected & processed');
  }

  // ────────────────────────────────────────────────────────────────────────

  /** Wait until the "NN%" reference-processing indicator disappears */
  async function waitForRefProcessed() {
    const t0 = Date.now();
    let sawPct = false;

    while (Date.now() - t0 < REF_TIMEOUT) {
      const txt = document.body.innerText;
      const m = txt.match(/\b(\d{1,3})%/);
      if (m) {
        sawPct = true;
        const pct = +m[1];
        if (pct >= 99) { await MC.sleep(800); return; }
      } else if (sawPct) {
        // Percentage was visible and is now gone → done
        return;
      }
      // Also check for "ingredients loading"
      if (txt.toLowerCase().includes('ingredients loading')) {
        log('Waiting for ingredients to load...');
      }
      await MC.sleep(POLL);
    }
    // If we never saw a percentage, assume it processed instantly
    if (!sawPct) return;
    warn('Ref processing wait timed out');
  }

  // ────────────────────────────────────────────────────────────────────────

  /** Step 3 — Type prompt into the prompt bar */
  async function typePrompt(text) {
    log('Typing prompt:', text.substring(0, 70) + '...');

    // Wait for "ingredients loading" to clear first
    const t0 = Date.now();
    while (Date.now() - t0 < 15_000) {
      if (!document.body.innerText.toLowerCase().includes('ingredients loading')) break;
      await MC.sleep(POLL);
    }

    const bar = await waitFor(findPromptBar, ELEM_TIMEOUT, 'prompt bar');
    await typeText(bar, text);
    await MC.sleep(400);

    // Verify
    const entered = bar.value || bar.textContent || bar.innerText || '';
    if (entered.length < 20) {
      warn('Prompt may not have entered — retrying with execCommand');
      bar.focus();
      document.execCommand('selectAll');
      document.execCommand('insertText', false, text);
      await MC.sleep(300);
    }
    log('Prompt entered');
  }

  // ────────────────────────────────────────────────────────────────────────

  /** Step 4 — Click the submit/create button */
  async function clickSubmit() {
    const btn = await waitFor(findSubmitBtn, ELEM_TIMEOUT, 'submit button');
    await click(btn);
    log('Submit clicked');
  }

  // ────────────────────────────────────────────────────────────────────────

  /** Step 5 — Wait for image generation to complete (0% → done) */
  async function waitForGeneration() {
    log('Waiting for generation...');
    await MC.sleep(3000); // initial delay for generation to start

    const t0 = Date.now();
    let lastPct = -1;
    let seenProgress = false;

    while (Date.now() - t0 < GEN_TIMEOUT) {
      const txt = document.body.innerText;
      const matches = txt.match(/\b(\d{1,3})%/g) || [];
      const pcts = matches.map(m => parseInt(m));

      if (pcts.length) {
        seenProgress = true;
        const lowest = Math.min(...pcts);
        if (lowest !== lastPct) {
          lastPct = lowest;
          if (lowest % 20 === 0 || lowest > 90) log(`Generation: ${lowest}%`);
        }
        if (pcts.every(p => p >= 99)) {
          log('Generation complete (>=99%)');
          await MC.sleep(1500);
          return;
        }
      } else if (seenProgress) {
        // Was showing %, now isn't → image finished rendering
        log('Generation complete (indicator gone)');
        await MC.sleep(1000);
        return;
      }
      await MC.sleep(POLL);
    }
    warn('Generation timeout — continuing anyway');
  }

  // ── DOWNLOAD PHASE ─────────────────────────────────────────────────────

  /** Get all clickable image cards in the gallery */
  function getGalleryCards() {
    // Images in the project gallery are rendered as cards/tiles
    // We need elements that have images and are clickable
    const candidates = $$('[class*="card"], [class*="tile"], [class*="grid-item"], [class*="gallery"] > div > div');
    const cards = [];
    for (const c of candidates) {
      if (c.querySelector('img') || c.querySelector('canvas') || c.style.backgroundImage) {
        // Exclude tiny elements (icons, thumbnails < 50px)
        if (c.offsetWidth > 80 && c.offsetHeight > 80) cards.push(c);
      }
    }
    if (cards.length) return cards;

    // Fallback: any large img in the main content area
    const imgs = $$('main img, [class*="content"] img, [class*="project"] img');
    return Array.from(imgs).filter(i => i.offsetWidth > 80);
  }

  /** Download all generated images by entering each edit view */
  async function downloadAllImages(count) {
    log(`Downloading ${count} images`);
    let downloaded = 0;

    for (let i = 0; i < count; i++) {
      log(`Download ${i + 1}/${count}: opening edit view`);

      // Find and click the image card
      // After downloading, the order might shift, so re-query each time
      const cards = getGalleryCards();
      if (i >= cards.length) {
        warn(`Only found ${cards.length} gallery cards, expected ${count}. Stopping downloads.`);
        break;
      }
      await click(cards[i]);
      await MC.sleep(2000);

      // Wait for edit page URL
      try {
        await waitFor(isEditPage, 10_000, 'edit page URL');
      } catch (_) {
        // Maybe the click didn't navigate — try clicking the image itself
        warn('Edit page not detected, retrying click');
        const cards2 = getGalleryCards();
        if (cards2[i]) {
          const img = cards2[i].querySelector('img') || cards2[i];
          await click(img);
          await MC.sleep(2000);
          await waitFor(isEditPage, 8_000, 'edit page URL (retry)');
        }
      }
      await MC.sleep(1500);

      // Click download
      const dlBtn = await waitFor(findDownloadBtn, ELEM_TIMEOUT, 'download button');
      await click(dlBtn);
      log('Download button clicked');

      // Wait for "Upscaling complete" / "has been downloaded"
      await waitForDownloadDone();
      downloaded++;

      // Go back to gallery
      const back = await waitFor(findBackBtn, ELEM_TIMEOUT, 'back button');
      await click(back);
      await MC.sleep(2000);

      // Confirm we're back on project page
      try {
        await waitFor(isProjectPage, 8_000, 'project page');
      } catch (_) {
        // If URL didn't change, try browser back
        warn('Back button may not have worked, trying history.back');
        history.back();
        await MC.sleep(2000);
      }
      await MC.sleep(1000);
    }

    log(`Downloaded ${downloaded}/${count} images`);
    return downloaded;
  }

  /** Wait for the download/upscale notification to confirm completion */
  async function waitForDownloadDone() {
    log('Waiting for upscale + download...');
    const t0 = Date.now();

    while (Date.now() - t0 < DL_TIMEOUT) {
      const txt = document.body.innerText.toLowerCase();
      if (txt.includes('upscaling complete') || txt.includes('has been downloaded') || txt.includes('download complete')) {
        log('Download confirmed!');
        await MC.sleep(1000);
        // Dismiss notification
        const dismiss = findByText('Dismiss', 'button,span,a');
        if (dismiss) { try { await click(dismiss); } catch (_) {} }
        return;
      }
      await MC.sleep(POLL);
    }
    warn('Download confirmation timeout — assuming it downloaded');
  }

  // ── MAIN JOB HANDLER ───────────────────────────────────────────────────

  async function runJob(job) {
    const { job_id, prompts, image_url, aspect_ratio, count } = job;
    const total = prompts.length;
    log(`Starting job ${job_id}: ${total} prompts`);

    try {
      // ── Always create a NEW project ──
      // Clicking "New project" or back button may reload the page (kills this script).
      // We use _onFreshProject flag + chrome.storage.local to survive reloads.

      if (!job._onFreshProject) {
        // First run — need to navigate to a fresh project
        job._onFreshProject = true;

        if (isProjectPage() || isEditPage()) {
          // Save job so it survives page reload, then navigate to dashboard
          log('Saving job & navigating to Flow dashboard');
          await new Promise(r => chrome.storage.local.set({ pendingFlowJob: job }, r));
          location.href = 'https://labs.google/fx/tools/flow';
          return; // script will reload → init() resumes with _onFreshProject = true
        }
      }

      // If we're on the dashboard, click "New project"
      if (isDashboard()) {
        log('On dashboard — clicking New Project');
        const np = await waitFor(
          () => findByText('New project', 'button,div,span,a,h3,h4'),
          8000, '"+ New project" button'
        );

        // Save job again in case "New project" click triggers reload
        await new Promise(r => chrome.storage.local.set({ pendingFlowJob: job }, r));
        await click(np);
        await MC.sleep(4000);

        // If still alive (SPA navigation), check if we landed on project page
        if (isProjectPage()) {
          chrome.storage.local.remove('pendingFlowJob');
          log('New project created (SPA navigation)');
        } else {
          // Page reloaded → init() will resume the job
          return;
        }
      }

      // At this point we must be on a project page (new or resumed)
      if (isProjectPage()) {
        // Clear any leftover pending job
        chrome.storage.local.remove('pendingFlowJob');
        log('On fresh project page');
        MC.sendStatus(job_id, 'running', 'New project created');
      } else {
        throw new Error('Expected project page but got: ' + location.href);
      }

      // ── Step 1: Settings ──
      await setSettings(count || 1, aspect_ratio || '1:1');
      MC.sendStatus(job_id, 'running', 'Settings configured');

      // ── Steps 2-5: Generate all images ──
      for (let i = 0; i < total; i++) {
        const label = `Prompt ${i + 1}/${total}`;
        MC.sendStatus(job_id, 'running', label);
        log(`\n──── ${label} ────`);

        // Attach reference image
        if (image_url) {
          if (i === 0) await uploadRefImage(image_url);
          else         await selectRefFromLibrary();
        }

        // Type prompt
        await typePrompt(prompts[i]);

        // Submit
        await clickSubmit();

        // Wait for generation
        await waitForGeneration();

        // Human-like pause between prompts
        if (i < total - 1) {
          const pause = 5000 + Math.random() * 7000;
          log(`Pausing ${(pause / 1000).toFixed(1)}s before next prompt`);
          await MC.sleep(pause);
        }
      }

      log('\nAll images generated — starting downloads');
      MC.sendStatus(job_id, 'running', 'Downloading images');

      // ── Step 6: Download all ──
      const dlCount = await downloadAllImages(total);

      // ── Done ──
      MC.sendStatus(job_id, 'complete', `Done: ${dlCount}/${total} images downloaded`);
      log(`Job ${job_id} complete!`);

      // Post download count to Flask for collection assembly
      try {
        await fetch(`${MC.SERVER}/api/ext/flow-complete`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ job_id, download_count: dlCount, total_prompts: total }),
        });
      } catch (e) { warn('Failed to post flow-complete:', e.message); }

    } catch (error) {
      err('Job failed:', error.message, error.stack);
      MC.sendStatus(job_id, 'error', error.message);
    }
  }

  // ── INIT & MESSAGING ───────────────────────────────────────────────────

  function init() {
    log('Content script loaded:', location.href);

    // Register flow_active capability
    chrome.storage.local.get(['extraCapabilities'], (data) => {
      const caps = new Set(data.extraCapabilities || []);
      if (!caps.has('flow_active')) {
        caps.add('flow_active');
        chrome.storage.local.set({ extraCapabilities: [...caps] });
        log('Registered flow_active capability');
      }
    });

    // Listen for RUN_JOB from background.js
    chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
      if (msg.type === 'RUN_JOB' && msg.job?.job_type === 'flow') {
        log('Received RUN_JOB:', msg.job.job_id);
        sendResponse({ ack: true });
        // Small delay to let the ack go through
        setTimeout(() => runJob(msg.job), 500);
        return true; // keep channel open
      }
    });

    // Check for pending job (page was navigated/reloaded mid-job)
    chrome.storage.local.get(['pendingFlowJob'], (data) => {
      if (data.pendingFlowJob) {
        log('Resuming pending job after page reload');
        const job = data.pendingFlowJob;
        chrome.storage.local.remove('pendingFlowJob');
        setTimeout(() => runJob(job), 1500);
      }
    });

    log('Flow bot ready ✓');
  }

  // Wait for utils.js (MC object) to be available
  if (typeof MC !== 'undefined') {
    init();
  } else {
    const check = setInterval(() => {
      if (typeof MC !== 'undefined') { clearInterval(check); init(); }
    }, 200);
    setTimeout(() => clearInterval(check), 10_000); // give up after 10s
  }

})();
