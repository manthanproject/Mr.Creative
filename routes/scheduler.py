from flask import Blueprint, render_template, request, jsonify, current_app
from flask_login import login_required, current_user
from models import db, ScheduledJob, Prompt, Collection
from datetime import datetime, timedelta
import json
import os

scheduler_bp = Blueprint('scheduler', __name__)


@scheduler_bp.route('/')
@login_required
def index():
    jobs = ScheduledJob.query.filter_by(user_id=current_user.id)\
        .order_by(ScheduledJob.scheduled_time.asc()).all()

    prompts = Prompt.query.filter_by(user_id=current_user.id, is_approved=True)\
        .order_by(Prompt.created_at.desc()).all()

    collections = Collection.query.filter_by(user_id=current_user.id)\
        .order_by(Collection.name.asc()).all()

    now = datetime.now()
    upcoming = [j for j in jobs if j.is_active and (j.next_run or j.scheduled_time) >= now]
    past = [j for j in jobs if not j.is_active or (j.next_run or j.scheduled_time) < now]

    try:
        from modules.auto_scheduler import get_scheduler_status
        scheduler_status = get_scheduler_status()
    except Exception:
        scheduler_status = {'running': False}

    return render_template('scheduler.html',
        jobs=jobs,
        upcoming=upcoming,
        past=past,
        prompts=prompts,
        collections=collections,
        now=now,
        scheduler_status=scheduler_status,
    )


@scheduler_bp.route('/create', methods=['POST'])
@login_required
def create():
    """Create a scheduled job. Supports JSON (campaign/generate) and FormData (photoshoot with image)."""
    if request.content_type and 'multipart/form-data' in request.content_type:
        name = request.form.get('name', '').strip()
        prompt_text = request.form.get('prompt_text', '').strip()
        feature = request.form.get('pomelli_feature', 'campaign')
        schedule_type = request.form.get('schedule_type', 'once')
        scheduled_time_str = request.form.get('scheduled_time', '')
        aspect_ratio = request.form.get('aspect_ratio', 'story')
        templates_json = request.form.get('templates', '[]')
        product_url = request.form.get('product_url', '').strip()

        image_file = request.files.get('image')
        saved_image_path = None
        if image_file and image_file.filename:
            from werkzeug.utils import secure_filename
            upload_dir = os.path.join(current_app.static_folder or 'static', 'uploads', 'scheduled')
            os.makedirs(upload_dir, exist_ok=True)
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            safe_name = secure_filename(image_file.filename)
            saved_filename = f"{timestamp}_{safe_name}"
            saved_image_path = os.path.join(upload_dir, saved_filename)
            image_file.save(saved_image_path)
    else:
        data = request.get_json() or {}
        name = data.get('name', '').strip()
        prompt_text = data.get('prompt_text', '').strip()
        feature = data.get('pomelli_feature', 'campaign')
        schedule_type = data.get('schedule_type', 'once')
        scheduled_time_str = data.get('scheduled_time', '')
        aspect_ratio = data.get('aspect_ratio', 'story')
        templates_json = json.dumps(data.get('templates', []))
        product_url = data.get('product_url', '').strip()
        saved_image_path = None

    if not name:
        return jsonify({'error': 'Job name is required'}), 400
    if not prompt_text and feature not in ('photoshoot',):
        return jsonify({'error': 'Prompt text is required'}), 400
    if feature == 'photoshoot' and not saved_image_path:
        return jsonify({'error': 'Product image is required for photoshoot'}), 400
    if not scheduled_time_str:
        return jsonify({'error': 'Scheduled time is required'}), 400

    try:
        scheduled_time = datetime.fromisoformat(scheduled_time_str)
    except (ValueError, TypeError):
        return jsonify({'error': 'Invalid date/time format'}), 400

    try:
        templates = json.loads(templates_json)
        if not isinstance(templates, list):
            templates = []
    except (json.JSONDecodeError, TypeError):
        templates = []

    job = ScheduledJob(
        user_id=current_user.id,
        name=name,
        prompt_text=prompt_text,
        pomelli_feature=feature,
        schedule_type=schedule_type,
        scheduled_time=scheduled_time,
        next_run=scheduled_time,
        is_active=True,
        image_path=saved_image_path,
        templates=json.dumps(templates),
        aspect_ratio=aspect_ratio,
        product_url=product_url,
    )
    db.session.add(job)
    db.session.commit()

    return jsonify({
        'success': True,
        'job': _job_to_dict(job),
        'message': f'Scheduled "{name}" ({feature}) for {scheduled_time.strftime("%b %d, %H:%M")}'
    })


@scheduler_bp.route('/<job_id>/update', methods=['POST'])
@login_required
def update(job_id):
    job = ScheduledJob.query.filter_by(id=job_id, user_id=current_user.id).first_or_404()
    data = request.get_json() or {}

    if 'name' in data:
        job.name = data['name'].strip()
    if 'prompt_text' in data:
        job.prompt_text = data['prompt_text'].strip()
    if 'pomelli_feature' in data:
        job.pomelli_feature = data['pomelli_feature']
    if 'schedule_type' in data:
        job.schedule_type = data['schedule_type']
    if 'aspect_ratio' in data:
        job.aspect_ratio = data['aspect_ratio']
    if 'templates' in data:
        job.templates = json.dumps(data['templates'])
    if 'scheduled_time' in data:
        try:
            job.scheduled_time = datetime.fromisoformat(data['scheduled_time'])
            job.next_run = job.scheduled_time
        except (ValueError, TypeError):
            return jsonify({'error': 'Invalid date/time'}), 400

    db.session.commit()
    return jsonify({'success': True, 'job': _job_to_dict(job)})


