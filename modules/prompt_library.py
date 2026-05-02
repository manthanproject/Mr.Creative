"""
Mr.Creative Prompt Library
Comprehensive prompt building system for FLUX-optimized image generation.

Data sources:
- fairy-root/Flux-Prompt-Generator: photography styles, photo types, places, backgrounds
- ComfyAssets/kiko-flux2-prompt-builder: cameras, lighting, composition, moods
- Black Forest Labs FLUX prompting guide: natural language structure, no negative prompts

FLUX prompt rules:
- Natural language paragraphs, NOT comma-separated keyword lists
- Specific camera + lens + aperture specs
- Dense, production-brief style descriptions
- Subject + Action + Style + Context framework
- No negative prompts (describe what you want, not what you don't)
"""

import os
import json
import random

# ═══════════════════════════════════════════════
# Load JSON data files
# ═══════════════════════════════════════════════

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'prompt_library')


def _load_json(filename):
    """Load a JSON data file from the prompt_library data directory."""
    path = os.path.join(DATA_DIR, filename)
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}


# Load all data at module import time
_CAMERAS = _load_json('cameras.json')       # {group: [{name, prompt}]}
_LIGHTING = _load_json('lighting.json')     # {group: [{name, prompt}]}
_COMPOSITION = _load_json('composition.json')  # {group: [{name, prompt}]}
_MOOD = _load_json('mood.json')             # {group: [{name, prompt}]}
_PHOTO_STYLES = _load_json('photography_styles.json')  # [str]
_PHOTO_TYPES = _load_json('photo_type.json')  # [str]
_PLACES = _load_json('place.json')          # [str]
_BACKGROUNDS = _load_json('background.json')  # [str]


# ═══════════════════════════════════════════════
# Flattened lists for random selection
# ═══════════════════════════════════════════════

def _flatten_grouped(data):
    """Flatten {group: [items]} to flat list of items."""
    flat = []
    for group_items in data.values():
        if isinstance(group_items, list):
            flat.extend(group_items)
    return flat

ALL_CAMERAS = _flatten_grouped(_CAMERAS)
ALL_LIGHTING = _flatten_grouped(_LIGHTING)
ALL_COMPOSITION = _flatten_grouped(_COMPOSITION)
ALL_MOOD = _flatten_grouped(_MOOD)


# ═══════════════════════════════════════════════
# Content-type specific configurations
# ═══════════════════════════════════════════════

