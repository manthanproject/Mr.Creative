from flask import Blueprint, render_template, request, jsonify, current_app
from flask_login import login_required, current_user
from models import db, Prompt, Generation, Collection, JobQueue
from datetime import datetime
import os
import threading
import json
import shutil
import zipfile
import re

generate_bp = Blueprint('generate', __name__)

# Global bot status for real-time updates
_bot_status = {}


def cleanup_stale_jobs(app):
    """Mark old stuck jobs as 'failed' on server startup.
    Only cleans jobs older than 1 hour (processing) or 10 min (queued)
    to avoid killing jobs that are still genuinely running after a Flask reload."""
    from datetime import timedelta
    with app.app_context():
        now = datetime.now()
        stale_count = 0

        # Processing jobs older than 1 hour are definitely stuck
        old_processing = JobQueue.query.filter(
            JobQueue.status == 'processing',
            JobQueue.started_at < now - timedelta(hours=1)
        ).all()
        for job in old_processing:
            job.status = 'failed'
            job.error_message = 'Timed out — job ran over 1 hour'
            stale_count += 1

        # Queued jobs older than 10 minutes never started
        old_queued = JobQueue.query.filter(
            JobQueue.status == 'queued',
            JobQueue.created_at < now - timedelta(minutes=10)
        ).all()
        for job in old_queued:
            job.status = 'failed'
            job.error_message = 'Never started — server may have restarted'
            stale_count += 1

        if stale_count:
            db.session.commit()
            print(f"[Cleanup] Marked {stale_count} stale job(s) as failed")

# ── Persistent Bot Manager ──
# Keeps Chrome alive between jobs. Only re-creates when account changes.
_persistent_bot = None
_persistent_bot_email = None
_persistent_bot_lock = threading.Lock()

# ── Job Execution Lock ──
# Ensures only ONE job runs the bot at a time. Others wait in line.
_job_execution_lock = threading.Lock()
_current_running_job_id = None


def _get_or_create_bot(config):
    """Get the persistent bot, reusing Chrome if the account hasn't changed.
    Creates a new bot + Chrome session only when:
    - First run (no bot exists)
    - Account email changed (user switched from UI)
    - Chrome session died/crashed
    """
    global _persistent_bot, _persistent_bot_email
    from modules.selenium_bot import PomelliBot

    new_email = config.get('google_email', '')

    with _persistent_bot_lock:
        # Check if we need a fresh bot
        need_new = False

        if _persistent_bot is None:
            need_new = True
            print(f"[BotManager] No existing bot, creating new one for {new_email}")
        elif _persistent_bot_email and new_email and _persistent_bot_email.lower() != new_email.lower():
            print(f"[BotManager] Account changed: {_persistent_bot_email} → {new_email}")
            # Account changed — aggressively kill old Chrome
            try:
                if _persistent_bot.driver:
                    _persistent_bot.driver.quit()
            except Exception:
                pass
            try:
                _persistent_bot._kill_orphaned_chrome()
            except Exception:
                pass
            import time as _time
            _time.sleep(3)
            _persistent_bot = None
            need_new = True
        else:
            # Same account — reuse if Chrome is still alive
            try:
                title = _persistent_bot.driver.title
                print(f"[BotManager] Reusing existing Chrome session ({_persistent_bot_email}) — page: {title[:50]}")
            except Exception:
                print(f"[BotManager] Chrome session dead, creating new one")
                try:
                    _persistent_bot.driver.quit()
                except Exception:
                    pass
                _persistent_bot = None
                need_new = True

        if need_new:
            was_account_switch = (_persistent_bot_email is not None and
                                  new_email and
                                  _persistent_bot_email.lower() != new_email.lower())
            _persistent_bot = PomelliBot(config)
            _persistent_bot_email = new_email
            if was_account_switch:
                _persistent_bot._force_relogin = True

    return _persistent_bot


