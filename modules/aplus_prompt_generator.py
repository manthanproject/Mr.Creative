"""
A+ Listing Prompt Generator
Upload product image to Gemini + one mega-prompt → N unique Flow-ready prompts
Premium prompt style: dense comma-separated descriptors with cinematic themed backgrounds
"""

import logging
logger = logging.getLogger('aplus')


PROMPT_TYPES = {
    1: ['hero'],
    2: ['hero', 'detail'],
    3: ['hero', 'detail', 'application'],
    4: ['hero', 'detail', 'application', 'durability'],
    5: ['hero', 'detail', 'application', 'durability', 'lifestyle_collage'],
    6: ['hero', 'detail', 'application', 'durability', 'lifestyle_collage', 'dimensions'],
    7: ['hero', 'detail', 'application', 'durability', 'lifestyle_collage', 'dimensions', 'build_quality'],
    8: ['hero', 'detail', 'application', 'durability', 'lifestyle_collage', 'dimensions', 'build_quality', 'lifestyle_banner'],
}

TYPE_DESCRIPTIONS = {
    'hero': 'PREMIUM HERO BANNER — Centered product with cinematic themed background, atmospheric effects, clean color palette, bold modern typography, ultra sharp product texture, realistic soft shadows, centered product dominance, studio lighting',
    'detail': 'DETAIL CLOSE-UP — Extreme close-up showing product texture/material quality, zoom detail circles highlighting craftsmanship, headline about quality/precision, cinematic themed background, macro photography style',
    'application': 'HOW TO USE / APPLY — Product being used/applied in realistic scenario, realistic interaction effects, headline about ease of use, minimal split layout, cinematic themed background',
    'durability': 'DURABILITY / SECURE HOLD — Product demonstrating strength/durability/quality, macro zoom circles showing build quality, headline about lasting quality, cinematic themed background',
    'lifestyle_collage': 'EVERYDAY STYLE COLLAGE — Product showcased in multiple real-world applications, floating collage arrangement on different surfaces/items, headline about versatility, premium icon section with feature badges',
    'dimensions': 'SIZE & DIMENSIONS — Product with clean measurement arrows showing actual dimensions, technical infographic style, cinematic themed background, bold modern typography',
    'build_quality': 'THICK PREMIUM BUILD — Angled side profile showing product depth/thickness/layers, zoom circles highlighting dense construction, headline about premium build quality',
    'lifestyle_banner': 'LIFESTYLE BANNER — Stylish people using/wearing product in different ways, cinematic themed background, editorial fashion aesthetic, headline about style versatility',
}


