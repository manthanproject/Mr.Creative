"""
Night Orchestrator — CompetitorWatcher
Monitors competitor Instagram and Pinterest pages (public profiles only).
Tracks follower changes, recent posts, engagement rates.
"""

import json
import re
import time
import random
import logging
from datetime import datetime
from typing import Optional

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger('night_ops')

_USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
]

# ── Competitor list (configurable via dashboard later) ──────────────
# Format: (platform, handle, page_url)
DEFAULT_COMPETITORS = [
    # Pinterest — beauty/personal care niche
    ('pinterest', 'celobeauty', 'https://www.pinterest.com/celobeauty/'),
    ('pinterest', 'naborijanatl', 'https://www.pinterest.com/naborijanatl/'),
    # Instagram — beauty/skincare niche (public profiles)
    ('instagram', 'dropy.in', 'https://www.instagram.com/dropy.in/'),         # own page
    ('instagram', 'naborija_natural', 'https://www.instagram.com/naborija_natural/'),
]


def _get_session():
    s = requests.Session()
    s.headers.update({
        'User-Agent': random.choice(_USER_AGENTS),
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
    })
    return s


def _polite_delay(min_s=2.0, max_s=5.0):
    time.sleep(random.uniform(min_s, max_s))


# ═══════════════════════════════════════════════════════════════════
#  PINTEREST PROFILE SCRAPER
# ═══════════════════════════════════════════════════════════════════

def scrape_pinterest_profile(session: requests.Session, handle: str, page_url: str) -> dict:
    """
    Scrape a public Pinterest profile for follower count and recent pins.
    """
    result = {
        'platform': 'pinterest',
        'handle': handle,
        'page_url': page_url,
        'follower_count': 0,
        'following_count': 0,
        'pin_count': 0,
        'recent_pins': [],
        'avg_engagement': 0.0,
        'error': None,
    }

    try:
        resp = session.get(page_url, timeout=15)
        if resp.status_code != 200:
            result['error'] = f'HTTP {resp.status_code}'
            return result

        html = resp.text

        # Extract from embedded JSON state
        pws_match = re.search(r'<script[^>]*id="__PWS_DATA__"[^>]*>(.+?)</script>', html, re.DOTALL)
        if pws_match:
            try:
                data = json.loads(pws_match.group(1))
                profile = _find_profile_in_pws(data)
                if profile:
                    result['follower_count'] = profile.get('follower_count', 0)
                    result['following_count'] = profile.get('following_count', 0)
                    result['pin_count'] = profile.get('pin_count', 0)
            except (json.JSONDecodeError, KeyError):
                pass

        # Fallback: parse HTML meta tags
        if result['follower_count'] == 0:
            soup = BeautifulSoup(html, 'html.parser')
            # Pinterest sometimes has follower count in meta description
            meta_desc = soup.select_one('meta[name="description"]')
            if meta_desc:
                content = meta_desc.get('content', '')
                follower_match = re.search(r'([\d,]+)\s*followers?', content, re.IGNORECASE)
                if follower_match:
                    result['follower_count'] = int(follower_match.group(1).replace(',', ''))

    except Exception as e:
        result['error'] = str(e)
        logger.error(f"[CompetitorWatcher] Pinterest profile error for {handle}: {e}")

    return result


def _find_profile_in_pws(data, depth=0):
    """Recursively find user profile data in Pinterest's PWS JSON."""
    if depth > 6:
        return None

    if isinstance(data, dict):
        if 'follower_count' in data and 'username' in data:
            return data
        for v in data.values():
            if isinstance(v, (dict, list)):
                found = _find_profile_in_pws(v, depth + 1)
                if found:
                    return found
    elif isinstance(data, list):
        for item in data:
            if isinstance(item, (dict, list)):
                found = _find_profile_in_pws(item, depth + 1)
                if found:
                    return found
    return None


# ═══════════════════════════════════════════════════════════════════
#  INSTAGRAM PROFILE SCRAPER (public, no login)
# ═══════════════════════════════════════════════════════════════════

