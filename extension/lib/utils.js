// ═══════════════════════════════════════════
// Mr.Creative Extension — DOM Utilities
// Shared across all content scripts
// ═══════════════════════════════════════════

const MC = {
  SERVER: 'http://localhost:5000',

  // ── Wait for element ──
  waitFor(selector, timeout = 30000) {
    return new Promise((resolve, reject) => {
      const el = document.querySelector(selector);
      if (el && el.offsetHeight > 0) return resolve(el);

      const observer = new MutationObserver(() => {
        const el = document.querySelector(selector);
        if (el && el.offsetHeight > 0) {
          observer.disconnect();
          clearTimeout(timer);
          resolve(el);
        }
      });

      observer.observe(document.body, { childList: true, subtree: true });

      const timer = setTimeout(() => {
        observer.disconnect();
        reject(new Error(`Timeout waiting for: ${selector}`));
      }, timeout);
    });
  },

  // ── Wait for element with text ──
  waitForText(selector, text, timeout = 30000) {
    return new Promise((resolve, reject) => {
      const check = () => {
        const els = document.querySelectorAll(selector);
        for (const el of els) {
          if (el.textContent.includes(text) && el.offsetHeight > 0) return el;
        }
        return null;
      };

      const found = check();
      if (found) return resolve(found);

      const observer = new MutationObserver(() => {
        const found = check();
        if (found) { observer.disconnect(); clearTimeout(timer); resolve(found); }
      });

      observer.observe(document.body, { childList: true, subtree: true, characterData: true });

      const timer = setTimeout(() => {
        observer.disconnect();
        reject(new Error(`Timeout waiting for "${text}" in ${selector}`));
      }, timeout);
    });
  },

  // ── Wait for element to disappear ──
  waitForGone(selector, timeout = 120000) {
    return new Promise((resolve, reject) => {
      if (!document.querySelector(selector)) return resolve();

      const observer = new MutationObserver(() => {
        if (!document.querySelector(selector)) {
          observer.disconnect();
          clearTimeout(timer);
          resolve();
        }
      });

      observer.observe(document.body, { childList: true, subtree: true });

      const timer = setTimeout(() => {
        observer.disconnect();
        reject(new Error(`Timeout waiting for ${selector} to disappear`));
      }, timeout);
    });
  },

  // ── Wait N ms ──
  sleep(ms) {
    return new Promise(r => setTimeout(r, ms));
  },

  // ── Click via JS (safe for Angular/CDK) ──
  click(el) {
    if (typeof el === 'string') el = document.querySelector(el);
    if (!el) throw new Error(`Element not found: ${el}`);
    el.scrollIntoView({ block: 'center' });
    el.click();
  },

  // ── Find button by aria-label ──
  btnByAria(label) {
    return document.querySelector(`button[aria-label="${label}"]`);
  },

  // ── Find button by text content ──
  btnByText(text) {
    for (const btn of document.querySelectorAll('button')) {
      if (btn.textContent.includes(text) && btn.offsetHeight > 0) return btn;
    }
    return null;
  },

  // ── Find visible buttons matching class ──
  btnByClass(cls) {
    const el = document.querySelector(`button.${cls}`);
    return el && el.offsetHeight > 0 ? el : null;
  },

  // ── Upload file to input[type="file"] via DataTransfer ──
  async uploadFile(input, fileUrl, filename) {
    const response = await fetch(fileUrl);
    const blob = await response.blob();
    const file = new File([blob], filename, { type: blob.type });
    const dt = new DataTransfer();
    dt.items.add(file);
    input.files = dt.files;
    input.dispatchEvent(new Event('change', { bubbles: true }));
  },

  // ── Send status to Flask server ──
  async sendStatus(jobId, state, message, data = {}) {
    try {
      await fetch(`${MC.SERVER}/api/ext/status`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ job_id: jobId, state, message, ...data })
      });
    } catch (e) {
      console.warn('[MC] Status send failed:', e);
    }
  },

  // ── Get next command from Flask server ──
  async getCommand() {
    try {
      const res = await fetch(`${MC.SERVER}/api/ext/command`);
      if (!res.ok) return null;
      return await res.json();
    } catch (e) {
      return null;
    }
  },

  // ── Extract image src from card containers ──
  getCardImages(selector = 'div.creative-card-container img') {
    return Array.from(document.querySelectorAll(selector))
      .map(img => img.src)
      .filter(Boolean);
  },

  // ── Log with prefix ──
  log(...args) {
    console.log('[Mr.Creative]', ...args);
  }
};