@scheduler_bp.route('/<job_id>/toggle', methods=['POST'])
@login_required
def toggle(job_id):
    job = ScheduledJob.query.filter_by(id=job_id, user_id=current_user.id).first_or_404()
    job.is_active = not job.is_active

    if job.is_active:
        now = datetime.now()
        if job.schedule_type == 'once':
            job.next_run = job.scheduled_time if job.scheduled_time > now else None
        elif job.schedule_type == 'daily':
            next_run = job.scheduled_time
            while next_run <= now:
                next_run += timedelta(days=1)
            job.next_run = next_run
        elif job.schedule_type == 'weekly':
            next_run = job.scheduled_time
            while next_run <= now:
                next_run += timedelta(weeks=1)
            job.next_run = next_run

    db.session.commit()
    return jsonify({
        'success': True,
        'is_active': job.is_active,
        'job': _job_to_dict(job),
    })


@scheduler_bp.route('/<job_id>/delete', methods=['POST'])
@login_required
def delete(job_id):
    job = ScheduledJob.query.filter_by(id=job_id, user_id=current_user.id).first_or_404()
    db.session.delete(job)
    db.session.commit()
    return jsonify({'success': True})


@scheduler_bp.route('/bulk-delete', methods=['POST'])
@login_required
def bulk_delete():
    data = request.get_json() or {}
    ids = data.get('ids', [])
    if not ids:
        return jsonify({'error': 'No jobs selected'}), 400

    deleted = 0
    for jid in ids:
        job = ScheduledJob.query.filter_by(id=jid, user_id=current_user.id).first()
        if job:
            db.session.delete(job)
            deleted += 1

    db.session.commit()
    return jsonify({
        'success': True,
        'deleted': deleted,
        'message': f'{deleted} job{"s" if deleted != 1 else ""} deleted'
    })


@scheduler_bp.route('/<job_id>/run-now', methods=['POST'])
@login_required
def run_now(job_id):
    """Trigger a scheduled job immediately — supports campaign, photoshoot, and generate."""
    job = ScheduledJob.query.filter_by(id=job_id, user_id=current_user.id).first_or_404()

    from routes.generate import (
        update_bot_status, run_bot_in_background, run_photoshoot_in_background
    )
    from models import JobQueue, Collection

    col_name = job.name[:50]
    collection = Collection(
        user_id=current_user.id,
        name=col_name,
        description=f'Scheduled: {job.name} ({job.pomelli_feature})'
    )
    db.session.add(collection)
    db.session.flush()

    queue_job = JobQueue(
        user_id=current_user.id,
        job_type='generate' if job.pomelli_feature == 'campaign' else 'photoshoot',
        status='queued',
    )
    db.session.add(queue_job)
    db.session.commit()

    job.last_run = datetime.now()
    if job.schedule_type == 'once':
        job.is_active = False
        job.next_run = None
    elif job.schedule_type == 'daily':
        job.next_run = datetime.now() + timedelta(days=1)
    elif job.schedule_type == 'weekly':
        job.next_run = datetime.now() + timedelta(weeks=1)
    db.session.commit()

    update_bot_status(queue_job.id, 'queued', f'Starting: {job.name}...', 0)

    try:
        templates = json.loads(job.templates) if job.templates else []
    except (json.JSONDecodeError, TypeError):
        templates = []

    import threading
    app = current_app

    if job.pomelli_feature == 'photoshoot':
        thread = threading.Thread(
            target=run_photoshoot_in_background,
            args=(app, job.image_path, templates, 'product',
                  collection.id, current_user.id, queue_job.id,
                  job.prompt_text, job.aspect_ratio),
            daemon=True
        )
    elif job.pomelli_feature == 'generate':
        thread = threading.Thread(
            target=run_photoshoot_in_background,
            args=(app, job.image_path, [], 'generate',
                  collection.id, current_user.id, queue_job.id,
                  job.prompt_text, job.aspect_ratio),
            daemon=True
        )
    else:
        # Campaign — text prompt with optional product_url, image, aspect_ratio
        thread = threading.Thread(
            target=run_bot_in_background,
            args=(app, job.prompt_text, collection.id, current_user.id, queue_job.id,
                  False, job.product_url or '', job.aspect_ratio, job.image_path),
            daemon=True
        )
    thread.start()

    return jsonify({
        'success': True,
        'queue_job_id': queue_job.id,
        'collection_id': collection.id,
        'message': f'Running "{job.name}" now!'
    })


@scheduler_bp.route('/badge-count')
@login_required
def badge_count():
    now = datetime.now()
    count = ScheduledJob.query.filter(
        ScheduledJob.user_id == current_user.id,
        ScheduledJob.is_active == True,
        ScheduledJob.next_run != None,
        ScheduledJob.next_run >= now,
    ).count()
    return jsonify({'count': count})


def _job_to_dict(job):
    try:
        templates = json.loads(job.templates) if job.templates else []
    except (json.JSONDecodeError, TypeError):
        templates = []

    return {
        'id': job.id,
        'name': job.name,
        'prompt_text': job.prompt_text,
        'pomelli_feature': job.pomelli_feature,
        'schedule_type': job.schedule_type,
        'scheduled_time': job.scheduled_time.isoformat() if job.scheduled_time else None,
        'next_run': job.next_run.isoformat() if job.next_run else None,
        'last_run': job.last_run.isoformat() if job.last_run else None,
        'is_active': job.is_active,
        'image_path': job.image_path,
        'templates': templates,
        'aspect_ratio': job.aspect_ratio,
        'product_url': job.product_url,
        'created_at': job.created_at.isoformat(),
    }