"""
Mr.Creative Gemini Bot
Selenium bot that uses Google Gemini (web) to generate image prompts.
Gemini can SEE the product image → writes accurate, product-specific prompts.

Replaces Agent 3 (Prompt Crafter) for better prompt quality.
Flow violations fix: Gemini is instructed to NOT use brand names in prompts.

Chrome profile: chrome_gemini on port 9224
"""

import os
import time
import math
import re
import subprocess

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains


class GeminiBot:
    """Selenium bot for Google Gemini web interface."""

    def __init__(self):
        self.driver: webdriver.Chrome | None = None
        self.connected: bool = False

    def connect(self) -> bool:
        """Connect to Chrome running on port 9224."""
        try:
            from modules.chrome_launcher import ensure_gemini_chrome
            ensure_gemini_chrome()
            time.sleep(2)

            options = webdriver.ChromeOptions()
            options.debugger_address = '127.0.0.1:9224'

            chromedriver_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                'chromedriver.exe'
            )
            service = webdriver.ChromeService(executable_path=chromedriver_path)
            self.driver = webdriver.Chrome(service=service, options=options)
            self.connected = True
            print("[GeminiBot] Connected to Chrome on port 9224")
            return True
        except Exception as e:
            print(f"[GeminiBot] Connection failed: {e}")
            return False

    def close(self):
        """Close ChromeDriver session (Chrome stays alive)."""
        if self.driver:
            try:
                self.driver.quit()
            except Exception:
                pass
            self.driver = None
            self.connected = False
            print("[GeminiBot] ChromeDriver session closed")

    def _drv(self) -> webdriver.Chrome:
        """Get driver — asserts not None to satisfy type checker."""
        assert self.driver is not None, "GeminiBot not connected — call connect() first"
        return self.driver

    def _navigate_to_gemini(self):
        """Navigate to a fresh Gemini chat page."""
        drv = self._drv()
        drv.get('https://gemini.google.com/app')
        time.sleep(4)
        print("[GeminiBot] On Gemini chat page")

    # ═══════════════════════════════════════════
    # Upload Image
    # ═══════════════════════════════════════════

    def _upload_image(self, image_path: str) -> bool:
        """Upload image to Gemini.
        Flow: click + button → click 'Upload files' → native file dialog → pyautogui.
        Selectors hardcoded from DevTools (May 2026).
        """
        abs_path = os.path.abspath(image_path)
        if not os.path.exists(abs_path):
            print(f"[GeminiBot] Image not found: {abs_path}")
            return False

        drv = self._drv()

        try:
            # Step 1: JS click the + button (open upload file menu)
            clicked_plus = drv.execute_script("""
                var btn = document.querySelector('button[aria-label="Open upload file menu"]');
                if (btn) { btn.click(); return 'clicked'; }
                return 'not_found';
            """)
            print(f"[GeminiBot] Plus button: {clicked_plus}")
            if clicked_plus == 'not_found':
                print("[GeminiBot] + button not found (selector: button[aria-label='Open upload file menu'])")
                return False

            # Step 2: Wait for menu to appear
            time.sleep(2)

            # Step 3: JS click "Upload files" from the dropdown
            clicked_upload = drv.execute_script("""
                var btn = document.querySelector('button[aria-label*="Upload files"]');
                if (btn) { btn.click(); return 'clicked'; }
                return 'not_found';
            """)
            print(f"[GeminiBot] Upload files: {clicked_upload}")
            if clicked_upload == 'not_found':
                # Close the menu before returning
                drv.execute_script("""
                    var close = document.querySelector('button[aria-label="Close upload file menu"]');
                    if (close) close.click();
                """)
                print("[GeminiBot] 'Upload files' button not found")
                return False

            # Step 4: Wait for native file dialog (auto-focuses on Windows)
            time.sleep(3)

            # Step 5: Paste file path in dialog and press Enter
            import pyautogui  # type: ignore[import-untyped]
            subprocess.run(['clip'], input=abs_path.encode(), check=True)
            pyautogui.hotkey('ctrl', 'a')
            time.sleep(0.3)
            pyautogui.hotkey('ctrl', 'v')
            time.sleep(1)
            pyautogui.press('enter')
            print(f"[GeminiBot] File selected: {os.path.basename(abs_path)}")

            # Step 6: Wait for upload to finish
            time.sleep(8)

            # Step 7: Verify thumbnail appeared
            has_thumb = drv.execute_script("""
                var imgs = document.querySelectorAll('img');
                for (var img of imgs) {
                    var r = img.getBoundingClientRect();
                    if (r.y > window.innerHeight - 350 && r.width > 30 && r.width < 200)
                        return true;
                }
                var cards = document.querySelectorAll(
                    '[class*="upload-card"], [class*="image-card"], [class*="attachment"]'
                );
                for (var c of cards) {
                    if (c.offsetParent) return true;
                }
                return false;
            """)
            print(f"[GeminiBot] Image thumbnail: {'confirmed!' if has_thumb else 'WARNING not found'}")
            return True

        except Exception as e:
            print(f"[GeminiBot] Image upload error: {e}")
            import traceback
            traceback.print_exc()
            return False

    # ═══════════════════════════════════════════
    # Type Prompt
    # ═══════════════════════════════════════════

    def _type_prompt(self, text: str) -> bool:
        """Type prompt into Gemini's Quill editor via ActionChains.send_keys."""
        drv = self._drv()
        try:
            drv.execute_script("""
                var editor = document.querySelector('div.ql-editor[aria-label="Enter a prompt for Gemini"]');
                if (!editor) editor = document.querySelector('div.ql-editor');
                if (editor) { editor.focus(); }
            """)
            time.sleep(0.5)

            actions = ActionChains(drv)
            actions.send_keys(text)
            actions.perform()
            time.sleep(1)

            print(f"[GeminiBot] Prompt typed: {text[:60]}...")
            return True

        except Exception as e:
            print(f"[GeminiBot] Type error: {e}")
            return False

    # ═══════════════════════════════════════════
    # Send Message
    # ═══════════════════════════════════════════

    def _send_message(self) -> bool:
        """Click send button or press Enter."""
        drv = self._drv()
        try:
            sent = drv.execute_script("""
                var btn = document.querySelector('button[aria-label="Send message"]');
                if (btn) { btn.click(); return 'clicked_send'; }
                return 'not_found';
            """)

            if sent == 'not_found':
                actions = ActionChains(drv)
                actions.send_keys(Keys.RETURN)
                actions.perform()
                sent = 'pressed_enter'

            print(f"[GeminiBot] Send: {sent}")
            return True

        except Exception as e:
            print(f"[GeminiBot] Send error: {e}")
            return False

    # ═══════════════════════════════════════════
    # Wait for Response
    # ═══════════════════════════════════════════

    def _wait_for_response(self, timeout: int = 90) -> str:
        """Wait for Gemini to finish generating response."""
        print("[GeminiBot] Waiting for response...")
        drv = self._drv()
        start = time.time()
        time.sleep(5)

        last_len = 0
        stable_count = 0

        while time.time() - start < timeout:
            response_text: str = drv.execute_script("""
                var els = document.querySelectorAll('message-content');
                if (els.length > 0) {
                    var text = els[els.length - 1].innerText || '';
                    if (text.length > 20) return text;
                }
                var alt = document.querySelectorAll('.model-response-text');
                if (alt.length > 0) {
                    var text = alt[alt.length - 1].innerText || '';
                    if (text.length > 20) return text;
                }
                return '';
            """) or ''

            current_len = len(response_text)
            if current_len > 50 and current_len == last_len:
                stable_count += 1
                if stable_count >= 4:
                    print(f"[GeminiBot] Response complete: {current_len} chars")
                    return response_text
            else:
                stable_count = 0

            last_len = current_len
            elapsed = int(time.time() - start)
            if elapsed % 10 == 0 and elapsed > 0:
                print(f"[GeminiBot] Generating... ({elapsed}s, {current_len} chars)")
            time.sleep(2)

        print(f"[GeminiBot] Timeout after {timeout}s")
        return drv.execute_script("""
            var els = document.querySelectorAll('message-content');
            if (els.length > 0) return els[els.length - 1].innerText || '';
            var alt = document.querySelectorAll('.model-response-text');
            if (alt.length > 0) return alt[alt.length - 1].innerText || '';
            return '';
        """) or ''

    # ═══════════════════════════════════════════
    # Parse Prompts
    # ═══════════════════════════════════════════

    def _parse_prompts_from_response(self, response_text: str, expected_count: int) -> list[str]:
        """Parse Flow prompts from Gemini's response."""
        if not response_text:
            return []

        print(f"[GeminiBot] Raw response (first 500 chars):\n{response_text[:500]}")

        prompts: list[str] = []
        lines = response_text.strip().split('\n')
        current_prompt = ''

        for line in lines:
            line = line.strip()

            if not line:
                if current_prompt and len(current_prompt) > 30:
                    prompts.append(current_prompt.strip())
                    current_prompt = ''
                continue

            cleaned = line.replace('**', '').replace('*', '').replace('`', '')

            # Remove numbered prefixes: "Prompt 1:", "1.", "1)", "Prompt 1 (Layout:...)"
            cleaned = re.sub(r'^(?:Prompt\s*)?\d+[\.\)\:\-\s]\s*', '', cleaned).strip()
            cleaned = re.sub(r'^[\-\•\*]\s+', '', cleaned).strip()
            # Remove sub-headers like "(Hero Shot Layout):"
            cleaned = re.sub(r'^\([^)]+\)\s*:?\s*', '', cleaned).strip()

            # Skip lines that are just layout labels (nothing left after stripping)
            if not cleaned:
                continue

            if cleaned.startswith(('# ', '## ', '### ', '---')):
                if current_prompt and len(current_prompt) > 30:
                    prompts.append(current_prompt.strip())
                    current_prompt = ''
                continue

            skip_starts = (
                'Here are', 'Sure,', 'Sure!', "I'll", 'These are', 'Note:', 'Remember',
                'Each prompt', 'Below are', 'Let me', 'Okay', "I've", 'The following',
                "I don't see", 'It looks like', 'However,', 'If you', 'Prompt ',
            )
            if any(cleaned.startswith(s) for s in skip_starts):
                continue

            # Strip surrounding quotes
            if len(cleaned) > 2 and cleaned[0] in '"\u201c' and cleaned[-1] in '"\u201d':
                cleaned = cleaned[1:-1].strip()

            if cleaned:
                if current_prompt:
                    current_prompt += ' ' + cleaned
                else:
                    current_prompt = cleaned

        if current_prompt and len(current_prompt) > 30:
            prompts.append(current_prompt.strip())

        prompts = [p for p in prompts if len(p) > 40]

        if len(prompts) > expected_count:
            prompts = prompts[:expected_count]

        print(f"[GeminiBot] Parsed {len(prompts)} prompts")
        for i, p in enumerate(prompts):
            print(f"  Prompt {i+1}: {p[:80]}...")
        return prompts

    # ═══════════════════════════════════════════
    # Main API
    # ═══════════════════════════════════════════

    def generate_prompts(
        self,
        image_path: str,
        content_type: str,
        count: int,
        brand_name: str = '',
        product_category: str = '',
    ) -> list[str]:
        """Generate Flow-ready prompts using Gemini vision."""
        prompt_count = math.ceil(count / 4)
        instruction = self._build_instruction(content_type, prompt_count, brand_name, product_category)

        if not self.connected:
            if not self.connect():
                return []

        try:
            self._navigate_to_gemini()
            time.sleep(2)

            if image_path and os.path.exists(image_path):
                uploaded = self._upload_image(image_path)
                if not uploaded:
                    print("[GeminiBot] Image upload failed — continuing without image")
            else:
                print(f"[GeminiBot] No image to upload: {image_path}")

            if not self._type_prompt(instruction):
                return []

            time.sleep(1)

            if not self._send_message():
                return []

            response = self._wait_for_response(timeout=90)
            if not response:
                return []

            prompts = self._parse_prompts_from_response(response, prompt_count)

            if not prompts:
                print("[GeminiBot] No prompts parsed — trying raw paragraphs")
                paragraphs = [p.strip() for p in response.split('\n\n') if len(p.strip()) > 50]
                prompts = paragraphs[:prompt_count]

            return prompts

        except Exception as e:
            print(f"[GeminiBot] Error: {e}")
            import traceback
            traceback.print_exc()
            return []

    def _build_instruction(
        self,
        content_type: str,
        prompt_count: int,
        brand_name: str = '',
        product_category: str = '',
    ) -> str:
        """Build a simple, generic instruction prompt for Gemini."""
        type_labels = {
            'a_plus': 'Amazon A+ product listing infographic designs (layouts with text, icons, benefit callouts, comparison grids, how-to-use panels)',
            'social_post': 'Instagram/Pinterest lifestyle social media posts with real-world scenes and camera details',
            'banner': 'website/ad hero banners with premium lighting and text-safe negative space',
            'lifestyle': 'editorial lifestyle photography showing the product in real-world use',
            'ad_creative': 'bold, scroll-stopping ad creatives with dramatic lighting and vivid colors',
        }

        type_desc = type_labels.get(content_type, type_labels['social_post'])

        return (
            f"Look at this product image. Write exactly {prompt_count} unique prompts "
            f"for Google Flow (an AI image generator that uses this product photo as reference)."
            f"\n\nContent type: {type_desc}"
            f"\n\nRules:"
            f"\n- NO brand names or trademarked names — describe the product visually instead"
            f"\n- Each prompt: one paragraph, 2-4 sentences"
            f"\n- Flow already has the product image — describe the scene/layout/context around it"
            f"\n- Each prompt must be unique — different angle, lighting, layout, or scene"
            f"\n- No markdown, no bullet points, no numbering, no headers, no labels"
            f"\n\nJust write {prompt_count} prompts separated by blank lines. Nothing else."
        )