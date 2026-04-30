"""
Mr.Creative — Pollinations.ai API Wrapper
Free image generation via Flux model. No API key needed.
"""

import requests
import os
import time
import urllib.parse


class PollinationsAPI:

    IMAGE_URL = 'https://image.pollinations.ai/prompt/'

    def __init__(self):
        pass

    def generate_image(self, prompt, width=1024, height=1024, seed=None, enhance=True, save_path=None):
        encoded_prompt = urllib.parse.quote(prompt)
        params = {
            'width': width,
            'height': height,
            'enhance': str(enhance).lower(),
            'nologo': 'true',
        }
        if seed is not None:
            params['seed'] = seed

        url = f"{self.IMAGE_URL}{encoded_prompt}"
        print(f"[Pollinations] Generating: {prompt[:60]}...")

        for attempt in range(3):
            try:
                resp = requests.get(url, params=params, timeout=120)
                if resp.status_code == 200 and len(resp.content) > 1000:
                    print(f"[Pollinations] Generated! Size: {len(resp.content) // 1024}KB")
                    if save_path:
                        os.makedirs(os.path.dirname(save_path), exist_ok=True)
                        with open(save_path, 'wb') as f:
                            f.write(resp.content)
                        return save_path
                    return resp.content
                else:
                    print(f"[Pollinations] Attempt {attempt+1} failed: status={resp.status_code} size={len(resp.content)}")
                    time.sleep(3)
            except requests.exceptions.Timeout:
                print(f"[Pollinations] Timeout on attempt {attempt+1}")
                time.sleep(5)
            except Exception as e:
                print(f"[Pollinations] Error: {e}")
                time.sleep(3)

        print("[Pollinations] All attempts failed")
        return None

    def generate_batch(self, prompts, width=1024, height=1024, save_dir=None, enhance=True):
        results = []
        for i, item in enumerate(prompts):
            prompt = item if isinstance(item, str) else item.get('prompt', '')
            w = item.get('width', width) if isinstance(item, dict) else width
            h = item.get('height', height) if isinstance(item, dict) else height
            filename = item.get('filename', f'gen_{i+1}.png') if isinstance(item, dict) else f'gen_{i+1}.png'

            save_path = os.path.join(save_dir, filename) if save_dir else None
            print(f"[Pollinations] Batch {i+1}/{len(prompts)}: {prompt[:40]}...")

            result = self.generate_image(prompt, w, h, enhance=enhance, save_path=save_path)
            results.append(result)

            if i < len(prompts) - 1:
                time.sleep(2)

        return results

    def test_connection(self):
        try:
            resp = requests.get(f"{self.IMAGE_URL}test", params={'width': 64, 'height': 64}, timeout=30)
            if resp.status_code == 200 and len(resp.content) > 100:
                return {'success': True, 'message': 'Pollinations.ai is reachable'}
            return {'success': False, 'message': f'Status {resp.status_code}'}
        except Exception as e:
            return {'success': False, 'message': str(e)}