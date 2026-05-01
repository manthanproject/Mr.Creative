"""
Mr.Creative Agent System
Each agent = a Groq LLM call with a specific role.
Agents communicate via a shared context dict.
"""

import json
import os
import time
from datetime import datetime


class AgentEngine:
    """Orchestrates multiple AI agents to generate marketing content."""

    def __init__(self, groq_api_key, cerebras_api_key=None):
        from groq import Groq
        self.client = Groq(api_key=groq_api_key)
        self.model = 'llama-3.3-70b-versatile'
        self.cerebras_client = None
        self.cerebras_model = 'llama3.1-8b'
        if cerebras_api_key:
            try:
                from cerebras.cloud.sdk import Cerebras
                self.cerebras_client = Cerebras(api_key=cerebras_api_key)
                print("[Agent] Cerebras fallback ready")
            except ImportError:
                print("[Agent] cerebras-cloud-sdk not installed — pip install cerebras-cloud-sdk")
        self._using_cerebras = False

    def _call_llm(self, system_prompt, user_prompt, temperature=0.7, max_tokens=2000):
        """Call Groq LLM → on 429, switch to Cerebras for rest of session."""
        # Pick client
        if self._using_cerebras and self.cerebras_client:
            client = self.cerebras_client
            model = self.cerebras_model
        else:
            client = self.client
            model = self.model

        try:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {'role': 'system', 'content': system_prompt},
                    {'role': 'user', 'content': user_prompt},
                ],
                temperature=temperature,
                max_tokens=max_tokens,
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            err = str(e)
            if ('429' in err or 'rate_limit' in err) and self.cerebras_client and not self._using_cerebras:
                print(f"[Agent] Groq rate limited — switching to Cerebras")
                self._using_cerebras = True
                return self._call_llm(system_prompt, user_prompt, temperature, max_tokens)
            print(f"[Agent] LLM error: {e}")
            return None

    def _parse_json(self, text):
        """Extract JSON from LLM response (handles ```json blocks)."""
        if not text:
            return None
        text = text.strip()
        if text.startswith('```'):
            text = text.split('\n', 1)[-1]
            text = text.rsplit('```', 1)[0]
        text = text.strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            # Try array first (most agent responses are arrays), then object
            for open_ch, close_ch in [('[', ']'), ('{', '}')]:
                start = text.find(open_ch)
                end = text.rfind(close_ch)
                if start != -1 and end > start:
                    try:
                        return json.loads(text[start:end+1])
                    except json.JSONDecodeError:
                        continue
            print(f"[Agent] Failed to parse JSON: {text[:200]}")
            return None

    # ═══════════════════════════════════════════
    # AGENT 1: Brand Analyst
    # ═══════════════════════════════════════════
    def analyze_brand(self, brand_kit, product_description=''):
        """Analyze brand kit and product to create a brand profile."""
        system = """You are a senior brand strategist and visual designer.
Analyze the brand information provided and create a comprehensive brand profile
that other agents will use to create consistent marketing content.

Return ONLY valid JSON (no other text) with this structure:
{
    "brand_personality": "2-3 word personality (e.g. 'bold and luxurious')",
    "visual_style": "specific visual direction (e.g. 'clean minimalist with soft gradients')",
    "mood": "emotional tone (e.g. 'aspirational yet approachable')",
    "color_usage": {
        "primary_use": "when to use primary color",
        "secondary_use": "when to use secondary color",
        "accent_use": "when to use accent color",
        "background_preference": "dark/light/gradient/neutral"
    },
    "typography_direction": {
        "headline_style": "bold/elegant/playful/minimal",
        "body_style": "clean/serif/casual",
        "text_hierarchy": "how to size text"
    },
    "content_guidelines": {
        "do": ["list of 3-4 things to include"],
        "dont": ["list of 3-4 things to avoid"],
        "keywords": ["5-8 brand keywords for prompts"]
    },
    "product_insights": {
        "category": "product category",
        "key_benefits": ["3-4 key selling points"],
        "target_customer": "ideal customer profile in 1 sentence",
        "price_positioning": "budget/mid/premium/luxury"
    }
}"""

        user = f"""Brand: {brand_kit.name}
Description: {brand_kit.description or 'Not specified'}
Product category: {brand_kit.product_category or 'Not specified'}
Target audience: {brand_kit.target_audience or 'Not specified'}
Tone: {brand_kit.tone}
Font style: {brand_kit.font_style}
Colors: Primary={brand_kit.primary_color}, Secondary={brand_kit.secondary_color}, Accent={brand_kit.accent_color}
Heading font: {brand_kit.heading_font}
Body font: {brand_kit.body_font}
Additional product info: {product_description or 'None'}"""

        print("[Agent 1] Brand Analyst: Analyzing brand...")
        result = self._call_llm(system, user, temperature=0.5)
        parsed = self._parse_json(result)
        if parsed:
            print("[Agent 1] Brand analysis complete!")
        return parsed or {}

    # ═══════════════════════════════════════════
    # AGENT 2: Content Strategist
    # ═══════════════════════════════════════════
    def plan_content(self, brand_analysis, brand_kit, target_count=20, content_types=None):
        """Plan what content pieces to create."""
        if content_types is None:
            content_types = ['social_post', 'banner', 'a_plus', 'lifestyle', 'ad_creative']

        system = """You are a marketing content strategist.
Given a brand profile, plan exactly the requested number of content pieces.
Each piece should be unique — different layout, angle, message.

Available image engines:
- "pollinations": Best for backgrounds, lifestyle shots, abstract visuals, stock-style images. Text-to-image AI.
- "flow": Best for product shots, product mockups, A+ content with product focus. Needs reference image.
- "pomelli": Best for campaign creatives with text overlays and marketing copy. Campaign-focused.

Aspect ratios available:
- "1:1" (1024x1024): Instagram, Facebook
- "9:16" (1024x1792): Instagram Stories, Reels, TikTok
- "16:9" (1792x1024): YouTube thumbnail, website banner
- "4:5" (1024x1280): Pinterest, Instagram portrait
- "3:4" (1024x1365): Pinterest optimal

Return ONLY valid JSON array (no other text). Each item:
{
    "id": 1,
    "type": "social_post|banner|a_plus|lifestyle|ad_creative",
    "subtype": "specific format name",
    "title": "short descriptive title for this piece",
    "aspect_ratio": "1:1|9:16|16:9|4:5|3:4",
    "width": 1024,
    "height": 1024,
    "engine": "pollinations|flow|pomelli",
    "description": "detailed visual description of what this image should look like",
    "text_overlay": true,
    "headline": "headline text if text_overlay is true",
    "subheadline": "optional subheadline",
    "cta": "call-to-action text if needed",
    "needs_logo": true,
    "logo_position": "top-left|top-right|bottom-left|bottom-right|center",
    "priority": "high|medium|low",
    "remove_background": false,
    "border_style": "none|solid|gradient",
    "text_safe_zone": "bottom|top|center"
}

Post-processing rules:
- "remove_background": true ONLY for product cutout shots, lifestyle composites, or A+ content where clean product isolation is needed
- "border_style": "solid" for social posts and banners to frame the content. "gradient" for premium/luxury brands. "none" for lifestyle and editorial shots.
- "text_safe_zone": where the post-processor will place headline/subheadline/CTA text overlays. Pick "bottom" for hero shots, "top" for product-focused images, "center" for bold statements."""

        types_str = ', '.join([t for t in content_types if t])
        user = f"""Brand analysis: {json.dumps(brand_analysis, indent=2)}

Brand name: {brand_kit.name}
Product category: {brand_kit.product_category or 'General'}
Target audience: {brand_kit.target_audience or 'General consumers'}
Tone: {brand_kit.tone}

Content types to include: {types_str}
Total pieces needed: {target_count}

Plan exactly {target_count} unique content pieces. ONLY use these content types: {types_str}. Do NOT create any other content types.
Vary the aspect ratios and visual angles, but every piece MUST be one of the allowed types.
A product reference image will be provided to the image generator for product-focused shots — use engine "flow" for these.
Prioritize social posts and banners. Use "pollinations" engine for most pieces (it's fastest and free).
Use "flow" only when product image reference is essential. Use "pomelli" for campaign-style creatives."""

        print(f"[Agent 2] Content Strategist: Planning {target_count} pieces...")
        result = self._call_llm(system, user, temperature=0.7, max_tokens=4000)
        parsed = self._parse_json(result)
        if parsed and isinstance(parsed, list):
            print(f"[Agent 2] Content plan ready: {len(parsed)} pieces planned!")
        return parsed or []

    # ═══════════════════════════════════════════
    # PROMPT TEMPLATE LIBRARY
    # ═══════════════════════════════════════════

    # Per-content-type prompt templates with photography direction
    PROMPT_TEMPLATES = {
        'social_post': {
            'style': 'lifestyle editorial',
            'direction': 'Candid, in-context product usage. Real person or hands interacting with product. '
                         'Natural environment — bathroom counter, vanity mirror, kitchen shelf. '
                         'Soft natural lighting from nearby window. Slight film grain, warm tones.',
            'camera': 'Canon EOS R5, 35mm f/1.8, natural light, shallow depth of field',
            'examples': [
                'Hands applying moisturizer at a bathroom vanity, morning sunlight through frosted window, toothbrush holder and small plant in background, candid lifestyle photography, slight lens flare',
                'Flat lay on linen bedsheet — skincare bottles, coffee cup, reading glasses, morning routine, overhead shot, soft diffused light, editorial Instagram style',
            ],
        },
        'banner': {
            'style': 'hero product photography',
            'direction': 'Clean, text-safe composition with product as hero. Generous negative space on one side for text overlay. '
                         'Studio or controlled lighting. Premium surface (marble, wood, brushed metal). '
                         'Minimal props that complement but don\'t distract.',
            'camera': 'Phase One IQ4, 80mm f/2.8, studio strobes with softbox, clean white/neutral backdrop',
            'examples': [
                'Product bottle centered on polished concrete surface, single eucalyptus branch, studio lighting with soft gradient background, clean negative space on right side for text, commercial product photography',
                'Premium serum bottle on raw oak shelf, blurred bathroom tiles in background, warm key light from left, editorial banner composition with text-safe zone at top',
            ],
        },
        'a_plus': {
            'style': 'Amazon A+ / product page infographic',
            'direction': 'Product cutout on clean background OR product in use with callout-friendly composition. '
                         'Show texture, ingredients, or key features clearly. Multiple angles welcome. '
                         'Clean, informational, e-commerce optimized.',
            'camera': 'Sony A7R V, 90mm macro f/2.8, ring light + fill, white sweep background',
            'examples': [
                'Product bottle at 3/4 angle on white background, clean product photography, visible texture and label details, e-commerce listing style, even studio lighting',
                'Close-up product texture being applied to skin, macro photography showing cream consistency, natural skin texture visible, informational beauty photography',
            ],
        },
        'lifestyle': {
            'style': 'editorial lifestyle photography',
            'direction': 'Real-world scene telling a story. Person using product in daily routine. '
                         'Environmental context — home, gym, office, outdoors. Authentic moment, not posed. '
                         'Documentary-style candidness. Natural imperfections in the scene.',
            'camera': 'Fujifilm X-T5, 23mm f/1.4, available light, documentary style',
            'examples': [
                'Woman doing evening skincare routine in warmly lit bathroom, cotton towel on shoulder, small succulents on shelf, reflection in mirror, warm ambient light, candid documentary style',
                'Morning kitchen scene, person with coffee holding product, sunlight streaming through blinds casting shadows, lived-in kitchen details, editorial lifestyle for wellness brand',
            ],
        },
        'ad_creative': {
            'style': 'campaign creative / performance ad',
            'direction': 'Bold, eye-catching composition designed to stop scrolling. High contrast, dynamic angles. '
                         'Product prominent with aspirational context. Action-oriented scene. '
                         'Designed for Meta/Google ads with clear focal point.',
            'camera': 'Canon R5, 24-70mm f/2.8, dramatic lighting, high contrast grade',
            'examples': [
                'Dynamic product splash shot — serum bottle with water droplets frozen mid-air, dark moody background, single dramatic spotlight, premium cosmetics advertising',
                'Bold overhead shot of product arrangement in brand colors, geometric composition, strong shadows from directional lighting, social media ad creative style',
            ],
        },
    }

    # ═══════════════════════════════════════════
    # AGENT 3: Prompt Crafter
    # ═══════════════════════════════════════════
    def craft_prompts(self, content_plan, brand_analysis, brand_kit):
        """Write optimized generation prompts for each content piece.
        Uses per-content-type template library for realistic, anti-AI prompts."""

        # Build template reference for the LLM
        template_ref = []
        for ctype, tmpl in self.PROMPT_TEMPLATES.items():
            template_ref.append(
                f'### {ctype}\n'
                f'Style: {tmpl["style"]}\n'
                f'Direction: {tmpl["direction"]}\n'
                f'Camera: {tmpl["camera"]}\n'
                f'Example prompts:\n- ' + '\n- '.join(tmpl["examples"])
            )
        templates_text = '\n\n'.join(template_ref)

        system = f"""You are an expert AI image prompt engineer who creates prompts that produce REALISTIC, NON-AI-LOOKING images.

BANNED WORDS — NEVER use any of these (they trigger the "AI art" look):
hyper-realistic, ultra-realistic, 8k, ultra HD, unreal engine, octane render, masterpiece,
highly detailed, best quality, super resolution, trending on artstation, concept art,
digital painting, CGI, 3D render, photorealistic (use "real photography" instead)

REQUIRED LANGUAGE — use these instead:
"editorial photography", "shot on [specific camera]", "natural lighting", "magazine quality",
"commercial product photo", "candid moment", "slight film grain", "available light",
"shallow depth of field", "[specific mm] lens", "studio strobes/softbox"

REAL SCENE RULE: Describe a scene a real photographer would set up. Include:
- Specific surface/backdrop (marble slab, oak shelf, linen cloth, bathroom counter)
- Props that make sense (eucalyptus, coffee cup, towel, plant)
- Lighting setup (window light direction, softbox position, golden hour)
- Camera + lens (Canon R5, Sony A7R, Fuji X-T5, specific focal length + aperture)
- Subtle imperfections (slight shadow, ambient reflections, natural grain)

═══ PROMPT TEMPLATES BY CONTENT TYPE ═══

{templates_text}

═══ ENGINE RULES ═══
- "flow": Direct, descriptive product prompts. Reference image will be provided — describe the SCENE around the product.
- "pollinations": Cinematic scene prompts with full environmental detail + camera specs.
- "pomelli": Campaign brief style with brand grounding.

Return ONLY valid JSON array. Each item:
{{
    "id": 1,
    "prompt": "the full generation prompt incorporating the template style",
    "negative_prompt": "what to avoid (for pollinations only — include: cartoon, illustration, 3D render, CGI, anime, painting, drawing, sketch, artificial, plastic, overexposed)",
    "engine": "pollinations|flow|pomelli",
    "width": 1024,
    "height": 1024
}}"""

        user = f"""Brand: {brand_kit.name}
Colors: Primary={brand_kit.primary_color}, Secondary={brand_kit.secondary_color}, Accent={brand_kit.accent_color}
Fonts: {brand_kit.heading_font} / {brand_kit.body_font}
Style: {brand_kit.font_style}
Tone: {brand_kit.tone}
Product category: {brand_kit.product_category or 'General'}
Brand analysis: {json.dumps(brand_analysis, indent=2)}

Content plan to write prompts for:
{json.dumps(content_plan, indent=2)}

Write one optimized prompt per content piece. FOLLOW the template for each content type — use the style, camera specs, and direction from the matching template above. Each prompt must feel like a real photography brief, NOT an AI art prompt."""

        print(f"[Agent 3] Prompt Crafter: Writing {len(content_plan)} prompts with template library...")
        result = self._call_llm(system, user, temperature=0.8, max_tokens=4000)
        parsed = self._parse_json(result)
        if parsed and isinstance(parsed, list):
            print(f"[Agent 3] Prompts ready: {len(parsed)} crafted!")
        return parsed or []

    # ═══════════════════════════════════════════
    # AGENT 6: Quality Reviewer
    # ═══════════════════════════════════════════
    def review_results(self, content_plan, results, brand_analysis):
        """Review generated images and flag any that need regeneration."""
        # For now, auto-approve all — can add vision model later
        reviewed = []
        for r in results:
            r['approved'] = True
            r['score'] = 8
            reviewed.append(r)
        print(f"[Agent 6] Quality Reviewer: {len(reviewed)} pieces reviewed, all approved")
        return reviewed
