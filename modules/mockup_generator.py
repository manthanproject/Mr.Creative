"""
Mr.Creative Mockup Generator
Places product images into real-world mockup scenes.
Uses HTML/CSS mockup frames → Playwright screenshot for high quality.

Mockup types:
- phone: Product on phone screen (Instagram post preview)
- laptop: Product on laptop screen (website preview)
- billboard: Product on outdoor billboard
- shopping_bag: Product on branded shopping bag
- floating: Product floating with shadow on gradient background
"""

import os
import base64
from modules.screenshot_engine import render_html_to_png


def _image_to_data_uri(image_path):
    """Convert local image to base64 data URI for embedding in HTML."""
    if not image_path or not os.path.exists(image_path):
        return ''
    ext = os.path.splitext(image_path)[1].lower()
    mime = {'jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.png': 'image/png',
            '.webp': 'image/webp', '.gif': 'image/gif'}.get(ext, 'image/png')
    with open(image_path, 'rb') as f:
        b64 = base64.b64encode(f.read()).decode()
    return f'data:{mime};base64,{b64}'


def _base_html(body, width=1200, height=800, bg_color='#f5f5f5'):
    """Wrap body in minimal HTML document."""
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<style>
    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
    body {{
        width: {width}px;
        height: {height}px;
        background: {bg_color};
        display: flex;
        align-items: center;
        justify-content: center;
        font-family: 'Segoe UI', system-ui, sans-serif;
        overflow: hidden;
    }}