CONTENT_TYPE_CONFIG = {
    'social_post': {
        'description': 'Lifestyle editorial for social media',
        'preferred_cameras': ['Canon', 'Fujifilm', 'Sony'],
        'preferred_lighting': ['Natural Light', 'Environmental'],
        'preferred_composition': ['Classic Rules', 'Leading & Framing'],
        'preferred_mood': ['Emotional Tones', 'Visual Aesthetics'],
        'photo_types': ['close-up detail', 'three-quarter view', 'overhead shot', 'front view', 'soft focus'],
        'surfaces': [
            'bathroom vanity with morning light',
            'linen bedsheet flat lay',
            'marble countertop near a window',
            'wooden shelf with small plant',
            'coffee table with magazine',
            'kitchen counter with fresh ingredients',
            'vanity mirror with warm lighting',
            'bedside table with soft lamp glow',
        ],
        'scenarios': [
            'person applying product at vanity mirror, candid morning routine moment',
            'hands holding product bottle, soft natural light from nearby window',
            'flat lay arrangement on textured surface with complementary props',
            'product in daily life context — gym bag, travel pouch, office desk',
            'close-up of product texture being applied to skin',
            'product bottles arranged aesthetically with fresh flowers and greenery',
            'someone reaching for product on bathroom shelf, casual candid shot',
            'product next to coffee cup and book, cozy morning scene',
        ],
        'prompt_template': (
            '{scenario}. {camera_prompt}, {lighting_prompt}. '
            '{composition_prompt}. {mood_prompt}. '
            'Editorial lifestyle photography, magazine quality, natural imperfections.'
        ),
    },
    'banner': {
        'description': 'Hero product shot for ads/website headers',
        'preferred_cameras': ['Phase One', 'Hasselblad', 'Canon', 'Sony'],
        'preferred_lighting': ['Studio Lighting', 'Dramatic & Cinematic'],
        'preferred_composition': ['Special Purpose', 'Spatial Techniques'],
        'preferred_mood': ['Visual Aesthetics', 'Stylistic Moods'],
        'photo_types': ['hero shot', 'front view', 'three-quarter view', 'close-up detail'],
        'surfaces': [
            'polished concrete surface with single accent prop',
            'raw oak shelf against blurred bathroom tiles',
            'brushed marble slab with dramatic shadow',
            'matte black surface with gradient background',
            'frosted glass shelf with soft backlight',
            'premium leather surface with warm spotlight',
            'white sweep background, clean studio',
            'terrazzo surface with eucalyptus sprig',
        ],
        'scenarios': [
            'hero product shot centered on {surface}, generous negative space on right for text overlay',
            'premium product on {surface}, single key light from left creating dramatic shadow, editorial banner composition',
            'product at 3/4 angle on {surface}, clean gradient background fading to brand color, commercial photography',
            'dynamic angle product shot on {surface}, bold lighting with single spotlight, text-safe zone at top',
            'product floating above {surface} with dramatic shadow below, clean isolated composition',
            'two products side by side on {surface}, symmetrical arrangement, premium brand photography',
        ],
        'prompt_template': (
            '{scenario}. {camera_prompt}, {lighting_prompt}. '
            '{composition_prompt}. {mood_prompt}. '
            'Professional commercial product photography, text-safe composition, premium brand aesthetic.'
        ),
    },
    'a_plus': {
        'description': 'Amazon A+ style e-commerce product photography',
        'preferred_cameras': ['Hasselblad', 'Phase One', 'Sony', 'Canon'],
        'preferred_lighting': ['Studio Lighting'],
        'preferred_composition': ['Special Purpose', 'Spatial Techniques'],
        'preferred_mood': ['Visual Aesthetics'],
        'photo_types': ['front view', 'close-up detail', 'macro view', 'overhead shot', 'three-quarter view', 'hero shot'],
        'surfaces': [
            'clean white background, studio sweep',
            'light gray seamless background',
            'marble slab with clean edges',
            'matte white surface with soft shadows',
            'neutral backdrop with product centered',
            'wooden surface showing natural grain texture',
        ],
        'scenarios': [
            'product at 3/4 angle on {surface}, every label detail visible and sharp, e-commerce listing style',
            'macro close-up of product texture and finish, showing ingredient quality, {surface}',
            'product from directly front on {surface}, clean and informational, Amazon product page style',
            'multiple angles of the same product — front, side, top — arranged on {surface}, catalog style',
            'product being held in hand showing scale and size, {surface} in background, real usage context',
            'before and after comparison layout style, product prominently featured on {surface}',
            'product ingredients or key features visible through packaging, studio macro on {surface}',
            'product with its packaging box partially open, revealing the product inside, unboxing style on {surface}',
        ],
        'prompt_template': (
            '{scenario}. {camera_prompt}, {lighting_prompt}. '
            '{composition_prompt}. '
            'E-commerce product photography, informational, clean, every detail sharp and visible. '
            'The product must be the clear hero of the image.'
        ),
    },
    'lifestyle': {
        'description': 'Documentary-style real-world usage photography',
        'preferred_cameras': ['Fujifilm', 'Leica', 'Sony', 'Other Cameras'],
        'preferred_lighting': ['Natural Light', 'Environmental'],
        'preferred_composition': ['Classic Rules', 'Leading & Framing', 'Dynamic Compositions'],
        'preferred_mood': ['Emotional Tones', 'Environmental Moods'],
        'photo_types': ['soft focus', 'bokeh effect', 'close-up detail', 'front view', 'side view'],
        'surfaces': [],
        'scenarios': [
            'person doing evening skincare routine in warmly lit bathroom, product visible on counter, cotton towel on shoulder, reflection in mirror',
            'morning kitchen scene, someone with coffee holding product, sunlight streaming through blinds casting shadows on counter',
            'product tucked in gym bag between water bottle and headphones, locker room background, active lifestyle context',
            'product on office desk next to laptop and plant, afternoon light through window, professional wellness context',
            'person applying product outdoors at golden hour, park bench, natural setting, wind in hair',
            'bathroom shelf vignette — product among real toiletries, toothbrush holder, small succulent, lived-in authentic',
            'travel context — product in carry-on bag, airport lounge or hotel room, cosmopolitan lifestyle',
            'evening self-care ritual, candles lit, product on bath tray, warm ambient lighting, relaxation mood',
        ],
        'prompt_template': (
            '{scenario}. {camera_prompt}, {lighting_prompt}. '
            '{composition_prompt}. {mood_prompt}. '
            'Documentary lifestyle photography, authentic and unstaged, natural imperfections, '
            'real human moment, editorial wellness brand aesthetic.'
        ),
    },
    'ad_creative': {
        'description': 'Bold campaign creative for Meta/Google ads',
        'preferred_cameras': ['Canon', 'Sony', 'Nikon'],
        'preferred_lighting': ['Dramatic & Cinematic', 'Studio Lighting', 'Color & Creative'],
        'preferred_composition': ['Dynamic Compositions', 'Spatial Techniques'],
        'preferred_mood': ['Visual Aesthetics', 'Stylistic Moods'],
        'photo_types': ['hero shot', 'close-up detail', 'front view', 'overhead shot'],
        'surfaces': [
            'dark moody background with single spotlight',
            'bold brand-colored gradient background',
            'dynamic splash of water or powder',
            'geometric shapes in brand colors',
            'abstract color field background',
            'dramatic dark surface with rim lighting',
        ],
        'scenarios': [
            'dynamic product splash shot — product with water droplets frozen mid-air, {surface}, premium cosmetics advertising',
            'bold overhead shot of product arrangement in brand colors, {surface}, geometric composition, strong directional shadows',
            'product mid-action — being squeezed, poured, or applied — capturing motion, {surface}, high-speed photography feel',
            'product against {surface}, dramatic rim lighting outlining product shape, bold and eye-catching for social media ads',
            'split-composition — product on one side, lifestyle context on other, {surface}, Meta ad creative format',
            'product floating in dramatic scene with ingredients or brand elements orbiting around it, {surface}',
        ],
        'prompt_template': (
            '{scenario}. {camera_prompt}, {lighting_prompt}. '
            '{composition_prompt}. {mood_prompt}. '
            'Bold campaign photography designed to stop scrolling, high contrast, '
            'dynamic composition, performance ad creative style.'
        ),
    },
}


