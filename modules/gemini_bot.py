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
        """
        abs_path = os.path.abspath(image_path)
        if not os.path.exists(abs_path):
            print(f"[GeminiBot] Image not found: {abs_path}")
            return False

        drv = self._drv()

        try:
            # Step 1: Click the + button in the input toolbar
            clicked_plus = drv.execute_script("""
                var editor = document.querySelector('div.ql-editor');
                if (!editor) return 'no_editor';

                // Walk up from editor to find the input container with the + button
                var container = editor;
                for (var i = 0; i < 10; i++) {
                    container = container.parentElement;
                    if (!container) break;
                    var btns = container.querySelectorAll('button, [role="button"]');
                    for (var b of btns) {
                        if (!b.offsetParent) continue;
                        var r = b.getBoundingClientRect();
                        // + button: small, near bottom-left, has an icon child
                        if (r.width < 60 && r.height < 60 && r.x < 200) {
                            var hasIcon = b.querySelector('mat-icon, svg, gem-icon');
                            if (hasIcon) {
                                b.click();
                                return 'clicked_at_' + Math.round(r.x) + ',' + Math.round(r.y);
                            }
                        }
                    }
                }

                // Fallback: any small button in bottom-left of viewport
                var allBtns = document.querySelectorAll('button');
                for (var b of allBtns) {
                    if (!b.offsetParent) continue;
                    var r = b.getBoundingClientRect();
                    if (r.y > window.innerHeight - 200 && r.x < 150 && r.width < 60) {
                        b.click();
                        return 'fallback_at_' + Math.round(r.x) + ',' + Math.round(r.y);
                    }
                }
                return 'not_found';
            """)
            print(f"[GeminiBot] Plus button: {clicked_plus}")

            if clicked_plus in ('not_found', 'no_editor'):
                # Last resort: click at estimated position relative to editor
                try:
                    editor_el = drv.find_element(By.CSS_SELECTOR, 'div.ql-editor')
                    actions = ActionChains(drv)
                    actions.move_to_element_with_offset(editor_el, -350, 50)
                    actions.click()
                    actions.perform()
                    print("[GeminiBot] Clicked at estimated + position")
                except Exception:
                    print("[GeminiBot] Could not click + button at all")
                    return False

            time.sleep(2)

            # Step 2: Click "Upload files" from dropdown menu
            clicked_upload = drv.execute_script("""
                var items = document.querySelectorAll(
                    'button, [role="menuitem"], [role="option"], .mat-mdc-list-item'
                );
                for (var item of items) {
                    if (!item.offsetParent) continue;
                    var label = item.getAttribute('aria-label') || '';
                    var text = (item.textContent || '').trim();
                    if (label.includes('Upload files') || text === 'Upload files'
                        || text.startsWith('Upload files')) {
                        item.click();
                        return 'clicked';
                    }
                }
                return 'not_found';
            """)
            print(f"[GeminiBot] Upload files menu: {clicked_upload}")

            if clicked_upload == 'not_found':
                print("[GeminiBot] 'Upload files' menu item not found")
                return False

            # Step 3: Wait for native file dialog to open (auto-focuses on Windows)
            time.sleep(3)

            # Step 4: Paste file path in the dialog and press Enter
            import pyautogui
            subprocess.run(['clip'], input=abs_path.encode(), check=True)
            pyautogui.hotkey('ctrl', 'a')
            time.sleep(0.3)
            pyautogui.hotkey('ctrl', 'v')
            time.sleep(1)
            pyautogui.press('enter')
            print(f"[GeminiBot] File selected: {os.path.basename(abs_path)}")

            # Step 5: Wait for upload to finish
            time.sleep(8)

            # Step 6: Verify thumbnail appeared
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
                var editor = document.querySelector('div.ql-editor[role="textbox"]');
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
                var btns = document.querySelectorAll('button');
                for (var b of btns) {
                    if (!b.offsetParent) continue;
                    var label = b.getAttribute('aria-label') || '';
                    if (label === 'Send message') {
                        b.click();
                        return 'clicked_send';
                    }
                }
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
                var selectors = [
                    '.model-response-text',
                    '.response-container-content',
                    '[data-message-author-role="model"] .message-content',
                    '.markdown-main-panel',
                    'model-response message-content',
                    '.response-content',
                ];
                for (var sel of selectors) {
                    var els = document.querySelectorAll(sel);
                    if (els.length > 0) {
                        var last = els[els.length - 1];
                        var text = last.innerText || last.textContent || '';
                        if (text.length > 20) return text;
                    }
                }
                var allTurns = document.querySelectorAll(
                    '.conversation-container > div, .chat-history > div'
                );
                if (allTurns.length > 0) {
                    return allTurns[allTurns.length - 1].innerText || '';
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
            var els = document.querySelectorAll(
                '.model-response-text, .markdown-main-panel, [data-message-author-role="model"]'
            );
            if (els.length > 0) return els[els.length - 1].innerText || '';
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

            # Remove numbered prefixes
            cleaned = re.sub(r'^(?:Prompt\s*)?\d+[\.\)\:\-]\s*', '', cleaned).strip()
            cleaned = re.sub(r'^[\-\•\*]\s+', '', cleaned).strip()
            # Remove sub-headers like "(Hero Shot Layout):"
            cleaned = re.sub(r'^\([^)]+\)\s*:?\s*', '', cleaned).strip()

            if cleaned.startswith(('# ', '## ', '### ', '---')):
                if current_prompt and len(current_prompt) > 30:
                    prompts.append(current_prompt.strip())
                    current_prompt = ''
                continue

            skip_starts = (
                'Here are', 'Sure,', 'Sure!', "I'll", 'These are', 'Note:', 'Remember',
                'Each prompt', 'Below are', 'Let me', 'Okay', "I've", 'The following',
                "I don't see", 'It looks like', 'However,', 'If you',
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
        """Build the instruction prompt for Gemini."""
        type_instructions = {
            'a_plus': (
                'Amazon A+ product listing infographic designs. Each prompt should describe a DIFFERENT layout:\n'
                '- Hero shot with bold heading, bullet points, and award badge\n'
                '- Multi-panel grid (2x2) with how-to-use steps, before/after, benefits\n'
                '- Comparison chart showing product vs generic alternatives with checkmarks\n'
                '- Feature benefits grid with icons and short descriptions\n'
                '- Product in hand showing real size with bold text overlay\n'
                '- Full page infographic combining hero, steps, and results\n'
                'These are DESIGNED INFOGRAPHIC IMAGES with text, icons, and data layouts — NOT just photography.'
            ),
            'social_post': (
                'Instagram/Pinterest lifestyle social media posts. Each prompt should describe a DIFFERENT scene:\n'
                '- Candid product usage at bathroom vanity with morning light\n'
                '- Flat lay on bedsheets/marble with props (coffee, book, flowers)\n'
                '- Shelfie on bathroom shelf with other products\n'
                '- Product in cosmetic bag or daily carry context\n'
                '- Evening routine with candles and warm lighting\n'
                'Include specific camera (Canon, Sony, Fuji), lens, aperture, and lighting details.'
            ),
            'banner': (
                'Website/ad hero banners with text-safe negative space. Each prompt should describe:\n'
                '- Product on premium surface (marble, concrete, wood) with space for text\n'
                '- Dramatic studio lighting with single spotlight\n'
                '- Product floating with shadow on clean background\n'
                '- Wide format with product on one side, text space on other\n'
                'Include camera specs and studio lighting setup details.'
            ),
            'lifestyle': (
                'Documentary-style editorial lifestyle photography. Each prompt should describe:\n'
                '- Person using product in real-world setting (bathroom, kitchen, gym)\n'
                '- Travel context (hotel, airport, on-the-go)\n'
                '- Morning/evening routine moments\n'
                '- Candid, unposed, authentic situations\n'
                'Include camera (Fuji, Leica), natural lighting, and environmental details.'
            ),
            'ad_creative': (
                'Bold, scroll-stopping Meta/Google ad creatives. Each prompt should describe:\n'
                '- Dynamic splash/action shot with the product\n'
                '- Neon rim lighting on dark reflective surface\n'
                '- Bold color contrast backgrounds (electric pink, yellow, orange)\n'
                '- Surreal/elevated product placement\n'
                'Include dramatic lighting, high contrast, and commercial photography specs.'
            ),
        }

        type_desc = type_instructions.get(content_type, type_instructions['social_post'])

        return (
            f"Look at this product image carefully. I need you to write exactly {prompt_count} "
            f"unique prompts for Google Flow (an AI image generator that takes this product image as reference)."
            f"\n\nContent type: {type_desc}"
            f"\n\nCRITICAL RULES:"
            f"\n1. Do NOT use any brand names, trademarked names, or specific product names in the prompts "
            f"— Flow will flag them as violations. Describe the product VISUALLY instead "
            f'(e.g. "the serum bottle" not "The Ordinary Niacinamide").'
            f"\n2. Each prompt must be a single paragraph, 2-4 sentences."
            f"\n3. Flow already has the product image as reference — describe the SCENE, LAYOUT, and CONTEXT around it."
            f"\n4. Make each prompt UNIQUE — different layout, angle, lighting, or scene."
            f"\n5. Do NOT include any markdown formatting, bullet points, or numbering in the prompt text itself."
            f"\n\nWrite exactly {prompt_count} prompts, each separated by a blank line. "
            f"Just the prompt text, nothing else — no labels, no \"Prompt 1:\", no headers."
        )