"""
Mr.Creative — AI Prompt Engine (Google Gemini)
Generates unique, non-repeating creative prompts using Gemini Flash.
"""

import re
import random
import time
from google import genai


class GeminiEngine:
    """AI-powered prompt engine using Google Gemini."""

    def __init__(self, api_key):
        self.api_key = api_key
        self.client = genai.Client(api_key=api_key)
        self.model = 'gemini-2.0-flash'

    def _call_api(self, prompt, temperature=1.0, max_tokens=2000):
        """Call Gemini API and return text response."""
        response = self.client.models.generate_content(
            model=self.model,
            contents=prompt,
            config=genai.types.GenerateContentConfig(
                temperature=temperature,
                max_output_tokens=max_tokens,
            ),
        )
        return response.text.strip()

    def _parse_numbered_list(self, text):
        """Parse a numbered list response into clean strings."""
        prompts = []
        for line in text.strip().split('\n'):
            line = line.strip()
            if not line:
                continue
            cleaned = re.sub(r'^[\d]+[\.\)\:\-]\s*', '', line)
            cleaned = re.sub(r'^[\-\*]\s*', '', cleaned)
            cleaned = cleaned.strip('"\'')
            if cleaned and len(cleaned) > 10:
                prompts.append(cleaned)
        return prompts

    def _random_seed_block(self):
        """Generate a unique seed block to force fresh output."""
        ts = int(time.time() * 1000)
        rand_id = random.randint(100000, 999999)
        styles = [
            'minimalist Scandinavian', 'bold maximalist', 'retro 70s warmth',
            'moody film noir', 'bright pop art', 'soft watercolor pastels',
            'raw brutalist', 'dreamy ethereal', 'editorial magazine',
            'tropical lush', 'futuristic neon', 'cozy cottagecore',
            'luxury art deco', 'gritty urban', 'whimsical fairy tale',
            'clean clinical', 'sunset golden hour', 'misty morning forest',
            'vibrant street food', 'monochrome high contrast',
            'Japanese wabi-sabi', 'Mediterranean sun-drenched',
            'cyberpunk dystopia', 'French provincial charm',
        ]
        industries = [
            'artisanal coffee', 'sustainable fashion', 'luxury skincare',
            'organic baby food', 'smart home tech', 'indie perfume',
            'plant-based protein', 'vintage eyewear', 'fitness wearables',
            'handmade ceramics', 'craft beer', 'eco cleaning products',
            'pet wellness', 'boutique hotel', 'electric bikes',
            'gourmet chocolate', 'yoga studio', 'kids educational toys',
            'natural hair care', 'meditation app', 'street sneakers',
            'artisan cheese', 'travel backpacks', 'home fragrance candles',
        ]
        tones = [
            'playful and energetic', 'sophisticated and calm',
            'bold and rebellious', 'warm and inviting',
            'mysterious and intriguing', 'fresh and youthful',
            'nostalgic and comforting', 'luxurious and aspirational',
            'earthy and authentic', 'sleek and futuristic',
        ]
        style = random.choice(styles)
        industry = random.choice(industries)
        tone = random.choice(tones)
        return style, industry, tone, f"SEED-{ts}-{rand_id}"

    def generate_prompts(self, base_text='', category='general', count=5):
        count = min(count, 8)
        category_context = {
            'general': 'product photography, social media campaigns, brand storytelling, and seasonal promotions',
            'product': 'product photography — studio shots, lifestyle integration, flat lays, close-ups',
            'campaign': 'full marketing campaigns — multi-platform, seasonal, launch events',
            'social': 'social media content — Instagram carousels, TikTok hooks, LinkedIn thought-leadership',
            'photoshoot': 'AI product photoshoots — creative lighting, styled environments, artistic compositions',
            'video': 'short-form video content — animations, product reveals, behind-the-scenes',
        }
        ctx = category_context.get(category, category_context['general'])
        style, industry_hint, tone, seed = self._random_seed_block()

        if base_text:
            prompt = f"""[{seed}]

You are a world-class creative marketing director generating prompts for Pomelli (Google's AI marketing tool).

TASK: Generate exactly {count} UNIQUE creative prompts based on this idea:
"{base_text}"

CREATIVE DIRECTION FOR THIS BATCH:
- Visual style inspiration: {style}
- Tone: {tone}
- Focus area: {ctx}

RULES:
- Each prompt MUST be completely different in concept, angle, and approach
- Each prompt: 2-3 sentences, vivid imagery, specific details (colors, textures, lighting, setting)
- Include specific creative directions like camera angles, color palettes, props, moods
- Do NOT write generic marketing copy — write detailed creative briefs
- Do NOT repeat words or phrases across prompts
- Surprise me — take unexpected creative angles on the idea

Return ONLY {count} prompts, numbered 1-{count}, one per line. No introductions or explanations."""
        else:
            prompt = f"""[{seed}]

You are a world-class creative marketing director generating prompts for Pomelli (Google's AI marketing tool).

TASK: Generate exactly {count} WILDLY DIVERSE creative marketing prompts.

CREATIVE DIRECTION FOR THIS BATCH:
- Visual style inspiration: {style}
- Tone: {tone}
- Include at least one prompt inspired by: {industry_hint}
- Focus area: {ctx}

RULES:
- Each prompt MUST target a DIFFERENT industry/product type
- Each prompt: 2-3 sentences, vivid imagery, specific details (colors, textures, lighting, setting)
- Include specific creative directions like camera angles, color palettes, props, moods
- Do NOT write generic marketing copy — write detailed creative briefs
- Do NOT repeat words or phrases across prompts
- Cover a MIX of: food & beverage, beauty, fashion, tech, home, wellness, lifestyle
- Surprise me with unexpected creative angles

Return ONLY {count} prompts, numbered 1-{count}, one per line. No introductions or explanations."""

        # Load recent prompts from DB to avoid repetition
        avoid_block = ''
        try:
            from flask import current_app
            from models import Prompt
            recent = Prompt.query.order_by(Prompt.created_at.desc()).limit(20).all()
            if recent:
                recent_texts = [p.text[:80] for p in recent if p.text]
                avoid_block = "\n\nDO NOT repeat or closely resemble any of these recent prompts:\n" + "\n".join(f"- {t}" for t in recent_texts)
        except Exception:
            pass

        text = self._call_api(prompt + avoid_block, temperature=1.0)
        results = self._parse_numbered_list(text)[:count]

        if len(results) < count // 2:
            fallback = f"""[{seed}-RETRY]
Generate {count} creative marketing prompts for AI product photography and campaigns.
Style: {style}. Tone: {tone}.
Numbered 1-{count}, one per line. Be specific and vivid."""
            text = self._call_api(fallback, temperature=1.0)
            results = self._parse_numbered_list(text)[:count]

        return results

    def refine_prompt(self, original_prompt, instruction):
        _, _, _, seed = self._random_seed_block()
        prompt = f"""[{seed}]

You are a creative director refining a marketing prompt.

ORIGINAL PROMPT:
"{original_prompt}"

CLIENT FEEDBACK:
"{instruction}"

Rewrite the prompt incorporating the feedback. Make it MORE specific, MORE vivid, and MORE detailed than the original. Add concrete visual details: colors, textures, lighting, composition, mood.

Return ONLY the refined prompt as a single paragraph. No quotes, no explanations."""

        result = self._call_api(prompt, temperature=0.9)
        result = re.sub(r'^[\d]+[\.\)\:]\s*', '', result.strip())
        result = result.strip('"\'')
        return result

    def enhance_prompt(self, prompt_text):
        style, _, tone, seed = self._random_seed_block()
        prompt = f"""[{seed}]

You are an expert creative director enhancing a basic marketing prompt into a detailed creative brief.

BASIC PROMPT:
"{prompt_text}"

ENHANCEMENT DIRECTION:
- Visual style to explore: {style}
- Tone: {tone}

Transform this into a rich, detailed creative brief by adding ALL of the following:
1. Specific visual style and art direction (lighting, shadows, color temperature)
2. Color palette (name 2-3 specific colors)
3. Composition and camera angle
4. Props, textures, and environmental details
5. Mood and emotional tone
6. Target platform (Instagram, TikTok, print, etc.)

Return ONLY the enhanced prompt as a single paragraph (3-5 sentences). No quotes, no labels, no explanations."""

        result = self._call_api(prompt, temperature=1.0)
        result = re.sub(r'^[\d]+[\.\)\:]\s*', '', result.strip())
        result = result.strip('"\'')
        result = re.sub(r'^(Enhanced|Refined|Updated|Here\'s the|The enhanced)\s*(prompt|version|brief)?[\:\-]?\s*', '', result, flags=re.IGNORECASE)
        return result.strip()

    def generate_variations(self, prompt_text, count=3):
        count = min(count, 5)
        style, _, tone, seed = self._random_seed_block()
        prompt = f"""[{seed}]

Generate {count} creative VARIATIONS of this marketing prompt.
Same core product/concept, but COMPLETELY different creative execution each time.

ORIGINAL:
"{prompt_text}"

VARIATION DIRECTIONS — each variation MUST differ in:
- Visual style (e.g. one minimalist, one maximalist, one editorial)
- Setting/environment
- Color palette
- Mood and tone

Return ONLY {count} variations, numbered 1-{count}, one per line. Each should be 2-3 sentences."""

        text = self._call_api(prompt, temperature=1.0)
        return self._parse_numbered_list(text)[:count]

    def suggest_categories(self, business_description):
        _, _, _, seed = self._random_seed_block()
        prompt = f"""[{seed}]

Based on this business: "{business_description}"

Suggest 5 UNIQUE and CREATIVE marketing campaign themes.
Go beyond obvious ideas — think seasonal moments, cultural trends, lifestyle angles, and emotional hooks.

Format each as: "Theme Name: one-sentence description"
Return ONLY 5 items, numbered 1-5."""

        results = []
        text = self._call_api(prompt, temperature=1.0)
        for line in text.strip().split('\n'):
            line = line.strip()
            if not line:
                continue
            cleaned = re.sub(r'^[\d]+[\.\)\:]\s*', '', line)
            if ':' in cleaned:
                name, desc = cleaned.split(':', 1)
                results.append({'name': name.strip(), 'description': desc.strip()})
        return results[:5]
