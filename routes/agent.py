from flask import Blueprint, render_template, request, jsonify, current_app
from flask_login import login_required, current_user
from models import db, BrandKit, AgentJob, Collection
from datetime import datetime
import json
import os
import threading

agent_bp = Blueprint('agent', __name__)

_agent_jobs = {}


@agent_bp.route('/')
@login_required
def index():
    brand_kits = BrandKit.query.filter_by(user_id=current_user.id)\
        .order_by(BrandKit.created_at.desc()).all()
    jobs = AgentJob.query.filter_by(user_id=current_user.id)\
        .order_by(AgentJob.created_at.desc()).limit(10).all()
    return render_template('agent.html', brand_kits=brand_kits, jobs=jobs)


@agent_bp.route('/brand-kit', methods=['POST'])
@login_required
def create_brand_kit():
    data = request.get_json() or {}
    name = data.get('name', '').strip()
    if not name:
        return jsonify({'error': 'Brand name is required'}), 400

    kit = BrandKit(
        user_id=current_user.id,
        name=name,
        description=data.get('description', '').strip(),
        primary_color=data.get('primary_color', '#000000'),
        secondary_color=data.get('secondary_color', '#FFFFFF'),
        accent_color=data.get('accent_color', '#C1CD7D'),
        heading_font=data.get('heading_font', 'Poppins'),
        body_font=data.get('body_font', 'Inter'),
        font_style=data.get('font_style', 'modern'),
        tone=data.get('tone', 'professional'),
        target_audience=data.get('target_audience', '').strip(),
        product_category=data.get('product_category', '').strip(),
    )

    # Handle logo upload
    logo = data.get('logo_path', '')
    if logo:
        kit.logo_path = logo

    db.session.add(kit)
    db.session.commit()
    return jsonify({'success': True, 'id': kit.id, 'name': kit.name})


@agent_bp.route('/brand-kit/<kit_id>')
@login_required
def get_brand_kit(kit_id):
    kit = BrandKit.query.filter_by(id=kit_id, user_id=current_user.id).first()
    if not kit:
        return jsonify({'error': 'Not found'}), 404
    return jsonify({
        'id': kit.id,
        'name': kit.name,
        'description': kit.description,
        'primary_color': kit.primary_color,
        'secondary_color': kit.secondary_color,
        'accent_color': kit.accent_color,
        'heading_font': kit.heading_font,
        'body_font': kit.body_font,
        'font_style': kit.font_style,
        'tone': kit.tone,
        'target_audience': kit.target_audience,
        'product_category': kit.product_category,
        'logo_path': kit.logo_path,
    })


@agent_bp.route('/brand-kit/<kit_id>/delete', methods=['POST'])
@login_required
def delete_brand_kit(kit_id):
    kit = BrandKit.query.filter_by(id=kit_id, user_id=current_user.id).first()
    if not kit:
        return jsonify({'error': 'Not found'}), 404
    db.session.delete(kit)
    db.session.commit()
    return jsonify({'success': True})


@agent_bp.route('/upload-logo', methods=['POST'])
@login_required
def upload_logo():
    if 'logo' not in request.files:
        return jsonify({'error': 'No file'}), 400
    f = request.files['logo']
    if not f.filename:
        return jsonify({'error': 'No file selected'}), 400

    upload_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                              'static', 'uploads', 'logos')
    os.makedirs(upload_dir, exist_ok=True)

    import uuid
    ext = os.path.splitext(f.filename)[1] or '.png'
    filename = f"logo_{uuid.uuid4().hex[:8]}{ext}"
    filepath = os.path.join(upload_dir, filename)
    f.save(filepath)

    rel_path = f"uploads/logos/{filename}"
    return jsonify({'success': True, 'path': rel_path})


@agent_bp.route('/launch', methods=['POST'])
@login_required
def launch_job():
    data = request.get_json() or {}
    kit_id = data.get('brand_kit_id', '').strip()
    if not kit_id:
        return jsonify({'error': 'Select a brand kit'}), 400

    kit = BrandKit.query.filter_by(id=kit_id, user_id=current_user.id).first()
    if not kit:
        return jsonify({'error': 'Brand kit not found'}), 404

    target_count = data.get('target_count', 20)
    content_types = data.get('content_types', ['social_post', 'banner', 'a_plus', 'lifestyle', 'ad_creative'])

    job = AgentJob(
        user_id=current_user.id,
        brand_kit_id=kit_id,
        target_count=min(target_count, 25),
        content_types=json.dumps(content_types),
        status='pending',
    )
    db.session.add(job)
    db.session.commit()

    # Run pipeline in background thread
    from modules.agent_pipeline import run_agent_pipeline
    flask_app = current_app._get_current_object()
    t = threading.Thread(target=run_agent_pipeline, args=(flask_app, job.id), daemon=True)
    t.start()

    return jsonify({'success': True, 'job_id': job.id})


@agent_bp.route('/status/<job_id>')
@login_required
def job_status(job_id):
    job = AgentJob.query.filter_by(id=job_id, user_id=current_user.id).first()
    if not job:
        return jsonify({'error': 'Not found'}), 404

    return jsonify({
        'status': job.status,
        'current_agent': job.current_agent,
        'progress': job.progress,
        'message': job.message,
        'collection_id': job.collection_id,
        'error_message': job.error_message,
    })


@agent_bp.route('/jobs')
@login_required
def list_jobs():
    jobs = AgentJob.query.filter_by(user_id=current_user.id)\
        .order_by(AgentJob.created_at.desc()).limit(10).all()
    return jsonify({'jobs': [{
        'id': j.id,
        'brand_kit_id': j.brand_kit_id,
        'status': j.status,
        'progress': j.progress,
        'message': j.message,
        'target_count': j.target_count,
        'collection_id': j.collection_id,
        'created_at': j.created_at.isoformat() if j.created_at else '',
    } for j in jobs]})
