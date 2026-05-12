"""
A+ Listing Prompt Generator
Input: product details -> Gemini generates 8 detailed image prompts -> ready for Flow
"""

import json
import logging

logger = logging.getLogger('aplus')

PROMPT_TYPES = [
    {'id': 'hero', 'name': 'Hero Image'},
    {'id': 'features', 'name': 'Key Features Infographic'},
    {'id': 'howto', 'name': 'How To Use'},
    {'id': 'dimensions', 'name': 'Size & Dimensions'},
    {'id': 'comparison', 'name': 'Comparison Chart'},
    {'id': 'lifestyle', 'name': 'Lifestyle Image'},
    {'id': 'multiuse', 'name': 'Multi-Use Versatility'},
    {'id': 'trust', 'name': 'Trust & Quality Badges'},
]


def generate_listing_prompts(product_info):
    from modules.night_orchestrator.llm import call_llm

    name = product_info.get('product_name', 'Product')
    category = product_info.get('category', 'General')
    dimensions = product_info.get('dimensions', 'Standard size')
    features = product_info.get('features', [])
    audience = product_info.get('target_audience', 'Adults 18-35')
    brand = product_info.get('brand_name', 'Premium Brand')
    usp = product_info.get('usp', 'Premium quality')
    colors = product_info.get('color_palette', {})
    style_notes = product_info.get('style_notes', '')

    primary_color = colors.get('primary', '#FFFFFF')
    secondary_color = colors.get('secondary', '#D4AF37')
    accent_color = colors.get('accent', '#000000')
    features_str = ', '.join(features) if features else 'Premium quality, Durable, Versatile'

    mega_prompt = f"""You are a world-class Amazon product listing image prompt engineer. Generate exactly 8 separate AI image generation prompts for this product.

PRODUCT DETAILS:
- Product: {name}
- Category: {category}
- Dimensions: {dimensions}
- Key Features: {features_str}
- Target Audience: {audience}
- Brand: {brand}
- USP: {usp}
- Color Palette: Primary {primary_color}, Secondary {secondary_color}, Accent {accent_color}
- Style Notes: {style_notes or 'Premium commercial quality'}

RULES FOR EVERY PROMPT:
- Ultra photorealistic, 12K UHD, HDR balanced, razor-sharp focus
- Professional 3-point studio lighting (softbox + fill + rim)
- Camera: full-frame DSLR, 85mm prime, f/8, ISO 100
- Typography: Bold uppercase geometric sans-serif (Montserrat/Gotham style)
- Use the EXACT color palette hex codes given above
- Clean geometric color-block layouts, strong spacing
- NO gradients, NO clutter, NO cartoonish rendering, NO watermarks
- Each prompt must be 150-250 words, completely self-contained
- Write ALL text/headlines/subtext that should appear in the image
- Negative: no blur, no low-quality, no messy typography, no gradients

Return ONLY a JSON array with exactly 8 objects (no markdown, no backticks):
[
  {{"id": "hero", "name": "Hero Image", "prompt": "full prompt text here..."}},
  {{"id": "features", "name": "Key Features Infographic", "prompt": "full prompt text..."}},
  {{"id": "howto", "name": "How To Use", "prompt": "full prompt text..."}},
  {{"id": "dimensions", "name": "Size & Dimensions", "prompt": "full prompt text..."}},
  {{"id": "comparison", "name": "Comparison Chart", "prompt": "full prompt text..."}},
  {{"id": "lifestyle", "name": "Lifestyle Image", "prompt": "full prompt text..."}},
  {{"id": "multiuse", "name": "Multi-Use Versatility", "prompt": "full prompt text..."}},
  {{"id": "trust", "name": "Trust & Quality Badges", "prompt": "full prompt text..."}}
]

PROMPT 1 (hero): Product centered on white background, soft shadow, no text, best angle, sharp detail.
PROMPT 2 (features): Product on one side, 4-5 feature callouts with icons + text. Write ACTUAL feature text.
PROMPT 3 (howto): 3-4 numbered usage steps. Write ACTUAL step titles and instructions.
PROMPT 4 (dimensions): Product with measurement lines showing actual dimensions.
PROMPT 5 (comparison): Table comparing product vs 2 competitors. Write ACTUAL comparison rows.
PROMPT 6 (lifestyle): Target audience using product. Editorial photography. Headline overlay.
PROMPT 7 (multiuse): Product in 4-6 use cases. Structured grid. Each labeled.
PROMPT 8 (trust): Product centered with 6 quality/trust badges. Write badge texts.

Make each prompt hyper-detailed and specific to THIS product."""

    try:
        result = call_llm(mega_prompt, temperature=0.7, max_tokens=4000)
        result = result.strip()
        if result.startswith('`'):
            lines = result.split(chr(10))
            if lines[0].strip().startswith('`'):
                lines = lines[1:]
            if lines and lines[-1].strip().startswith('`'):
                lines = lines[:-1]
            result = chr(10).join(lines)
        prompts = json.loads(result)
        if isinstance(prompts, list) and len(prompts) >= 1:
            return prompts
        raise ValueError("Expected list")
    except Exception as e:
        logger.error(f"[A+ Prompts] Error: {e}")
        return _fallback_prompts(product_info)


def _fallback_prompts(product_info):
    name = product_info.get('product_name', 'Product')
    brand = product_info.get('brand_name', 'Brand')
    features = product_info.get('features', ['Premium Quality', 'Durable', 'Versatile'])
    colors = product_info.get('color_palette', {})
    primary = colors.get('primary', '#FFFFFF')
    secondary = colors.get('secondary', '#D4AF37')
    base = f"Ultra photorealistic professional product photography, 12K UHD, HDR balanced, studio lighting, {primary} and {secondary} color palette, Montserrat typography, no gradients, no clutter."
    return [
        {'id': 'hero', 'name': 'Hero Image', 'prompt': f'{base} {name} centered on pure white background, soft shadow, sharp detail, no text.'},
        {'id': 'features', 'name': 'Key Features', 'prompt': f'{base} Infographic for {name}. Product left, 4 features right: {", ".join(features[:4])}. Brand: {brand}.'},
        {'id': 'howto', 'name': 'How To Use', 'prompt': f'{base} 3-step usage guide for {name}. Numbered steps. Headline: HOW TO USE. Brand: {brand}.'},
        {'id': 'dimensions', 'name': 'Size & Dimensions', 'prompt': f'{base} Dimension infographic for {name}. Measurement lines. {product_info.get("dimensions", "")}. Brand: {brand}.'},
        {'id': 'comparison', 'name': 'Comparison Chart', 'prompt': f'{base} Comparison table for {name} vs competitors. 5 rows. Checkmarks/crosses. Brand: {brand}.'},
        {'id': 'lifestyle', 'name': 'Lifestyle Image', 'prompt': f'{base} Lifestyle photo using {name}. Modern setting. Headline: MADE FOR YOUR LIFESTYLE. Brand: {brand}.'},
        {'id': 'multiuse', 'name': 'Multi-Use', 'prompt': f'{base} {name} in 4 use contexts. Grid collage. Headline: STYLE IT YOUR WAY. Brand: {brand}.'},
        {'id': 'trust', 'name': 'Trust Badges', 'prompt': f'{base} {name} with 6 quality badges. Headline: CRAFTED WITH PRECISION. Brand: {brand}.'},
    ]
