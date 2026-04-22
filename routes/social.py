from flask import Blueprint, render_template, request, jsonify, current_app
from flask_login import login_required, current_user
from models import db, SocialPost, Collection, Generation
from datetime import datetime
import os

social_bp = Blueprint('social', __name__)


@social_bp.route('/')
@login_required
def index():
    posts = SocialPost.query.filter_by(user_id=current_user.id)\
        .order_by(SocialPost.created_at.desc()).all()
    collections = Collection.query.filter_by(user_id=current_user.id)\
        .order_by(Collection.name.asc()).all()
    return render_template('social.html', posts=posts, collections=collections)


@social_bp.route('/boards')
@login_required
def list_boards():
    """List Pinterest boards."""
    token = current_app.config.get('PINTEREST_ACCESS_TOKEN', '')
    if not token:
        return jsonify({'error': 'Pinterest token not configured'}), 400

    from modules.pinterest_api import PinterestAPI
    api = PinterestAPI(token)
    boards = api.list_boards()
    return jsonify({'boards': boards})


@social_bp.route('/test-connection')
@login_required
def test_connection():
    """Test Pinterest API connection."""
    token = current_app.config.get('PINTEREST_ACCESS_TOKEN', '')
    if not token:
        return jsonify({'error': 'Pinterest token not configured'}), 400

    from modules.pinterest_api import PinterestAPI
    api = PinterestAPI(token)
    result = api.test_connection()
    return jsonify(result)


@social_bp.route('/generate-caption', methods=['POST'])
@login_required
def generate_caption():
    """Generate AI caption + hashtags for a post."""
    data = request.get_json() or {}
    prompt_text = data.get('prompt_text', '').strip()
    platform = data.get('platform', 'pinterest')
    product_url = data.get('product_url', '').strip()

    if not prompt_text:
        return jsonify({'error': 'Prompt text required'}), 400

    from modules.gemini_engine import GeminiEngine
    api_key = current_app.config.get('GROQ_API_KEY', '')
    if not api_key:
        return jsonify({'error': 'Groq API key not configured'}), 400

    engine = GeminiEngine(api_key)
    result = engine.generate_social_caption(prompt_text, platform, product_url)
    return jsonify(result)


@social_bp.route('/collection-images/<collection_id>')
@login_required
def collection_images(collection_id):
    """Get images from a collection for posting."""
    from modules.collection_mgr import get_collection_files
    output_folder = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'static', 'outputs')
    files = get_collection_files(collection_id, output_folder)
    images = [f for f in files if f['file_type'] == 'image']
    return jsonify({'images': images})


@social_bp.route('/create', methods=['POST'])
@login_required
def create_post():
    """Create a social post (draft or scheduled)."""
    data = request.get_json() or {}

    image_path = data.get('image_path', '').strip()
    if not image_path:
        return jsonify({'error': 'Image is required'}), 400

    post = SocialPost(
        user_id=current_user.id,
        collection_id=data.get('collection_id', '') or None,
        platform=data.get('platform', 'pinterest'),
        image_path=image_path,
        title=data.get('title', '').strip(),
        caption=data.get('caption', '').strip(),
        hashtags=data.get('hashtags', '').strip(),
        pin_link=data.get('pin_link', '').strip(),
        board_id=data.get('board_id', '').strip(),
        board_name=data.get('board_name', '').strip(),
        status='draft',
    )

    # Schedule if time provided
    scheduled_at = data.get('scheduled_at', '').strip()
    if scheduled_at:
        try:
            post.scheduled_at = datetime.fromisoformat(scheduled_at)
            post.status = 'scheduled'
        except ValueError:
            pass

    db.session.add(post)
    db.session.commit()
    return jsonify({'success': True, 'id': post.id, 'status': post.status})


@social_bp.route('/update/<post_id>', methods=['POST'])
@login_required
def update_post(post_id):
    """Update a social post."""
    post = SocialPost.query.filter_by(id=post_id, user_id=current_user.id).first()
    if not post:
        return jsonify({'error': 'Post not found'}), 404
    if post.status == 'posted':
        return jsonify({'error': 'Cannot edit posted content'}), 400

    data = request.get_json() or {}
    if 'title' in data:
        post.title = data['title'].strip()
    if 'caption' in data:
        post.caption = data['caption'].strip()
    if 'hashtags' in data:
        post.hashtags = data['hashtags'].strip()
    if 'pin_link' in data:
        post.pin_link = data['pin_link'].strip()
    if 'board_id' in data:
        post.board_id = data['board_id'].strip()
    if 'board_name' in data:
        post.board_name = data['board_name'].strip()
    if 'scheduled_at' in data:
        try:
            post.scheduled_at = datetime.fromisoformat(data['scheduled_at'])
            if post.status == 'draft':
                post.status = 'scheduled'
        except ValueError:
            pass

    db.session.commit()
    return jsonify({'success': True})


@social_bp.route('/delete/<post_id>', methods=['POST'])
@login_required
def delete_post(post_id):
    """Delete a social post."""
    post = SocialPost.query.filter_by(id=post_id, user_id=current_user.id).first()
    if not post:
        return jsonify({'error': 'Post not found'}), 404

    db.session.delete(post)
    db.session.commit()
    return jsonify({'success': True})


@social_bp.route('/post-now/<post_id>', methods=['POST'])
@login_required
def post_now(post_id):
    """Immediately post to Pinterest."""
    post = SocialPost.query.filter_by(id=post_id, user_id=current_user.id).first()
    if not post:
        return jsonify({'error': 'Post not found'}), 404
    if post.status == 'posted':
        return jsonify({'error': 'Already posted'}), 400

    token = current_app.config.get('PINTEREST_ACCESS_TOKEN', '')
    if not token:
        return jsonify({'error': 'Pinterest token not configured'}), 400

    if not post.board_id:
        return jsonify({'error': 'Select a board first'}), 400

    from modules.pinterest_api import PinterestAPI
    api = PinterestAPI(token)

    # Build full image path
    image_full_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        'static', post.image_path)

    description = post.caption
    if post.hashtags:
        description += '\n\n' + post.hashtags

    post.status = 'posting'
    db.session.commit()

    status_code, result = api.create_pin(
        board_id=post.board_id,
        title=post.title,
        description=description,
        link=post.pin_link,
        image_path=image_full_path,
    )

    if status_code in (200, 201):
        post.status = 'posted'
        post.posted_at = datetime.now()
        post.platform_post_id = result.get('id', '')
        post.error_message = None
        db.session.commit()
        return jsonify({'success': True, 'pin_id': result.get('id', '')})
    else:
        post.status = 'failed'
        post.error_message = result.get('message', str(result))[:200]
        db.session.commit()
        return jsonify({'error': post.error_message}), 400


@social_bp.route('/schedule/<post_id>', methods=['POST'])
@login_required
def schedule_post(post_id):
    """Set schedule time for a post."""
    post = SocialPost.query.filter_by(id=post_id, user_id=current_user.id).first()
    if not post:
        return jsonify({'error': 'Post not found'}), 404

    data = request.get_json() or {}
    scheduled_at = data.get('scheduled_at', '').strip()
    if not scheduled_at:
        return jsonify({'error': 'Schedule time required'}), 400

    try:
        post.scheduled_at = datetime.fromisoformat(scheduled_at)
        post.status = 'scheduled'
        db.session.commit()
        return jsonify({'success': True})
    except ValueError:
        return jsonify({'error': 'Invalid date format'}), 400
