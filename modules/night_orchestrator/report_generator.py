"""
Night Orchestrator — ReportGenerator
Compiles all overnight agent outputs into a single morning report.
Optionally uses Groq to generate an executive summary.
"""

import json
import logging
from datetime import datetime

logger = logging.getLogger('night_ops')


def generate_morning_report(
    app,
    trend_data: dict,
    competitor_data: dict,
    performance_data: dict,
    content_plan: dict,
    cycle_meta: dict,
) -> dict:
    """
    Compile all agent outputs into a single morning report.
    Saves to night_reports table.
    Returns the full report dict.
    """
    with app.app_context():
        from models import db, NightReport
        from config import Config

        report = {
            'generated_at': datetime.now().isoformat(),
            'cycle_duration': cycle_meta.get('duration_minutes', 0),
            'cycle_status': cycle_meta.get('status', 'unknown'),
            'sections': {},
        }

        # ── Section 1: Trend Highlights ──
        report['sections']['trends'] = _summarize_trends(trend_data)

        # ── Section 2: Competitor Intelligence ──
        report['sections']['competitors'] = _summarize_competitors(competitor_data)

        # ── Section 3: Own Performance ──
        report['sections']['performance'] = _summarize_performance(performance_data)

        # ── Section 4: Content Plan ──
        report['sections']['content_plan'] = _summarize_plan(content_plan)

        # ── Section 5: Errors & Warnings ──
        report['sections']['issues'] = _collect_issues(
            trend_data, competitor_data, performance_data, content_plan, cycle_meta
        )

        # ── Generate executive summary via Groq (if key available) ──
        groq_key = Config.GROQ_API_KEY
        gemini_key = Config.GEMINI_API_KEY
        if groq_key or gemini_key:
            report['executive_summary'] = _generate_executive_summary(report)
        else:
            report['executive_summary'] = _fallback_summary(report)

        # Save to DB
        try:
            db_report = NightReport(
                report_type='morning',
                report_data=json.dumps(report, ensure_ascii=False),
                summary=report['executive_summary'],
                status='completed',
            )
            db.session.add(db_report)
            db.session.commit()
            logger.info("[ReportGen] Morning report saved")
        except Exception as e:
            logger.error(f"[ReportGen] DB save error: {e}")
            db.session.rollback()

        return report


def _summarize_trends(data: dict) -> dict:
    if not data:
        return {'status': 'skipped', 'highlights': []}

    highlights = []

    # Top Pinterest trends
    for pin in data.get('top_pinterest', [])[:3]:
        highlights.append({
            'source': 'Pinterest',
            'title': pin.get('title', '')[:100],
            'query': pin.get('query', ''),
            'score': pin.get('score', 0),
        })

    # Top Amazon products
    for prod in data.get('top_amazon', [])[:3]:
        highlights.append({
            'source': 'Amazon',
            'title': prod.get('title', '')[:100],
            'rank': prod.get('rank', 0),
            'price': prod.get('price', ''),
            'category': prod.get('category', ''),
        })

    return {
        'status': 'ok',
        'pinterest_total': data.get('pinterest_count', 0),
        'amazon_total': data.get('amazon_count', 0),
        'highlights': highlights,
    }


def _summarize_competitors(data: dict) -> dict:
    if not data:
        return {'status': 'skipped', 'profiles': []}

    profiles = []
    for r in data.get('results', []):
        profiles.append({
            'platform': r.get('platform', ''),
            'handle': r.get('handle', ''),
            'followers': r.get('follower_count', 0),
            'engagement': r.get('avg_engagement', 0),
            'error': r.get('error'),
        })

    error_count = len(data.get('errors', []))

    return {
        'status': 'ok',
        'total_scanned': data.get('total_scanned', 0),
        'errors': error_count,
        'profiles': profiles,
    }


def _summarize_performance(data: dict) -> dict:
    if not data:
        return {'status': 'skipped'}

    internal = data.get('internal', {})
    gens = internal.get('generations', {})

    return {
        'status': 'ok',
        'total_generations': gens.get('total', 0),
        'success_rate': gens.get('success_rate', 0),
        'today_generations': gens.get('last_24h', 0),
        'by_feature': gens.get('by_feature', {}),
        'social_posted': internal.get('social', {}).get('posted', 0),
        'ig_followers': data.get('external', {}).get('instagram', {}).get('followers', 0),
        'ig_engagement': data.get('external', {}).get('instagram', {}).get('avg_engagement', 0),
    }


