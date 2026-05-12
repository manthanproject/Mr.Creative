"""A+ Copy Generator - uses Gemini/Groq for marketing copy."""
import json, logging
logger = logging.getLogger('aplus')

def generate_aplus_copy(product_name, product_category, key_features=None,
                         target_audience=None, brand_name=None, template_type='hero_banner'):
    from modules.night_orchestrator.llm import call_llm
    templates_spec = {
        'hero_banner': {
            'desc': 'Hero banner with headline, tagline, 4 benefit badges',
            'fields': '{"headline": "bold headline (max 8 words)", "tagline": "value proposition", "benefits": [{"icon_emoji": "emoji", "title": "benefit", "desc": "one line"}] (4 items), "cta": "CTA text"}',
        },
        'feature_grid': {
            'desc': '3x2 grid of features with icons',
            'fields': '{"section_title": "heading", "features": [{"icon_emoji": "emoji", "title": "feature (2-3 words)", "desc": "one sentence"}] (6 items)}',
        },
        'comparison_chart': {
            'desc': 'Product comparison table',
            'fields': '{"section_title": "heading", "product_name": "your product", "competitors": ["Comp A", "Comp B"], "rows": [{"feature": "name", "product_score": "5/5 or Yes", "comp_a_score": "3/5", "comp_b_score": "2/5"}] (6-8 rows), "verdict": "conclusion"}',
        },
        'how_to_steps': {
            'desc': '4 step usage guide',
            'fields': '{"section_title": "heading", "steps": [{"number": 1, "title": "step (2-4 words)", "desc": "instruction", "icon_emoji": "emoji"}] (4 items), "pro_tip": "expert tip"}',
        },
    }
    spec = templates_spec.get(template_type, templates_spec['hero_banner'])
    features_str = ', '.join(key_features) if key_features else 'not specified'
    prompt = (
        "You are a senior e-commerce copywriter for premium beauty/health brands on Amazon India.\n"
        "Generate marketing copy for an A+ listing image.\n\n"
        f"Product: {product_name}\n"
        f"Brand: {brand_name or 'Premium Brand'}\n"
        f"Category: {product_category or 'Beauty'}\n"
        f"Key Features: {features_str}\n"
        f"Target Audience: {target_audience or 'Women 18-35'}\n\n"
        f"Template: {template_type} - {spec['desc']}\n\n"
        f"Return ONLY valid JSON (no markdown, no backticks):\n{spec['fields']}\n\n"
        "Write like L'Oreal/Neutrogena - premium but accessible. Keep text concise for images."
    )

    try:
        result = call_llm(prompt, temperature=0.7, max_tokens=1000)
        result = result.strip()
        # Remove markdown code fences if present
        if result.startswith('`'):
            lines = result.split('\n')
            # Remove first and last lines if they are fences
            if lines[0].strip().startswith('`'):
                lines = lines[1:]
            if lines and lines[-1].strip().startswith('`'):
                lines = lines[:-1]
            result = '\n'.join(lines)
        return json.loads(result)
    except Exception as e:
        logger.error(f"[A+ Copy] Error: {e}")
        return _fallback(template_type, product_name)

def generate_full_aplus_set(product_name, product_category, key_features=None,
                             target_audience=None, brand_name=None):
    results = {}
    for t in ['hero_banner', 'feature_grid', 'comparison_chart', 'how_to_steps']:
        try:
            results[t] = generate_aplus_copy(product_name, product_category, key_features, target_audience, brand_name, t)
        except Exception as e:
            results[t] = _fallback(t, product_name)
    return results

def _fallback(template_type, product_name):
    return {
        'headline': product_name,
        'tagline': 'Premium quality for everyday beauty',
        'section_title': 'Why Choose ' + product_name,
        'benefits': [
            {'icon_emoji': '\u2728', 'title': 'Premium Quality', 'desc': 'Made with finest ingredients'},
            {'icon_emoji': '\u2B50', 'title': 'Long Lasting', 'desc': 'All-day performance'},
            {'icon_emoji': '\U0001F49A', 'title': 'Gentle Formula', 'desc': 'For all skin types'},
            {'icon_emoji': '\u2705', 'title': 'Dermatologist Tested', 'desc': 'Clinically proven'},
        ],
        'features': [
            {'icon_emoji': '\u2728', 'title': 'Premium', 'desc': 'Advanced formulation'},
            {'icon_emoji': '\u2B50', 'title': 'Quick Results', 'desc': 'Visible improvement'},
            {'icon_emoji': '\U0001F49A', 'title': 'Natural', 'desc': 'Clean beauty'},
            {'icon_emoji': '\U0001F6E1', 'title': 'Safe', 'desc': 'Dermatologist tested'},
            {'icon_emoji': '\U0001F4A7', 'title': 'Hydrating', 'desc': 'Deep moisture'},
            {'icon_emoji': '\u267B', 'title': 'Eco-Friendly', 'desc': 'Sustainable'},
        ],
        'cta': 'Shop Now',
    }
