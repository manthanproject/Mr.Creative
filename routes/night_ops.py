"""
Mr.Creative — Night Ops Routes
Dashboard for morning reports, manual cycle triggers, competitor management.
"""

from flask import Blueprint, render_template, jsonify, request
from flask_login import login_required
import json
import re
from datetime import datetime, timedelta

night_ops_bp = Blueprint('night_ops', __name__, url_prefix='/night-ops')


@night_ops_bp.route('/')
@login_required
def index():
    """Morning report dashboard."""
    from models import db, NightReport, ContentPlan, NightTrend, NightCompetitor

    # Latest morning report
    latest_report = NightReport.query.filter_by(
        report_type='morning'
    ).order_by(NightReport.created_at.desc()).first()

    # Recent reports (last 7 days)
    week_ago = datetime.now() - timedelta(days=7)
    recent_reports = NightReport.query.filter(
        NightReport.created_at >= week_ago,
        NightReport.report_type == 'morning',
    ).order_by(NightReport.created_at.desc()).limit(7).all()

    # Today's content plan
    today = datetime.now().date()
    todays_plan = ContentPlan.query.filter_by(plan_date=today).first()
    tomorrows_plan = ContentPlan.query.filter_by(
        plan_date=today + timedelta(days=1)
    ).first()

    # Stats
    trend_count = NightTrend.query.filter(NightTrend.scanned_at >= week_ago).count()
    competitor_count = NightCompetitor.query.filter(NightCompetitor.scanned_at >= week_ago).count()

    return render_template('night_ops.html',
        latest_report=latest_report,
        recent_reports=recent_reports,
        todays_plan=todays_plan,
        tomorrows_plan=tomorrows_plan,
        trend_count=trend_count,
        competitor_count=competitor_count,
    )


@night_ops_bp.route('/api/start-cycle', methods=['POST'])
@login_required
def start_cycle():
    """Manually trigger a night cycle."""
    from flask import current_app
    from modules.night_orchestrator.orchestrator import is_running, run_nightly_cycle_async

    if is_running():
        return jsonify({'error': 'Cycle already running'}), 409

    app = current_app._get_current_object()  # type: ignore[attr-defined]
    result = run_nightly_cycle_async(app, manual=True)
    return jsonify(result)


@night_ops_bp.route('/api/cycle-status')
@login_required
def cycle_status():
    """Poll current cycle status."""
    from modules.night_orchestrator.orchestrator import get_cycle_status
    return jsonify(get_cycle_status())


@night_ops_bp.route('/api/reset', methods=['POST'])
@login_required
def reset_dashboard():
    """Clear all night ops data and reset cycle state."""
    from models import db, NightTrend, NightCompetitor, NightReport, ContentPlan
    from modules.night_orchestrator.orchestrator import _current_cycle

    deleted = {}
    for model, name in [
        (NightTrend, 'trends'),
        (NightCompetitor, 'competitors'),
        (NightReport, 'reports'),
        (ContentPlan, 'plans'),
    ]:
        count = model.query.count()
        model.query.delete()
        deleted[name] = count

    db.session.commit()

    _current_cycle.update({
        'running': False, 'status': 'idle', 'current_agent': None,
        'started_at': None, 'progress': 0, 'log': [], 'result': None,
    })

    return jsonify({'status': 'reset', 'deleted': deleted})


@night_ops_bp.route('/api/report/<report_id>')
@login_required
def get_report(report_id):
    """Get full report data."""
    from models import NightReport

    report = NightReport.query.get_or_404(report_id)
    try:
        data = json.loads(report.report_data)
    except (json.JSONDecodeError, TypeError):
        data = {}

    return jsonify({
        'id': report.id,
        'type': report.report_type,
        'data': data,
        'summary': report.summary,
        'status': report.status,
        'created_at': report.created_at.isoformat(),
    })


@night_ops_bp.route('/api/plan/<plan_id>/approve', methods=['POST'])
@login_required
def approve_plan(plan_id):
    """Approve a content plan."""
    from models import db, ContentPlan

    plan = ContentPlan.query.get_or_404(plan_id)
    plan.status = 'approved'
    db.session.commit()
    return jsonify({'status': 'approved', 'id': plan.id})


@night_ops_bp.route('/api/trends')
@login_required
def get_trends():
    """Get recent trends with optional filters."""
    from models import NightTrend

    source = request.args.get('source', '')
    days = int(request.args.get('days', 7))
    limit = int(request.args.get('limit', 50))

    since = datetime.now() - timedelta(days=days)
    query = NightTrend.query.filter(NightTrend.scanned_at >= since)

    if source:
        query = query.filter_by(source=source)

    trends = query.order_by(NightTrend.score.desc()).limit(limit).all()

    return jsonify([
        {
            'id': t.id,
            'source': t.source,
            'category': t.category,
            'data': json.loads(t.trend_data) if t.trend_data else {},
            'score': t.score,
            'scanned_at': t.scanned_at.isoformat(),
        }
        for t in trends
    ])


@night_ops_bp.route('/api/competitors')
@login_required
def get_competitors():
    """Get latest competitor data."""
    from models import NightCompetitor

    days = int(request.args.get('days', 7))
    since = datetime.now() - timedelta(days=days)

    comps = NightCompetitor.query.filter(
        NightCompetitor.scanned_at >= since
    ).order_by(NightCompetitor.scanned_at.desc()).all()

    # Deduplicate by handle (keep latest)
    seen = {}
    for c in comps:
        if c.handle not in seen:
            seen[c.handle] = {
                'id': c.id,
                'platform': c.platform,
                'handle': c.handle,
                'page_url': c.page_url,
                'followers': c.follower_count,
                'engagement': c.avg_engagement,
                'data': json.loads(c.last_post_data) if c.last_post_data else {},
                'scanned_at': c.scanned_at.isoformat(),
            }

    return jsonify(list(seen.values()))


