"""
Extension API — Communication bridge between Mr.Creative Flask server and Chrome extension.

Endpoints:
  GET  /api/ext/command       - Extension polls for next pending job
  POST /api/ext/ack           - Extension acknowledges job receipt
  POST /api/ext/status        - Extension reports job progress
  GET  /api/ext/status        - Popup checks server status
  GET  /api/ext/queue         - Popup gets job queue
  GET  /api/ext/selection/<id> - Extension polls for user selection (idea/animate)
  POST /api/ext/selection/<id> - Dashboard sends user selection
  POST /api/ext/download      - Extension sends image URL for server-side download
  POST /api/ext/stop          - Stop current job
"""

from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user
import json
import os
import requests
import time
from datetime import datetime
from threading import Lock

bp = Blueprint('extension', __name__, url_prefix='/api/ext')

# ── In-memory job state (shared between extension and dashboard) ──
_state = {
    'pending_command': None,      # Next job for extension to pick up
    'current_job': None,          # Currently running job info
    'selections': {},             # User selections keyed by job_id
    'job_queue': [],              # Pending jobs
}
_lock = Lock()


@bp.route('/command', methods=['GET'])
def get_command():
    """Extension polls this every 3s to check for pending work."""
    with _lock:
        cmd = _state['pending_command']
        if cmd:
            return jsonify(cmd)
    return jsonify(None), 204


@bp.route('/ack', methods=['POST'])
def ack_command():
    """Extension confirms it received and started the job."""
    data = request.json
    with _lock:
        _state['pending_command'] = None
        _state['current_job'] = {
            'job_id': data.get('job_id'),
            'state': 'running',
            'started_at': datetime.now().isoformat()
        }
    return jsonify({'ok': True})


@bp.route('/status', methods=['GET'])
def get_status():
    """Popup checks server connection and current job state."""
    with _lock:
        current = _state.get('current_job')
    return jsonify({
        'connected': True,
        'message': 'Server running',
        'current_job': current,
        'queue_size': len(_state.get('job_queue', []))
    })


@bp.route('/status', methods=['POST'])
def update_status():
    """Extension reports job progress."""
    data = request.json
    with _lock:
        if _state['current_job'] and _state['current_job']['job_id'] == data.get('job_id'):
            _state['current_job']['state'] = data.get('state', 'running')
            _state['current_job']['message'] = data.get('message', '')

            # If extension sent idea cards or creative images, store them
            if 'ideas' in data:
                _state['current_job']['ideas'] = data['ideas']
            if 'images' in data:
                _state['current_job']['images'] = data['images']

            # Job complete or error — move off current
            if data.get('state') in ('complete', 'error'):
                _state['current_job']['completed_at'] = datetime.now().isoformat()

    return jsonify({'ok': True})


@bp.route('/queue', methods=['GET'])
def get_queue():
    """Popup gets list of pending/active jobs."""
    with _lock:
        jobs = _state.get('job_queue', [])
        current = _state.get('current_job')

    result = []
    if current:
        result.append({
            'id': current.get('job_id'),
            'type': current.get('type', 'unknown'),
            'status': 'running',
            'name': current.get('message', '')
        })
    for j in jobs:
        result.append({
            'id': j.get('job_id'),
            'type': j.get('job_type', 'unknown'),
            'status': 'queued',
            'name': j.get('prompt_text', '')[:30]
        })
    return jsonify(result)


@bp.route('/submit', methods=['POST'])
def submit_job():
    """Dashboard submits a new job for the extension to pick up."""
    data = request.json
    job = {
        'job_id': data.get('job_id', f"ext_{int(time.time())}"),
        'job_type': data.get('job_type', 'campaign'),  # campaign, photoshoot, flow
        'prompt_text': data.get('prompt_text', ''),
        'image_url': data.get('image_url'),             # URL to fetch image from
        'image_filename': data.get('image_filename', 'product.jpg'),
        'templates': data.get('templates', []),
        'aspect_ratio': data.get('aspect_ratio', 'story'),
        'photoshoot_mode': data.get('photoshoot_mode', 'product'),
        'count': data.get('count', 4),
        'reuse_project': data.get('reuse_project', False),
    }

    with _lock:
        if _state['pending_command'] is None and _state['current_job'] is None:
            # No active job — send immediately
            _state['pending_command'] = job
        else:
            # Queue it
            _state['job_queue'].append(job)

    return jsonify({'job_id': job['job_id'], 'queued': True})


