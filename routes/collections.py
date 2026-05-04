from flask import Blueprint, render_template, request, jsonify, redirect, url_for, flash, current_app, send_file
from flask_login import login_required, current_user
from models import db, Collection, Generation
from modules.collection_mgr import (
    save_upload_to_collection, export_collection_as_zip,
    get_collection_files, allowed_file
)
from datetime import datetime, UTC
import os

collections_bp = Blueprint('collections', __name__)


@collections_bp.route('/')
@login_required
def index():
    collections = Collection.query.filter_by(user_id=current_user.id)\
        .order_by(Collection.updated_at.desc()).all()
    return render_template('collections.html', collections=collections)


@collections_bp.route('/create', methods=['POST'])
@login_required
def create():
    name = request.form.get('name', '').strip()
    description = request.form.get('description', '').strip()

    if not name:
        flash('Collection name is required.', 'error')
        return redirect(url_for('collections.index'))

    collection = Collection(
        user_id=current_user.id,
        name=name,
        description=description
    )
    db.session.add(collection)
    db.session.commit()

    flash('Collection created!', 'success')
    return redirect(url_for('collections.view', collection_id=collection.id))


@collections_bp.route('/<collection_id>')
@login_required
def view(collection_id):
    collection = Collection.query.filter_by(id=collection_id, user_id=current_user.id).first_or_404()
    generations = Generation.query.filter_by(collection_id=collection_id)\
        .order_by(Generation.created_at.desc()).all()

    # Also get files from the collection folder
    output_folder = current_app.config.get('OUTPUT_FOLDER', 'static/outputs')
    folder_files = get_collection_files(collection_id, output_folder)

    return render_template('collection_detail.html',
        collection=collection,
        generations=generations,
        folder_files=folder_files,
    )


@collections_bp.route('/<collection_id>/upload', methods=['POST'])
@login_required
def upload(collection_id):
    """Upload files directly to a collection."""
    collection = Collection.query.filter_by(id=collection_id, user_id=current_user.id).first_or_404()

    if 'files' not in request.files:
        return jsonify({'error': 'No files uploaded'}), 400

    files = request.files.getlist('files')
    output_folder = current_app.config.get('OUTPUT_FOLDER', 'static/outputs')

    uploaded = []
    for file in files:
        if file and file.filename and allowed_file(file.filename):
            info = save_upload_to_collection(file, collection_id, output_folder, current_user.id)
            if info:
                # Create generation record
                gen = Generation(
                    user_id=current_user.id,
                    collection_id=collection_id,
                    input_type='upload',
                    output_type=info['file_type'],
                    output_path=info['path'],
                    pomelli_feature='manual',
                    status='completed',
                    file_size=info['file_size'],
                    completed_at=datetime.now(UTC),
                )
                db.session.add(gen)
                uploaded.append(info['filename'])

    # Update collection timestamp
    collection.updated_at = datetime.now(UTC)
    db.session.commit()

    if uploaded:
        return jsonify({
            'success': True,
            'uploaded': uploaded,
            'count': len(uploaded),
            'message': f'{len(uploaded)} files uploaded!'
        })
    else:
        return jsonify({'error': 'No valid files to upload'}), 400


@collections_bp.route('/<collection_id>/export-zip')
@login_required
def export_zip(collection_id):
    """Export collection as ZIP download."""
    collection = Collection.query.filter_by(id=collection_id, user_id=current_user.id).first_or_404()
    generations = Generation.query.filter_by(collection_id=collection_id).all()

    output_folder = current_app.config.get('OUTPUT_FOLDER', 'static/outputs')
    zip_path = export_collection_as_zip(collection_id, output_folder, generations)

    if zip_path:
        full_path = os.path.join('static', zip_path)
        if os.path.exists(full_path):
            return send_file(full_path, as_attachment=True,
                download_name=f"{collection.name}.zip")

    flash('No files to export.', 'error')
    return redirect(url_for('collections.view', collection_id=collection_id))


@collections_bp.route('/<collection_id>/toggle-share', methods=['POST'])
@login_required
def toggle_share(collection_id):
    collection = Collection.query.filter_by(id=collection_id, user_id=current_user.id).first_or_404()
    collection.is_public = not collection.is_public
    db.session.commit()
    return jsonify({
        'success': True,
        'is_public': collection.is_public,
        'share_url': f'/collections/shared/{collection.share_token}' if collection.is_public else None
    })


@collections_bp.route('/shared/<share_token>')
def shared_view(share_token):
    collection = Collection.query.filter_by(share_token=share_token, is_public=True).first_or_404()
    generations = Generation.query.filter_by(collection_id=collection.id)\
        .order_by(Generation.created_at.desc()).all()

    output_folder = current_app.config.get('OUTPUT_FOLDER', 'static/outputs')
    folder_files = get_collection_files(collection.id, output_folder)

    return render_template('collection_shared.html',
        collection=collection,
        generations=generations,
        folder_files=folder_files,
    )


@collections_bp.route('/<collection_id>/delete', methods=['POST'])
@login_required
def delete(collection_id):
    collection = Collection.query.filter_by(id=collection_id, user_id=current_user.id).first_or_404()

    # Delete collection folder
    output_folder = current_app.config.get('OUTPUT_FOLDER', 'static/outputs')
    col_dir = os.path.join(output_folder, f'collection_{collection_id}')
    if os.path.exists(col_dir):
        import shutil
        shutil.rmtree(col_dir, ignore_errors=True)

    db.session.delete(collection)
    db.session.commit()
    return jsonify({'success': True})


@collections_bp.route('/bulk-delete', methods=['POST'])
@login_required
def bulk_delete():
    """Delete multiple collections at once."""
    data = request.get_json() or {}
    collection_ids = data.get('ids', [])

    if not collection_ids:
        return jsonify({'error': 'No collections selected'}), 400

    output_folder = current_app.config.get('OUTPUT_FOLDER', 'static/outputs')
    deleted_count = 0

    for col_id in collection_ids:
        collection = Collection.query.filter_by(id=col_id, user_id=current_user.id).first()
        if collection:
            # Delete collection folder
            col_dir = os.path.join(output_folder, f'collection_{col_id}')
            if os.path.exists(col_dir):
                import shutil
                shutil.rmtree(col_dir, ignore_errors=True)

            db.session.delete(collection)
            deleted_count += 1

    db.session.commit()
    return jsonify({
        'success': True,
        'deleted': deleted_count,
        'message': f'{deleted_count} collection{"s" if deleted_count != 1 else ""} deleted'
    })


@collections_bp.route('/compare')
@login_required
def compare():
    """Before/After comparison view."""
    collections = Collection.query.filter_by(user_id=current_user.id)\
        .order_by(Collection.updated_at.desc()).all()
    return render_template('compare.html', collections=collections)