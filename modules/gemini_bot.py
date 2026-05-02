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
import json
import math
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


class GeminiBot:
    """Selenium bot for Google Gemini web interface."""

    def __init__(self):
        self.driver = None
        self.connected = False

    def connect(self):
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

    def _navigate_to_gemini(self):
        """Navigate to Gemini and ensure we're on the chat page."""
        current = self.driver.current_url
        if 'gemini.google.com' not in current:
            self.driver.get('https://gemini.google.com/app')
            time.sleep(3)
        else:
            # Start new chat
            self.driver.get('https://gemini.google.com/app')
            time.sleep(3)
        print("[GeminiBot] On Gemini chat page")

    def _bring_chrome_to_front(self):
        """Bring Chrome window to foreground before pyautogui actions."""
        try:
            self.driver.switch_to.window(self.driver.current_window_handle)
            time.sleep(0.3)
            # Also maximize to ensure it's visible
            self.driver.execute_script("window.focus();")
            time.sleep(0.3)
        except Exception:
            pass

    def _upload_image(self, image_path):
        """Upload image to Gemini using the hidden file selector button."""
        abs_path = os.path.abspath(image_path)
        if not os.path.exists(abs_path):
            print(f"[GeminiBot] Image not found: {abs_path}")
            return False

        try:
            self._bring_chrome_to_front()

            # Click the hidden file image selector button directly
            self.driver.execute_script("""
                var btn = document.querySelector('button.hidden-local-file-image-selector-button');
                if (btn) {
                    btn.removeAttribute('aria-hidden');
                    btn.style.display = 'block';
                    btn.click();
                }
            """)
            print("[GeminiBot] Hidden image selector button clicked")
            time.sleep(3)

            # Native file dialog is open — paste path
            import pyautogui
            import subprocess
            subprocess.run(['clip'], input=abs_path.encode(), check=True)
            pyautogui.hotkey('ctrl', 'v')
            time.sleep(1)
            pyautogui.press('enter')
            print(f"[GeminiBot] File path pasted: {os.path.basename(abs_path)}")

            # Wait for upload
            time.sleep(8)
            print("[GeminiBot] Image uploaded!")
            return True

        except Exception as e:
            print(f"[GeminiBot] Image upload error: {e}")
            return False

    def _type_prompt(self, text):
        """Type prompt into Gemini's Quill editor."""
        try:
            self._bring_chrome_to_front()

            # Focus the editor via JavaScript
            self.driver.execute_script("""
                var editor = document.querySelector('div.ql-editor[role="textbox"]');
                if (editor) { editor.focus(); }
            """)
            time.sleep(0.5)

            # Paste text via clipboard + pyautogui
            import pyperclip
            import pyautogui
            pyperclip.copy(text)
            pyautogui.hotkey('ctrl', 'v')
            time.sleep(1)

            print(f"[GeminiBot] Prompt typed: {text[:60]}...")
            return True

        except Exception as e:
            print(f"[GeminiBot] Type error: {e}")
            return False

    def _send_message(self):
        """Click Gemini's send button (aria-label='Send message')."""
        try:
            sent = self.driver.execute_script("""
                // Exact selector: button with aria-label="Send message"
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
                # Fallback: press Enter in the editor
                editor = self.driver.find_element(By.CSS_SELECTOR, 'div.ql-editor[role="textbox"]')
                if editor:
                    from selenium.webdriver.common.keys import Keys
                    editor.send_keys(Keys.RETURN)
                    sent = 'pressed_enter'

            print(f"[GeminiBot] Send: {sent}")
            return sent != 'not_found'

        except Exception as e:
            print(f"[GeminiBot] Send error: {e}")
            return False

    def _wait_for_response(self, timeout=90):
        """Wait for Gemini to finish generating response."""
        print("[GeminiBot] Waiting for response...")
        start = time.time()
        time.sleep(5)  # Initial wait for response to start

        last_len = 0
        stable_count = 0

        while time.time() - start < timeout:
            response_text = self.driver.execute_script("""
                // Gemini model responses — try multiple selectors
                var selectors = [
                    '.model-response-text',
                    '.response-container-content',
                    '[data-message-author-role="model"] .message-content',
                    '.markdown-main-panel',
                    'message-content .model-response-text',
                    '.response-content',
                    // Angular component selectors
                    'model-response message-content',
                    '.conversation-container model-response',
                ];

                for (var sel of selectors) {
                    var els = document.querySelectorAll(sel);
                    if (els.length > 0) {
                        // Get the LAST response (most recent)
                        var last = els[els.length - 1];
                        var text = last.innerText || last.textContent || '';
                        if (text.length > 20) return text;
                    }
                }

                // Broad fallback: get all visible text after the last user message
                var allTurns = document.querySelectorAll('.conversation-container > div, .chat-history > div');
                if (allTurns.length > 0) {
                    var last = allTurns[allTurns.length - 1];
                    return last.innerText || '';
                }

                return '';
            """)

            current_len = len(response_text) if response_text else 0

            if current_len > 50 and current_len == last_len:
                stable_count += 1
                if stable_count >= 4:  # Stable for ~8 seconds
                    print(f"[GeminiBot] Response complete: {current_len} chars")
                    return response_text
            else:
                stable_count = 0

            last_len = current_len
            elapsed = int(time.time() - start)
            if elapsed % 10 == 0 and elapsed > 0:
                print(f"[GeminiBot] Generating... ({elapsed}s, {current_len} chars)")
            time.sleep(2)

        print(f"[GeminiBot] Timeout after {timeout}s — returning what we have")
        # Return whatever we have
        return self.driver.execute_script("""
            var els = document.querySelectorAll('.model-response-text, .markdown-main-panel, [data-message-author-role="model"]');
            if (els.length > 0) return els[els.length - 1].innerText || '';
            return '';
        """) or ''

    def _parse_prompts_from_response(self, response_text, expected_count):
        """Parse Flow prompts from Gemini's response text."""
        if not response_text:
            return []

        prompts = []
        lines = response_text.strip().split('\n')

        current_prompt = ''
        for line in lines:
            line = line.strip()
            if not line:
                if current_prompt and len(current_prompt) > 30:
                    prompts.append(current_prompt.strip())
                    current_prompt = ''
                continue

            # Skip headers, labels, numbering prefixes
            cleaned = line
            # Remove "Prompt 1:", "1.", "1)", etc.
            for prefix in ['Prompt ', 'prompt ', 'PROMPT ']:
                if cleaned.startswith(prefix):
                    cleaned = cleaned[len(prefix):]
                    # Remove number and colon
                    if cleaned and cleaned[0].isdigit():
                        i = 0
                        while i < len(cleaned) and (cleaned[i].isdigit() or cleaned[i] in ':.)- '):
                            i += 1
                        cleaned = cleaned[i:].strip()
                    break

            if cleaned.startswith(('# ', '## ', '### ', '**Prompt', '---')):
                if current_prompt and len(current_prompt) > 30:
                    prompts.append(current_prompt.strip())
                    current_prompt = ''
                continue

            # Remove markdown bold/italic
            cleaned = cleaned.replace('**', '').replace('*', '').replace('`', '')

            if cleaned:
                if current_prompt:
                    current_prompt += ' ' + cleaned
                else:
                    current_prompt = cleaned

        # Don't forget the last one
        if current_prompt and len(current_prompt) > 30:
            prompts.append(current_prompt.strip())

        # Filter out non-prompt text (too short or looks like instructions)
        prompts = [p for p in prompts if len(p) > 50 and not p.startswith(('Here', 'Sure', 'I\'ll', 'These', 'Note', 'Remember', 'Each'))]

        # Trim to expected count
        if len(prompts) > expected_count:
            prompts = prompts[:expected_count]

        print(f"[GeminiBot] Parsed {len(prompts)} prompts from response")
        return prompts

    # ═══════════════════════════════════════════
    # Main API
    # ═══════════════════════════════════════════

    def generate_prompts(self, image_path, content_type, count, brand_name='', product_category=''):
        """Generate Flow-ready prompts using Gemini vision.

        Args:
            image_path: Path to product reference image
            content_type: 'a_plus', 'social_post', 'banner', 'lifestyle', 'ad_creative'
            count: Total images needed (prompts = ceil(count/4))
            brand_name: Brand name for context
            product_category: Product category

        Returns:
            List of prompt strings ready for Flow
        """
        prompt_count = math.ceil(count / 4)

        # Build the Gemini instruction
        instruction = self._build_instruction(content_type, prompt_count, brand_name, product_category)

        if not self.connected:
            if not self.connect():
                print("[GeminiBot] Cannot connect to Gemini")
                return []

        try:
            # Step 1: Navigate to fresh Gemini chat
            self._navigate_to_gemini()
            time.sleep(2)

            # Step 2: Upload product image
            if image_path and os.path.exists(image_path):
                uploaded = self._upload_image(image_path)
                if not uploaded:
                    print("[GeminiBot] Image upload failed — continuing without image")
            else:
                print(f"[GeminiBot] No image to upload: {image_path}")

            # Step 3: Type the instruction prompt
            typed = self._type_prompt(instruction)
            if not typed:
                print("[GeminiBot] Failed to type prompt")
                return []

            time.sleep(1)

            # Step 4: Send
            sent = self._send_message()
            if not sent:
                print("[GeminiBot] Failed to send message")
                return []

            # Step 5: Wait for response
            response = self._wait_for_response(timeout=90)
            if not response:
                print("[GeminiBot] No response from Gemini")
                return []

            # Step 6: Parse prompts
            prompts = self._parse_prompts_from_response(response, prompt_count)

            if not prompts:
                print("[GeminiBot] No prompts parsed — returning raw response lines")
                # Last resort: split by double newline and use first N paragraphs
                paragraphs = [p.strip() for p in response.split('\n\n') if len(p.strip()) > 50]
                prompts = paragraphs[:prompt_count]

            return prompts

        except Exception as e:
            print(f"[GeminiBot] Error: {e}")
            import traceback
            traceback.print_exc()
            return []

    def _build_instruction(self, content_type, prompt_count, brand_name='', product_category=''):
        """Build the instruction prompt for Gemini based on content type."""

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
        brand_ctx = f' for the brand "{brand_name}"' if brand_name else ''
        cat_ctx = f' ({product_category} product)' if product_category else ''

        return f"""Look at this product image carefully. I need you to write exactly {prompt_count} unique prompts for Google Flow (an AI image generator that takes this product image as reference).

Content type: {type_desc}

CRITICAL RULES:
1. Do NOT use any brand names, trademarked names, or specific product names in the prompts — Flow will flag them as violations. Describe the product VISUALLY instead (e.g. "the serum bottle" not "The Ordinary Niacinamide").
2. Each prompt must be a single paragraph, 2-4 sentences.
3. Flow already has the product image as reference — describe the SCENE, LAYOUT, and CONTEXT around it.
4. Make each prompt UNIQUE — different layout, angle, lighting, or scene.
5. Do NOT include any markdown formatting, bullet points, or numbering in the prompt text itself.

Write exactly {prompt_count} prompts, each separated by a blank line. Just the prompt text, nothing else — no labels, no "Prompt 1:", no headers."""