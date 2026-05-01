"""
Mr.Creative Template System
Pre-built brand templates for quick content generation without the full pipeline.
Combines HTML templates + brand kit + screenshot engine for one-click generation.

Templates: sale banner, testimonial, product card, feature highlight,
           announcement, countdown, quote card, stats card.
"""

import os
import json
from modules.html_templates import sale_template, aplus_template, comparison_template, _lighten, _darken_hex
from modules.screenshot_engine import render_html_to_png


# ═══════════════════════════════════════════════
# Additional HTML Templates (beyond Sprint 2)
# ═══════════════════════════════════════════════

def testimonial_template(brand_name, quote, author, role='', rating=5,
                          primary='#1a1a2e', secondary='#e94560', accent='#0f3460',
                          heading_font='Poppins', body_font='Inter',
                          width=1080, height=1080):
    """Customer testimonial / review card."""
    stars = '★' * rating + '☆' * (5 - rating)
    role_html = f'<div class="author-role">{role}</div>' if role else ''

    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<style>
    @import url('https://fonts.googleapis.com/css2?family={heading_font.replace(" ", "+")}:wght@400;600;700&family={body_font.replace(" ", "+")}:wght@400;500&display=swap');
    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
    body {{ width: {width}px; height: {height}px; background: {primary}; color: white;
           font-family: '{body_font}', sans-serif; display: flex; align-items: center;
           justify-content: center; overflow: hidden; }}
    .card {{ text-align: center; padding: 60px 50px; max-width: 900px; }}
    .quote-mark {{ font-size: 80px; color: {accent}; line-height: 1; margin-bottom: 10px; opacity: 0.6; }}
    .quote {{ font-family: '{heading_font}', sans-serif; font-size: 28px; font-weight: 500;
              line-height: 1.5; margin-bottom: 30px; font-style: italic; }}
    .stars {{ font-size: 24px; color: #fbbf24; margin-bottom: 20px; letter-spacing: 4px; }}
    .divider {{ width: 50px; height: 3px; background: {accent}; margin: 0 auto 20px; border-radius: 2px; }}
    .author-name {{ font-family: '{heading_font}', sans-serif; font-size: 18px; font-weight: 600; }}
    .author-role {{ font-size: 14px; color: rgba(255,255,255,0.5); margin-top: 4px; }}
    .brand {{ position: absolute; bottom: 30px; left: 50%; transform: translateX(-50%);
              font-size: 12px; letter-spacing: 3px; text-transform: uppercase; color: {accent}; opacity: 0.5; }}
</style></head>
<body>
<div class="card">
    <div class="quote-mark">"</div>
    <div class="quote">{quote}</div>
    <div class="stars">{stars}</div>
    <div class="divider"></div>
    <div class="author-name">{author}</div>
    {role_html}
</div>
<div class="brand">{brand_name}</div>
</body></html>"""


def stats_template(brand_name, stats, headline='',
                    primary='#1a1a2e', secondary='#e94560', accent='#0f3460',
                    heading_font='Poppins', body_font='Inter',
                    width=1080, height=1080):
    """Stats / numbers card — show key metrics.
    stats: [{"value": "98%", "label": "Customer satisfaction"}, ...]
    """
    stats_html = ''
    for s in stats[:4]:
        stats_html += f"""
        <div class="stat">
            <div class="stat-value">{s.get('value', '')}</div>
            <div class="stat-label">{s.get('label', '')}</div>
        </div>"""

    headline_html = f'<div class="headline">{headline}</div>' if headline else ''
    cols = min(len(stats), 4)
    if cols <= 2:
        grid = f'repeat({cols}, 1fr)'
    else:
        grid = 'repeat(2, 1fr)'

    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<style>
    @import url('https://fonts.googleapis.com/css2?family={heading_font.replace(" ", "+")}:wght@400;600;700&display=swap');
    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
    body {{ width: {width}px; height: {height}px; background: {primary}; color: white;
           font-family: '{body_font}', sans-serif; display: flex; flex-direction: column;
           align-items: center; justify-content: center; overflow: hidden; padding: 60px; }}
    .headline {{ font-family: '{heading_font}', sans-serif; font-size: 36px; font-weight: 700;
                 text-align: center; margin-bottom: 50px; line-height: 1.3; }}
    .stats-grid {{ display: grid; grid-template-columns: {grid}; gap: 40px; width: 100%; max-width: 800px; }}
    .stat {{ text-align: center; padding: 30px; background: rgba(255,255,255,0.05);
             border-radius: 20px; border: 1px solid rgba(255,255,255,0.08); }}
    .stat-value {{ font-family: '{heading_font}', sans-serif; font-size: 48px; font-weight: 700;
                   color: {accent}; margin-bottom: 8px; }}
    .stat-label {{ font-size: 14px; color: rgba(255,255,255,0.6); line-height: 1.4; }}
    .brand {{ position: absolute; bottom: 30px; font-size: 12px; letter-spacing: 3px;
              text-transform: uppercase; color: rgba(255,255,255,0.3); }}
</style></head>
<body>
{headline_html}
<div class="stats-grid">{stats_html}</div>
<div class="brand">{brand_name}</div>
</body></html>"""


def announcement_template(brand_name, headline, body_text, cta_text='',
                           primary='#1a1a2e', secondary='#e94560', accent='#0f3460',
                           heading_font='Poppins', body_font='Inter',
                           width=1080, height=1080):
    """Announcement / news card."""
    cta_html = f'<div class="cta">{cta_text}</div>' if cta_text else ''

    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<style>
    @import url('https://fonts.googleapis.com/css2?family={heading_font.replace(" ", "+")}:wght@400;600;700&display=swap');
    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
    body {{ width: {width}px; height: {height}px; background: {primary}; color: white;
           font-family: '{body_font}', sans-serif; display: flex; align-items: center;
           justify-content: center; overflow: hidden; position: relative; }}
    .accent-bg {{ position: absolute; width: 600px; height: 600px;
                  background: radial-gradient(circle, {secondary}15, transparent 70%);
                  border-radius: 50%; top: -100px; right: -100px; }}
    .card {{ text-align: center; padding: 60px; z-index: 1; max-width: 850px; }}
    .badge {{ display: inline-block; background: {accent}; color: white; font-size: 12px;
              font-weight: 600; padding: 6px 16px; border-radius: 20px; letter-spacing: 2px;
              text-transform: uppercase; margin-bottom: 24px; }}
    .headline {{ font-family: '{heading_font}', sans-serif; font-size: 42px; font-weight: 700;
                 line-height: 1.2; margin-bottom: 20px; }}
    .body-text {{ font-size: 18px; color: rgba(255,255,255,0.7); line-height: 1.6; margin-bottom: 30px; }}
    .cta {{ display: inline-block; background: {secondary}; padding: 14px 36px; border-radius: 8px;
            font-family: '{heading_font}', sans-serif; font-weight: 600; font-size: 16px;
            text-transform: uppercase; letter-spacing: 1px; }}
    .brand {{ position: absolute; bottom: 30px; font-size: 12px; letter-spacing: 3px;
              text-transform: uppercase; color: rgba(255,255,255,0.3); }}
</style></head>
<body>
<div class="accent-bg"></div>
<div class="card">
    <div class="badge">New</div>
    <div class="headline">{headline}</div>
    <div class="body-text">{body_text}</div>
    {cta_html}
</div>
<div class="brand">{brand_name}</div>
</body></html>"""


# ═══════════════════════════════════════════════
# Template Registry
# ═══════════════════════════════════════════════

TEMPLATES = {
    'sale_banner': {
        'name': 'Sale Banner',
        'icon': '🏷️',
        'func': sale_template,
        'size': (1200, 628),
        'fields': ['headline', 'discount_text', 'subheadline', 'cta_text', 'promo_code'],
        'defaults': {
            'headline': 'Summer Sale',
            'discount_text': '50% OFF',
            'subheadline': 'On all imported products',
            'cta_text': 'Shop Now',
            'promo_code': '',
        },
    },
    'a_plus': {
        'name': 'A+ Product Listing',
        'icon': '📊',
        'func': aplus_template,
        'size': (1200, 1600),
        'fields': ['product_name', 'tagline', 'features'],
        'defaults': {
            'product_name': 'Product Name',
            'tagline': 'Your product tagline here',
            'features': [
                {'icon': '✦', 'title': 'Feature 1', 'desc': 'Description'},
                {'icon': '✦', 'title': 'Feature 2', 'desc': 'Description'},
                {'icon': '✦', 'title': 'Feature 3', 'desc': 'Description'},
                {'icon': '✦', 'title': 'Feature 4', 'desc': 'Description'},
            ],
        },
    },
    'comparison': {
        'name': 'Comparison Card',
        'icon': '⚖️',
        'func': comparison_template,
        'size': (1080, 1080),
        'fields': ['headline', 'left_label', 'right_label', 'comparison_points', 'cta_text'],
        'defaults': {
            'headline': 'Why Choose Us?',
            'left_label': 'Others',
            'right_label': 'Our Brand',
            'comparison_points': [
                {'feature': 'Quality', 'left': 'Average', 'right': 'Premium'},
                {'feature': 'Price', 'left': 'Expensive', 'right': 'Fair'},
                {'feature': 'Support', 'left': 'Slow', 'right': '24/7'},
            ],
            'cta_text': 'Try Now',
        },
    },
    'testimonial': {
        'name': 'Testimonial',
        'icon': '💬',
        'func': testimonial_template,
        'size': (1080, 1080),
        'fields': ['quote', 'author', 'role', 'rating'],
        'defaults': {
            'quote': 'This product changed my skincare routine completely!',
            'author': 'Happy Customer',
            'role': 'Verified Buyer',
            'rating': 5,
        },
    },
    'stats': {
        'name': 'Stats Card',
        'icon': '📈',
        'func': stats_template,
        'size': (1080, 1080),
        'fields': ['headline', 'stats'],
        'defaults': {
            'headline': 'Why Customers Love Us',
            'stats': [
                {'value': '98%', 'label': 'Customer satisfaction'},
                {'value': '50K+', 'label': 'Happy customers'},
                {'value': '4.9★', 'label': 'Average rating'},
                {'value': '24hr', 'label': 'Delivery time'},
            ],
        },
    },
    'announcement': {
        'name': 'Announcement',
        'icon': '📢',
        'func': announcement_template,
        'size': (1080, 1080),
        'fields': ['headline', 'body_text', 'cta_text'],
        'defaults': {
            'headline': 'Exciting News!',
            'body_text': 'We\'re launching something special. Stay tuned for the big reveal.',
            'cta_text': 'Learn More',
        },
    },
}


def generate_from_template(template_key, brand_kit, output_path, overrides=None):
    """Generate an image from a pre-built template.

    Args:
        template_key: Key from TEMPLATES dict
        brand_kit: BrandKit model instance (or dict with brand fields)
        output_path: Where to save the PNG
        overrides: Dict of field overrides (optional)

    Returns:
        Output path on success, None on failure
    """
    tmpl = TEMPLATES.get(template_key)
    if not tmpl:
        print(f"[Template] Unknown template: {template_key}")
        return None

    # Build kwargs from brand kit + defaults + overrides
    if hasattr(brand_kit, 'name'):
        # SQLAlchemy model
        brand_data = {
            'brand_name': brand_kit.name,
            'primary': brand_kit.primary_color or '#1a1a2e',
            'secondary': brand_kit.secondary_color or '#e94560',
            'accent': brand_kit.accent_color or '#0f3460',
            'heading_font': brand_kit.heading_font or 'Poppins',
            'body_font': brand_kit.body_font or 'Inter',
        }
    else:
        # Dict
        brand_data = {
            'brand_name': brand_kit.get('name', 'Brand'),
            'primary': brand_kit.get('primary_color', '#1a1a2e'),
            'secondary': brand_kit.get('secondary_color', '#e94560'),
            'accent': brand_kit.get('accent_color', '#0f3460'),
            'heading_font': brand_kit.get('heading_font', 'Poppins'),
            'body_font': brand_kit.get('body_font', 'Inter'),
        }

    kwargs = {**brand_data, **tmpl['defaults']}
    if overrides:
        kwargs.update(overrides)

    width, height = tmpl['size']
    kwargs['width'] = width
    kwargs['height'] = height

    # Generate HTML
    html = tmpl['func'](**kwargs)

    # Render to PNG
    return render_html_to_png(html, output_path, width=width, height=height)


def list_templates():
    """Return list of available templates with metadata."""
    return [{
        'key': k,
        'name': v['name'],
        'icon': v['icon'],
        'size': v['size'],
        'fields': v['fields'],
        'defaults': v['defaults'],
    } for k, v in TEMPLATES.items()]
