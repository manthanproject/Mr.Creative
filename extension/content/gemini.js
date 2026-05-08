// ═══════════════════════════════════════════
// GEMINI BOT — Automates prompt generation via gemini.google.com
// DOM selectors verified May 8 2026
// ═══════════════════════════════════════════

const GSEL = {
  inputField:     'div.ql-editor.textarea',
  sendBtn:        'button[aria-label="Send message"]',
  uploadMenuBtn:  'button[aria-label="Open upload file menu"]',
  uploadFilesBtn: 'button[aria-label*="Upload files"]',
  codeBlockPre:   'code-block pre',
  copyCodeBtn:    'button[aria-label="Copy code"]',
  responseText:   '.model-response-text',
  loadingSpinner: '.loading-content-spinner-container',  // actual loading spinner, not avatar icon
};

const PROMPT_TEMPLATES = {
  campaign: `You are an expert e-commerce marketing strategist. Analyze this product image and create a detailed Pomelli Campaign prompt.

The prompt should include:
- A compelling campaign theme/concept (2-3 sentences)
- Target audience description
- Visual style direction (colors, mood, composition)
- Key selling points to highlight
- Call-to-action suggestion

Format your response as a SINGLE code block with the complete prompt text that can be directly pasted into Pomelli Campaign's prompt field. No explanations outside the code block.`,

  photoshoot: `You are an expert e-commerce product photographer and art director. Analyze this product image and create a detailed Pomelli Photoshoot prompt.

The prompt should describe:
- Product positioning and angle suggestions
- Background/setting recommendations (studio, lifestyle, contextual)
- Lighting direction
- Props and styling elements
- Color palette that complements the product

Format your response as a SINGLE code block with the complete prompt text. No explanations outside the code block.`,

  flow: `You are an expert Amazon Listing Optimizer, Copywriter, and E-commerce Art Director. Analyze this product image and generate a complete Amazon A+ Content Layout prompt for FLOW AI.

The prompt must include:
- Product Description based on what you see in the image
- Target Audience
- Tone
- 5 A+ Content Modules (Standard Company Logo/Hero Banner, Standard Single Image & Sidebar, Standard Three Image & Text, Standard Single Image & Light Text, Standard Four Image & Text)
- For each module: Image Prompt + Copy instructions

Format your response as a SINGLE code block with the complete prompt. No explanations outside the code block.`,

  social: `You are a social media marketing expert. Analyze this product image and create engaging social media post prompts.

Create 3 different post variations:
1. Instagram carousel concept (5 slides)
2. Story/Reel concept
3. Facebook/LinkedIn post

Each should include: visual description, caption text, hashtags, call-to-action.

Format your response as a SINGLE code block. No explanations outside the code block.`
};

MC.log('Gemini content script loaded on:', location.href);

// Register this profile as gemini-capable
try {
  chrome.runtime.sendMessage({ type: 'ADD_CAPABILITY', capability: 'gemini' });
} catch (e) {}

