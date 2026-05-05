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
    'a_plus': {
        'description': 'Amazon/Flipkart A+ product listing content — designed infographic images',
        'preferred_cameras': [],
        'preferred_lighting': [],
        'preferred_composition': [],
        'preferred_mood': [],
        'photo_types': ['infographic', 'product listing', 'hero banner', 'feature grid'],
        'surfaces': [],
        'scenarios': [],
        'prompt_template': '{scenario}',
        'expert_prompts': [
            'A+ product listing infographic with hero shot, key benefits with icons, feature grid, how-to-use steps, ingredient callouts, before and after comparison, multi-angle views, and a quality badge. Clean professional layout with bold headings and organized sections.',
        ],
    },
    'social_post': {
        'description': 'Lifestyle editorial for social media',
        'preferred_cameras': ['Canon', 'Fujifilm', 'Sony'],
        'preferred_lighting': ['Natural Light', 'Environmental'],
        'preferred_composition': ['Classic Rules', 'Leading & Framing'],
        'preferred_mood': ['Emotional Tones', 'Visual Aesthetics'],
        'photo_types': ['close-up detail', 'three-quarter view', 'overhead shot', 'front view', 'soft focus'],
        'surfaces': [],
        'scenarios': [],
        'prompt_template': '{scenario}',
        'expert_prompts': [
            'A candid, aesthetically pleasing shot of the product resting on a terrazzo bathroom vanity next to a minimalist ceramic toothbrush holder. Captured with a Sony A7IV and a 35mm f/1.4 lens at f/2.8, creating a soft, creamy background blur that keeps the environment contextual but the product in sharp focus. Natural morning light filters through a frosted bathroom window, casting soft, inviting highlights on the label and glass bottle.',
            'A top-down flat lay composition featuring the product as the focal point, surrounded by a minimalist cup of black coffee, an open neutral-toned journal, and a pair of chic tortoiseshell glasses. Photographed with a Canon EOS R6 and a 50mm lens at f/5.6 to ensure edge-to-edge sharpness across the items lying on clean white bedsheets. Soft, diffused daylight from a nearby window creates gentle, natural shadows that give depth to the lifestyle scene.',
            'The product stands proudly on a wooden windowsill, bathed in warm, directional morning sunlight that casts long, dramatic shadows. Shot on a Fujifilm X-T5 with a 23mm f/1.4 lens at f/4, the golden hour light creates a bright, optimistic mood perfect for a morning skincare routine post. The bottle label is perfectly exposed and readable, contrasting beautifully against the warm tones of the wood and the bright glow of the sunrise.',
            'A trendy shelfie featuring the product front and center on a floating acrylic bathroom shelf, flanked slightly out of focus by other minimalist beauty products. Captured using a Leica Q3 with its fixed 28mm lens at f/2.8, framing the product as the hero while providing aspirational bathroom context. Soft, warm overhead bathroom lighting mixed with an LED vanity ring light creates a cozy, modern glow that perfectly illuminates the label.',
            'The product is peeking out of a high-end, neutral-toned canvas cosmetic bag resting on a marble cafe table. Photographed with a Hasselblad X2D 100C and a 45mm lens at f/4, capturing incredible detail in the canvas texture while keeping the label razor-sharp and centered. Soft, overcast natural light from the cafe patio provides even, flattering illumination that highlights the product as a daily, on-the-go essential.',
            'A beautiful, soft social media flat lay showing the product resting gently on flowing white silk fabric, accompanied by fresh, minimal white eucalyptus sprigs. Shot with a Sony A7RV and a 50mm f/1.2 lens at f/4, the composition is airy and elegant. A large diffused softbox from above mimics soft overcast daylight, eliminating harsh shadows and enhancing the pure, clean aesthetic of the white label.',
            'The product sits on a dark slate bathroom counter, illuminated by the warm, cozy glow of a nearby lit candle in the background. Captured on a Canon EOS R5 with an 85mm f/1.2 lens at f/2.0 to create a moody, shallow depth of field perfect for an evening wind-down routine post. The ambient candlelight is supplemented by a hidden, cool-toned LED fill light that specifically targets the product label, making it pop.',
            'A close-up shot of the product resting on a beautifully textured, ribbed beige stone tray. Photographed using a Fujifilm GFX 100S with an 80mm lens at f/5.6, focusing intently on the interaction between the smooth glass of the dropper bottle and the rough, tactile grooves of the tray. Side-angled window light creates micro-shadows across the ribbed stone, framing the perfectly exposed, crisp label in the center.',
        ],
    },
    'banner': {
        'description': 'Hero product shot for ads/website headers',
        'preferred_cameras': ['Phase One', 'Hasselblad', 'Canon', 'Sony'],
        'preferred_lighting': ['Studio Lighting', 'Dramatic & Cinematic'],
        'preferred_composition': ['Special Purpose', 'Spatial Techniques'],
        'preferred_mood': ['Visual Aesthetics', 'Stylistic Moods'],
        'photo_types': ['hero shot', 'front view', 'three-quarter view', 'close-up detail'],
        'surfaces': [],
        'scenarios': [],
        'prompt_template': '{scenario}',
        'expert_prompts': [
            'A wide-format website banner featuring the product placed on the far right side of the frame, leaving abundant clean, textured white plaster space on the left for text placement. Captured with a Phase One XF IQ4 and an 80mm lens at f/11, the bottle is incredibly crisp and commanding. A large softbox with a grid highlights the edge of the glass bottle and casts a subtle, elegant shadow to the left, grounding the product on the plaster surface.',
            'A moody, high-end banner shot of the product standing on a slab of black Nero Marquina marble, utilizing a wide 16:9 aspect ratio. Photographed with a Hasselblad H6D-100c and a 100mm lens at f/8, the white label creates a striking, bold contrast against the dark environment. A single, focused snoot light creates a dramatic pool of illumination strictly around the bottle, letting the edges of the marble fade into deep, luxurious shadows.',
            'A striking, modern composition where the product appears to be levitating an inch above a seamless pastel blue backdrop, designed for an ad header. Shot on a Sony A7RV with a 90mm Macro lens at f/8, the image freezes the bottle mid-air with complete sharpness. A hard overhead strobe casts a sharp, distinct drop shadow directly beneath the floating bottle, emphasizing the bold, weightless, clinical nature of the product.',
            'An ultra-modern, scroll-stopping wide banner featuring the product resting on a geometric, bright yellow acrylic podium. Captured with a Canon EOS R5 and a 50mm f/1.2 lens at f/8, the vibrant pop of yellow contrasts heavily with the clinical label, commanding immediate attention. Bright, punchy commercial lighting with edge highlights ensures the glass bottle looks premium and three-dimensional.',
            'A dynamic, wide panoramic shot of the product sitting in a shallow pool of pure, rippling water with a perfect mirror reflection underneath. Photographed using a Leica SL2 with a 90mm lens at f/8 to capture the crisp text of the label and the intricate details of the water ripples. Backlighting combined with a soft front fill creates glowing, luminous water while keeping the label perfectly legible.',
            'A wide-angle website hero banner showing the product standing on a smooth, cylindrical concrete pedestal against a soft grey background. Shot with a Fujifilm GFX 100S and a 45mm lens at f/11, the composition places the pedestal exactly in the lower center, leaving the top and sides open for web copy. Diffused, wrap-around softbox lighting creates an incredibly smooth gradient across the grey background.',
            'A horizontal banner layout where the product is positioned strongly on the left third of the frame, resting on frosted glass, leaving the right side completely open. Captured with a Hasselblad X2D 100C and a 65mm lens at f/8, the clinical packaging is meticulously sharp. Lighting from beneath the frosted glass gives the surface a glowing, ethereal quality, while a subtle front light ensures the brand typography is perfectly readable.',
            'A highly symmetrical, imposing hero banner of the product shot perfectly head-on, taking up the center third of a 16:9 frame. Photographed with a Phase One XF IQ4 and a 150mm lens at f/16 to flatten the perspective and eliminate any distortion. Dual strip softboxes on the left and right create perfect, identical vertical reflection lines down the sides of the glass bottle, exuding clinical perfection against a pure white background.',
        ],
    },
    'lifestyle': {
        'description': 'Documentary-style real-world usage photography',
        'preferred_cameras': ['Fujifilm', 'Leica', 'Sony', 'Other Cameras'],
        'preferred_lighting': ['Natural Light', 'Environmental'],
        'preferred_composition': ['Classic Rules', 'Leading & Framing', 'Dynamic Compositions'],
        'preferred_mood': ['Emotional Tones', 'Environmental Moods'],
        'photo_types': ['soft focus', 'bokeh effect', 'close-up detail', 'front view', 'side view'],
        'surfaces': [],
        'scenarios': [],
        'prompt_template': '{scenario}',
        'expert_prompts': [
            'A documentary-style lifestyle shot of a person hands placing the product onto a wet, steamy bathroom sink edge after a shower. Photographed with a Leica M11 and a 35mm Summilux lens at f/2.0, focusing sharply on the bottle while the background shows blurred, steamy tiles and a damp towel. Authentic, moody natural light filters through a condensation-covered bathroom window, giving the scene a raw, lived-in morning routine atmosphere.',
            'A candid, over-the-shoulder lifestyle image of a young woman looking into a bathroom mirror as she applies a drop of serum to her cheek from the glass dropper. Shot with a Sony A7IV and a 50mm f/1.4 lens at f/2.8, the camera focuses strictly on the dropper and the bottle in her hand, blurring her face slightly in the mirror reflection. Soft, flattering LED vanity lights combined with ambient room lighting create a realistic, modern skincare routine moment.',
            'A gritty, realistic editorial shot looking down into an open gym duffel bag on a locker room bench, where the product sits securely next to a folded towel and headphones. Captured with a Fujifilm X-Pro3 and a 23mm f/1.4 lens at f/4 to give a slightly raw, photojournalistic feel. The harsh, overhead fluorescent lights of the locker room cast authentic, contrasty shadows, grounding the product as a staple in an active daily lifestyle.',
            'An atmospheric lifestyle photograph of the product resting on a hotel room nightstand, with a blurred cityscape visible through a large window in the background. Photographed with a Canon EOS R6 and an 85mm lens at f/1.8, the shallow depth of field isolates the crisp label against the busy urban bokeh. The moody, blue-hour twilight from the window illuminates the bottle softly, portraying the product as a reliable travel companion.',
            'A warm, documentary-style image of a person sitting on a messy, cozy bed, holding the product thoughtfully in their lap. Shot using a Hasselblad X1D II 50C and a 45mm lens at f/2.8, the focal point is entirely on the bottle label and the relaxed grip of their hands. Dappled afternoon sunlight streams through window blinds, casting organic, uneven light patterns across the bedsheets.',
            'An editorial-style lifestyle shot of two friends getting ready, with one person hand holding the product while offering the dropper to the other person out of frame. Captured with a Sony A7S III and a 35mm lens at f/2.8 for a wide, inclusive, and authentic feel. Natural, bright daylight fills the modern bedroom, rendering the label bright and clear against the casual, lifestyle-driven backdrop.',
            'A close-up lifestyle photograph focusing on a person dispensing a drop of serum onto the back of their hand, with the bottle held prominently in the frame. Shot with a Canon EOS R5 and a 100mm Macro lens at f/4, capturing the tactile interaction between the dropper and human skin. Soft, diffused natural light from a nearby window creates a gentle, realistic skin texture and highlights the viscous drop.',
            'A top-down documentary shot of a person packing a hardshell suitcase, with their hand placing the product into a mesh toiletry compartment. Captured with a Leica Q2 using its 28mm lens at f/4, the image feels spontaneous and real, prioritizing the sharp label among folded clothes. Ambient, soft room lighting provides an even, low-contrast exposure that feels like a genuine, unstyled travel moment.',
        ],
    },
    'ad_creative': {
        'description': 'Bold campaign creative for Meta/Google ads',
        'preferred_cameras': ['Canon', 'Sony', 'Phase One', 'Hasselblad'],
        'preferred_lighting': ['Dramatic & Cinematic', 'Studio Lighting', 'Color & Creative'],
        'preferred_composition': ['Dynamic Compositions', 'Spatial Techniques'],
        'preferred_mood': ['Visual Aesthetics', 'Stylistic Moods'],
        'photo_types': ['hero shot', 'close-up detail', 'front view', 'overhead shot'],
        'surfaces': [],
        'scenarios': [],
        'prompt_template': '{scenario}',
        'expert_prompts': [
            'A high-impact, scroll-stopping ad creative featuring the product centered on a vibrant, electric pink acrylic backdrop. Photographed with a Phase One XF IQ4 and an 80mm lens at f/11, the stark clinical label violently contrasts with the intense background color. Hard, punchy commercial strobe lighting with sharp shadows ensures the bottle jumps off the screen, designed to immediately grab attention in a fast-paced social feed.',
            'A dynamic, freeze-frame action shot for a performance ad, showing the product crashing into a shallow pool of milky water, sending dramatic, sculptural splashes into the air. Captured with a Sony A1 and a 90mm Macro lens at f/8 using an ultra-fast shutter speed. High-speed flash sync lighting freezes the chaotic water droplets in mid-air while keeping the product label perfectly crisp and legible amidst the splash.',
            'An edgy, modern ad creative showing the product standing on a black reflective glass surface, illuminated by cyberpunk-style neon rim lighting. Shot on a Canon EOS R5 with a 50mm f/1.2 lens at f/5.6, the bottle is dark in the center but outlined by glowing vibrant blue and magenta lights from the sides. The clinical label is spot-lit perfectly from the front, ensuring brand recognition within the trendy, dramatic aesthetic.',
            'A surreal, eye-catching ad composition where the product rests on a stone podium floating in the sky against a backdrop of fluffy, stylized pastel clouds. Photographed using a Hasselblad H6D-100c with a 100mm lens at f/8 to achieve a high-end look. Bright, omnidirectional studio lighting mimics perfect sunlight, casting sharp shadows on the floating stone while keeping the product label impossibly clean and in focus.',
            'A luxurious, aspirational ad creative positioning the product next to a flowing, miniature tabletop waterfall on a bed of smooth river stones. Captured with a Fujifilm GFX 100S and a 110mm lens at f/5.6, blending the clinical nature of the product with high-end spa aesthetics. Shimmering, dappled lighting creates caustic light reflections on the glass bottle and the stones, making the product look incredibly refreshing and premium.',
            'A highly engaging, extreme macro ad shot focusing entirely on the tip of the glass dropper as a perfectly spherical drop of serum falls, with the brand label heavily blurred in the deep background. Shot with a Leica SL2 and a 100mm Macro lens at f/8, the falling droplet acts like a magnifying glass, catching vibrant studio reflections. A targeted ring light makes the droplet sparkle.',
            'A visually striking ad creative featuring the product resting on a bright orange seamless paper backdrop, cut by a harsh, diagonal slash of shadow from a window blind. Captured on a Canon EOS R3 with an 85mm lens at f/8, utilizing bold geometric lighting to create instant visual interest. The bright sunlight brilliantly illuminates the label in the top half of the frame, while the bottom fades into dramatic, artistic shadow.',
            'An energetic, playful ad creative mimicking a stop-motion frame, showing the product, the glass dropper, and the box exploding outward and levitating separately against a mint-green background. Photographed with a Sony A7RV and a 50mm lens at f/8, everything is kept in critical focus to showcase all elements of the packaging. Even, flat strobe lighting ensures bold color saturation and makes the labels pop aggressively.',
        ],
    },
    'model_photography': {
        'name': 'Model Photography',
        'description': 'Virtual models wearing or using the product',
        'expert_prompts': [
            'create a professional product photograph of a female model holding this product in a clean studio setting',
            'design a lifestyle photograph of a male model casually using this product outdoors in natural lighting',
            'create an editorial fashion photograph of a model showcasing this product in an urban setting',
            'design a close-up product photograph with a models hands elegantly presenting this product',
            'create a lifestyle photograph of a young professional using this product in a modern home setting',
            'design a fitness lifestyle photograph of an athletic model using this product in a gym environment',
            'create a beauty editorial photograph of a model applying or wearing this product with soft studio lighting',
            'design a candid street style photograph of a model incorporating this product into their everyday outfit',
        ],
        'cameras': [],
        'lightings': [],
        'prompt_template': '{scenario}',
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

    Uses expert prompts (complete paragraphs) when available,
    falls back to template assembly for custom types.
    """
    seed = hash(f'{content_type}_{index}') & 0xFFFFFFFF
    rng = random.Random(seed)

    config = CONTENT_TYPE_CONFIG.get(content_type, CONTENT_TYPE_CONFIG.get('social_post')) or {}

    # Use expert prompts if available (preferred — these are complete, self-contained)
    expert_prompts = config.get('expert_prompts', [])
    if expert_prompts:
        prompt = expert_prompts[index % len(expert_prompts)]
    else:
        # Fallback to template assembly
        camera = get_camera(content_type, seed)
        lighting = get_lighting(content_type, seed + 1)
        composition = get_composition(content_type, seed + 2)
        mood = get_mood(content_type, seed + 3)
        scenario = get_scenario(content_type, seed + 4)

        template = str(config.get('prompt_template', ''))
        prompt = template.format(
            scenario=scenario,
            camera_prompt=camera.get('prompt', ''),
            lighting_prompt=lighting.get('prompt', ''),
            composition_prompt=composition.get('prompt', ''),
            mood_prompt=mood.get('prompt', ''),
        )

    # Brand info intentionally NOT injected — Flow uses the reference image for the
    # real product. Adding brand context causes Flow to invent fake brand names/logos.

    photo_type = get_photo_type(content_type, seed + 5)

    return {
        'prompt': prompt,
        'photo_type': photo_type,
        'camera': '',
        'lighting': '',
        'composition': '',
        'mood': '',
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

    Provides expert prompt examples for the LLM to follow as templates,
    plus camera/lighting options for variety.
    """
    context_parts = []

    for ctype in content_types:
        if ctype not in CONTENT_TYPE_CONFIG:
            continue

        config = CONTENT_TYPE_CONFIG[ctype]

        # Expert prompt examples (show 3 as reference)
        expert_prompts = config.get('expert_prompts', [])
        examples = expert_prompts[:3] if expert_prompts else []

        # Get sample cameras for variety
        cameras = []
        for group in config['preferred_cameras']:
            if group in _CAMERAS:
                cameras.extend([c['prompt'] for c in _CAMERAS[group][:2]])

        # Get sample lighting
        lighting = []
        for group in config['preferred_lighting']:
            if group in _LIGHTING:
                lighting.extend([l['prompt'] for l in _LIGHTING[group][:3]])

        examples_text = '\n'.join(f'  EXAMPLE {i+1}: {p}' for i, p in enumerate(examples))

        context_parts.append(f"""
=== {ctype.upper()} ===
Description: {config['description']}

EXPERT PROMPT EXAMPLES (follow this style exactly — complete natural language paragraphs with camera specs, lighting, surface, and composition built in):
{examples_text}

Additional camera options to vary across prompts:
{chr(10).join(f'  - {c}' for c in cameras[:4])}

Additional lighting options:
{chr(10).join(f'  - {l}' for l in lighting[:4])}

RULES FOR {ctype.upper()}:
- Each prompt must be a complete, self-contained paragraph (3-4 sentences)
- Include specific camera + lens + aperture (vary across prompts!)
- Include specific lighting setup
- Include specific surface/backdrop/environment
- The product MUST be the clear hero — visible, in focus, readable label
- Write like a professional photography brief, NOT keyword lists
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
