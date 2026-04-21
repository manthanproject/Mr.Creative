from flask import Blueprint, render_template, request, jsonify, redirect, url_for, flash
from flask_login import login_required, current_user
from models import db, Project

projects_bp = Blueprint('projects', __name__)


@projects_bp.route('/')
@login_required
def index():
    projects = Project.query.filter_by(user_id=current_user.id)\
        .order_by(Project.updated_at.desc()).all()
    return render_template('projects.html', projects=projects)


@projects_bp.route('/create', methods=['POST'])
@login_required
def create():
    name = request.form.get('name', '').strip()
    description = request.form.get('description', '').strip()
    website_url = request.form.get('website_url', '').strip()

    if not name:
        flash('Project name is required.', 'error')
        return redirect(url_for('projects.index'))

    project = Project(
        user_id=current_user.id,
        name=name,
        description=description,
        website_url=website_url
    )
    db.session.add(project)
    db.session.commit()

    flash('Project created!', 'success')
    return redirect(url_for('projects.index'))


@projects_bp.route('/<project_id>')
@login_required
def view(project_id):
    project = Project.query.filter_by(id=project_id, user_id=current_user.id).first_or_404()
    return render_template('project_detail.html', project=project)


@projects_bp.route('/<project_id>/delete', methods=['POST'])
@login_required
def delete(project_id):
    project = Project.query.filter_by(id=project_id, user_id=current_user.id).first_or_404()
    db.session.delete(project)
    db.session.commit()
    return jsonify({'success': True})
