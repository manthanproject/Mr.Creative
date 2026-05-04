from flask import Blueprint, render_template, request, jsonify, current_app
from flask_login import login_required, current_user
from models import db, Collection, Generation
from datetime import datetime
import os
import threading
import uuid
import shutil

banners_bp = Blueprint('banners', __name__)

# Job status storage
_banner_jobs = {}


@banners_bp.route('/')
@login_required
def index():
    collections = Collection.query.filter_by(user_id=current_user.id)\
        .order_by(Collection.name.asc()).all()
    return render_template('banners.html', collections=collections)


@banners_bp.route('/generate', methods=['POST'])
@login_required
def generate():
    # Support both JSON and FormData
    if request.content_type and 'multipart/form-data' in request.content_type:
        prompt = request.form.get('prompt', '').strip()
        aspect_ratio = request.form.get('aspect_ratio', '1:1')
        count = min(int(request.form.get('count', 4)), 4)
        collection_id = request.form.get('collection_id', '').strip()
    else:
        data = request.get_json() or {}
        prompt = data.get('prompt', '').strip()
        aspect_ratio = data.get('aspect_ratio', '1:1')
        count = min(int(data.get('count', 4)), 4)
        collection_id = data.get('collection_id', '').strip()

    if not prompt:
        return jsonify({'error': 'Enter a banner prompt'}), 400

    # Handle image upload
    image_path = None
    image_file = request.files.get('image')
    if image_file and image_file.filename:
        upload_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'static', 'uploads')
        os.makedirs(upload_dir, exist_ok=True)
        safe_name = f"flow_{uuid.uuid4().hex[:8]}_{image_file.filename}"
        image_path = os.path.join(upload_dir, safe_name)
        image_file.save(image_path)

    # Create collection
    if not collection_id:
        col_name = f"Flow — {prompt[:40]}"
        collection = Collection(
            user_id=current_user.id,
            name=col_name,
            description=f'Generated via Flow Bot | {aspect_ratio} x{count}'
        )
        db.session.add(collection)
        db.session.flush()
        collection_id = collection.id
        db.session.commit()

    job_id = str(uuid.uuid4())
    _banner_jobs[job_id] = {
        'status': 'starting',
        'message': 'Connecting to Flow...',
        'progress': 0,
        'images': [],
        'errors': [],
        'collection_id': collection_id,
    }

    flask_app = current_app._get_current_object()

    thread = threading.Thread(
        target=_run_flow_bot,
        args=(job_id, prompt, aspect_ratio, count, collection_id, current_user.id, flask_app),
        kwargs={'image_path': image_path},
        daemon=True,
    )
    thread.start()

    return jsonify({'success': True, 'job_id': job_id, 'collection_id': collection_id})


@banners_bp.route('/status/<job_id>')
@login_required
def status(job_id):
    job = _banner_jobs.get(job_id, {})
    return jsonify(job)


@banners_bp.route('/active-job')
@login_required
def active_job():
    """Check if there's a running Flow job."""
    for job_id, job in _banner_jobs.items():
        if job.get('status') not in ('complete', 'error'):
            return jsonify({
                'active': True,
                'job_id': job_id,
                'collection_id': job.get('collection_id', ''),
                'status': job.get('status', ''),
                'message': job.get('message', ''),
                'progress': job.get('progress', 0),
            })
    return jsonify({'active': False})


