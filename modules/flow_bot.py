"""
Mr.Creative — Flow Bot (Google Flow Selenium Automation)
Automates image generation on labs.google/fx/tools/flow
Uses existing Chrome session (debug port 9222).

DOM Selectors (April 2026):
  Dashboard: div/card with text 'New project'
  Prompt: DIV[contenteditable] (widest, ~564px)
  Create: button with text containing 'Create' + 'arrow_forward'
  Model config: button containing 'Nano Banana 2'
  Dropdown: buttons with class 'flow_tab_slider_trigger'
    Mode: imageImage / videocamVideo
    AR: crop_16_916:9, crop_square1:1, crop_9_169:16, crop_landscape4:3, crop_portrait3:4
    Count: x1, x2, x3, x4
  Image cards: A.sc-3ab8616e-0 with href containing /edit/
  Edit page: Download btn text 'downloadDownload', 2K btn text '2KUpscaled'
  Back: button text 'arrow_backBack'
"""

import os
import time
import datetime

from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from selenium.common.exceptions import TimeoutException

FLOW_URL = 'https://labs.google/fx/tools/flow'
DOWNLOAD_WAIT = 25

ASPECT_RATIO_MAP = {
    'landscape': 'crop_16_916:9',
    'square':    'crop_square1:1',
    'story':     'crop_9_169:16',
    'feed':      'crop_portrait3:4',
    'wide':      'crop_landscape4:3',
}

ASPECT_RATIOS = {
    'story':     {'label': 'Story (9:16)'},
    'square':    {'label': 'Square (1:1)'},
    'landscape': {'label': 'Landscape (16:9)'},
    'feed':      {'label': 'Feed (3:4)'},
    'wide':      {'label': 'Wide (4:3)'},
}