# ═══════════════════════════════════════════════
# Core API
# ═══════════════════════════════════════════════

def get_camera(content_type=None, seed=None):
    """Get a random camera+lens combo appropriate for content type.

    Returns dict with 'name' and 'prompt' keys.
    """
    rng = random.Random(seed) if seed else random

    if content_type and content_type in CONTENT_TYPE_CONFIG:
        preferred = CONTENT_TYPE_CONFIG[content_type]['preferred_cameras']
        candidates = []
        for group in preferred:
            if group in _CAMERAS:
                candidates.extend(_CAMERAS[group])
        if candidates:
            return rng.choice(candidates)

    if ALL_CAMERAS:
        return rng.choice(ALL_CAMERAS)
    return {'name': 'Canon EOS R5', 'prompt': 'shot on Canon EOS R5 with a 50mm f/1.4 lens'}


def get_lighting(content_type=None, seed=None):
    """Get a random lighting setup appropriate for content type."""
    rng = random.Random(seed) if seed else random

    if content_type and content_type in CONTENT_TYPE_CONFIG:
        preferred = CONTENT_TYPE_CONFIG[content_type]['preferred_lighting']
        candidates = []
        for group in preferred:
            if group in _LIGHTING:
                candidates.extend(_LIGHTING[group])
        if candidates:
            return rng.choice(candidates)

    if ALL_LIGHTING:
        return rng.choice(ALL_LIGHTING)
    return {'name': 'Natural Light', 'prompt': 'natural window lighting, soft and diffused'}


