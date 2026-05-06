// ═══════════════════════════════════════════
// Mr.Creative Extension — Pomelli Bot
// Runs on: labs.google.com/pomelli/*
// Handles: Campaign + Photoshoot modes
// ═══════════════════════════════════════════

// ── DOM SELECTORS (from Chrome DevTools console dumps, May 5 2026) ──
const SEL = {
  // Campaign landing page (/campaigns)
  textarea:           'textarea[placeholder*="Describe the campaign"]',
  imagesBtn:          'button[aria-label="Add image ingredient"]',
  aspectRatioBtn:     'button.aspect-ratio-button',
  generateIdeasBtn:   'button[aria-label="Generate Ideas"]',
  productBtn:         'button[aria-label="Add product"]',

  // Aspect ratio menu items
  aspectMenuItem:     'button.mat-mdc-menu-item',

  // Select Images dialog (CDK overlay)
  imageDialog:        'app-image-ingredient-picker-dialog',
  uploadComponent:    'app-upload-image-button',
  uploadBtn:          'app-upload-image-button button',
  fileInput:          'app-upload-image-button input[type="file"]',
  dialogConfirmBtn:   '.cdk-overlay-pane button',  // scan for "Update"/"Confirm" text

  // Creatives page (after idea selected)
  creativeGrid:       'div.creative-grid',
  creativeCard:       'div.creative-card-container',
  creativeCardImg:    'div.creative-card-container img',
  animateBtn:         'button[aria-label="Animate"]',
  animateNoTextBtn:   'button[aria-label="Animate without text"]',
  moreBtn:            'button[aria-label="More"]',
  backBtn:            'button.back-button',
  addCreativeBtn:     'button',  // text "Add Creative"

  // Idea cards (campaign results)
  ideaCard:           'mat-card, [class*="idea-card"], [class*="suggestion"]',
  deleteIdeaBtn:      'button[aria-label="Delete idea"]',

  // Photoshoot page
  photoshootModeCard: 'div.photoshoot-branch-button',
  shotThumbnail:      'div.shot-thumbnail',
  selectionCount:     'span.selection-count',
  looksGoodBtn:       'button',  // text "Looks Good"

  // Photoshoot upload
  psUploadComponent:  'app-upload-image-button',
  psFileInput:        'app-upload-image-button input[type="file"]',
  psAspectSelector:   'app-aspect-ratio-selector button',
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

      if (!location.href.includes('/campaigns')) {
        location.href = 'https://labs.google.com/pomelli/campaigns';
        await MC.sleep(5000);
        await MC.waitFor(SEL.textarea, 30000);
      }

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

      // Step 3: Upload image
      if (image_url) {
        MC.log('Campaign: uploading image');
        await MC.sendStatus(job_id, 'entering_prompt', `Adding image: ${image_filename}`);

        // Click "Images" button
        const imgBtn = await MC.waitFor(SEL.imagesBtn);
        MC.click(imgBtn);
        await MC.sleep(3000);

        // Wait for dialog
        await MC.waitFor(SEL.imageDialog);
        MC.log('Campaign: dialog opened');
        await MC.sleep(2000);

        // Find file input inside dialog's upload component
        const pane = this._getDialogPane();
        const fileInput = pane
          ? pane.querySelector(SEL.fileInput)
          : document.querySelector(SEL.fileInput);

        if (fileInput) {
          await MC.uploadFile(fileInput, image_url, image_filename);
          MC.log('Campaign: file uploaded via input');
          await MC.sleep(5000);  // wait for upload + auto-select

          // Click Update/Confirm
          await this._clickDialogConfirm(pane);
          await MC.sleep(2000);
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

      // Step 7: Send idea cards to server for user selection
      const ideas = ideaCards.map((card, i) => ({
        index: i,
        text: card.textContent.trim().substring(0, 200)
      }));
      await MC.sendStatus(job_id, 'waiting_selection', 'Select a campaign idea...', { ideas });

      // Step 8: Wait for user selection from server
      MC.log('Campaign: waiting for user to select idea');
      const selection = await this._waitForSelection(job_id);

      if (selection && selection.idea_index !== undefined) {
        // Click the selected idea card
        const cards = document.querySelectorAll(SEL.deleteIdeaBtn);
        // The idea cards are siblings of delete buttons — find the card container
        const allCards = this._getVisibleIdeaCards();
        if (allCards[selection.idea_index]) {
          MC.click(allCards[selection.idea_index]);
          MC.log(`Campaign: selected idea ${selection.idea_index}`);
        }

        // Step 9: Wait for creatives to load
        await MC.sendStatus(job_id, 'generating', 'Generating creatives...');
        await this._waitForCreatives();

        // Step 10: Extract creative images and send to server
        const images = MC.getCardImages();
        MC.log(`Campaign: ${images.length} creatives ready`);
        await MC.sendStatus(job_id, 'waiting_animate', 'Select images to animate...', { images });

        // Step 11: Wait for animate selection
        const animateSelection = await this._waitForSelection(job_id);

        if (animateSelection && animateSelection.animate_indices) {
          // Animate only selected cards
          for (const idx of animateSelection.animate_indices) {
            await this._animateCard(idx, job_id);
          }
        }

        // Step 12: Download all images
        await MC.sendStatus(job_id, 'downloading', 'Downloading images...');
        const downloadedImages = await this._downloadAllCards();
        await MC.sendStatus(job_id, 'complete', `Done! ${downloadedImages.length} assets downloaded.`, {
          downloaded: downloadedImages
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
    // Idea cards are clickable cards with campaign descriptions
    // They appear below the prompt area with titles + descriptions
    const cards = [];
    const containers = document.querySelectorAll('mat-card, [class*="idea"], [class*="suggestion-card"]');
    for (const c of containers) {
      if (c.offsetHeight > 0 && c.textContent.trim().length > 20) {
        cards.push(c);
      }
    }
    return cards;
  },

  // ── Wait for creatives (images) to load ──
  async _waitForCreatives(timeout = 180000) {
    MC.log('Waiting for creatives...');
    const start = Date.now();
    while (Date.now() - start < timeout) {
      const cards = document.querySelectorAll(SEL.creativeCard);
      if (cards.length >= 4) {
        // Check if all have loaded images (not loading spinners)
        const loading = document.querySelectorAll('[class*="loading"], [class*="spinner"]');
        const loadingInGrid = Array.from(loading).filter(l =>
          l.closest(SEL.creativeGrid) || l.closest(SEL.creativeCard)
        );
        if (loadingInGrid.length === 0) {
          MC.log(`All ${cards.length} creatives loaded`);
          return;
        }
      }
      await MC.sleep(3000);
    }
    throw new Error('Creatives did not load');
  },

  // ── Animate a specific card by index ──
  async _animateCard(index, jobId) {
    const cards = document.querySelectorAll(SEL.creativeCard);
    if (!cards[index]) return;

    const card = cards[index];
    const animBtn = card.querySelector(SEL.animateBtn.replace('button', '') + ', button.animate-button');

    // Find animate button inside this specific card
    const btn = card.querySelector('button.animate-button') ||
                card.querySelector('button[aria-label="Animate"]');

    if (!btn) { MC.log(`No animate button in card ${index}`); return; }

    await MC.sendStatus(jobId, 'animating', `Animating card ${index + 1}...`);
    MC.click(btn);

    // Wait for animation to complete (video element appears or loading finishes)
    await MC.sleep(30000);  // Animations take ~30s
    MC.log(`Card ${index} animated`);
  },

  // ── Download all creative card images ──
  async _downloadAllCards() {
    const images = MC.getCardImages();
    const downloaded = [];

    for (let i = 0; i < images.length; i++) {
      try {
        // Send image URL to server for download
        await fetch(`${MC.SERVER}/api/ext/download`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ url: images[i], index: i })
        });
        downloaded.push(images[i]);
      } catch (e) {
        MC.log(`Download failed for card ${i}:`, e);
      }
    }
    return downloaded;
  },

  // ── Poll server for user selection ──
  async _waitForSelection(jobId, timeout = 300000) {
    const start = Date.now();
    while (Date.now() - start < timeout) {
      try {
        const res = await fetch(`${MC.SERVER}/api/ext/selection/${jobId}`);
        if (res.ok) {
          const data = await res.json();
          if (data && data.selected) return data;
        }
      } catch (e) { /* retry */ }
      await MC.sleep(2000);
    }
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

      if (!location.href.includes('/photoshoot')) {
        location.href = 'https://labs.google.com/pomelli/photoshoot';
        await MC.sleep(5000);
      }

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

      // Step 9: Download
      await MC.sendStatus(job_id, 'downloading', 'Downloading...');
      const images = MC.getCardImages('img.thumbnail, img[class*="generated"]');
      MC.log(`Photoshoot: ${images.length} images ready`);

      for (let i = 0; i < images.length; i++) {
        await fetch(`${MC.SERVER}/api/ext/download`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ url: images[i], index: i, job_id })
        });
      }

      await MC.sendStatus(job_id, 'complete', `Done! ${images.length} images downloaded.`);

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
