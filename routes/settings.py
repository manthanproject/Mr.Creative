from flask import Blueprint, render_template, request, jsonify, current_app, redirect, url_for
from flask_login import login_required, current_user
from models import db, User, Generation, Collection, Prompt, JobQueue, ScheduledJob
from datetime import datetime
import os
import json

settings_bp = Blueprint('settings', __name__)


@settings_bp.route('/')
@login_required
def index():
    # Compute account stats
    total_generations = Generation.query.filter_by(user_id=current_user.id).count()
    total_collections = Collection.query.filter_by(user_id=current_user.id).count()
    total_prompts = Prompt.query.filter_by(user_id=current_user.id).count()
    total_jobs = JobQueue.query.filter_by(user_id=current_user.id).count()

    # Compute storage used
    output_folder = current_app.config.get('OUTPUT_FOLDER', 'static/outputs')
    storage_bytes = _get_user_storage(current_user.id, output_folder)

    return render_template('settings.html',
        stats={
            'generations': total_generations,
            'collections': total_collections,
            'prompts': total_prompts,
            'jobs': total_jobs,
            'storage_bytes': storage_bytes,
            'storage_display': _format_bytes(storage_bytes),
        },
    )


@settings_bp.route('/update-profile', methods=['POST'])
@login_required
def update_profile():
    data = request.get_json() or {}
    username = data.get('username', '').strip()
    email = data.get('email', '').strip()
    avatar_color = data.get('avatar_color', '').strip()

    errors = []

    if username and username != current_user.username:
        # Check uniqueness
        existing = User.query.filter(User.username == username, User.id != current_user.id).first()
        if existing:
            errors.append('Username already taken')
        elif len(username) < 2:
            errors.append('Username must be at least 2 characters')
        else:
            current_user.username = username

    if email and email != current_user.email:
        existing = User.query.filter(User.email == email, User.id != current_user.id).first()
        if existing:
            errors.append('Email already in use')
        else:
            current_user.email = email

    if avatar_color and avatar_color.startswith('#') and len(avatar_color) == 7:
        current_user.avatar_color = avatar_color

    if errors:
        return jsonify({'error': '; '.join(errors)}), 400

    db.session.commit()
    return jsonify({
        'success': True,
        'username': current_user.username,
        'email': current_user.email,
        'avatar_color': current_user.avatar_color,
        'initials': current_user.initials,
    })


@settings_bp.route('/change-password', methods=['POST'])
@login_required
def change_password():
    data = request.get_json() or {}
    current_pw = data.get('current_password', '')
    new_pw = data.get('new_password', '')
    confirm_pw = data.get('confirm_password', '')

    if not current_pw:
        return jsonify({'error': 'Current password is required'}), 400
    if not current_user.check_password(current_pw):
        return jsonify({'error': 'Current password is incorrect'}), 400
    if not new_pw or len(new_pw) < 6:
        return jsonify({'error': 'New password must be at least 6 characters'}), 400
    if new_pw != confirm_pw:
        return jsonify({'error': 'Passwords do not match'}), 400

    current_user.set_password(new_pw)
    db.session.commit()
    return jsonify({'success': True, 'message': 'Password updated!'})


@settings_bp.route('/delete-account', methods=['POST'])
@login_required
def delete_account():
    data = request.get_json() or {}
    password = data.get('password', '')

    if not password or not current_user.check_password(password):
        return jsonify({'error': 'Incorrect password'}), 400

    user_id = current_user.id

    # Delete all user data
    output_folder = current_app.config.get('OUTPUT_FOLDER', 'static/outputs')

    # Delete collection folders
    collections = Collection.query.filter_by(user_id=user_id).all()
    for col in collections:
        col_dir = os.path.join(output_folder, f'collection_{col.id}')
        if os.path.exists(col_dir):
            import shutil
            shutil.rmtree(col_dir, ignore_errors=True)

    # Delete DB records (cascades handle most of it)
    # Clean up non-cascaded tables
    ScheduledJob.query.filter_by(user_id=user_id).delete()
    JobQueue.query.filter_by(user_id=user_id).delete()

    # Delete the user (cascades: projects, prompts, generations, collections)
    user = User.query.get(user_id)
    db.session.delete(user)
    db.session.commit()

    # Logout
    from flask_login import logout_user
    logout_user()

    return jsonify({'success': True, 'redirect': '/auth/login'})


@settings_bp.route('/clear-data', methods=['POST'])
@login_required
def clear_data():
    """Clear all generations and downloads but keep account + collections."""
    data = request.get_json() or {}
    what = data.get('what', 'generations')  # generations, jobs, all

    if what in ('generations', 'all'):
        Generation.query.filter_by(user_id=current_user.id).delete()

    if what in ('jobs', 'all'):
        JobQueue.query.filter_by(user_id=current_user.id).delete()
        ScheduledJob.query.filter_by(user_id=current_user.id).delete()

    db.session.commit()
    return jsonify({'success': True, 'message': f'Cleared {what}!'})


def _get_user_storage(user_id, output_folder):
    """Calculate total storage used by user's collections."""
    total = 0
    collections = Collection.query.filter_by(user_id=user_id).all()
    for col in collections:
        col_dir = os.path.join(output_folder, f'collection_{col.id}')
        if os.path.exists(col_dir):
            for dirpath, dirnames, filenames in os.walk(col_dir):
                for f in filenames:
                    fp = os.path.join(dirpath, f)
                    try:
                        total += os.path.getsize(fp)
                    except OSError:
                        pass
    return total


def _format_bytes(b):
    if b < 1024:
        return f'{b} B'
    elif b < 1024 * 1024:
        return f'{b / 1024:.1f} KB'
    elif b < 1024 * 1024 * 1024:
        return f'{b / (1024 * 1024):.1f} MB'
    else:
        return f'{b / (1024 * 1024 * 1024):.2f} GB'