def _release_bot_for_reuse(bot):
    """After a job finishes, prepare bot for next job reuse.
    Navigate back to Pomelli home so next job starts clean."""
    global _persistent_bot_email
    # Reset per-job state but keep the driver alive
    bot._pending_ideas = []
    bot._selected_idea = None
    bot._pending_animate_cards = []
    bot._selected_animate_indices = None
    bot._current_job_id = None
    bot.errors = []
    # Navigate back to Pomelli home for next job
    try:
        bot.driver.get('https://labs.google.com/pomelli')
        print("[BotManager] Navigated back to Pomelli home for next job")
    except Exception:
        pass
    # Remember which account we're logged into
    _persistent_bot_email = bot.config.get('google_email', '')


def get_bot_status(job_id):
    return _bot_status.get(job_id, {
        'step': 'queued',
        'message': 'Waiting to start...',
        'progress': 0,
    })


def update_bot_status(job_id, step, message, progress=0):
    _bot_status[job_id] = {
        'step': step,
        'message': message,
        'progress': progress,
        'updated_at': datetime.now().isoformat(),
    }


def _hook_bot_status(bot, job_id):
    """Hook into bot status updates for real-time UI progress."""
    original_update = bot._update_status

    def status_hook(status, message=''):
        original_update(status, message)
        progress_map = {
            'idle': 0, 'logging_in': 5, 'navigating': 10,
            'entering_prompt': 20, 'generating': 40,
            'animating': 60, 'downloading': 75,
            'complete': 100, 'error': -1,
        }
        pct = progress_map.get(status, 30)

        # Fine-grained progress from message keywords
        msg_lower = message.lower()
        if 'ideas' in msg_lower:
            pct = 30
        if 'creatives' in msg_lower and 'loading' in msg_lower:
            pct = 50
        if 'ready' in msg_lower or 'loaded' in msg_lower:
            pct = 65
        if 'downloaded creative' in msg_lower or 'downloaded photoshoot' in msg_lower:
            pct = 80
        if 'uploading' in msg_lower:
            pct = 15
        if 'template' in msg_lower:
            pct = 25
        if 'create photoshoot' in msg_lower:
            pct = 35
        if 'generating photoshoot' in msg_lower:
            pct = 50
        if 'download all' in msg_lower:
            pct = 85
        # Animate-specific progress
        if 'extracting card' in msg_lower:
            pct = 55
        if 'waiting_for_animate' in msg_lower:
            pct = 58
        if 'animating' in msg_lower and 'card' in msg_lower:
            pct = 62
        if 'waiting for all videos' in msg_lower:
            pct = 65
        if 'animations complete' in msg_lower or 'all animations' in msg_lower:
            pct = 72
        if 'downloading videos' in msg_lower:
            pct = 78
        if 'downloading images' in msg_lower:
            pct = 76
        if status == 'complete':
            pct = 100

        update_bot_status(job_id, status, message, pct)

        # If bot has pending ideas, include them in status
        if hasattr(bot, '_pending_ideas') and bot._pending_ideas:
            _bot_status[job_id]['ideas'] = bot._pending_ideas

        # If bot has pending animate cards, include them in status
        if hasattr(bot, '_pending_animate_cards') and bot._pending_animate_cards:
            _bot_status[job_id]['animate_cards'] = bot._pending_animate_cards

    bot._update_status = status_hook


def _save_downloaded_files(app, result, collection_id, user_id, job, feature='campaign'):
    """Save downloaded files to collection. Returns count of saved files."""
    output_folder = app.config.get('OUTPUT_FOLDER',
        os.path.join(app.static_folder, 'outputs'))
    col_dir = os.path.join(output_folder, f'collection_{collection_id}')
    os.makedirs(col_dir, exist_ok=True)

    saved_count = 0
    for filepath in result['downloaded_files']:
        if os.path.exists(filepath):
            filename = os.path.basename(filepath)
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            new_name = f"{timestamp}_{filename}"
            dest = os.path.join(col_dir, new_name)
            shutil.copy2(filepath, dest)

            # Determine output type from extension
            ext = os.path.splitext(filename)[1].lower()
            output_type = 'video' if ext in ('.mp4', '.webm', '.mov') else 'image'

            gen = Generation(
                user_id=user_id,
                collection_id=collection_id,
                input_type='image' if feature == 'photoshoot' else 'text',
                output_type=output_type,
                output_path=f'outputs/collection_{collection_id}/{new_name}',
                pomelli_feature=feature,
                status='completed',
                file_size=os.path.getsize(dest),
                completed_at=datetime.now(),
            )
            db.session.add(gen)
            saved_count += 1

    return saved_count