class FlowBot:

    def __init__(self, driver, download_dir=None, expected_email=None):
        self.driver = driver
        self.download_dir = download_dir or os.path.expanduser('~/Downloads')
        self.expected_email = expected_email
        os.makedirs(self.download_dir, exist_ok=True)
        self.status = 'idle'
        self.status_message = ''
        self.errors = []
        # Set download path via CDP (Browser-level, not Page-level)
        try:
            abs_path = os.path.abspath(self.download_dir)
            self.driver.execute_cdp_cmd('Browser.setDownloadBehavior', {
                'behavior': 'allow', 'downloadPath': abs_path})
            print(f"[FlowBot] CDP download path set to: {abs_path}")
        except Exception as e:
            print(f"[FlowBot] ⚠️ CDP setDownloadBehavior failed: {e}")

    def _update_status(self, status, message=''):
        self.status = status
        self.status_message = message
        print(f"[FlowBot] {status}: {message}")

    def _is_on_flow(self):
        try:
            url = self.driver.current_url
            return 'labs.google' in url and ('flow' in url or 'fx' in url)
        except Exception:
            return False

    def _js_click(self, script):
        """Run JS that returns an element, then click it."""
        el = self.driver.execute_script(script)
        if el:
            try:
                ActionChains(self.driver).move_to_element(el).pause(0.3).click().perform()
            except Exception:
                self.driver.execute_script("arguments[0].click();", el)
            return True
        return False

    # ══════════════════════════════════════
    # NAVIGATION
    # ══════════════════════════════════════

    def _ensure_flow_account(self):
        """Sign out and re-login if wrong Google account is active on Flow."""
        try:
            # Read current account email from the page
            current_email = self.driver.execute_script("""
                var btns = document.querySelectorAll('button, a');
                for (var b of btns) {
                    if (!b.offsetParent) continue;
                    var r = b.getBoundingClientRect();
                    if (r.x > window.innerWidth - 80 && r.y < 60 && r.width < 50) {
                        b.click(); return 'opened';
                    }
                }
                return 'no_avatar';
            """)
            time.sleep(2)

            # Grab email from opened menu
            logged_email = self.driver.execute_script("""
                var els = document.querySelectorAll('*');
                for (var el of els) {
                    if (!el.offsetParent) continue;
                    var t = (el.textContent || '').trim();
                    if (t.includes('@') && t.includes('.com') && t.indexOf('@') === t.lastIndexOf('@') && t.length < 60 && !t.includes(' ')) {
                        return t;
                    }
                }
                return '';
            """)
            self._update_status('navigating', f'Current account: {logged_email}')

            # Close menu
            self.driver.execute_script("document.body.click();")
            time.sleep(1)

            if logged_email and self.expected_email.lower() == logged_email.lower():
                self._update_status('navigating', 'Correct account already active!')
                return

            # Wrong account — sign out
            self._update_status('navigating', f'Switching to {self.expected_email}...')

            # Re-open avatar menu and click Sign out
            self.driver.execute_script("""
                var btns = document.querySelectorAll('button, a');
                for (var b of btns) {
                    if (!b.offsetParent) continue;
                    var r = b.getBoundingClientRect();
                    if (r.x > window.innerWidth - 80 && r.y < 60 && r.width < 50) {
                        b.click(); return;
                    }
                }
            """)
            time.sleep(2)
            self.driver.execute_script("""
                var btns = document.querySelectorAll('button, a');
                for (var b of btns) {
                    if (!b.offsetParent) continue;
                    if (b.textContent.trim() === 'Sign out') { b.click(); return; }
                }
            """)
            time.sleep(3)

            # Navigate back to Flow — triggers Google account picker
            self.driver.get(FLOW_URL)
            time.sleep(5)

            # Pick correct account from chooser
            if 'accounts.google.com' in self.driver.current_url:
                self._update_status('navigating', f'Selecting {self.expected_email}...')
                self.driver.execute_script("""
                    var target = arguments[0].toLowerCase();
                    var accs = document.querySelectorAll('div[data-email], li[data-identifier]');
                    for (var a of accs) {
                        var email = (a.getAttribute('data-email') || a.getAttribute('data-identifier') || '').toLowerCase();
                        if (email === target) { a.click(); return; }
                    }
                """, self.expected_email.lower())
                for _ in range(20):
                    time.sleep(2)
                    if self._is_on_flow():
                        break
                time.sleep(3)
                self._update_status('navigating', f'Logged in as {self.expected_email}!')
            else:
                self._update_status('navigating', 'No account picker — proceeding...')

        except Exception as e:
            self._update_status('navigating', f'Account switch error: {str(e)[:60]}')
            try:
                self.driver.execute_script("document.body.click();")
            except Exception:
                pass

    def navigate_to_flow(self):
        """Go to Flow → handle landing → dashboard → New Project → prompt bar."""
        self._update_status('navigating', 'Opening Flow...')
        self.driver.get(FLOW_URL)
        time.sleep(5)

        # Step 0: Log expected account
        if self.expected_email:
            self._update_status('navigating', f'Using account: {self.expected_email}')

        # Step 1: Landing page → click "Create with Flow"
        for attempt in range(3):
            is_landing = self.driver.execute_script(
                "return document.body.innerText.includes('Create with Flow') && document.body.innerText.includes('Where the next wave');")
            if is_landing:
                self._update_status('navigating', 'Clicking Create with Flow...')
                self.driver.execute_script("""
                    var els = document.querySelectorAll('a, button');
                    for (var el of els) { if (el.offsetParent && el.textContent.includes('Create with Flow')) { el.click(); break; } }
                """)
                time.sleep(5)
            else:
                break

        # Step 1.5: Consent dialog — "Experience and shape AI tools"
        for _ in range(5):
            has_consent = self.driver.execute_script("""
                return document.body.innerText.includes('Experience and shape AI tools');
            """)
            if has_consent:
                self._update_status('navigating', 'Dismissing consent dialog...')
                self.driver.execute_script("""
                    var btns = document.querySelectorAll('button');
                    for (var b of btns) {
                        if (b.offsetParent && b.textContent.trim() === 'Next') { b.click(); return; }
                    }
                """)
                time.sleep(3)
            else:
                break

        # Step 2: Google login redirect
        if 'accounts.google.com' in self.driver.current_url:
            self._update_status('navigating', 'Handling Google login...')
            # Click the account (should auto-pick from existing cookies)
            self.driver.execute_script("""
                var accs = document.querySelectorAll('div[data-email], li[data-identifier], *[data-authuser]');
                if (accs.length > 0) accs[0].click();
            """)
            for _ in range(20):
                time.sleep(2)
                if self._is_on_flow():
                    break

        # Step 2.5: If stuck on old project page, go back to dashboard
        if '/project/' in self.driver.current_url:
            self._update_status('navigating', 'On old project — going back to dashboard...')
            # Try clicking back arrow
            self.driver.execute_script("""
                var back = document.querySelector('button[aria-label="Back"], a[aria-label="Back"]');
                if (back) { back.click(); return; }
                var arrows = document.querySelectorAll('button, a');
                for (var el of arrows) {
                    if (!el.offsetParent) continue;
                    var r = el.getBoundingClientRect();
                    if (r.x < 80 && r.y < 120 && r.width < 60 && el.textContent.includes('arrow_back')) {
                        el.click(); return;
                    }
                }
            """)
            time.sleep(3)
            # If still on project page, navigate directly to dashboard
            if '/project/' in self.driver.current_url:
                self.driver.get(FLOW_URL)
                time.sleep(5)

        # Step 3: Close announcement banner if present
        for _ in range(3):
            banner_closed = self.driver.execute_script("""
                // Try multiple close button selectors
                var selectors = [
                    'button[aria-label="Close"]',
                    'button[aria-label="close"]',
                    'button[aria-label="Dismiss"]',
                ];
                for (var sel of selectors) {
                    var btn = document.querySelector(sel);
                    if (btn && btn.offsetParent) { btn.click(); return 'closed_aria'; }
                }
                // Try X button in top-right area of banner
                var btns = document.querySelectorAll('button');
                for (var b of btns) {
                    if (!b.offsetParent) continue;
                    var r = b.getBoundingClientRect();
                    if (r.x > window.innerWidth - 100 && r.y < 200 && r.width < 60 && r.height < 60) {
                        var txt = b.textContent.trim();
                        if (txt === '✕' || txt === 'close' || txt === '×' || txt.length <= 2) {
                            b.click(); return 'closed_x';
                        }
                    }
                }
                return 'no_banner';
            """)
            if banner_closed and banner_closed.startswith('closed'):
                self._update_status('navigating', f'Banner dismissed ({banner_closed})')
                time.sleep(2)
            else:
                break

        # Step 4: Dashboard → click "+ New project"
        for attempt in range(15):
            if '/project/' in self.driver.current_url:
                self._update_status('navigating', 'Project page loaded!')
                break
            self._update_status('navigating', f'Clicking New Project (attempt {attempt+1})...')
            clicked = self.driver.execute_script("""
                // Try 1: Find by text
                var all = document.querySelectorAll('*');
                for (var el of all) {
                    if (!el.offsetParent) continue;
                    var r = el.getBoundingClientRect();
                    try {
                        if (el.innerText && el.innerText.includes('New project') && r.width < 400 && r.height > 20) {
                            el.scrollIntoView({block: 'center'});
                            el.click();
                            return 'clicked_text';
                        }
                    } catch(e) {}
                }

                // Try 2: Find the + card specifically
                var cards = document.querySelectorAll('div, button, a');
                for (var c of cards) {
                    if (!c.offsetParent) continue;
                    var t = c.textContent.trim();
                    if (t.includes('New project') && t.includes('+')) {
                        c.scrollIntoView({block: 'center'});
                        c.click();
                        return 'clicked_plus_card';
                    }
                }

                // Try 3: Click the bottom-center card by position
                var vpW = window.innerWidth;
                var vpH = window.innerHeight;
                var el = document.elementFromPoint(vpW / 2, vpH - 150);
                if (el) {
                    el.click();
                    return 'clicked_position_' + el.tagName;
                }

                return 'not_found';
            """)
            print(f"[FlowBot] New Project click result: {clicked}")
            if clicked and clicked.startswith('clicked'):
                time.sleep(5)
                if '/project/' in self.driver.current_url:
                    break
            else:
                time.sleep(2)

        # Step 5: Wait for prompt bar
        for _ in range(20):
            has_prompt = self.driver.execute_script("""
                var divs = document.querySelectorAll('div[contenteditable="true"]');
                for (var d of divs) { if (d.getBoundingClientRect().width > 200) return true; }
                return false;
            """)
            if has_prompt and '/project/' in self.driver.current_url:
                self._update_status('navigating', 'Project ready!')
                return True
            time.sleep(2)

        self._update_status('error', 'Project did not load')
        return False

    # ══════════════════════════════════════
    # SETTINGS (Model dropdown)
    # ══════════════════════════════════════

    def set_image_settings(self, aspect_ratio='landscape', count=4):
        self._update_status('settings', f'Setting: {aspect_ratio}, x{count}')

        # Open dropdown
        opened = self._js_click("""
            var btns = document.querySelectorAll('button');
            for (var b of btns) { if (b.offsetParent && b.textContent.includes('Nano Banana')) return b; }
            return null;
        """)
        if not opened:
            self._update_status('settings', 'Model dropdown not found')
            return
        time.sleep(1)

        # Select Image mode
        self._click_flow_tab('imageImage')
        time.sleep(0.3)

        # Select aspect ratio
        ar_text = ASPECT_RATIO_MAP.get(aspect_ratio, 'crop_square1:1')
        self._click_flow_tab(ar_text)
        time.sleep(0.3)

        # Select count
        self._click_flow_tab(f'x{count}')
        time.sleep(0.3)

        # Close dropdown
        try:
            ActionChains(self.driver).move_by_offset(-300, -300).click().perform()
        except Exception:
            pass
        time.sleep(0.5)
        self._update_status('settings', 'Settings applied!')

    def _click_flow_tab(self, target_text):
        result = self.driver.execute_script("""
            var target = arguments[0];
            var btns = document.querySelectorAll('button.flow_tab_slider_trigger');
            for (var b of btns) {
                if (b.offsetParent && b.textContent.trim() === target) {
                    b.scrollIntoView({block: 'center'});
                    return b;
                }
            }
            return null;
        """, target_text)
        if result:
            try:
                ActionChains(self.driver).move_to_element(result).pause(0.2).click().perform()
                print(f"[FlowBot] Tab click: clicked_{target_text} (ActionChains)")
            except Exception:
                self.driver.execute_script("arguments[0].click();", result)
                print(f"[FlowBot] Tab click: clicked_{target_text} (JS fallback)")
        else:
            print(f"[FlowBot] Tab click: not_found_{target_text}")

    # ══════════════════════════════════════
    # PROMPT + CREATE
    # ══════════════════════════════════════

    def type_prompt(self, prompt_text):
        self._update_status('entering_prompt', f'Typing: {prompt_text[:50]}...')
        prompt_el = self.driver.execute_script("""
            var divs = document.querySelectorAll('div[contenteditable="true"]');
            var best = null, bestW = 0;
            for (var d of divs) { var w = d.getBoundingClientRect().width; if (w > bestW) { best = d; bestW = w; } }
            return best;
        """)
        if not prompt_el:
            raise RuntimeError('Prompt input not found')

        ActionChains(self.driver).move_to_element(prompt_el).pause(0.3).click().perform()
        time.sleep(0.3)
        prompt_el.send_keys(Keys.CONTROL, 'a')
        time.sleep(0.1)
        prompt_el.send_keys(Keys.DELETE)
        time.sleep(0.2)

        # Paste via clipboard — fastest method that triggers contenteditable events
        import pyperclip
        pyperclip.copy(prompt_text)
        # Verify clipboard was set correctly
        try:
            clip = pyperclip.paste()
            if clip != prompt_text:
                print(f"[FlowBot] ⚠️ Clipboard mismatch! Expected prompt, got: {clip[:50]}...")
        except Exception:
            pass
        prompt_el.send_keys(Keys.CONTROL, Keys.SHIFT, 'v')
        time.sleep(0.5)
        self._update_status('entering_prompt', 'Prompt entered!')

    def click_create(self):
        self._update_status('generating', 'Clicking Create...')
        clicked = self._js_click("""
            var btns = document.querySelectorAll('button');
            for (var b of btns) {
                if (b.offsetParent && b.textContent.includes('Create') && b.textContent.includes('arrow_forward'))
                    return b;
            }
            return null;
        """)
        if clicked:
            self._update_status('generating', 'Create clicked!')
            time.sleep(3)
        else:
            self._update_status('error', 'Create button not found')
        return clicked

    def count_images(self):
        return self.driver.execute_script("""
            return document.querySelectorAll('a[href*="/edit/"] img[src*="getMediaUrlRedirect"]').length;
        """)

    def wait_for_images(self, count_before, expected=4, timeout=300):
        self._update_status('generating', 'Waiting for images...')
        start = time.time()
        last_count = 0
        last_change_time = time.time()
        while time.time() - start < timeout:
            time.sleep(4)
            current = self.count_images()
            new_count = current - count_before
            elapsed = int(time.time() - start)
            self._update_status('generating', f'{new_count}/{expected} images generated ({elapsed}s)')
            if new_count >= expected:
                time.sleep(3)
                return True
            if new_count > last_count:
                last_count = new_count
                last_change_time = time.time()
            elif new_count > 0 and time.time() - last_change_time > 45:
                self._update_status('generating', f'No new images for 45s — proceeding with {new_count} images')
                time.sleep(2)
                return True
            # Detect failed images early
            if new_count > 0:
                has_failed = self.driver.execute_script("""
                    return document.body.innerText.includes('Failed') ||
                           document.body.innerText.includes('unusual activity') ||
                           document.body.innerText.includes('Something went wrong');
                """)
                if has_failed and time.time() - last_change_time > 15:
                    self._update_status('generating', f'Failed image detected — proceeding with {new_count} images')
                    time.sleep(2)
                    return True
        return True

    # ══════════════════════════════════════
    # DOWNLOAD (click each image → Download → 2K → back)
    # ══════════════════════════════════════

    def get_new_image_edit_urls(self, count_before):
        """Get edit page URLs for newly generated images."""
        all_urls = self.driver.execute_script("""
            var links = [];
            document.querySelectorAll('a[href*="/edit/"]').forEach(function(a) {
                if (a.querySelector('img[src*="getMediaUrlRedirect"]'))
                    links.push(a.getAttribute('href'));
            });
            return links;
        """)
        # Newest images are at the top/start
        new_urls = all_urls[:len(all_urls) - count_before] if count_before > 0 else all_urls[-4:]
        return new_urls[:4]

    def download_single_image_2k(self, edit_url):
        """Navigate to edit page → Download → 2K → wait → back."""
        full_url = 'https://labs.google' + edit_url if edit_url.startswith('/') else edit_url
        self.driver.get(full_url)
        time.sleep(4)

        # Wait for Download button
        for _ in range(15):
            has_dl = self.driver.execute_script("""
                var btns = document.querySelectorAll('button');
                for (var b of btns) { if (b.offsetParent && b.textContent.includes('Download')) return true; }
                return false;
            """)
            if has_dl:
                break
            time.sleep(1)

        # Click Download button
        clicked_dl = self._js_click("""
            var btns = document.querySelectorAll('button');
            for (var b of btns) { if (b.offsetParent && b.textContent.includes('downloadDownload')) return b; }
            for (var b of btns) { if (b.offsetParent && b.textContent.includes('Download')) return b; }
            return null;
        """)
        if not clicked_dl:
            all_btns = self.driver.execute_script("""
                return Array.from(document.querySelectorAll('button'))
                    .filter(b => b.offsetParent)
                    .map(b => b.textContent.trim().substring(0, 60));
            """)
            print(f"[FlowBot] ⚠️ Download button NOT FOUND! Visible buttons: {all_btns}")
            self._update_status('downloading', 'Download button not found!')
            return
        print(f"[FlowBot] ✓ Download button clicked")
        time.sleep(3)  # Wait for dropdown menu to fully render

        # Retry loop — dropdown may take time to appear
        clicked_2k = None
        for attempt in range(5):
            clicked_2k = self._js_click("""
            var btns = document.querySelectorAll('button');
            for (var b of btns) { if (b.offsetParent && b.textContent.includes('2K') && b.textContent.includes('Upscaled')) return b; }
            return null;
        """)
            if clicked_2k:
                print(f"[FlowBot] 2K option found on attempt {attempt + 1}")
                break
            time.sleep(1)
        if clicked_2k:
            self._update_status('downloading', 'Downloading 2K image...')
        else:
            # 2K not available — must click Standard explicitly (first click only opened dropdown)
            clicked_std = self._js_click("""
                var btns = document.querySelectorAll('button');
                for (var b of btns) {
                    if (b.offsetParent && b.textContent.includes('Standard')) return b;
                }
                for (var b of btns) {
                    if (b.offsetParent && b.textContent.includes('Original')) return b;
                }
                return null;
            """)
            if clicked_std:
                self._update_status('downloading', 'Downloading standard image...')
            else:
                all_btns = self.driver.execute_script("""
                    return Array.from(document.querySelectorAll('button'))
                        .filter(b => b.offsetParent)
                        .map(b => b.textContent.trim().substring(0, 60));
                """)
                print(f"[FlowBot] ⚠️ No download option found after dropdown! Buttons: {all_btns}")
                self._update_status('downloading', 'No download option found!')
                return

        # Wait for download toast or timeout
        for _ in range(DOWNLOAD_WAIT):
            done = self.driver.execute_script("""
                var text = document.body.innerText;
                if (text.includes('Something went wrong')) return 'error';
                if (text.includes('Upscaling complete') || text.includes('image has been downloaded') || text.includes('Download complete')) return 'done';
                return 'waiting';
            """)
            if done == 'done':
                self._update_status('downloading', 'Download complete!')
                self.driver.execute_script("""
                    var els = document.querySelectorAll('*');
                    for (var el of els) { if (el.offsetParent && el.textContent.trim() === 'Dismiss') { el.click(); break; } }
                """)
                time.sleep(1)
                break
            elif done == 'error':
                self._update_status('downloading', '2K failed — downloading standard...')
                # Dismiss error toast
                self.driver.execute_script("""
                    var els = document.querySelectorAll('*');
                    for (var el of els) { if (el.offsetParent && el.textContent.trim() === 'Dismiss') { el.click(); break; } }
                """)
                time.sleep(1)
                # Click Download again for standard quality
                self._js_click("""
                    var btns = document.querySelectorAll('button');
                    for (var b of btns) { if (b.offsetParent && b.textContent.includes('downloadDownload')) return b; }
                    for (var b of btns) { if (b.offsetParent && b.textContent.includes('Download')) return b; }
                    return null;
                """)
                time.sleep(2)
                # Click standard download (not 2K)
                self._js_click("""
                    var btns = document.querySelectorAll('button');
                    for (var b of btns) {
                        if (b.offsetParent && b.textContent.includes('Standard') && !b.textContent.includes('2K')) return b;
                    }
                    // Or just click the first download option that's not 2K
                    for (var b of btns) {
                        if (b.offsetParent && b.textContent.includes('Download') && !b.textContent.includes('2K')) return b;
                    }
                    return null;
                """)
                time.sleep(5)
                break
            time.sleep(1)

    def download_all_new_images(self, edit_urls, project_url):
        """Download each new image in 2K, collecting files after each download."""
        all_files = []
        self._update_status('downloading', f'Downloading {len(edit_urls)} images in 2K...')

        for i, url in enumerate(edit_urls):
            # Snapshot BEFORE each individual download
            before = {}
            for f in os.listdir(self.download_dir):
                fp = os.path.join(self.download_dir, f)
                if os.path.isfile(fp):
                    before[f] = os.path.getmtime(fp)

            self._update_status('downloading', f'Downloading image {i+1}/{len(edit_urls)} in 2K...')
            self.download_single_image_2k(url)

            # Wait for any pending .crdownload files
            for _ in range(15):
                pending = [f for f in os.listdir(self.download_dir) if f.endswith('.crdownload')]
                if not pending:
                    break
                time.sleep(2)
            time.sleep(2)

            # Collect new OR modified files from this download
            for f in os.listdir(self.download_dir):
                if not f.lower().endswith(('.png', '.jpg', '.jpeg', '.webp')):
                    continue
                if f.endswith(('.crdownload', '.tmp')):
                    continue
                fp = os.path.join(self.download_dir, f)
                if not os.path.isfile(fp):
                    continue
                mtime = os.path.getmtime(fp)
                # New file OR existing file that was modified (overwritten)
                if f not in before or mtime > before[f] + 1:
                    # Rename to unique name so next iteration doesn't confuse it
                    import uuid
                    ext = os.path.splitext(f)[1]
                    unique_name = f"flow_dl_{i+1}_{uuid.uuid4().hex[:8]}{ext}"
                    unique_path = os.path.join(self.download_dir, unique_name)
                    os.rename(fp, unique_path)
                    all_files.append(unique_path)
                    print(f"[FlowBot] Captured file {i+1}: {f} → {unique_name}")
                    break  # One file per download

        # Go back to project
        self.driver.get(project_url)
        time.sleep(3)

        print(f"[FlowBot] Total new files: {len(all_files)}")
        return all_files

    def upload_reference_image(self, image_path):
        """Upload a reference image via Flow's + button → Upload image → file explorer."""
        if not image_path or not os.path.exists(image_path):
            self._update_status('entering_prompt', 'No reference image to upload')
            return False

        abs_path = os.path.abspath(image_path)
        self._update_status('entering_prompt', f'Uploading reference: {os.path.basename(abs_path)}')

        try:
            # Step 1: Click the "+" button (text contains "add_2", bottom area, small 32x32)
            clicked = self.driver.execute_script("""
                var btns = document.querySelectorAll('button');
                for (var b of btns) {
                    if (!b.offsetParent) continue;
                    var r = b.getBoundingClientRect();
                    var txt = b.textContent.trim();
                    if (txt.includes('add_2') && r.y > window.innerHeight - 200 && r.width < 50) {
                        b.click();
                        return 'clicked';
                    }
                }
                return 'not_found';
            """)
            self._update_status('entering_prompt', f'Plus button: {clicked}')
            time.sleep(2)

            # Step 2: Click "Upload image" option (div with class containing sc-f4d15a74)
            clicked = self.driver.execute_script("""
                var els = document.querySelectorAll('div[class*="sc-f4d15a74"]');
                for (var el of els) {
                    if (!el.offsetParent) continue;
                    var txt = el.textContent.trim();
                    if (txt === 'Upload image') {
                        el.click();
                        return 'clicked';
                    }
                }
                // Fallback: any visible element with exact text
                var all = document.querySelectorAll('div, button, span');
                for (var el of all) {
                    if (!el.offsetParent) continue;
                    if (el.textContent.trim() === 'Upload image' && el.children.length === 0) {
                        el.click();
                        return 'clicked_fallback';
                    }
                }
                return 'not_found';
            """)
            self._update_status('entering_prompt', f'Upload image: {clicked}')
            time.sleep(2)

            # Step 3: Handle "Notice" consent dialog — click "I agree"
            for _ in range(3):
                agreed = self.driver.execute_script("""
                    var btns = document.querySelectorAll('button');
                    for (var b of btns) {
                        if (!b.offsetParent) continue;
                        var txt = b.textContent.trim();
                        if (txt === 'I agree' || txt === 'Accept' || txt === 'OK') {
                            b.click();
                            return 'agreed';
                        }
                    }
                    return 'no_dialog';
                """)
                if agreed == 'agreed':
                    self._update_status('entering_prompt', 'Accepted notice dialog')
                    time.sleep(2)
                    break
                time.sleep(1)

            # Step 4: File explorer opens — paste path via pyautogui
            import pyautogui
            import subprocess
            time.sleep(3)
            subprocess.run(['clip'], input=abs_path.encode(), check=True)
            pyautogui.hotkey('ctrl', 'v')
            time.sleep(0.5)
            pyautogui.press('enter')
            self._update_status('entering_prompt', f'Uploading: {os.path.basename(abs_path)}')
            time.sleep(10)

            # Step 5: Close the image picker panel if still open (click outside or press Escape)
            self.driver.execute_script("document.body.click();")
            time.sleep(1)

            # Verify image appeared in prompt area
            has_image = self.driver.execute_script("""
                var imgs = document.querySelectorAll('img[src*="blob:"], img[src*="getMediaUrlRedirect"], img[src*="googleusercontent"]');
                for (var img of imgs) {
                    var r = img.getBoundingClientRect();
                    if (r.width > 30 && r.height > 30 && r.y > window.innerHeight - 300) {
                        return true;
                    }
                }
                return false;
            """)
            if has_image:
                self._update_status('entering_prompt', 'Reference image uploaded!')
            else:
                self._update_status('entering_prompt', 'Image may not have attached — proceeding')

            return True

        except Exception as e:
            self._update_status('entering_prompt', f'Image upload error: {str(e)[:60]}')
            return False

    # ══════════════════════════════════════
    # FULL WORKFLOW
    # ══════════════════════════════════════

    def generate_banners(self, prompt, aspect_ratio='landscape', count=4, download_dir=None, image_path=None, reuse_project=False):
        """Full: navigate → settings → prompt → create → wait → download 2K each.
        Returns: {'success': bool, 'downloaded_files': [...], 'errors': [...]}
        """
        if download_dir:
            self.download_dir = download_dir
            os.makedirs(self.download_dir, exist_ok=True)
            try:
                abs_path = os.path.abspath(self.download_dir)
                self.driver.execute_cdp_cmd('Browser.setDownloadBehavior', {
                    'behavior': 'allow', 'downloadPath': abs_path})
            except Exception as e:
                print(f"[FlowBot] ⚠️ CDP setDownloadBehavior failed: {e}")

        result = {'success': False, 'downloaded_files': [], 'errors': []}

        try:
            if reuse_project:
                # Already on project page from previous batch
                self._update_status('navigating', 'Reusing current project...')
                count_before = self.count_images()
                project_url = self.driver.current_url
            else:
                # Navigate
                if not self.navigate_to_flow():
                    result['errors'].append('Could not open Flow project')
                    return result

                # Settings
                self.set_image_settings(aspect_ratio, count)

                # Upload reference image if provided
                if image_path:
                    self.upload_reference_image(image_path)

                # Count existing images AFTER upload so reference image is included
                count_before = self.count_images()
                project_url = self.driver.current_url

            # Type prompt + Create
            self.type_prompt(prompt)
            if not self.click_create():
                result['errors'].append('Could not click Create')
                return result

            # Wait for images
            self.wait_for_images(count_before, count)

            # Get edit URLs for new images
            edit_urls = self.get_new_image_edit_urls(count_before)
            self._update_status('downloading', f'Found {len(edit_urls)} new images to download')

            if not edit_urls:
                result['errors'].append('No new images found')
                return result

            # Download each in 2K
            files = self.download_all_new_images(edit_urls, project_url)
            result['downloaded_files'] = files
            result['success'] = len(files) > 0
            result['errors'] = self.errors
            self._update_status('complete', f'Done! {len(files)} banners downloaded in 2K')

        except Exception as e:
            result['errors'].append(str(e))
            self._update_status('error', str(e)[:100])

        return result