const GeminiBot = {
  async run(job) {
    const { prompt_type, image_url, image_filename, custom_instructions, job_id } = job;
    try {
      MC.log('Gemini: starting prompt generation for', prompt_type);
      await MC.sendStatus(job_id, 'navigating', 'Opening Gemini...');
      await MC.waitFor(GSEL.inputField, 30000);
      await MC.sleep(2000);

      if (image_url) {
        await MC.sendStatus(job_id, 'entering_prompt', 'Uploading product image...');
        await this._uploadImage(image_url, image_filename);
      }

      await MC.sendStatus(job_id, 'entering_prompt', 'Typing prompt...');
      const template = PROMPT_TEMPLATES[prompt_type] || PROMPT_TEMPLATES.flow;
      let fullPrompt = template;
      if (custom_instructions) fullPrompt += '\n\nAdditional instructions: ' + custom_instructions;

      const inputEl = document.querySelector(GSEL.inputField);
      if (!inputEl) throw new Error('Input field not found');
      inputEl.focus();
      await MC.sleep(500);

      // Gemini uses a rich editor — execCommand doesn't work reliably
      // Use paragraph insertion instead
      inputEl.innerHTML = '<p>' + fullPrompt.replace(/\n/g, '</p><p>') + '</p>';
      inputEl.dispatchEvent(new Event('input', { bubbles: true }));
      inputEl.dispatchEvent(new Event('change', { bubbles: true }));
      await MC.sleep(1000);

      // Verify text was entered
      if (inputEl.textContent.trim().length < 20) {
        MC.log('Gemini: paragraph method failed, trying clipboard paste');
        inputEl.focus();
        inputEl.innerHTML = '';
        // Fallback: simulate paste
        const clipData = new DataTransfer();
        clipData.setData('text/plain', fullPrompt);
        const pasteEvent = new ClipboardEvent('paste', { bubbles: true, cancelable: true, clipboardData: clipData });
        inputEl.dispatchEvent(pasteEvent);
        await MC.sleep(1000);
      }
      MC.log('Gemini: input field text length:', inputEl.textContent.trim().length);

      await MC.sendStatus(job_id, 'generating', 'Sending to Gemini...');
      const sendBtn = document.querySelector(GSEL.sendBtn);
      if (sendBtn) MC.click(sendBtn);
      else throw new Error('Send button not found');

      await MC.sendStatus(job_id, 'generating', 'Waiting for Gemini response...');
      await this._waitForResponse();

      await MC.sendStatus(job_id, 'downloading', 'Extracting prompt...');
      const result = this._extractResponse();

      // Send result via background script to avoid CORS
      chrome.runtime.sendMessage({
        type: 'GEMINI_RESULT',
        job_id: job_id,
        prompt_type: prompt_type,
        result: result
      });
      await MC.sendStatus(job_id, 'complete', 'Prompt generated successfully');
    } catch (err) {
      MC.log('Gemini error:', err.message);
      await MC.sendStatus(job_id, 'error', 'Failed: ' + err.message);
    }
  },

  async _uploadImage(imageUrl, filename) {
    const plusBtn = document.querySelector(GSEL.uploadMenuBtn);
    if (!plusBtn) return;
    MC.click(plusBtn);
    await MC.sleep(1000);
    const uploadBtn = document.querySelector(GSEL.uploadFilesBtn);
    if (!uploadBtn) return;
    MC.click(uploadBtn);
    await MC.sleep(1000);
    const fileInput = document.querySelector('input[type="file"]');
    if (fileInput) {
      try {
        const resp = await fetch(imageUrl);
        const blob = await resp.blob();
        const file = new File([blob], filename || 'product.jpg', { type: blob.type });
        const dt = new DataTransfer();
        dt.items.add(file);
        fileInput.files = dt.files;
        fileInput.dispatchEvent(new Event('change', { bubbles: true }));
        await MC.sleep(5000);
      } catch (e) { MC.log('Gemini: upload failed:', e.message); }
    }
  },

  async _waitForResponse(timeout = 120000) {
    await MC.sleep(3000);
    const start = Date.now();
    while (Date.now() - start < timeout) {
      const spinners = [...document.querySelectorAll(GSEL.loadingSpinner)].filter(s => s.offsetHeight > 0);
      const sendBtn = document.querySelector(GSEL.sendBtn);
      const sendVisible = sendBtn && sendBtn.offsetHeight > 0;
      const responses = document.querySelectorAll(GSEL.responseText);
      const lastResponse = responses[responses.length - 1];
      const hasContent = lastResponse && lastResponse.textContent.trim().length > 50;
      if (spinners.length === 0 && hasContent && sendVisible) {
        await MC.sleep(2000);
        return;
      }
      await MC.sleep(3000);
    }
  },

  _extractResponse() {
    const codeBlock = document.querySelector(GSEL.codeBlockPre);
    if (codeBlock && codeBlock.textContent.trim().length > 50) return codeBlock.textContent.trim();
    const responses = document.querySelectorAll(GSEL.responseText);
    if (responses.length > 0) return responses[responses.length - 1].textContent.trim();
    throw new Error('No response text found');
  }
};

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg.type === 'RUN_JOB' && msg.job.job_type === 'gemini') {
    GeminiBot.run(msg.job);
    sendResponse({ ok: true });
  }
  return true;
});

setTimeout(async () => {
  try {
    const res = await fetch(MC.SERVER + '/api/ext/pending-for-tab');
    if (res.ok && res.status !== 204) {
      const job = await res.json();
      if (job && job.job_id && job.job_type === 'gemini') {
        GeminiBot.run(job);
        await fetch(MC.SERVER + '/api/ext/ack', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ job_id: job.job_id, profile_id: 'gemini-content' })
        });
      }
    }
  } catch (e) {}
}, 3000);
