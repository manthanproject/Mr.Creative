"""
Mr.Creative HTML Templates
Generates branded HTML for A+ content, sale banners, and comparison cards.
Rendered to PNG via screenshot_engine.py (Playwright).

Each template takes brand_kit data + content variables → returns HTML string.
"""

import os
from typing import Optional


def _font_import(heading_font, body_font):
    """Generate Google Fonts import CSS."""
    fonts = set([heading_font, body_font])
    families = '&family='.join([f.replace(' ', '+') + ':wght@400;600;700' for f in fonts])
    return f'@import url("https://fonts.googleapis.com/css2?family={families}&display=swap");'


def _base_styles(primary, secondary, accent, heading_font, body_font):
    """Common CSS variables and reset."""
    return f"""
    <style>
        {_font_import(heading_font, body_font)}
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        :root {{
            --primary: {primary};
            --secondary: {secondary};
            --accent: {accent};
            --heading-font: '{heading_font}', sans-serif;
            --body-font: '{body_font}', sans-serif;
        }}
        body {{
            font-family: var(--body-font);
            -webkit-font-smoothing: antialiased;
        }}
    </style>"""


# ═══════════════════════════════════════════════
# Template 1: A+ Product Listing
# ═══════════════════════════════════════════════

def aplus_template(
    brand_name: str,
    product_name: str,
    tagline: str,
    features: list,  # [{"icon": "emoji", "title": "...", "desc": "..."}, ...]
    product_image_url: Optional[str] = None,
    primary: str = '#1a1a2e',
    secondary: str = '#e94560',
    accent: str = '#0f3460',
    heading_font: str = 'Poppins',
    body_font: str = 'Inter',
    width: int = 1200,
    height: int = 1600,
) -> str:
    """Amazon A+ style product listing with features grid.

    Args:
        features: List of dicts with 'icon' (emoji), 'title', 'desc'
                  Ideal: 4-6 features
    """
    features_html = ''
    for f in features[:6]:
        icon = f.get('icon', '✦')
        title = f.get('title', '')
        desc = f.get('desc', '')
        features_html += f"""
        <div class="feature-card">
            <div class="feature-icon">{icon}</div>
            <div class="feature-title">{title}</div>
            <div class="feature-desc">{desc}</div>
        </div>"""

    product_img = ''
    if product_image_url:
        product_img = f'<img src="{product_image_url}" class="product-img" alt="{product_name}">'

    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
{_base_styles(primary, secondary, accent, heading_font, body_font)}
<style>
    .container {{
        width: {width}px;
        min-height: {height}px;
        background: linear-gradient(180deg, {primary} 0%, {_lighten(primary, 0.15)} 100%);
        color: white;
        padding: 60px 50px;
        display: flex;
        flex-direction: column;
    }}
    .header {{
        text-align: center;
        margin-bottom: 40px;
    }}
    .brand-name {{
        font-family: var(--heading-font);
        font-size: 18px;
        font-weight: 600;
        letter-spacing: 3px;
        text-transform: uppercase;
        color: {accent};
        margin-bottom: 12px;
    }}
    .product-name {{
        font-family: var(--heading-font);
        font-size: 42px;
        font-weight: 700;
        line-height: 1.2;
        margin-bottom: 16px;
    }}
    .tagline {{
        font-size: 18px;
        color: rgba(255,255,255,0.75);
        max-width: 600px;
        margin: 0 auto;
        line-height: 1.5;
    }}
    .product-section {{
        text-align: center;
        margin: 40px 0;
    }}
    .product-img {{
        max-width: 350px;
        max-height: 400px;
        object-fit: contain;
        filter: drop-shadow(0 20px 40px rgba(0,0,0,0.3));
    }}
    .features-grid {{
        display: grid;
        grid-template-columns: repeat(2, 1fr);
        gap: 24px;
        margin-top: 40px;
    }}
    .feature-card {{
        background: rgba(255,255,255,0.08);
        border: 1px solid rgba(255,255,255,0.12);
        border-radius: 16px;
        padding: 28px 24px;
        text-align: center;
    }}
    .feature-icon {{
        font-size: 36px;
        margin-bottom: 12px;
    }}
    .feature-title {{
        font-family: var(--heading-font);
        font-size: 16px;
        font-weight: 600;
        margin-bottom: 8px;
    }}
    .feature-desc {{
        font-size: 13px;
        color: rgba(255,255,255,0.65);
        line-height: 1.5;
    }}
    .footer-bar {{
        margin-top: auto;
        padding-top: 30px;
        text-align: center;
        border-top: 1px solid rgba(255,255,255,0.1);
    }}
    .footer-bar span {{
        font-size: 13px;
        color: rgba(255,255,255,0.4);
        letter-spacing: 2px;
        text-transform: uppercase;
    }}
