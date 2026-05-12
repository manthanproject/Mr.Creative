"""
A+ Listing Prompt Generator
Generates 8 prompts one at a time via Gemini — no JSON parsing issues.
"""

import logging
logger = logging.getLogger('aplus')

PROMPT_SPECS = [
    {'id': 'hero', 'name': 'Hero Image', 'instruction': 'Product centered on pure white seamless background, soft shadow beneath, no text, no graphics, best angle showing full detail. Sharp focus on every texture and detail.'},
    {'id': 'features', 'name': 'Key Features Infographic', 'instruction': 'Product on one side, 4-5 feature callouts with minimal icons and bold headlines on the other side. Write the ACTUAL feature titles and one-line descriptions. Color-block layout.'},
    {'id': 'howto', 'name': 'How To Use', 'instruction': '3-4 numbered steps showing product usage/application. Write ACTUAL step titles and instructions. Clean instructional infographic layout.'},
    {'id': 'dimensions', 'name': 'Size & Dimensions', 'instruction': 'Product centered with measurement lines showing actual dimensions. Technical infographic. Show size reference comparisons.'},
    {'id': 'comparison', 'name': 'Comparison Chart', 'instruction': 'Table comparing this product vs 2 generic competitors. Write ACTUAL feature comparison rows with checkmarks and crosses. Product wins all categories.'},
    {'id': 'lifestyle', 'name': 'Lifestyle Image', 'instruction': 'Target audience using the product in real-world context. Modern setting, editorial photography, shallow depth of field. Product is focal point. Headline overlay.'},
    {'id': 'multiuse', 'name': 'Multi-Use Versatility', 'instruction': 'Product shown in 4-6 different use cases or surfaces. Structured grid collage with equal spacing. Each context labeled.'},
    {'id': 'trust', 'name': 'Trust & Quality Badges', 'instruction': 'Product centered with 6 quality/trust badge seals arranged around it. Write the badge texts. Clean premium layout.'},
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

    primary = colors.get('primary', '#FFFFFF')
    secondary = colors.get('secondary', '#D4AF37')
    accent = colors.get('accent', '#000000')
    features_str = ', '.join(features) if features else 'Premium, Durable, Versatile'

    base_context = (
        f"Product: {name} | Category: {category} | Size: {dimensions} | "
        f"Features: {features_str} | Audience: {audience} | Brand: {brand} | USP: {usp} | "
        f"Style: {style_notes or 'Premium commercial, natural product photography'}"
    )

    results = []
    for spec in PROMPT_SPECS:
        try:
            ask = (
                f"You are a premium Amazon listing image prompt engineer. "
                f"Write ONE detailed AI image generation prompt (150-250 words) for: {spec['name']}.\n\n"
                f"PRODUCT: {base_context}\n\n"
                f"IMAGE TYPE: {spec['instruction']}\n\n"
                f"RULES: Ultra photorealistic, 12K UHD, professional 3-point studio lighting, "
                f"85mm prime lens f/8 ISO 100. "
                f"Clean professional layout. NO color blocks, NO hex codes, NO forced color palette. "
                f"Let the AI decide natural colors based on the product. NO gradients NO clutter NO cartoonish. "
                f"Write ALL text/headlines that should appear in the image. "
                f"Include negative prompt at end.\n\n"
                f"Return ONLY the prompt text, nothing else. No markdown, no labels, no explanations."
            )
            result = call_llm(ask, temperature=0.7, max_tokens=800)
            if result and len(result.strip()) > 50:
                results.append({
                    'id': spec['id'],
                    'name': spec['name'],
                    'prompt': result.strip(),
                })
                logger.info(f"[A+ Prompts] Generated: {spec['name']}")
            else:
                raise ValueError("Empty or too short")
        except Exception as e:
            logger.warning(f"[A+ Prompts] {spec['name']} failed: {e}, using fallback")
            results.append({
                'id': spec['id'],
                'name': spec['name'],
                'prompt': _single_fallback(spec, product_info),
            })

    return results


def _single_fallback(spec, info):
    name = info.get('product_name', 'Product')
    brand = info.get('brand_name', 'Brand')
    colors = info.get('color_palette', {})
    p = colors.get('primary', '#FFFFFF')
    s = colors.get('secondary', '#D4AF37')
    return (
        f"Ultra photorealistic product photography, 12K UHD, HDR balanced, "
        f"studio lighting, {p} and {s} palette, Montserrat typography. "
        f"{spec['instruction']} Product: {name}. Brand: {brand}. "
        f"No gradients, no clutter, no cartoonish rendering."
    )
