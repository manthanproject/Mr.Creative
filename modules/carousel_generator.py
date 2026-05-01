"""
Mr.Creative Carousel Generator
Creates multi-slide Instagram carousels from pipeline images.
Each slide gets consistent brand framing, numbering, and swipe indicators.

Slide structure:
- Slide 1: Hook (bold headline, eye-catching)
- Slides 2-N-1: Content (image + caption)
- Slide N: CTA (call to action, follow/shop/link)
"""

import os
import base64
from PIL import Image
from modules.screenshot_engine import render_html_to_png


def _image_to_data_uri(image_path):
    """Convert image to base64 data URI."""
    if not image_path or not os.path.exists(image_path):
        return ''
    with open(image_path, 'rb') as f:
        b64 = base64.b64encode(f.read()).decode()
    ext = os.path.splitext(image_path)[1].lower()
    mime = {'.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.png': 'image/png',
            '.webp': 'image/webp'}.get(ext, 'image/png')
    return f'data:{mime};base64,{b64}'


def _dots_html(total, active_index, accent_color):
    """Generate swipe indicator dots HTML."""
    dots = ''
    for i in range(total):
        cls = 'dot active' if i == active_index else 'dot'
        dots += f'<span class="{cls}"></span>'
    return f'<div class="dots">{dots}</div>'


def _slide_html(content_html, slide_num, total_slides, brand_name,
                primary, secondary, accent, heading_font, body_font):
    """Wrap slide content in consistent brand frame."""
    dots = _dots_html(total_slides, slide_num - 1, accent)

    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<style>
    @import url('https://fonts.googleapis.com/css2?family={heading_font.replace(" ", "+")}:wght@400;600;700&family={body_font.replace(" ", "+")}:wght@400;500&display=swap');
    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
    body {{
        width: 1080px;
        height: 1080px;
        background: {primary};
        color: white;
        font-family: '{body_font}', sans-serif;
        overflow: hidden;
        position: relative;
    }}
    .slide-content {{
        width: 100%;
        height: 100%;
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        padding: 60px 50px 80px;
    }}
    .brand-bar {{
        position: absolute;
        top: 0;
        left: 0;
        right: 0;
        padding: 20px 30px;
        display: flex;
        justify-content: space-between;
        align-items: center;
    }}
    .brand-name {{
        font-family: '{heading_font}', sans-serif;
        font-size: 14px;
        font-weight: 600;
        letter-spacing: 3px;
        text-transform: uppercase;
        color: {accent};
    }}
    .slide-counter {{
        font-size: 13px;
        color: rgba(255,255,255,0.4);
    }}
    .dots {{
        position: absolute;
        bottom: 24px;
        left: 50%;
        transform: translateX(-50%);
        display: flex;
        gap: 6px;
    }}
    .dot {{
        width: 8px;
        height: 8px;
        border-radius: 50%;
        background: rgba(255,255,255,0.25);
    }}
    .dot.active {{
        background: {accent};
        width: 20px;
        border-radius: 4px;
    }}
    {content_html['css']}
</style></head>
<body>
    <div class="brand-bar">
        <span class="brand-name">{brand_name}</span>
        <span class="slide-counter">{slide_num}/{total_slides}</span>
    </div>
    <div class="slide-content">
        {content_html['body']}
    </div>
    {dots}