def run_bot_in_background(app, prompt_text, collection_id, user_id, job_id,
                          enable_animate=False, product_url=None,
                          campaign_aspect_ratio=None, campaign_images=0):
    """Background thread for campaign generation. Waits for queue lock."""
    global _current_running_job_id

    with app.app_context():
        # Wait for queue lock — only one job at a time
        if _job_execution_lock.locked():
            update_bot_status(job_id, 'queued',
                f'Waiting in queue... (job {_current_running_job_id[:8] if _current_running_job_id else "?"} is running)', 1)
            print(f"[Queue] Job {job_id[:8]} waiting — bot busy with {_current_running_job_id[:8] if _current_running_job_id else '?'}")

        _job_execution_lock.acquire()
        _current_running_job_id = job_id
        print(f"[Queue] Job {job_id[:8]} acquired lock — starting")

        try:
            job = db.session.get(JobQueue, job_id)
            if not job:
                return
            # Check if job was cancelled while waiting
            db.session.refresh(job)
            if job.status == 'failed':
                print(f"[Queue] Job {job_id[:8]} was cancelled while waiting — skipping")
                return

            job.status = 'processing'
            job.started_at = datetime.now()
            db.session.commit()

            config = {
                'google_email': app.config.get('GOOGLE_EMAIL', ''),
                'google_password': app.config.get('GOOGLE_PASSWORD', ''),
                'download_dir': os.path.join(app.static_folder, 'downloads'),
                'headless': False,
            }

            bot = _get_or_create_bot(config)
            bot.config = config
            bot._current_job_id = job_id
            bot._pending_ideas = []
            bot._selected_idea = None
            bot._pending_animate_cards = []
            bot._selected_animate_indices = None
            _hook_bot_status(bot, job_id)

            try:
                update_bot_status(job_id, 'connecting', 'Connecting to Chrome...', 5)
                result = bot.run_full_workflow(
                    prompt_text=prompt_text,
                    enable_animate_selection=enable_animate,
                    product_url=product_url,
                    campaign_aspect_ratio=campaign_aspect_ratio,
                    campaign_images=campaign_images if campaign_images else None,
                )

                if result['success'] and result['downloaded_files']:
                    update_bot_status(job_id, 'saving', 'Saving to collection...', 90)
                    saved_count = _save_downloaded_files(
                        app, result, collection_id, user_id, job, feature='campaign')
                    job.status = 'completed'
                    job.completed_at = datetime.now()
                    update_bot_status(job_id, 'complete',
                        f'Done! {saved_count} assets saved.', 100)
                else:
                    job.status = 'failed'
                    error_msg = '; '.join(result.get('errors', ['No files downloaded']))
                    job.error_message = error_msg[:200]
                    update_bot_status(job_id, 'error', error_msg[:100], -1)

            except Exception as e:
                job.status = 'failed'
                job.error_message = str(e)[:200]
                update_bot_status(job_id, 'error', str(e)[:100], -1)

            db.session.commit()
            _release_bot_for_reuse(bot)

        finally:
            _current_running_job_id = None
            _job_execution_lock.release()
            print(f"[Queue] Job {job_id[:8]} released lock")