def get_composition(content_type=None, seed=None):
    """Get a random composition rule appropriate for content type."""
    rng = random.Random(seed) if seed else random

    if content_type and content_type in CONTENT_TYPE_CONFIG:
        preferred = CONTENT_TYPE_CONFIG[content_type]['preferred_composition']
        candidates = []
        for group in preferred:
            if group in _COMPOSITION:
                candidates.extend(_COMPOSITION[group])
        if candidates:
            return rng.choice(candidates)

    if ALL_COMPOSITION:
        return rng.choice(ALL_COMPOSITION)
    return {'name': 'Rule of Thirds', 'prompt': 'rule of thirds composition, subject off-center'}


def get_mood(content_type=None, seed=None):
    """Get a random mood/atmosphere appropriate for content type."""
    rng = random.Random(seed) if seed else random

    if content_type and content_type in CONTENT_TYPE_CONFIG:
        preferred = CONTENT_TYPE_CONFIG[content_type]['preferred_mood']
        candidates = []
        for group in preferred:
            if group in _MOOD:
                candidates.extend(_MOOD[group])
        if candidates:
            return rng.choice(candidates)

    if ALL_MOOD:
        return rng.choice(ALL_MOOD)
    return {'name': 'Natural', 'prompt': 'natural mood, organic atmosphere'}


def get_scenario(content_type, seed=None):
    """Get a random scenario for the given content type."""
    rng = random.Random(seed) if seed else random

    config = CONTENT_TYPE_CONFIG.get(content_type)
    if not config:
        return 'Product photography on clean surface'

    scenarios = config['scenarios']
    scenario = rng.choice(scenarios)

    # Fill in {surface} if present
    if '{surface}' in scenario and config.get('surfaces'):
        surface = rng.choice(config['surfaces'])
        scenario = scenario.replace('{surface}', surface)

    return scenario


def get_photo_type(content_type=None, seed=None):
    """Get a random photo type/angle."""
    rng = random.Random(seed) if seed else random

    if content_type and content_type in CONTENT_TYPE_CONFIG:
        types = CONTENT_TYPE_CONFIG[content_type]['photo_types']
        if types:
            return rng.choice(types)

    if _PHOTO_TYPES:
        return rng.choice(_PHOTO_TYPES)
    return 'front view'


# ═══════════════════════════════════════════════
# High-level prompt builder
# ═══════════════════════════════════════════════

def build_prompt(content_type, brand_info=None, index=0):
    """Build a complete FLUX-optimized prompt for the given content type.

    Args:
        content_type: 'social_post', 'banner', 'a_plus', 'lifestyle', 'ad_creative'
        brand_info: Dict with brand details (name, colors, tone, product_category)
        index: Prompt index (used as seed offset for variety)

    Returns:
        Dict with 'prompt', 'photo_type', 'camera', 'lighting', 'composition', 'mood'
    """
    seed = hash(f'{content_type}_{index}') & 0xFFFFFFFF

    camera = get_camera(content_type, seed)
    lighting = get_lighting(content_type, seed + 1)
    composition = get_composition(content_type, seed + 2)
    mood = get_mood(content_type, seed + 3)
    scenario = get_scenario(content_type, seed + 4)
    photo_type = get_photo_type(content_type, seed + 5)

    config = CONTENT_TYPE_CONFIG.get(content_type, CONTENT_TYPE_CONFIG['social_post'])
    template = config['prompt_template']

    prompt = template.format(
        scenario=scenario,
        camera_prompt=camera.get('prompt', ''),
        lighting_prompt=lighting.get('prompt', ''),
        composition_prompt=composition.get('prompt', ''),
        mood_prompt=mood.get('prompt', ''),
    )

    # Inject brand info if provided
    if brand_info:
        brand_context = []
        if brand_info.get('name'):
            brand_context.append(f"for {brand_info['name']}")
        if brand_info.get('product_category'):
            brand_context.append(f"{brand_info['product_category']} product")
        if brand_info.get('tone'):
            brand_context.append(f"{brand_info['tone']} brand tone")
        if brand_context:
            prompt += f" Brand context: {', '.join(brand_context)}."

    return {
        'prompt': prompt,
        'photo_type': photo_type,
        'camera': camera.get('name', ''),
        'lighting': lighting.get('name', ''),
        'composition': composition.get('name', ''),
        'mood': mood.get('name', ''),
    }


