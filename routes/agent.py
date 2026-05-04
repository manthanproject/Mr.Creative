from flask import Blueprint, render_template, request, jsonify, current_app, flash, redirect, url_for
from flask_login import login_required, current_user
from models import db, BrandKit, AgentJob, Collection, Generation
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


@agent_bp.route('/clear-history', methods=['POST'])
@login_required
def clear_history():
    jobs = AgentJob.query.filter_by(user_id=current_user.id).all()
    count = len(jobs)
    for job in jobs:
        db.session.delete(job)
    db.session.commit()
    flash(f'Cleared {count} jobs from history', 'success')
    return redirect(url_for('agent.index'))


@agent_bp.route('/job/<job_id>/pause', methods=['POST'])
@login_required
def pause_job(job_id):
    job = AgentJob.query.filter_by(id=job_id, user_id=current_user.id).first()
    if not job or job.status in ('complete', 'failed'):
        return jsonify({'error': 'Cannot pause this job'}), 400
    if job.control_action == 'pause':
        job.control_action = ''  # Toggle: unpause
    else:
        job.control_action = 'pause'
    db.session.commit()
    return jsonify({'success': True, 'action': job.control_action})


@agent_bp.route('/job/<job_id>/stop', methods=['POST'])
@login_required
def stop_job(job_id):
    job = AgentJob.query.filter_by(id=job_id, user_id=current_user.id).first()
    if not job or job.status in ('complete', 'failed'):
        return jsonify({'error': 'Cannot stop this job'}), 400
    job.control_action = 'stop'
    db.session.commit()
    return jsonify({'success': True})


@agent_bp.route('/upload-reference', methods=['POST'])
@login_required
def upload_reference():
    if 'image' not in request.files:
        return jsonify({'error': 'No file'}), 400
    f = request.files['image']
    if not f.filename:
        return jsonify({'error': 'No file selected'}), 400

    upload_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                              'static', 'uploads', 'references')
    os.makedirs(upload_dir, exist_ok=True)

    import uuid as _uuid
    ext = os.path.splitext(f.filename)[1] or '.png'
    filename = f"ref_{_uuid.uuid4().hex[:8]}{ext}"
    filepath = os.path.join(upload_dir, filename)
    f.save(filepath)

    rel_path = f"uploads/references/{filename}"
    return jsonify({'success': True, 'path': rel_path})


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
    aspect_ratio = data.get('aspect_ratio', 'mixed')
    reference_image = data.get('reference_image', None)
    post_options = data.get('post_options', {})

    job = AgentJob(
        user_id=current_user.id,
        brand_kit_id=kit_id,
        target_count=min(target_count, 25),
        content_types=json.dumps(content_types),
        aspect_ratio=aspect_ratio,
        reference_image=reference_image,
        post_options=json.dumps(post_options),
        status='pending',
    )
    db.session.add(job)
    db.session.commit()

    # Run pipeline in background thread
    from modules.agent_pipeline import run_agent_pipeline
    flask_app = current_app
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
        'control_action': job.control_action or '',
        'llm_provider': job.llm_provider or '',
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


@agent_bp.route('/mockups/<job_id>', methods=['POST'])
@login_required
def generate_mockups(job_id):
    """Generate mockups from a completed job's results."""
    job = AgentJob.query.filter_by(id=job_id, user_id=current_user.id).first()
    if not job or job.status != 'complete':
        return jsonify({'error': 'Job not found or not complete'}), 400

    results = json.loads(job.results) if job.results else []
    brand_kit = BrandKit.query.get(job.brand_kit_id)
    if not brand_kit:
        return jsonify({'error': 'Brand kit not found'}), 404

    # Use first successful image for mockups
    first_image = None
    base_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'static')
    for r in results:
        if 'error' not in r and r.get('path'):
            candidate = os.path.join(base_dir, r['path'])
            if os.path.exists(candidate):
                first_image = candidate
                break

    if not first_image:
        return jsonify({'error': 'No images found in job results'}), 400

    data = request.get_json() or {}
    mockup_types = data.get('types', ['phone', 'laptop', 'floating'])

    from modules.mockup_generator import generate_mockup as gen_mockup
    output_dir = os.path.join(base_dir, 'outputs', f'collection_{job.collection_id}')
    os.makedirs(output_dir, exist_ok=True)

    generated = []
    for mtype in mockup_types:
        out_path = os.path.join(output_dir, f'mockup_{mtype}.png')
        result = gen_mockup(
            mtype, first_image, out_path,
            brand_name=brand_kit.name,
            bg_color=brand_kit.primary_color,
            accent_color=brand_kit.accent_color,
        )
        if result:
            rel = os.path.relpath(result, base_dir).replace('\\', '/')
            generated.append({'type': mtype, 'path': rel})

            # Add to collection
            gen = Generation(
                user_id=job.user_id,
                collection_id=job.collection_id,
                output_path=rel,
                pomelli_feature='mockup',
                status='completed',
                tags=f'Mockup — {mtype} | {brand_kit.name}',
            )
            db.session.add(gen)

    db.session.commit()
    return jsonify({'success': True, 'mockups': generated})


@agent_bp.route('/carousel/<job_id>', methods=['POST'])
@login_required
def generate_carousel_route(job_id):
    """Generate Instagram carousel from a completed job's results."""
    job = AgentJob.query.filter_by(id=job_id, user_id=current_user.id).first()
    if not job or job.status != 'complete':
        return jsonify({'error': 'Job not found or not complete'}), 400

    results = json.loads(job.results) if job.results else []
    brand_kit = BrandKit.query.get(job.brand_kit_id)
    if not brand_kit:
        return jsonify({'error': 'Brand kit not found'}), 404

    base_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'static')

    # Collect successful image paths (max 8 for carousel)
    image_paths = []
    captions = []
    for r in results:
        if 'error' not in r and r.get('path'):
            full = os.path.join(base_dir, r['path'])
            if os.path.exists(full):
                image_paths.append(full)
                captions.append(r.get('caption', r.get('title', '')))
        if len(image_paths) >= 8:
            break

    if len(image_paths) < 2:
        return jsonify({'error': 'Need at least 2 images for a carousel'}), 400

    data = request.get_json() or {}
    hook = data.get('hook_headline', f'{brand_kit.name}\nContent Collection')
    hook_sub = data.get('hook_subheadline', 'Swipe to explore →')
    cta = data.get('cta_text', f'Follow @{brand_kit.name.lower().replace(" ", "")}\nfor more')

    from modules.carousel_generator import generate_carousel
    output_dir = os.path.join(base_dir, 'outputs', f'collection_{job.collection_id}', 'carousel')

    slides = generate_carousel(
        image_paths=image_paths,
        output_dir=output_dir,
        brand_name=brand_kit.name,
        hook_headline=hook,
        hook_subheadline=hook_sub,
        captions=captions,
        cta_text=cta,
        primary=brand_kit.primary_color,
        secondary=brand_kit.secondary_color,
        accent=brand_kit.accent_color,
        heading_font=brand_kit.heading_font,
        body_font=brand_kit.body_font,
    )

    generated = []
    for slide_path in slides:
        rel = os.path.relpath(slide_path, base_dir).replace('\\', '/')
        generated.append({'path': rel})

        gen = Generation(
            user_id=job.user_id,
            collection_id=job.collection_id,
            output_path=rel,
            pomelli_feature='carousel',
            status='completed',
            tags=f'Carousel | {brand_kit.name}',
        )
        db.session.add(gen)

    db.session.commit()
    return jsonify({'success': True, 'slides': generated, 'count': len(generated)})
