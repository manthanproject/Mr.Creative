from flask import Blueprint, render_template, request, jsonify, redirect, url_for, flash
from flask_login import login_required, current_user
from models import db, Prompt

prompts_bp = Blueprint('prompts', __name__)


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
