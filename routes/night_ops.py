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
    todays_plan = ContentPlan.query.filter_by(plan_date=today).first() or ContentPlan.query.filter_by(plan_date=today + timedelta(days=1)).first()
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
    niche = (request.json or {}).get('niche', 'all')
    result = run_nightly_cycle_async(app, manual=True, niche=niche)
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
    # LLM key check handled by llm.py
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
        from modules.night_orchestrator.llm import call_llm
        result_text = call_llm(prompt)
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

@night_ops_bp.route('/api/watched-competitors')
@login_required
def list_watched():
    from models import WatchedCompetitor
    comps = WatchedCompetitor.query.order_by(WatchedCompetitor.added_at.desc()).all()
    return jsonify([{
        'id': c.id, 'platform': c.platform, 'handle': c.handle,
        'page_url': c.page_url, 'niche': c.niche, 'is_own': c.is_own,
    } for c in comps])


@night_ops_bp.route('/api/competitor/add', methods=['POST'])
@login_required
def add_competitor():
    from models import db, WatchedCompetitor
    data = request.json or {}
    platform = data.get('platform', '').strip().lower()
    handle = data.get('handle', '').strip().lstrip('@')
    niche = data.get('niche', '').strip()
    is_own = data.get('is_own', False)

    if platform not in ('instagram', 'pinterest'):
        return jsonify({'error': 'Platform must be instagram or pinterest'}), 400
    if not handle:
        return jsonify({'error': 'Handle is required'}), 400

    existing = WatchedCompetitor.query.filter_by(platform=platform, handle=handle).first()
    if existing:
        return jsonify({'error': f'@{handle} on {platform} already exists'}), 409

    if platform == 'instagram':
        page_url = f'https://www.instagram.com/{handle}/'
    else:
        page_url = f'https://www.pinterest.com/{handle}/'

    comp = WatchedCompetitor(platform=platform, handle=handle, page_url=page_url, niche=niche, is_own=is_own)
    db.session.add(comp)
    db.session.commit()
    return jsonify({'status': 'added', 'id': comp.id, 'handle': handle, 'platform': platform})


@night_ops_bp.route('/api/competitor/<comp_id>', methods=['DELETE'])
@login_required
def remove_competitor(comp_id):
    from models import db, WatchedCompetitor
    comp = WatchedCompetitor.query.get_or_404(comp_id)
    db.session.delete(comp)
    db.session.commit()
    return jsonify({'status': 'removed', 'id': comp_id})

@night_ops_bp.route('/analytics')
@login_required
def analytics():
    return render_template('competitor_analytics.html')


@night_ops_bp.route('/api/competitor-insights', methods=['POST'])
@login_required
def competitor_insights():
    from config import Config
    # LLM key check handled by llm.py

    data = request.json or {}
    competitors = data.get('competitors', [])

    prompt = f"""You are a competitive intelligence analyst for dropy.in, an Indian e-commerce brand selling imported beauty, health, and skincare products.

Analyze these competitors and provide actionable insights:

{json.dumps(competitors, indent=1)}

Provide your analysis covering:
1. Who is the strongest competitor and why
2. Content gaps we can exploit (what are they NOT doing)
3. Engagement patterns (what type of content gets most engagement)
4. Recommended counter-strategy for each competitor
5. Quick wins we can implement this week
6. Products/topics we should create content about based on competitor activity

Be specific, data-driven, and actionable. Format with clear sections. Keep it under 400 words."""

    try:
        from modules.night_orchestrator.llm import call_llm
        insights = call_llm(prompt)
        return jsonify({'insights': insights})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@night_ops_bp.route('/api/generate-leads', methods=['POST'])
