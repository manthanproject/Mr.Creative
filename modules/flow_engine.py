"""
Mr.Creative — Flow Engine (HuggingFace InferenceClient — FREE)
Model: FLUX.1-schnell via hf-inference provider
"""

import os
import io
import datetime
from huggingface_hub import InferenceClient

ASPECT_RATIOS = {
    'story':     {'label': 'Story (9:16)',     'width': 768,  'height': 1344},
    'square':    {'label': 'Square (1:1)',      'width': 1024, 'height': 1024},
    'landscape': {'label': 'Landscape (16:9)',  'width': 1344, 'height': 768},
    'feed':      {'label': 'Feed (4:5)',        'width': 896,  'height': 1152},
    'wide':      {'label': 'Wide (4:1)',        'width': 1344, 'height': 384},
}


def _generate_single_image(api_key, prompt, aspect_ratio='landscape', variation_index=0):
    try:
        client = InferenceClient(
            provider="hf-inference",
            api_key=api_key,
        )
        ar_info = ASPECT_RATIOS.get(aspect_ratio, ASPECT_RATIOS['landscape'])
        full_prompt = f"{prompt}, variation {variation_index + 1}, unique creative interpretation, high quality, professional"

        image = client.text_to_image(
            full_prompt,
            model="black-forest-labs/FLUX.1-schnell",
            width=ar_info['width'],
            height=ar_info['height'],
        )

        # image is a PIL.Image object
        buf = io.BytesIO()
        image.save(buf, format='PNG')
        image_bytes = buf.getvalue()

        return {
            'success': True,
            'image_data': image_bytes,
            'extension': 'png',
            'variation': variation_index,
        }
    except Exception as e:
        return {'success': False, 'error': str(e)[:200], 'variation': variation_index}


def generate_banners(prompt, aspect_ratio='landscape', count=4,
                     output_dir=None, collection_id=None, api_key=None, **kwargs):
    results = {'success': False, 'images': [], 'errors': []}

    if not api_key:
        results['errors'].append('No HuggingFace API key configured')
        return results

    for i in range(count):
        result = _generate_single_image(api_key, prompt, aspect_ratio, i)
        if result['success']:
            ts = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"banner_{ts}_{result['variation']+1}.{result['extension']}"

            if output_dir:
                os.makedirs(output_dir, exist_ok=True)
                filepath = os.path.join(output_dir, filename)
                with open(filepath, 'wb') as f:
                    f.write(result['image_data'])
                results['images'].append({
                    'filename': filename,
                    'path': filepath,
                    'size': len(result['image_data']),
                    'variation': result['variation'],
                })
        else:
            results['errors'].append(f"Image {result['variation']+1}: {result['error']}")

    results['success'] = len(results['images']) > 0
    return results
