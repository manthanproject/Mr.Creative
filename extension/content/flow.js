// ═══════════════════════════════════════════
// Mr.Creative Extension — Flow Bot
// Runs on: labs.google/fx/tools/flow*
// Handles: A+ content / banner generation
// ═══════════════════════════════════════════

const FlowBot = {

  async run(job) {
    const { prompt_text, image_url, image_filename, aspect_ratio, count, reuse_project, job_id } = job;

    try {
      // Step 1: Navigate if needed
      if (!location.href.includes('/flow')) {
        location.href = 'https://labs.google/fx/tools/flow';
        await MC.sleep(5000);
      }

      await MC.sendStatus(job_id, 'navigating', 'Flow page ready');

      if (reuse_project) {
        // Batch 2+: already on project page
        await this._enterPromptAndGenerate(prompt_text, image_url, image_filename, job_id);
      } else {
        // Batch 1: create new project
        await this._createNewProject(prompt_text, image_url, image_filename, aspect_ratio, job_id);
      }

      // Wait for images to generate
      await MC.sendStatus(job_id, 'generating', 'Waiting for images...');
      await this._waitForResults(job_id);

      // Download
      await MC.sendStatus(job_id, 'downloading', 'Downloading images...');
      await this._downloadResults(job_id, count || 4);

      await MC.sendStatus(job_id, 'complete', 'Flow batch complete!');

    } catch (err) {
      MC.log('Flow error:', err);
      await MC.sendStatus(job_id, 'error', `Failed: ${err.message}`);
    }
  },

  async _createNewProject(prompt, imageUrl, imageFilename, aspectRatio, jobId) {
    await MC.sendStatus(jobId, 'entering_prompt', 'Creating new project...');

    // Find prompt input (textarea or contenteditable)
    const promptEl = await MC.waitFor('textarea, [contenteditable="true"], input[type="text"]', 15000);
    if (promptEl.tagName === 'TEXTAREA' || promptEl.tagName === 'INPUT') {
      promptEl.value = prompt;
      promptEl.dispatchEvent(new Event('input', { bubbles: true }));
    } else {
      promptEl.textContent = prompt;
      promptEl.dispatchEvent(new Event('input', { bubbles: true }));
    }
    await MC.sleep(1000);

    // Upload reference image if provided
    if (imageUrl) {
      await this._uploadReferenceImage(imageUrl, imageFilename, jobId);
    }

    // Click Create/Generate
    const createBtn = MC.btnByText('Create') || MC.btnByText('Generate');
    if (createBtn) {
      MC.click(createBtn);
      MC.log('Flow: clicked Create');
    }
  },

  async _enterPromptAndGenerate(prompt, imageUrl, imageFilename, jobId) {
    await MC.sendStatus(jobId, 'entering_prompt', 'Entering prompt (batch 2+)...');

    // Find prompt area on existing project
    const promptEl = document.querySelector('textarea, [contenteditable="true"]');
    if (promptEl) {
      if (promptEl.tagName === 'TEXTAREA') {
        promptEl.value = prompt;
      } else {
        promptEl.textContent = prompt;
      }
      promptEl.dispatchEvent(new Event('input', { bubbles: true }));
    }

    // Upload reference image (every batch)
    if (imageUrl) {
      await this._uploadReferenceImage(imageUrl, imageFilename, jobId);
    }

    // Click generate
    await MC.sleep(1000);
    const genBtn = MC.btnByText('Create') || MC.btnByText('Generate');
    if (genBtn) MC.click(genBtn);
  },

  async _uploadReferenceImage(imageUrl, filename, jobId) {
    await MC.sendStatus(jobId, 'entering_prompt', `Uploading reference: ${filename}`);

    // Look for file input on page
    const fileInput = document.querySelector('input[type="file"]');
    if (fileInput) {
      await MC.uploadFile(fileInput, imageUrl, filename);
      MC.log('Flow: reference image uploaded via input');
      await MC.sleep(3000);
      return;
    }

    // If no file input visible, click + button to open upload panel
    const addBtn = MC.btnByText('+') || document.querySelector('button[aria-label*="add"], button[aria-label*="upload"]');
    if (addBtn) {
      MC.click(addBtn);
      await MC.sleep(2000);

      // Now find file input
      const fi = document.querySelector('input[type="file"]');
      if (fi) {
        await MC.uploadFile(fi, imageUrl, filename);
        MC.log('Flow: reference image uploaded after clicking +');
        await MC.sleep(3000);
      }
    }
  },

  async _waitForResults(jobId, timeout = 300000) {
    const start = Date.now();
    let lastCount = 0;

    while (Date.now() - start < timeout) {
      // Count loaded images (not spinners)
      const images = document.querySelectorAll('img[src*="blob:"], img[src*="lh3.google"]');
      const spinners = document.querySelectorAll('[class*="loading"], [class*="spinner"], mat-spinner');

      if (images.length > lastCount) {
        lastCount = images.length;
        await MC.sendStatus(jobId, 'generating', `${images.length} images loaded...`);
      }

      if (images.length > 0 && spinners.length === 0) {
        MC.log(`Flow: ${images.length} results ready`);
        return;
      }

      await MC.sleep(5000);
    }
    throw new Error('Flow results did not load');
  },

  async _downloadResults(jobId, count) {
    const images = document.querySelectorAll('img[src*="blob:"], img[src*="lh3.google"]');
    let downloaded = 0;

    for (let i = 0; i < Math.min(images.length, count); i++) {
      try {
        // Try to find 2K download button
        // Flow has a download dropdown with resolution options
        const card = images[i].closest('[class*="card"], [class*="result"]');
        if (card) {
          const dlBtn = card.querySelector('button[aria-label*="ownload"]');
          if (dlBtn) {
            MC.click(dlBtn);
            await MC.sleep(1000);

            // Look for 2K option in dropdown
            const twoK = MC.btnByText('2K') || MC.btnByText('2048');
            if (twoK) {
              MC.click(twoK);
              await MC.sleep(2000);
            }
            downloaded++;
            continue;
          }
        }

        // Fallback: send URL to server
        await fetch(`${MC.SERVER}/api/ext/download`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ url: images[i].src, index: i, job_id: jobId })
        });
        downloaded++;
      } catch (e) {
        MC.log(`Flow download ${i} failed:`, e);
      }
    }

    MC.log(`Flow: downloaded ${downloaded} images`);
  }
};

// ── Command listener ──
chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg.type === 'RUN_JOB') {
    FlowBot.run(msg.job);
    sendResponse({ ok: true });
  }
  return true;
});

MC.log('Flow content script loaded on:', location.href);
