"""
Night Orchestrator — ContentPlanner
Uses Groq (Llama 3.3 70B) to analyze trends, competitor data, and performance,
then generates a next-day content plan.
"""

import json
import logging
from datetime import datetime, date, timedelta

logger = logging.getLogger('night_ops')

# ── Brand context for LLM ──────────────────────────────────────────
BRAND_CONTEXT = """
You are a content strategist for two Indian e-commerce brands:

1. **dropy.in** — Shopify store selling imported beauty, health, and lifestyle products.
   Target: 18-35 urban Indian women interested in premium imported beauty/skincare.
   Products: CeraVe, Korean beauty, imported skincare, health supplements.
   Tone: Modern, aspirational, educational. Mix Hindi + English.
   Platforms: Instagram, Pinterest.

2. **Rudra Retails** (rudraretails.com) — Branded personal care products.
   Location: Navi Mumbai, Vashi.
   Target: Local customers, value-conscious buyers.
   Tone: Trustworthy, approachable, local.

Content types available:
- Campaign images (product-focused, lifestyle scenes)
- Photoshoot images (product on models/backgrounds)
- A+ content (infographics, benefit charts)
- Carousels (multi-image educational content)
- Social posts (Instagram stories, Pinterest pins)
- Banners (promotional, seasonal)
"""

PLAN_SYSTEM_PROMPT = f"""
{BRAND_CONTEXT}

You are generating a CONTENT PLAN for tomorrow based on:
1. Trending topics (what's hot in beauty/health)
2. Competitor activity (what rivals are posting)
3. Own performance data (what's working for us)

Generate a JSON content plan with this exact structure:
{{
  "plan_date": "YYYY-MM-DD",
  "theme": "Brief daily theme",
  "priority_products": ["product1", "product2"],
  "content_items": [
    {{
      "type": "campaign|photoshoot|carousel|story|pin|banner",
      "product": "specific product or category",
      "style": "aesthetic/mood description",
      "caption_idea": "caption suggestion",
      "hashtags": ["tag1", "tag2"],
      "platform": "instagram|pinterest|both",
      "priority": "high|medium|low",
      "reason": "why this content now"
    }}
  ],
  "posting_schedule": [
    {{"time": "10:00 AM", "platform": "instagram", "content_index": 0}},
    {{"time": "02:00 PM", "platform": "pinterest", "content_index": 1}}
  ],
  "insights": "2-3 sentence summary of why this plan makes sense"
}}

Generate 5-8 content items. Be specific about products and styles.
Respond ONLY with valid JSON, no markdown, no explanation.
"""


def run_content_planning(app, trend_data: dict, competitor_data: dict, performance_data: dict) -> dict:
    """
    Generate tomorrow's content plan using Groq LLM.
    Saves plan to content_plans table.
    Returns the plan dict.
    """
    with app.app_context():
        from models import db, ContentPlan, NightReport
        from config import Config

        groq_key = Config.GROQ_API_KEY
        if not groq_key:
            logger.error("[ContentPlanner] No GROQ_API_KEY configured")
            return {'error': 'No GROQ_API_KEY', 'plan': None}

        # Build the analysis prompt
        tomorrow = (date.today() + timedelta(days=1)).isoformat()

        user_prompt = _build_analysis_prompt(trend_data, competitor_data, performance_data, tomorrow)

        # Call Groq
        try:
            plan_json = _call_groq(groq_key, user_prompt)
            plan_data = json.loads(plan_json)
        except json.JSONDecodeError as e:
            logger.error(f"[ContentPlanner] Groq returned invalid JSON: {e}")
            # Try to extract JSON from response
            plan_data = _try_extract_json(plan_json)
            if not plan_data:
                return {'error': f'Invalid JSON from LLM: {e}', 'plan': None}
        except Exception as e:
            logger.error(f"[ContentPlanner] Groq API error: {e}")
            return {'error': str(e), 'plan': None}

        # Ensure plan_date is set
        plan_data['plan_date'] = plan_data.get('plan_date', tomorrow)

        # Save to DB
        try:
            plan = ContentPlan(
                plan_date=date.fromisoformat(plan_data['plan_date']),
                plan_data=json.dumps(plan_data, ensure_ascii=False),
                status='pending',
            )
            db.session.add(plan)

            # Also save as a night report
            report = NightReport(
                report_type='plan',
                report_data=json.dumps(plan_data, ensure_ascii=False),
                summary=plan_data.get('insights', ''),
                status='completed',
            )
            db.session.add(report)

            db.session.commit()
            logger.info(f"[ContentPlanner] Plan generated for {plan_data['plan_date']}")
        except Exception as e:
            logger.error(f"[ContentPlanner] DB save error: {e}")
            db.session.rollback()

        return {
            'plan_date': plan_data.get('plan_date'),
            'theme': plan_data.get('theme', ''),
            'content_count': len(plan_data.get('content_items', [])),
            'plan': plan_data,
        }