@login_required
def generate_leads():
    """Generate actionable leads from trend + competitor data via Groq."""
    from models import db, NightTrend, NightCompetitor, NightReport
    from config import Config

    # LLM key check handled by llm.py

    niche = (request.json or {}).get('niche', 'all')
    since = datetime.now() - timedelta(days=7)

    # Gather trends
    trends_q = NightTrend.query.filter(NightTrend.scanned_at >= since)
    all_trends = trends_q.order_by(NightTrend.score.desc()).limit(50).all()
    trend_items = []
    for t_item in all_trends:
        try:
            data = json.loads(t_item.trend_data) if t_item.trend_data else {}
        except Exception:
            data = {}
        title = data.get('title', '') or t_item.category or ''
        if niche != 'all':
            combined = (t_item.category + ' ' + title).lower()
            niche_kw = NICHE_MAP.get(niche, [])
            if not any(kw in combined for kw in niche_kw):
                continue
        trend_items.append({
            'source': t_item.source, 'title': title[:80],
            'price': data.get('price', ''), 'score': t_item.score,
        })

    # Gather competitors
    comps = NightCompetitor.query.filter(NightCompetitor.scanned_at >= since).all()
    comp_items = []
    for c in comps:
        try:
            cdata = json.loads(c.last_post_data) if c.last_post_data else {}
        except Exception:
            cdata = {}
        pin_titles = [p.get('title', '')[:60] for p in (cdata.get('recent_pins', []) or [])[:5]]
        comp_items.append({
            'handle': c.handle, 'platform': c.platform,
            'followers': c.follower_count, 'top_pins': pin_titles,
        })

    niche_label = NICHE_LABELS.get(niche, 'All Niches') if niche != 'all' else 'All Niches'

    prompt = f"""You are a lead generation expert for dropy.in, an Indian e-commerce brand selling imported beauty, health, and skincare products online (Shopify store + marketplace).

Based on this market intelligence data, generate ACTIONABLE LEADS:

=== TRENDING PRODUCTS ({len(trend_items)} items, {niche_label}) ===
{json.dumps(trend_items[:20], indent=1)}

=== COMPETITOR ACTIVITY ===
{json.dumps(comp_items, indent=1)}

Generate leads as JSON with this exact structure:
{{
  "product_leads": [
    {{"product": "specific product name", "why": "why stock/promote this", "urgency": "high|medium|low", "source": "amazon|pinterest|competitor", "action": "what to do right now"}}
  ],
  "content_leads": [
    {{"format": "carousel|reel|story|pin|banner|blog", "topic": "specific topic", "hook": "attention-grabbing first line", "products_to_feature": ["product1"], "platform": "instagram|pinterest|both"}}
  ],
  "keyword_leads": [
    {{"keyword": "search term", "intent": "buy|research|compare", "ad_copy": "short Google/social ad text"}}
  ],
  "collab_leads": [
    {{"type": "influencer|brand|page", "suggestion": "who to approach", "pitch": "one-line pitch idea", "why": "reason"}}
  ],
  "quick_wins": [
    {{"action": "specific action", "effort": "low|medium", "impact": "high|medium", "timeline": "today|this week|this month"}}
  ]
}}

Generate 3-5 items per category. Be SPECIFIC to Indian market and dropy.in products (CeraVe, Korean beauty, imported skincare). No generic advice.
Respond ONLY with valid JSON."""

    try:
        from modules.night_orchestrator.llm import call_llm
        result_text = call_llm(prompt)
        result_text = re.sub(r'^```(?:json)?\s*', '', result_text)
        result_text = re.sub(r'\s*```$', '', result_text)

        try:
            leads = json.loads(result_text)
        except json.JSONDecodeError:
            start = result_text.find('{')
            end = result_text.rfind('}')
            if start != -1 and end > start:
                leads = json.loads(result_text[start:end+1])
            else:
                leads = {'error': 'Failed to parse', 'raw': result_text[:500]}

        # Save as report
        report = NightReport(
            report_type='leads',
            report_data=json.dumps(leads, ensure_ascii=False),
            summary=f"Leads for {niche_label}: {len(leads.get('product_leads',[]))} products, {len(leads.get('content_leads',[]))} content, {len(leads.get('keyword_leads',[]))} keywords",
            status='completed',
        )
        db.session.add(report)
        db.session.commit()

        leads['niche'] = niche_label
        leads['trend_count'] = len(trend_items)
        return jsonify(leads)

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@night_ops_bp.route('/marketing-analysis')
@login_required
def marketing_analysis():
    return render_template('marketing_analysis.html')


