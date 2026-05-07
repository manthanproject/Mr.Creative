// ═══════════════════════════════════════════
// Mr.Creative Extension — Pomelli Bot
// Runs on: labs.google.com/pomelli/*
// Handles: Campaign + Photoshoot modes
// ═══════════════════════════════════════════

// ── DOM SELECTORS (verified May 7 2026) ──
const SEL = {
  // Campaign landing page (/campaigns)
  textarea: 'textarea',
  imagesBtn: 'button[aria-label="Add image ingredient"]',
  aspectRatioBtn: 'button.aspect-ratio-button',
  generateIdeasBtn: 'button.prompt-send-button',
  productBtn: 'button[aria-label="Add product"]',

  // Aspect ratio menu items
  aspectMenuItem: 'button.mat-mdc-menu-item',

  // Select Images dialog (CDK overlay)
  imageDialog: 'app-image-ingredient-picker-dialog',
  uploadComponent: 'app-upload-image-button',
  uploadBtn: 'app-upload-image-button button',
  fileInput: 'app-upload-image-button input[type="file"]',
  dialogOverlay: '.cdk-overlay-pane',
  dialogConfirmBtn: '.cdk-overlay-pane button',  // scan for "Update"/"Confirm" text

  // Idea cards (campaign results)
  ideaCard: '.campaign-idea-card',
  ideaTitle: '.idea-title',
  ideaDescription: '.idea-description',
  campaignGrid: '.campaign-grid',
  deleteIdeaBtn: 'button[aria-label="Delete idea"]',

  // Creatives page (after idea selected)
  creativeGrid: 'div.creative-grid',
  creativeCard: 'div.creative-card-container',
  creativeCardImg: 'div.creative-card-container img',
  animateBtn: 'button.animate-button',  // opacity:0, needs hover first
  animateNoTextBtn: 'button[aria-label="Animate without text"]',
  moreBtn: 'button[aria-label="More"]',
  backBtn: 'button.back-button',

  // Photoshoot page
  photoshootModeCard: 'div.photoshoot-branch-button',
  shotThumbnail: 'div.shot-thumbnail',
  selectionCount: 'span.selection-count',
  looksGoodBtn: 'button',  // text "Looks Good"

  // Photoshoot upload
  psUploadComponent: 'app-upload-image-button',
  psFileInput: 'app-upload-image-button input[type="file"]',
  psAspectSelector: 'app-aspect-ratio-selector button',
};

// ═══════════════════════════════════════════
// CAMPAIGN BOT
// ═══════════════════════════════════════════