def build_mega_prompt(count, brand_info=None):
    """Build one mega-prompt that asks Gemini for N unique image prompts."""
    types = PROMPT_TYPES.get(min(count, 8), PROMPT_TYPES[8])
    while len(types) < count:
        types.append(types[len(types) % 8])

    type_list = ""
    for i, t in enumerate(types[:count]):
        desc = TYPE_DESCRIPTIONS.get(t, t)
        type_list += f"\nPROMPT {i+1} — {desc}"

    brand_context = ""
    if brand_info:
        name = brand_info.get('product_name', '')
        features = brand_info.get('features', [])
        if name:
            brand_context = f"\nProduct: {name}"
        if features:
            brand_context += f"\nFeatures: {', '.join(features)}"

    prompt = f"""Look at this product image carefully. You are an ultra-premium Amazon listing image prompt engineer.

Generate exactly {count} unique AI image generation prompts for this product's Amazon A+ listing.
{brand_context}

STYLE RULES — FOLLOW THIS EXACT FORMAT:
Each prompt must be a SINGLE DENSE PARAGRAPH of comma-separated descriptors (NOT sentences). Study this example:

"Premium Amazon infographic design for [product type], centered [describe product in detail] with ultra realistic texture, cinematic soft-focus [themed] background with [atmospheric effects like fog, smoke, energy glow], clean [color] palette with soft accents, abstract energy wave shapes, bold modern typography, headline "[HEADLINE TEXT]", subtext "[SUBTEXT]", hyper detailed texture, realistic shadows beneath product, modern editorial composition, centered product dominance, studio lighting, professional Amazon listing image, Canon EOS R5 photography style, 85mm lens, HDR balanced rendering, masterpiece, best quality, ultra photorealistic 12K rendering, square format, clean minimal layout

Negative prompt: blur, clutter, [specific negatives], watermark, cartoonish render, low quality"

CRITICAL RULES:
1. Each prompt is ONE dense paragraph — NO line breaks, NO bullet points, just comma-separated descriptors
2. DESCRIBE THE EXACT PRODUCT you see in the image — its shape, colors, text on labels, branding, materials, every visual detail so the AI reproduces it faithfully
3. Include CINEMATIC THEMED BACKGROUNDS related to the product's category (atmospheric fog, energy effects, themed environments matching the product's world/aesthetic)
4. Include SPECIFIC TYPOGRAPHY in quotes — actual headline and subtext (e.g., headline "PRECISION CRAFTED", subtext "PREMIUM QUALITY MATERIALS")
5. Include camera specs: Canon EOS R5, 85mm lens, HDR balanced rendering
6. Include quality tags: masterpiece, best quality, ultra photorealistic 12K rendering
7. End EACH prompt with a separate line starting with "Negative prompt:" followed by relevant negatives
8. Each prompt must be 150-300 words (the dense paragraph + negative prompt)
9. For infographic types include: zoom detail circles, measurement arrows, feature icon sections, headline/subtext typography as appropriate
10. Make backgrounds CINEMATIC and THEMED — not just plain white. Use atmospheric effects, soft-focus themed environments, abstract energy shapes, fog, smoke, aura glow matching the product's world

IMAGE TYPES NEEDED:{type_list}

FORMAT: Separate each prompt with exactly this line:
===PROMPT===

IMPORTANT: Return your response inside a SINGLE code block (triple backticks).
Inside the code block, separate each prompt with ===PROMPT=== on its own line.
No numbering, no labels, no section titles, no "---" dividers, no explanations.
Start directly with the first prompt paragraph inside the code block.
Each prompt = one dense paragraph + one "Negative prompt:" line."""

    return prompt, types[:count]


def parse_prompts(response_text, expected_types):
    """Parse Gemini response into individual prompts."""
    raw = response_text.strip()
    parts = [p.strip() for p in raw.split('===PROMPT===') if p.strip()]

    prompts = []
    for i, text in enumerate(parts):
        ptype = expected_types[i] if i < len(expected_types) else f'extra_{i}'
        prompts.append({
            'id': ptype,
            'name': TYPE_DESCRIPTIONS.get(ptype, ptype),
            'prompt': text,
        })

    return prompts


def generate_listing_prompts(product_info, count=8, image_url=None):
    """Generate N listing prompts using call_llm (Gemini API/Extension/Groq chain)."""
    from modules.night_orchestrator.llm import call_llm

    mega, types = build_mega_prompt(count, product_info)

    try:
        result = call_llm(mega, temperature=0.7, max_tokens=8000, image_url=image_url)
        prompts = parse_prompts(result, types)
        if len(prompts) >= 1:
            print(f"[A+ Prompts] Generated {len(prompts)} prompts")
            return prompts
        raise ValueError("No prompts parsed")
    except Exception as e:
        logger.error(f"[A+ Prompts] Error: {e}")
        return _fallback_prompts(product_info, types)


def _fallback_prompts(info, types):
    """Basic fallback if LLM fails."""
    name = info.get('product_name', 'Product')
    brand = info.get('brand_name', 'Brand')
    prompts = []
    for t in types:
        desc = TYPE_DESCRIPTIONS.get(t, t)
        prompts.append({
            'id': t,
            'name': desc,
            'prompt': f"Ultra-premium Amazon infographic design for {name}, centered product with ultra realistic texture, cinematic themed background with atmospheric fog and soft energy glow, clean grey palette with soft accents, bold modern typography, hyper detailed texture, realistic soft shadows, modern editorial composition, centered product dominance, studio lighting, professional Amazon listing image, Canon EOS R5 photography style, 85mm lens, HDR balanced rendering, masterpiece, best quality, ultra photorealistic 12K rendering\n\nNegative prompt: blur, clutter, cartoonish render, watermark, low quality, fake texture",
        })
    return prompts
