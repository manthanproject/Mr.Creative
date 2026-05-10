"""
Night Orchestrator — Browser Factory
Isolated headless Chrome for overnight scraping.
Uses port 9224 + chrome_night_ops_profile to avoid conflicts with Pomelli (9222) / Flow bots.
"""

import os
import logging
import subprocess
import time

logger = logging.getLogger('night_ops')

NIGHT_OPS_DEBUG_PORT = 9224
NIGHT_OPS_PROFILE_DIR = 'chrome_night_ops_profile'


def create_headless_driver(download_dir: str | None = None):
    """
    Create an isolated headless Chrome driver for night ops scraping.
    Returns a webdriver.Chrome instance. Caller MUST call driver.quit() when done.
    """
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service

    # Kill any orphaned Chrome on our port
    _kill_port(NIGHT_OPS_DEBUG_PORT)

    profile_dir = os.path.abspath(NIGHT_OPS_PROFILE_DIR)
    os.makedirs(profile_dir, exist_ok=True)

    options = Options()
    options.add_argument('--headless=new')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-gpu')
    options.add_argument('--disable-blink-features=AutomationControlled')
    options.add_argument('--window-size=1920,1080')
    options.add_argument(f'--remote-debugging-port={NIGHT_OPS_DEBUG_PORT}')
    options.add_argument(f'--user-data-dir={profile_dir}')
    options.add_argument('--disable-extensions')
    options.add_argument('--disable-notifications')
    options.add_argument('--lang=en-US')
    options.add_experimental_option('excludeSwitches', ['enable-automation'])
    options.add_experimental_option('useAutomationExtension', False)

    if download_dir:
        os.makedirs(download_dir, exist_ok=True)
        options.add_experimental_option('prefs', {
            'download.default_directory': os.path.abspath(download_dir),
            'download.prompt_for_download': False,
        })

    # Try local chromedriver first, then fallback
    driver = None
    local_driver = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        'chromedriver.exe'
    )

    try:
        if os.path.exists(local_driver):
            service = Service(local_driver)
            driver = webdriver.Chrome(service=service, options=options)
        else:
            try:
                from webdriver_manager.chrome import ChromeDriverManager
                service = Service(ChromeDriverManager().install())
                driver = webdriver.Chrome(service=service, options=options)
            except ImportError:
                driver = webdriver.Chrome(options=options)
    except Exception as e:
        logger.error(f"[Browser] Chrome start failed: {e}")
        _kill_port(NIGHT_OPS_DEBUG_PORT)
        raise

    # Anti-detection
    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    driver.implicitly_wait(5)
    driver.set_page_load_timeout(30)

    logger.info("[Browser] Headless Chrome started (port 9224)")
    return driver


def _kill_port(port: int):
    """Kill any process using the specified port (Windows)."""
    try:
        result = subprocess.run(
            f'netstat -ano | findstr :{port}',
            capture_output=True, text=True, shell=True, timeout=5
        )
        for line in result.stdout.strip().split('\n'):
            parts = line.split()
            if len(parts) >= 5 and 'LISTENING' in line:
                pid = parts[-1]
                try:
                    subprocess.run(f'taskkill /F /PID {pid}', shell=True, timeout=5,
                                   capture_output=True)
                    logger.info(f"[Browser] Killed orphaned Chrome PID {pid} on port {port}")
                except Exception:
                    pass
    except Exception:
        pass
