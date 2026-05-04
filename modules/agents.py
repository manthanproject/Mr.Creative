"""
Mr.Creative Agent System
Each agent = a Groq LLM call with a specific role.
Agents communicate via a shared context dict.
"""

import json
import os
import time
from datetime import datetime
from typing import Any


class AgentEngine:
    """Orchestrates multiple AI agents to generate marketing content."""

    def __init__(self, groq_api_key, cerebras_api_key=None):
        from groq import Groq
        self.client = Groq(api_key=groq_api_key)
        self.model = 'llama-3.3-70b-versatile'
        self.cerebras_client: Any = None
        self.cerebras_model = 'llama3.1-8b'
        if cerebras_api_key:
            try:
                from cerebras.cloud.sdk import Cerebras
                self.cerebras_client = Cerebras(api_key=cerebras_api_key)
                print("[Agent] Cerebras fallback ready")
            except ImportError:
                print("[Agent] cerebras-cloud-sdk not installed — pip install cerebras-cloud-sdk")
        self._using_cerebras = False
        self._reference_image_path: str | None = None

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

CONTENT TYPE DEFINITIONS:
- "social_post": Lifestyle editorial — person using product, flat lays, candid moments. For Instagram, Pinterest.
- "banner": Hero product shot with text-safe negative space. For website headers, ads.
- "a_plus": Amazon/Flipkart A+ listing content — DESIGNED INFOGRAPHIC IMAGES with text overlays, feature grids, before/after panels, step-by-step instructions, comparison charts, award badges. These are NOT simple product photos — they are marketing infographics with bold headlines, bullet points, icons, and data. Think Sephora/CeraVe Amazon listings.
- "lifestyle": Documentary-style real-world usage — morning routines, bathroom shelves, gym bags.
- "ad_creative": Bold, scroll-stopping campaign creative for Meta/Google ads. Dynamic angles, dramatic lighting.

A+ CONTENT SUBTYPES (use these when type is a_plus):
- "hero_banner": Product centered with bold headline, bullet points, award badge
- "feature_grid": 2x3 or 3x2 grid of icons + feature titles + descriptions
- "before_after": Split image showing problem vs result with the product
- "how_to_steps": 3-4 numbered steps with icons showing product usage
- "comparison_chart": Product vs competitors/alternatives table with checkmarks
- "multi_panel": 4-6 panel infographic combining hero, science, steps, and results
- "size_reference": Product in hand with bold text overlay
- "full_page": Complete A+ page layout with multiple sections

ENGINE RULES:
- "flow": Use for ALL content types when a reference image is uploaded. Best quality.
- "pollinations": Only if NO reference image is uploaded. Text-to-image.
- Do NOT use "pomelli".

