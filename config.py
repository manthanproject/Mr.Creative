import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'mr-creative-secret-key-change-in-production')
    SQLALCHEMY_DATABASE_URI = f'sqlite:///{os.path.join(BASE_DIR, "database.db")}'
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Upload settings
    UPLOAD_FOLDER = os.path.join(BASE_DIR, 'static', 'uploads')
    OUTPUT_FOLDER = os.path.join(BASE_DIR, 'static', 'outputs')
    MAX_CONTENT_LENGTH = 50 * 1024 * 1024  # 50MB max upload
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp', 'bmp'}

    # Gemini API (add your key here or set env variable)
    GROQ_API_KEY = os.environ.get('GROQ_API_KEY', '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')
    GEMINI_API_KEY = 'AIzaSyDjxd3esxIbfHsH-acqrvedXBaFsAqnS50'
    HF_API_KEY = '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'

    # Pomelli settings
    POMELLI_URL = 'https://labs.google.com/pomelli'
    GOOGLE_EMAIL = os.environ.get('GOOGLE_EMAIL', 'dropsyshops45@gmail.com')
    GOOGLE_PASSWORD = os.environ.get('GOOGLE_PASSWORD', 'Matrix@404')

    # Selenium settings
    CHROME_DRIVER_PATH = os.environ.get('CHROME_DRIVER_PATH', '')
    DOWNLOAD_DIR = os.path.join(BASE_DIR, 'static', 'downloads')
    HEADLESS_MODE = False  # Set True for production
    CHROME_PROFILE_DIR = os.path.join(BASE_DIR, 'chrome_session')

    # Scheduler
    SCHEDULER_ENABLED = True
