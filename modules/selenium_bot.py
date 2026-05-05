# pyright: reportOptionalMemberAccess=false
"""
Mr.Creative — Selenium Bot for Pomelli Automation
Exact Pomelli flow: Enter prompt → Generate Ideas → Pick idea → Wait for 4 creatives → Download all via 3-dot menu
Photoshoot flow: Upload image → Select templates → Create Photoshoot → Wait → Download All
Animate flow: After creatives ready → User picks cards → Click Animate → Wait for videos → Download All

DOM Selectors extracted from live Pomelli console (March 2026):
  Landing: div.title-medium.on-surface-variant (text cards, NOT clickable buttons)
  Intermediate: button.edit-button (pencil icons), APP-PHOTOSHOOT-INGREDIENTS-EDITOR
  Upload: app-upload-image-button button, img.thumbnail.img-loaded, span.selection-count
  Templates: div.label.label-large.selected, mat-icon.selected-icon, div.seasonal-label
  Results: APP-PHOTOSHOOT-EDITOR, app-shimmer-loader, mat-progress-spinner, "Download All"
  Animate: button.animate-button[aria-label="Animate"], button[aria-label="Animate without text"]
           div.video-container, video.video, button.play-pause-button, button.overflow-button
  All pages: span.mdc-button__label for button text identification
"""

import os
import re
import time
import shutil
import datetime
import base64
from typing import Any

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import (
    TimeoutException, NoSuchElementException,
    ElementClickInterceptedException, WebDriverException,
    StaleElementReferenceException
)

try:
    from webdriver_manager.chrome import ChromeDriverManager
except ImportError:
    ChromeDriverManager = None


POMELLI_URL = 'https://labs.google.com/pomelli'
POMELLI_HOME = 'https://labs.google.com/pomelli/'
POMELLI_PHOTOSHOOT = 'https://labs.google.com/pomelli/photoshoot'

WAIT_SHORT = 5
WAIT_MEDIUM = 15
WAIT_LONG = 60
WAIT_CREATIVES = 600
WAIT_ANIMATE = 600
DOWNLOAD_WAIT = 8


class PomelliBotStatus:
    IDLE = 'idle'
    LOGGING_IN = 'logging_in'
    NAVIGATING = 'navigating'
    ENTERING_PROMPT = 'entering_prompt'
    GENERATING = 'generating'
    ANIMATING = 'animating'
    DOWNLOADING = 'downloading'
    COMPLETE = 'complete'
    ERROR = 'error'


