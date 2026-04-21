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
    data = request.get_json() or {}
    prompt = data.get('prompt', '').strip()
    aspect_ratio = data.get('aspect_ratio', '1:1')
    count = min(int(data.get('count', 4)), 4)
    collection_id = data.get('collection_id', '').strip()
    model = data.get('model', 'nano_banana_2')

    if not prompt:
        return jsonify({'error': 'Enter a banner prompt'}), 400

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
        daemon=True,
    )
    thread.start()

    return jsonify({'success': True, 'job_id': job_id, 'collection_id': collection_id})


@banners_bp.route('/status/<job_id>')
@login_required
def status(job_id):
    job = _banner_jobs.get(job_id, {})
    return jsonify(job)


def _run_flow_bot(job_id, prompt, aspect_ratio, count, collection_id, user_id, flask_app):
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service
    from modules.flow_bot import FlowBot

    job = _banner_jobs[job_id]

    try:
        # Connect to Chrome on port 9222
        job['status'] = 'connecting'
        job['message'] = 'Connecting to Chrome...'
        job['progress'] = 5

        opts = Options()
        opts.add_experimental_option('debuggerAddress', '127.0.0.1:9222')

        local_driver = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'chromedriver.exe')
        if os.path.exists(local_driver):
            service = Service(local_driver)
            driver = webdriver.Chrome(service=service, options=opts)
        else:
            driver = webdriver.Chrome(options=opts)

        output_dir = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), '..', 'static', 'outputs', f'collection_{collection_id}')
        os.makedirs(output_dir, exist_ok=True)

        download_dir = flask_app.config.get('CHROME_DOWNLOAD_DIR', os.path.join(
            os.path.dirname(os.path.abspath(__file__)), '..', 'static', 'downloads'))

        bot = FlowBot(driver, download_dir=download_dir)

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
        )

        # Move downloaded files to collection output dir and save to DB
        with flask_app.app_context():
            saved = []
            for filepath in result.get('downloaded_files', []):
                if os.path.exists(filepath):
                    filename = os.path.basename(filepath)
                    dest = os.path.join(output_dir, filename)
                    shutil.move(filepath, dest)
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