def run_photoshoot_in_background(app, image_path, templates, photoshoot_mode,
                                  collection_id, user_id, job_id, prompt_text='',
                                  aspect_ratio='story'):
    """Background thread for photoshoot generation. Waits for queue lock."""
    global _current_running_job_id

    with app.app_context():
        # Wait for queue lock — only one job at a time
        if _job_execution_lock.locked():
            update_bot_status(job_id, 'queued',
                f'Waiting in queue... (job {_current_running_job_id[:8] if _current_running_job_id else "?"} is running)', 1)
            print(f"[Queue] Photoshoot {job_id[:8]} waiting — bot busy with {_current_running_job_id[:8] if _current_running_job_id else '?'}")

        _job_execution_lock.acquire()
        _current_running_job_id = job_id
        print(f"[Queue] Photoshoot {job_id[:8]} acquired lock — starting")

        try:
            job = db.session.get(JobQueue, job_id)
            if not job:
                return
            db.session.refresh(job)
            if job.status == 'failed':
                print(f"[Queue] Photoshoot {job_id[:8]} was cancelled while waiting — skipping")
                return

            job.status = 'processing'
            job.started_at = datetime.now()
            db.session.commit()

            config = {
                'google_email': app.config.get('GOOGLE_EMAIL', ''),
                'google_password': app.config.get('GOOGLE_PASSWORD', ''),
                'download_dir': os.path.join(app.static_folder, 'downloads'),
                'headless': False,
                'aspect_ratio': aspect_ratio,
            }

            bot = _get_or_create_bot(config)
            bot.config = config
            bot._current_job_id = job_id
            _hook_bot_status(bot, job_id)

            try:
                update_bot_status(job_id, 'connecting', 'Connecting to Chrome...', 5)
                result = bot.run_full_workflow(
                    prompt_text=prompt_text,
                    image_path=image_path,
                    templates=templates,
                    photoshoot_mode=photoshoot_mode,
                )

                if result['success'] and result['downloaded_files']:
                    update_bot_status(job_id, 'saving', 'Saving photoshoot to collection...', 90)
                    saved_count = _save_downloaded_files(
                        app, result, collection_id, user_id, job, feature='photoshoot')
                    job.status = 'completed'
                    job.completed_at = datetime.now()
                    update_bot_status(job_id, 'complete',
                        f'Done! {saved_count} photoshoot assets saved.', 100)
                else:
                    job.status = 'failed'
                    error_msg = '; '.join(result.get('errors', ['No files downloaded']))
                    job.error_message = error_msg[:200]
                    update_bot_status(job_id, 'error', error_msg[:100], -1)

            except Exception as e:
                job.status = 'failed'
                job.error_message = str(e)[:200]
                update_bot_status(job_id, 'error', str(e)[:100], -1)

            db.session.commit()
            _release_bot_for_reuse(bot)

        finally:
            _current_running_job_id = None
            _job_execution_lock.release()
            print(f"[Queue] Photoshoot {job_id[:8]} released lock")


# ==========================================
# ROUTES
# ==========================================

@generate_bp.route('/')
@login_required
def index():
    approved_prompts = Prompt.query.filter_by(
        user_id=current_user.id, is_approved=True
    ).order_by(Prompt.created_at.desc()).all()

    collections = Collection.query.filter_by(user_id=current_user.id)\
        .order_by(Collection.name.asc()).all()

    recent_jobs = JobQueue.query.filter_by(user_id=current_user.id)\
        .order_by(JobQueue.created_at.desc()).limit(20).all()

    return render_template('generate.html',
        approved_prompts=approved_prompts,
        collections=collections,
        recent_jobs=recent_jobs,
        config=current_app.config,
    )


@generate_bp.route('/launch', methods=['POST'])
@login_required
def launch():
    """Launch a campaign generation job."""
    data = request.get_json() or {}
    prompt_id = data.get('prompt_id')
    collection_id = data.get('collection_id')
    custom_prompt = data.get('custom_prompt', '').strip()
    enable_animate = data.get('enable_animate', False)
    product_url = data.get('product_url', '').strip()
    campaign_aspect_ratio = data.get('campaign_aspect_ratio', '').strip() or None
    campaign_images = data.get('campaign_images', 0)  # Number of images to select, 0 = none

    prompt_text = custom_prompt
    if prompt_id:
        prompt = Prompt.query.filter_by(id=prompt_id, user_id=current_user.id).first()
        if prompt:
            prompt_text = prompt.text

    if not prompt_text:
        return jsonify({'error': 'Enter a prompt or select an approved one'}), 400

    col_name = prompt_text[:50].strip()
    if not collection_id:
        collection = Collection(
            user_id=current_user.id,
            name=col_name,
            description='Auto-generated by Mr.Creative bot'
        )
        db.session.add(collection)
        db.session.flush()
        collection_id = collection.id

    job = JobQueue(
        user_id=current_user.id,
        prompt_id=prompt_id,
        job_type='generate',
        status='queued',
    )
    db.session.add(job)
    db.session.commit()

    update_bot_status(job.id, 'queued', 'Starting bot...', 0)

    app = current_app._get_current_object()
    thread = threading.Thread(
        target=run_bot_in_background,
        args=(app, prompt_text, collection_id, current_user.id, job.id,
              enable_animate, product_url, campaign_aspect_ratio, campaign_images),
        daemon=True
    )
    thread.start()

    return jsonify({
        'success': True,
        'job_id': job.id,
        'collection_id': collection_id,
        'message': f'Generation started! Collection: "{col_name}"'
    })


