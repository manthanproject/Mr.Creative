from flask import Blueprint, render_template, request, jsonify, redirect, url_for, flash
from flask_login import login_required, current_user
from models import db, Prompt

prompts_bp = Blueprint('prompts', __name__)


@prompts_bp.route('/library')
@login_required
def library():
    """Curated prompt library with expert prompts organized by category."""
    from modules.prompt_library import CONTENT_TYPE_CONFIG

    icons = {
        'a_plus': '📊',
        'social_post': '📱',
        'banner': '🖼',
        'lifestyle': '🌿',
        'ad_creative': '📣',
        'model_photography': '👤',
    }

    categories = []
    total = 0
    for key, config in CONTENT_TYPE_CONFIG.items():
        prompts = config.get('expert_prompts', [])
        if not prompts:
            continue
        cat = {
            'key': key,
            'name': config.get('name', key.replace('_', ' ').title()),
            'icon': icons.get(key, '📝'),
            'prompts': [{'text': p, 'preview': None, 'is_custom': False} for p in prompts],
        }
        categories.append(cat)
        total += len(prompts)

    # Add user's custom prompts
    custom_prompts = Prompt.query.filter_by(user_id=current_user.id).order_by(Prompt.created_at.desc()).all()
    if custom_prompts:
        custom_by_type: dict = {}
        for p in custom_prompts:
            ptype = p.prompt_type or 'custom'
            if ptype not in custom_by_type:
                custom_by_type[ptype] = []
            custom_by_type[ptype].append(
                {'text': p.text, 'preview': None, 'id': p.id, 'is_custom': True}
            )

        for ptype, items in custom_by_type.items():
            existing = next((c for c in categories if c['key'] == ptype), None)
            if existing:
                for p in items:
                    prompt_list = existing['prompts']
                    if isinstance(prompt_list, list):
                        prompt_list.append(p)
            else:
                categories.append({
                    'key': ptype,
                    'name': ptype.replace('_', ' ').title(),
                    'icon': icons.get(ptype, '⭐'),
                    'prompts': items,
                })
            total += len(items)

    from modules.prompt_previews import get_preview
    # Attach preview images to prompts
    for cat in categories:
        for prompt in cat['prompts']:
            if not prompt.get('preview'):
                preview = get_preview(prompt['text'])
                if preview:
                    prompt['preview'] = '/static/' + preview

    return render_template('prompt_library.html', categories=categories, total_prompts=total)


@prompts_bp.route('/library/set-preview', methods=['POST'])
@login_required
def set_prompt_preview():
    data = request.get_json() or {}
    prompt_text = data.get('prompt_text', '')
    image_path = data.get('image_path', '')
    if not prompt_text or not image_path:
        return jsonify({'error': 'Missing data'}), 400
    from modules.prompt_previews import set_preview
    set_preview(prompt_text, image_path)
    return jsonify({'success': True})


@prompts_bp.route('/library/add', methods=['POST'])
@login_required
def library_add():
    data = request.get_json() or {}
    text = (data.get('text') or '').strip()
    category = data.get('category') or 'custom'
    if not text:
        return jsonify({'error': 'Prompt text required'}), 400
    prompt = Prompt(
        user_id=current_user.id,
        text=text,
        prompt_type=category,
        is_approved=True,
        status='approved',
    )
    db.session.add(prompt)
    db.session.commit()
    return jsonify({'success': True, 'id': prompt.id})


@prompts_bp.route('/library/<prompt_id>/delete', methods=['POST'])
@login_required
def library_delete(prompt_id):
    prompt = Prompt.query.filter_by(id=prompt_id, user_id=current_user.id).first()
    if not prompt:
        return jsonify({'error': 'Not found'}), 404
    db.session.delete(prompt)
    db.session.commit()
    return jsonify({'success': True})


@prompts_bp.route('/')
@login_required
def index():
    tab = request.args.get('tab', 'all')
    if tab == 'favorites':
        prompts = Prompt.query.filter_by(user_id=current_user.id, is_favorite=True)\
            .order_by(Prompt.created_at.desc()).all()
    elif tab == 'approved':
        prompts = Prompt.query.filter_by(user_id=current_user.id, is_approved=True)\
            .order_by(Prompt.created_at.desc()).all()
    else:
        prompts = Prompt.query.filter_by(user_id=current_user.id)\
            .order_by(Prompt.created_at.desc()).all()

    return render_template('prompts.html', prompts=prompts, active_tab=tab)


@prompts_bp.route('/create', methods=['POST'])
@login_required
def create():
    text = request.form.get('text', '').strip()
    prompt_type = request.form.get('prompt_type', 'manual')
    auto_approve = request.form.get('auto_approve', '')

    if not text:
        flash('Prompt text cannot be empty.', 'error')
        return redirect(url_for('prompts.index'))

    prompt = Prompt(
        user_id=current_user.id,
        text=text,
        prompt_type=prompt_type,
        is_approved=bool(auto_approve),
        status='approved' if auto_approve else 'draft'
    )
    db.session.add(prompt)
    db.session.commit()

    flash('Prompt approved & queued!' if auto_approve else 'Prompt saved as draft!', 'success')
    return redirect(url_for('prompts.index'))


@prompts_bp.route('/<prompt_id>/approve', methods=['POST'])
@login_required
def approve(prompt_id):
    prompt = Prompt.query.filter_by(id=prompt_id, user_id=current_user.id).first_or_404()
    prompt.is_approved = True
    prompt.status = 'approved'
    db.session.commit()
    return jsonify({'success': True, 'status': 'approved'})


@prompts_bp.route('/<prompt_id>/favorite', methods=['POST'])
@login_required
def toggle_favorite(prompt_id):
    prompt = Prompt.query.filter_by(id=prompt_id, user_id=current_user.id).first_or_404()
    prompt.is_favorite = not prompt.is_favorite
    db.session.commit()
    return jsonify({'success': True, 'is_favorite': prompt.is_favorite})


@prompts_bp.route('/<prompt_id>/delete', methods=['POST'])
@login_required
def delete(prompt_id):
    prompt = Prompt.query.filter_by(id=prompt_id, user_id=current_user.id).first_or_404()
    db.session.delete(prompt)
    db.session.commit()
    return jsonify({'success': True})
