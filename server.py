from flask import Flask, redirect, url_for, request
from flask_login import LoginManager
from flask_cors import CORS  # type: ignore[import-untyped]
from config import Config
from models import db, User
import os


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
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
    def add_static_cors(response):
        """Allow extension to fetch uploaded images."""
        if '/static/uploads/' in request.path:
            response.headers['Access-Control-Allow-Origin'] = '*'
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

    # Load persisted active accounts (survives restarts)
    active_accounts_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'active_accounts.json')
    if os.path.exists(active_accounts_path):
        try:
            import json
            with open(active_accounts_path, 'r') as f:
                active = json.load(f)
            saved_accounts_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'saved_accounts.json')
            saved = []
            if os.path.exists(saved_accounts_path):
                with open(saved_accounts_path, 'r') as f:
                    saved = json.load(f)
            # Restore Pomelli active account
            if active.get('pomelli'):
                match = next((a for a in saved if a['email'] == active['pomelli']), None)
                if match:
                    app.config['GOOGLE_EMAIL'] = match['email']
                    app.config['GOOGLE_PASSWORD'] = match['password']
            # Restore Flow active account
            if active.get('flow'):
                match = next((a for a in saved if a['email'] == active['flow']), None)
                if match:
                    app.config['FLOW_GOOGLE_EMAIL'] = match['email']
                    app.config['FLOW_GOOGLE_PASSWORD'] = match['password']
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

    # Root route
    @app.route('/')
    def index():
        return redirect(url_for('auth.login'))

    # Create tables
    with app.app_context():
        db.create_all()

        # Auto-migrate: add new columns to existing tables
        import sqlite3
        db_path = app.config['SQLALCHEMY_DATABASE_URI'].replace('sqlite:///', '')
        conn = sqlite3.connect(db_path)
        migrations = [
            ("agent_jobs", "aspect_ratio", "VARCHAR(10) DEFAULT 'mixed'"),
            ("agent_jobs", "reference_image", "VARCHAR(255)"),
            ("agent_jobs", "control_action", "VARCHAR(10) DEFAULT ''"),
            ("agent_jobs", "llm_provider", "VARCHAR(20) DEFAULT ''"),
            ("agent_jobs", "post_options", "TEXT DEFAULT '{}'"),
        ]
        for table, column, col_type in migrations:
            try:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")
                print(f"[Migration] Added {table}.{column}")
            except sqlite3.OperationalError:
                pass  # Column already exists
        conn.commit()
        conn.close()

    # Clean up stale jobs from previous crashes/restarts
    from routes.generate import cleanup_stale_jobs
    cleanup_stale_jobs(app)

    # Start auto-scheduler (checks for due jobs every 60s)
    # Only start in the main process, not in Flask's reloader child process
    if os.environ.get('WERKZEUG_RUN_MAIN') == 'true' or not app.debug:
        from modules.auto_scheduler import init_scheduler
        init_scheduler(app)

    return app


# Vercel needs a top-level app instance

app = create_app()

if __name__ == '__main__':
    import os
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=True, host='0.0.0.0', port=port)