def _summarize_plan(data: dict) -> dict:
    if not data:
        return {'status': 'skipped'}

    plan = data.get('plan')
    if not plan:
        return {'status': 'failed', 'error': data.get('error', 'Unknown')}

    return {
        'status': 'ok',
        'plan_date': plan.get('plan_date', ''),
        'theme': plan.get('theme', ''),
        'content_count': len(plan.get('content_items', [])),
        'items': [
            {
                'type': item.get('type', ''),
                'product': item.get('product', ''),
                'platform': item.get('platform', ''),
                'priority': item.get('priority', ''),
            }
            for item in plan.get('content_items', [])[:8]
        ],
    }


def _collect_issues(trends, competitors, performance, plan, meta) -> list:
    issues = []

    if not trends or trends.get('total_saved', 0) == 0:
        issues.append({'level': 'warning', 'agent': 'TrendScout', 'message': 'No trends collected'})

    if competitors:
        error_count = len(competitors.get('errors', []))
        if error_count > 0:
            issues.append({
                'level': 'warning',
                'agent': 'CompetitorWatcher',
                'message': f'{error_count} profiles failed to scrape',
            })

    if plan and plan.get('error'):
        issues.append({'level': 'error', 'agent': 'ContentPlanner', 'message': plan['error']})

    if meta.get('errors'):
        for err in meta['errors']:
            issues.append({'level': 'error', 'agent': err.get('agent', '?'), 'message': err.get('message', '')})

    return issues


def _generate_executive_summary(report: dict) -> str:
    """Use LLM to generate a concise morning briefing."""
    try:
        from modules.night_orchestrator.llm import call_llm

        # Build a concise data summary for the LLM
        sections = report.get('sections', {})
        trends = sections.get('trends', {})
        comps = sections.get('competitors', {})
        perf = sections.get('performance', {})
        plan = sections.get('content_plan', {})
        issues = sections.get('issues', [])

        prompt = f"""Generate a brief morning briefing (4-6 sentences) for a small e-commerce team.
Data from overnight agents:

Trends: {trends.get('pinterest_total', 0)} Pinterest pins, {trends.get('amazon_total', 0)} Amazon products scanned.
Top trend highlights: {json.dumps(trends.get('highlights', [])[:3], default=str)}

Competitors: {comps.get('total_scanned', 0)} profiles scanned.
Competitor summary: {json.dumps(comps.get('profiles', [])[:3], default=str)}

Own performance: {perf.get('total_generations', 0)} total generations ({perf.get('success_rate', 0)}% success).
Today: {perf.get('today_generations', 0)} new. IG followers: {perf.get('ig_followers', 0)}.

Content plan: {plan.get('content_count', 0)} items planned. Theme: {plan.get('theme', 'N/A')}.

Issues: {len(issues)} ({', '.join(i['message'][:50] for i in issues[:3]) or 'None'}).

Write a brief, actionable morning briefing. Be direct. Mention what to focus on today.
Respond ONLY with the briefing text, no JSON, no markdown."""

        summary = call_llm(prompt, temperature=0.5, max_tokens=500)
        logger.info("[ReportGen] Executive summary generated via LLM")
        return summary

    except Exception as e:
        logger.error(f"[ReportGen] Groq summary error: {e}")
        return _fallback_summary(report)


def _fallback_summary(report: dict) -> str:
    """Generate a basic summary without LLM."""
    sections = report.get('sections', {})
    trends = sections.get('trends', {})
    plan = sections.get('content_plan', {})
    issues = sections.get('issues', [])

    parts = []
    parts.append(f"Night cycle completed in {report.get('cycle_duration', '?')} minutes.")

    if trends.get('pinterest_total', 0) > 0 or trends.get('amazon_total', 0) > 0:
        parts.append(f"Scanned {trends.get('pinterest_total', 0)} Pinterest trends and {trends.get('amazon_total', 0)} Amazon products.")

    if plan.get('content_count', 0) > 0:
        parts.append(f"Content plan ready: {plan['content_count']} items, theme: '{plan.get('theme', 'N/A')}'.")

    if issues:
        parts.append(f"⚠ {len(issues)} issues detected — check the report details.")

    return ' '.join(parts)
