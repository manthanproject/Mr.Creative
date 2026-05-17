"""
A+ Listing Prompt Generator
Upload product image to Gemini + one mega-prompt → N unique Flow-ready prompts
"""

import logging
logger = logging.getLogger('aplus')


PROMPT_TYPES = {
    1: ['hero'],
    2: ['hero', 'features'],
    3: ['hero', 'features', 'lifestyle'],
    4: ['hero', 'features', 'lifestyle', 'howto'],
    5: ['hero', 'features', 'lifestyle', 'howto', 'dimensions'],
    6: ['hero', 'features', 'lifestyle', 'howto', 'dimensions', 'comparison'],
    7: ['hero', 'features', 'lifestyle', 'howto', 'dimensions', 'comparison', 'multiuse'],
    8: ['hero', 'features', 'lifestyle', 'howto', 'dimensions', 'comparison', 'multiuse', 'trust'],
}

TYPE_DESCRIPTIONS = {
    'hero': 'Hero Image — product centered on white background, no text, best angle, sharp detail',
    'features': 'Key Features Infographic — product on one side, 4-5 feature callouts with icons + text on other side',
    'lifestyle': 'Lifestyle Image — target audience USING the product in real-world context, editorial photography',
    'howto': 'How To Use — 3-4 numbered usage steps with actual step titles and instructions',
    'dimensions': 'Size & Dimensions — product with measurement lines showing actual dimensions',
    'comparison': 'Comparison Chart — table comparing product vs 2 generic competitors with checkmarks/crosses',
    'multiuse': 'Multi-Use Versatility — product in 4-6 different use cases, structured grid collage',
    'trust': 'Trust & Quality Badges — product centered with 6 quality/trust badge seals around it',
}


def build_mega_prompt(count, brand_info=None):
    """Build one mega-prompt that asks Gemini for N unique image prompts."""
    # Pick which types to use
    types = PROMPT_TYPES.get(min(count, 8), PROMPT_TYPES[8])
    # If more than 8, repeat types with variations
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

    prompt = f"""Look at this product image carefully. You are a world-class Amazon listing image prompt engineer.

Generate exactly {count} unique AI image generation prompts for this product's Amazon A+ listing.
{brand_context}

CRITICAL — REFERENCE IMAGE RULES:
- A reference image of the product will be provided to the AI image generator
- The product in the generated image MUST look IDENTICAL to the reference image
- DO NOT describe the product appearance in detail — instead say the product from the reference image
- DO NOT change, redesign, or reimagine the product label, text, colors, shape, logo, or packaging
- The prompt should describe the SCENE, BACKGROUND, LIGHTING, COMPOSITION around the unchanged product

Each prompt MUST:
- Be 100-200 words, completely self-contained
- Reference the product as the exact product from the reference image (never describe it from scratch)
- Include: scene/background description, lighting (3-point studio), camera (85mm f/8 ISO 100), composition
- For infographic types: describe text overlays, icons, layout alongside the unchanged product
- End with negative prompt: no blur, no low quality, no cartoonish, no product modification, no label changes
- Be ultra photorealistic, 12K UHD quality

IMAGE TYPES NEEDED:{type_list}

FORMAT: Separate each prompt with exactly this line:
===PROMPT===

IMPORTANT: Return your response inside a SINGLE code block (triple backticks).
Inside the code block, separate each prompt with ===PROMPT=== on its own line.
No numbering, no labels, no explanations outside the code block.
Start directly with the first prompt inside the code block."""

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
            'prompt': f"Ultra photorealistic 12K UHD product photography, {desc}. Product: {name}. Brand: {brand}. 85mm lens f/8 ISO 100, 3-point studio lighting. No gradients, no clutter, no cartoonish.",
        })
    return prompts
