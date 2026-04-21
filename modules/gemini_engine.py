"""
Mr.Creative — AI Prompt Engine (Groq)
Generates unique, non-repeating creative prompts every time.
"""

import re
import random
import time
import requests
import json


class GeminiEngine:
    """AI-powered prompt engine using Groq (Llama 3)."""

    def __init__(self, api_key):
        self.api_key = api_key
        self.api_url = 'https://api.groq.com/openai/v1/chat/completions'
        self.model = 'llama-3.3-70b-versatile'

    def _call_api(self, prompt, temperature=1.0, max_tokens=2000):
        """Call Groq API and return text response."""
        headers = {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json',
        }
        data = {
            'model': self.model,
            'messages': [
                {
                    'role': 'system',
                    'content': (
                        'You are a world-class creative director who always produces '
                        'fresh, original, and surprising ideas. You never repeat yourself. '
                        'Every response must be completely different from anything you have '
                        'written before. Be bold, specific, and vivid.'
                    ),
                },
                {'role': 'user', 'content': prompt},
            ],
            'max_tokens': max_tokens,
            'temperature': temperature,
            'top_p': 0.95,
        }
        response = requests.post(self.api_url, headers=headers, json=data, timeout=45)
        response.raise_for_status()
        result = response.json()
        return result['choices'][0]['message']['content'].strip()

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
        """Generate a unique seed block to bust LLM caching and force fresh output."""
        ts = int(time.time() * 1000)
        rand_id = random.randint(100000, 999999)
        # Random style direction
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
        # Random industries to push diversity
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
        # Random tones
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

You are a top-tier creative marketing director generating prompts for Pomelli (Google's AI marketing tool).

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

You are a top-tier creative marketing director generating prompts for Pomelli (Google's AI marketing tool).

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

        text = self._call_api(prompt, temperature=1.0)
        results = self._parse_numbered_list(text)[:count]

        # Fallback: if parsing failed or too few results, retry once with simpler prompt
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
        # Clean up any numbering or quotes
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
        # Remove any "Enhanced prompt:" or similar prefixes
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