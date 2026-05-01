"""
Mr.Creative Copywriter
AI-powered caption, hashtag, and description generator.
Uses Groq (primary) / Cerebras (fallback) — same pattern as AgentEngine.
Replaces broken Gemini-based caption generator.

Learnings from ericosiu/ai-marketing-skills:
- Instagram: hook in first line, 15-25 hashtags, mix popular + niche
- Pinterest: SEO-optimized, keyword-rich, 2-5 targeted hashtags
- Anti-AI: no corporate jargon, no significance inflation, specific over vague
"""

import json


class Copywriter:
    """Generate marketing copy (captions, hashtags, descriptions) via LLM."""

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
            except ImportError:
                pass
        self._using_cerebras = False

    def _call_llm(self, system_prompt, user_prompt, temperature=0.8, max_tokens=1000):
        """Call LLM with Groq → Cerebras fallback."""
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
                print("[Copywriter] Groq rate limited — switching to Cerebras")
                self._using_cerebras = True
                return self._call_llm(system_prompt, user_prompt, temperature, max_tokens)
            print(f"[Copywriter] LLM error: {e}")
            return None

    # ═══════════════════════════════════════════
    # Platform-specific caption guides
    # ═══════════════════════════════════════════

    PLATFORM_GUIDES = {
        'pinterest': {
            'rules': 'Pinterest pin description — SEO-optimized, keyword-rich, 2-3 sentences. '
                     'Front-load keywords naturally. Use 2-5 targeted hashtags at the end. '
                     'Include product benefits, not just features. Write for search discovery.',
            'hashtag_count': '3-5',
            'tone': 'informative, aspirational, search-friendly',
            'example': 'Hydrate and protect your skin with this lightweight vitamin C serum. '
                       'Perfect for morning routines — absorbs quickly, no sticky residue. '
                       '#skincare #vitaminC #morningroutine #glowingskin',
        },
        'instagram': {
            'rules': 'Instagram caption — hook in the FIRST LINE (before "more" truncation). '
                     'Body: 2-3 punchy sentences delivering value. CTA at the end. '
                     'Hashtags: 15-25 at the end, mix of popular (500K+) and niche (10K-100K). '
                     'Conversational, not corporate. Use line breaks for readability.',
            'hashtag_count': '15-25',
            'tone': 'conversational, engaging, authentic',
            'example': 'Your morning routine is missing this one step 👇\n\n'
                       'Vitamin C before sunscreen = the glow-up your skin deserves. '
                       'This serum absorbs in 30 seconds flat — no pilling, no stickiness.\n\n'
                       'Drop a ☀️ if you\'re adding this to your AM routine\n\n'
                       '#skincare #vitaminc #morningroutine #skincareroutine #glowingskin '
                       '#serumreview #beautytips #skincareobsessed',
        },
        'facebook': {
            'rules': 'Facebook post — conversational, engaging, clear CTA. '
                     '2-4 sentences. Ask a question or share a tip to drive comments. '
                     '3-5 hashtags max. Emojis sparingly (1-2).',
            'hashtag_count': '3-5',
            'tone': 'friendly, conversational, community-focused',
            'example': 'Ever wonder why your moisturizer feels heavy by noon? 🤔\n\n'
                       'Try switching to a water-based formula — your skin will thank you. '
                       'We\'ve been loving this lightweight gel cream for summer.\n\n'
                       '#skincaretips #summerskincare #beautyhack',
        },
        'general': {
            'rules': 'Marketing description — clear, benefit-focused, 2-3 sentences. '
                     'Lead with the key benefit. Include one specific detail or number. '
                     'End with a soft CTA. 3-5 hashtags.',
            'hashtag_count': '3-5',
            'tone': 'professional, benefit-focused',
            'example': 'Clinically proven to boost hydration by 72% in just 4 weeks. '
                       'This serum combines hyaluronic acid with niacinamide for visible results. '
                       'Try it today — your skin will notice the difference.\n\n'
                       '#skincare #hydration #beautyessentials',
        },
    }

    # ═══════════════════════════════════════════
    # Single caption generation
    # ═══════════════════════════════════════════

    def generate_caption(self, prompt_text, platform='pinterest', product_url='',
                         brand_name='', tone='professional'):
        """Generate caption + hashtags for a single image/post.

        Args:
            prompt_text: Description of the image/product
            platform: pinterest, instagram, facebook, general
            product_url: Optional product link
            brand_name: Brand name for context
            tone: Brand tone (professional, playful, luxury, etc.)

        Returns:
            dict with 'title', 'caption', 'hashtags'
        """
        guide = self.PLATFORM_GUIDES.get(platform, self.PLATFORM_GUIDES['general'])

        system = f"""You are a social media marketing copywriter who writes like a real person, NOT like AI.

PLATFORM: {platform}
RULES: {guide['rules']}
TONE: {tone}

ANTI-AI RULES (from humanizer checklist):
- NO corporate jargon: "leverage", "synergy", "innovative", "cutting-edge", "transformative"
- NO significance inflation: "game-changing", "revolutionary", "groundbreaking"
- NO filler: "In today's world", "It's no secret that", "When it comes to"
- NO fake enthusiasm: excessive exclamation marks, "absolutely love", "truly amazing"
- Write like a real person talking to a friend — specific, casual, genuine
- Use specific numbers and details over vague claims

Return ONLY this exact format (no other text):
TITLE: (catchy 5-10 word title)
CAPTION: (the caption following platform rules above)
HASHTAGS: (hashtags separated by spaces, {guide['hashtag_count']} tags)"""

        user = f"""Write a {platform} caption for:
"{prompt_text}"
{f'Brand: {brand_name}' if brand_name else ''}
{f'Product link: {product_url}' if product_url else ''}

Make it sound human and authentic. Follow the platform rules strictly."""

        result = self._call_llm(system, user, temperature=0.85)
        return self._parse_caption_response(result)

    # ═══════════════════════════════════════════
    # Batch caption generation (for pipeline)
    # ═══════════════════════════════════════════

    def generate_batch_captions(self, results, content_plan, brand_name='',
                                tone='professional', platform='instagram'):
        """Generate captions for all images in a pipeline batch.

        Args:
            results: List of result dicts from pipeline (with 'title', 'type', etc.)
            content_plan: Content plan from Agent 2
            brand_name: Brand name
            tone: Brand tone
            platform: Target platform for captions

        Returns:
            Updated results list with 'caption', 'hashtags' added to each
        """
        # Build batch prompt — all images at once for consistency
        items = []
        for i, result in enumerate(results):
            if 'error' in result:
                continue
            plan_idx = result.get('id', i + 1) - 1
            plan_item = content_plan[plan_idx] if plan_idx < len(content_plan) else {}
            items.append({
                'id': result.get('id', i + 1),
                'title': result.get('title', plan_item.get('title', f'Image {i+1}')),
                'type': result.get('type', plan_item.get('type', 'social_post')),
                'description': plan_item.get('description', ''),
                'headline': plan_item.get('headline', ''),
            })

        if not items:
            return results

        guide = self.PLATFORM_GUIDES.get(platform, self.PLATFORM_GUIDES['general'])

        system = f"""You are a social media copywriter for {brand_name or 'a brand'}.
Tone: {tone}
Platform: {platform}
Rules: {guide['rules']}

ANTI-AI: Write like a real person. No corporate speak. Specific details over vague claims.

Return ONLY a valid JSON array. Each item:
{{
    "id": 1,
    "caption": "the caption text",
    "hashtags": "hashtag1 hashtag2 hashtag3"
}}"""

        user = f"""Write {platform} captions for these {len(items)} images:

{json.dumps(items, indent=2)}

Each caption should be unique and match the content type. {guide['hashtag_count']} hashtags per caption."""

        result = self._call_llm(system, user, temperature=0.8, max_tokens=3000)
        captions = self._parse_json(result)

        if captions and isinstance(captions, list):
            # Merge captions into results
            caption_map = {c['id']: c for c in captions if isinstance(c, dict)}
            for result_item in results:
                rid = result_item.get('id')
                if rid in caption_map:
                    result_item['caption'] = caption_map[rid].get('caption', '')
                    result_item['hashtags'] = caption_map[rid].get('hashtags', '')
            print(f"[Copywriter] Generated {len(captions)} captions")
        else:
            print("[Copywriter] Failed to parse batch captions")

        return results

    # ═══════════════════════════════════════════
    # Parsing helpers
    # ═══════════════════════════════════════════

    def _parse_caption_response(self, text):
        """Parse TITLE/CAPTION/HASHTAGS format response."""
        if not text:
            return {'title': '', 'caption': '', 'hashtags': ''}

        title = ''
        caption = ''
        hashtags = ''
        for line in text.strip().split('\n'):
            line = line.strip()
            if line.upper().startswith('TITLE:'):
                title = line[6:].strip().strip('"')
            elif line.upper().startswith('CAPTION:'):
                caption = line[8:].strip().strip('"')
            elif line.upper().startswith('HASHTAGS:'):
                hashtags = line[9:].strip()

        # If structured parsing failed, try to extract from raw text
        if not caption and text:
            lines = [l.strip() for l in text.split('\n') if l.strip()]
            if len(lines) >= 2:
                caption = lines[0]
                # Find hashtag line
                for l in lines:
                    if '#' in l:
                        hashtags = l
                        break

        return {
            'title': title,
            'caption': caption,
            'hashtags': hashtags,
        }

    def _parse_json(self, text):
        """Extract JSON from LLM response."""
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
            for open_ch, close_ch in [('[', ']'), ('{', '}')]:
                start = text.find(open_ch)
                end = text.rfind(close_ch)
                if start != -1 and end > start:
                    try:
                        return json.loads(text[start:end+1])
                    except json.JSONDecodeError:
                        continue
            return None
