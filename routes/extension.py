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

from flask import Blueprint, request, jsonify, after_this_request
from flask_login import login_required, current_user
import os
import requests  # type: ignore[import-untyped]
import time
from datetime import datetime, timedelta
from threading import Lock

bp = Blueprint('extension', __name__, url_prefix='/api/ext')


@bp.after_request
def add_cors_headers(response):
    """Allow Chrome extension content scripts to call these endpoints."""
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    return response


@bp.route('/<path:path>', methods=['OPTIONS'])
def handle_options(path):
    """Handle CORS preflight requests."""
    response = jsonify({'ok': True})
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    return response

# ── In-memory job state (shared between extension and dashboard) ──
_state = {
    'pending_commands': {},       # profile_id → job (targeted commands)
    'pending_any': None,          # Job for any available profile
    'current_jobs': {},           # profile_id → job info
    'selections': {},             # job_id → user selection
    'job_queue': [],              # Pending jobs
    'profiles': {},               # profile_id → {account, capabilities, last_seen, cooldown_until}
}
_lock = Lock()


@bp.route('/command', methods=['GET'])
def get_command():
    """Extension polls this — returns job targeted at this profile or any available job."""
    profile_id = request.args.get('profile_id', 'unknown')
    with _lock:
        # Update last_seen
        if profile_id in _state['profiles']:
            _state['profiles'][profile_id]['last_seen'] = datetime.now().isoformat()

        # Check for targeted command first
        cmd = _state['pending_commands'].pop(profile_id, None)
        if cmd:
            return jsonify(cmd)

        # Check for any-profile command
        if _state['pending_any']:
            # Check if this profile can handle it and is not in cooldown
            job = _state['pending_any']
            profile = _state['profiles'].get(profile_id, {})
            caps = profile.get('capabilities', [])
            cooldown = profile.get('cooldown_until')

            if cooldown and datetime.fromisoformat(cooldown) > datetime.now():
                return ('', 204)  # This profile is in cooldown

            if job.get('job_type') in caps or not caps:
                _state['pending_any'] = None
                return jsonify(job)

    return ('', 204)


@bp.route('/ack', methods=['POST'])
def ack_command():
    data = request.json
    profile_id = data.get('profile_id', 'unknown')
    with _lock:
        _state['current_jobs'][profile_id] = {
            'job_id': data.get('job_id'),
            'profile_id': profile_id,
            'state': 'running',
            'started_at': datetime.now().isoformat()
        }
    return jsonify({'ok': True})


@bp.route('/status', methods=['GET'])
def get_status():
    with _lock:
        profiles = {}
        for pid, info in _state['profiles'].items():
            cooldown = info.get('cooldown_until')
            in_cooldown = cooldown and datetime.fromisoformat(cooldown) > datetime.now()
            profiles[pid] = {
                'account': info.get('account', 'unknown'),
                'capabilities': info.get('capabilities', []),
                'status': 'cooldown' if in_cooldown else 'active',
                'current_job': _state['current_jobs'].get(pid)
            }
    return jsonify({
        'connected': True,
        'message': f"Server running — {len(profiles)} profile(s) connected",
        'profiles': profiles,
        'queue_size': len(_state['job_queue']) if isinstance(_state.get('job_queue'), list) else 0
    })


@bp.route('/status', methods=['POST'])
def update_status():
    data = request.json
    job_id = data.get('job_id')
    with _lock:
        # Find which profile is running this job
        for pid, job in _state['current_jobs'].items():
            if job.get('job_id') == job_id:
                job['state'] = data.get('state', 'running')
                job['message'] = data.get('message', '')
                job['type'] = data.get('type', job.get('type', ''))
                if 'ideas' in data: job['ideas'] = data['ideas']
                if 'images' in data: job['images'] = data['images']

                # Handle cooldown (rate limited)
                msg_lower = data.get('message', '').lower()
                if 'unusual activity' in msg_lower or 'rate limit' in msg_lower:
                    if pid in _state['profiles']:
                        # Cooldown this profile for 2 hours
                        cooldown = datetime.now() + timedelta(hours=2)
                        _state['profiles'][pid]['cooldown_until'] = cooldown.isoformat()

                if data.get('state') in ('complete', 'error'):
                    job['completed_at'] = datetime.now().isoformat()
                break
    return jsonify({'ok': True})


