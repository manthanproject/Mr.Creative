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
        return (200, {'status': 'exported'})

    def validate_credentials(self):
        return {'connected': True, 'message': 'Export mode — no credentials needed'}


class InstagramAdapter(PlatformAdapter):
    """Instagram posting via instagrapi (no API key needed — uses login).
    Source: Klaudiusz321/social-media-agents pattern."""

    def __init__(self, username, password):
        super().__init__('instagram')
        self.username = username
        self.password = password
        self._client: object | None = None

    def _get_client(self):
        if self._client is None:
            try:
                from instagrapi import Client
                self._client = Client()
                self._client.login(self.username, self.password)
                print(f"[Instagram] Logged in as {self.username}")
            except ImportError:
                print("[Instagram] pip install instagrapi")
                return None
            except Exception as e:
                print(f"[Instagram] Login failed: {e}")
                return None
        return self._client

    def post(self, image_path, title, caption, hashtags, **kwargs):
        client = self._get_client()
        if not client:
            return {'success': False, 'error': 'Instagram login failed'}

        try:
            full_caption = caption
            if hashtags:
                full_caption += '\n\n' + hashtags

            media = client.photo_upload(
                path=image_path,
                caption=full_caption,
            )
            media_url = f"https://www.instagram.com/p/{media.code}"
            print(f"[Instagram] Posted: {media_url}")
            return {
                'success': True,
                'post_id': media.id,
                'url': media_url,
            }
        except Exception as e:
            print(f"[Instagram] Post failed: {e}")
            return {'success': False, 'error': str(e)}

    def post_carousel(self, image_paths, caption, hashtags='', **kwargs):
        """Post multiple images as Instagram carousel."""
        client = self._get_client()
        if not client:
            return {'success': False, 'error': 'Instagram login failed'}

        try:
            full_caption = caption
            if hashtags:
                full_caption += '\n\n' + hashtags

            media = client.album_upload(
                paths=image_paths,
                caption=full_caption,
            )
            media_url = f"https://www.instagram.com/p/{media.code}"
            print(f"[Instagram] Carousel posted: {media_url}")
            return {
                'success': True,
                'post_id': media.id,
                'url': media_url,
            }
        except Exception as e:
            print(f"[Instagram] Carousel failed: {e}")
            return {'success': False, 'error': str(e)}

    def validate_credentials(self):
        client = self._get_client()
        if client:
            info = client.account_info()
            return {
                'connected': True,
                'username': info.username,
                'followers': info.follower_count,
            }
        return {'connected': False, 'error': 'Login failed'}


class TwitterAdapter(PlatformAdapter):
    """Twitter/X posting via tweepy."""

    def __init__(self, api_key, api_secret, access_token, access_secret):
        super().__init__('twitter')
        self.api_key = api_key
        self.api_secret = api_secret
        self.access_token = access_token
        self.access_secret = access_secret
        self._client: object | None = None
        self._api: object | None = None

    def _get_client(self):
        if self._client is None:
            try:
                import tweepy
                # v2 client for tweets
                self._client = tweepy.Client(
                    consumer_key=self.api_key,
                    consumer_secret=self.api_secret,
                    access_token=self.access_token,
                    access_token_secret=self.access_secret,
                )
                # v1.1 API for media upload
                auth = tweepy.OAuth1UserHandler(
                    self.api_key, self.api_secret,
                    self.access_token, self.access_secret,
                )
                self._api = tweepy.API(auth)
                print("[Twitter] Authenticated")
            except ImportError:
                print("[Twitter] pip install tweepy")
                return None, None
            except Exception as e:
                print(f"[Twitter] Auth failed: {e}")
                return None, None
        return self._client, self._api

    def post(self, image_path, title, caption, hashtags, **kwargs):
        client, api = self._get_client()
        if not client or not api:
            return {'success': False, 'error': 'Twitter auth failed'}

        try:
            # Upload media via v1.1
            media = api.media_upload(filename=image_path)

            # Post tweet with media via v2
            text = caption[:250]  # Leave room for hashtags
            if hashtags:
                remaining = 280 - len(text) - 2
                tags = hashtags.split()[:3]  # Max 3 hashtags for Twitter
                tag_text = ' '.join(tags)
                if len(tag_text) <= remaining:
                    text += '\n\n' + tag_text

            response = client.create_tweet(
                text=text,
                media_ids=[media.media_id],
            )
            tweet_id = response.data['id']
            tweet_url = f"https://twitter.com/i/status/{tweet_id}"
            print(f"[Twitter] Posted: {tweet_url}")
            return {
                'success': True,
                'tweet_id': tweet_id,
                'url': tweet_url,
            }
        except Exception as e:
            print(f"[Twitter] Post failed: {e}")
            return {'success': False, 'error': str(e)}

    def validate_credentials(self):
        client, api = self._get_client()
        if client:
            me = client.get_me()
            return {
                'connected': True,
                'username': me.data.username,
            }
        return {'connected': False, 'error': 'Auth failed'}


