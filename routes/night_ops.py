"""
Mr.Creative — Night Ops Routes
Dashboard for morning reports, manual cycle triggers, competitor management.
"""

from flask import Blueprint, render_template, jsonify, request
from flask_login import login_required
import json
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

    result = run_nightly_cycle_async(current_app._get_current_object(), manual=True)
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
