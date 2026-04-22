"""
Mr.Creative — AI Prompt Engine (Groq (Llama 3.3 70B))
Generates unique, non-repeating creative prompts using Llama 3.3 70B.
"""

import re
import random
import time
from groq import Groq


class GeminiEngine:
    """AI-powered prompt engine using Groq (Llama 3.3 70B)."""

    def __init__(self, api_key):
        self.api_key = api_key
        self.client = Groq(api_key=api_key)
        self.model = 'llama-3.3-70b-versatile'

    def _call_api(self, prompt, temperature=1.0, max_tokens=2000):
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return response.choices[0].message.content.strip()

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

    def generate_prompts(self, base_text='', category='general', count=5, tool='campaign'):
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

        # Tool-specific prompt engineering
        tool_config = {
            'campaign': {
                'role': 'a world-class creative marketing director generating campaign briefs for Pomelli (Google\'s AI marketing tool)',
                'format': 'Each prompt should be a marketing brief: describe the product/service, target audience, campaign goal, brand voice, visual theme, and call-to-action. Think like an ad agency creative director.',
                'rules': [
                    'Include target audience demographics or psychographics',
                    'Mention a specific campaign goal (awareness, conversion, launch, seasonal)',
                    'Suggest brand voice and visual direction (colors, mood, typography style)',
                    'Include a call-to-action or tagline direction',
                    'Each prompt: 2-3 sentences as a complete campaign brief',
                ],
                'examples_hint': 'campaign launches, seasonal promotions, product spotlights, brand storytelling',
            },
            'photoshoot': {
                'role': 'an expert product photography art director creating shot briefs for AI-powered product photoshoots',
                'format': 'Each prompt should describe the product, its physical appearance, the styled environment/setting, and lighting. Think like a commercial photographer planning a shoot.',
                'rules': [
                    'Describe the product physically (material, color, shape, size)',
                    'Specify the setting/environment (marble surface, botanical garden, kitchen counter, etc.)',
                    'Include lighting direction (soft window light, dramatic side light, golden hour, studio strobes)',
                    'Mention props and styling elements (flowers, fabrics, ingredients, lifestyle items)',
                    'Each prompt: 2-3 sentences as a photography shot brief',
                ],
                'examples_hint': 'studio product shots, lifestyle integration, flat lays, close-up detail shots, seasonal styled scenes',
            },
            'flow': {
                'role': 'an expert AI image generation prompt engineer creating prompts for Google Flow (Nano Banana 2 model)',
                'format': 'Each prompt should be an image generation prompt with visual composition, art style, colors, lighting, and quality keywords. Think like a Midjourney/DALL-E power user.',
                'rules': [
                    'Start with the main subject and composition',
                    'Include specific art/photography style (editorial, cinematic, minimalist, etc.)',
                    'Specify color palette and lighting (warm tones, cool blues, soft diffused, dramatic shadows)',
                    'Add quality boosters at the end (8K, ultra detailed, professional photography, etc.)',
                    'Do NOT include negative prompts or technical parameters',
                    'Each prompt: 1-2 sentences, dense with visual keywords, comma-separated style',
                ],
                'examples_hint': 'product hero shots, banner designs, social media visuals, brand imagery, artistic compositions',
            },
        }

        tc = tool_config.get(tool, tool_config['campaign'])

        style, industry_hint, tone, seed = self._random_seed_block()

        if base_text:
            prompt = f"""[{seed}]

You are {tc['role']}.

TASK: Generate exactly {count} UNIQUE creative prompts based on this idea:
"{base_text}"

CREATIVE DIRECTION FOR THIS BATCH:
- Visual style inspiration: {style}
- Tone: {tone}
- Focus area: {ctx}

FORMAT: {tc['format']}

RULES:
- Each prompt MUST be completely different in concept, angle, and approach
{''.join(f'{chr(10)}- {r}' for r in tc['rules'])}
- Do NOT write generic marketing copy — write detailed creative briefs
- Do NOT repeat words or phrases across prompts
- Surprise me — take unexpected creative angles on the idea

Return ONLY {count} prompts, numbered 1-{count}, one per line. No introductions or explanations."""
        else:
            prompt = f"""[{seed}]

You are {tc['role']}.

TASK: Generate exactly {count} WILDLY DIVERSE creative prompts.

CREATIVE DIRECTION FOR THIS BATCH:
- Visual style inspiration: {style}
- Tone: {tone}
- Include at least one prompt inspired by: {industry_hint}
- Focus area: {ctx}
- Prompt types to cover: {tc['examples_hint']}

FORMAT: {tc['format']}

RULES:
- Each prompt MUST target a DIFFERENT industry/product type
{''.join(f'{chr(10)}- {r}' for r in tc['rules'])}
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
You are {tc['role']}.
Generate {count} creative prompts for {tc['examples_hint']}.
Style: {style}. Tone: {tone}.
{tc['format']}
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

    def generate_social_caption(self, prompt_text, platform='pinterest', product_url=''):
        """Generate a social media caption with hashtags for a platform."""
        _, _, _, seed = self._random_seed_block()

        platform_guides = {
            'pinterest': 'Pinterest pin description — SEO-optimized, keyword-rich, 2-3 sentences max. Include relevant keywords naturally. No excessive hashtags — Pinterest uses 2-5 targeted hashtags at the end.',
            'instagram': 'Instagram caption — engaging, conversational, with a hook in the first line. Use 15-25 relevant hashtags at the end, mix of popular and niche.',
            'facebook': 'Facebook post — conversational, engaging, with a clear CTA. Use 3-5 hashtags max.',
        }

        guide = platform_guides.get(platform, platform_guides['pinterest'])

        prompt = f"""[{seed}]

You are a social media marketing expert.

TASK: Write a {platform} caption for this content:
"{prompt_text}"

PLATFORM GUIDE: {guide}
{f'PRODUCT LINK: {product_url}' if product_url else ''}

Return your response in this EXACT format (no other text):
TITLE: (a catchy 5-10 word title)
CAPTION: (the main caption text, 1-3 sentences)
HASHTAGS: (relevant hashtags separated by spaces, e.g. #skincare #beauty #luxury)"""

        result = self._call_api(prompt, temperature=0.9, max_tokens=500)

        title = ''
        caption = ''
        hashtags = ''
        for line in result.strip().split('\n'):
            line = line.strip()
            if line.upper().startswith('TITLE:'):
                title = line[6:].strip().strip('"')
            elif line.upper().startswith('CAPTION:'):
                caption = line[8:].strip().strip('"')
            elif line.upper().startswith('HASHTAGS:'):
                hashtags = line[9:].strip()

        return {
            'title': title,
            'caption': caption,
            'hashtags': hashtags,
        }
