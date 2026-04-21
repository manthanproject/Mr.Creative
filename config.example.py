"""
Mr.Creative — config template
Copy this to config.py and fill in real values. config.py is gitignored.
"""

import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'change-me-to-a-random-string')
    SQLALCHEMY_DATABASE_URI = f'sqlite:///{os.path.join(BASE_DIR, "database.db")}'
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Upload settings
    UPLOAD_FOLDER = os.path.join(BASE_DIR, 'static', 'uploads')
    OUTPUT_FOLDER = os.path.join(BASE_DIR, 'static', 'outputs')
    MAX_CONTENT_LENGTH = 50 * 1024 * 1024  # 50MB max upload
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp', 'bmp'}

    # LLM / image API keys
    GROQ_API_KEY = os.environ.get('GROQ_API_KEY', 'gsk_...')
    GEMINI_API_KEY = 'AIza...'
    HF_API_KEY = 'hf_...'

    # Pomelli account
    POMELLI_URL = 'https://labs.google.com/pomelli'
    GOOGLE_EMAIL = os.environ.get('GOOGLE_EMAIL', 'your-pomelli-account@gmail.com')
    GOOGLE_PASSWORD = os.environ.get('GOOGLE_PASSWORD', 'your-password')

    # Flow account (Google Pro subscription)
    FLOW_GOOGLE_EMAIL = 'your-flow-account@gmail.com'
    FLOW_GOOGLE_PASSWORD = 'your-password'

    # Selenium / Chrome
    CHROME_DRIVER_PATH = os.environ.get('CHROME_DRIVER_PATH', '')
    DOWNLOAD_DIR = os.path.join(BASE_DIR, 'static', 'downloads')
    CHROME_DOWNLOAD_DIR = r'C:\Users\YourName\Downloads'
    HEADLESS_MODE = False
    CHROME_PROFILE_DIR = os.path.join(BASE_DIR, 'chrome_session')

    # Scheduler
    SCHEDULER_ENABLED = True