def scrape_instagram_profile(session: requests.Session, handle: str, page_url: str) -> dict:
    """
    Scrape a public Instagram profile.
    Instagram is heavily JS-rendered — we try embedded JSON and meta tags.
    Falls back to basic meta/og data if API-like endpoints are blocked.
    """
    result = {
        'platform': 'instagram',
        'handle': handle,
        'page_url': page_url,
        'follower_count': 0,
        'following_count': 0,
        'post_count': 0,
        'recent_posts': [],
        'avg_engagement': 0.0,
        'bio': '',
        'error': None,
    }

    try:
        resp = session.get(page_url, timeout=15)
        if resp.status_code != 200:
            result['error'] = f'HTTP {resp.status_code}'
            return result

        html = resp.text

        # Strategy 1: shared_data JSON (older IG pages)
        sd_match = re.search(r'window\._sharedData\s*=\s*({.+?});</script>', html)
        if sd_match:
            try:
                shared = json.loads(sd_match.group(1))
                user = shared.get('entry_data', {}).get('ProfilePage', [{}])[0].get('graphql', {}).get('user', {})
                if user:
                    result['follower_count'] = user.get('edge_followed_by', {}).get('count', 0)
                    result['following_count'] = user.get('edge_follow', {}).get('count', 0)
                    result['post_count'] = user.get('edge_owner_to_timeline_media', {}).get('count', 0)
                    result['bio'] = user.get('biography', '')

                    # Recent posts
                    edges = user.get('edge_owner_to_timeline_media', {}).get('edges', [])
                    for edge in edges[:6]:
                        node = edge.get('node', {})
                        result['recent_posts'].append({
                            'shortcode': node.get('shortcode', ''),
                            'caption': (node.get('edge_media_to_caption', {}).get('edges', [{}])[0]
                                        .get('node', {}).get('text', ''))[:200],
                            'likes': node.get('edge_liked_by', {}).get('count', 0),
                            'comments': node.get('edge_media_to_comment', {}).get('count', 0),
                            'image_url': node.get('thumbnail_src', ''),
                            'timestamp': node.get('taken_at_timestamp', 0),
                        })

                    # Calculate avg engagement
                    if result['recent_posts'] and result['follower_count'] > 0:
                        total_eng = sum(p['likes'] + p['comments'] for p in result['recent_posts'])
                        result['avg_engagement'] = round(
                            (total_eng / len(result['recent_posts'])) / result['follower_count'] * 100, 2
                        )
                    return result
            except (json.JSONDecodeError, KeyError, IndexError):
                pass

        # Strategy 2: meta tags fallback
        soup = BeautifulSoup(html, 'html.parser')
        meta_desc = soup.select_one('meta[property="og:description"]')
        if meta_desc:
            content = meta_desc.get('content', '')
            # Format: "1,234 Followers, 567 Following, 89 Posts"
            follower_match = re.search(r'([\d,.]+[KkMm]?)\s*Followers', content)
            following_match = re.search(r'([\d,.]+[KkMm]?)\s*Following', content)
            post_match = re.search(r'([\d,.]+)\s*Posts', content)

            if follower_match:
                result['follower_count'] = _parse_count(follower_match.group(1))
            if following_match:
                result['following_count'] = _parse_count(following_match.group(1))
            if post_match:
                result['post_count'] = _parse_count(post_match.group(1))

        # Bio from og:title or description
        meta_title = soup.select_one('meta[property="og:title"]')
        if meta_title:
            result['bio'] = meta_title.get('content', '').split(' • ')[-1] if meta_title else ''

    except Exception as e:
        result['error'] = str(e)
        logger.error(f"[CompetitorWatcher] Instagram profile error for {handle}: {e}")

    return result


def _parse_count(text: str) -> int:
    """Parse follower/post counts like '1,234', '12.5K', '1.2M'."""
    text = text.strip().replace(',', '')
    multiplier = 1
    if text.upper().endswith('K'):
        multiplier = 1000
        text = text[:-1]
    elif text.upper().endswith('M'):
        multiplier = 1_000_000
        text = text[:-1]
    try:
        return int(float(text) * multiplier)
    except ValueError:
        return 0


# ═══════════════════════════════════════════════════════════════════
#  MAIN ENTRY POINT
# ═══════════════════════════════════════════════════════════════════

def run_competitor_scan(app, competitors: list[tuple] | None = None) -> dict:
    """
    Full competitor scan.
    Saves results to night_competitors table.
    Returns summary dict.
    """
    with app.app_context():
        from models import db, NightCompetitor

        competitors = competitors or DEFAULT_COMPETITORS
        session = _get_session()
        scan_time = datetime.now()
        results = []

        for platform, handle, page_url in competitors:
            logger.info(f"[CompetitorWatcher] Scanning {platform}/{handle}")

            if platform == 'pinterest':
                data = scrape_pinterest_profile(session, handle, page_url)
            elif platform == 'instagram':
                data = scrape_instagram_profile(session, handle, page_url)
            else:
                logger.warning(f"[CompetitorWatcher] Unknown platform: {platform}")
                continue

            results.append(data)

            # Save to DB
            try:
                comp = NightCompetitor(
                    platform=platform,
                    handle=handle,
                    page_url=page_url,
                    last_post_data=json.dumps(data, ensure_ascii=False),
                    follower_count=data.get('follower_count', 0),
                    avg_engagement=data.get('avg_engagement', 0.0),
                    scanned_at=scan_time,
                )
                db.session.add(comp)
            except Exception as e:
                logger.error(f"[CompetitorWatcher] DB save error for {handle}: {e}")

            _polite_delay()

        db.session.commit()
        logger.info(f"[CompetitorWatcher] Scanned {len(results)} competitors")

        return {
            'total_scanned': len(results),
            'scan_time': scan_time.isoformat(),
            'results': results,
            'errors': [r for r in results if r.get('error')],
        }