</style></head>
<body>
<div class="container">
    <div class="header">
        <div class="brand-name">{brand_name}</div>
        <div class="product-name">{product_name}</div>
        <div class="tagline">{tagline}</div>
    </div>
    <div class="product-section">{product_img}</div>
    <div class="features-grid">{features_html}</div>
    <div class="footer-bar"><span>{brand_name}</span></div>
</div>
</body></html>"""


# ═══════════════════════════════════════════════
# Template 2: Sale / Promo Banner
# ═══════════════════════════════════════════════

def sale_template(
    brand_name: str,
    headline: str,
    discount_text: str,  # e.g. "50% OFF", "FLAT ₹500 OFF"
    subheadline: str = '',
    cta_text: str = 'Shop Now',
    promo_code: str = '',
    product_image_url: Optional[str] = None,
    primary: str = '#1a1a2e',
    secondary: str = '#e94560',
    accent: str = '#0f3460',
    heading_font: str = 'Poppins',
    body_font: str = 'Inter',
    width: int = 1200,
    height: int = 628,
) -> str:
    """Sale/promo banner with discount, CTA, optional promo code."""

    promo_html = ''
    if promo_code:
        promo_html = f"""
        <div class="promo-code">
            <span class="promo-label">USE CODE</span>
            <span class="promo-value">{promo_code}</span>
        </div>"""

    product_img = ''
    if product_image_url:
        product_img = f'<img src="{product_image_url}" class="product-img" alt="Product">'

    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
{_base_styles(primary, secondary, accent, heading_font, body_font)}
<style>
    .container {{
        width: {width}px;
        height: {height}px;
        background: linear-gradient(135deg, {primary} 0%, {_darken_hex(primary, 0.2)} 100%);
        color: white;
        display: flex;
        align-items: center;
        overflow: hidden;
        position: relative;
    }}
    .accent-circle {{
        position: absolute;
        width: 500px;
        height: 500px;
        background: radial-gradient(circle, {secondary}30, transparent 70%);
        border-radius: 50%;
        right: -100px;
        top: -100px;
    }}
    .content {{
        flex: 1;
        padding: 50px 60px;
        z-index: 1;
    }}
    .brand-name {{
        font-family: var(--heading-font);
        font-size: 14px;
        font-weight: 600;
        letter-spacing: 3px;
        text-transform: uppercase;
        color: {accent};
        margin-bottom: 16px;
    }}
    .discount {{
        font-family: var(--heading-font);
        font-size: 72px;
        font-weight: 700;
        line-height: 1;
        color: {secondary};
        margin-bottom: 12px;
    }}
    .headline {{
        font-family: var(--heading-font);
        font-size: 32px;
        font-weight: 700;
        line-height: 1.2;
        margin-bottom: 12px;
    }}
    .subheadline {{
        font-size: 16px;
        color: rgba(255,255,255,0.7);
        margin-bottom: 24px;
        line-height: 1.5;
    }}
    .cta-button {{
        display: inline-block;
        background: {secondary};
        color: white;
        font-family: var(--heading-font);
        font-size: 16px;
        font-weight: 600;
        padding: 14px 36px;
        border-radius: 8px;
        text-transform: uppercase;
        letter-spacing: 1px;
    }}
    .promo-code {{
        margin-top: 20px;
        display: inline-flex;
        align-items: center;
        gap: 8px;
    }}
    .promo-label {{
        font-size: 12px;
        color: rgba(255,255,255,0.5);
        letter-spacing: 1px;
    }}
    .promo-value {{
        font-family: var(--heading-font);
        font-size: 18px;
        font-weight: 700;
        background: rgba(255,255,255,0.1);
        border: 1px dashed rgba(255,255,255,0.3);
        padding: 6px 16px;
        border-radius: 6px;
        letter-spacing: 2px;
    }}
    .product-side {{
        flex: 0 0 400px;
        display: flex;
        align-items: center;
        justify-content: center;
        padding: 40px;
        z-index: 1;
    }}
    .product-img {{
        max-width: 320px;
        max-height: 90%;
        object-fit: contain;
        filter: drop-shadow(0 15px 30px rgba(0,0,0,0.4));
    }}
</style></head>
<body>
<div class="container">
    <div class="accent-circle"></div>
    <div class="content">
        <div class="brand-name">{brand_name}</div>
        <div class="discount">{discount_text}</div>
        <div class="headline">{headline}</div>
        <div class="subheadline">{subheadline}</div>
        <div class="cta-button">{cta_text}</div>
        {promo_html}
    </div>
    <div class="product-side">{product_img}</div>
</div>
</body></html>"""


