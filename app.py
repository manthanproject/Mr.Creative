from flask import Flask, redirect, url_for
from flask_login import LoginManager
from config import Config
from models import db, User
import os


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

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

    # Ensure directories exist
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    os.makedirs(app.config['OUTPUT_FOLDER'], exist_ok=True)
    os.makedirs(app.config.get('DOWNLOAD_DIR', 'static/downloads'), exist_ok=True)

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

    # Root route
    @app.route('/')
    def index():
        return redirect(url_for('auth.login'))

    # Create tables
    with app.app_context():
        db.create_all()

    # Clean up stale jobs from previous crashes/restarts
    from routes.generate import cleanup_stale_jobs
    cleanup_stale_jobs(app)

    # Start auto-scheduler (checks for due jobs every 60s)
    # Only start in the main process, not in Flask's reloader child process
    if os.environ.get('WERKZEUG_RUN_MAIN') == 'true' or not app.debug:
        from modules.auto_scheduler import init_scheduler
        init_scheduler(app)

    return app


if __name__ == '__main__':
    app = create_app()
    app.run(debug=True, port=5000)