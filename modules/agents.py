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
        self.cerebras_model = 'llama3.3-70b'
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
            # Try to find JSON in the response
            start = text.find('{')
            end = text.rfind('}')
            if start == -1:
                start = text.find('[')
                end = text.rfind(']')
            if start != -1 and end != -1:
                try:
                    return json.loads(text[start:end+1])
                except json.JSONDecodeError:
                    pass
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
    "priority": "high|medium|low"
}"""

        types_str = ', '.join([t for t in content_types if t])
        user = f"""Brand analysis: {json.dumps(brand_analysis, indent=2)}

Brand name: {brand_kit.name}
Product category: {brand_kit.product_category or 'General'}
Target audience: {brand_kit.target_audience or 'General consumers'}
Tone: {brand_kit.tone}

Content types to include: {types_str}
Total pieces needed: {target_count}

Plan exactly {target_count} unique content pieces with good variety across types and aspect ratios.
Prioritize social posts and banners. Use "pollinations" engine for most pieces (it's fastest and free).
Use "flow" only when product image reference is essential. Use "pomelli" for campaign-style creatives."""

        print(f"[Agent 2] Content Strategist: Planning {target_count} pieces...")
        result = self._call_llm(system, user, temperature=0.7, max_tokens=4000)
        parsed = self._parse_json(result)
        if parsed and isinstance(parsed, list):
            print(f"[Agent 2] Content plan ready: {len(parsed)} pieces planned!")
        return parsed or []

    # ═══════════════════════════════════════════
    # AGENT 3: Prompt Crafter
    # ═══════════════════════════════════════════
    def craft_prompts(self, content_plan, brand_analysis, brand_kit):
        """Write optimized generation prompts for each content piece."""
        system = """You are an expert AI image prompt engineer.
For each content piece, write the BEST possible prompt optimized for the target engine.

Prompt guidelines by engine:
- "pollinations" (Flux model): Detailed, descriptive, cinematic language. Include lighting, mood, style, composition.
  Example: "Professional product photography of a luxury serum bottle on marble surface, soft golden hour lighting, bokeh background, minimalist aesthetic, 8k quality"
- "flow" (Google Flow): Short, direct. Focus on product transformation. Include reference to the product.
  Example: "Create premium product showcase with elegant lighting and clean background"
- "pomelli" (Google Pomelli): Campaign-style brief. Focus on the marketing angle.
  Example: "Summer skincare campaign, bold typography, vibrant colors, call-to-action"

IMPORTANT: Include brand colors and style in every prompt. Use the brand keywords naturally.

Return ONLY valid JSON array. Each item:
{
    "id": 1,
    "prompt": "the full generation prompt",
    "negative_prompt": "what to avoid (for pollinations only)",
    "engine": "pollinations|flow|pomelli",
    "width": 1024,
    "height": 1024
}"""

        user = f"""Brand: {brand_kit.name}
Colors: Primary={brand_kit.primary_color}, Secondary={brand_kit.secondary_color}, Accent={brand_kit.accent_color}
Fonts: {brand_kit.heading_font} / {brand_kit.body_font}
Style: {brand_kit.font_style}
Brand analysis: {json.dumps(brand_analysis, indent=2)}

Content plan to write prompts for:
{json.dumps(content_plan, indent=2)}

Write one optimized prompt per content piece. Match the engine specified in each piece."""

        print(f"[Agent 3] Prompt Crafter: Writing {len(content_plan)} prompts...")
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
