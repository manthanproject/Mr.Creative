// ═══════════════════════════════════════════
// Mr.Creative Extension — Flow Bot
// Runs on: labs.google/fx/tools/flow*
// DOM selectors verified May 8 2026
// ═══════════════════════════════════════════

const FSEL = {
  promptInput:    'div[contenteditable="true"]',
  submitBtn:      'button.sc-e5032833-5',
  settingsBtn:    'button.sc-3bb56e4a-0',
  aspectRatio:    '.flow_tab_slider_trigger',
  fileInput:      'input[type="file"][accept="image/*"]',
  resultImages:   'img[src*="blob:"], img[src*="lh3.google"], img[src*="generated"]',
  spinners:       '[class*="loading"], [class*="spinner"], mat-spinner, [class*="shimmer"]',
};

MC.log('Flow content script loaded on:', location.href);

const FlowBot = {
  async run(job) {
    var prompt_text = job.prompt_text, image_url = job.image_url, image_filename = job.image_filename;
    var count = job.count, job_id = job.job_id;
    try {
      MC.log('Flow: starting job', job_id, 'prompt length:', prompt_text ? prompt_text.length : 0);
      await MC.sendStatus(job_id, 'navigating', 'Waiting for Flow page...');
      await this._waitForPageReady();
      if (image_url) {
        await MC.sendStatus(job_id, 'entering_prompt', 'Uploading reference: ' + image_filename);
        await this._uploadReferenceImage(image_url, image_filename);
      }
      await MC.sendStatus(job_id, 'entering_prompt', 'Typing prompt...');
      await this._typePrompt(prompt_text);
      await MC.sendStatus(job_id, 'generating', 'Submitting to Flow...');
      await this._clickSubmit();
      await MC.sendStatus(job_id, 'generating', 'Waiting for images...');
      await this._waitForResults(job_id);
      await MC.sendStatus(job_id, 'downloading', 'Downloading images...');
      await this._downloadResults(job_id, count || 4);
      await MC.sendStatus(job_id, 'complete', 'Flow generation complete!');
    } catch (err) {
      MC.log('Flow error:', err);
      await MC.sendStatus(job_id, 'error', 'Failed: ' + err.message);
    }
  },

  async _waitForPageReady() {
    // Check if on landing page (no prompt input) — click New Project
    await MC.sleep(2000);
    var promptEl = document.querySelector(FSEL.promptInput);
    if (!promptEl) {
      MC.log('Flow: on landing page, clicking New Project...');
      var newBtn = [...document.querySelectorAll('button')].find(function(b) {
        return b.textContent.includes('New project') || b.textContent.includes('new_project');
      });
      if (newBtn) {
        MC.click(newBtn);
        MC.log('Flow: clicked New Project');
        await MC.sleep(5000);
      }
    }
    var el = await MC.waitFor(FSEL.promptInput, 30000);
    MC.log('Flow: page ready, prompt input found');
    await MC.sleep(1000);
    return el;
  },

  async _typePrompt(prompt) {
    var promptEl = document.querySelector(FSEL.promptInput);
    if (!promptEl) throw new Error('Prompt input not found');
    promptEl.focus();
    await MC.sleep(300);
    promptEl.innerHTML = '<p>' + prompt.replace(/\n/g, '</p><p>') + '</p>';
    promptEl.dispatchEvent(new Event('input', { bubbles: true }));
    promptEl.dispatchEvent(new Event('change', { bubbles: true }));
    await MC.sleep(500);
    var textLen = promptEl.textContent.trim().length;
    MC.log('Flow: typed prompt, length:', textLen);
    if (textLen < 20) {
      promptEl.textContent = prompt;
      promptEl.dispatchEvent(new Event('input', { bubbles: true }));
      await MC.sleep(500);
    }
  },

  async _uploadReferenceImage(imageUrl, filename) {
    var fileInput = document.querySelector(FSEL.fileInput);
    if (fileInput) {
      try {
        var resp = await fetch(imageUrl);
        var blob = await resp.blob();
        var file = new File([blob], filename || 'product.jpg', { type: blob.type });
        var dt = new DataTransfer();
        dt.items.add(file);
        fileInput.files = dt.files;
        fileInput.dispatchEvent(new Event('change', { bubbles: true }));
        MC.log('Flow: reference image uploaded');
        await MC.sleep(3000);
        return;
      } catch (e) { MC.log('Flow: upload failed:', e.message); }
    }
    var addBtn = [...document.querySelectorAll('button')].find(function(b) {
      return b.textContent.includes('Add Media') || b.textContent.includes('addAdd');
    });
    if (addBtn) {
      MC.click(addBtn);
      await MC.sleep(2000);
      var fi = document.querySelector(FSEL.fileInput);
      if (fi) {
        try {
          var r = await fetch(imageUrl);
          var bl = await r.blob();
          var f = new File([bl], filename || 'product.jpg', { type: bl.type });
          var d = new DataTransfer();
          d.items.add(f);
          fi.files = d.files;
          fi.dispatchEvent(new Event('change', { bubbles: true }));
          MC.log('Flow: image uploaded after Add Media');
          await MC.sleep(3000);
        } catch (e) { MC.log('Flow: fallback upload failed:', e.message); }
      }
    }
  },

  async _clickSubmit() {
    var submitBtn = document.querySelector(FSEL.submitBtn);
    if (!submitBtn) {
      submitBtn = [...document.querySelectorAll('button')].find(function(b) {
        return b.textContent.includes('arrow_forward') && b.textContent.includes('Create');
      });
    }
    if (!submitBtn) {
      submitBtn = [...document.querySelectorAll('button')].find(function(b) {
        var t = b.textContent.trim();
        return t.endsWith('Create') && t.includes('arrow');
      });
    }
    if (submitBtn) {
      MC.click(submitBtn);
      MC.log('Flow: clicked submit');
      await MC.sleep(2000);
    } else {
      throw new Error('Submit/Create button not found');
    }
  },

  async _waitForResults(jobId) {
    var timeout = 300000;
    var start = Date.now();
    var lastCount = 0;
    while (Date.now() - start < timeout) {
      var images = document.querySelectorAll(FSEL.resultImages);
      var spinners = [...document.querySelectorAll(FSEL.spinners)].filter(function(s) { return s.offsetHeight > 0; });
      if (images.length > lastCount) {
        lastCount = images.length;
        await MC.sendStatus(jobId, 'generating', images.length + ' images loaded...');
      }
      if (images.length > 0 && spinners.length === 0 && Date.now() - start > 15000) {
        MC.log('Flow: ' + images.length + ' results ready');
        return;
      }
      await MC.sleep(5000);
    }
    throw new Error('Flow results did not load within timeout');
  },

  async _downloadResults(jobId, count) {
    var images = document.querySelectorAll(FSEL.resultImages);
    var downloaded = 0;
    MC.log('Flow: found ' + images.length + ' images to download');
    for (var i = 0; i < Math.min(images.length, count); i++) {
      try {
        var imgSrc = images[i].src;
        if (!imgSrc || imgSrc === 'data:') continue;
        var card = images[i].closest('[class*="card"], [class*="result"], [class*="item"]');
        if (card) {
          var dlBtn = card.querySelector('button[aria-label*="ownload"]');
          if (dlBtn) {
            MC.click(dlBtn);
            await MC.sleep(1500);
            var twoK = [...document.querySelectorAll('button, [role="menuitem"]')].find(function(b) {
              return b.textContent.includes('2K') || b.textContent.includes('2048');
            });
            if (twoK) { MC.click(twoK); await MC.sleep(2000); downloaded++; continue; }
          }
        }
        var resp = await fetch(imgSrc);
        var blob = await resp.blob();
        var reader = new FileReader();
        var base64 = await new Promise(function(resolve) {
          reader.onload = function() { resolve(reader.result); };
          reader.readAsDataURL(blob);
        });
        await fetch(MC.SERVER + '/api/ext/download', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ url: imgSrc, data: base64, is_base64: true, index: i, job_id: jobId, filename: 'flow_' + (i+1) + '.png' })
        });
        downloaded++;
        MC.log('Flow: downloaded image ' + (i+1));
      } catch (e) { MC.log('Flow: download ' + i + ' failed:', e.message); }
    }
    MC.log('Flow: downloaded ' + downloaded + '/' + Math.min(images.length, count));
  }
};

chrome.runtime.onMessage.addListener(function(msg, sender, sendResponse) {
  if (msg.type === 'RUN_JOB' && (msg.job.job_type === 'flow' || msg.job.job_type === 'aplus')) {
    FlowBot.run(msg.job);
    sendResponse({ ok: true });
  }
  return true;
});

setTimeout(async function() {
  try {
    var res = await fetch(MC.SERVER + '/api/ext/pending-for-tab');
    if (res.ok && res.status !== 204) {
      var job = await res.json();
      if (job && job.job_id && (job.job_type === 'flow' || job.job_type === 'aplus')) {
        FlowBot.run(job);
        await fetch(MC.SERVER + '/api/ext/ack', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ job_id: job.job_id, profile_id: 'flow-content' })
        });
      }
    }
  } catch (e) {}
}, 3000);