@generate_bp.route('/upload-and-launch', methods=['POST'])
@login_required
def upload_and_launch():
    """Launch a photoshoot generation job with image upload."""
    image_file = request.files.get('image')
    has_image = image_file and image_file.filename

    photoshoot_mode = request.form.get('photoshoot_mode', 'product')
    if not has_image and photoshoot_mode not in ('generate', 'campaign'):
        return jsonify({'error': 'No image uploaded'}), 400

    collection_id = request.form.get('collection_id', '').strip()
    templates_json = request.form.get('templates', '[]')
    prompt_text = request.form.get('prompt_text', '').strip()
    aspect_ratio = request.form.get('aspect_ratio', 'story')
    product_url = request.form.get('product_url', '').strip()
    enable_animate = request.form.get('enable_animate', 'false').lower() == 'true'

    try:
        templates = json.loads(templates_json)
        if not isinstance(templates, list):
            templates = []
        templates = templates[:4]
    except (json.JSONDecodeError, TypeError):
        templates = []

    upload_dir = os.path.join(current_app.static_folder, 'uploads', 'photoshoot')
    os.makedirs(upload_dir, exist_ok=True)

    from werkzeug.utils import secure_filename
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    saved_path = None
    if has_image:
        safe_name = secure_filename(image_file.filename)
        saved_filename = f"{timestamp}_{safe_name}"
        saved_path = os.path.join(upload_dir, saved_filename)
        image_file.save(saved_path)
        name_no_ext = os.path.splitext(safe_name)[0]
        clean = re.sub(r'^\d{8}_\d{6}_', '', name_no_ext)
        clean = clean.replace('_', ' ').replace('-', ' ').strip().title()
        if not clean:
            clean = name_no_ext
        if photoshoot_mode == 'campaign':
            col_name = prompt_text[:50].strip() if prompt_text else f'Campaign — {clean[:40]}'
        else:
            col_name = f'Photoshoot — {clean[:40]}'
    else:
        col_name = f'Generated — {prompt_text[:40]}' if prompt_text else 'Generated Image'

    if not collection_id:
        desc = 'Auto-generated by Mr.Creative bot' if photoshoot_mode == 'campaign' else \
               f'AI Photoshoot ({", ".join(templates[:3]) if templates else "auto templates"})'
        collection = Collection(
            user_id=current_user.id,
            name=col_name,
            description=desc
        )
        db.session.add(collection)
        db.session.flush()
        collection_id = collection.id

    job = JobQueue(
        user_id=current_user.id,
        job_type='generate' if photoshoot_mode == 'campaign' else 'photoshoot',
        status='queued',
    )
    db.session.add(job)
    db.session.commit()

    app = current_app._get_current_object()

    if photoshoot_mode == 'campaign':
        # Campaign with image — use campaign bot
        update_bot_status(job.id, 'queued', 'Starting campaign bot...', 0)
        thread = threading.Thread(
            target=run_bot_in_background,
            args=(app, prompt_text, collection_id, current_user.id, job.id,
                  enable_animate, product_url, aspect_ratio, saved_path),
            daemon=True
        )
    else:
        # Photoshoot / Generate mode
        update_bot_status(job.id, 'queued', 'Starting photoshoot bot...', 0)
        thread = threading.Thread(
            target=run_photoshoot_in_background,
            args=(app, saved_path, templates, photoshoot_mode,
                  collection_id, current_user.id, job.id, prompt_text, aspect_ratio),
            daemon=True
        )
    thread.start()

    msg = 'Campaign started!' if photoshoot_mode == 'campaign' else 'Photoshoot started!'
    return jsonify({
        'success': True,
        'job_id': job.id,
        'collection_id': collection_id,
        'message': f'{msg} Collection: "{col_name}"'
    })