const CampaignBot = {

  async run(job) {
    const { prompt_text, image_url, image_filename, aspect_ratio, job_id } = job;

    try {
      // Step 1: Navigate to campaigns
      MC.log('Campaign: navigating to /campaigns');
      await MC.sendStatus(job_id, 'navigating', 'Opening campaigns page...');

      await MC.waitFor(SEL.textarea, 30000);

      // Step 2: Type prompt
      MC.log('Campaign: entering prompt');
      await MC.sendStatus(job_id, 'entering_prompt', 'Entering prompt...');
      const textarea = await MC.waitFor(SEL.textarea);
      textarea.focus();
      textarea.value = '';
      // Angular needs input event to detect changes
      textarea.value = prompt_text;
      textarea.dispatchEvent(new Event('input', { bubbles: true }));
      await MC.sleep(500);

      // Step 3: Upload image (optional — continues without if it fails)
      if (image_url) {
        try {
          MC.log('Campaign: uploading image');
          await MC.sendStatus(job_id, 'entering_prompt', `Adding image: ${image_filename}`);

          const imgBtn = await MC.waitFor(SEL.imagesBtn, 5000);
          imgBtn.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));
          await MC.sleep(3000);

          // Wait for dialog — shorter timeout, skip if it doesn't open
          const dialog = await MC.waitFor('.cdk-overlay-pane app-upload-image-button', 10000);
          MC.log('Campaign: dialog opened');
          await MC.sleep(2000);

          const pane = this._getDialogPane();
          const fileInput = pane
            ? pane.querySelector(SEL.fileInput)
            : document.querySelector(SEL.fileInput);

          if (fileInput) {
            await MC.uploadFile(fileInput, image_url, image_filename);
            MC.log('Campaign: file uploaded');
            await MC.sleep(5000);
            await this._clickDialogConfirm(pane);
            await MC.sleep(2000);
          }
        } catch (imgErr) {
          MC.log('Campaign: image upload skipped:', imgErr.message);
          await MC.sendStatus(job_id, 'entering_prompt', 'Image upload skipped, continuing...');
          // Close dialog if it opened
          const closeBtn = document.querySelector('.cdk-overlay-pane button[aria-label="close"], .cdk-overlay-pane .close-button');
          if (closeBtn) closeBtn.click();
          await MC.sleep(1000);
        }
      }

      // Step 4: Set aspect ratio
      if (aspect_ratio) {
        MC.log('Campaign: setting aspect ratio');
        await MC.sendStatus(job_id, 'entering_prompt', `Setting aspect ratio: ${aspect_ratio}`);
        await this._setAspectRatio(aspect_ratio);
      }

      // Step 5: Click Generate Ideas
      MC.log('Campaign: generating ideas');
      await MC.sendStatus(job_id, 'generating', 'Clicking Generate Ideas...');
      const genBtn = await MC.waitFor(SEL.generateIdeasBtn);
      MC.click(genBtn);

      // Step 6: Wait for idea cards
      await MC.sendStatus(job_id, 'generating', 'Waiting for ideas...');
      const ideaCards = await this._waitForIdeaCards();
      MC.log(`Campaign: ${ideaCards.length} ideas generated`);

      // Step 7: Build ideas list (3 cards = 3 ideas, no dedup needed with verified selector)
      const ideas = ideaCards.map((card, i) => ({
        index: i,
        text: this._getIdeaText(card)
      }));
      MC.log(`Campaign: ${ideas.length} ideas`);
      await MC.sendStatus(job_id, 'waiting_selection', 'Select a campaign idea...', { ideas });

      // Step 8: Wait for user selection from server
      MC.log('Campaign: waiting for user to select idea');
      const selection = await this._waitForSelection(job_id);

      if (selection && selection.idea_index !== undefined) {
        const allCards = this._getVisibleIdeaCards();
        if (allCards[selection.idea_index]) {
          MC.click(allCards[selection.idea_index]);
          MC.log(`Campaign: selected idea ${selection.idea_index}`);
        }

        // Step 9: Wait for creatives to load
        await MC.sendStatus(job_id, 'generating', 'Generating creatives...');
        await this._waitForCreatives();

        // Step 10: Smart animate — only Story (9:16) supports animation
        const animateSupported = (aspect_ratio || '').includes('9:16') || aspect_ratio === 'story';
        if (animateSupported) {
          const images = await this._extractCreativeImages();
          MC.log(`Campaign: ${images.length} creatives ready for animate selection`);
          await MC.sendStatus(job_id, 'waiting_animate', 'Select images to animate...', { images });

          // Step 11: Wait for animate selection, then click ALL animate buttons,
          // THEN wait once for ALL videos to complete (matches Selenium pattern)
          const animateSelection = await this._waitForSelection(job_id);
          if (animateSelection && animateSelection.animate_indices && animateSelection.animate_indices.length) {
            const videosBefore = document.querySelectorAll('video').length;
            MC.log(`Animate: clicking ${animateSelection.animate_indices.length} buttons, videosBefore=${videosBefore}`);
            for (const idx of animateSelection.animate_indices) {
              await this._clickAnimateButton(idx, job_id);
            }
            await this._waitForAnimationsToComplete(job_id, videosBefore);
          }
        } else {
          MC.log(`Campaign: aspect ratio ${aspect_ratio} doesn't support animate — skipping`);
        }

        // Step 12: Download all images
        await MC.sendStatus(job_id, 'downloading', 'Downloading images...');
        const downloadedImages = await this._downloadAllCards(job_id);

        // Step 13: Save to collection on server
        await MC.sendStatus(job_id, 'saving', 'Saving to collection...');
        let collectionId = '';
        try {
          const finRes = await fetch(`${MC.SERVER}/api/ext/finalize`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ job_id })
          });
          const finData = await finRes.json();
          collectionId = finData.collection_id || '';
          MC.log(`Campaign: saved ${finData.saved} files to collection ${collectionId}`);
        } catch (e) {
          MC.log('Campaign: finalize failed:', e.message);
        }

        // Navigate back to /campaigns landing
        const m = location.pathname.match(/^(\/u\/\d+)?\//);
        const prefix = (m && m[1]) || '';
        location.href = `https://labs.google.com${prefix}/pomelli/campaigns`;

        await MC.sendStatus(job_id, 'complete', `Done! ${downloadedImages.length} assets downloaded.`, {
          downloaded: downloadedImages,
          collection_id: collectionId
        });
      }

    } catch (err) {
      MC.log('Campaign error:', err);
      await MC.sendStatus(job_id, 'error', `Failed: ${err.message}`);
    }
  },

  // ── Get the CDK dialog pane that contains upload component ──
  _getDialogPane() {
    const panes = document.querySelectorAll('.cdk-overlay-pane');
    for (let i = panes.length - 1; i >= 0; i--) {
      if (panes[i].querySelector(SEL.uploadComponent)) return panes[i];
    }
    return null;
  },

  // ── Click Update or Confirm in dialog ──
  async _clickDialogConfirm(pane) {
    const root = pane || document;
    for (let attempt = 0; attempt < 15; attempt++) {
      for (const btn of root.querySelectorAll('button')) {
        const txt = btn.textContent.trim();
        if ((txt === 'Update' || txt === 'Confirm') && btn.offsetHeight > 0 && !btn.disabled) {
          MC.click(btn);
          MC.log(`Campaign: clicked ${txt}`);
          return;
        }
      }
      await MC.sleep(1000);
    }
    MC.log('Campaign: Update/Confirm not found');
  },

  // ── Set aspect ratio ──
  async _setAspectRatio(ratio) {
    const ratioMap = { story: 'Story (9:16)', square: 'Square (1:1)', feed: 'Feed (4:5)' };
    const label = ratioMap[ratio] || ratioMap.story;

    // Check if already set
    const arBtn = document.querySelector(SEL.aspectRatioBtn);
    if (arBtn && arBtn.textContent.includes(label.split(' ')[0])) {
      MC.log(`Aspect ratio already: ${label}`);
      return;
    }

    // Open menu
    MC.click(arBtn);
    await MC.sleep(500);

    // Click matching menu item
    const menuItem = await MC.waitForText(SEL.aspectMenuItem, label.split(' ')[0], 5000);
    if (menuItem) MC.click(menuItem);
    await MC.sleep(500);
  },

  // ── Wait for idea cards to appear ──
  async _waitForIdeaCards(timeout = 60000) {
    const start = Date.now();
    while (Date.now() - start < timeout) {
      const cards = this._getVisibleIdeaCards();
      if (cards.length >= 3) return cards;  // Pomelli generates 3 ideas
      await MC.sleep(2000);
    }
    throw new Error('Idea cards did not appear');
  },

  // ── Get visible idea cards ──
  _getVisibleIdeaCards() {
    return Array.from(document.querySelectorAll(SEL.ideaCard))
      .filter(c => c.offsetHeight > 0);
  },

  _getIdeaText(card) {
    const title = card.querySelector(SEL.ideaTitle);
    const desc = card.querySelector(SEL.ideaDescription);
    const t = title ? title.textContent.trim() : '';
    const d = desc ? desc.textContent.trim() : '';
    if (t && d) return `${t} — ${d}`;
    return t || d;
  },

  // ── Wait for creatives (images) to load ──
  // Mirrors selenium_bot._wait_for_creatives: waits for all Pomelli loaders to disappear
  // AND at least 15s elapsed before accepting "loaded" state.
  async _waitForCreatives(timeout = 180000) {
    MC.log('Waiting for creatives...');
    // Initial page transition wait (matches Selenium bot)
    await MC.sleep(8000);
    const start = Date.now();
    while (Date.now() - start < timeout) {
      const visible = (sel) => Array.from(document.querySelectorAll(sel))
        .filter(el => el.offsetParent !== null).length;
      const shimmer = visible('app-shimmer-loader');
      const spinner = visible('mat-progress-spinner');
      const progress = visible('app-generation-progress-loader .text');
      const elapsed = (Date.now() - start) / 1000;
      MC.log(`Creatives poll: shimmer=${shimmer}, spinner=${spinner}, progress=${progress}, elapsed=${elapsed.toFixed(1)}s`);
      if (shimmer === 0 && spinner === 0 && progress === 0 && elapsed >= 15) {
        MC.log('All creatives loaded');
        return;
      }
      await MC.sleep(5000);
    }
    MC.log('Creatives wait timed out — continuing anyway');
  },

  // ── Extract creative images as base64 (Pomelli image URLs need auth cookies) ──
  // Fetches with credentials → blob → createImageBitmap → canvas thumbnail.
  // Avoids the cross-origin tainted-canvas error from drawing <img> directly.
  async _extractCreativeImages() {
    // Trigger lazy-load for cards below the viewport
    window.scrollTo(0, document.body.scrollHeight);
    await MC.sleep(800);
    window.scrollTo(0, 0);
    await MC.sleep(500);

    const cards = Array.from(document.querySelectorAll(SEL.creativeCard));
    const imgs = cards
      .map(c => c.querySelector('img'))
      .filter(img => img && img.src && (img.naturalWidth || 0) > 0);
    MC.log(`_extractCreativeImages: ${cards.length} cards, ${imgs.length} with imgs`);

    const dataUris = [];
    for (const img of imgs) {
      try {
        const resp = await fetch(img.src, { credentials: 'include' });
        if (!resp.ok) { MC.log(`Fetch ${resp.status} for ${img.src}`); continue; }
        const blob = await resp.blob();
        const bmp = await createImageBitmap(blob);
        const w = Math.min(bmp.width, 400);
        const h = Math.round(bmp.height * (w / bmp.width));
        const canvas = document.createElement('canvas');
        canvas.width = w;
        canvas.height = h;
        const ctx = canvas.getContext('2d');
        ctx.drawImage(bmp, 0, 0, w, h);
        dataUris.push(canvas.toDataURL('image/jpeg', 0.7));
        bmp.close && bmp.close();
      } catch (e) {
        MC.log('Failed to extract image:', e.message);
      }
    }
    MC.log(`Extracted ${dataUris.length} creative thumbnails as base64`);
    return dataUris;
  },

  // ── Click animate button on a single card (no waiting) ──
  // Mirrors Selenium animate_selected_cards: queue all animations quickly,
  // then wait once page-level via _waitForAnimationsToComplete.
  async _clickAnimateButton(index, jobId) {
    const cards = document.querySelectorAll(SEL.creativeCard);
    if (!cards[index]) { MC.log(`No card at index ${index}`); return; }

    const card = cards[index];
    card.scrollIntoView({ block: 'center', behavior: 'instant' });
    await MC.sleep(400);

    // Reveal opacity:0 buttons via non-bubbling hover events on container...
    for (const evtName of ['mouseenter', 'pointerenter']) {
      card.dispatchEvent(new MouseEvent(evtName, { bubbles: false, cancelable: true }));
    }
    // ...and on the inner img (some Pomelli builds expect mouseover on the visual)
    const innerImg = card.querySelector('img');
    if (innerImg) {
      for (const evtName of ['mouseover', 'pointerover']) {
        innerImg.dispatchEvent(new MouseEvent(evtName, { bubbles: false, cancelable: true }));
      }
    }
    await MC.sleep(2000);

    // Pick the mdc-button variant (NOT mdc-icon-button)
    const animateButtons = card.querySelectorAll('button.animate-button');
    let btn = null;
    for (const b of animateButtons) {
      if (b.classList.contains('mdc-button') && !b.classList.contains('mdc-icon-button')) {
        btn = b;
        break;
      }
    }
    if (!btn) btn = card.querySelector('button.animate-button.mdc-button')
      || card.querySelector('button.animate-button')
      || card.querySelector('button[aria-label="Animate"]');

    if (!btn) { MC.log(`No animate button in card ${index}`); return; }

    await MC.sendStatus(jobId, 'animating', `Queuing animate ${index + 1}...`);
    MC.click(btn);
    await MC.sleep(3000);
    MC.log(`Card ${index}: animate button clicked`);
  },

  // ── Wait for ALL animations to finish (page-level) ──
  // Mirrors Selenium _wait_for_animations_to_complete.
  async _waitForAnimationsToComplete(jobId, videosBefore) {
    const start = Date.now();
    const timeout = 600000;  // 10 min
    let lastLog = 0;
    while (Date.now() - start < timeout) {
      const visible = (sel) => Array.from(document.querySelectorAll(sel))
        .filter(el => el.offsetParent !== null).length;
      const shimmer = visible('app-shimmer-loader');
      const spinner = visible('mat-progress-spinner');
      const progress = visible('app-generation-progress-loader .text');
      const totalLoading = shimmer + spinner + progress;
      const videoEls = document.querySelectorAll('video');
      const videoCount = videoEls.length;
      const elapsed = (Date.now() - start) / 1000;

      // Detect "high demand" / rate-limit error (check visible snackbars/banners only)
      const bannerSels = 'snack-bar-container, .mat-mdc-snack-bar-container, [role="alert"], .error-banner, .cdk-overlay-pane';
      const errBanner = Array.from(document.querySelectorAll(bannerSels))
        .some(el => el.offsetParent !== null && /high demand|try again later|unusual activity/i.test(el.textContent || ''));

      if (Date.now() - lastLog > 8000) {
        MC.log(`Animate poll: shimmer=${shimmer}, spinner=${spinner}, progress=${progress}, videos=${videoCount}, elapsed=${elapsed.toFixed(0)}s`);
        await MC.sendStatus(jobId, 'animating',
          `Waiting for animations... ${videoCount} video(s), ${totalLoading} loader(s), ${elapsed.toFixed(0)}s`);
        lastLog = Date.now();
      }

      if (errBanner && elapsed > 30) {
        MC.log('Animate: high-demand banner detected — aborting wait');
        return;
      }

      // Done: at least one new video AND no loaders
      if (videoCount > videosBefore && totalLoading === 0) {
        MC.log(`Animate complete: ${videoCount} videos, 0 loaders, ${elapsed.toFixed(1)}s`);
        return;
      }

      // No early give-up — keep polling until video appears or 10min timeout
      // (Selenium WAIT_ANIMATE = 600s with no early exit either)
      await MC.sleep(8000);
    }
    MC.log('Animate wait timed out (10 min)');
  },

  // ── Download all creative card images ──
  // Server can't fetch Pomelli URLs (auth-gated). Fetch with page cookies,
  // convert to base64 data URI, POST to server with is_base64 flag.
  async _downloadAllCards(jobId) {
    // Trigger lazy-load for cards below the viewport
    window.scrollTo(0, document.body.scrollHeight);
    await MC.sleep(800);
    window.scrollTo(0, 0);
    await MC.sleep(500);

    const cards = Array.from(document.querySelectorAll(SEL.creativeCard));
    const srcs = Array.from(new Set(
      cards
        .map(c => c.querySelector('img'))
        .filter(img => img && img.src && (img.naturalWidth || 0) > 0)
        .map(img => img.src)
    ));
    MC.log(`Downloading ${srcs.length} unique images from ${cards.length} cards...`);

    const downloaded = [];
    for (let i = 0; i < srcs.length; i++) {
      const src = srcs[i];
      try {
        const resp = await fetch(src, { credentials: 'include' });
        if (!resp.ok) { MC.log(`  [${i}] fetch ${resp.status}`); continue; }
        const blob = await resp.blob();
        const dataUri = await new Promise((resolve, reject) => {
          const reader = new FileReader();
          reader.onload = () => resolve(reader.result);
          reader.onerror = () => reject(reader.error);
          reader.readAsDataURL(blob);
        });
        const postRes = await fetch(`${MC.SERVER}/api/ext/download`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ url: dataUri, index: i, is_base64: true, job_id: jobId })
        });
        const postData = await postRes.json().catch(() => ({}));
        MC.log(`  [${i}] ${blob.size}b → server: ${JSON.stringify(postData)}`);
        if (postRes.ok) downloaded.push(src);
      } catch (e) {
        MC.log(`  [${i}] download failed: ${e.message}`);
      }
    }
    // Download videos — check <source> children too (same as Selenium)
    window.scrollTo(0, 0);
    await MC.sleep(1000);
    window.scrollTo(0, document.body.scrollHeight / 2);
    await MC.sleep(1000);
    window.scrollTo(0, 0);
    await MC.sleep(2000);
    const videos = document.querySelectorAll('video');
    MC.log(`Found ${videos.length} video elements on page`);
    for (const video of videos) {
      let src = video.src || video.currentSrc || '';
      if (!src || src.startsWith('blob:') || src.startsWith('data:')) {
        const sources = video.querySelectorAll('source');
        for (const s of sources) {
          if (s.src && s.src.startsWith('http')) { src = s.src; break; }
        }
      }
      MC.log(`Video element: src=${src.substring(0, 80)}`);
      if (src && src.startsWith('http')) {
        try {
          MC.log(`Downloading video: ${src.substring(0, 80)}...`);
          const resp = await fetch(src, { credentials: 'include' });
          const blob = await resp.blob();
          const dataUri = await new Promise((resolve) => {
            const reader = new FileReader();
            reader.onloadend = () => resolve(reader.result);
            reader.readAsDataURL(blob);
          });
          await fetch(`${MC.SERVER}/api/ext/download`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ url: dataUri, index: downloaded.length, is_base64: true, job_id: jobId })
          });
          MC.log(`Video saved: ${blob.size} bytes`);
          downloaded.push(src);
        } catch (e) {
          MC.log(`Video download failed: ${e.message}`);
        }
      }
    }

    MC.log(`Downloaded ${downloaded.length} total (images + videos)`);
    return downloaded;
  },

  // ── Poll server for user selection ──
  async _waitForSelection(jobId, timeout = 300000) {
    MC.log(`_waitForSelection: polling /api/ext/selection/${jobId} (timeout ${timeout}ms)`);
    const start = Date.now();
    let polls = 0;
    while (Date.now() - start < timeout) {
      polls++;
      try {
        const res = await fetch(`${MC.SERVER}/api/ext/selection/${jobId}`);
        if (res.status === 204) {
          // No selection yet — empty body, skip res.json()
          if (polls % 10 === 1) MC.log(`_waitForSelection poll #${polls}: 204 (no selection yet)`);
        } else if (res.ok) {
          const data = await res.json();
          if (polls % 10 === 1) {
            MC.log(`_waitForSelection poll #${polls}: status=${res.status}, data=${JSON.stringify(data)}`);
          }
          if (data && data.selected) {
            MC.log(`_waitForSelection received selection on poll #${polls}: ${JSON.stringify(data)}`);
            return data;
          }
        } else if (polls % 10 === 1) {
          MC.log(`_waitForSelection poll #${polls}: HTTP ${res.status}`);
        }
      } catch (e) {
        if (polls % 10 === 1) MC.log(`_waitForSelection poll #${polls} error: ${e.message}`);
      }
      await MC.sleep(2000);
    }
    MC.log(`_waitForSelection timed out after ${polls} polls`);
    return null;
  }
};