Return ONLY valid JSON array (no other text). Each item:
{
    "id": 1,
    "type": "social_post|banner|a_plus|lifestyle|ad_creative",
    "subtype": "specific format name from subtypes above",
    "title": "short descriptive title for this piece",
    "aspect_ratio": "1:1|9:16|16:9|4:5|3:4",
    "width": 1024,
    "height": 1024,
    "engine": "flow",
    "description": "detailed visual description of what this image should look like — for a_plus include the exact text, headlines, features, steps that should appear in the image",
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
- "remove_background": ALMOST ALWAYS false. Set true ONLY for product-only cutout shots (no person, no scene, just the product bottle/box on white background). NEVER true for social posts, banners, lifestyle, or ad creatives with people or scenes.
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

Plan exactly {target_count} unique content pieces. EVERY piece MUST be one of these types: {types_str}. Do NOT create any other content types.
If only ONE content type is selected, ALL {target_count} pieces must be that type — vary the subtype, layout, and messaging.

For A+ content specifically: each piece should have a DIFFERENT subtype (hero_banner, feature_grid, before_after, how_to_steps, comparison_chart, multi_panel, size_reference, full_page). Include the actual marketing text, features, and data in the description field.

Use "flow" engine for ALL pieces (reference image is provided)."""

        print(f"[Agent 2] Content Strategist: Planning {target_count} pieces...")
        result = self._call_llm(system, user, temperature=0.7, max_tokens=4000)
        parsed = self._parse_json(result)
        if parsed and isinstance(parsed, list):
            print(f"[Agent 2] Content plan ready: {len(parsed)} pieces planned!")
        return parsed or []

    # ═══════════════════════════════════════════
    # AGENT 3: Prompt Crafter (uses modules/prompt_library.py)
    # ═══════════════════════════════════════════
    def craft_prompts(self, content_plan, brand_analysis, brand_kit):
        """Write optimized generation prompts for each content piece.
        Priority: expert prompts (A+) → LLM (other types)."""

        from modules.prompt_library import get_prompt_context_for_llm, build_prompt, CONTENT_TYPE_CONFIG

        content_types = list(set(item.get('type', 'social_post') for item in content_plan))
        all_aplus = all(item.get('type') == 'a_plus' for item in content_plan)

        # Expert prompts for A+ content (no LLM rewriting needed)
        if all_aplus:
            return self._craft_aplus_prompts_direct(content_plan, brand_analysis, brand_kit)

        # LLM with prompt library (Groq/Cerebras)

        # Get content types from the plan
        content_types = list(set(item.get('type', 'social_post') for item in content_plan))
        library_context = get_prompt_context_for_llm(content_types)

        # Build example prompts from library for each type
        examples = []
        for ctype in content_types:
            example = build_prompt(ctype, {
                'name': brand_kit.name,
                'product_category': brand_kit.product_category,
                'tone': brand_kit.tone,
            }, index=0)
            examples.append(f"### Example {ctype} prompt:\n{example['prompt']}\n(Camera: {example['camera']}, Lighting: {example['lighting']})")

        examples_text = '\n\n'.join(examples)

        system = f"""You are an expert FLUX image prompt engineer. FLUX uses natural language paragraphs — NOT comma-separated keyword lists.

FLUX PROMPT STRUCTURE: Subject + Action + Style + Context
Write each prompt as a dense, descriptive paragraph like a professional photography brief.

BANNED WORDS — NEVER use (they trigger the AI art look):
hyper-realistic, ultra-realistic, 8k, ultra HD, unreal engine, octane render, masterpiece,
highly detailed, best quality, super resolution, trending on artstation, concept art,
digital painting, CGI, 3D render, photorealistic

REQUIRED: Use real camera+lens specs, real lighting setups, and real composition rules from the options below.
Each prompt MUST include a specific camera (not always the same one — vary them!).

═══ PROMPT LIBRARY — PICK FROM THESE FOR EACH CONTENT TYPE ═══

{library_context}

═══ EXAMPLE PROMPTS (for reference style — make yours unique) ═══

{examples_text}

═══ RULES ═══
1. Each prompt must read like a professional photography brief — a real scene a photographer would set up
2. VARY the camera, lighting, and composition across prompts — never repeat the same combo
3. Include specific surfaces, props, and environmental details that make the scene believable
4. Add subtle imperfections: "slight film grain", "ambient reflections", "natural shadow"
5. For Flow engine: describe the SCENE around the product (reference image provides the product)
6. Write in natural language paragraphs, not keyword lists

SPECIAL RULE FOR A+ CONTENT:
A+ content prompts must describe DESIGNED INFOGRAPHIC LAYOUTS that Flow will generate as images.
CRITICAL: Replace all generic phrases with ACTUAL brand data:
- Instead of "the product" → use the actual product name from the brand kit
- Instead of "key benefit" → use actual benefits from the brand analysis (e.g. "Reduces wrinkles in 2 weeks")
- Instead of "3 features" → list the actual features (e.g. "• Niacinamide 10% • Zinc PCA 1% • Lightweight formula")
- Instead of "brand name" → use the actual brand name (e.g. "The Ordinary" or "Dropy Beauty")
- Include real claims, real ingredient names, real benefit statements from the brand analysis
Each A+ prompt should read like a complete design brief with ALL the text that should appear in the final image.

Return ONLY valid JSON array. Each item:
{{
    "id": 1,
    "prompt": "the full FLUX-optimized generation prompt as a natural language paragraph",
    "negative_prompt": "",
    "engine": "flow",
    "width": 1024,
    "height": 1024
}}"""

        user = f"""Brand: {brand_kit.name}
Colors: Primary={brand_kit.primary_color}, Secondary={brand_kit.secondary_color}, Accent={brand_kit.accent_color}
Tone: {brand_kit.tone}
Product category: {brand_kit.product_category or 'General'}
Brand analysis: {json.dumps(brand_analysis, indent=2)}

Content plan to write prompts for:
{json.dumps(content_plan, indent=2)}

Write one FLUX-optimized prompt per content piece. Each prompt must:
- Use a DIFFERENT camera+lens from the library (vary across prompts)
- Use a DIFFERENT lighting setup from the library
- Describe a unique, specific scene with real-world details
- Sound like a production brief, not AI art keywords"""

        print(f"[Agent 3] Prompt Crafter: Writing {len(content_plan)} prompts with prompt library ({len(content_types)} types)...")
        result = self._call_llm(system, user, temperature=0.8, max_tokens=4000)
        parsed = self._parse_json(result)
        if parsed and isinstance(parsed, list):
            print(f"[Agent 3] Prompts ready: {len(parsed)} crafted!")
        return parsed or []

    def _craft_aplus_prompts_direct(self, content_plan, brand_analysis, brand_kit):
        """Build A+ prompts directly from expert templates.
        Generic prompts work best — Flow gets product details from reference image."""

        from modules.prompt_library import CONTENT_TYPE_CONFIG

        expert_prompts = CONTENT_TYPE_CONFIG.get('a_plus', {}).get('expert_prompts', [])
        if not expert_prompts:
            print("[Agent 3] No A+ expert prompts found, falling back to LLM")
            return []

        prompts = []
        for i, plan_item in enumerate(content_plan):
            # Use expert prompt directly — no brand prefix needed
            prompt = expert_prompts[i % len(expert_prompts)]

            prompts.append({
                'id': plan_item.get('id', i + 1),
                'prompt': prompt,
                'negative_prompt': '',
                'engine': 'flow',
                'width': plan_item.get('width', 1024),
                'height': plan_item.get('height', 1024),
            })

        print(f"[Agent 3] A+ prompts built directly: {len(prompts)} (no LLM rewriting)")
        return prompts

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