@night_ops_bp.route('/api/marketing-report', methods=['POST'])
@login_required
def generate_marketing_report():
    """Generate comprehensive marketing analysis via Groq."""
    from models import NightTrend, NightCompetitor, NightReport, db
    from config import Config

    # LLM key check handled by llm.py

    niche = (request.json or {}).get('niche', 'all')
    since = datetime.now() - timedelta(days=7)

    trends = NightTrend.query.filter(NightTrend.scanned_at >= since).order_by(NightTrend.score.desc()).limit(30).all()
    trend_items = []
    for t_item in trends:
        try:
            data = json.loads(t_item.trend_data) if t_item.trend_data else {}
        except Exception:
            data = {}
        title = data.get('title', '') or t_item.category or ''
        if niche != 'all':
            combined = (t_item.category + ' ' + title).lower()
            niche_kw = NICHE_MAP.get(niche, [])
            if not any(kw in combined for kw in niche_kw):
                continue
        trend_items.append({'source': t_item.source, 'title': title[:60], 'price': data.get('price', ''), 'score': t_item.score})

    comps = NightCompetitor.query.filter(NightCompetitor.scanned_at >= since).all()
    comp_items = []
    for c in comps:
        try:
            cdata = json.loads(c.last_post_data) if c.last_post_data else {}
        except Exception:
            cdata = {}
        pins = [p.get('title', '')[:50] for p in (cdata.get('recent_pins', []) or [])[:5]]
        comp_items.append({'handle': c.handle, 'platform': c.platform, 'followers': c.follower_count, 'engagement': c.avg_engagement, 'top_content': pins})

    niche_label = NICHE_LABELS.get(niche, 'All Niches') if niche != 'all' else 'All Niches'

    prompt = f"""You are a senior marketing strategist analyzing the Indian e-commerce market for dropy.in.

dropy.in sells imported beauty, health, skincare, and personal care products (CeraVe, Korean beauty, imported brands) through Shopify + marketplaces. Based in Navi Mumbai. Target: 18-35 urban Indian women.

=== MARKET DATA ({niche_label}) ===
Trending Products ({len(trend_items)}): {json.dumps(trend_items[:15], indent=1)}
Competitors ({len(comp_items)}): {json.dumps(comp_items, indent=1)}

Generate a COMPREHENSIVE marketing analysis as JSON:
{{"executive_summary":"3-4 sentence overview","swot":{{"strengths":["s1","s2","s3"],"weaknesses":["w1","w2","w3"],"opportunities":["o1","o2","o3"],"threats":["t1","t2","t3"]}},"market_opportunities":[{{"segment":"name","size":"potential","competition":"low|medium|high","recommendation":"action"}}],"audience_personas":[{{"name":"persona","age":"range","profile":"description","pain_points":["p1","p2"],"channels":["ch1"],"buying_triggers":["b1"]}}],"content_strategy":{{"pillars":["p1","p2","p3"],"weekly_plan":[{{"day":"Monday","content_type":"carousel|reel|story|pin","topic":"topic","platform":"instagram|pinterest|both"}}],"hashtag_strategy":["h1","h2","h3","h4","h5"]}},"seo_keywords":[{{"keyword":"term","volume_estimate":"high|medium|low","difficulty":"easy|medium|hard","intent":"buy|research|compare","content_idea":"what to create"}}],"ad_campaigns":[{{"name":"campaign","objective":"awareness|traffic|conversions","platform":"google|instagram|facebook","budget_range":"INR daily","target_audience":"who","ad_copy":"headline + desc","cta":"action"}}],"pricing_insights":{{"strategy":"recommendation","competitive_range":"observation","recommendations":["r1","r2"]}},"competitive_positioning":{{"current_position":"where now","desired_position":"where to be","differentiators":["d1","d2","d3"],"gaps_to_close":["g1","g2"]}},"action_plan_30_days":[{{"week":1,"actions":["a1","a2","a3"]}},{{"week":2,"actions":["a1","a2"]}},{{"week":3,"actions":["a1","a2"]}},{{"week":4,"actions":["a1","a2"]}}]}}

Be SPECIFIC to Indian market and dropy.in. No generic advice. Respond ONLY with valid JSON."""

    try:
        from modules.night_orchestrator.llm import call_llm
        result_text = call_llm(prompt)
        result_text = re.sub(r'^```(?:json)?\s*', '', result_text)
        result_text = re.sub(r'\s*```$', '', result_text)

        try:
            report = json.loads(result_text)
        except json.JSONDecodeError:
            start = result_text.find('{')
            end = result_text.rfind('}')
            if start != -1 and end > start:
                report = json.loads(result_text[start:end + 1])
            else:
                return jsonify({'error': 'Failed to parse', 'raw': result_text[:500]}), 500

        db_report = NightReport(
            report_type='marketing',
            report_data=json.dumps(report, ensure_ascii=False),
            summary=report.get('executive_summary', '')[:200],
            status='completed',
        )
        db.session.add(db_report)
        db.session.commit()

        report['niche'] = niche_label
        return jsonify(report)

    except Exception as e:
        return jsonify({'error': str(e)}), 500