// ═══════════════════════════════════════════
// PHOTOSHOOT BOT
// ═══════════════════════════════════════════

const PhotoshootBot = {

  async run(job) {
    const { image_url, image_filename, templates, aspect_ratio, photoshoot_mode, job_id } = job;

    try {
      // Step 1: Navigate to photoshoot
      MC.log('Photoshoot: navigating');
      await MC.sendStatus(job_id, 'navigating', 'Opening Pomelli...');

      // Step 2: Wait for editor or landing page
      await MC.sendStatus(job_id, 'navigating', 'Waiting for page...');
      await MC.sleep(8000);

      // Step 3: Click mode card if on landing page
      const modeCard = document.querySelector(SEL.photoshootModeCard);
      if (modeCard) {
        MC.click(modeCard);
        await MC.sleep(3000);
      }

      // Step 4: Set aspect ratio
      if (aspect_ratio) {
        await MC.sendStatus(job_id, 'entering_prompt', `Setting aspect ratio: ${aspect_ratio}`);
        const arSelector = document.querySelector('app-aspect-ratio-selector button');
        if (arSelector) {
          MC.click(arSelector);
          await MC.sleep(500);
          const ratioMap = { story: '9:16', square: '1:1', feed: '4:5' };
          const target = ratioMap[aspect_ratio] || '9:16';
          const menuItem = await MC.waitForText('button.mat-mdc-menu-item', target, 5000);
          if (menuItem) MC.click(menuItem);
          await MC.sleep(500);
        }
      }

      // Step 5: Upload product image
      if (image_url) {
        await MC.sendStatus(job_id, 'entering_prompt', `Uploading: ${image_filename}`);

        // Click Product Image edit button (first edit)
        const editBtns = document.querySelectorAll('button');
        for (const btn of editBtns) {
          if (btn.textContent.includes('edit') && btn.offsetHeight > 0) {
            MC.click(btn);
            break;
          }
        }
        await MC.sleep(2000);

        // Find file input
        const fileInput = document.querySelector(SEL.psFileInput);
        if (fileInput) {
          await MC.uploadFile(fileInput, image_url, image_filename);
          MC.log('Photoshoot: image uploaded');
          await MC.sleep(5000);

          // Click Looks Good
          const lgBtn = await MC.waitForText('button', 'Looks Good', 10000);
          if (lgBtn) MC.click(lgBtn);
          await MC.sleep(2000);
        }
      }

      // Step 6: Select templates
      if (templates && templates.length) {
        await MC.sendStatus(job_id, 'entering_prompt', `Selecting templates...`);

        // Click Templates edit (second edit)
        // Wait for Templates button to be enabled
        await MC.sleep(3000);
        const editBtns2 = document.querySelectorAll('button');
        let clickedEdit = false;
        for (const btn of editBtns2) {
          if (btn.textContent.includes('edit') && btn.offsetHeight > 0 && !btn.disabled) {
            MC.click(btn);
            clickedEdit = true;
            break;
          }
        }
        if (!clickedEdit) MC.log('Photoshoot: edit button not found for templates');
        await MC.sleep(3000);

        // Read current templates and swap
        await this._selectTemplates(templates);

        // Click Looks Good
        const lgBtn2 = await MC.waitForText('button', 'Looks Good', 10000);
        if (lgBtn2) MC.click(lgBtn2);
        await MC.sleep(1000);
      }

      // Step 7: Click Generate Photoshoot
      await MC.sendStatus(job_id, 'generating', 'Generating photoshoot...');
      const genBtn = MC.btnByText('Generate Photoshoot') || MC.btnByText('Generate');
      if (genBtn) MC.click(genBtn);

      // Step 8: Wait for images
      await MC.sendStatus(job_id, 'generating', 'Waiting for images...');
      await this._waitForImages();

      // Step 9: Download via fetch+base64 (same as CampaignBot)
      await MC.sendStatus(job_id, 'downloading', 'Downloading...');
      window.scrollTo(0, document.body.scrollHeight);
      await MC.sleep(1000);
      window.scrollTo(0, 0);
      await MC.sleep(1000);

      const cards = document.querySelectorAll('.creative-card-container, .shot-result-card, .generated-image');
      const allImgs = cards.length > 0
        ? [...cards].map(c => c.querySelector('img')).filter(i => i && i.src && (i.naturalWidth||0) > 0)
        : [...document.querySelectorAll('img')].filter(i => i.offsetParent && i.src && (i.naturalWidth||0) > 200);
      const uniqueSrcs = [...new Set(allImgs.map(i => i.src))];
      MC.log(`Photoshoot: ${uniqueSrcs.length} images to download`);

      const downloaded = [];
      for (let i = 0; i < uniqueSrcs.length; i++) {
        try {
          const resp = await fetch(uniqueSrcs[i], { credentials: 'include' });
          const blob = await resp.blob();
          const dataUri = await new Promise(resolve => {
            const reader = new FileReader();
            reader.onloadend = () => resolve(reader.result);
            reader.readAsDataURL(blob);
          });
          await fetch(`${MC.SERVER}/api/ext/download`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ url: dataUri, index: i, is_base64: true, job_id: job_id })
          });
          downloaded.push(uniqueSrcs[i]);
          MC.log(`Photoshoot: saved image ${i+1}/${uniqueSrcs.length}`);
        } catch (e) {
          MC.log(`Photoshoot: download failed ${i}: ${e.message}`);
        }
      }

      // Save to collection
      await MC.sendStatus(job_id, 'saving', 'Saving to collection...');
      let collectionId = '';
      try {
        const finRes = await fetch(`${MC.SERVER}/api/ext/finalize`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ job_id: job_id })
        });
        const finData = await finRes.json();
        collectionId = finData.collection_id || '';
        MC.log(`Photoshoot: saved to collection ${collectionId}`);
      } catch (e) {
        MC.log(`Photoshoot: finalize failed: ${e.message}`);
      }

      await MC.sendStatus(job_id, 'complete', `Done! ${downloaded.length} images downloaded.`, {
        downloaded, collection_id: collectionId
      });

    } catch (err) {
      MC.log('Photoshoot error:', err);
      await MC.sendStatus(job_id, 'error', `Failed: ${err.message}`);
    }
  },

  // ── Select templates by hover+click on shot-thumbnail cards ──
  async _selectTemplates(wanted) {
    const cards = document.querySelectorAll(SEL.shotThumbnail);
    MC.log(`Photoshoot: ${cards.length} template cards found, want: ${wanted.join(', ')}`);

    // Read current state
    const current = [];
    const cardMap = {};

    for (const card of cards) {
      // Hover to reveal label
      card.dispatchEvent(new MouseEvent('mouseenter', { bubbles: true }));
      await MC.sleep(200);
      const label = card.textContent.trim().replace('arrow_drop_down', '').trim();
      if (label) {
        cardMap[label] = card;
        if (card.classList.contains('selected')) current.push(label);
      }
    }

    const toDeselect = current.filter(t => !wanted.includes(t));
    const toSelect = wanted.filter(t => !current.includes(t));

    // Swap one-by-one
    for (let i = 0; i < Math.max(toDeselect.length, toSelect.length); i++) {
      if (toDeselect[i] && cardMap[toDeselect[i]]) {
        MC.click(cardMap[toDeselect[i]]);
        await MC.sleep(500);
      }
      if (toSelect[i] && cardMap[toSelect[i]]) {
        MC.click(cardMap[toSelect[i]]);
        await MC.sleep(500);
      }
    }

    MC.log('Photoshoot: templates selected');
  },

  // ── Wait for generated images ──
  async _waitForImages(timeout = 180000) {
    const start = Date.now();
    while (Date.now() - start < timeout) {
      const loading = document.querySelectorAll('[class*="loading"], mat-spinner');
      if (loading.length === 0) {
        const images = document.querySelectorAll('img.thumbnail, img[class*="generated"]');
        if (images.length > 0) {
          MC.log(`Photoshoot: ${images.length} images loaded`);
          return;
        }
      }
      await MC.sleep(5000);
    }
    throw new Error('Images did not load');
  }
};


// ═══════════════════════════════════════════
// COMMAND LISTENER
// ═══════════════════════════════════════════

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg.type === 'RUN_JOB') {
    const job = msg.job;
    MC.log('Received job:', job.job_type, job.job_id);

    if (job.job_type === 'campaign') {
      CampaignBot.run(job);
    } else if (job.job_type === 'photoshoot') {
      PhotoshootBot.run(job);
    }

    sendResponse({ ok: true });
  }
  return true;  // async
});

MC.log('Pomelli content script loaded on:', location.href);

// Self-check: poll server for any pending job (backup if background dispatch failed)
(async function selfCheck() {
  await MC.sleep(3000);  // Let background dispatch try first
  try {
    const res = await fetch(MC.SERVER + '/api/ext/pending-for-tab');
    if (res.ok) {
      const job = await res.json();
      if (job && job.job_id) {
        MC.log('Self-check found pending job:', job.job_type, job.job_id);
        if (job.job_type === 'campaign') CampaignBot.run(job);
        else if (job.job_type === 'photoshoot') PhotoshootBot.run(job);
        // Ack the job
        await fetch(MC.SERVER + '/api/ext/ack', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ job_id: job.job_id, profile_id: 'content-script' })
        });
      }
    }
  } catch (e) {}
})();