# ═══════════════════════════════════════════════
# Template 3: Comparison Card
# ═══════════════════════════════════════════════

def comparison_template(
    brand_name: str,
    headline: str,
    left_label: str,  # e.g. "Without", "Before", "Competitor"
    right_label: str,  # e.g. "With [Product]", "After", "Our Product"
    comparison_points: list,  # [{"feature": "...", "left": "...", "right": "..."}, ...]
    subheadline: str = '',
    cta_text: str = '',
    primary: str = '#1a1a2e',
    secondary: str = '#e94560',
    accent: str = '#0f3460',
    heading_font: str = 'Poppins',
    body_font: str = 'Inter',
    width: int = 1080,
    height: int = 1080,
) -> str:
    """Comparison card — product vs competitor, before/after, with/without."""

    rows_html = ''
    for point in comparison_points[:8]:
        feature = point.get('feature', '')
        left = point.get('left', '')
        right = point.get('right', '')
        rows_html += f"""
        <div class="comp-row">
            <div class="comp-left">
                <span class="comp-indicator bad">✗</span>
                <span>{left}</span>
            </div>
            <div class="comp-feature">{feature}</div>
            <div class="comp-right">
                <span class="comp-indicator good">✓</span>
                <span>{right}</span>
            </div>
        </div>"""

    cta_html = ''
    if cta_text:
        cta_html = f'<div class="cta-button">{cta_text}</div>'

    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
{_base_styles(primary, secondary, accent, heading_font, body_font)}
<style>
    .container {{
        width: {width}px;
        min-height: {height}px;
        background: {primary};
        color: white;
        padding: 50px 40px;
        display: flex;
        flex-direction: column;
    }}
    .header {{
        text-align: center;
        margin-bottom: 40px;
    }}
    .brand-name {{
        font-family: var(--heading-font);
        font-size: 14px;
        font-weight: 600;
        letter-spacing: 3px;
        text-transform: uppercase;
        color: {accent};
        margin-bottom: 12px;
    }}
    .headline {{
        font-family: var(--heading-font);
        font-size: 32px;
        font-weight: 700;
        line-height: 1.2;
        margin-bottom: 10px;
    }}
    .subheadline {{
        font-size: 15px;
        color: rgba(255,255,255,0.6);
    }}
    .comp-header {{
        display: grid;
        grid-template-columns: 1fr 140px 1fr;
        gap: 12px;
        margin-bottom: 8px;
        padding: 0 16px;
    }}
    .comp-header-label {{
        font-family: var(--heading-font);
        font-size: 14px;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 1px;
        padding: 12px 0;
    }}
    .comp-header-label.left {{
        text-align: left;
        color: rgba(255,255,255,0.5);
    }}
    .comp-header-label.center {{
        text-align: center;
        color: rgba(255,255,255,0.4);
    }}
    .comp-header-label.right {{
        text-align: right;
        color: {secondary};
    }}
    .comp-body {{
        flex: 1;
    }}
    .comp-row {{
        display: grid;
        grid-template-columns: 1fr 140px 1fr;
        gap: 12px;
        padding: 16px;
        border-bottom: 1px solid rgba(255,255,255,0.08);
        align-items: center;
    }}
    .comp-row:nth-child(even) {{
        background: rgba(255,255,255,0.03);
        border-radius: 8px;
    }}
    .comp-left {{
        display: flex;
        align-items: center;
        gap: 10px;
        font-size: 14px;
        color: rgba(255,255,255,0.55);
    }}
    .comp-feature {{
        text-align: center;
        font-family: var(--heading-font);
        font-size: 13px;
        font-weight: 600;
        color: rgba(255,255,255,0.8);
    }}
    .comp-right {{
        display: flex;
        align-items: center;
        justify-content: flex-end;
        gap: 10px;
        font-size: 14px;
        color: white;
    }}
    .comp-indicator {{
        display: inline-flex;
        align-items: center;
        justify-content: center;
        width: 22px;
        height: 22px;
        border-radius: 50%;
        font-size: 12px;
        font-weight: 700;
    }}
    .comp-indicator.bad {{
        background: rgba(255,80,80,0.2);
        color: #ff5050;
    }}
    .comp-indicator.good {{
        background: rgba(80,255,120,0.2);
        color: #50ff78;
    }}
    .footer {{
        margin-top: 30px;
        text-align: center;
    }}
    .cta-button {{
        display: inline-block;
        background: {secondary};
        color: white;
        font-family: var(--heading-font);
        font-size: 15px;
        font-weight: 600;
        padding: 14px 32px;
        border-radius: 8px;
        text-transform: uppercase;
        letter-spacing: 1px;
    }}