# -- Niche category mapping --
NICHE_MAP = {
    'skincare': ['skin_care', 'skincare', 'cerave', 'korean beauty', 'face wash', 'moisturizer', 'serum', 'sunscreen', 'cleanser'],
    'haircare': ['hair_care', 'hair care', 'shampoo', 'conditioner', 'hair oil', 'hair'],
    'beauty': ['beauty', 'makeup', 'cosmetic', 'lipstick', 'foundation', 'nail', 'aesthetic'],
    'personal_care': ['health_personal_care', 'personal care', 'body wash', 'soap', 'deodorant', 'bath', 'body'],
    'health': ['health', 'wellness', 'supplement', 'vitamin', 'fitness', 'lifestyle'],
}

NICHE_LABELS = {
    'skincare': 'Skincare',
    'haircare': 'Hair Care',
    'beauty': 'Beauty & Makeup',
    'personal_care': 'Personal Care',
    'health': 'Health & Wellness',
}


def _match_niche(category_text: str, niche: str) -> bool:
    text = (category_text or '').lower()
    keywords = NICHE_MAP.get(niche, [])
    return any(kw in text for kw in keywords)


@night_ops_bp.route('/api/niche-trends')
@login_required
def get_niche_trends():
    from models import NightTrend
    niche = request.args.get('niche', '')
    days = int(request.args.get('days', 7))
    limit = int(request.args.get('limit', 30))
    if not niche or niche not in NICHE_MAP:
        return jsonify({'error': 'Invalid niche', 'valid': list(NICHE_MAP.keys())}), 400
    since = datetime.now() - timedelta(days=days)
    all_trends = NightTrend.query.filter(NightTrend.scanned_at >= since).order_by(NightTrend.score.desc()).all()
    filtered = []
    for t in all_trends:
        cat = t.category or ''
        try:
            data = json.loads(t.trend_data) if t.trend_data else {}
        except (json.JSONDecodeError, TypeError):
            data = {}
        title = data.get('title', '') or data.get('query', '')
        if _match_niche(f"{cat} {title}", niche):
            filtered.append({'id': t.id, 'source': t.source, 'category': t.category, 'data': data, 'score': t.score})
            if len(filtered) >= limit:
                break
    return jsonify({'niche': niche, 'label': NICHE_LABELS.get(niche, niche), 'count': len(filtered), 'trends': filtered})


@night_ops_bp.route('/api/niche-analysis', methods=['POST'])
@login_required
def run_niche_analysis():
    from models import NightTrend, NightCompetitor
    from config import Config
    niche = request.json.get('niche', '')
    if not niche or niche not in NICHE_MAP:
        return jsonify({'error': 'Invalid niche'}), 400
    groq_key = Config.GROQ_API_KEY
    if not groq_key:
        return jsonify({'error': 'No GROQ_API_KEY configured'}), 500
    since = datetime.now() - timedelta(days=7)
    all_trends = NightTrend.query.filter(NightTrend.scanned_at >= since).all()
    niche_trends = []
    for t in all_trends:
        cat = t.category or ''
        try:
            data = json.loads(t.trend_data) if t.trend_data else {}
        except (json.JSONDecodeError, TypeError):
            data = {}
        title = data.get('title', '') or data.get('query', '')
        if _match_niche(f"{cat} {title}", niche):
            niche_trends.append({'source': t.source, 'title': title[:80], 'category': cat, 'score': t.score})
    comps = NightCompetitor.query.filter(NightCompetitor.scanned_at >= since).all()
    comp_summary = [{'platform': c.platform, 'handle': c.handle, 'followers': c.follower_count} for c in comps]
    label = NICHE_LABELS.get(niche, niche)
    prompt = f"""Analyze the {label} niche for an Indian e-commerce brand selling imported beauty/health products (dropy.in).

=== {label.upper()} TRENDS ({len(niche_trends)} items) ===
{json.dumps(niche_trends[:15], indent=1)}

=== COMPETITORS ===
{json.dumps(comp_summary, indent=1)}

Provide a focused analysis as JSON:
{{"niche": "{niche}", "summary": "3-4 sentence analysis", "top_opportunities": ["opp1","opp2","opp3"], "trending_products": ["prod1","prod2","prod3"], "content_suggestions": [{{"type": "carousel|campaign|story|pin", "idea": "specific idea", "product": "target product", "reason": "why now"}}], "risk_factors": ["risk1","risk2"], "score": 0.8}}

Be specific to Indian market. Focus on actionable items. Respond ONLY with valid JSON."""
    try:
        from groq import Groq
        client = Groq(api_key=groq_key)
        response = client.chat.completions.create(model='llama-3.3-70b-versatile', messages=[{"role": "user", "content": prompt}], temperature=0.6, max_tokens=2000)
        result_text = (response.choices[0].message.content or '').strip()
        result_text = re.sub(r'^```(?:json)?\s*', '', result_text)
        result_text = re.sub(r'\s*```$', '', result_text)
        analysis = json.loads(result_text)
    except json.JSONDecodeError:
        analysis = {'summary': result_text, 'error': 'Failed to parse JSON'}
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    analysis['trend_count'] = len(niche_trends)
    analysis['label'] = label
    return jsonify(analysis)
