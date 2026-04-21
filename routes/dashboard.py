from flask import Blueprint, render_template
from flask_login import login_required, current_user
from models import db, Prompt, Generation, Collection, Project, JobQueue

dashboard_bp = Blueprint('dashboard', __name__)


@dashboard_bp.route('/dashboard')
@login_required
def index():
    # Stats
    total_prompts = Prompt.query.filter_by(user_id=current_user.id).count()
    total_generations = Generation.query.filter_by(user_id=current_user.id).count()
    total_collections = Collection.query.filter_by(user_id=current_user.id).count()
    total_favorites = Prompt.query.filter_by(user_id=current_user.id, is_favorite=True).count()
    queued_jobs = JobQueue.query.filter_by(user_id=current_user.id, status='queued').count()
    processing_jobs = JobQueue.query.filter_by(user_id=current_user.id, status='processing').count()

    # Recent activity
    recent_generations = Generation.query.filter_by(user_id=current_user.id)\
        .order_by(Generation.created_at.desc()).limit(8).all()
    recent_prompts = Prompt.query.filter_by(user_id=current_user.id)\
        .order_by(Prompt.created_at.desc()).limit(5).all()
    collections = Collection.query.filter_by(user_id=current_user.id)\
        .order_by(Collection.updated_at.desc()).limit(4).all()

    return render_template('dashboard.html',
        stats={
            'prompts': total_prompts,
            'generations': total_generations,
            'collections': total_collections,
            'favorites': total_favorites,
            'queued': queued_jobs,
            'processing': processing_jobs,
        },
        recent_generations=recent_generations,
        recent_prompts=recent_prompts,
        collections=collections,
    )
