from flask import Blueprint, render_template, request, jsonify, current_app
from flask_login import login_required, current_user
from models import db, Collection, Generation
from modules.flow_engine import generate_banners, ASPECT_RATIOS
from datetime import datetime
import os

banners_bp = Blueprint('banners', __name__)


@banners_bp.route('/')
@login_required
def index():
    collections = Collection.query.filter_by(user_id=current_user.id)\
        .order_by(Collection.name.asc()).all()
    return render_template('banners.html',
        collections=collections,
        aspect_ratios=ASPECT_RATIOS,
    )


@banners_bp.route('/generate', methods=['POST'])
@login_required
def generate():
    data = request.get_json() or {}
    prompt = data.get('prompt', '').strip()
    aspect_ratio = data.get('aspect_ratio', 'landscape')
    collection_id = data.get('collection_id', '').strip()
    count = min(int(data.get('count', 4)), 4)

    if not prompt:
        return jsonify({'error': 'Enter a banner prompt'}), 400

    api_key = current_app.config.get('HF_API_KEY', '')
    if not api_key:
        return jsonify({'error': 'HuggingFace API key not configured in config.py'}), 500

    if not collection_id:
        col_name = f"Banners — {prompt[:40]}"
        collection = Collection(
            user_id=current_user.id,
            name=col_name,
            description=f'Generated via FLUX.1 Schnell | {ASPECT_RATIOS.get(aspect_ratio, {}).get("label", aspect_ratio)}'
        )
        db.session.add(collection)
        db.session.flush()
        collection_id = collection.id

    output_dir = os.path.join(
        current_app.static_folder, 'outputs', f'collection_{collection_id}')

    result = generate_banners(
        prompt=prompt,
        api_key=api_key,
        aspect_ratio=aspect_ratio,
        count=count,
        output_dir=output_dir,
        collection_id=collection_id,
    )

    saved = []
    for img in result['images']:
        gen = Generation(
            user_id=current_user.id,
            collection_id=collection_id,
            input_type='text',
            output_type='image',
            output_path=f"outputs/collection_{collection_id}/{img['filename']}",
            pomelli_feature='flow_banner',
            status='completed',
            file_size=img['size'],
            completed_at=datetime.now(),
        )
        db.session.add(gen)
        saved.append({
            'filename': img['filename'],
            'path': f"/static/outputs/collection_{collection_id}/{img['filename']}",
            'size': img['size'],
        })

    db.session.commit()

    return jsonify({
        'success': result['success'],
        'images': saved,
        'errors': result['errors'],
        'collection_id': collection_id,
        'count': len(saved),
    })
