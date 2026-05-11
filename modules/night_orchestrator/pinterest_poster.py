"""
Night Orchestrator — Pinterest Auto-Poster
Reads approved content plans, finds images, generates captions,
creates scheduled SocialPost records.
Auto-scheduler handles the actual posting.
"""

import json
import logging
import os
from datetime import datetime, date, timedelta

logger = logging.getLogger('night_ops')


def auto_post_from_plan(app, plan_id, board_id, user_id, link=''):
    """
    Take an approved content plan and create scheduled Pinterest posts.

    Flow:
    1. Read plan items where platform = pinterest or both
    2. Find matching images from recent generations/collections
    3. Generate caption + hashtags via Gemini for each
    4. Create SocialPost records with optimal schedule
    5. Return summary
    """
    with app.app_context():
        from models import db, ContentPlan, SocialPost, Generation, Collection

        plan = ContentPlan.query.get(plan_id)
        if not plan:
            return {'success': False, 'error': 'Plan not found'}
        if plan.status not in ('approved', 'executed'):
            return {'success': False, 'error': f'Plan status is "{plan.status}", must be approved'}

        try:
            plan_data = json.loads(plan.plan_data) if plan.plan_data else {}
        except json.JSONDecodeError:
            return {'success': False, 'error': 'Invalid plan data JSON'}

        content_items = plan_data.get('content_items', [])
        if not content_items:
            return {'success': False, 'error': 'No content items in plan'}

        pinterest_items = []
        for item in content_items:
            plat = (item.get('platform') or '').lower()
            if plat in ('pinterest', 'both'):
                pinterest_items.append(item)

        if not pinterest_items:
            return {'success': False, 'error': 'No Pinterest items in this plan'}

        available_images = _find_available_images(user_id)
        if not available_images:
            return {'success': False, 'error': 'No generated images found. Generate some content first.'}

        schedule_times = _get_optimal_schedule(len(pinterest_items))
        created = []
        errors = []

        for i, item in enumerate(pinterest_items):
            try:
                image = _match_image(item, available_images, used=[c['image_path'] for c in created])
                if not image:
                    errors.append(f"No image found for: {item.get('product', 'unknown')}")
                    continue

                caption_data = _generate_caption(app, item)

                title = caption_data.get('title', item.get('product', 'Pin'))[:100]
                caption = caption_data.get('caption', item.get('caption_idea', ''))[:500]
                hashtags = caption_data.get('hashtags', '')
                if isinstance(hashtags, list):
                    hashtags = ' '.join(f'#{h.strip("#")}' for h in hashtags[:5])

                post = SocialPost(
                    user_id=user_id,
                    platform='pinterest',
                    image_path=image['path'],
                    title=title,
                    caption=caption,
                    hashtags=hashtags,
                    pin_link=link or 'https://dropy.in',
                    board_id=board_id,
                    scheduled_at=schedule_times[i] if i < len(schedule_times) else None,
                    status='scheduled' if i < len(schedule_times) else 'draft',
                )
                db.session.add(post)
                created.append({
                    'title': title,
                    'image_path': image['path'],
                    'scheduled_at': schedule_times[i].isoformat() if i < len(schedule_times) else None,
                })
                logger.info(f"[PinterestPoster] Created post: {title[:40]}")

            except Exception as e:
                errors.append(f"Error for {item.get('product', '?')}: {str(e)[:100]}")
                logger.error(f"[PinterestPoster] Item error: {e}")

        if created:
            plan.status = 'executed'
            db.session.commit()

        return {
            'success': len(created) > 0,
            'created_posts': len(created),
            'errors': errors,
            'posts': created,
        }


def _find_available_images(user_id):
    from models import Generation

    cutoff = datetime.now() - timedelta(days=30)
    gens = Generation.query.filter(
        Generation.user_id == user_id,
        Generation.status == 'completed',
        Generation.output_type == 'image',
        Generation.output_path.isnot(None),
        Generation.created_at >= cutoff,
    ).order_by(Generation.created_at.desc()).limit(100).all()

    images = []
    for g in gens:
        if g.output_path:
            images.append({
                'id': g.id,
                'path': g.output_path,
                'tags': (g.tags or '').lower(),
                'feature': g.pomelli_feature or '',
                'collection_id': g.collection_id,
                'created_at': g.created_at,
            })
    return images


def _match_image(plan_item, available_images, used=None):
    used = used or []
    unused = [img for img in available_images if img['path'] not in used]
    if not unused:
        unused = available_images

    product = (plan_item.get('product') or '').lower()
    style = (plan_item.get('style') or '').lower()
    item_type = (plan_item.get('type') or '').lower()
    keywords = set((product + ' ' + style + ' ' + item_type).split())

    scored = []
    for img in unused:
        score = 0
        img_text = img['tags'] + ' ' + img['feature']
        for kw in keywords:
            if len(kw) > 2 and kw in img_text:
                score += 1
        scored.append((score, img))

    scored.sort(key=lambda x: -x[0])
    return scored[0][1] if scored else None


def _generate_caption(app, plan_item):
    try:
        from modules.night_orchestrator.llm import call_llm

        product = plan_item.get('product', 'beauty product')
        style = plan_item.get('style', 'elegant and clean')
        caption_idea = plan_item.get('caption_idea', '')
        hashtags_hint = plan_item.get('hashtags', [])

        prompt = f"""Generate a Pinterest pin caption for an e-commerce beauty/health product.

Product: {product}
Style/Mood: {style}
Caption idea: {caption_idea}
Suggested hashtags: {', '.join(hashtags_hint) if isinstance(hashtags_hint, list) else hashtags_hint}

Respond ONLY with JSON, no markdown:
{{"title": "short pin title (max 100 chars)", "caption": "engaging pin description (max 400 chars, include CTA)", "hashtags": "#tag1 #tag2 #tag3 #tag4 #tag5"}}"""

        result = call_llm(prompt, temperature=0.8, max_tokens=500)
        result = result.strip()
        if result.startswith('```'):
            result = result.split('\n', 1)[-1].rsplit('```', 1)[0]

        return json.loads(result)

    except Exception as e:
        logger.warning(f"[PinterestPoster] Caption generation failed: {e}")
        return {
            'title': plan_item.get('product', 'Pin')[:100],
            'caption': plan_item.get('caption_idea', '')[:400],
            'hashtags': ' '.join(f'#{h}' for h in plan_item.get('hashtags', [])[:5])
                        if isinstance(plan_item.get('hashtags'), list) else '',
        }


def _get_optimal_schedule(count, start_hour=8, posts_per_day=4):
    from modules.social_manager import get_posting_schedule
    return get_posting_schedule(
        count=count,
        platform='pinterest',
        posts_per_day=posts_per_day,
    )


def get_boards(app):
    with app.app_context():
        token = app.config.get('PINTEREST_ACCESS_TOKEN', '')
        if not token:
            return {'success': False, 'error': 'Pinterest token not configured'}

        from modules.pinterest_api import PinterestAPI
        api = PinterestAPI(token)

        try:
            boards = api.list_boards()
            return {'success': True, 'boards': boards}
        except Exception as e:
            return {'success': False, 'error': str(e)}