</body></html>"""


# ═══════════════════════════════════════════════
# Slide Types
# ═══════════════════════════════════════════════

def _hook_slide(headline, subheadline='', accent='#e94560', heading_font='Poppins'):
    """Slide 1: Bold hook headline."""
    return {
        'css': f"""
            .hook-headline {{
                font-family: '{heading_font}', sans-serif;
                font-size: 64px;
                font-weight: 700;
                text-align: center;
                line-height: 1.15;
                margin-bottom: 20px;
            }}
            .hook-sub {{
                font-size: 20px;
                color: rgba(255,255,255,0.6);
                text-align: center;
                max-width: 700px;
                line-height: 1.5;
            }}
            .hook-accent {{
                color: {accent};
            }}
            .hook-line {{
                width: 60px;
                height: 4px;
                background: {accent};
                margin: 24px auto;
                border-radius: 2px;
            }}
        """,
        'body': f"""
            <div class="hook-headline">{headline}</div>
            <div class="hook-line"></div>
            <div class="hook-sub">{subheadline}</div>
        """,
    }


def _content_slide(image_path, caption='', heading_font='Poppins'):
    """Middle slides: Image + caption."""
    img_uri = _image_to_data_uri(image_path)
    caption_html = f'<div class="content-caption">{caption}</div>' if caption else ''

    return {
        'css': f"""
            .content-image {{
                max-width: 700px;
                max-height: 650px;
                object-fit: contain;
                border-radius: 16px;
                filter: drop-shadow(0 10px 30px rgba(0,0,0,0.3));
            }}
            .content-caption {{
                font-family: '{heading_font}', sans-serif;
                font-size: 22px;
                font-weight: 600;
                text-align: center;
                margin-top: 24px;
                max-width: 700px;
                line-height: 1.4;
            }}
        """,
        'body': f"""
            <img class="content-image" src="{img_uri}" alt="Content">
            {caption_html}
        """,
    }


def _cta_slide(cta_text, subtext='', accent='#e94560', heading_font='Poppins'):
    """Last slide: Call to action."""
    return {
        'css': f"""
            .cta-text {{
                font-family: '{heading_font}', sans-serif;
                font-size: 48px;
                font-weight: 700;
                text-align: center;
                margin-bottom: 30px;
            }}
            .cta-button {{
                display: inline-block;
                background: {accent};
                padding: 18px 48px;
                border-radius: 12px;
                font-family: '{heading_font}', sans-serif;
                font-size: 20px;
                font-weight: 600;
                letter-spacing: 1px;
                text-transform: uppercase;
            }}
            .cta-sub {{
                font-size: 16px;
                color: rgba(255,255,255,0.5);
                margin-top: 20px;
                text-align: center;
            }}
        """,
        'body': f"""
            <div class="cta-text">{cta_text}</div>
            <div class="cta-button">Shop Now →</div>
            <div class="cta-sub">{subtext}</div>
        """,
    }


# ═══════════════════════════════════════════════
# Main Generator
# ═══════════════════════════════════════════════

def generate_carousel(
    image_paths,
    output_dir,
    brand_name='',
    hook_headline='',
    hook_subheadline='',
    captions=None,
    cta_text='',
    cta_subtext='',
    primary='#1a1a2e',
    secondary='#e94560',
    accent='#0f3460',
    heading_font='Poppins',
    body_font='Inter',
):
    """Generate a full Instagram carousel from images.

    Args:
        image_paths: List of image file paths (content slides)
        output_dir: Where to save carousel slides
        brand_name: Brand name shown on each slide
        hook_headline: Headline for first (hook) slide
        hook_subheadline: Subheadline for hook slide
        captions: List of captions per image (optional)
        cta_text: Text for final CTA slide
        cta_subtext: Subtext for CTA slide
        primary-accent: Brand colors
        heading_font, body_font: Brand fonts

    Returns:
        List of output PNG paths
    """
    os.makedirs(output_dir, exist_ok=True)

    if not captions:
        captions = [''] * len(image_paths)

    # Total slides: hook + content + CTA
    has_hook = bool(hook_headline)
    has_cta = bool(cta_text)
    total = len(image_paths) + (1 if has_hook else 0) + (1 if has_cta else 0)

    results = []
    slide_num = 0

    # Slide 1: Hook
    if has_hook:
        slide_num += 1
        content = _hook_slide(hook_headline, hook_subheadline, accent, heading_font)
        html = _slide_html(content, slide_num, total, brand_name,
                           primary, secondary, accent, heading_font, body_font)
        out = os.path.join(output_dir, f'carousel_{slide_num:02d}_hook.png')
        render_html_to_png(html, out, width=1080, height=1080)
        results.append(out)

    # Content slides
    for i, img_path in enumerate(image_paths):
        slide_num += 1
        caption = captions[i] if i < len(captions) else ''
        content = _content_slide(img_path, caption, heading_font)
        html = _slide_html(content, slide_num, total, brand_name,
                           primary, secondary, accent, heading_font, body_font)
        out = os.path.join(output_dir, f'carousel_{slide_num:02d}_content.png')
        render_html_to_png(html, out, width=1080, height=1080)
        results.append(out)

    # CTA slide
    if has_cta:
        slide_num += 1
        content = _cta_slide(cta_text, cta_subtext, accent, heading_font)
        html = _slide_html(content, slide_num, total, brand_name,
                           primary, secondary, accent, heading_font, body_font)
        out = os.path.join(output_dir, f'carousel_{slide_num:02d}_cta.png')
        render_html_to_png(html, out, width=1080, height=1080)
        results.append(out)

    print(f"[Carousel] Generated {len(results)} slides in {output_dir}")
    return results
