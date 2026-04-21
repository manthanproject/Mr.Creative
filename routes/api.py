from flask import Blueprint, jsonify, request, current_app
from flask_login import login_required, current_user
from models import db, Prompt, Generation, Collection, JobQueue

api_bp = Blueprint('api', __name__)


def get_gemini_engine():
    """Initialize and return AI engine (Gemini)."""
    from modules.gemini_engine import GeminiEngine
    api_key = current_app.config.get('GEMINI_API_KEY', '')
    if not api_key:
        return None
    return GeminiEngine(api_key)


# ==========================================
# GEMINI AI ENDPOINTS
# ==========================================

@api_bp.route('/generate-prompts', methods=['POST'])
@login_required
def generate_prompts():
    """Generate creative prompt suggestions using Gemini."""
    data = request.get_json() or {}
    base_text = data.get('base_text', '').strip()
    category = data.get('category', 'general')
    count = data.get('count', 5)

    engine = get_gemini_engine()
    if not engine:
        return jsonify({'error': 'Gemini API key not configured. Add it in config.py', 'prompts': []}), 400

    try:
        prompts = engine.generate_prompts(
            base_text=base_text,
            category=category,
            count=count
        )
        if not prompts:
            return jsonify({'error': 'No prompts generated. Try a different input.', 'prompts': []}), 200

        return jsonify({'prompts': prompts, 'count': len(prompts)})

    except Exception as e:
        error_msg = str(e)
        # Provide user-friendly error messages
        if 'API_KEY_INVALID' in error_msg or 'PERMISSION_DENIED' in error_msg:
            error_msg = 'Invalid Gemini API key. Please check your key in config.py'
        elif 'quota' in error_msg.lower():
            error_msg = 'Gemini API quota exceeded. Please try again later.'
        elif 'network' in error_msg.lower() or 'connection' in error_msg.lower():
            error_msg = 'Network error connecting to Gemini. Check your internet connection.'

        return jsonify({'error': error_msg, 'prompts': []}), 500


@api_bp.route('/refine-prompt', methods=['POST'])
@login_required
def refine_prompt():
    """Refine an existing prompt based on user instruction."""
    data = request.get_json() or {}
    original = data.get('original', '').strip()
    instruction = data.get('instruction', '').strip()

    if not original:
        return jsonify({'error': 'Original prompt is required'}), 400
    if not instruction:
        return jsonify({'error': 'Refinement instruction is required'}), 400

    engine = get_gemini_engine()
    if not engine:
        return jsonify({'error': 'Gemini API key not configured'}), 400

    try:
        refined = engine.refine_prompt(original, instruction)
        return jsonify({'refined': refined})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@api_bp.route('/enhance-prompt', methods=['POST'])
@login_required
def enhance_prompt():
    """Auto-enhance a prompt with more detail and style."""
    data = request.get_json() or {}
    prompt_text = data.get('text', '').strip()

    if not prompt_text:
        return jsonify({'error': 'Prompt text is required'}), 400

    engine = get_gemini_engine()
    if not engine:
        return jsonify({'error': 'Gemini API key not configured'}), 400

    try:
        enhanced = engine.enhance_prompt(prompt_text)
        return jsonify({'enhanced': enhanced})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@api_bp.route('/prompt-variations', methods=['POST'])
@login_required
def prompt_variations():
    """Generate variations of an existing prompt."""
    data = request.get_json() or {}
    prompt_text = data.get('text', '').strip()
    count = data.get('count', 3)

    if not prompt_text:
        return jsonify({'error': 'Prompt text is required'}), 400

    engine = get_gemini_engine()
    if not engine:
        return jsonify({'error': 'Gemini API key not configured'}), 400

    try:
        variations = engine.generate_variations(prompt_text, count=count)
        return jsonify({'variations': variations})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@api_bp.route('/suggest-categories', methods=['POST'])
@login_required
def suggest_categories():
    """Suggest campaign categories for a business."""
    data = request.get_json() or {}
    description = data.get('description', '').strip()

    if not description:
        return jsonify({'error': 'Business description is required'}), 400

    engine = get_gemini_engine()
    if not engine:
        return jsonify({'error': 'Gemini API key not configured'}), 400

    try:
        categories = engine.suggest_categories(description)
        return jsonify({'categories': categories})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ==========================================
# PROMPT CRUD VIA API (for AJAX)
# ==========================================

@api_bp.route('/prompts/save', methods=['POST'])
@login_required
def save_prompt_api():
    """Save a prompt via API (used by AI suggestions)."""
    data = request.get_json() or {}
    text = data.get('text', '').strip()
    prompt_type = data.get('prompt_type', 'generated')
    auto_approve = data.get('auto_approve', False)

    if not text:
        return jsonify({'error': 'Prompt text is required'}), 400

    prompt = Prompt(
        user_id=current_user.id,
        text=text,
        prompt_type=prompt_type,
        is_approved=auto_approve,
        status='approved' if auto_approve else 'draft'
    )
    db.session.add(prompt)
    db.session.commit()

    return jsonify({'success': True, 'prompt': prompt.to_dict()})


# ==========================================
# STATS & DATA ENDPOINTS
# ==========================================

@api_bp.route('/stats')
@login_required
def stats():
    return jsonify({
        'prompts': Prompt.query.filter_by(user_id=current_user.id).count(),
        'generations': Generation.query.filter_by(user_id=current_user.id).count(),
        'collections': Collection.query.filter_by(user_id=current_user.id).count(),
        'favorites': Prompt.query.filter_by(user_id=current_user.id, is_favorite=True).count(),
        'queued': JobQueue.query.filter_by(user_id=current_user.id, status='queued').count(),
        'processing': JobQueue.query.filter_by(user_id=current_user.id, status='processing').count(),
    })


@api_bp.route('/queue/status')
@login_required
def queue_status():
    jobs = JobQueue.query.filter_by(user_id=current_user.id)\
        .order_by(JobQueue.created_at.desc()).limit(20).all()
    return jsonify({
        'jobs': [{
            'id': j.id,
            'job_type': j.job_type,
            'status': j.status,
            'created_at': j.created_at.isoformat(),
            'started_at': j.started_at.isoformat() if j.started_at else None,
            'completed_at': j.completed_at.isoformat() if j.completed_at else None,
            'error_message': j.error_message,
        } for j in jobs]
    })


@api_bp.route('/generations/recent')
@login_required
def recent_generations():
    limit = request.args.get('limit', 12, type=int)
    generations = Generation.query.filter_by(user_id=current_user.id)\
        .order_by(Generation.created_at.desc()).limit(limit).all()
    return jsonify({
        'generations': [g.to_dict() for g in generations]
    })


@api_bp.route('/prompts/search')
@login_required
def search_prompts():
    q = request.args.get('q', '').strip()
    if not q:
        return jsonify({'prompts': []})
    prompts = Prompt.query.filter_by(user_id=current_user.id)\
        .filter(Prompt.text.ilike(f'%{q}%'))\
        .order_by(Prompt.created_at.desc()).limit(20).all()
    return jsonify({
        'prompts': [p.to_dict() for p in prompts]
    })

@api_bp.route('/test-gemini')
@login_required
def test_gemini():
    """Quick test page for Gemini connection."""
    try:
        engine = get_gemini_engine()
        if not engine:
            return jsonify({'status': 'FAIL', 'error': 'No API key configured'})
        result = engine._call_api("Say hello in 5 words")
        return jsonify({'status': 'OK', 'response': result})
    except Exception as e:
        return jsonify({'status': 'FAIL', 'error': str(e)})