@generate_bp.route('/select-idea/<job_id>', methods=['POST'])
@login_required
def select_idea(job_id):
    """User selects an idea from the generated options."""
    data = request.get_json() or {}
    idea_index = data.get('index', 0)
    _bot_status.setdefault(job_id, {})['selected_idea'] = idea_index
    return jsonify({'success': True, 'selected': idea_index})


@generate_bp.route('/select-animate/<job_id>', methods=['POST'])
@login_required
def select_animate(job_id):
    """User selects which cards to animate (or skips)."""
    data = request.get_json() or {}
    indices = data.get('indices', [])  # [] means skip animation
    # Validate: must be list of ints 0-3
    valid_indices = [i for i in indices if isinstance(i, int) and 0 <= i <= 3]
    _bot_status.setdefault(job_id, {})['selected_animate_indices'] = valid_indices
    return jsonify({'success': True, 'animate_indices': valid_indices})


@generate_bp.route('/pause-job', methods=['POST'])
@login_required
def pause_job():
    """Pause the running bot at the next safe checkpoint."""
    if _persistent_bot and hasattr(_persistent_bot, 'pause'):
        _persistent_bot.pause()
        return jsonify({'success': True, 'paused': True})
    return jsonify({'success': False, 'error': 'No active bot'})


@generate_bp.route('/resume-job', methods=['POST'])
@login_required
def resume_job():
    """Resume the paused bot."""
    if _persistent_bot and hasattr(_persistent_bot, 'resume'):
        _persistent_bot.resume()
        return jsonify({'success': True, 'paused': False})
    return jsonify({'success': False, 'error': 'No active bot'})


@generate_bp.route('/status/<job_id>')
@login_required
def job_status(job_id):
    job = JobQueue.query.filter_by(id=job_id, user_id=current_user.id).first_or_404()
    bot_status = get_bot_status(job_id)

    # Check if bot is currently paused
    is_paused = False
    if _persistent_bot and hasattr(_persistent_bot, '_is_paused'):
        is_paused = _persistent_bot._is_paused

    # Queue info
    queue_busy = _job_execution_lock.locked()
    running_job = _current_running_job_id

    return jsonify({
        'job_id': job.id,
        'status': job.status,
        'ideas': bot_status.get('ideas', []),
        'animate_cards': bot_status.get('animate_cards', []),
        'error_message': job.error_message,
        'bot_step': bot_status.get('step', ''),
        'bot_message': bot_status.get('message', ''),
        'bot_progress': bot_status.get('progress', 0),
        'is_paused': is_paused,
        'queue_busy': queue_busy,
        'running_job_id': running_job,
        'created_at': job.created_at.isoformat(),
        'completed_at': job.completed_at.isoformat() if job.completed_at else None,
    })


@generate_bp.route('/active-job')
@login_required
def active_job():
    """Return the currently running/processing job (if any).
    DB is the source of truth — if a job says 'processing' or 'queued', it's active."""

    # Primary: Find any job that's still processing or queued in DB
    job = JobQueue.query.filter(
        JobQueue.user_id == current_user.id,
        JobQueue.status.in_(['processing', 'queued'])
    ).order_by(JobQueue.created_at.desc()).first()

    if not job:
        return jsonify({'active': False})

    # Get live bot status for this job
    bot_status = get_bot_status(job.id)

    # Find collection_id: check bot's current job first, then most recent collection
    collection_id = None
    collection = Collection.query.filter_by(user_id=current_user.id)\
        .order_by(Collection.created_at.desc()).first()
    if collection:
        collection_id = collection.id

    return jsonify({
        'active': True,
        'job_id': job.id,
        'collection_id': collection_id,
        'status': job.status,
        'bot_step': bot_status.get('step', ''),
        'bot_message': bot_status.get('message', ''),
        'bot_progress': bot_status.get('progress', 0),
    })


