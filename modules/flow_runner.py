# pyright: reportOptionalMemberAccess=false
"""
Standalone Flow bot runner for agent pipeline.
Manages a persistent session across batches.
"""

import os
import shutil
import time
from typing import Any
from selenium.webdriver.chrome.options import Options
from selenium import webdriver


class FlowSession:
    """Keeps driver + bot alive across multiple batches."""

    def __init__(self):
        self.driver: webdriver.Chrome | None = None
        self.bot: Any = None

    def start(self):
        from modules.chrome_launcher import ensure_flow_chrome
        from modules.flow_bot import FlowBot

        if not ensure_flow_chrome('crimsonbox69@gmail.com'):
            print("[FlowSession] Could not launch Flow Chrome")
            return False

        opts = Options()
        opts.add_experimental_option('debuggerAddress', '127.0.0.1:9223')

        self.driver = webdriver.Chrome(options=opts)
        self.driver.set_script_timeout(120)

        download_dir = os.path.expanduser('~/Downloads')
        self.bot = FlowBot(self.driver, download_dir=download_dir)
        print("[FlowSession] Session started")
        return True

    def run_batch(self, prompt, aspect_ratio='1:1', count=4, output_dir=None, reference_image=None, is_first=True):
        """Run a single batch. is_first=True creates new project, False reuses current."""
        if not self.bot:
            print("[FlowSession] No active session")
            return []

        ar_map = {
            '1:1': 'square',
            '16:9': 'landscape',
            '9:16': 'portrait',
            '4:3': 'landscape',
            '3:4': 'portrait',
            '4:5': 'portrait',
        }
        flow_ar = ar_map.get(aspect_ratio, 'square')

        result = self.bot.generate_banners(
            prompt=prompt,
            aspect_ratio=flow_ar,
            count=min(count, 4),
            image_path=reference_image,
            reuse_project=not is_first,
        )

        # Move downloaded files to output_dir
        final_files = []
        if result.get('success') and result.get('downloaded_files'):
            if output_dir:
                os.makedirs(output_dir, exist_ok=True)
            for src_path in result['downloaded_files']:
                if os.path.exists(src_path):
                    if output_dir:
                        dst_path = os.path.join(output_dir, os.path.basename(src_path))
                        shutil.move(src_path, dst_path)
                        final_files.append(dst_path)
                    else:
                        final_files.append(src_path)

        print(f"[FlowSession] Batch done: {len(final_files)} images")
        return final_files

    def close(self):
        if self.driver:
            try:
                self.driver.quit()
                print("[FlowSession] ChromeDriver session closed — Chrome stays alive")
            except Exception:
                pass
            self.driver = None
            self.bot = None


# Backward-compatible wrapper for single-batch calls
def run_flow_batch(prompt, aspect_ratio='1:1', count=4, output_dir=None, reference_image=None):
    session = FlowSession()
    if not session.start():
        return []
    try:
        return session.run_batch(prompt, aspect_ratio, count, output_dir, reference_image, is_first=True)
    finally:
        session.close()