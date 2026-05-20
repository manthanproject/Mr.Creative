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
  const DL_TIMEOUT   = 15_000;     // 30s max per download
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
  async function click(el, { trusted = false } = {}) {
    el.scrollIntoView({ behavior: 'instant', block: 'center' });
    await MC.sleep(150 + Math.random() * 200);

    if (trusted) {
      // Use debugger Input.dispatchMouseEvent for isTrusted=true
      const rect = el.getBoundingClientRect();
      const x = rect.left + rect.width / 2;
      const y = rect.top + rect.height / 2;
      try {
        await new Promise((resolve, reject) => {
          chrome.runtime.sendMessage({
            type: 'FLOW_TRUSTED_CLICK',
            x: Math.round(x),
            y: Math.round(y)
          }, resp => {
            if (resp && resp.success) resolve();
            else reject(new Error(resp?.error || 'trusted click failed'));
          });
        });
        return;
      } catch (e) {
        warn('Trusted click failed, falling back to DOM click:', e.message);
      }
    }

    // Fallback: DOM click (isTrusted=false)
    el.click();
    el.dispatchEvent(new PointerEvent('pointerdown', { bubbles: true }));
    el.dispatchEvent(new PointerEvent('pointerup', { bubbles: true }));
  }

  /** Type text into input/textarea/contenteditable */
  async function typeText(el, text, opts = {}) {
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
      // contenteditable (Slate.js) — human-like Ctrl+V paste via debugger
      el.scrollIntoView({ behavior: 'smooth', block: 'center' });
      await MC.sleep(500 + Math.random() * 300);
      el.click();
      el.focus();
      await MC.sleep(600 + Math.random() * 400);

      // Build message — optionally include submit flag
      const msgPayload = { type: 'FLOW_PASTE', text: text };
      if (opts && opts.doSubmit) {
        msgPayload.doSubmit = true;
      }

      const result = await new Promise((resolve, reject) => {
        chrome.runtime.sendMessage(msgPayload, r => {
          if (chrome.runtime.lastError) reject(new Error(chrome.runtime.lastError.message));
          else resolve(r);
        });
      });
      console.log('[Flow] FLOW_PASTE result:', JSON.stringify(result));

      await MC.sleep(1500 + Math.random() * 1000);
      const clean = (s) => (s || '').replace(/\u200B/g, '').replace(/\uFEFF/g, '').trim();
      console.log('[Flow] Text in editor after paste:', clean(el.textContent).length, 'chars');
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

  // ── ELEMENT FINDERS (exact selectors from Flow's DOM) ──────────────────

  function findPromptBar() {
    // Slate.js editor — the main prompt input
    return $([
      'div[data-slate-editor="true"]',
      '[role="textbox"][contenteditable="true"]',
    ]);
  }

  function findSubmitBtn() {
    // The arrow_forward/Create button — rightmost in bottom bar
    // Class: sc-e5032833-5   Text includes: "Create"
    return $([
      'button.sc-e5032833-5',
      'button.ghPNWI',
    ]) || (() => {
      // Fallback: find button whose text includes "Create" in the bottom bar
      const btns = $$('button');
      for (const b of btns) {
        const t = b.textContent.trim();
        if (t.includes('Create') && t.includes('arrow_forward')) return b;
      }
      return null;
    })();
  }

  function findPlusBtn() {
    // The + / reference image button — has aria-haspopup="dialog"
    // Class: sc-3bb56e4a-0   Text includes: "add_2"
    return $([
      'button[aria-haspopup="dialog"].sc-3bb56e4a-0',
      'button.cRBTkw',
    ]) || (() => {
      // Fallback: button with aria-haspopup="dialog" near bottom of page
      const btns = document.querySelectorAll('button[aria-haspopup="dialog"]');
      for (const b of btns) {
        if (b.getBoundingClientRect().bottom > window.innerHeight - 200) return b;
      }
      return null;
    })();
  }

  function findSettingsArea() {
    // The model/settings trigger in the bottom bar
    // Uses aria-haspopup="menu" and contains "Nano Banana" or "Banana"
    const btns = document.querySelectorAll('button[aria-haspopup="menu"]');
    for (const b of btns) {
      const t = b.textContent || '';
      if (t.includes('Banana') || t.includes('Nano') || t.includes('banana')) return b;
    }
    // Fallback: any button with aria-haspopup="menu" near bottom of page
    for (const b of btns) {
      if (b.getBoundingClientRect().bottom > window.innerHeight - 200) return b;
    }
    return null;
  }

  function findDownloadBtn() {
    // In edit view: download icon button in the top toolbar
    // It's a button containing google-symbols icon "download" or "arrow_downward"
    const btns = document.querySelectorAll('button');
    for (const b of btns) {
      const icon = b.querySelector('i.google-symbols, i[class*="google-symbols"]');
      if (icon) {
        const iconText = icon.textContent.trim();
        if (iconText === 'download' || iconText === 'file_download' || iconText === 'arrow_downward') return b;
      }
      // Also check aria-label
      const label = (b.getAttribute('aria-label') || '').toLowerCase();
      if (label.includes('download')) return b;
    }
    return null;
  }

  function findBackBtn() {
    // Back button has google-symbols icon "arrow_back" and span "Back"
    const btns = document.querySelectorAll('button');
    for (const b of btns) {
      const icon = b.querySelector('i.google-symbols, i[class*="google-symbols"]');
      if (icon && icon.textContent.trim() === 'arrow_back') return b;
    }
    // Fallback: button with span text "Back"
    for (const b of btns) {
      const span = b.querySelector('span');
      if (span && span.textContent.trim() === 'Back') return b;
    }
    return null;
  }

  // ── FLOW BOT ACTIONS ────────────────────────────────────────────────────

  /** Step 1 — Open settings popup, set count to 1x (and optional aspect ratio) */
  async function setSettings(count = 1, aspectRatio) {
    log('Setting count →', count, aspectRatio ? `aspect → ${aspectRatio}` : '');

    // Open the settings popup (retry up to 3 times)
    const area = await waitFor(findSettingsArea, ELEM_TIMEOUT, 'settings area');
    log('Found settings area:', area.textContent.trim().substring(0, 40));
    for (let attempt = 0; attempt < 3; attempt++) {
      await click(area);
      await MC.sleep(1200);
      // Check if popup appeared by looking for count buttons
      const testBtn = document.querySelector('button.flow_tab_slider_trigger, button[role="tab"]');
      if (testBtn) { log('Settings popup opened on attempt', attempt + 1); break; }
      log('Settings popup not open yet, retrying click...');
    }

    // --- Count ---
    const countLabel = count === 1 ? '1x' : `x${count}`;
    const countBtn = await waitFor(() => {
      // Count buttons use Radix tabs with class flow_tab_slider_trigger
      const btns = document.querySelectorAll('button.flow_tab_slider_trigger, button[role="tab"]');
      for (const b of btns) {
        if (b.textContent.trim() === countLabel) return b;
      }
      // Fallback: any button with exact count text
      for (const b of document.querySelectorAll('button')) {
        if (b.textContent.trim() === countLabel) return b;
      }
      return null;
    }, 8000, `count button "${countLabel}"`);
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

    // Click + button (may need retry)
    for (let attempt = 0; attempt < 3; attempt++) {
      const plus = await waitFor(findPlusBtn, ELEM_TIMEOUT, '+ button');
      await click(plus);
      await MC.sleep(1500);

      // Check if panel opened (any popup/overlay appeared with images)
      const panel = document.querySelector('[role="dialog"], [class*="popover"], [class*="overlay"], [class*="panel"], [class*="asset"]');
      if (panel) {
        log('Asset panel opened on attempt', attempt + 1);
        break;
      }
      // Also check for items with img (panel might not have specific role)
      const anyAssetImg = document.querySelectorAll('img');
      let foundPopupImg = false;
      for (const img of anyAssetImg) {
        const rect = img.getBoundingClientRect();
        // Look for small thumbnails in the lower part of screen (panel area)
        if (rect.width > 20 && rect.width < 200 && rect.top > 400) {
          foundPopupImg = true;
          break;
        }
      }
      if (foundPopupImg) {
        log('Asset panel detected via thumbnail on attempt', attempt + 1);
        break;
      }
      log('Asset panel not detected, retrying click...');
    }

    await MC.sleep(1000);

    // Find the first clickable asset item (not "Upload image")
    const firstAsset = await waitFor(() => {
      // Look for any element with text matching uploaded file OR containing an img thumbnail
      const allElements = document.querySelectorAll('div, button, li, span, a');
      for (const el of allElements) {
        const text = el.textContent.trim();
        // Skip "Upload image" and very large/small elements
        if (text.toLowerCase().includes('upload image')) continue;
        if (el.offsetWidth < 30 || el.offsetWidth > 600) continue;
        if (el.offsetHeight < 20 || el.offsetHeight > 200) continue;

        // Must have a small img inside (thumbnail) or be an asset item
        const img = el.querySelector('img');
        if (img && img.width > 15 && img.width < 150) {
          // Check it's in the popup area (below the gallery)
          const rect = el.getBoundingClientRect();
          if (rect.top > 300) return el;
        }

        // Or text matches common patterns like ".png", ".jpg", filename
        if ((text.endsWith('.png') || text.endsWith('.jpg') || text.endsWith('.jpeg')) && text.length < 100) {
          const rect = el.getBoundingClientRect();
          if (rect.top > 300) return el;
        }
      }
      return null;
    }, 12000, 'first asset in library');

    await click(firstAsset);
    log('Clicked first asset');
    await MC.sleep(2000);
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
  async function typePrompt(text, includeSubmit = false) {
    log('Typing prompt:', text.substring(0, 70) + '...');

    // Wait for "ingredients loading" to clear first
    const t0 = Date.now();
    while (Date.now() - t0 < 15_000) {
      if (!document.body.innerText.toLowerCase().includes('ingredients loading')) break;
      await MC.sleep(POLL);
    }

    const bar = await waitFor(findPromptBar, ELEM_TIMEOUT, 'prompt bar');
    const opts = {};
    if (includeSubmit) {
      opts.doSubmit = true;
    }
    await typeText(bar, text, opts);
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
    if (includeSubmit) log('Submit included in paste session');
  }

  // ────────────────────────────────────────────────────────────────────────

  /** Step 4 — Click the submit/create button via debugger trusted click */
  async function clickSubmit() {
    const btn = await waitFor(findSubmitBtn, ELEM_TIMEOUT, 'submit button');
    btn.scrollIntoView({ behavior: 'smooth', block: 'center' });
    await MC.sleep(800 + Math.random() * 500);

    const rect = btn.getBoundingClientRect();
    const result = await new Promise((resolve, reject) => {
      chrome.runtime.sendMessage({
        type: 'FLOW_CLICK',
        x: Math.round(rect.left + rect.width / 2),
        y: Math.round(rect.top + rect.height / 2),
      }, r => {
        if (chrome.runtime.lastError) reject(new Error(chrome.runtime.lastError.message));
        else resolve(r);
      });
    });
    log('Submit clicked via debugger:', JSON.stringify(result));
    await MC.sleep(1000);
  }

  // ────────────────────────────────────────────────────────────────────────

  /** Step 5 — Wait for image generation to complete. Returns 'success', 'failed', or 'timeout'. */
  async function waitForGeneration() {
    log('Waiting for generation...');

    const imgsBefore = document.querySelectorAll('img[alt="Generated image"]').length;
    log('Images in gallery before generation:', imgsBefore);

    await MC.sleep(5000);

    const t0 = Date.now();
    let lastLogTime = 0;

    while (Date.now() - t0 < GEN_TIMEOUT) {
      // Check for failure — "unusual activity" or "Failed"
      const bodyText = document.body.innerText;
      if (bodyText.includes('unusual activity') || bodyText.includes('Failed')) {
        warn('Generation blocked — unusual activity detected, skipping this prompt');
        // Dismiss the error banner if possible
        const dismiss = findByText('Dismiss', 'button,span,a');
        if (dismiss) { try { await click(dismiss); } catch (_) {} }
        await MC.sleep(2000);
        return 'failed';
      }

      const imgsNow = document.querySelectorAll('img[alt="Generated image"]').length;
      if (imgsNow > imgsBefore) {
        log(`Generation complete — new image appeared (${imgsBefore} → ${imgsNow})`);
        await MC.sleep(2000);
        return 'success';
      }

      // Secondary: check for percentage progress
      const matches = bodyText.match(/\b(\d{1,2})%/g) || [];
      const pcts = matches.map(m => parseInt(m)).filter(p => p < 99);
      if (pcts.length && Date.now() - lastLogTime > 10000) {
        log(`Generation in progress: ${Math.max(...pcts)}%`);
        lastLogTime = Date.now();
      }

      await MC.sleep(POLL);
    }
    warn('Generation timeout — continuing anyway');
    return 'timeout';
  }

  // ── DOWNLOAD PHASE ─────────────────────────────────────────────────────

  /** Get all clickable image cards in the gallery */
  function getGalleryCards() {
    // Generated images have alt="Generated image"
    const imgs = document.querySelectorAll('img[alt="Generated image"]');
    if (imgs.length) {
      // Return clickable wrappers (parent div or the img itself)
      return Array.from(imgs).map(img => {
        // Walk up to find a clickable container
        let el = img;
        for (let i = 0; i < 4; i++) {
          if (el.parentElement && el.parentElement.offsetWidth > 80) {
            el = el.parentElement;
            // Stop at a reasonable container (not the whole page)
            if (el.offsetWidth > 800) { el = img; break; }
          }
        }
        return el;
      });
    }

    // Fallback: any large img in the main content area
    const allImgs = $$('main img, [class*="content"] img, [class*="project"] img');
    return Array.from(allImgs).filter(i => i.offsetWidth > 80 && i.offsetHeight > 80);
  }

  /** Download all generated images by entering each edit view */
  async function downloadAllImages(count, job_id) {
    log(`Downloading ${count} images`);
    let downloaded = 0;

    for (let i = 0; i < count; i++) {
      log(`Download ${i + 1}/${count}: opening edit view`);
      if (job_id) MC.sendStatus(job_id, 'running', `Download ${i + 1}/${count}`);

      const cards = getGalleryCards();
      if (i >= cards.length) {
        warn(`Only found ${cards.length} gallery cards, expected ${count}. Stopping downloads.`);
        break;
      }
      await click(cards[i]);
      await MC.sleep(1000);

      // Wait for edit page
      try {
        await waitFor(isEditPage, 5000, 'edit page URL');
      } catch (_) {
        warn('Edit page not detected, retrying click');
        const cards2 = getGalleryCards();
        if (cards2[i]) {
          const img = cards2[i].querySelector('img') || cards2[i];
          await click(img);
          await MC.sleep(1000);
          await waitFor(isEditPage, 5000, 'edit page URL (retry)');
        }
      }
      await MC.sleep(800);

      // Click download icon
      const dlBtn = await waitFor(findDownloadBtn, 5000, 'download button');
      await click(dlBtn);
      log('Download button clicked');
      await MC.sleep(600);

      // Try 2K first
      const sizeBtn2K = await waitFor(() => {
        const items = document.querySelectorAll('button[role="menuitem"]');
        for (const item of items) {
          if (item.textContent.trim().includes('2K')) return item;
        }
        return null;
      }, 5000, 'download size option');
      await click(sizeBtn2K);
      log('Selected 2K');

      // Wait for 2K download — check for success or failure
      const dlResult = await waitForDownloadDone();

      if (dlResult === 'failed') {
        // 2K failed — fallback to 1K
        log('2K upscale failed — falling back to 1K');
        await MC.sleep(1000);

        // Click download button again
        const dlBtn2 = await waitFor(findDownloadBtn, 5000, 'download button (retry)');
        await click(dlBtn2);
        await MC.sleep(600);

        // Select 1K
        const sizeBtn1K = await waitFor(() => {
          const items = document.querySelectorAll('button[role="menuitem"]');
          for (const item of items) {
            if (item.textContent.trim().includes('1K')) return item;
          }
          return null;
        }, 5000, '1K download option');
        await click(sizeBtn1K);
        log('Selected 1K fallback');
        await MC.sleep(3000); // 1K downloads instantly
      }
      downloaded++;

      // Go back to gallery
      const back = await waitFor(findBackBtn, 5000, 'back button');
      await click(back);
      await MC.sleep(2000);

      // Confirm we're back and gallery is loaded
      try {
        await waitFor(isProjectPage, 5000, 'project page');
      } catch (_) {
        history.back();
        await MC.sleep(2000);
      }
      // Wait for gallery cards to re-render before next download
      await waitFor(() => getGalleryCards().length > 0, 8000, 'gallery cards to load');
      await MC.sleep(1000);
    }

    log(`Downloaded ${downloaded}/${count} images`);
    return downloaded;
  }

  /** Wait for download — returns 'success', 'failed', or 'timeout' */
  async function waitForDownloadDone() {
    log('Waiting for download...');
    const t0 = Date.now();
    while (Date.now() - t0 < DL_TIMEOUT) {
      const txt = document.body.innerText.toLowerCase();

      // Check for failure first
      if (txt.includes('upscaling failed') || txt.includes('upscale failed')) {
        warn('Upscaling failed!');
        await MC.sleep(500);
        const dismiss = findByText('Dismiss', 'button,span,a');
        if (dismiss) { try { await click(dismiss); } catch (_) {} }
        return 'failed';
      }

      // Check for success
      if (txt.includes('upscaling complete') || txt.includes('has been downloaded') ||
          txt.includes('download complete') || txt.includes('been downloaded') ||
          txt.includes('download will start')) {
        log('Download confirmed!');
        await MC.sleep(500);
        const dismiss = findByText('Dismiss', 'button,span,a');
        if (dismiss) { try { await click(dismiss); } catch (_) {} }
        return 'success';
      }
      await MC.sleep(POLL);
    }
    warn('Download timeout — assuming it downloaded');
    return 'timeout';
  }

  // ── MAIN JOB HANDLER ───────────────────────────────────────────────────

  /** Check if stop was requested via Flask */
  async function shouldStop() {
    try {
      const res = await fetch(`${MC.SERVER}/api/ext/check-stop`);
      const data = await res.json();
      return data.stop === true;
    } catch (_) {
      return false;
    }
  }

  async function runJob(job) {
    const { job_id, prompts, image_url, aspect_ratio, count } = job;
    const total = prompts.length;
    log(`Starting job ${job_id}: ${total} prompts`);

    // Clear any previous stop flag
    try {
      await fetch(`${MC.SERVER}/api/ext/stop-flow`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ clear: true })
      });
    } catch (_) {}

    try {
      const isResume = (job.start_index || 0) > 0;

      if (isResume && job.project_url) {
        // ── RESUME: navigate to existing project ──
        log(`Resuming job on existing project: ${job.project_url}`);
        if (location.href !== job.project_url && !isProjectPage()) {
          await new Promise(r => chrome.storage.local.set({ pendingFlowJob: job }, r));
          location.href = job.project_url;
          return;
        }
        if (isProjectPage()) {
          chrome.storage.local.remove('pendingFlowJob');
          log('On existing project page — resuming');
          MC.sendStatus(job_id, 'running', `Resuming from prompt ${job.start_index + 1}`);
        }
      } else {
        // ── NEW JOB: create a new project ──
        if (!job._onFreshProject) {
          job._onFreshProject = true;
          if (isProjectPage() || isEditPage()) {
            log('Saving job & navigating to Flow dashboard');
            await new Promise(r => chrome.storage.local.set({ pendingFlowJob: job }, r));
            location.href = 'https://labs.google/fx/tools/flow';
            return;
          }
        }

        if (isDashboard()) {
          log('On dashboard — clicking New Project');
          const np = await waitFor(
            () => findByText('New project', 'button,div,span,a,h3,h4'),
            8000, '"+ New project" button'
          );
          await new Promise(r => chrome.storage.local.set({ pendingFlowJob: job }, r));
          await click(np, { trusted: true });
          await MC.sleep(4000);
          if (isProjectPage()) {
            chrome.storage.local.remove('pendingFlowJob');
            log('New project created (SPA navigation)');
          } else {
            return;
          }
        }

        if (isProjectPage()) {
          chrome.storage.local.remove('pendingFlowJob');
          log('On fresh project page');
          MC.sendStatus(job_id, 'running', 'New project created');
        } else {
          throw new Error('Expected project page but got: ' + location.href);
        }

        // ── Step 1: Settings (best-effort) ──
        try {
          await setSettings(count || 1, aspect_ratio || '1:1');
          MC.sendStatus(job_id, 'running', 'Settings configured');
        } catch (settingsErr) {
          warn('Settings step failed, continuing with current defaults:', settingsErr.message);
          MC.sendStatus(job_id, 'running', 'Settings skipped, using current defaults');
        }
      }

      // ── Steps 2-5: Generate all images ──
      const startIndex = job.start_index || 0;
      if (startIndex > 0) log(`Resuming from prompt ${startIndex + 1}/${total}`);

      for (let i = startIndex; i < total; i++) {
        const label = `Prompt ${i + 1}/${total}`;
        MC.sendStatus(job_id, 'running', label);
        log(`\n──── ${label} ────`);

        // Check if stop was requested
        if (await shouldStop()) {
          warn(`Stop requested — saving progress at prompt ${i}/${total}`);
          MC.sendStatus(job_id, 'stopped', `Stopped at prompt ${i}/${total}`);
          try {
            await fetch(`${MC.SERVER}/api/ext/save-progress`, {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ job_id, completed_index: i, total, project_url: location.href }),
            });
          } catch (_) {}
          break;
        }

        // Attach reference image
        if (image_url) {
          if (i === 0 && startIndex === 0) await uploadRefImage(image_url);
          else                              await selectRefFromLibrary();
        }

        // Type prompt + submit in one debugger session (paste + click)
        await typePrompt(prompts[i], true);

        // Wait for generation
        const genResult = await waitForGeneration();

        if (genResult === 'failed') {
          warn(`Prompt ${i + 1} failed (403/unusual activity) — skipping to next`);
          MC.sendStatus(job_id, 'running', `Prompt ${i + 1} failed, skipping`);
          // Wait before retrying next prompt
          await MC.sleep(15000 + Math.random() * 10000);
          continue;
        }

        // Human-like pause between prompts
        if (i < total - 1) {
          const pause = 8000 + Math.random() * 12000; // 8-20s between prompts
          log(`Pausing ${(pause / 1000).toFixed(1)}s before next prompt`);
          await MC.sleep(pause);
        }
      }

      // Count actually generated images (not including ref)
      const generatedCount = getGalleryCards().length;
      log(`\n${generatedCount} images generated — starting downloads`);
      MC.sendStatus(job_id, 'running', 'Downloading images');

      // ── Step 6: Download all ──
      const dlCount = await downloadAllImages(generatedCount, job_id);

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
