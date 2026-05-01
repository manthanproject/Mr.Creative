"""
Mr.Creative Social Manager
Bulk post creation, export, and multi-platform posting infrastructure.

Features:
- Bulk create posts from pipeline job results
- Export images + captions as zip for manual posting
- Platform adapter pattern (Pinterest ready, Instagram/TikTok pluggable)
- Auto-caption integration with Copywriter module
"""

import os
import json
import csv
import zipfile
import io
from datetime import datetime, timedelta


def bulk_create_posts(db, user_id, job_results, collection_id,
                       platform='pinterest', schedule_interval=60):
    """Create SocialPost records from pipeline job results.

    Args:
        db: SQLAlchemy db instance
        user_id: User ID
        job_results: List of result dicts from pipeline (with caption, hashtags)
        collection_id: Collection ID
        platform: Target platform
        schedule_interval: Minutes between scheduled posts (0 = all draft)

    Returns:
        List of created post IDs
    """
    from models import SocialPost

    posts = []
    schedule_time = datetime.now() + timedelta(minutes=30)  # Start 30min from now

    for i, result in enumerate(job_results):
        if 'error' in result:
            continue
        if not result.get('path'):
            continue

        title = result.get('title', f'Post {i+1}')
        caption = result.get('caption', '')
        hashtags = result.get('hashtags', '')

        # Schedule time (if interval > 0)
        scheduled_at = None
        status = 'draft'
        if schedule_interval > 0:
            scheduled_at = schedule_time + timedelta(minutes=schedule_interval * i)
            status = 'scheduled'

        post = SocialPost(
            user_id=user_id,
            collection_id=collection_id,
            platform=platform,
            image_path=result['path'],
            title=title[:200],
            caption=caption,
            hashtags=hashtags,
            scheduled_at=scheduled_at,
            status=status,
        )
        db.session.add(post)
        posts.append(post)

    db.session.commit()
    ids = [p.id for p in posts]
    print(f"[SocialManager] Created {len(ids)} posts ({status})")
    return ids


def export_to_zip(results, base_dir, brand_name=''):
    """Export images + captions as a downloadable zip.

    Creates a zip with:
    - All images
    - captions.csv with columns: filename, title, caption, hashtags
    - posting_guide.txt with platform-specific tips

    Args:
        results: List of result dicts from pipeline
        base_dir: Static files base directory
        brand_name: Brand name for the guide

    Returns:
        BytesIO zip buffer (ready to send as response)
    """
    zip_buffer = io.BytesIO()

    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
        # CSV data
        csv_buffer = io.StringIO()
        writer = csv.writer(csv_buffer)
        writer.writerow(['filename', 'title', 'caption', 'hashtags', 'type'])

        for result in results:
            if 'error' in result:
                continue
            path = result.get('path', '')
            if not path:
                continue

            full_path = os.path.join(base_dir, path)
            if not os.path.exists(full_path):
                continue

            filename = os.path.basename(full_path)

            # Add image to zip
            zf.write(full_path, f'images/{filename}')

            # Add to CSV
            writer.writerow([
                filename,
                result.get('title', ''),
                result.get('caption', ''),
                result.get('hashtags', ''),
                result.get('type', ''),
            ])

        # Add CSV
        zf.writestr('captions.csv', csv_buffer.getvalue())

        # Add posting guide
        guide = f"""# {brand_name} — Social Media Posting Guide

## How to use these files

### Instagram
1. Open Instagram app → New Post
2. Select image from images/ folder
3. Copy caption from captions.csv
4. Add hashtags from captions.csv
5. Post or schedule

### Pinterest
1. Create new Pin
2. Upload image
3. Add title and description from captions.csv
4. Select appropriate board
5. Publish

### Facebook
1. Create new post
2. Upload image
3. Copy caption from captions.csv
4. Add 3-5 hashtags
5. Post or schedule

### TikTok
1. Create new photo post
2. Upload image
3. Add caption from captions.csv
4. Add trending hashtags
5. Post

## Tips
- Post during peak hours (9-11 AM, 7-9 PM local time)
- Space posts 1-2 hours apart
- Engage with comments within the first hour
- Use all hashtags on Instagram, fewer on other platforms
"""
        zf.writestr('posting_guide.txt', guide)

    zip_buffer.seek(0)
    return zip_buffer


def get_posting_schedule(count, platform='instagram', start_hour=9, end_hour=21,
                          posts_per_day=3, start_date=None):
    """Generate an optimal posting schedule.

    Args:
        count: Number of posts
        platform: Target platform
        start_hour: First post hour (24h)
        end_hour: Last post hour (24h)
        posts_per_day: Max posts per day
        start_date: Start date (default: tomorrow)

    Returns:
        List of datetime objects for each post
    """
    if start_date is None:
        start_date = datetime.now().replace(hour=0, minute=0, second=0) + timedelta(days=1)

    # Platform-specific optimal times
    peak_hours = {
        'instagram': [9, 12, 17, 19, 21],
        'pinterest': [8, 14, 20, 22],
        'facebook': [9, 13, 16, 19],
        'tiktok': [7, 10, 19, 22],
    }
    hours = peak_hours.get(platform, [9, 13, 18])

    schedule = []
    day = 0
    hour_idx = 0

    for i in range(count):
        if hour_idx >= min(posts_per_day, len(hours)):
            hour_idx = 0
            day += 1

        h = hours[hour_idx % len(hours)]
        post_time = start_date + timedelta(days=day, hours=h, minutes=(i % 4) * 15)
        schedule.append(post_time)
        hour_idx += 1

    return schedule


# ═══════════════════════════════════════════════
# Platform Adapters (pluggable pattern)
# ═══════════════════════════════════════════════

class PlatformAdapter:
    """Base class for social platform adapters."""

    def __init__(self, name):
        self.name = name

    def post(self, image_path, title, caption, hashtags, **kwargs):
        raise NotImplementedError

    def validate_credentials(self):
        raise NotImplementedError


class PinterestAdapter(PlatformAdapter):
    """Pinterest posting via existing PinterestAPI."""

    def __init__(self, access_token):
        super().__init__('pinterest')
        self.token = access_token

    def post(self, image_path, title, caption, hashtags, board_id='', link='', **kwargs):
        from modules.pinterest_api import PinterestAPI
        api = PinterestAPI(self.token)
        description = caption
        if hashtags:
            description += '\n\n' + hashtags
        return api.create_pin(
            board_id=board_id,
            title=title,
            description=description,
            link=link,
            image_path=image_path,
        )

    def validate_credentials(self):
        from modules.pinterest_api import PinterestAPI
        api = PinterestAPI(self.token)
        return api.test_connection()


class ExportAdapter(PlatformAdapter):
    """Fallback: export for manual posting."""

    def __init__(self):
        super().__init__('export')

    def post(self, image_path, title, caption, hashtags, **kwargs):
        # No-op — export handles this via zip
        return (200, {'status': 'exported'})

    def validate_credentials(self):
        return {'connected': True, 'message': 'Export mode — no credentials needed'}


# Adapter registry
ADAPTERS = {
    'pinterest': lambda token: PinterestAdapter(token) if token else None,
    'export': lambda _: ExportAdapter(),
}


def get_adapter(platform, config):
    """Get platform adapter instance.

    Args:
        platform: Platform name
        config: Flask app config dict

    Returns:
        PlatformAdapter instance or None
    """
    factory = ADAPTERS.get(platform)
    if not factory:
        return None

    if platform == 'pinterest':
        token = config.get('PINTEREST_ACCESS_TOKEN', '')
        return factory(token)
    return factory(None)
