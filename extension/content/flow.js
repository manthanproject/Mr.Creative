// ═══════════════════════════════════════════
// Mr.Creative Extension — Flow Bot
// Matches Selenium FlowBot logic exactly
// DOM selectors verified May 8 2026
// ═══════════════════════════════════════════

const ASPECT_RATIO_MAP = {
  landscape: 'crop_16_916:9',
  square:    'crop_square1:1',
  story:     'crop_9_169:16',
  feed:      'crop_portrait3:4',
  wide:      'crop_landscape4:3',
};

MC.log('Flow content script loaded on:', location.href);
try { chrome.runtime.sendMessage({ type: 'ADD_CAPABILITY', capability: 'flow_active' }); } catch(e) {}

const FlowBot = {

  async run(job) {
    var prompts = job.prompts || [];
    var single = job.prompt_text || '';
    var image_url = job.image_url;
    var image_filename = job.image_filename || 'product.jpg';
    var aspect_ratio = job.aspect_ratio || 'square';
    var count = job.count || 1;
    var job_id = job.job_id;

    if (prompts.length === 0 && single) prompts = [single];
    MC.log('Flow: starting job', job_id, prompts.length + ' prompts');

    try {
      await MC.sendStatus(job_id, 'navigating', 'Opening Flow project...');
      await this._ensureProjectPage(job_id);

      await MC.sendStatus(job_id, 'settings', 'Setting: ' + aspect_ratio + ', ' + count + 'x');
      await this._setImageSettings(aspect_ratio, count);

      for (var i = 0; i < prompts.length; i++) {
        var promptText = typeof prompts[i] === 'object' ? prompts[i].prompt : prompts[i];
        MC.log('Flow: prompt ' + (i+1) + '/' + prompts.length);

        if (image_url) {
          await MC.sendStatus(job_id, 'generating', 'Image ' + (i+1) + '/' + prompts.length + ': uploading ref...');
          await this._uploadRefViaButton(image_url, image_filename);
        }

        await MC.sendStatus(job_id, 'generating', 'Image ' + (i+1) + '/' + prompts.length + ': typing prompt...');
        await this._typePrompt(promptText);

        if (image_url) await this._waitImgProcess();

        var before = this._countImages();
        await MC.sendStatus(job_id, 'generating', 'Image ' + (i+1) + '/' + prompts.length + ': creating...');
        await this._clickCreate();
        await this._waitForResults(job_id, before);
        MC.log('Flow: image ' + (i+1) + ' done!');

        if (i < prompts.length - 1) {
          var delay = Math.floor(Math.random() * 7000) + 5000;
          await MC.sendStatus(job_id, 'generating', 'Waiting ' + Math.round(delay/1000) + 's...');
          await MC.sleep(delay);
        }
      }

      await MC.sendStatus(job_id, 'downloading', 'Downloading ' + prompts.length + ' images...');
      await this._downloadAll(job_id, prompts.length);
      await MC.sendStatus(job_id, 'complete', prompts.length + ' images done!', {total_images: prompts.length});
    } catch (err) {
      MC.log('Flow error:', err);
      await MC.sendStatus(job_id, 'error', 'Failed: ' + err.message);
    }
  },

  async _uploadRefViaButton(imageUrl, filename) {
    // Click + button
    var plus = document.querySelector('button[aria-label="Add"]') || document.querySelector('.prompt-actions button');
    if (!plus) {
      var btns = document.querySelectorAll('button');
      for (var b of btns) { if (b.offsetParent && b.textContent.trim() === '+') { plus = b; break; } }
    }
    if (!plus) {
      // Try the + icon in prompt bar
      var icons = document.querySelectorAll('button');
      for (var b of icons) { if (b.offsetParent && b.innerHTML.includes('add') && b.getBoundingClientRect().width < 60) { plus = b; break; } }
    }
    if (plus) {
      plus.click();
      MC.log('Flow: + button clicked');
      await MC.sleep(1000);
    }

    // Click Upload image option
    var uploadOpt = null;
    var allEls = document.querySelectorAll('button, div, li, [role="menuitem"]');
    for (var el of allEls) {
      if (el.offsetParent && el.textContent.includes('Upload') && el.textContent.includes('image')) {
        uploadOpt = el;
        break;
      }
    }
    if (uploadOpt) {
      uploadOpt.click();
      MC.log('Flow: Upload image clicked');
      await MC.sleep(1000);
    }

    // Find file input and inject file
    var fileInput = document.querySelector('input[type="file"]');
    if (fileInput) {
      try {
        var resp = await fetch(imageUrl);
        var blob = await resp.blob();
        var file = new File([blob], filename, { type: blob.type });
        var dt = new DataTransfer();
        dt.items.add(file);
        fileInput.files = dt.files;
        fileInput.dispatchEvent(new Event('change', { bubbles: true }));
        MC.log('Flow: file injected');
        await MC.sleep(3000);
      } catch (e) { MC.log('Flow: upload failed:', e.message); }
    } else {
      MC.log('Flow: no file input found');
    }
  },

  async _waitImgProcess() {
    for (var i = 0; i < 30; i++) {
      var found = false;
      document.querySelectorAll('span, div, p').forEach(function(el) {
        if (el.offsetParent && el.textContent.trim().match(/^\d+%$/)) found = true;
      });
      if (!found) return;
      await MC.sleep(1000);
    }
  },

  async _downloadAll(jobId, count) {
    var allLinks = [];
    document.querySelectorAll('a[href*="/edit/"]').forEach(function(a) {
      if (a.querySelector('img[src*="getMediaUrlRedirect"]')) allLinks.push(a.getAttribute('href'));
    });
    var toDownload = allLinks.slice(-count);
    MC.log('Flow: downloading ' + toDownload.length + ' images');
    for (var i = 0; i < toDownload.length; i++) {
      await MC.sendStatus(jobId, 'downloading', 'Download ' + (i+1) + '/' + toDownload.length);
      await this._downloadSingleImage(toDownload[i], i, jobId);
    }
  },

  // ══════════════════════════════════════
  // NAVIGATION (matches Selenium navigate_to_flow)
  // ══════════════════════════════════════

  async _ensureProjectPage(jobId) {
    await MC.sleep(2000);

    // Already on project page?
    if (location.href.includes('/project/')) {
      MC.log('Flow: already on project page');
      // Wait for prompt bar
      await this._waitForPromptBar();
      return;
    }

    // On landing page — click New Project (15 retries like Selenium)
    MC.log('Flow: on landing page, clicking New Project...');
    for (var attempt = 0; attempt < 15; attempt++) {
      if (location.href.includes('/project/')) {
        await MC.sendStatus(jobId, 'navigating', 'Project page loaded!');
        break;
      }
      await MC.sendStatus(jobId, 'navigating', 'Clicking New Project (attempt ' + (attempt+1) + ')...');

      // Method 1: Find by innerText (matches Selenium)
      var clicked = false;
      var allEls = document.querySelectorAll('*');
      for (var el of allEls) {
        if (!el.offsetParent) continue;
        try {
          if (el.innerText && el.innerText.includes('New project')) {
            var r = el.getBoundingClientRect();
            if (r.width < 400 && r.height > 20) {
              el.scrollIntoView({block: 'center'});
              el.click();
              MC.log('Flow: clicked_text');
              clicked = true;
              break;
            }
          }
        } catch(e) {}
      }

      // Method 2: Find + card specifically
      if (!clicked) {
        var cards = document.querySelectorAll('div, button, a');
        for (var c of cards) {
          if (!c.offsetParent) continue;
          var t = c.textContent.trim();
          if (t.includes('New project') && t.includes('+')) {
            c.scrollIntoView({block: 'center'});
            c.click();
            MC.log('Flow: clicked_plus_card');
            clicked = true;
            break;
          }
        }
      }

      // Method 3: Click by position (center-bottom)
      if (!clicked) {
        var posEl = document.elementFromPoint(window.innerWidth / 2, window.innerHeight - 150);
        if (posEl) {
          posEl.click();
          MC.log('Flow: clicked_position_' + posEl.tagName);
          clicked = true;
        }
      }

      if (clicked) {
        await MC.sleep(5000);
        if (location.href.includes('/project/')) break;
      } else {
        await MC.sleep(2000);
      }
    }

    // Wait for prompt bar
    await this._waitForPromptBar();
  },

  async _waitForPromptBar() {
    for (var i = 0; i < 20; i++) {
      var divs = document.querySelectorAll('div[contenteditable="true"]');
      for (var d of divs) {
        if (d.getBoundingClientRect().width > 200) {
          MC.log('Flow: prompt bar found');
          return;
        }
      }
      await MC.sleep(2000);
    }
    throw new Error('Prompt bar did not appear');
  },

  // ══════════════════════════════════════
  // SETTINGS (matches Selenium set_image_settings)
  // ══════════════════════════════════════

  async _setImageSettings(aspectRatio, count) {
    // Open dropdown — click Nano Banana button
    var nanoBtns = document.querySelectorAll('button');
    var opened = false;
    for (var b of nanoBtns) {
      if (b.offsetParent && b.textContent.includes('Nano Banana')) {
        b.click();
        MC.log('Flow: opened model dropdown');
        opened = true;
        break;
      }
    }
    if (!opened) {
      MC.log('Flow: model dropdown not found, skipping settings');
      return;
    }
    await MC.sleep(1000);

    // Select Image mode
    this._clickFlowTab('imageImage');
    await MC.sleep(300);

    // Select aspect ratio
    var arText = ASPECT_RATIO_MAP[aspectRatio] || 'crop_square1:1';
    this._clickFlowTab(arText);
    await MC.sleep(300);

    // Select count
    this._clickFlowTab(count + 'x') || if (count > 1) this._clickFlowTab(count + 'x') || this._clickFlowTab('x' + count);
    await MC.sleep(300);

    // Close dropdown — click outside
    document.body.click();
    await MC.sleep(500);
    MC.log('Flow: settings applied — ' + aspectRatio + ' x' + count);
  },

  _clickFlowTab(targetText) {
    var btns = document.querySelectorAll('button.flow_tab_slider_trigger');
    for (var b of btns) {
      if (b.offsetParent && b.textContent.trim() === targetText) {
        b.scrollIntoView({block: 'center'});
        b.click();
        MC.log('Flow: tab click — ' + targetText);
        return true;
      }
    }
    MC.log('Flow: tab not found — ' + targetText);
    return false;
  },

  // ══════════════════════════════════════
  // PROMPT (matches Selenium type_prompt)
  // ══════════════════════════════════════

  async _typePrompt(prompt) {
    // Find widest contenteditable div (matches Selenium)
    var divs = document.querySelectorAll('div[contenteditable="true"]');
    var best = null, bestW = 0;
    for (var d of divs) {
      var w = d.getBoundingClientRect().width;
      if (w > bestW) { best = d; bestW = w; }
    }
    if (!best) throw new Error('Prompt input not found');

    // Focus and clear
    best.focus();
    await MC.sleep(300);
    best.innerHTML = '';
    await MC.sleep(200);

    // Type via innerHTML (extension cant use clipboard like Selenium)
    best.innerHTML = '<p>' + prompt.replace(/\n/g, '</p><p>') + '</p>';
    best.dispatchEvent(new Event('input', { bubbles: true }));
    await MC.sleep(500);

    var textLen = best.textContent.trim().length;
    MC.log('Flow: typed prompt, length:', textLen);

    // Fallback if innerHTML didnt work
    if (textLen < 20 && prompt.length > 20) {
      MC.log('Flow: innerHTML failed, trying textContent');
      best.textContent = prompt;
      best.dispatchEvent(new Event('input', { bubbles: true }));
      await MC.sleep(500);
      textLen = best.textContent.trim().length;
      MC.log('Flow: textContent length:', textLen);
    }
  },

  // ══════════════════════════════════════
  // UPLOAD REFERENCE IMAGE
  // ══════════════════════════════════════

  async _uploadReferenceImage(imageUrl, filename) {
    var fileInput = document.querySelector('input[type="file"][accept="image/*"]');
    if (!fileInput) {
      MC.log('Flow: no file input found');
      return;
    }
    try {
      var resp = await fetch(imageUrl);
      var blob = await resp.blob();
      var file = new File([blob], filename, { type: blob.type });
      var dt = new DataTransfer();
      dt.items.add(file);
      fileInput.files = dt.files;
      fileInput.dispatchEvent(new Event('change', { bubbles: true }));
      MC.log('Flow: reference image uploaded');
      await MC.sleep(3000);

      // Wait for image processing (percentage indicator)
      for (var i = 0; i < 30; i++) {
        var progress = -1;
        var els = document.querySelectorAll('span, div, p');
        for (var el of els) {
          var txt = el.textContent.trim();
          if (txt.match(/^\d+%$/) && el.offsetParent) {
            progress = parseInt(txt);
            break;
          }
        }
        if (progress === -1) break;  // No progress indicator = done
        if (progress >= 100) break;
        MC.log('Flow: image processing ' + progress + '%');
        await MC.sleep(2000);
      }
    } catch (e) {
      MC.log('Flow: upload failed:', e.message);
    }
  },

  // ══════════════════════════════════════
  // CREATE (matches Selenium click_create)
  // ══════════════════════════════════════

  async _clickCreate() {
    var btns = document.querySelectorAll('button');
    for (var b of btns) {
      if (b.offsetParent && b.textContent.includes('Create') && b.textContent.includes('arrow_forward')) {
        b.click();
        MC.log('Flow: Create clicked');
        await MC.sleep(3000);
        return;
      }
    }
    // Fallback: any visible Create button
    for (var b of btns) {
      if (b.offsetParent && b.textContent.includes('Create')) {
        b.click();
        MC.log('Flow: Create clicked (fallback)');
        await MC.sleep(3000);
        return;
      }
    }
    throw new Error('Create button not found');
  },

  // ══════════════════════════════════════
  // WAIT FOR RESULTS (matches Selenium)
  // ══════════════════════════════════════

  _countImages() {
    return document.querySelectorAll('a[href*="/edit/"] img[src*="getMediaUrlRedirect"]').length;
  },

  async _waitForResults(jobId, countBefore, timeout) {
    timeout = timeout || 300000;
    var start = Date.now();
    while (Date.now() - start < timeout) {
      var current = this._countImages();
      if (current > countBefore) {
        var newCount = current - countBefore;
        await MC.sendStatus(jobId, 'generating', newCount + ' new images generated...');
        if (Date.now() - start > 15000) {
          MC.log('Flow: ' + newCount + ' results ready');
          // Wait a bit more for all images to finish
          await MC.sleep(5000);
          var final = this._countImages() - countBefore;
          MC.log('Flow: final count: ' + final);
          return;
        }
      }
      await MC.sleep(5000);
    }
    throw new Error('Flow results did not load');
  },

  // ══════════════════════════════════════
  // DOWNLOAD (matches Selenium — navigate to edit, 2K, back)
  // ══════════════════════════════════════

  async _downloadResults(jobId, count, countBefore) {
    // Get edit URLs for new images
    var allLinks = [];
    document.querySelectorAll('a[href*="/edit/"]').forEach(function(a) {
      if (a.querySelector('img[src*="getMediaUrlRedirect"]'))
        allLinks.push(a.getAttribute('href'));
    });

    var newLinks = countBefore > 0 ? allLinks.slice(0, allLinks.length - countBefore) : allLinks.slice(-4);
    newLinks = newLinks.slice(0, count);
    MC.log('Flow: downloading ' + newLinks.length + ' images');

    for (var i = 0; i < newLinks.length; i++) {
      await MC.sendStatus(jobId, 'downloading', 'Downloading image ' + (i+1) + '/' + newLinks.length + '...');
      await this._downloadSingleImage(newLinks[i], i, jobId);
    }
  },

  async _downloadSingleImage(editUrl, index, jobId) {
    // Navigate to edit page
    var fullUrl = editUrl.startsWith('/') ? 'https://labs.google' + editUrl : editUrl;
    location.href = fullUrl;
    await MC.sleep(4000);

    // Wait for Download button
    for (var i = 0; i < 15; i++) {
      var btns = document.querySelectorAll('button');
      var hasDl = false;
      for (var b of btns) { if (b.offsetParent && b.textContent.includes('Download')) { hasDl = true; break; } }
      if (hasDl) break;
      await MC.sleep(1000);
    }

    // Click Download
    var btns = document.querySelectorAll('button');
    var clicked = false;
    for (var b of btns) {
      if (b.offsetParent && (b.textContent.includes('downloadDownload') || b.textContent.includes('Download'))) {
        b.click();
        MC.log('Flow: Download button clicked');
        clicked = true;
        break;
      }
    }
    if (!clicked) {
      MC.log('Flow: Download button not found');
      return;
    }
    await MC.sleep(2000);

    // Try 2K Upscaled
    var allEls = document.querySelectorAll('button, div, li, a, span, [role="menuitem"], [role="option"]');
    var clicked2k = false;
    for (var el of allEls) {
      var txt = el.textContent.trim();
      if (el.offsetParent && txt.includes('2K') && (txt.includes('Upscaled') || txt.includes('upscaled'))) {
        el.click();
        MC.log('Flow: 2K Upscaled clicked');
        clicked2k = true;
        break;
      }
    }
    if (!clicked2k) {
      // Try Standard/1K/Original
      for (var el of allEls) {
        var txt = el.textContent.trim();
        if (el.offsetParent && (txt.includes('1K') || txt.includes('Standard') || txt.includes('Original'))) {
          el.click();
          MC.log('Flow: Standard download clicked');
          break;
        }
      }
    }

    // Wait for download toast
    for (var i = 0; i < 25; i++) {
      var bodyText = document.body.innerText;
      if (bodyText.includes('Something went wrong')) {
        MC.log('Flow: download error, dismissing');
        break;
      }
      if (bodyText.includes('Upscaling complete') || bodyText.includes('downloaded') || bodyText.includes('Download complete')) {
        MC.log('Flow: download complete');
        // Dismiss toast
        var els = document.querySelectorAll('*');
        for (var el of els) { if (el.offsetParent && el.textContent.trim() === 'Dismiss') { el.click(); break; } }
        await MC.sleep(1000);
        break;
      }
      await MC.sleep(1000);
    }

    // Go back to project
    var backBtn = document.querySelectorAll('button');
    for (var b of backBtn) {
      if (b.offsetParent && (b.textContent.includes('arrow_backBack') || b.textContent.includes('Back'))) {
        b.click();
        MC.log('Flow: navigated back');
        await MC.sleep(3000);
        return;
      }
    }
    // Fallback: browser back
    history.back();
    await MC.sleep(3000);
  }
};

// ── Command listener ──
chrome.runtime.onMessage.addListener(function(msg, sender, sendResponse) {
  if (msg.type === 'RUN_JOB' && (msg.job.job_type === 'flow' || msg.job.job_type === 'aplus')) {
    FlowBot.run(msg.job);
    sendResponse({ ok: true });
  }
  return true;
});

// ── Self-check: pick up pending job if dispatch failed ──
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
