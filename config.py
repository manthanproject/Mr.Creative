"""Mr.Creative — Config (reads from env vars)"""
import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret-key')
    _db_url = os.environ.get('DATABASE_URL', f'sqlite:///{os.path.join(BASE_DIR, "database.db")}')
    if _db_url.startswith('postgres://'):
        _db_url = _db_url.replace('postgres://', 'postgresql://', 1)
    SQLALCHEMY_DATABASE_URI = _db_url
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    UPLOAD_FOLDER = os.path.join(BASE_DIR, 'static', 'uploads')
    OUTPUT_FOLDER = os.path.join(BASE_DIR, 'static', 'outputs')
    MAX_CONTENT_LENGTH = 50 * 1024 * 1024
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp', 'bmp'}

    GROQ_API_KEY = os.environ.get('GROQ_API_KEY', '')
    CEREBRAS_API_KEY = os.environ.get('CEREBRAS_API_KEY', '')
    GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY', '')
    HF_API_KEY = os.environ.get('HF_API_KEY', '')
    PINTEREST_ACCESS_TOKEN = os.environ.get('PINTEREST_ACCESS_TOKEN', '')

    POMELLI_URL = 'https://labs.google.com/pomelli'
    GOOGLE_EMAIL = os.environ.get('GOOGLE_EMAIL', '')
    GOOGLE_PASSWORD = os.environ.get('GOOGLE_PASSWORD', '')

    DOWNLOAD_DIR = os.path.join(BASE_DIR, 'static', 'downloads')
    CHROME_DOWNLOAD_DIR = os.environ.get('CHROME_DOWNLOAD_DIR', '/tmp/downloads')
    HEADLESS_MODE = True
    SCHEDULER_ENABLED = os.environ.get('SCHEDULER_ENABLED', 'true').lower() == 'true'
