import os
import json
import hashlib

PREVIEWS_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'static', 'data', 'prompt_previews.json')


def _ensure_dir():
    os.makedirs(os.path.dirname(PREVIEWS_FILE), exist_ok=True)


def _load():
    _ensure_dir()
    if os.path.exists(PREVIEWS_FILE):
        with open(PREVIEWS_FILE, 'r') as f:
            return json.load(f)
    return {}


def _save(data):
    _ensure_dir()
    with open(PREVIEWS_FILE, 'w') as f:
        json.dump(data, f, indent=2)


def prompt_hash(text):
    return hashlib.md5(text.strip().lower().encode()).hexdigest()[:12]


def get_preview(prompt_text):
    """Get preview image path for a prompt."""
    data = _load()
    h = prompt_hash(prompt_text)
    return data.get(h)


def set_preview(prompt_text, image_path):
    """Set preview image for a prompt."""
    data = _load()
    h = prompt_hash(prompt_text)
    data[h] = image_path
    _save(data)


def get_all_previews():
    """Get all preview mappings."""
    return _load()


def set_preview_if_missing(prompt_text, image_path):
    """Set preview only if one doesn't exist yet."""
    data = _load()
    h = prompt_hash(prompt_text)
    if h not in data:
        data[h] = image_path
        _save(data)
        return True
    return False