</style></head>
<body>{body}</body></html>"""


# ═══════════════════════════════════════════════
# Phone Mockup
# ═══════════════════════════════════════════════

def phone_mockup(product_image_path, output_path, brand_name='',
                 bg_color='#1a1a2e', accent_color='#e94560'):
    """Product displayed on a phone screen.

    Args:
        product_image_path: Path to product image
        output_path: Where to save mockup PNG
        brand_name: Optional brand name below phone
        bg_color: Background color
        accent_color: Accent color for decorative elements
    """
    img_uri = _image_to_data_uri(product_image_path)
    brand_html = f'<div class="brand">{brand_name}</div>' if brand_name else ''

    body = f"""
    <style>
        body {{ background: linear-gradient(135deg, {bg_color}, {_lighten(bg_color, 0.15)}); }}
        .scene {{ text-align: center; }}
        .phone {{
            width: 280px;
            height: 580px;
            background: #111;
            border-radius: 36px;
            padding: 12px;
            box-shadow: 0 30px 60px rgba(0,0,0,0.4), 0 0 0 2px #333;
            display: inline-block;
        }}
        .phone-screen {{
            width: 100%;
            height: 100%;
            border-radius: 24px;
            overflow: hidden;
            background: #fff;
        }}
        .phone-screen img {{
            width: 100%;
            height: 100%;
            object-fit: cover;
        }}
        .notch {{
            width: 120px;
            height: 28px;
            background: #111;
            border-radius: 0 0 16px 16px;
            margin: 0 auto;
            position: relative;
            top: 0;
            z-index: 2;
        }}
        .brand {{
            margin-top: 30px;
            font-size: 18px;
            font-weight: 600;
            color: {accent_color};
            letter-spacing: 3px;
            text-transform: uppercase;
        }}
        .dots {{
            position: absolute;
            bottom: 60px;
            left: 50%;
            transform: translateX(-50%);
        }}
        .dot {{
            display: inline-block;
            width: 8px;
            height: 8px;
            border-radius: 50%;
            background: {accent_color}60;
            margin: 0 4px;
        }}
        .dot.active {{ background: {accent_color}; width: 20px; border-radius: 4px; }}
    </style>
    <div class="scene">
        <div class="phone">
            <div class="notch"></div>
            <div class="phone-screen">
                <img src="{img_uri}" alt="Product">
            </div>
        </div>
        {brand_html}
    </div>"""

    html = _base_html(body, 800, 900, bg_color)
    return render_html_to_png(html, output_path, width=800, height=900)


# ═══════════════════════════════════════════════
# Laptop Mockup
# ═══════════════════════════════════════════════

def laptop_mockup(product_image_path, output_path, brand_name='',
                  bg_color='#f0f0f0', accent_color='#333'):
    """Product displayed on a laptop screen."""
    img_uri = _image_to_data_uri(product_image_path)
    brand_html = f'<div class="brand">{brand_name}</div>' if brand_name else ''

    body = f"""
    <style>
        body {{ background: linear-gradient(180deg, {bg_color}, #e0e0e0); }}
        .scene {{ text-align: center; }}
        .laptop {{
            display: inline-block;
        }}
        .screen-frame {{
            width: 700px;
            height: 440px;
            background: #1a1a1a;
            border-radius: 12px 12px 0 0;
            padding: 20px 20px 12px 20px;
            box-shadow: 0 -2px 20px rgba(0,0,0,0.15);
        }}
        .screen {{
            width: 100%;
            height: 100%;
            border-radius: 4px;
            overflow: hidden;
            background: #fff;
        }}
        .screen img {{
            width: 100%;
            height: 100%;
            object-fit: cover;
        }}
        .keyboard {{
            width: 800px;
            height: 16px;
            background: linear-gradient(180deg, #c0c0c0, #a0a0a0);
            border-radius: 0 0 8px 8px;
            margin: 0 auto;
        }}
        .base {{
            width: 300px;
            height: 6px;
            background: #b0b0b0;
            border-radius: 0 0 6px 6px;
            margin: 0 auto;
        }}
        .brand {{
            margin-top: 24px;
            font-size: 16px;
            font-weight: 600;
            color: {accent_color};
            letter-spacing: 2px;
            text-transform: uppercase;
        }}
    </style>
    <div class="scene">
        <div class="laptop">
            <div class="screen-frame">
                <div class="screen">
                    <img src="{img_uri}" alt="Product">
                </div>
            </div>
            <div class="keyboard"></div>
            <div class="base"></div>
        </div>
        {brand_html}
    </div>"""

    html = _base_html(body, 1000, 700, bg_color)
    return render_html_to_png(html, output_path, width=1000, height=700)


# ═══════════════════════════════════════════════
# Billboard Mockup
# ═══════════════════════════════════════════════

def billboard_mockup(product_image_path, output_path, brand_name='',
                     bg_color='#87CEEB', accent_color='#333'):
    """Product on an outdoor billboard."""
    img_uri = _image_to_data_uri(product_image_path)
    brand_html = f'<div class="brand-tag">{brand_name}</div>' if brand_name else ''

    body = f"""
    <style>
        body {{
            background: linear-gradient(180deg, {bg_color} 0%, #d4e8d0 60%, #8b9467 60%, #6b7a4a 100%);
            align-items: flex-end;
            padding-bottom: 40px;
        }}
        .billboard {{
            text-align: center;
        }}
        .board {{
            width: 700px;
            height: 350px;
            background: #222;
            border: 8px solid #555;
            border-radius: 4px;
            overflow: hidden;
            box-shadow: 0 10px 40px rgba(0,0,0,0.3);
        }}
        .board img {{
            width: 100%;
            height: 100%;
            object-fit: cover;
        }}
        .pole {{
            width: 16px;
            height: 120px;
            background: linear-gradient(90deg, #666, #888, #666);
            margin: 0 auto;
        }}
        .brand-tag {{
            position: absolute;
            bottom: 180px;
            right: 80px;
            font-size: 12px;
            color: rgba(255,255,255,0.6);
            letter-spacing: 2px;
            text-transform: uppercase;
        }}
    </style>
    <div class="billboard">
        <div class="board">
            <img src="{img_uri}" alt="Billboard">
        </div>
        <div class="pole"></div>
        {brand_html}
    </div>"""

    html = _base_html(body, 1000, 700, bg_color)
    return render_html_to_png(html, output_path, width=1000, height=700)


# ═══════════════════════════════════════════════
# Floating Product Mockup
# ═══════════════════════════════════════════════

def floating_mockup(product_image_path, output_path, brand_name='',
                    bg_color='#1a1a2e', accent_color='#e94560'):
    """Product floating with dramatic shadow on gradient background."""
    img_uri = _image_to_data_uri(product_image_path)
    brand_html = f'<div class="brand">{brand_name}</div>' if brand_name else ''

    body = f"""
    <style>
        body {{
            background: radial-gradient(ellipse at center, {_lighten(bg_color, 0.2)}, {bg_color});
        }}
        .scene {{ text-align: center; position: relative; }}
        .product {{
            max-width: 450px;
            max-height: 550px;
            object-fit: contain;
            filter: drop-shadow(0 40px 50px rgba(0,0,0,0.5));
            animation: none;
        }}
        .shadow {{
            width: 300px;
            height: 30px;
            background: radial-gradient(ellipse, rgba(0,0,0,0.3), transparent);
            border-radius: 50%;
            margin: 20px auto 0;
        }}
        .brand {{
            margin-top: 24px;
            font-size: 20px;
            font-weight: 600;
            color: {accent_color};
            letter-spacing: 4px;
            text-transform: uppercase;
        }}
        .accent-ring {{
            position: absolute;
            width: 400px;
            height: 400px;
            border: 2px solid {accent_color}20;
            border-radius: 50%;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -55%);
        }}
    </style>
    <div class="scene">
        <div class="accent-ring"></div>
        <img class="product" src="{img_uri}" alt="Product">
        <div class="shadow"></div>
        {brand_html}
    </div>"""

    html = _base_html(body, 800, 900, bg_color)
    return render_html_to_png(html, output_path, width=800, height=900)


# ═══════════════════════════════════════════════
# Mockup Registry
# ═══════════════════════════════════════════════

MOCKUP_TYPES = {
    'phone': {'func': phone_mockup, 'desc': 'Product on phone screen'},
    'laptop': {'func': laptop_mockup, 'desc': 'Product on laptop screen'},
    'billboard': {'func': billboard_mockup, 'desc': 'Product on outdoor billboard'},
    'floating': {'func': floating_mockup, 'desc': 'Floating product with shadow'},
}


def generate_mockup(mockup_type, product_image_path, output_path, **kwargs):
    """Generate a mockup by type name.

    Args:
        mockup_type: 'phone', 'laptop', 'billboard', 'floating'
        product_image_path: Path to product/content image
        output_path: Where to save the mockup PNG
        **kwargs: brand_name, bg_color, accent_color

    Returns:
        Output path on success, None on failure
    """
    entry = MOCKUP_TYPES.get(mockup_type)
    if not entry:
        print(f"[Mockup] Unknown type: {mockup_type}. Options: {list(MOCKUP_TYPES.keys())}")
        return None
    return entry['func'](product_image_path, output_path, **kwargs)


def generate_all_mockups(product_image_path, output_dir, brand_name='', **kwargs):
    """Generate all mockup types for a single product image.

    Returns:
        Dict of {type: output_path}
    """
    os.makedirs(output_dir, exist_ok=True)
    results = {}
    base = os.path.splitext(os.path.basename(product_image_path))[0]
    for mtype in MOCKUP_TYPES:
        out = os.path.join(output_dir, f'{base}_mockup_{mtype}.png')
        result = generate_mockup(mtype, product_image_path, out,
                                 brand_name=brand_name, **kwargs)
        if result:
            results[mtype] = result
    print(f"[Mockup] Generated {len(results)} mockups for {base}")
    return results


# ═══════════════════════════════════════════════
# Utility
# ═══════════════════════════════════════════════

def _lighten(hex_color, factor=0.2):
    """Lighten a hex color."""
    hex_color = hex_color.lstrip('#')
    r, g, b = int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
    r = min(255, int(r + (255 - r) * factor))
    g = min(255, int(g + (255 - g) * factor))
    b = min(255, int(b + (255 - b) * factor))
    return f'#{r:02x}{g:02x}{b:02x}'
