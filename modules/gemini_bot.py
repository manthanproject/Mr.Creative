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

    def _upload_image(self, image_path):
        """Upload image to Gemini chat via file input."""
        abs_path = os.path.abspath(image_path)
        if not os.path.exists(abs_path):
            print(f"[GeminiBot] Image not found: {abs_path}")
            return False

        try:
            # Look for file input element
            file_input = None

            # Method 1: Find hidden file input
            inputs = self.driver.find_elements(By.CSS_SELECTOR, 'input[type="file"]')
            if inputs:
                file_input = inputs[0]
                self.driver.execute_script("""
                    arguments[0].style.display = 'block';
                    arguments[0].style.opacity = '1';
                    arguments[0].style.position = 'fixed';
                    arguments[0].style.top = '0';
                    arguments[0].style.zIndex = '99999';
                """, file_input)
                time.sleep(0.5)
                file_input.send_keys(abs_path)
                print(f"[GeminiBot] Image uploaded via file input: {os.path.basename(abs_path)}")
                time.sleep(3)
                return True

            # Method 2: Click the add/attach button first to reveal file input
            clicked = self.driver.execute_script("""
                var btns = document.querySelectorAll('button, [role="button"]');
                for (var b of btns) {
                    if (!b.offsetParent) continue;
                    var label = (b.getAttribute('aria-label') || b.textContent || '').toLowerCase();
                    if (label.includes('add image') || label.includes('upload') || label.includes('attach') 
                        || label.includes('add file') || label.includes('add photo')) {
                        b.click();
                        return 'clicked_' + label.substring(0, 30);
                    }
                }
                // Try the + icon button
                for (var b of btns) {
                    if (!b.offsetParent) continue;
                    var text = b.textContent.trim();
                    if (text === '+' || text === 'add') {
                        b.click();
                        return 'clicked_plus';
                    }
                }
                return 'not_found';
            """)
            print(f"[GeminiBot] Attach button: {clicked}")
            time.sleep(2)

            # Now try file input again
            inputs = self.driver.find_elements(By.CSS_SELECTOR, 'input[type="file"]')
            if inputs:
                file_input = inputs[0]
                self.driver.execute_script("arguments[0].style.display='block';", file_input)
                time.sleep(0.5)
                file_input.send_keys(abs_path)
                print(f"[GeminiBot] Image uploaded after attach click: {os.path.basename(abs_path)}")
                time.sleep(3)
                return True

            print("[GeminiBot] Could not find file input for image upload")
            return False

        except Exception as e:
            print(f"[GeminiBot] Image upload error: {e}")
            return False

    def _type_prompt(self, text):
        """Type prompt into Gemini chat input."""
        try:
            # Find the chat input — could be rich text editor or textarea
            input_el = None

            # Try contenteditable div (Gemini's rich text editor)
            editors = self.driver.find_elements(By.CSS_SELECTOR, 
                'div[contenteditable="true"], div.ql-editor, [role="textbox"]')
            for ed in editors:
                if ed.is_displayed():
                    input_el = ed
                    break

            # Try textarea/input fallback
            if not input_el:
                textareas = self.driver.find_elements(By.CSS_SELECTOR, 'textarea, input[type="text"]')
                for ta in textareas:
                    if ta.is_displayed():
                        input_el = ta
                        break

            if not input_el:
                print("[GeminiBot] Could not find chat input")
                return False

            # Clear and type using clipboard paste (handles contenteditable)
            input_el.click()
            time.sleep(0.3)

            import pyperclip
            pyperclip.copy(text)
            input_el.send_keys(Keys.CONTROL, 'a')
            time.sleep(0.1)
            input_el.send_keys(Keys.CONTROL, Keys.SHIFT, 'v')
            time.sleep(0.5)

            print(f"[GeminiBot] Prompt typed: {text[:60]}...")
            return True

        except Exception as e:
            print(f"[GeminiBot] Type error: {e}")
            return False

    def _send_message(self):
        """Click send button or press Enter."""
        try:
            # Try send button
            sent = self.driver.execute_script("""
                var btns = document.querySelectorAll('button, [role="button"]');
                for (var b of btns) {
                    if (!b.offsetParent) continue;
                    var label = (b.getAttribute('aria-label') || '').toLowerCase();
                    if (label.includes('send') || label.includes('submit')) {
                        b.click();
                        return 'clicked_send';
                    }
                }
                // Try mat-icon-button with send icon
                var icons = document.querySelectorAll('mat-icon, .material-icons, [data-mat-icon-name]');
                for (var icon of icons) {
                    if (icon.textContent.trim() === 'send' || icon.textContent.trim() === 'arrow_upward') {
                        var btn = icon.closest('button');
                        if (btn) { btn.click(); return 'clicked_icon'; }
                    }
                }
                return 'not_found';
            """)

            if sent == 'not_found':
                # Fallback: press Enter
                editors = self.driver.find_elements(By.CSS_SELECTOR,
                    'div[contenteditable="true"], textarea, [role="textbox"]')
                for ed in editors:
                    if ed.is_displayed():
                        ed.send_keys(Keys.RETURN)
                        sent = 'pressed_enter'
                        break

            print(f"[GeminiBot] Send: {sent}")
            return sent != 'not_found'

        except Exception as e:
            print(f"[GeminiBot] Send error: {e}")
            return False

    def _wait_for_response(self, timeout=60):
        """Wait for Gemini to finish generating response."""
        print("[GeminiBot] Waiting for response...")
        start = time.time()

        # Wait for response to start (new model-turn div appears)
        time.sleep(5)

        # Wait for response to complete (no more streaming)
        last_len = 0
        stable_count = 0

        while time.time() - start < timeout:
            # Get the latest response text
            response_text = self.driver.execute_script("""
                // Get all model response turns
                var turns = document.querySelectorAll(
                    '.model-response-text, .response-container, ' +
                    '[data-message-author-role="model"], .message-content, ' +
                    '.markdown-main-panel, .response-content'
                );
                if (turns.length === 0) {
                    // Fallback: get all message-like divs
                    turns = document.querySelectorAll('.conversation-container > div');
                }
                if (turns.length === 0) return '';
                
                // Get the last turn's text
                var last = turns[turns.length - 1];
                return last.innerText || last.textContent || '';
            """)

            current_len = len(response_text)

            if current_len > 0 and current_len == last_len:
                stable_count += 1
                if stable_count >= 3:
                    # Response hasn't changed for 3 checks — done
                    print(f"[GeminiBot] Response complete: {current_len} chars")
                    return response_text
            else:
                stable_count = 0

            last_len = current_len
            elapsed = int(time.time() - start)
            if elapsed % 10 == 0:
                print(f"[GeminiBot] Generating... ({elapsed}s, {current_len} chars)")
            time.sleep(2)

        print(f"[GeminiBot] Timeout after {timeout}s")
        # Return whatever we have
        return self.driver.execute_script("""
            var turns = document.querySelectorAll(
                '.model-response-text, [data-message-author-role="model"], .markdown-main-panel'
            );
            if (turns.length === 0) return '';
            return turns[turns.length - 1].innerText || '';
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