@bp.route('/register', methods=['POST'])
def register_profile():
    data = request.json
    profile_id = data.get('profile_id', 'unknown')
    with _lock:
        _state['profiles'][profile_id] = {
            'account': data.get('account', 'unknown'),
            'capabilities': data.get('capabilities', []),
            'profile_dir': data.get('profile_dir', ''),
            'last_seen': datetime.now().isoformat(),
            'cooldown_until': None
        }
    print(f"[Extension] Profile registered: {profile_id} — {data.get('account')}")
    return jsonify({'ok': True, 'profile_id': profile_id})


@bp.route('/queue', methods=['GET'])
def get_queue():
    """Popup gets list of pending/active jobs."""
    with _lock:
        jq = _state.get('job_queue', [])
        cj = _state.get('current_jobs', {})
        jobs = list(jq) if isinstance(jq, list) else []
        current_jobs = list(cj.values()) if isinstance(cj, dict) else []

    result = []
    for current in current_jobs:
        if isinstance(current, dict):
            result.append({
                'id': current.get('job_id'),
                'type': current.get('type', 'unknown'),
                'status': 'running',
                'name': current.get('message', '')
            })
    for j in jobs:
        if isinstance(j, dict):
            result.append({
                'id': j.get('job_id'),
                'type': j.get('job_type', 'unknown'),
                'status': 'queued',
                'name': j.get('prompt_text', '')[:30]
            })
    return jsonify(result)


@bp.route('/submit', methods=['POST'])
def submit_job():
    data = request.json
    job = {
        'job_id': data.get('job_id', f"ext_{int(time.time())}"),
        'job_type': data.get('job_type', 'campaign'),
        'prompt_text': data.get('prompt_text', ''),
        'image_url': data.get('image_url'),
        'image_filename': data.get('image_filename', 'product.jpg'),
        'templates': data.get('templates', []),
        'aspect_ratio': data.get('aspect_ratio', 'story'),
        'photoshoot_mode': data.get('photoshoot_mode', 'product'),
        'count': data.get('count', 4),
        'reuse_project': data.get('reuse_project', False),
        'target_account': data.get('target_account'),  # Optional: route to specific account
    }

    with _lock:
        target = data.get('target_account')

        if target:
            # Route to specific profile by account name
            for pid, info in _state['profiles'].items():
                if target.lower() in info.get('account', '').lower():
                    _state['pending_commands'][pid] = job
                    return jsonify({'job_id': job['job_id'], 'queued': True, 'routed_to': pid})

        # Find best available profile (not in cooldown, has capability)
        best_profile = None
        for pid, info in _state['profiles'].items():
            cooldown = info.get('cooldown_until')
            if cooldown and datetime.fromisoformat(cooldown) > datetime.now():
                continue
            caps = info.get('capabilities', [])
            if job['job_type'] in caps or not caps:
                # Prefer profile not currently busy
                current = _state['current_jobs'].get(pid)
                if not current or (isinstance(current, dict) and current.get('state') in ('complete', 'error', None)):
                    best_profile = pid
                    break

        if best_profile:
            _state['pending_commands'][best_profile] = job
            return jsonify({'job_id': job['job_id'], 'queued': True, 'routed_to': best_profile})
        else:
            # No profile available — put in general queue
            _state['pending_any'] = job
            return jsonify({'job_id': job['job_id'], 'queued': True, 'routed_to': 'any'})


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
        cj = _state.get('current_jobs', {})
        if isinstance(cj, dict):
            for pid, job in cj.items():
                if isinstance(job, dict) and job.get('job_id') == job_id:
                    return jsonify(job)
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
    with _lock:
        _state['pending_commands'] = {}
        _state['pending_any'] = None
        _state['current_jobs'] = {}
        _state['job_queue'] = []
        _state['selections'] = {}
    return jsonify({'ok': True})


@bp.route('/next', methods=['POST'])
def advance_queue():
    with _lock:
        # Clear completed jobs from current_jobs
        cj = _state.get('current_jobs', {})
        if isinstance(cj, dict):
            for pid in list(cj.keys()):
                job = cj[pid]
                if isinstance(job, dict) and job.get('state') in ('complete', 'error'):
                    del cj[pid]

        # Move next queued job
        jq = _state.get('job_queue', [])
        if isinstance(jq, list) and jq:
            next_job = jq.pop(0)
            _state['pending_any'] = next_job
    return jsonify({'ok': True})