# ═══════════════════════════════════════════════
# Platform Constraints (from social-media-agents)
# ═══════════════════════════════════════════════

PLATFORM_CONSTRAINTS = {
    'instagram': {
        'max_caption_length': 2200,
        'hashtag_limit': 30,
        'ideal_image_ratio': '1:1',
        'image_sizes': {'square': (1080, 1080), 'portrait': (1080, 1350), 'story': (1080, 1920)},
        'supports_carousel': True,
        'max_carousel_images': 10,
    },
    'twitter': {
        'max_caption_length': 280,
        'hashtag_limit': 3,
        'ideal_image_ratio': '16:9',
        'image_sizes': {'landscape': (1200, 675), 'square': (1200, 1200)},
        'supports_carousel': False,
        'max_carousel_images': 4,
    },
    'pinterest': {
        'max_caption_length': 500,
        'hashtag_limit': 5,
        'ideal_image_ratio': '2:3',
        'image_sizes': {'pin': (1000, 1500), 'square': (1000, 1000)},
        'supports_carousel': True,
        'max_carousel_images': 5,
    },
    'facebook': {
        'max_caption_length': 63206,
        'hashtag_limit': 5,
        'ideal_image_ratio': '1.91:1',
        'image_sizes': {'landscape': (1200, 630), 'square': (1080, 1080)},
        'supports_carousel': True,
        'max_carousel_images': 10,
    },
    'tiktok': {
        'max_caption_length': 2200,
        'hashtag_limit': 5,
        'ideal_image_ratio': '9:16',
        'image_sizes': {'vertical': (1080, 1920)},
        'supports_carousel': True,
        'max_carousel_images': 35,
    },
}


# Adapter registry
ADAPTERS = {
    'pinterest': lambda config: PinterestAdapter(config.get('PINTEREST_ACCESS_TOKEN', ''))
                                if config.get('PINTEREST_ACCESS_TOKEN') else None,
    'instagram': lambda config: InstagramAdapter(
                                config.get('INSTAGRAM_USERNAME', ''),
                                config.get('INSTAGRAM_PASSWORD', ''))
                                if config.get('INSTAGRAM_USERNAME') else None,
    'twitter': lambda config: TwitterAdapter(
                              config.get('TWITTER_API_KEY', ''),
                              config.get('TWITTER_API_SECRET', ''),
                              config.get('TWITTER_ACCESS_TOKEN', ''),
                              config.get('TWITTER_ACCESS_SECRET', ''))
                              if config.get('TWITTER_API_KEY') else None,
    'export': lambda config: ExportAdapter(),
}


def get_adapter(platform, config):
    """Get platform adapter instance."""
    factory = ADAPTERS.get(platform)
    if not factory:
        return None
    try:
        return factory(config)
    except Exception as e:
        print(f"[SocialManager] Adapter error for {platform}: {e}")
        return None
