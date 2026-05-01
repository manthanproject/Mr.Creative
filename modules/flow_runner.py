"""
Standalone Flow bot runner for agent pipeline.
Connects to Flow Chrome, runs a generation, returns file paths.
"""

import os
import shutil
import time
from selenium.webdriver.chrome.options import Options
from selenium import webdriver


def run_flow_batch(prompt, aspect_ratio='1:1', count=4, output_dir=None, reference_image=None):
    """Run a single Flow bot generation and return downloaded file paths.

    Args:
        prompt: Text prompt for image generation
        aspect_ratio: '1:1', '16:9', '9:16', '4:3', '3:4'
        count: Number of images (1-4)
        output_dir: Where to save final images
        reference_image: Optional path to reference image

    Returns:
        List of file paths to generated images
    """
    from modules.chrome_launcher import ensure_flow_chrome
    from modules.flow_bot import FlowBot

    # Ensure Chrome is running with the right profile
    if not ensure_flow_chrome('crimsonbox69@gmail.com'):
        print("[FlowRunner] Could not launch Flow Chrome")
        return []

    # Connect to Chrome
    opts = Options()
    opts.add_experimental_option('debuggerAddress', '127.0.0.1:9223')

    driver = None
    try:
        driver = webdriver.Chrome(options=opts)
        driver.set_script_timeout(120)

        download_dir = os.path.expanduser('~/Downloads')

        # Create bot and run
        bot = FlowBot(driver, download_dir=download_dir)

        # Map aspect ratios to Flow format
        ar_map = {
            '1:1': 'square',
            '16:9': 'landscape',
            '9:16': 'portrait',
            '4:3': 'landscape',
            '3:4': 'portrait',
            '4:5': 'portrait',
        }
        flow_ar = ar_map.get(aspect_ratio, 'square')

        result = bot.generate_banners(
            prompt=prompt,
            aspect_ratio=flow_ar,
            count=min(count, 4),
            image_path=reference_image,
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

        print(f"[FlowRunner] Batch done: {len(final_files)} images")
        return final_files

    except Exception as e:
        print(f"[FlowRunner] Error: {e}")
        import traceback
        traceback.print_exc()
        return []

    finally:
        if driver:
            try:
                driver.quit()
                print("[FlowRunner] ChromeDriver session closed — Chrome stays alive")
            except Exception:
                pass