</style></head>
<body>
<div class="container">
    <div class="header">
        <div class="brand-name">{brand_name}</div>
        <div class="headline">{headline}</div>
        <div class="subheadline">{subheadline}</div>
    </div>
    <div class="comp-header">
        <div class="comp-header-label left">{left_label}</div>
        <div class="comp-header-label center">Feature</div>
        <div class="comp-header-label right">{right_label}</div>
    </div>
    <div class="comp-body">{rows_html}</div>
    <div class="footer">{cta_html}</div>
</div>
</body></html>"""


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


def _darken_hex(hex_color, factor=0.2):
    """Darken a hex color."""
    hex_color = hex_color.lstrip('#')
    r, g, b = int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
    r = int(r * (1 - factor))
    g = int(g * (1 - factor))
    b = int(b * (1 - factor))
    return f'#{r:02x}{g:02x}{b:02x}'


# ═══════════════════════════════════════════════
# Template Registry — used by Agent pipeline
# ═══════════════════════════════════════════════

TEMPLATE_REGISTRY = {
    'a_plus': {
        'function': aplus_template,
        'description': 'Amazon A+ style product listing with features grid',
        'default_size': (1200, 1600),
    },
    'sale_banner': {
        'function': sale_template,
        'description': 'Sale/promo banner with discount, CTA, promo code',
        'default_size': (1200, 628),
    },
    'comparison': {
        'function': comparison_template,
        'description': 'Comparison card — product vs competitor, before/after',
        'default_size': (1080, 1080),
    },
}