@generate_bp.route('/clear-jobs', methods=['POST'])
@login_required
def clear_jobs():
    JobQueue.query.filter_by(user_id=current_user.id).delete()
    db.session.commit()
    return jsonify({'success': True})


@generate_bp.route('/save-credentials', methods=['POST'])
@login_required
def save_credentials():
    """Hot-swap Google credentials and save to accounts list."""
    data = request.get_json() or {}
    email = data.get('email', '').strip()
    password = data.get('password', '').strip()

    if not email or not password:
        return jsonify({'error': 'Email and password are required'}), 400

    # Update in-memory config (takes effect on next bot run)
    current_app.config['GOOGLE_EMAIL'] = email
    current_app.config['GOOGLE_PASSWORD'] = password

    # Save to accounts file for future quick-switch
    _save_account(email, password)

    return jsonify({'success': True, 'email': email})


@generate_bp.route('/saved-accounts')
@login_required
def saved_accounts():
    """List saved accounts for Pomelli (filter out Flow-only accounts)."""
    accounts = _load_accounts()
    active = current_app.config.get('GOOGLE_EMAIL', '')
    # Pomelli accounts — exclude known Flow-only accounts
    flow_only = {'crimsonbox69@gmail.com'}
    filtered = [a for a in accounts if a['email'].lower() not in flow_only]
    return jsonify({
        'accounts': [{'email': a['email'], 'active': a['email'] == active} for a in filtered],
        'active': active,
    })


@generate_bp.route('/switch-account', methods=['POST'])
@login_required
def switch_account():
    """Quick-switch to a previously saved account."""
    data = request.get_json() or {}
    email = data.get('email', '').strip()
    if not email:
        return jsonify({'error': 'Email is required'}), 400

    accounts = _load_accounts()
    match = next((a for a in accounts if a['email'] == email), None)

    if match:
        current_app.config['GOOGLE_EMAIL'] = match['email']
        current_app.config['GOOGLE_PASSWORD'] = match.get('password', '')
        _save_active_account('pomelli', match['email'])
        return jsonify({'success': True, 'email': match['email']})

    # Account not in list — add it (no password needed with Chrome profiles)
    accounts.append({'email': email, 'password': 'profile-session'})
    _write_accounts(accounts)
    current_app.config['GOOGLE_EMAIL'] = email
    current_app.config['GOOGLE_PASSWORD'] = ''
    _save_active_account('pomelli', email)
    return jsonify({'success': True, 'email': email})


@generate_bp.route('/delete-account', methods=['POST'])
@login_required
def delete_account():
    """Remove a saved account."""
    data = request.get_json() or {}
    email = data.get('email', '').strip()
    if not email:
        return jsonify({'error': 'Email is required'}), 400

    accounts = _load_accounts()
    accounts = [a for a in accounts if a['email'] != email]
    _write_accounts(accounts)
    return jsonify({'success': True})


# ── Account storage helpers ──

def _accounts_file():
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'saved_accounts.json')


def _load_accounts():
    path = _accounts_file()
    if os.path.exists(path):
        try:
            with open(path, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return []
    return []


def _write_accounts(accounts):
    path = _accounts_file()
    with open(path, 'w') as f:
        json.dump(accounts, f, indent=2)


def _active_accounts_file():
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'active_accounts.json')


def _save_active_account(tool, email):
    """Persist which account is active for each tool (pomelli/flow)."""
    path = _active_accounts_file()
    data = {}
    if os.path.exists(path):
        try:
            with open(path, 'r') as f:
                data = json.load(f)
        except Exception:
            pass
    data[tool] = email
    with open(path, 'w') as f:
        json.dump(data, f, indent=2)


def _load_active_accounts():
    """Load persisted active accounts for all tools."""
    path = _active_accounts_file()
    if os.path.exists(path):
        try:
            with open(path, 'r') as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def _save_account(email, password):
    accounts = _load_accounts()
    # Update existing or add new
    found = False
    for a in accounts:
        if a['email'] == email:
            a['password'] = password
            found = True
            break
    if not found:
        accounts.append({'email': email, 'password': password})
    _write_accounts(accounts)