@bp.route('/upload-image', methods=['POST'])
def upload_image():
    """Dashboard uploads product image, returns URL for extension to fetch."""
    file = request.files.get('image')
    if not file:
        return jsonify({'error': 'No file'}), 400
    filename = f"ext_{int(time.time())}_{file.filename}"
    upload_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'static', 'uploads')
    os.makedirs(upload_dir, exist_ok=True)
    filepath = os.path.join(upload_dir, filename)
    file.save(filepath)
    url = f"http://localhost:5000/static/uploads/{filename}"
    return jsonify({'url': url, 'filename': filename})


@bp.route('/job-status/<job_id>', methods=['GET'])
def get_job_status(job_id):
    """Dashboard polls this for job progress."""
    with _lock:
        current = _state.get('current_job')
        if isinstance(current, dict) and current.get('job_id') == job_id:
            return jsonify(current)
    return jsonify({'state': 'unknown'}), 404


@bp.route('/selection/<job_id>', methods=['GET'])
def get_selection(job_id):
    """Extension polls for user selection (idea card or animate cards)."""
    with _lock:
        sel = _state['selections'].get(job_id)
    if sel:
        return jsonify(sel)
    return jsonify(None), 204


@bp.route('/selection/<job_id>', methods=['POST'])
def set_selection(job_id):
    """Dashboard sends user's selection for a waiting job."""
    data = request.json
    with _lock:
        _state['selections'][job_id] = {
            'selected': True,
            'idea_index': data.get('idea_index'),
            'animate_indices': data.get('animate_indices', []),
        }
    return jsonify({'ok': True})


@bp.route('/download', methods=['POST'])
def download_image():
    """Extension sends image URL — server downloads and saves to collection."""
    data = request.json
    image_url = data.get('url')
    index = data.get('index', 0)
    job_id = data.get('job_id', '')

    if not image_url:
        return jsonify({'error': 'No URL'}), 400

    try:
        # Download image
        resp = requests.get(image_url, timeout=30)
        if resp.status_code != 200:
            return jsonify({'error': f'HTTP {resp.status_code}'}), 400

        # Save to downloads folder
        downloads_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'static', 'downloads')
        os.makedirs(downloads_dir, exist_ok=True)

        ext = 'jpg'
        if 'png' in resp.headers.get('content-type', ''):
            ext = 'png'
        elif 'webp' in resp.headers.get('content-type', ''):
            ext = 'webp'

        filename = f"{job_id}_{index}.{ext}" if job_id else f"ext_{int(time.time())}_{index}.{ext}"
        filepath = os.path.join(downloads_dir, filename)

        with open(filepath, 'wb') as f:
            f.write(resp.content)

        return jsonify({
            'ok': True,
            'path': filepath,
            'size': len(resp.content),
            'filename': filename
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@bp.route('/stop', methods=['POST'])
def stop_job():
    """Stop current job and clear queue."""
    with _lock:
        _state['pending_command'] = None
        _state['current_job'] = None
        _state['job_queue'] = []
        _state['selections'] = {}
    return jsonify({'ok': True})


@bp.route('/next', methods=['POST'])
def advance_queue():
    """Move next queued job to pending (called after job completes)."""
    with _lock:
        _state['current_job'] = None
        if _state['job_queue']:
            _state['pending_command'] = _state['job_queue'].pop(0)
        else:
            _state['pending_command'] = None
    return jsonify({'ok': True})