def build_prompt_batch(content_type, count, brand_info=None):
    """Build multiple unique prompts for the same content type.

    Args:
        content_type: Content type string
        count: Number of prompts to generate
        brand_info: Brand details dict

    Returns:
        List of prompt dicts
    """
    prompts = []
    for i in range(count):
        p = build_prompt(content_type, brand_info, index=i)
        prompts.append(p)
    return prompts


def get_prompt_context_for_llm(content_types, count=5):
    """Generate a rich context block for the LLM prompt crafter.

    Instead of the LLM making up camera specs, we provide real ones
    from our library for it to choose from.

    Args:
        content_types: List of content type strings
        count: Number of examples per type

    Returns:
        String with camera/lighting/composition options per content type
    """
    context_parts = []

    for ctype in content_types:
        if ctype not in CONTENT_TYPE_CONFIG:
            continue

        config = CONTENT_TYPE_CONFIG[ctype]

        # Get sample cameras for this type
        cameras = []
        for group in config['preferred_cameras']:
            if group in _CAMERAS:
                cameras.extend([c['prompt'] for c in _CAMERAS[group][:2]])

        # Get sample lighting
        lighting = []
        for group in config['preferred_lighting']:
            if group in _LIGHTING:
                lighting.extend([l['prompt'] for l in _LIGHTING[group][:3]])

        # Get sample compositions
        compositions = []
        for group in config['preferred_composition']:
            if group in _COMPOSITION:
                compositions.extend([c['prompt'] for c in _COMPOSITION[group][:2]])

        # Get scenarios
        scenarios = config['scenarios'][:4]

        context_parts.append(f"""
=== {ctype.upper()} ===
Description: {config['description']}
Photo types to use: {', '.join(config['photo_types'])}

Camera options (pick one per prompt):
{chr(10).join(f'  - {c}' for c in cameras[:6])}

Lighting options (pick one per prompt):
{chr(10).join(f'  - {l}' for l in lighting[:6])}

Composition options (pick one per prompt):
{chr(10).join(f'  - {c}' for c in compositions[:4])}

Scene scenarios (use as inspiration, vary each prompt):
{chr(10).join(f'  - {s}' for s in scenarios)}
""")

    return '\n'.join(context_parts)


# ═══════════════════════════════════════════════
# Stats & Info
# ═══════════════════════════════════════════════

def get_library_stats():
    """Return stats about the loaded prompt library."""
    return {
        'cameras': len(ALL_CAMERAS),
        'lighting': len(ALL_LIGHTING),
        'compositions': len(ALL_COMPOSITION),
        'moods': len(ALL_MOOD),
        'photography_styles': len(_PHOTO_STYLES) if isinstance(_PHOTO_STYLES, list) else 0,
        'photo_types': len(_PHOTO_TYPES) if isinstance(_PHOTO_TYPES, list) else 0,
        'places': len(_PLACES) if isinstance(_PLACES, list) else 0,
        'content_types': list(CONTENT_TYPE_CONFIG.keys()),
        'scenarios_per_type': {k: len(v['scenarios']) for k, v in CONTENT_TYPE_CONFIG.items()},
    }