def _build_analysis_prompt(trends: dict, competitors: dict, performance: dict, plan_date: str) -> str:
    """Build the user prompt with all collected data."""

    # Summarize trends
    trend_summary = "No trend data available."
    if trends:
        pinterest_top = trends.get('top_pinterest', [])
        amazon_top = trends.get('top_amazon', [])
        parts = []
        if pinterest_top:
            pins = [p.get('title', '')[:80] for p in pinterest_top[:5]]
            parts.append(f"Pinterest trending: {', '.join(pins)}")
        if amazon_top:
            prods = [f"#{p.get('rank',0)} {p.get('title','')[:60]}" for p in amazon_top[:5]]
            parts.append(f"Amazon bestsellers: {', '.join(prods)}")
        if parts:
            trend_summary = '\n'.join(parts)

    # Summarize competitors
    comp_summary = "No competitor data available."
    if competitors and competitors.get('results'):
        parts = []
        for r in competitors['results'][:5]:
            handle = r.get('handle', '?')
            followers = r.get('follower_count', 0)
            eng = r.get('avg_engagement', 0)
            platform = r.get('platform', '?')
            parts.append(f"  {platform}/{handle}: {followers:,} followers, {eng}% engagement")
        comp_summary = '\n'.join(parts)

    # Summarize own performance
    perf_summary = "No performance data available."
    if performance:
        internal = performance.get('internal', {})
        gens = internal.get('generations', {})
        social = internal.get('social', {})
        parts = []
        if gens and not gens.get('error'):
            parts.append(f"  Generations: {gens.get('total', 0)} total, {gens.get('success_rate', 0)}% success, {gens.get('last_24h', 0)} today")
        if social and not social.get('error'):
            parts.append(f"  Social posts: {social.get('posted', 0)} posted, {social.get('pending_scheduled', 0)} scheduled")
        external = performance.get('external', {})
        ig = external.get('instagram', {})
        if ig and not ig.get('error'):
            parts.append(f"  Instagram: {ig.get('followers', 0):,} followers, {ig.get('avg_engagement', 0)}% engagement")
        perf_summary = '\n'.join(parts) if parts else perf_summary

    return f"""Generate a content plan for {plan_date}.

=== TRENDING NOW ===
{trend_summary}

=== COMPETITOR ACTIVITY ===
{comp_summary}

=== OUR PERFORMANCE ===
{perf_summary}

Based on this data, create tomorrow's content plan. Focus on what's trending and what competitors are doing well that we can learn from. Prioritize content types that have worked best for us."""


def _call_groq(api_key: str, user_prompt: str) -> str:
    """Call Groq API with content planning prompt."""
    from groq import Groq

    client = Groq(api_key=api_key)
    response = client.chat.completions.create(
        model='llama-3.3-70b-versatile',
        messages=[
            {"role": "system", "content": PLAN_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.7,
        max_tokens=3000,
    )
    return (response.choices[0].message.content or '').strip()


def _try_extract_json(text: str) -> dict | None:
    """Try to extract JSON from a response that might have extra text."""
    import re

    # Try to find JSON block in markdown code fences
    match = re.search(r'```(?:json)?\s*(\{.+?\})\s*```', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    # Try to find raw JSON object
    match = re.search(r'\{[^{}]*"content_items"[^{}]*\[.+?\]\s*\}', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass

    # Last resort: find first { and last }
    start = text.find('{')
    end = text.rfind('}')
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(text[start:end + 1])
        except json.JSONDecodeError:
            pass

    return None
