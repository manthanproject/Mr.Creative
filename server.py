from dotenv import load_dotenv
load_dotenv()
from flask import Flask, redirect, url_for, request
from flask_login import LoginManager
from flask_cors import CORS  # type: ignore[import-untyped]
from config import Config
from models import db, User
import os


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    # Serverless: NullPool = no connection pooling overhead, fresh connection per request
    if os.environ.get('VERCEL'):
        from sqlalchemy.pool import NullPool
        app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
            'poolclass': NullPool,
            'connect_args': {'connect_timeout': 5},
        }
    # Serverless: NullPool = no connection pooling overhead, fresh connection per request
    if os.environ.get('VERCEL'):
        from sqlalchemy.pool import NullPool
        app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
            'poolclass': NullPool,
            'connect_args': {'connect_timeout': 5},
        }
    app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50MB for base64 image uploads

    CORS(app, resources={r"/api/ext/*": {"origins": "*"}})

    @app.route('/download-extension')
    def download_extension():
        import zipfile, io
        from flask import send_file
        ext_dir = os.path.join(app.root_path, 'extension')
        if not os.path.exists(ext_dir):
            return 'Extension folder not found', 404
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
            for root, dirs, files in os.walk(ext_dir):
                # Skip node_modules, .git, __pycache__
                dirs[:] = [d for d in dirs if d not in ('node_modules', '.git', '__pycache__')]
                for f in files:
                    fpath = os.path.join(root, f)
                    arcname = os.path.join('mr-creative-extension', os.path.relpath(fpath, ext_dir))
                    zf.write(fpath, arcname)
        buf.seek(0)
        return send_file(buf, mimetype='application/zip', as_attachment=True,
                         download_name='mr-creative-extension.zip')

    @app.after_request
    def add_headers(response):
        if '/static/uploads/' in request.path:
            response.headers['Access-Control-Allow-Origin'] = '*'
        if '/static/' in request.path:
            # Static assets: cache with revalidation (not immutable — we update in place)
            response.headers['Cache-Control'] = 'public, max-age=3600, must-revalidate'
        elif response.content_type and 'text/html' in response.content_type:
            # Dynamic HTML: never cache — prevents double-render from stale-while-revalidate
            response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
            response.headers['Pragma'] = 'no-cache'
        return response

    # Initialize extensions
    db.init_app(app)

    # Login manager
    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    login_manager.login_message_category = 'info'

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, user_id)

    @login_manager.unauthorized_handler
    def unauthorized():
        return redirect(url_for('auth.login'))

    # Ensure directories exist (skip on read-only filesystems like Vercel)
    for _dir in [app.config.get('UPLOAD_FOLDER', ''), app.config.get('OUTPUT_FOLDER', ''), app.config.get('DOWNLOAD_DIR', '')]:
        if _dir:
            try:
                os.makedirs(_dir, exist_ok=True)
            except OSError:
                pass

    # Load active accounts from DB
    try:
        from models import SavedAccount
        with app.app_context():
            for acct in SavedAccount.query.filter_by(is_active=True).all():
                if acct.service == 'flow':
                    app.config['FLOW_GOOGLE_EMAIL'] = acct.email
                    app.config['FLOW_GOOGLE_PASSWORD'] = acct.password_enc
                elif acct.service == 'pomelli':
                    app.config['GOOGLE_EMAIL'] = acct.email
                    app.config['GOOGLE_PASSWORD'] = acct.password_enc
    except Exception:
        pass

    # Register blueprints
    from routes.auth import auth_bp
    from routes.dashboard import dashboard_bp
    from routes.prompts import prompts_bp
    from routes.collections import collections_bp
    from routes.projects import projects_bp
    from routes.api import api_bp
    from routes.scheduler import scheduler_bp
    from routes.settings import settings_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(prompts_bp, url_prefix='/prompts')
    app.register_blueprint(collections_bp, url_prefix='/collections')
    app.register_blueprint(projects_bp, url_prefix='/projects')
    app.register_blueprint(api_bp, url_prefix='/api')
    app.register_blueprint(scheduler_bp, url_prefix='/scheduler')
    app.register_blueprint(settings_bp, url_prefix='/settings')

    from routes.generate import generate_bp
    app.register_blueprint(generate_bp, url_prefix='/generate')

    from routes.banners import banners_bp
    app.register_blueprint(banners_bp, url_prefix='/banners')

    from routes.social import social_bp
    app.register_blueprint(social_bp, url_prefix='/social')

    from routes.agent import agent_bp
    app.register_blueprint(agent_bp, url_prefix='/agent')

    from routes.extension import bp as extension_bp
    app.register_blueprint(extension_bp)

    from routes.night_ops import night_ops_bp
    app.register_blueprint(night_ops_bp)

    # Root route
    @app.route('/')
    def index():
        return redirect(url_for('auth.login'))

    # Create tables
    with app.app_context():
        try:
            db.create_all()
        except Exception as e:
            print(f"[DB] create_all failed: {e}")

        # Auto-migrate (SQLite only)
        if 'sqlite' in app.config.get('SQLALCHEMY_DATABASE_URI', ''):
            try:
                import sqlite3
                db_path = app.config['SQLALCHEMY_DATABASE_URI'].replace('sqlite:///', '')
                conn = sqlite3.connect(db_path)
                for table, column, col_type in [
                    ("agent_jobs", "aspect_ratio", "VARCHAR(10) DEFAULT 'mixed'"),
                    ("agent_jobs", "reference_image", "VARCHAR(255)"),
                    ("agent_jobs", "control_action", "VARCHAR(10) DEFAULT ''"),
                    ("agent_jobs", "llm_provider", "VARCHAR(20) DEFAULT ''"),
                    ("agent_jobs", "post_options", "TEXT DEFAULT '{}'"),
                ]:
                    try:
                        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")
                    except sqlite3.OperationalError:
                        pass
                conn.commit()
                conn.close()
            except Exception:
                pass

    if not os.environ.get('VERCEL'):
        try:
            from routes.generate import cleanup_stale_jobs
            cleanup_stale_jobs(app)
        except Exception:
            pass
        if os.environ.get('WERKZEUG_RUN_MAIN') == 'true' or not app.debug:
            try:
                from modules.auto_scheduler import init_scheduler
                init_scheduler(app)
            except Exception:
                pass
            try:
                from modules.night_orchestrator.orchestrator import init_night_scheduler
                init_night_scheduler(app)
            except Exception:
                pass

    return app