def _run_flow_bot(job_id, prompt, aspect_ratio, count, collection_id, user_id, flask_app, image_path=None):
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service
    from modules.flow_bot import FlowBot

    job = _banner_jobs[job_id]
    driver = None

    try:
        # Auto-launch Flow Chrome if not running
        from modules.chrome_launcher import ensure_flow_chrome
        flow_email = flask_app.config.get('FLOW_GOOGLE_EMAIL', '')
        if not ensure_flow_chrome(flow_email):
            _banner_jobs[job_id]['status'] = 'error'
            _banner_jobs[job_id]['message'] = 'Could not launch Chrome for Flow. Start it manually.'
            return

        # Connect to Chrome on port 9222
        job['status'] = 'connecting'
        job['message'] = 'Connecting to Chrome...'
        job['progress'] = 5

        opts = Options()
        opts.add_experimental_option('debuggerAddress', '127.0.0.1:9223')

        local_driver = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'chromedriver.exe')
        if os.path.exists(local_driver):
            service = Service(local_driver)
            driver = webdriver.Chrome(service=service, options=opts)
        else:
            driver = webdriver.Chrome(options=opts)

        output_dir = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), '..', 'static', 'outputs', f'collection_{collection_id}')
        os.makedirs(output_dir, exist_ok=True)

        download_dir = flask_app.config.get('CHROME_DOWNLOAD_DIR', os.path.expanduser('~/Downloads'))

        expected_email = flask_app.config.get('FLOW_GOOGLE_EMAIL', '')
        bot = FlowBot(driver, download_dir=download_dir, expected_email=expected_email)

        # Hook into bot status updates
        original_update = bot._update_status
        def status_hook(status, message=''):
            original_update(status, message)
            job['message'] = message
            if 'navigat' in status:
                job['status'] = 'navigating'
                job['progress'] = 10
            elif 'settings' in status:
                job['status'] = 'settings'
                job['progress'] = 20
            elif 'entering' in status:
                job['status'] = 'entering_prompt'
                job['progress'] = 30
            elif 'generating' in status:
                job['status'] = 'generating'
                if '/4' in message:
                    try:
                        done = int(message.split('/')[0])
                        job['progress'] = 40 + (done * 10)
                    except Exception:
                        job['progress'] = 45
            elif 'download' in status:
                job['status'] = 'downloading'
                job['progress'] = 80
            elif 'complete' in status:
                job['progress'] = 95
        bot._update_status = status_hook

        # Run the bot
        result = bot.generate_banners(
            prompt=prompt,
            aspect_ratio=aspect_ratio,
            count=count,
            image_path=image_path,
        )

        # Move downloaded files to collection output dir and save to DB
        with flask_app.app_context():
            saved = []
            downloaded = result.get('downloaded_files', [])
            if not isinstance(downloaded, list):
                downloaded = []
            for filepath in downloaded:
                if os.path.exists(filepath):
                    filename = os.path.basename(filepath)
                    dest = os.path.join(output_dir, filename)
                    shutil.move(filepath, dest)
                    if not os.path.exists(dest):
                        continue
                    file_size = os.path.getsize(dest)

                    gen = Generation(
                        user_id=user_id,
                        collection_id=collection_id,
                        input_type='text',
                        output_type='image',
                        output_path=f"outputs/collection_{collection_id}/{filename}",
                        pomelli_feature='flow_banner',
                        status='completed',
                        file_size=file_size,
                        completed_at=datetime.now(),
                    )
                    db.session.add(gen)
                    saved.append({
                        'filename': filename,
                        'path': f"/static/outputs/collection_{collection_id}/{filename}",
                        'size': file_size,
                    })

            db.session.commit()

            job['status'] = 'complete'
            job['message'] = f'{len(saved)} banners generated in 2K!'
            job['progress'] = 100
            job['images'] = saved
            job['errors'] = result.get('errors', [])

    except Exception as e:
        job['status'] = 'error'
        job['message'] = str(e)[:200]
        job['progress'] = 0
        job['errors'] = [str(e)]
    finally:
        # Quit this ChromeDriver session (not Chrome itself — it stays alive on port 9222)
        if driver is not None:
            try:
                driver.quit()
                print("[FlowBot] ChromeDriver session closed — Chrome stays alive for next job")
            except Exception:
                pass


@banners_bp.route('/flow-accounts')
@login_required
def flow_accounts():
    """List saved accounts for Flow."""
    import json
    accounts_file = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'saved_accounts.json')
    accounts = []
    if os.path.exists(accounts_file):
        try:
            with open(accounts_file, 'r') as f:
                accounts = json.load(f)
        except Exception:
            pass
    active = current_app.config.get('FLOW_GOOGLE_EMAIL', '')
    return jsonify({
        'accounts': [{'email': a['email'], 'active': a['email'] == active} for a in accounts],
        'active': active,
    })


@banners_bp.route('/flow-switch-account', methods=['POST'])
@login_required
def flow_switch_account():
    """Switch the active Flow account."""
    import json
    data = request.get_json() or {}
    email = data.get('email', '').strip()
    password = data.get('password', '').strip()

    if not email:
        return jsonify({'error': 'Email is required'}), 400

    accounts_file = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'saved_accounts.json')
    accounts = []
    if os.path.exists(accounts_file):
        try:
            with open(accounts_file, 'r') as f:
                accounts = json.load(f)
        except Exception:
            pass

    match = next((a for a in accounts if a['email'] == email), None)

    if match:
        current_app.config['FLOW_GOOGLE_EMAIL'] = match['email']
        current_app.config['FLOW_GOOGLE_PASSWORD'] = match['password']
        _save_flow_active(match['email'])
        return jsonify({'success': True, 'email': match['email']})
    elif password:
        accounts.append({'email': email, 'password': password})
        with open(accounts_file, 'w') as f:
            json.dump(accounts, f, indent=2)
        current_app.config['FLOW_GOOGLE_EMAIL'] = email
        current_app.config['FLOW_GOOGLE_PASSWORD'] = password
        _save_flow_active(email)
        return jsonify({'success': True, 'email': email})
    else:
        return jsonify({'error': 'Account not found. Provide password to save new account.'}), 404


@banners_bp.route('/flow-delete-account', methods=['POST'])
@login_required
def flow_delete_account():
    """Remove a saved account from Flow list."""
    import json
    data = request.get_json() or {}
    email = data.get('email', '').strip()
    if not email:
        return jsonify({'error': 'Email is required'}), 400

    accounts_file = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'saved_accounts.json')
    accounts = []
    if os.path.exists(accounts_file):
        try:
            with open(accounts_file, 'r') as f:
                accounts = json.load(f)
        except Exception:
            pass

    accounts = [a for a in accounts if a['email'] != email]
    with open(accounts_file, 'w') as f:
        json.dump(accounts, f, indent=2)

    # If deleted account was the active Flow account, clear it
    if current_app.config.get('FLOW_GOOGLE_EMAIL', '') == email:
        current_app.config['FLOW_GOOGLE_EMAIL'] = ''
        current_app.config['FLOW_GOOGLE_PASSWORD'] = ''
        _save_flow_active('')

    return jsonify({'success': True})


def _save_flow_active(email):
    """Persist active Flow account to disk."""
    import json
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'active_accounts.json')
    data = {}
    if os.path.exists(path):
        try:
            with open(path, 'r') as f:
                data = json.load(f)
        except Exception:
            pass
    data['flow'] = email
    with open(path, 'w') as f:
        json.dump(data, f, indent=2)