class PomelliBot:

    def __init__(self, config):
        self.config = config
        self.driver: webdriver.Chrome | None = None
        self.status = PomelliBotStatus.IDLE
        self.status_message = ''
        self.errors: list[str] = []
        # Shared state for UI interaction
        self._pending_ideas: list[Any] = []
        self._selected_idea: int | None = None
        self._pending_animate_cards: list[Any] = []
        self._selected_animate_indices: list[int] | None = None  # None = waiting, [] = skip, [0,1,...] = animate these
        self._current_job_id: str | None = None
        self._force_relogin = False  # Set by bot manager on account switch
        # Pause/Resume support
        import threading
        self._pause_event = threading.Event()
        self._pause_event.set()  # Start in "running" state
        self._is_paused = False

    def pause(self):
        """Pause the bot at the next checkpoint."""
        self._pause_event.clear()
        self._is_paused = True
        self._update_status(self.status, f'⏸ PAUSED — {self.status_message}')

    def resume(self):
        """Resume the bot from where it was paused."""
        self._is_paused = False
        self._pause_event.set()

    def _check_pause(self):
        """Checkpoint — blocks here if bot is paused. Call at safe points in the workflow."""
        if not self._pause_event.is_set():
            self._update_status(self.status, f'⏸ Paused — waiting to resume...')
            self._pause_event.wait()  # Blocks until resume() is called
            if not self._is_paused:
                self._update_status(self.status, '▶ Resumed!')

    def _update_status(self, status, message=''):
        self.status = status
        self.status_message = message
        print(f"[PomelliBot] {status}: {message}")

    # ============================================
    # BROWSER SETUP
    # ============================================
    CHROME_DEBUG_PORT = 9222

    def _setup_driver(self):
        download_dir = os.path.abspath(self.config.get('download_dir', './downloads'))
        os.makedirs(download_dir, exist_ok=True)
        self._download_dir = download_dir

        # Kill any orphaned Chrome using our debug port (from previous server run)
        self._kill_orphaned_chrome()

        options = Options()
        prefs = {
            'download.default_directory': download_dir,
            'download.prompt_for_download': False,
            'download.directory_upgrade': True,
            'safebrowsing.enabled': True,
            'profile.default_content_settings.popups': 0,
            # Disable autofill and password manager (prevents wrong email on account switch)
            'credentials_enable_service': False,
            'profile.password_manager_enabled': False,
            'autofill.profile_enabled': False,
            'autofill.credit_card_enabled': False,
        }
        options.add_experimental_option('prefs', prefs)
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-blink-features=AutomationControlled')
        options.add_argument('--window-size=1920,1080')
        options.add_argument(f'--remote-debugging-port={self.CHROME_DEBUG_PORT}')
        options.add_experimental_option('excludeSwitches', ['enable-automation'])
        options.add_experimental_option('useAutomationExtension', False)
        if self.config.get('headless', False):
            options.add_argument('--headless=new')
        # Always use a persistent profile so Google login cookies survive
        profile_dir = self.config.get('chrome_profile_dir') or os.path.abspath('chrome_pomelli_profile')
        os.makedirs(profile_dir, exist_ok=True)
        options.add_argument(f'--user-data-dir={os.path.abspath(profile_dir)}')
        # Start Chrome with retry (profile lock may take a moment to release)
        last_error = None
        for attempt in range(3):
            try:
                # Try local chromedriver first (instant, no download)
                local_driver = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'chromedriver.exe')
                if os.path.exists(local_driver):
                    service = Service(local_driver)
                    self.driver = webdriver.Chrome(service=service, options=options)
                elif ChromeDriverManager:
                    service = Service(ChromeDriverManager().install())
                    self.driver = webdriver.Chrome(service=service, options=options)
                else:
                    self.driver = webdriver.Chrome(options=options)
                last_error = None
                break
            except WebDriverException as e:
                last_error = e
                if attempt < 2:
                    self._update_status(PomelliBotStatus.NAVIGATING,
                        f'Chrome start failed (attempt {attempt+1}), retrying...')
                    self._kill_orphaned_chrome()
                    time.sleep(2)
        if last_error:
            raise RuntimeError(f"Failed to start Chrome after 3 attempts: {last_error}")
        self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        self.driver.implicitly_wait(3)
        self.driver.set_script_timeout(120)  # 2 min for async video downloads
        self.driver.execute_cdp_cmd('Page.setDownloadBehavior', {'behavior': 'allow', 'downloadPath': download_dir})

    def _kill_orphaned_chrome(self):
        """Kill any Chrome processes using our debug port or profile directory."""
        import subprocess
        profile_dir = self.config.get('chrome_profile_dir') or os.path.abspath('chrome_pomelli_profile')

        # 1. Kill Chrome by debug port
        try:
            result = subprocess.run(
                ['netstat', '-ano'],
                capture_output=True, text=True, timeout=5
            )
            for line in result.stdout.split('\n'):
                if f':{self.CHROME_DEBUG_PORT}' in line and 'LISTENING' in line:
                    parts = line.strip().split()
                    pid = parts[-1]
                    if pid.isdigit():
                        subprocess.run(['taskkill', '/F', '/PID', pid],
                                     capture_output=True, timeout=5)
                        self._update_status(PomelliBotStatus.NAVIGATING,
                            f'Killed Chrome on port {self.CHROME_DEBUG_PORT} (PID {pid})')
        except Exception:
            pass

        # 2. Kill any chrome.exe using our profile directory
        try:
            result = subprocess.run(
                ['wmic', 'process', 'where', "name='chrome.exe'", 'get', 'ProcessId,CommandLine', '/format:list'],
                capture_output=True, text=True, timeout=10
            )
            profile_name = os.path.basename(profile_dir).lower()
            current_pid = None
            for line in result.stdout.split('\n'):
                line = line.strip()
                if line.startswith('CommandLine=') and profile_name in line.lower():
                    # Next ProcessId line is the PID to kill
                    current_pid = 'pending'
                elif line.startswith('ProcessId=') and current_pid == 'pending':
                    pid = line.split('=')[1].strip()
                    if pid.isdigit():
                        subprocess.run(['taskkill', '/F', '/PID', pid],
                                     capture_output=True, timeout=5)
                    current_pid = None
        except Exception:
            pass

        time.sleep(2)

        # 3. Clean up Chrome profile lock files
        for lock_file in ['SingletonLock', 'SingletonCookie', 'SingletonSocket']:
            lock_path = os.path.join(profile_dir, lock_file)
            try:
                if os.path.exists(lock_path):
                    os.remove(lock_path)
            except Exception:
                pass

    def _clear_profile_passwords(self):
        """Delete saved passwords, autofill, AND cookies from Chrome profile.
        Nuclear option to ensure account switch works cleanly."""
        profile_dir = self.config.get('chrome_profile_dir') or os.path.abspath('chrome_pomelli_profile')
        default_dir = os.path.join(profile_dir, 'Default')
        files_to_delete = [
            'Login Data',           # Saved passwords
            'Login Data-journal',
            'Web Data',             # Autofill data
            'Web Data-journal',
            'Cookies',              # Session cookies (old Google/Pomelli login)
            'Cookies-journal',
            'Network Action Predictor',
            'Preferences',          # May contain autofill prefs
        ]
        for fname in files_to_delete:
            fpath = os.path.join(default_dir, fname)
            try:
                if os.path.exists(fpath):
                    os.remove(fpath)
                    self._update_status(PomelliBotStatus.NAVIGATING, f'Cleared {fname}')
            except Exception:
                pass
        # Also try the top-level profile dir (some Chrome versions put files here)
        for fname in ['Cookies', 'Cookies-journal', 'Login Data', 'Login Data-journal']:
            fpath = os.path.join(profile_dir, fname)
            try:
                if os.path.exists(fpath):
                    os.remove(fpath)
            except Exception:
                pass

    def _try_reconnect_chrome(self):
        """Try to reconnect to a Chrome instance on our debug port.
        Returns True if successful."""
        # Auto-launch Pomelli Chrome if not running
        from modules.chrome_launcher import ensure_pomelli_chrome
        email = self.config.get('google_email', '')
        ensure_pomelli_chrome(email)

        download_dir = os.path.abspath(self.config.get('download_dir', './downloads'))
        os.makedirs(download_dir, exist_ok=True)
        self._download_dir = download_dir
        options = Options()
        options.add_experimental_option("debuggerAddress", f"127.0.0.1:{self.CHROME_DEBUG_PORT}")
        try:
            self.driver = webdriver.Chrome(options=options)
            # Verify it's alive
            _ = self.driver.title
            self.driver.set_script_timeout(120)  # 2 min for async video downloads
            self.driver.execute_cdp_cmd('Page.setDownloadBehavior', {
                'behavior': 'allow', 'downloadPath': download_dir})
            self._update_status(PomelliBotStatus.NAVIGATING,
                f'Reconnected to existing Chrome: {self.driver.title[:50]}')
            return True
        except Exception:
            self.driver = None
            return False

    def connect_to_existing_chrome(self, debug_port=9222):
        download_dir = os.path.abspath(self.config.get('download_dir', './downloads'))
        os.makedirs(download_dir, exist_ok=True)
        self._download_dir = download_dir
        options = Options()
        options.add_experimental_option("debuggerAddress", f"127.0.0.1:{debug_port}")
        try:
            self.driver = webdriver.Chrome(options=options)
            self._update_status(PomelliBotStatus.NAVIGATING, f'Connected to Chrome: {self.driver.title}')
            self.driver.execute_cdp_cmd('Page.setDownloadBehavior', {'behavior': 'allow', 'downloadPath': download_dir})
            return True
        except Exception:
            pass
        self._update_status(PomelliBotStatus.NAVIGATING, 'Starting Chrome...')
        import subprocess
        chrome_path = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
        user_data = os.path.abspath('chrome_debug')
        subprocess.Popen([chrome_path, f'--remote-debugging-port={debug_port}', f'--user-data-dir={user_data}', 'https://labs.google.com/pomelli/'])
        time.sleep(5)
        try:
            self.driver = webdriver.Chrome(options=options)
            self._update_status(PomelliBotStatus.NAVIGATING, f'Connected to Chrome: {self.driver.title}')
            self.driver.execute_cdp_cmd('Page.setDownloadBehavior', {'behavior': 'allow', 'downloadPath': download_dir})
            return True
        except Exception as e:
            self._update_status(PomelliBotStatus.ERROR, f'Cannot connect to Chrome: {str(e)}')
            self.errors.append(str(e))
            return False

    # ============================================
    # GOOGLE LOGIN
    # ============================================
    def _type_slowly(self, element, text, delay=0.015):
        """Paste text instantly via JS instead of typing char by char."""
        try:
            self.driver.execute_script("""
                var el = arguments[0];
                var text = arguments[1];
                el.focus();
                el.value = text;
                el.dispatchEvent(new Event('input', {bubbles: true}));
                el.dispatchEvent(new Event('change', {bubbles: true}));
            """, element, text)
        except Exception:
            # Fallback: clipboard paste
            import pyperclip
            pyperclip.copy(text)
            element.send_keys(Keys.CONTROL, 'v')

    def _handle_account_chooser(self):
        """Handle Google's 'Choose an account' page.
        Clicks 'Use another account' to get to the email input field."""
        time.sleep(2)
        try:
            # Check if we're on the account chooser page
            if 'accountchooser' not in self.driver.current_url and 'signin' not in self.driver.current_url:
                return

            self._update_status(PomelliBotStatus.LOGGING_IN, 'Account chooser detected...')

            # Try clicking "Use another account"
            use_another_selectors = [
                '//div[contains(text(), "Use another account")]',
                '//li[contains(., "Use another account")]',
                '//*[contains(text(), "Use another account")]',
            ]
            for xpath in use_another_selectors:
                try:
                    btn = WebDriverWait(self.driver, 5).until(
                        EC.element_to_be_clickable((By.XPATH, xpath)))
                    btn.click()
                    self._update_status(PomelliBotStatus.LOGGING_IN, 'Clicked "Use another account"')
                    time.sleep(3)
                    return
                except (TimeoutException, Exception):
                    continue

            # If "Use another account" not found, check if our email is listed
            configured_email = self.config.get('google_email', '').lower()
            if configured_email:
                try:
                    # Click the matching account row directly
                    accounts = self.driver.find_elements(By.CSS_SELECTOR,
                        'div[data-email], li[data-identifier]')
                    for acc in accounts:
                        acc_email = (acc.get_attribute('data-email') or
                                    acc.get_attribute('data-identifier') or
                                    acc.text or '').lower()
                        if configured_email in acc_email:
                            acc.click()
                            self._update_status(PomelliBotStatus.LOGGING_IN,
                                f'Selected existing account: {configured_email}')
                            time.sleep(3)
                            return
                except Exception:
                    pass

            self._update_status(PomelliBotStatus.LOGGING_IN,
                'Account chooser — no matching action found, waiting for email input...')
        except Exception:
            pass

    def _ensure_on_pomelli_or_login(self):
        """After navigating to Pomelli, check if we got redirected to login.
        With Chrome profiles, just click the right account — never type passwords."""
        time.sleep(3)
        for attempt in range(10):
            if self._is_on_pomelli():
                self._update_status(PomelliBotStatus.LOGGING_IN, 'Already logged in!')
                return True

            url = self.driver.current_url
            if 'accounts.google.com' in url:
                self._update_status(PomelliBotStatus.LOGGING_IN, 'Account chooser detected...')

                # Try clicking matching account directly
                configured_email = self.config.get('google_email', '').lower()
                clicked = self.driver.execute_script("""
                    var target = arguments[0];
                    // Try data-email accounts
                    var accs = document.querySelectorAll('div[data-email], li[data-identifier]');
                    for (var a of accs) {
                        var email = (a.getAttribute('data-email') || a.getAttribute('data-identifier') || '').toLowerCase();
                        if (email === target) { a.click(); return 'clicked_data'; }
                    }
                    // Try by visible text
                    var all = document.querySelectorAll('div, li, a');
                    for (var el of all) {
                        if (!el.offsetParent) continue;
                        if (el.textContent.toLowerCase().includes(target) && el.children.length < 5) {
                            el.click(); return 'clicked_text';
                        }
                    }
                    return 'not_found';
                """, configured_email)

                self._update_status(PomelliBotStatus.LOGGING_IN, f'Account click: {clicked}')

                if clicked != 'not_found':
                    # Wait for redirect to Pomelli
                    for _ in range(15):
                        time.sleep(2)
                        if self._is_on_pomelli():
                            self._update_status(PomelliBotStatus.LOGGING_IN, 'Logged in!')
                            return True
                        # Handle password page if Google asks (rare with saved sessions)
                        if 'challenge' in self.driver.current_url or 'pwd' in self.driver.current_url:
                            self._update_status(PomelliBotStatus.LOGGING_IN, 'Password required — using saved session...')
                            break
                    if self._is_on_pomelli():
                        return True

                # If account not found in chooser, try "Use another account" then type email only
                self._handle_account_chooser()

            time.sleep(2)

        # Last resort: try full login
        if not self._is_on_pomelli():
            self._update_status(PomelliBotStatus.LOGGING_IN, 'Profile login needed — attempting...')
            return self.login_google()

        return self._is_on_pomelli()

    def login_google(self):
        self._update_status(PomelliBotStatus.LOGGING_IN, 'Opening Pomelli...')
        email = self.config.get('google_email', '')
        password = self.config.get('google_password', '')
        self.driver.get(POMELLI_URL)
        time.sleep(4)
        if self._is_on_pomelli():
            self._update_status(PomelliBotStatus.NAVIGATING, 'Already logged in!')
            return True
        if not email or not password:
            self._update_status(PomelliBotStatus.ERROR, 'No Google credentials configured')
            return False
        try:
            # Handle "Choose an account" page (appears when accounts exist in Chrome)
            self._handle_account_chooser()

            self._update_status(PomelliBotStatus.LOGGING_IN, f'Entering email: {email}...')
            email_input = WebDriverWait(self.driver, WAIT_LONG).until(EC.presence_of_element_located((By.CSS_SELECTOR, 'input[type="email"]')))

            # Triple-click to select all, delete, then type fresh
            email_input.click(); time.sleep(0.1); email_input.send_keys(Keys.CONTROL, "a")
            time.sleep(0.3)
            email_input.send_keys(Keys.DELETE)
            time.sleep(0.3)
            email_input.send_keys(Keys.ESCAPE)  # Dismiss autofill dropdown
            time.sleep(0.3)

            # Type the correct email character by character
            self._type_slowly(email_input, email)
            time.sleep(0.3)
            email_input.send_keys(Keys.ESCAPE)  # Dismiss autofill dropdown again
            time.sleep(0.5)

            # Verify
            actual = email_input.get_attribute('value')
            self._update_status(PomelliBotStatus.LOGGING_IN, f'Email field value: {actual}')

            if actual.lower() != email.lower():
                self._update_status(PomelliBotStatus.LOGGING_IN,
                    f'Wrong value! Clearing and retrying...')
                # Nuclear: JS set value
                self.driver.execute_script("""
                    var el = arguments[0];
                    var nativeSet = Object.getOwnPropertyDescriptor(
                        window.HTMLInputElement.prototype, 'value').set;
                    nativeSet.call(el, '');
                    el.dispatchEvent(new Event('input', {bubbles:true}));
                """, email_input)
                time.sleep(0.3)
                self.driver.execute_script("""
                    var el = arguments[0];
                    var nativeSet = Object.getOwnPropertyDescriptor(
                        window.HTMLInputElement.prototype, 'value').set;
                    nativeSet.call(el, arguments[1]);
                    el.dispatchEvent(new Event('input', {bubbles:true}));
                    el.dispatchEvent(new Event('change', {bubbles:true}));
                """, email_input, email)
                time.sleep(0.5)
                actual = email_input.get_attribute('value')
                self._update_status(PomelliBotStatus.LOGGING_IN, f'After JS fix: {actual}')

            time.sleep(1)
            try:
                WebDriverWait(self.driver, WAIT_SHORT).until(EC.element_to_be_clickable((By.XPATH, '//button[contains(text(), "Next")] | //span[contains(text(), "Next")]/ancestor::button'))).click()
            except TimeoutException:
                email_input.send_keys(Keys.RETURN)
            time.sleep(5)

            self._update_status(PomelliBotStatus.LOGGING_IN, 'Entering password...')
            time.sleep(3)
            password_input = WebDriverWait(self.driver, WAIT_LONG).until(EC.visibility_of_element_located((By.CSS_SELECTOR, 'input[type="password"]')))
            time.sleep(1)
            # Clear password field
            password_input.click(); time.sleep(0.1); password_input.send_keys(Keys.CONTROL, "a")
            time.sleep(0.2)
            password_input.send_keys(Keys.DELETE)
            password_input.send_keys(Keys.ESCAPE)
            time.sleep(0.3)
            self._type_slowly(password_input, password)
            time.sleep(1)
            try:
                WebDriverWait(self.driver, WAIT_SHORT).until(EC.element_to_be_clickable((By.XPATH, '//button[contains(text(), "Next")] | //span[contains(text(), "Next")]/ancestor::button'))).click()
            except TimeoutException:
                password_input.send_keys(Keys.RETURN)
            time.sleep(5)
            # Handle Google interstitial pages (profile picture, recovery, etc.)
            for _ in range(8):
                try:
                    if self._is_on_pomelli():
                        break
                    # Try clicking Skip/No thanks/Not now buttons via JS (element not always interactable)
                    skipped = self.driver.execute_script("""
                        var xpaths = [
                            '//button[contains(text(), "Skip")]',
                            '//span[contains(text(), "Skip")]/ancestor::button',
                            '//button[contains(text(), "Not now")]',
                            '//span[contains(text(), "Not now")]/ancestor::button',
                            '//button[contains(text(), "No thanks")]',
                            '//a[contains(text(), "Skip")]',
                        ];
                        for (var xp of xpaths) {
                            try {
                                var result = document.evaluate(xp, document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null);
                                if (result.singleNodeValue) {
                                    result.singleNodeValue.click();
                                    return true;
                                }
                            } catch(e) {}
                        }
                        return false;
                    """)
                    if not skipped:
                        break
                    time.sleep(3)
                except Exception:
                    break
            time.sleep(5)
            if not self._is_on_pomelli():
                self._update_status(PomelliBotStatus.LOGGING_IN, 'Waiting for 2FA/redirect...')
                for _ in range(24):
                    time.sleep(5)
                    if self._is_on_pomelli():
                        break
            if self._is_on_pomelli():
                self._update_status(PomelliBotStatus.NAVIGATING, 'Login successful!')
                return True
            self._update_status(PomelliBotStatus.ERROR, 'Login failed or timed out')
            return False
        except Exception as e:
            self._update_status(PomelliBotStatus.ERROR, f'Login error: {str(e)}')
            self.errors.append(str(e))
            return False

    def _is_on_pomelli(self):
        try:
            return '/pomelli' in self.driver.current_url and 'accounts.google.com' not in self.driver.current_url
        except Exception:
            return False

    # ============================================
    # CAMPAIGN FLOW
    # ============================================
    def generate_campaign(self, prompt_text, product_url=None, campaign_images=None, aspect_ratio=None):
        try:
            self._update_status(PomelliBotStatus.NAVIGATING, 'Going to Pomelli home...')
            self.driver.get(POMELLI_HOME)
            time.sleep(3)
            # Check if redirected to Google login
            if not self._is_on_pomelli():
                if not self._ensure_on_pomelli_or_login():
                    raise RuntimeError('Could not reach Pomelli — redirected to login')
                self.driver.get(POMELLI_HOME)
                time.sleep(5)
            self._check_pause()
            self._update_status(PomelliBotStatus.ENTERING_PROMPT, 'Entering prompt...')
            textarea = WebDriverWait(self.driver, WAIT_MEDIUM).until(EC.visibility_of_element_located((By.CSS_SELECTOR, 'textarea[placeholder*="Describe"]')))
            textarea.clear()
            self._type_slowly(textarea, prompt_text, delay=0.03)
            time.sleep(1)

            # ── Campaign options (each step is independent — if one fails, others still run) ──
            if product_url:
                self._check_pause()
                try:
                    self._campaign_add_product_url(product_url)
                except Exception as e:
                    self._update_status(PomelliBotStatus.ENTERING_PROMPT,
                        f'Product URL skipped: {str(e)[:50]}')

            if campaign_images:
                self._check_pause()
                try:
                    self._campaign_add_images(campaign_images)
                except Exception as e:
                    self._update_status(PomelliBotStatus.ENTERING_PROMPT,
                        f'Image selection skipped: {str(e)[:50]}')

            old_count = len(self.driver.find_elements(By.CSS_SELECTOR, 'button[aria-label="Delete idea"]'))
            self._check_pause()
            # Dismiss any lingering overlays from product/image dialogs
            self._dismiss_all_overlays()
            # Select aspect ratio if specified
            try:
                ar = aspect_ratio or 'story'
                ar_map = {'story': 'Story (9:16)', 'square': 'Square (1:1)', 'feed': 'Feed (4:5)'}
                ar_label = ar_map.get(ar, 'Story (9:16)')
                self._update_status(PomelliBotStatus.ENTERING_PROMPT, f'Setting aspect ratio: {ar_label}')
                ar_btn = self.driver.find_element(By.XPATH, '//button[contains(., "Aspect Ratio")]')
                ar_btn.click()
                time.sleep(1)
                option = WebDriverWait(self.driver, 5).until(
                    EC.element_to_be_clickable((By.XPATH, f'//button[contains(., "{ar_label}")]')))
                option.click()
                time.sleep(0.5)
                print(f"[PomelliBot] Aspect ratio set to: {ar_label}")
            except Exception as e:
                print(f"[PomelliBot] Aspect ratio selection failed (continuing): {e}")
            self._update_status(PomelliBotStatus.GENERATING, 'Clicking Generate Ideas...')
            try:
                gen_btn = WebDriverWait(self.driver, WAIT_MEDIUM).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, 'button[aria-label="Generate Ideas"]')))
                self.driver.execute_script("arguments[0].click();", gen_btn)
                print("[PomelliBot] Clicked Generate Ideas via aria-label + JS click")
            except Exception as e1:
                print(f"[PomelliBot] aria-label click failed: {e1}")
                btn = WebDriverWait(self.driver, WAIT_MEDIUM).until(
                    EC.element_to_be_clickable((By.XPATH, '//button[contains(., "Generate Ideas")]')))
                self.driver.execute_script("arguments[0].click();", btn)
                print("[PomelliBot] Clicked Generate Ideas via XPATH fallback")
            time.sleep(3)
            self._update_status(PomelliBotStatus.GENERATING, 'Waiting for ideas...')
            self._wait_for_idea_cards(old_count)
            self._update_status(PomelliBotStatus.GENERATING, 'Extracting ideas...')
            ideas = self._extract_ideas()
            if ideas:
                self._pending_ideas = ideas
                self._selected_idea = None
                self._update_status(PomelliBotStatus.GENERATING, 'WAITING_FOR_SELECTION')
                for _ in range(300):
                    if self._selected_idea is not None:
                        break
                    from routes.generate import _bot_status
                    sel = _bot_status.get(self._current_job_id, {}).get('selected_idea')
                    if sel is not None:
                        self._selected_idea = sel
                        break
                    time.sleep(1)
                if self._selected_idea is not None:
                    self._click_idea_by_index(self._selected_idea)
                else:
                    self._update_status(PomelliBotStatus.GENERATING, 'No selection, using first idea...')
                    self._click_idea_by_index(0)
            else:
                self._click_first_idea()
            self._check_pause()
            self._update_status(PomelliBotStatus.GENERATING, 'Waiting for creatives...')
            self._wait_for_creatives_to_load()
            self._update_status(PomelliBotStatus.COMPLETE, 'All 4 creatives generated!')
            return True
        except Exception as e:
            self._update_status(PomelliBotStatus.ERROR, f'Generation failed: {str(e)}')
            self.errors.append(str(e))
            return False

    def _campaign_add_product_url(self, url):
        """Click Product button → enter URL → click Add → wait for extraction → close dialog.
        If extraction fails or times out, closes dialog and continues without product."""
        self._update_status(PomelliBotStatus.ENTERING_PROMPT, f'Adding product URL: {url[:50]}...')
        try:
            # Click the Product button
            prod_btn = WebDriverWait(self.driver, WAIT_MEDIUM).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR,
                    'button[aria-label="Add product ingredient"]')))
            ActionChains(self.driver).move_to_element(prod_btn).pause(0.3).click().perform()
            time.sleep(2)

            # Wait for the dialog to open
            url_input = WebDriverWait(self.driver, WAIT_MEDIUM).until(
                EC.visibility_of_element_located((By.CSS_SELECTOR,
                    'input[placeholder*="yourbusiness.com"]')))
            time.sleep(0.5)

            # Type the product URL
            url_input.click()
            url_input.clear()
            self._type_slowly(url_input, url, delay=0.02)
            time.sleep(1)

            # Click the Add button
            add_btn = WebDriverWait(self.driver, WAIT_MEDIUM).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR,
                    'button[aria-label="Add product from URL"]')))
            add_btn.click()
            self._update_status(PomelliBotStatus.ENTERING_PROMPT, 'Extracting product...')

            # Wait for extraction (up to 30s), check for success or error
            extraction_ok = False
            for _ in range(15):
                time.sleep(2)
                # Check if dialog closed (extraction succeeded)
                dialogs = self.driver.find_elements(By.CSS_SELECTOR,
                    'app-product-url-scraper-dialog')
                if not dialogs:
                    extraction_ok = True
                    break
                # Check for error message
                error_text = self.driver.execute_script("""
                    var dialog = document.querySelector('app-product-url-scraper-dialog');
                    if (!dialog) return '';
                    return dialog.textContent || '';
                """)
                if 'something went wrong' in error_text.lower() or 'taking too long' in error_text.lower():
                    self._update_status(PomelliBotStatus.ENTERING_PROMPT,
                        'Product extraction failed — skipping, continuing...')
                    break
                # Check if "Extracting..." is still showing
                if 'extracting' in error_text.lower():
                    continue

            # Close dialog if still open (X button or backdrop)
            self._close_product_dialog()

            if extraction_ok:
                self._update_status(PomelliBotStatus.ENTERING_PROMPT, 'Product added!')
            else:
                self._update_status(PomelliBotStatus.ENTERING_PROMPT,
                    'Product extraction failed — continuing without product')

        except Exception as e:
            self._update_status(PomelliBotStatus.ENTERING_PROMPT,
                f'Product URL failed: {str(e)[:60]} — continuing...')
            self._close_product_dialog()

    def _close_product_dialog(self):
        """Close the Product URL dialog and dismiss any overlay backdrop."""
        # Try clicking the X button
        try:
            close_btn = self.driver.find_element(By.CSS_SELECTOR,
                'button[aria-label="close product url scraper dialog"]')
            self.driver.execute_script("arguments[0].click();", close_btn)
            time.sleep(1)
        except NoSuchElementException:
            pass

        # Dismiss any remaining overlay backdrop
        try:
            self.driver.execute_script("""
                document.querySelectorAll('.cdk-overlay-backdrop').forEach(function(el) { el.click(); });
                document.querySelectorAll('.cdk-overlay-container .cdk-overlay-pane').forEach(function(el) { el.remove(); });
            """)
            time.sleep(1)
        except Exception:
            pass

    def _campaign_add_images(self, image_path):
        """Click Images button → open dialog → click Upload Images → upload user's file via
        file explorer (pyautogui) → wait for upload → click Looks Good.
        Same approach as _ps_upload_and_select but for campaign's image picker dialog."""
        if not image_path or not os.path.exists(image_path):
            self._update_status(PomelliBotStatus.ENTERING_PROMPT, 'No campaign image to upload')
            return

        abs_path = os.path.abspath(image_path)
        self._update_status(PomelliBotStatus.ENTERING_PROMPT, f'Adding image: {os.path.basename(abs_path)}')

        try:
            # 1. Click the Images button on campaign page
            img_btn = WebDriverWait(self.driver, WAIT_MEDIUM).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR,
                    'button[aria-label="Add image ingredient"]')))
            ActionChains(self.driver).move_to_element(img_btn).pause(0.3).click().perform()
            time.sleep(3)

            # 2. Wait for dialog to open
            WebDriverWait(self.driver, WAIT_MEDIUM).until(
                EC.presence_of_element_located((By.CSS_SELECTOR,
                    'app-resource-picker-dialog')))
            time.sleep(2)

            # 3. Click Upload Images button inside the dialog
            upload_btn = WebDriverWait(self.driver, WAIT_MEDIUM).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR,
                    'app-upload-image-button button')))
            ActionChains(self.driver).move_to_element(upload_btn).pause(0.3).click().perform()
            self._update_status(PomelliBotStatus.ENTERING_PROMPT, 'Clicked Upload Images')

            # 4. Handle file explorer dialog via pyautogui (same as photoshoot)
            import pyautogui
            import subprocess
            time.sleep(2)
            subprocess.run(['clip'], input=abs_path.encode(), check=True)
            pyautogui.hotkey('ctrl', 'v')
            time.sleep(0.5)
            pyautogui.press('enter')
            self._update_status(PomelliBotStatus.ENTERING_PROMPT, f'Uploading: {os.path.basename(abs_path)}')
            time.sleep(10)  # Wait for upload to complete

            # 5. Check selection count
            try:
                sel = self.driver.find_element(By.CSS_SELECTOR, 'span.selection-count').text
                self._update_status(PomelliBotStatus.ENTERING_PROMPT, f'Selection: {sel.strip()}')
                # If not auto-selected, click the last thumbnail
                match = re.search(r'\((\d+)/\d+ selected\)', sel)
                if match and int(match.group(1)) == 0:
                    thumbs = self.driver.find_elements(By.CSS_SELECTOR, 'img.thumbnail.img-loaded')
                    if thumbs:
                        ActionChains(self.driver).move_to_element(thumbs[-1]).pause(0.3).click().perform()
                        time.sleep(1)
                        sel = self.driver.find_element(By.CSS_SELECTOR, 'span.selection-count').text
                        self._update_status(PomelliBotStatus.ENTERING_PROMPT, f'Selected: {sel.strip()}')
            except Exception:
                pass

            # 6. Click Looks Good
            time.sleep(1)
            try:
                looks_good = WebDriverWait(self.driver, WAIT_MEDIUM).until(
                    EC.element_to_be_clickable((By.XPATH,
                        '//span[contains(text(), "Looks Good")]/ancestor::button')))
                ActionChains(self.driver).move_to_element(looks_good).pause(0.3).click().perform()
                self._update_status(PomelliBotStatus.ENTERING_PROMPT, 'Image added!')
                time.sleep(2)
            except TimeoutException:
                self._update_status(PomelliBotStatus.ENTERING_PROMPT,
                    'Looks Good not found — closing dialog')

        except Exception as e:
            self._update_status(PomelliBotStatus.ENTERING_PROMPT,
                f'Image upload failed: {str(e)[:60]}')

        # Always clean up
        self._dismiss_all_overlays()

    def _dismiss_all_overlays(self):
        """Dismiss any open dialog overlays."""
        try:
            self.driver.execute_script("""
                document.querySelectorAll('.cdk-overlay-backdrop').forEach(function(el) { el.click(); });
                document.querySelectorAll('.cdk-overlay-container .cdk-overlay-backdrop').forEach(function(el) { el.remove(); });
            """)
            time.sleep(0.5)
        except Exception:
            pass

    def _campaign_set_aspect_ratio(self, ratio):
        """Set aspect ratio on the campaign page. Same button as Generate/Edit."""
        ratio_map = {'story': 'Story (9:16)', 'square': 'Square (1:1)', 'feed': 'Feed (4:5)'}
        target = ratio_map.get(ratio, ratio_map.get('story'))
        self._update_status(PomelliBotStatus.ENTERING_PROMPT, f'Setting aspect ratio: {target}')
        try:
            ar_btn = WebDriverWait(self.driver, WAIT_MEDIUM).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, 'button.aspect-ratio-button')))
            ActionChains(self.driver).move_to_element(ar_btn).pause(0.3).click().perform()
            time.sleep(1)
            for item in self.driver.find_elements(By.CSS_SELECTOR,
                    'button.mat-mdc-menu-item[role="menuitem"]'):
                if target in item.text:
                    item.click()
                    self._update_status(PomelliBotStatus.ENTERING_PROMPT, f'Aspect ratio: {target}')
                    time.sleep(1)
                    return
        except Exception as e:
            self._update_status(PomelliBotStatus.ENTERING_PROMPT,
                f'Aspect ratio failed: {str(e)[:60]}')

    def _wait_for_idea_cards(self, old_count=0):
        start = time.time()
        while time.time() - start < 180:
            time.sleep(4)
            try:
                url = self.driver.current_url
                if '/campaigns/' in url:
                    print("[PomelliBot] Campaign URL detected — ideas loaded")
                    return
                delete_btns = self.driver.find_elements(By.CSS_SELECTOR, 'button[aria-label="Delete idea"]')
                idea_cards = self.driver.find_elements(By.CSS_SELECTOR, 'div.campaign-idea-card')
                print(f"[PomelliBot] Waiting... delete_btns={len(delete_btns)} idea_cards={len(idea_cards)}")
                if len(delete_btns) - old_count >= 3 or len(idea_cards) >= 3:
                    time.sleep(2)
                    return
            except Exception as e:
                err_type = type(e).__name__
                err_msg = str(e).split('\n')[0][:100]
                print(f"[PomelliBot] Wait error: {err_type}: {err_msg}")
                # If Chrome disconnected, try to recover
                try:
                    _ = self.driver.title
                except Exception:
                    print("[PomelliBot] Chrome disconnected during wait!")
                    raise
                time.sleep(3)

    def _click_first_idea(self):
        time.sleep(2)
        btns = self.driver.find_elements(By.CSS_SELECTOR, 'button[aria-label="Delete idea"]')
        if btns:
            try:
                card = self.driver.execute_script("""
                    let el = arguments[0];
                    for (let i = 0; i < 10; i++) { el = el.parentElement; if (!el) break;
                      if (el.tagName === 'MAT-CARD' || el.getAttribute('role') === 'button' || el.style.cursor === 'pointer') return el; }
                    return arguments[0].parentElement.parentElement;
                """, btns[0])
                if card:
                    card.click()
                    time.sleep(3)
            except Exception:
                pass

    def _extract_ideas(self):
        """Extract idea titles + descriptions from div.campaign-idea-card."""
        time.sleep(2)
        ideas = self.driver.execute_script("""
            var cards = document.querySelectorAll('div.campaign-idea-card');
            var results = [];
            for (var card of cards) {
                if (!card.offsetParent) continue;
                var title = card.querySelector('.title-medium');
                var desc = card.querySelector('.label-medium');
                if (title) {
                    results.push({
                        title: title.textContent.trim(),
                        description: desc ? desc.textContent.trim() : '',
                        x: Math.round(card.getBoundingClientRect().left)
                    });
                }
            }
            results.sort(function(a, b) { return a.x - b.x; });
            return results;
        """)
        self._update_status(PomelliBotStatus.GENERATING, f'Found {len(ideas)} ideas')
        return ideas

    def _click_idea_by_index(self, index):
        """Click a specific idea card by index (0-based, left to right)."""
        cards = self.driver.execute_script("""
            var cards = document.querySelectorAll('div.campaign-idea-card');
            var visible = [];
            for (var c of cards) { if (c.offsetParent) visible.push(c); }
            visible.sort(function(a, b) {
                return a.getBoundingClientRect().left - b.getBoundingClientRect().left;
            });
            return visible;
        """)
        if cards and index < len(cards):
            card = cards[index]
            ActionChains(self.driver).move_to_element(card).pause(0.3).click().perform()
            self._update_status(PomelliBotStatus.GENERATING, f'Selected idea {index + 1}')
            time.sleep(3)
        else:
            self._click_first_idea()

    def download_assets(self, output_dir=None):
        self._update_status(PomelliBotStatus.DOWNLOADING, 'Preparing to download...')
        download_dir = output_dir or self._download_dir
        os.makedirs(download_dir, exist_ok=True)
        existing_files = set(os.listdir(download_dir))
        self.driver.execute_cdp_cmd('Page.setDownloadBehavior', {'behavior': 'allow', 'downloadPath': download_dir})
        try:
            time.sleep(3)
            cards = self.driver.execute_script("""
                var all=document.querySelectorAll('*'),cards=[];
                for(var el of all){var r=el.getBoundingClientRect();
                if(r.width>200&&r.height>300&&r.width<500&&r.top>100&&el.querySelector('img'))cards.push(el);}
                var u=[];for(var c of cards){var d=false;for(var x of u){if(x.contains(c)||c.contains(x)){d=true;break;}}if(!d)u.push(c);}return u;
            """)
            for i, card in enumerate(cards):
                try:
                    ActionChains(self.driver).move_to_element(card).perform()
                    time.sleep(0.5)
                    w = self.driver.execute_script("return arguments[0].offsetWidth", card)
                    h = self.driver.execute_script("return arguments[0].offsetHeight", card)
                    ActionChains(self.driver).move_to_element_with_offset(card, w//2-15, -h//2+15).pause(0.5).click().perform()
                    time.sleep(2)
                    items = WebDriverWait(self.driver, 10).until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, 'button.mat-mdc-menu-item, [role="menuitem"]')))
                    if len(items) >= 2:
                        items[1].click()
                    time.sleep(2)
                    try:
                        ActionChains(self.driver).move_by_offset(-300, -300).perform()
                    except Exception:
                        pass
                    time.sleep(1)
                except Exception:
                    try:
                        self.driver.execute_script("document.querySelectorAll('.cdk-overlay-backdrop').forEach(el=>el.click());")
                    except Exception:
                        pass
                    time.sleep(2)
            time.sleep(DOWNLOAD_WAIT)
            return self._collect_downloads(download_dir, existing_files)
        except Exception as e:
            self._update_status(PomelliBotStatus.ERROR, f'Download error: {str(e)}')
            self.errors.append(str(e))
            return []

    def _collect_downloads(self, download_dir, existing_files):
        """Collect new files from download dir."""
        downloaded = []
        time.sleep(2)
        try:
            for f in set(os.listdir(download_dir)) - existing_files:
                if not f.endswith(('.crdownload', '.tmp')):
                    downloaded.append(os.path.join(download_dir, f))
        except Exception:
            pass
        return downloaded

    # ============================================
    # PHOTOSHOOT FLOW — Exact DOM selectors
    # ============================================
    def run_photoshoot(self, image_path, templates=None, photoshoot_mode='product'):
        if not templates:
            templates = []
        try:
            # ── Force navigate to clean landing page ──
            self._update_status(PomelliBotStatus.NAVIGATING, 'Resetting to Pomelli home...')
            self.driver.get(POMELLI_HOME)
            time.sleep(3)
            if not self._is_on_pomelli():
                if not self._ensure_on_pomelli_or_login():
                    raise RuntimeError('Could not reach Pomelli — redirected to login')

            # Navigate to Photoshoot landing page
            self._update_status(PomelliBotStatus.NAVIGATING, 'Opening Photoshoot page...')
            self.driver.get(POMELLI_PHOTOSHOOT)
            time.sleep(5)
            self._ensure_on_photoshoot_page()

            self._check_pause()
            self._update_status(PomelliBotStatus.NAVIGATING, 'Clicking mode card...')
            self._ps_click_mode_card(photoshoot_mode)

            # ── Upload product image ──
            self._check_pause()
            self._update_status(PomelliBotStatus.ENTERING_PROMPT, 'Clicking Product Image edit...')
            self._ps_click_edit_button('first')
            time.sleep(2)

            self._check_pause()
            self._update_status(PomelliBotStatus.ENTERING_PROMPT, 'Uploading product image...')
            self._ps_upload_and_select(image_path)

            # ── Select templates ──
            if templates and photoshoot_mode == 'product':
                self._check_pause()
                # Wait for templates card to become enabled
                self._update_status(PomelliBotStatus.ENTERING_PROMPT, 'Waiting for Templates to enable...')
                for _ in range(15):
                    disabled = self.driver.find_elements(By.CSS_SELECTOR, 'div.ingredient.disabled')
                    if not disabled:
                        break
                    time.sleep(1)
                time.sleep(1)

                self._update_status(PomelliBotStatus.ENTERING_PROMPT, 'Clicking Templates edit...')
                self._ps_click_edit_button('second')
                time.sleep(2)
                self._update_status(PomelliBotStatus.ENTERING_PROMPT, f'Selecting {len(templates)} templates...')
                self._ps_match_templates(templates)

            # ── Generate ──
            self._check_pause()
            self._update_status(PomelliBotStatus.GENERATING, 'Clicking Generate Photoshoot...')
            self._ps_click_create()

            self._check_pause()
            self._update_status(PomelliBotStatus.GENERATING, 'Waiting for images...')
            self._wait_for_creatives_to_load()

            self._update_status(PomelliBotStatus.COMPLETE, 'Photoshoot creatives ready!')
            return True
        except Exception as e:
            self._update_status(PomelliBotStatus.ERROR, f'Photoshoot failed: {str(e)}')
            self.errors.append(str(e))
            return False

    def _ensure_on_photoshoot_page(self):
        """If Pomelli redirected to Campaigns or home, navigate back to Photoshoot."""
        time.sleep(2)
        current = self.driver.current_url
        # Already on photoshoot? Check if landing page or editor rendered
        if 'photoshoot' in current:
            return
        # Redirected to campaigns or home — click sidebar
        self._update_status(PomelliBotStatus.NAVIGATING, 'Redirected — clicking Photoshoot sidebar...')
        for link in self.driver.find_elements(By.CSS_SELECTOR, 'div.nav-item'):
            if 'Photoshoot' in link.text:
                self.driver.execute_script("arguments[0].click();", link)
                time.sleep(3)
                return
        # Fallback: direct navigation
        self.driver.get(POMELLI_PHOTOSHOOT)
        time.sleep(3)

    def _ps_click_mode_card(self, mode):
        """Navigate past landing page to editor. Handles both states:
        A) Landing page with cards → click card → editor loads
        B) Editor already loaded → proceed directly"""
        target = 'Create a product' if mode == 'product' else 'Generate or edit'

        for attempt in range(3):
            # Poll for 30s — detect whichever page we're on
            for tick in range(30):
                time.sleep(1)
                try:
                    # State B: editor already loaded
                    if self.driver.find_elements(By.CSS_SELECTOR, 'div.ingredient'):
                        self._update_status(PomelliBotStatus.NAVIGATING, 'Editor loaded!')
                        return

                    # State A: landing page cards
                    cards = self.driver.find_elements(By.CSS_SELECTOR, 'div.photoshoot-branch-button')
                    for card in cards:
                        if target in card.text:
                            self.driver.execute_script("arguments[0].click();", card)
                            self._update_status(PomelliBotStatus.NAVIGATING, f'Clicked: {card.text.strip()[:40]}')
                            # Wait for editor
                            for _ in range(20):
                                time.sleep(1)
                                if self.driver.find_elements(By.CSS_SELECTOR, 'div.ingredient'):
                                    self._update_status(PomelliBotStatus.NAVIGATING, 'Editor loaded!')
                                    return
                            break

                    # Fallback: title text
                    if not cards:
                        titles = self.driver.find_elements(By.CSS_SELECTOR, 'div.title-medium.on-surface-variant')
                        for t in titles:
                            if target in t.text:
                                self.driver.execute_script("arguments[0].click();", t)
                                self._update_status(PomelliBotStatus.NAVIGATING, f'Clicked title: {t.text.strip()[:40]}')
                                for _ in range(20):
                                    time.sleep(1)
                                    if self.driver.find_elements(By.CSS_SELECTOR, 'div.ingredient'):
                                        self._update_status(PomelliBotStatus.NAVIGATING, 'Editor loaded!')
                                        return
                                break
                except Exception:
                    pass

            # Retry
            self._update_status(PomelliBotStatus.NAVIGATING, f'Retry {attempt+1}/3...')
            self.driver.get(POMELLI_PHOTOSHOOT)
            time.sleep(5)

        raise RuntimeError('Could not reach editor page')

    def _ps_click_edit_button(self, which='first'):
        """Editor page: click pencil edit button. 'first'=Product Image, 'second'=Templates."""
        idx = 0 if which == 'first' else 1
        for _ in range(15):
            # Filter to only visible icon buttons with text "edit"
            btns = []
            for b in self.driver.find_elements(By.CSS_SELECTOR, 'button'):
                if b.is_displayed() and b.text.strip() == 'edit' and 'edit' in (b.get_attribute('class') or ''):
                    btns.append(b)
            if len(btns) > idx:
                self.driver.execute_script("arguments[0].click();", btns[idx])
                self._update_status(PomelliBotStatus.ENTERING_PROMPT, f'Clicked edit button ({which})')
                time.sleep(2)
                return
            time.sleep(1)
        self._update_status(PomelliBotStatus.ENTERING_PROMPT, f'Edit button "{which}" not found')

    def _ps_upload_and_select(self, image_path):
        """Upload page: upload image via file dialog, then click Looks Good."""
        abs_path = os.path.abspath(image_path)
        if not os.path.exists(abs_path):
            raise FileNotFoundError(f'Image not found: {abs_path}')

        # Wait for upload page
        for _ in range(10):
            if self.driver.find_elements(By.CSS_SELECTOR, 'app-upload-image-button'):
                break
            time.sleep(1)
        time.sleep(1)

        # Click "Upload Images" button
        try:
            upload_btn = WebDriverWait(self.driver, WAIT_MEDIUM).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, 'app-upload-image-button button')))
            self.driver.execute_script("arguments[0].click();", upload_btn)
            self._update_status(PomelliBotStatus.ENTERING_PROMPT, 'Clicked Upload Images')
        except TimeoutException:
            self._update_status(PomelliBotStatus.ENTERING_PROMPT, 'Upload button not found')
            return

        # File dialog: paste path and enter
        import pyautogui
        import subprocess
        time.sleep(2)
        subprocess.run(['clip'], input=abs_path.encode(), check=True)
        pyautogui.hotkey('ctrl', 'v')
        time.sleep(0.5)
        pyautogui.press('enter')
        self._update_status(PomelliBotStatus.ENTERING_PROMPT, f'Path entered: {os.path.basename(abs_path)}')
        time.sleep(10)

        # Image is auto-selected after upload — just verify
        try:
            time.sleep(3)
            thumbs = self.driver.find_elements(By.CSS_SELECTOR, 'img.thumbnail')
            self._update_status(PomelliBotStatus.ENTERING_PROMPT, f'{len(thumbs)} thumbnails found')

            # Check if Looks Good is already enabled (image auto-selected)
            looks_good_ready = False
            for btn in self.driver.find_elements(By.CSS_SELECTOR, 'button'):
                if 'Looks Good' in btn.text and btn.is_enabled():
                    looks_good_ready = True
                    break

            if looks_good_ready:
                self._update_status(PomelliBotStatus.ENTERING_PROMPT, 'Image auto-selected!')
            elif thumbs:
                # Fallback: click first thumbnail if not auto-selected
                self._update_status(PomelliBotStatus.ENTERING_PROMPT, 'Not auto-selected — clicking first thumbnail')
                self.driver.execute_script("arguments[0].click();", thumbs[0])
                time.sleep(2)
        except Exception as e:
            self._update_status(PomelliBotStatus.ENTERING_PROMPT, f'Selection error: {str(e)[:50]}')

        # Click Looks Good
        self._ps_click_looks_good()

    def _ps_match_templates(self, user_templates):
        """Template picker: swap templates to match user selection. Always keep 4."""
        user_wants = set(t.strip() for t in user_templates[:4])

        # Pad to 4 if user gave fewer
        available_names = ['Studio', 'Floating', 'Ingredient', 'In Use', 'Contextual', 'Flatlay']
        while len(user_wants) < 4:
            for fallback in available_names:
                if fallback not in user_wants:
                    user_wants.add(fallback)
                    break
            else:
                break

        # Wait for template picker
        for _ in range(10):
            if self.driver.find_elements(By.CSS_SELECTOR, 'app-template-picker'):
                break
            time.sleep(1)
        time.sleep(2)

        self._update_status(PomelliBotStatus.ENTERING_PROMPT, f'Want: {sorted(user_wants)}')

        def find_img_for_label(label_el):
            """Walk backwards from label to find its IMG sibling."""
            return self.driver.execute_script("""
                var el = arguments[0].previousElementSibling;
                while (el) { if (el.tagName === 'IMG') return el; el = el.previousElementSibling; }
                return null;
            """, label_el)

        def get_selected_names():
            """Get names of currently selected templates."""
            names = []
            for lbl in self.driver.find_elements(By.CSS_SELECTOR, 'div.label.label-large.selected'):
                name = lbl.text.strip()
                # Skip seasonal labels (contain "arrow_drop_down")
                if name and 'arrow_drop_down' not in name:
                    names.append(name)
            return names

        # Read current state
        current = get_selected_names()
        self._update_status(PomelliBotStatus.ENTERING_PROMPT, f'Currently selected: {current}')

        to_deselect = [n for n in current if n not in user_wants]
        to_select = [n for n in user_wants if n not in current]

        self._update_status(PomelliBotStatus.ENTERING_PROMPT,
            f'Swap: deselect {to_deselect}, select {to_select}')

        # Swap one-by-one: deselect one → select one (keep count at 4)
        for i in range(max(len(to_deselect), len(to_select))):
            # Deselect one unwanted
            if i < len(to_deselect):
                target_name = to_deselect[i]
                for lbl in self.driver.find_elements(By.CSS_SELECTOR, 'div.label.label-large.selected'):
                    if lbl.text.strip() == target_name:
                        img = find_img_for_label(lbl)
                        if img:
                            self.driver.execute_script(
                                "arguments[0].scrollIntoView({block:'center'});", img)
                            time.sleep(0.3)
                            ActionChains(self.driver).move_to_element(img).pause(0.2).click().perform()
                            self._update_status(PomelliBotStatus.ENTERING_PROMPT, f'Deselected: {target_name}')
                            time.sleep(0.8)
                            break

            # Select one wanted from pool
            if i < len(to_select):
                target_name = to_select[i]
                # Re-query labels (DOM changed)
                for lbl in self.driver.find_elements(By.CSS_SELECTOR, 'div.label.label-large'):
                    if 'selected' in (lbl.get_attribute('class') or ''):
                        continue
                    if lbl.text.strip() == target_name:
                        img = find_img_for_label(lbl)
                        if img:
                            self.driver.execute_script(
                                "arguments[0].scrollIntoView({block:'center'});", img)
                            time.sleep(0.3)
                            ActionChains(self.driver).move_to_element(img).pause(0.2).click().perform()
                            self._update_status(PomelliBotStatus.ENTERING_PROMPT, f'Selected: {target_name}')
                            time.sleep(0.8)
                            break

        # Verify
        time.sleep(1)
        final = get_selected_names()
        count_el = self.driver.find_elements(By.CSS_SELECTOR, 'span.selection-count')
        count_text = count_el[0].text if count_el else '?'
        self._update_status(PomelliBotStatus.ENTERING_PROMPT, f'Final: {final} {count_text}')

        if len(final) != 4:
            self._update_status(PomelliBotStatus.ENTERING_PROMPT,
                f'WARNING: {len(final)} selected, need 4!')

        self._ps_click_looks_good()

    def _ps_click_looks_good(self):
        """Click the 'Looks Good' button (shared across sub-pages)."""
        time.sleep(1)
        for _ in range(20):
            for btn in self.driver.find_elements(By.CSS_SELECTOR, 'button'):
                if 'Looks Good' in btn.text and btn.is_displayed():
                    if btn.is_enabled():
                        self.driver.execute_script("arguments[0].click();", btn)
                        self._update_status(PomelliBotStatus.ENTERING_PROMPT, 'Clicked Looks Good')
                        time.sleep(3)
                        return
                    else:
                        self._update_status(PomelliBotStatus.ENTERING_PROMPT, 'Looks Good disabled — waiting...')
            time.sleep(1)
        self._update_status(PomelliBotStatus.ENTERING_PROMPT, 'Looks Good not found after 20s')

    def _ps_click_create(self):
        """Click 'Generate Photoshoot' button on editor page."""
        for _ in range(30):
            for btn in self.driver.find_elements(By.CSS_SELECTOR, 'button'):
                txt = btn.text.strip()
                if ('Generate Photoshoot' in txt or 'Create Photoshoot' in txt):
                    if btn.is_enabled() and btn.is_displayed():
                        self.driver.execute_script("arguments[0].click();", btn)
                        self._update_status(PomelliBotStatus.GENERATING, f'Clicked: {txt}')
                        time.sleep(5)
                        return
                    else:
                        self._update_status(PomelliBotStatus.GENERATING, 'Generate button disabled — waiting...')
            time.sleep(1)
        raise RuntimeError('Generate Photoshoot button not found or stayed disabled')

    def _wait_for_creatives_to_load(self):
        """Results page: wait for all loading indicators to disappear."""
        start = time.time()
        while time.time() - start < WAIT_CREATIVES:
            time.sleep(5)
            shimmers = [s for s in self.driver.find_elements(By.CSS_SELECTOR, 'app-shimmer-loader') if s.is_displayed()]
            spinners = [s for s in self.driver.find_elements(By.CSS_SELECTOR, 'mat-progress-spinner') if s.is_displayed()]
            texts = [t for t in self.driver.find_elements(By.CSS_SELECTOR, 'app-generation-progress-loader .text') if t.is_displayed()]
            total = len(shimmers) + len(spinners) + len(texts)
            elapsed = int(time.time() - start)
            if total == 0 and elapsed > 15:
                self._update_status(PomelliBotStatus.GENERATING, 'All creatives ready!')
                time.sleep(5)
                return True
            self._update_status(PomelliBotStatus.GENERATING, f'Waiting... {total} loading ({elapsed}s)')
        return True

    def download_photoshoot_assets(self, output_dir=None):
        """Download each image individually by hover+click."""
        self._check_pause()
        self._update_status(PomelliBotStatus.DOWNLOADING, 'Preparing download...')
        download_dir = output_dir or self._download_dir
        os.makedirs(download_dir, exist_ok=True)
        existing = set(os.listdir(download_dir))
        self.driver.execute_cdp_cmd('Page.setDownloadBehavior', {'behavior': 'allow', 'downloadPath': download_dir})
        try:
            time.sleep(1)
            self._update_status(PomelliBotStatus.DOWNLOADING, 'Downloading images individually...')
            self._ps_download_by_hover(download_dir)
            time.sleep(DOWNLOAD_WAIT)
            files = self._collect_downloads(download_dir, existing)
            self._update_status(PomelliBotStatus.COMPLETE, f'Downloaded {len(files)} assets!')
            return files
        except Exception as e:
            self._update_status(PomelliBotStatus.ERROR, f'Download error: {str(e)}')
            self.errors.append(str(e))
            return []

    def _ps_download_by_hover(self, download_dir):
        """Download images by extracting src URLs via JS and fetching with Python."""
        time.sleep(2)
        img_urls = self.driver.execute_script("""
            var results = [];
            var imgs = document.querySelectorAll('img');
            for (var img of imgs) {
                if (!img.offsetParent || !img.src) continue;
                var r = img.getBoundingClientRect();
                if (r.width > 100 && r.height > 100 && r.left > 0
                    && img.naturalWidth > 200) {
                    results.push({src: img.src, x: Math.round(r.left)});
                }
            }
            results.sort(function(a, b) { return a.x - b.x; });
            return results;
        """)
        self._update_status(PomelliBotStatus.DOWNLOADING, f'Found {len(img_urls)} images')
        self._download_urls(img_urls, download_dir, 'image')

    def _download_urls(self, url_list, download_dir, asset_type='image'):
        """Download URLs. Images use urllib, videos use browser fetch for proper auth."""
        if asset_type == 'video':
            self._download_videos_via_browser(url_list, download_dir)
        else:
            self._download_images_via_urllib(url_list, download_dir)

    def _download_images_via_urllib(self, url_list, download_dir):
        """Download images using urllib with session cookies."""
        cookies = {c['name']: c['value'] for c in self.driver.get_cookies()}
        import urllib.request
        for i, info in enumerate(url_list):
            try:
                src = info['src']
                ts = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
                filepath = os.path.join(download_dir, f'pomelli-image-{ts}_{i+1}.png')
                if src.startswith('data:'):
                    header, b64 = src.split(',', 1)
                    with open(filepath, 'wb') as f:
                        f.write(base64.b64decode(b64))
                else:
                    req = urllib.request.Request(src)
                    req.add_header('Cookie', '; '.join(f'{k}={v}' for k, v in cookies.items()))
                    req.add_header('User-Agent', 'Mozilla/5.0')
                    with urllib.request.urlopen(req) as resp:
                        with open(filepath, 'wb') as f:
                            f.write(resp.read())
                size_kb = os.path.getsize(filepath) // 1024
                self._update_status(PomelliBotStatus.DOWNLOADING,
                    f'Saved image {i+1}/{len(url_list)} ({size_kb}KB)')
            except Exception as e:
                self._update_status(PomelliBotStatus.DOWNLOADING,
                    f'Failed image {i+1}: {str(e)[:60]}')

    def _download_videos_via_browser(self, url_list, download_dir):
        """Download videos using the browser's fetch API (has full Pomelli auth).
        Falls back to <a download> click if fetch fails."""
        for i, info in enumerate(url_list):
            src = info['src']
            ts = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f'pomelli-video-{ts}_{i+1}.mp4'
            filepath = os.path.join(download_dir, filename)

            self._update_status(PomelliBotStatus.DOWNLOADING,
                f'Downloading video {i+1}/{len(url_list)} via browser...')

            try:
                # Method 1: Use browser's fetch API to get video as base64
                result = self.driver.execute_async_script("""
                    var url = arguments[0];
                    var callback = arguments[arguments.length - 1];
                    fetch(url, {credentials: 'include'})
                        .then(function(response) {
                            if (!response.ok) throw new Error('HTTP ' + response.status);
                            return response.blob();
                        })
                        .then(function(blob) {
                            // Check if it's actually a video
                            var type = blob.type || '';
                            var reader = new FileReader();
                            reader.onload = function() {
                                callback({
                                    success: true,
                                    data: reader.result,
                                    type: type,
                                    size: blob.size
                                });
                            };
                            reader.onerror = function() {
                                callback({success: false, error: 'FileReader failed'});
                            };
                            reader.readAsDataURL(blob);
                        })
                        .catch(function(err) {
                            callback({success: false, error: err.message || String(err)});
                        });
                """, src)

                if result and result.get('success'):
                    data_url = result['data']
                    content_type = result.get('type', '')
                    blob_size = result.get('size', 0)

                    self._update_status(PomelliBotStatus.DOWNLOADING,
                        f'Video {i+1}: type={content_type} size={blob_size//1024}KB')

                    # Extract base64 data after the header
                    if ',' in data_url:
                        b64_data = data_url.split(',', 1)[1]
                        with open(filepath, 'wb') as f:
                            f.write(base64.b64decode(b64_data))

                        size_kb = os.path.getsize(filepath) // 1024
                        # Verify it's actually a video (should be > 100KB)
                        if size_kb < 50:
                            self._update_status(PomelliBotStatus.DOWNLOADING,
                                f'Video {i+1} too small ({size_kb}KB), may be invalid')
                        else:
                            self._update_status(PomelliBotStatus.DOWNLOADING,
                                f'Saved video {i+1}/{len(url_list)} ({size_kb}KB)')
                    else:
                        self._update_status(PomelliBotStatus.DOWNLOADING,
                            f'Video {i+1}: invalid data URL response')
                else:
                    error = result.get('error', 'unknown') if result else 'no response'
                    self._update_status(PomelliBotStatus.DOWNLOADING,
                        f'Browser fetch failed for video {i+1}: {error}')
                    # Method 2: Fall back to <a download> click
                    self._download_video_via_link_click(src, download_dir, i, len(url_list))

            except Exception as e:
                self._update_status(PomelliBotStatus.DOWNLOADING,
                    f'Video download error {i+1}: {str(e)[:80]}')
                # Fall back to link click
                try:
                    self._download_video_via_link_click(src, download_dir, i, len(url_list))
                except Exception:
                    pass

    def _download_video_via_link_click(self, url, download_dir, index, total):
        """Fallback: trigger download by clicking an <a download> link in the browser."""
        self._update_status(PomelliBotStatus.DOWNLOADING,
            f'Trying link-click download for video {index+1}...')
        self.driver.execute_cdp_cmd('Page.setDownloadBehavior', {
            'behavior': 'allow', 'downloadPath': download_dir})
        self.driver.execute_script("""
            var a = document.createElement('a');
            a.href = arguments[0];
            a.download = 'pomelli-video-download.mp4';
            a.style.display = 'none';
            document.body.appendChild(a);
            a.click();
            setTimeout(function() { document.body.removeChild(a); }, 1000);
        """, url)
        # Wait for download to complete
        time.sleep(15)
        self._update_status(PomelliBotStatus.DOWNLOADING,
            f'Link-click download triggered for video {index+1}')

    # ============================================
    # ANIMATE FLOW
    # ============================================
    def extract_creative_cards(self):
        """After creatives are ready, extract thumbnail info for each card.
        Converts images to base64 data URIs so they display in Mr.Creative UI
        (Pomelli image URLs require auth cookies that Mr.Creative doesn't have).
        Returns list of dicts: {index, src, x, has_animate_btn}"""
        time.sleep(3)

        # Extract images and convert to base64 via canvas (bypasses CORS for same-origin)
        cards = self.driver.execute_script("""
            var results = [];
            var imgs = document.querySelectorAll('img');
            for (var img of imgs) {
                if (!img.offsetParent || !img.src) continue;
                var r = img.getBoundingClientRect();
                if (r.width > 100 && r.height > 100 && r.left > 0
                    && img.naturalWidth > 200) {
                    // Convert to base64 via canvas
                    var b64 = '';
                    try {
                        var canvas = document.createElement('canvas');
                        // Use smaller size for thumbnail (saves bandwidth)
                        var scale = Math.min(200 / img.naturalWidth, 350 / img.naturalHeight);
                        canvas.width = Math.round(img.naturalWidth * scale);
                        canvas.height = Math.round(img.naturalHeight * scale);
                        var ctx = canvas.getContext('2d');
                        ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
                        b64 = canvas.toDataURL('image/jpeg', 0.7);
                    } catch(e) {
                        b64 = img.src;  // Fallback to URL if canvas fails (CORS)
                    }
                    results.push({
                        src: b64,
                        x: Math.round(r.left),
                        y: Math.round(r.top),
                        w: Math.round(r.width),
                        h: Math.round(r.height)
                    });
                }
            }
            results.sort(function(a, b) { return a.x - b.x; });
            return results;
        """)

        card_info = []
        for i, c in enumerate(cards):
            card_info.append({
                'index': i,
                'src': c['src'],
                'x': c['x'],
                'has_animate_btn': True,
            })

        # Move mouse away
        try:
            ActionChains(self.driver).move_by_offset(-400, -400).perform()
        except Exception:
            pass

        self._update_status(PomelliBotStatus.GENERATING,
            f'Found {len(card_info)} cards, {sum(1 for c in card_info if c["has_animate_btn"])} animatable')
        return card_info

    def animate_selected_cards(self, indices):
        """Click Animate on each selected card index (0-based, left-to-right).
        Tracks cards by src URL to avoid position shift after each animation."""
        if not indices:
            self._update_status(PomelliBotStatus.ANIMATING, 'No cards selected for animation, skipping.')
            return True

        self._update_status(PomelliBotStatus.ANIMATING,
            f'Animating {len(indices)} cards: {[i+1 for i in indices]}')

        # Step 1: Snapshot the src URLs of cards BEFORE any animation
        all_cards = self._scan_creative_images()
        target_srcs = []
        for idx in indices:
            if idx < len(all_cards):
                target_srcs.append(all_cards[idx]['src'])
                self._update_status(PomelliBotStatus.ANIMATING,
                    f'Marked card {idx+1} for animation (src: ...{all_cards[idx]["src"][-30:]})')

        # Step 2: Animate each card by finding it via src URL
        for i, src in enumerate(target_srcs):
            self._check_pause()
            self._update_status(PomelliBotStatus.ANIMATING,
                f'Animating card {i+1}/{len(target_srcs)}...')
            self._animate_card_by_src(src, i)

        # Wait for all videos to finish generating
        self._update_status(PomelliBotStatus.ANIMATING, 'Waiting for all videos to generate...')
        self._wait_for_animations_to_complete()
        return True

    def _scan_creative_images(self):
        """Scan all creative images, return list of {el, src, x, y} sorted left-to-right."""
        return self.driver.execute_script("""
            var results = [];
            var imgs = document.querySelectorAll('img');
            for (var img of imgs) {
                if (!img.offsetParent || !img.src) continue;
                var r = img.getBoundingClientRect();
                if (r.width > 150 && r.height > 200 && r.left > 200
                    && img.naturalWidth > 200) {
                    results.push({el: img, src: img.src, x: r.left, y: r.top,
                        cx: r.left + r.width/2, cy: r.top + r.height/2});
                }
            }
            results.sort(function(a, b) { return a.x - b.x; });
            return results;
        """)

    def _animate_card_by_src(self, target_src, attempt_num):
        """Find a card by its src URL (handles position shifts), scroll if needed, then animate."""
        time.sleep(1)

        # Try to find the card, scrolling if necessary
        img_el = None
        for scroll_attempt in range(5):
            img_el = self.driver.execute_script("""
                var target = arguments[0];
                var imgs = document.querySelectorAll('img');
                for (var img of imgs) {
                    if (!img.offsetParent || !img.src) continue;
                    if (img.src === target) {
                        img.scrollIntoView({block: 'center', behavior: 'smooth'});
                        return img;
                    }
                }
                return null;
            """, target_src)

            if img_el:
                break

            # Scroll right to find off-screen cards
            self.driver.execute_script("window.scrollBy({left: 400, behavior: 'smooth'})")
            time.sleep(1)

        if not img_el:
            self._update_status(PomelliBotStatus.ANIMATING,
                f'Card not found after scrolling, skipping')
            return

        time.sleep(1)
        self._update_status(PomelliBotStatus.ANIMATING,
            f'Found card, triggering Animate...')

        # Use pure JS hover + click — no physical mouse movement to avoid triggering adjacent cards
        anim_btn = self.driver.execute_script("""
            var img = arguments[0];
            // Dispatch hover events up the tree to reveal animate button
            var el = img;
            var cardEl = null;
            for (var i = 0; i < 10; i++) {
                if (!el.parentElement) break;
                el = el.parentElement;
                ['mouseenter', 'mouseover', 'pointerenter', 'pointerover'].forEach(function(evt) {
                    el.dispatchEvent(new MouseEvent(evt, {bubbles: true, cancelable: true}));
                });
                // Check if animate button appeared at each level
                var btn = el.querySelector('button[aria-label="Animate"]');
                if (btn) cardEl = el;
            }
            // Wait briefly for button to render
            return cardEl;
        """, img_el)
        time.sleep(2)

        # Now find the animate button strictly within this card
        clicked = self.driver.execute_script("""
            var img = arguments[0];
            var imgRect = img.getBoundingClientRect();
            var el = img;
            for (var i = 0; i < 10; i++) {
                if (!el.parentElement) break;
                el = el.parentElement;
                var btn = el.querySelector('button[aria-label="Animate"]');
                if (btn) {
                    var btnRect = btn.getBoundingClientRect();
                    // Verify button is within this card's horizontal bounds
                    if (btnRect.left >= imgRect.left - 20 && btnRect.right <= imgRect.right + 20) {
                        btn.click();
                        return 'clicked';
                    }
                }
            }
            return 'not_found';
        """, img_el)

        if clicked != 'clicked':
            self._update_status(PomelliBotStatus.ANIMATING,
                f'Animate button not found for this card, skipping')
            return

        self._update_status(PomelliBotStatus.ANIMATING, f'Clicked Animate!')
        time.sleep(3)

        # Handle "Animate without text" dialog if it appears
        try:
            dialog_clicked = self.driver.execute_script("""
                var btns = document.querySelectorAll('button');
                for (var b of btns) {
                    var t = b.textContent.trim();
                    if ((t === 'Animate without text' || b.getAttribute('aria-label') === 'Animate without text')
                        && b.offsetParent) {
                        b.click();
                        return 'clicked';
                    }
                }
                return 'no_dialog';
            """)
            if dialog_clicked == 'clicked':
                self._update_status(PomelliBotStatus.ANIMATING, 'Clicked "Animate without text"')
                time.sleep(2)
        except Exception:
            pass

        self._update_status(PomelliBotStatus.ANIMATING, f'Animation started!')
        time.sleep(2)

    def _wait_for_animations_to_complete(self):
        """Wait for video generation to complete.
        Video generation takes 1-5 minutes. We wait until:
        - Video elements with real src appear, OR
        - High demand error is detected, OR
        - Timeout (10 min)"""
        start = time.time()
        found_videos_count = 0

        while time.time() - start < WAIT_ANIMATE:
            time.sleep(8)
            elapsed = int(time.time() - start)

            # Check loading indicators
            shimmers = [s for s in self.driver.find_elements(By.CSS_SELECTOR, 'app-shimmer-loader') if s.is_displayed()]
            spinners = [s for s in self.driver.find_elements(By.CSS_SELECTOR, 'mat-progress-spinner') if s.is_displayed()]
            progress_texts = [t for t in self.driver.find_elements(
                By.CSS_SELECTOR, 'app-generation-progress-loader .text') if t.is_displayed()]
            total_loading = len(shimmers) + len(spinners) + len(progress_texts)

            # Check for video elements with real HTTPS src (not empty, not blob)
            video_count = self.driver.execute_script("""
                var count = 0;
                document.querySelectorAll('video').forEach(function(v) {
                    var src = v.src || v.currentSrc || '';
                    if (src && src.startsWith('http')) count++;
                });
                return count;
            """)

            # Check for "high demand" / error messages on the page
            error_detected = self.driver.execute_script("""
                var text = (document.body.innerText || '').toLowerCase();
                return text.indexOf('high demand') > -1 || text.indexOf('experiencing high') > -1;
            """)

            # High demand error — stop waiting, download what we have
            if error_detected:
                self._update_status(PomelliBotStatus.ANIMATING,
                    f'Pomelli high demand error. {video_count} videos generated. Downloading...')
                time.sleep(3)
                return True

            # Videos found — success!
            if video_count > 0 and total_loading == 0:
                self._update_status(PomelliBotStatus.ANIMATING,
                    f'Animation complete! {video_count} video(s) ready.')
                time.sleep(5)
                return True

            # Still loading — keep waiting
            if total_loading > 0 or elapsed < 120:
                self._update_status(PomelliBotStatus.ANIMATING,
                    f'Generating video... {total_loading} loading, {video_count} videos ({elapsed}s)')
                continue

            # No loaders AND no videos AND past 2 minutes — something went wrong
            if total_loading == 0 and video_count == 0 and elapsed > 120:
                self._update_status(PomelliBotStatus.ANIMATING,
                    f'No videos appeared after {elapsed}s. Proceeding to download images...')
                time.sleep(3)
                return True

        self._update_status(PomelliBotStatus.ANIMATING, 'Animation wait timed out')
        return True

    def extract_video_urls(self):
        """Extract all video src URLs from the results page.
        Pomelli uses real HTTPS URLs like:
        https://labs.google.com/pomelli_downloads/accounts/.../resources/...?authuser=0"""
        # Scroll through page to trigger lazy-loaded videos
        self.driver.execute_script("window.scrollTo(0, 0);")
        time.sleep(1)
        self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight / 2);")
        time.sleep(1)
        self.driver.execute_script("window.scrollTo(0, 0);")
        time.sleep(2)

        video_data = self.driver.execute_script("""
            var results = [];
            var seen = {};
            // Find ALL video elements on the page (don't filter by visibility)
            var videos = document.querySelectorAll('video');
            for (var v of videos) {
                var src = v.src || v.currentSrc || '';
                // Also check source child elements
                if (!src || src.startsWith('blob:') || src.startsWith('data:')) {
                    var sources = v.querySelectorAll('source');
                    for (var s of sources) {
                        if (s.src && s.src.startsWith('http')) { src = s.src; break; }
                    }
                }
                // Only keep real HTTPS URLs (pomelli_downloads pattern)
                if (src && src.startsWith('http') && !seen[src]) {
                    seen[src] = true;
                    var r = v.getBoundingClientRect();
                    results.push({
                        src: src,
                        x: Math.round(r.left),
                        cls: v.className,
                        w: Math.round(r.width),
                        h: Math.round(r.height),
                        visible: !!(v.offsetParent),
                        parentTag: v.parentElement ? v.parentElement.tagName : 'none'
                    });
                }
            }
            results.sort(function(a, b) { return a.x - b.x; });
            return results;
        """)

        # Log what was found for debugging
        for i, v in enumerate(video_data):
            self._update_status(PomelliBotStatus.DOWNLOADING,
                f'Video {i+1}: {v["cls"]} {v["w"]}x{v["h"]} visible={v["visible"]} parent={v["parentTag"]}')

        self._update_status(PomelliBotStatus.DOWNLOADING, f'Found {len(video_data)} video URLs')
        return video_data

    def extract_image_urls(self):
        """Extract all visible creative image URLs from results page."""
        time.sleep(1)
        # Scroll to top to ensure all cards are in view
        self.driver.execute_script("window.scrollTo(0, 0);")
        time.sleep(1)

        img_data = self.driver.execute_script("""
            var results = [];
            var seen = {};
            var imgs = document.querySelectorAll('img');
            for (var img of imgs) {
                if (!img.offsetParent || !img.src) continue;
                // Skip duplicates by src
                if (seen[img.src]) continue;
                var r = img.getBoundingClientRect();
                // Creative images are large (>150px wide, >200px tall), right of sidebar (>200px left)
                if (r.width > 100 && r.height > 100 && r.left > 0
                    && img.naturalWidth > 200) {
                    seen[img.src] = true;
                    results.push({src: img.src, x: Math.round(r.left)});
                }
            }
            results.sort(function(a, b) { return a.x - b.x; });
            return results;
        """)
        self._update_status(PomelliBotStatus.DOWNLOADING, f'Found {len(img_data)} images')
        return img_data

    def download_all_assets_with_videos(self, output_dir=None):
        """Download both images and videos from the results page.
        If animate failed (high demand, etc.), still downloads all available images."""
        self._check_pause()
        self._update_status(PomelliBotStatus.DOWNLOADING, 'Preparing to download all assets...')
        download_dir = output_dir or self._download_dir
        os.makedirs(download_dir, exist_ok=True)
        existing = set(os.listdir(download_dir))
        self.driver.execute_cdp_cmd('Page.setDownloadBehavior', {
            'behavior': 'allow', 'downloadPath': download_dir})

        try:
            # Scroll to top to see all cards
            self.driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(2)

            # Download images
            self._update_status(PomelliBotStatus.DOWNLOADING, 'Downloading images...')
            img_urls = self.extract_image_urls()

            # If very few images found, try scrolling down and scanning again
            if len(img_urls) < 3:
                self._update_status(PomelliBotStatus.DOWNLOADING,
                    f'Only found {len(img_urls)} images, scrolling to find more...')
                self.driver.execute_script("window.scrollTo(0, 0);")
                time.sleep(1)
                # Also try the original photoshoot hover download method
                all_imgs = self.driver.execute_script("""
                    var results = [];
                    var seen = {};
                    var imgs = document.querySelectorAll('img');
                    for (var img of imgs) {
                        if (!img.src || seen[img.src]) continue;
                        if (img.naturalWidth > 200 && img.naturalHeight > 200) {
                            seen[img.src] = true;
                            results.push({src: img.src, x: Math.round(img.getBoundingClientRect().left)});
                        }
                    }
                    results.sort(function(a, b) { return a.x - b.x; });
                    return results;
                """)
                if len(all_imgs) > len(img_urls):
                    img_urls = all_imgs

            self._download_urls(img_urls, download_dir, 'image')

            # Download videos (if any were generated)
            self._update_status(PomelliBotStatus.DOWNLOADING, 'Downloading videos...')
            video_urls = self.extract_video_urls()
            if video_urls:
                self._download_urls(video_urls, download_dir, 'video')
            else:
                self._update_status(PomelliBotStatus.DOWNLOADING,
                    'No videos generated (Pomelli may have hit capacity). Images downloaded.')

            time.sleep(DOWNLOAD_WAIT)
            files = self._collect_downloads(download_dir, existing)
            self._update_status(PomelliBotStatus.COMPLETE,
                f'Downloaded {len(files)} assets ({len(img_urls)} images, {len(video_urls)} videos)!')
            return files
        except Exception as e:
            self._update_status(PomelliBotStatus.ERROR, f'Download error: {str(e)}')
            self.errors.append(str(e))
            return []

    # ============================================
    # GENERATE/EDIT FLOW
    # ============================================
    def run_generate_edit(self, prompt_text='', image_path=None, aspect_ratio='story'):
        try:
            self._update_status(PomelliBotStatus.NAVIGATING, 'Opening Photoshoot page...')
            self.driver.get(POMELLI_PHOTOSHOOT)
            time.sleep(3)
            if not self._is_on_pomelli():
                if not self._ensure_on_pomelli_or_login():
                    raise RuntimeError('Could not reach Pomelli — redirected to login')
                self.driver.get(POMELLI_PHOTOSHOOT)
                time.sleep(3)

            self._update_status(PomelliBotStatus.NAVIGATING, 'Clicking Generate/Edit card...')
            self._ps_click_mode_card('generate')

            for _ in range(10):
                if self.driver.find_elements(By.CSS_SELECTOR, 'app-interleaved-editor'):
                    break
                time.sleep(1)
            time.sleep(2)

            if prompt_text:
                self._check_pause()
                self._update_status(PomelliBotStatus.ENTERING_PROMPT, 'Typing prompt...')
                self._ge_type_prompt(prompt_text)

            if image_path and os.path.exists(image_path):
                self._check_pause()
                self._update_status(PomelliBotStatus.ENTERING_PROMPT, 'Adding reference image...')
                self._ge_add_image(image_path)

            if aspect_ratio and aspect_ratio != 'story':
                self._ge_set_aspect_ratio(aspect_ratio)

            self._check_pause()
            self._update_status(PomelliBotStatus.GENERATING, 'Clicking Generate...')
            self._ge_click_generate()

            self._check_pause()
            self._update_status(PomelliBotStatus.GENERATING, 'Waiting for images...')
            self._wait_for_creatives_to_load()

            self._update_status(PomelliBotStatus.COMPLETE, 'Generated images ready!')
            return True
        except Exception as e:
            self._update_status(PomelliBotStatus.ERROR, f'Generate/Edit failed: {str(e)}')
            self.errors.append(str(e))
            return False

    def _ge_type_prompt(self, prompt_text):
        quill = self.driver.find_element(By.CSS_SELECTOR, 'connect-quill-input')
        quill.click()
        time.sleep(0.5)
        self.driver.execute_script("""
            var q = document.querySelector('connect-quill-input');
            var p = q.querySelector('p');
            if (p) p.textContent = arguments[0];
            else q.textContent = arguments[0];
            q.dispatchEvent(new Event('input', {bubbles: true}));
            q.dispatchEvent(new Event('change', {bubbles: true}));
        """, prompt_text)
        time.sleep(1)
        self._update_status(PomelliBotStatus.ENTERING_PROMPT, f'Typed: {prompt_text[:50]}')

    def _ge_add_image(self, image_path):
        abs_path = os.path.abspath(image_path)
        try:
            btn = WebDriverWait(self.driver, WAIT_MEDIUM).until(EC.element_to_be_clickable((By.XPATH,
                '//span[@class="mdc-button__label" and contains(text(), "Add Images")]/ancestor::button')))
            ActionChains(self.driver).move_to_element(btn).pause(0.3).click().perform()
            time.sleep(2)
        except TimeoutException:
            self._update_status(PomelliBotStatus.ENTERING_PROMPT, 'Add Images not found')
            return
        try:
            upload_btn = WebDriverWait(self.driver, WAIT_MEDIUM).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, 'app-upload-image-button button')))
            ActionChains(self.driver).move_to_element(upload_btn).pause(0.3).click().perform()
        except TimeoutException:
            return
        import pyautogui
        import subprocess
        time.sleep(2)
        subprocess.run(['clip'], input=abs_path.encode(), check=True)
        pyautogui.hotkey('ctrl', 'v')
        time.sleep(0.5)
        pyautogui.press('enter')
        self._update_status(PomelliBotStatus.ENTERING_PROMPT, f'Uploaded: {os.path.basename(abs_path)}')
        time.sleep(8)

    def _ge_set_aspect_ratio(self, ratio):
        ratio_map = {'story': 'Story (9:16)', 'square': 'Square (1:1)', 'feed': 'Feed (4:5)'}
        target = ratio_map.get(ratio, ratio_map['story'])
        try:
            ar_btn = self.driver.find_element(By.CSS_SELECTOR, 'button.aspect-ratio-button')
            ActionChains(self.driver).move_to_element(ar_btn).pause(0.3).click().perform()
            time.sleep(1)
            for item in self.driver.find_elements(By.CSS_SELECTOR, 'button.mat-mdc-menu-item[role="menuitem"]'):
                if target in item.text:
                    item.click()
                    time.sleep(1)
                    return
        except Exception:
            pass

    def _ge_click_generate(self):
        btn = WebDriverWait(self.driver, WAIT_MEDIUM).until(EC.element_to_be_clickable((By.XPATH,
            '//span[@class="mdc-button__label" and contains(text(), "Generate")]/ancestor::button')))
        ActionChains(self.driver).move_to_element(btn).pause(0.3).click().perform()
        self._update_status(PomelliBotStatus.GENERATING, 'Clicked Generate!')
        time.sleep(5)

    # ============================================
    # FULL WORKFLOW (updated with animate support)
    # ============================================
    def animate_asset(self):
        """Legacy single-animate method — kept for backward compatibility."""
        try:
            btns = self.driver.find_elements(By.XPATH, '//button[contains(text(), "Animate")] | //span[contains(text(), "Animate")]/ancestor::button')
            if btns:
                self.driver.execute_script("arguments[0].click();", btns[0])
                time.sleep(30)
                return True
            return False
        except Exception:
            return False

    def _verify_or_switch_account(self):
        """Check if Chrome is logged into the correct Google account.
        Returns True if correct account (or can't determine), False if wrong account."""
        try:
            _ = self.driver.title
        except Exception:
            return False

        configured_email = self.config.get('google_email', '')
        if not configured_email:
            return True

        try:
            # Method 1: Check Pomelli page for account info
            logged_email = self.driver.execute_script("""
                var els = document.querySelectorAll(
                    'a[aria-label*="@"], [data-email], img[alt*="@"], ' +
                    'button[aria-label*="@"], [aria-label*="Account"], ' +
                    'a[href*="accounts.google.com"]'
                );
                for (var el of els) {
                    var text = el.getAttribute('aria-label') || el.getAttribute('data-email') ||
                               el.getAttribute('alt') || el.getAttribute('title') || '';
                    var match = text.match(/[\\w.+-]+@[\\w.-]+/);
                    if (match) return match[0];
                }
                return '';
            """)

            if logged_email:
                if configured_email.lower() == logged_email.lower():
                    self._update_status(PomelliBotStatus.NAVIGATING,
                        f'Verified account: {logged_email}')
                    return True
                else:
                    self._update_status(PomelliBotStatus.NAVIGATING,
                        f'Wrong account: {logged_email} → need {configured_email}')
                    return False

            # Method 2: If can't detect from Pomelli, check Google's account page
            self._update_status(PomelliBotStatus.NAVIGATING, 'Checking Google account...')
            current_url = self.driver.current_url
            self.driver.get('https://accounts.google.com/SignOutOptions')
            time.sleep(3)

            page_text = self.driver.execute_script("return document.body.innerText || '';")
            # Navigate back
            self.driver.get(current_url)
            time.sleep(2)

            if configured_email.lower() in page_text.lower():
                self._update_status(PomelliBotStatus.NAVIGATING,
                    f'Verified account via Google: {configured_email}')
                return True
            elif '@' in page_text:
                # Found a different email
                self._update_status(PomelliBotStatus.NAVIGATING,
                    f'Wrong Google account detected → need {configured_email}')
                return False
            else:
                # Can't determine — not logged into any Google account
                self._update_status(PomelliBotStatus.NAVIGATING, 'No Google account detected')
                return False

        except Exception:
            return True  # On error, proceed and let login_google handle it

    def _ensure_connected(self):
        """Ensure we have a working Chrome driver. Tries in order:
        1. Reuse existing driver (from previous job in same server session)
        2. Account switch → kill everything, fresh Chrome, sign out, login
        3. Reconnect to Chrome on debug port (after server restart)
        4. Start fresh Chrome with persistent profile + login"""

        # ── 1. Reuse existing driver (unless account was switched)
        if self.driver is not None and not self._force_relogin:
            try:
                _ = self.driver.title
                self._update_status(PomelliBotStatus.NAVIGATING, 'Reusing Chrome session')
                return
            except Exception:
                self._update_status(PomelliBotStatus.NAVIGATING, 'Chrome session dead')
                self.driver = None

        # ── 2. Account switch — NO reconnect, go fully fresh
        if self._force_relogin:
            self._update_status(PomelliBotStatus.NAVIGATING,
                'Account switch — killing old Chrome and starting fresh...')
            # Kill existing driver
            if self.driver is not None:
                try:
                    self.driver.quit()
                except Exception:
                    pass
                self.driver = None
                time.sleep(2)
            # Kill any orphaned Chrome on our port/profile
            self._kill_orphaned_chrome()
            # Delete saved passwords from profile so autofill doesn't restore old email
            self._clear_profile_passwords()
            # Start fresh Chrome
            self._setup_driver()
            # Clear ALL cookies across ALL domains using CDP (kills Pomelli + Google sessions)
            self._update_status(PomelliBotStatus.LOGGING_IN, 'Clearing all session data...')
            try:
                self.driver.execute_cdp_cmd('Network.clearBrowserCookies', {})
                self.driver.execute_cdp_cmd('Network.clearBrowserCache', {})
            except Exception:
                pass
            # Also clear via Storage API for Pomelli domain
            try:
                self.driver.get('https://labs.google.com/pomelli/')
                time.sleep(2)
                self.driver.execute_script("window.sessionStorage.clear(); window.localStorage.clear();")
                self.driver.delete_all_cookies()
            except Exception:
                pass
            # Sign out of Google
            self._update_status(PomelliBotStatus.LOGGING_IN, 'Signing out of old account...')
            try:
                self.driver.get('https://accounts.google.com/Logout')
                time.sleep(4)
            except Exception:
                pass
            self._force_relogin = False
            # Login with new credentials
            if not self.login_google():
                raise Exception('Login failed after account switch')
            return

        # ── 3. Try reconnecting to Chrome on debug port (after server restart)
        if self.driver is None:
            self._update_status(PomelliBotStatus.NAVIGATING, 'Trying to reconnect to Chrome...')
            if self._try_reconnect_chrome():
                # Reconnected! Check if on Pomelli AND correct account
                if self._is_on_pomelli():
                    # Verify the logged-in account matches
                    if self._verify_or_switch_account():
                        self._update_status(PomelliBotStatus.NAVIGATING, 'Reconnected — correct account!')
                        return
                    else:
                        # Wrong account — sign out and re-login
                        self._update_status(PomelliBotStatus.LOGGING_IN,
                            'Reconnected but wrong account — signing out...')
                        try:
                            self.driver.get('https://accounts.google.com/Logout')
                            time.sleep(4)
                        except Exception:
                            pass
                        if self.login_google():
                            return
                        # Login failed — fall through to fresh
                        try:
                            self.driver.quit()
                        except Exception:
                            pass
                        self.driver = None
                else:
                    # Not on Pomelli — try login
                    if self.login_google():
                        return

        # ── 4. Start fresh Chrome with persistent profile
        self._update_status(PomelliBotStatus.NAVIGATING, 'Starting fresh Chrome...')
        self._setup_driver()
        if not self.login_google():
            raise Exception('Login failed')

    def run_full_workflow(self, prompt_text=None, image_path=None, animate=False,
                         templates=None, photoshoot_mode='product',
                         enable_animate_selection=False,
                         product_url=None, campaign_aspect_ratio=None,
                         campaign_images=None):
        """Full workflow: connect → verify account → generate → animate → download.

        Args:
            enable_animate_selection: If True, after creatives are ready the bot
                pauses and exposes card thumbnails so the UI can let the user pick
                which to animate. The UI sets self._selected_animate_indices.
        """
        result = {
            'success': False,
            'downloaded_files': [],
            'errors': [],
            'status': '',
        }

        # ── CONNECT ──
        try:
            self._ensure_connected()
        except Exception as e:
            result['errors'].append(str(e))
            result['status'] = f'Connection failed: {str(e)[:100]}'
            return result

        try:

            # ── GENERATE ──
            if photoshoot_mode == 'generate':
                success = self.run_generate_edit(
                    prompt_text or '', image_path=image_path,
                    aspect_ratio=self.config.get('aspect_ratio', 'story'))
            elif image_path and os.path.exists(image_path):
                success = self.run_photoshoot(
                    image_path, templates=templates, photoshoot_mode=photoshoot_mode)
            elif prompt_text:
                success = self.generate_campaign(
                    prompt_text,
                    product_url=product_url,
                    campaign_images=campaign_images,
                    aspect_ratio=campaign_aspect_ratio)
            else:
                success = False

            if not success:
                result['errors'] = self.errors
                result['status'] = 'Generation failed'
                return result

            # ── ANIMATE SELECTION (if enabled) ──
            did_animate = False
            if enable_animate_selection:
                # Animate only works on Story (9:16) — skip for Square and Feed
                if campaign_aspect_ratio and campaign_aspect_ratio in ('square', 'feed'):
                    self._update_status(PomelliBotStatus.ANIMATING,
                        f'⚠ Animate not available for {campaign_aspect_ratio} ratio — downloading images only')
                    enable_animate_selection = False
                # Check for animation generation limit BEFORE attempting animate
                elif self.driver.execute_script(
                    "return !!document.querySelector('div.out-of-generations-message');"):
                    self._update_status(PomelliBotStatus.ANIMATING,
                        '⚠ Animation limit reached — downloading images only')
                    enable_animate_selection = False
                else:
                    self._update_status(PomelliBotStatus.GENERATING, 'Extracting card thumbnails...')
                card_info = self.extract_creative_cards()
                if card_info:
                    self._pending_animate_cards = card_info
                    self._selected_animate_indices = None
                    self._update_status(PomelliBotStatus.GENERATING, 'WAITING_FOR_ANIMATE_SELECTION')

                    # Wait up to 5 min for user to pick animate cards
                    for _ in range(300):
                        if self._selected_animate_indices is not None:
                            break
                        # Check if UI posted a selection
                        from routes.generate import _bot_status
                        sel = _bot_status.get(self._current_job_id, {}).get('selected_animate_indices')
                        if sel is not None:
                            self._selected_animate_indices = sel
                            break
                        time.sleep(1)

                    if self._selected_animate_indices is not None and len(self._selected_animate_indices) > 0:
                        self.animate_selected_cards(self._selected_animate_indices)
                        did_animate = True
                    else:
                        self._update_status(PomelliBotStatus.GENERATING, 'No cards selected for animation, skipping.')

            elif animate:
                # Legacy: just animate the first card
                self.animate_asset()
                did_animate = True

            # ── DOWNLOAD ──
            if did_animate:
                downloaded = self.download_all_assets_with_videos()
            else:
                downloaded = self.download_photoshoot_assets()

            result['downloaded_files'] = downloaded
            result['success'] = len(downloaded) > 0
            result['status'] = f'Complete! {len(downloaded)} files downloaded'
            result['errors'] = self.errors
        except Exception as e:
            result['errors'].append(str(e))
            result['status'] = f'Error: {str(e)}'
        return result

    def close(self):
        if self.driver:
            try:
                self.driver.quit()
            except Exception:
                pass
            self.driver = None

    def take_screenshot(self, filename='screenshot.png'):
        if self.driver:
            self.driver.save_screenshot(filename)
            return filename
        return None