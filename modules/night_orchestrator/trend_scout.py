"""
Night Orchestrator — TrendScout
Scrapes trending content from Pinterest and Amazon bestsellers.
Uses requests + BeautifulSoup (no Selenium overhead for public pages).
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

# ── User agents rotation ────────────────────────────────────────────
_USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
]

# ── Target categories for dropy.in + Rudra Retails ──────────────────
PINTEREST_SEARCH_QUERIES = [
    'beauty products trending 2026',
    'skincare routine trending',
    'hair care products',
    'personal care aesthetic',
    'health wellness products',
    'CeraVe skincare',
    'Korean beauty products',
    'imported beauty India',
    'lifestyle products aesthetic',
    'bath body products trending',
]

AMAZON_BESTSELLER_URLS = [
    # Amazon India - Beauty bestsellers
    ('https://www.amazon.in/gp/bestsellers/beauty/ref=zg_bs_beauty_sm', 'beauty'),
    # Amazon India - Health & Personal Care
    ('https://www.amazon.in/gp/bestsellers/hpc/ref=zg_bs_hpc_sm', 'health_personal_care'),
    # Amazon India - Skin Care
    ('https://www.amazon.in/gp/bestsellers/beauty/1374407031/ref=zg_bs_nav_beauty_1', 'skin_care'),
    # Amazon India - Hair Care
    ('https://www.amazon.in/gp/bestsellers/beauty/1374340031/ref=zg_bs_nav_beauty_1', 'hair_care'),
]


def _get_session():
    """Create a requests session with random UA and common headers."""
    s = requests.Session()
    s.headers.update({
        'User-Agent': random.choice(_USER_AGENTS),
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
    })
    return s


def _polite_delay(min_s=1.5, max_s=3.5):
    """Random delay to avoid rate limiting."""
    time.sleep(random.uniform(min_s, max_s))


# ═══════════════════════════════════════════════════════════════════
#  PINTEREST TREND SCANNER
# ═══════════════════════════════════════════════════════════════════

def scan_pinterest_trends(queries: list[str] | None = None, max_per_query: int = 10) -> list[dict]:
    """
    Scrape Pinterest search results for trending pins.
    Returns list of trend dicts: {title, description, image_url, pin_url, query, score}
    """
    queries = queries or PINTEREST_SEARCH_QUERIES
    all_trends = []
    session = _get_session()

    for query in queries:
        try:
            logger.info(f"[TrendScout] Pinterest search: {query}")
            url = f'https://www.pinterest.com/search/pins/?q={requests.utils.quote(query)}'
            resp = session.get(url, timeout=15)

            if resp.status_code != 200:
                logger.warning(f"[TrendScout] Pinterest {resp.status_code} for '{query}'")
                _polite_delay()
                continue

            # Pinterest renders via React — HTML has limited data in initial load
            # Try to extract from embedded JSON state
            trends = _parse_pinterest_html(resp.text, query)
            all_trends.extend(trends[:max_per_query])

            logger.info(f"[TrendScout] Found {len(trends)} pins for '{query}'")
            _polite_delay()

        except Exception as e:
            logger.error(f"[TrendScout] Pinterest error for '{query}': {e}")
            continue

    # Deduplicate by title
    seen = set()
    unique = []
    for t in all_trends:
        key = t.get('title', '')[:50].lower()
        if key and key not in seen:
            seen.add(key)
            unique.append(t)

    logger.info(f"[TrendScout] Pinterest total: {len(unique)} unique trends")
    return unique


def _parse_pinterest_html(html: str, query: str) -> list[dict]:
    """
    Extract pin data from Pinterest HTML.
    Pinterest embeds JSON resource data in script tags.
    """
    trends = []

    # Strategy 1: Parse __PWS_DATA__ JSON blob (Pinterest's embedded state)
    pws_match = re.search(r'<script[^>]*id="__PWS_DATA__"[^>]*>(.+?)</script>', html, re.DOTALL)
    if pws_match:
        try:
            data = json.loads(pws_match.group(1))
            pins = _extract_pins_from_pws(data)
            for pin in pins:
                pin['query'] = query
                pin['source'] = 'pinterest'
                trends.append(pin)
            if trends:
                return trends
        except (json.JSONDecodeError, KeyError):
            pass

    # Strategy 2: Look for JSON in other script tags
    for match in re.finditer(r'<script[^>]*type="application/json"[^>]*>(.+?)</script>', html, re.DOTALL):
        try:
            data = json.loads(match.group(1))
            pins = _extract_pins_from_pws(data)
            for pin in pins:
                pin['query'] = query
                pin['source'] = 'pinterest'
                trends.append(pin)
            if trends:
                return trends
        except (json.JSONDecodeError, KeyError):
            pass

    # Strategy 3: Fallback to basic HTML parsing (limited data)
    soup = BeautifulSoup(html, 'html.parser')
    for img in soup.select('img[src*="pinimg.com"]'):
        title = img.get('alt', '').strip()
        if title and len(title) > 5:
            trends.append({
                'title': title,
                'description': '',
                'image_url': img.get('src', ''),
                'pin_url': '',
                'query': query,
                'source': 'pinterest',
                'score': 0.5,
            })

    return trends


def _extract_pins_from_pws(data: dict | list, depth: int = 0) -> list[dict]:
    """Recursively extract pin objects from Pinterest's nested JSON state."""
    if depth > 8:
        return []

    pins = []

    if isinstance(data, dict):
        # Check if this dict looks like a pin
        if data.get('type') == 'pin' or ('grid_title' in data) or ('closeup_description' in data):
            pin = {
                'title': data.get('grid_title', '') or data.get('title', ''),
                'description': data.get('closeup_description', '') or data.get('description', ''),
                'image_url': '',
                'pin_url': f"https://www.pinterest.com/pin/{data['id']}/" if data.get('id') else '',
                'score': min(1.0, (data.get('repin_count', 0) + data.get('comment_count', 0)) / 100),
            }
            # Extract image URL
            images = data.get('images', {}) or data.get('image_medium_size_pixels', {})
            if isinstance(images, dict):
                for key in ['orig', '736x', '564x', '474x', '236x']:
                    if key in images and isinstance(images[key], dict):
                        pin['image_url'] = images[key].get('url', '')
                        break
            if pin['title']:
                pins.append(pin)

        # Recurse into values
        for v in data.values():
            if isinstance(v, (dict, list)):
                pins.extend(_extract_pins_from_pws(v, depth + 1))

    elif isinstance(data, list):
        for item in data:
            if isinstance(item, (dict, list)):
                pins.extend(_extract_pins_from_pws(item, depth + 1))

    return pins


# ═══════════════════════════════════════════════════════════════════
#  AMAZON BESTSELLER SCANNER
# ═══════════════════════════════════════════════════════════════════

def scan_amazon_bestsellers(urls: list[tuple[str, str]] | None = None, max_per_page: int = 20) -> list[dict]:
    """
    Scrape Amazon India bestseller pages.
    Returns list of product dicts: {rank, title, price, rating, reviews, image_url, product_url, category}
    """
    urls = urls or AMAZON_BESTSELLER_URLS
    all_products = []
    session = _get_session()

    for url, category in urls:
        try:
            logger.info(f"[TrendScout] Amazon bestsellers: {category}")
            resp = session.get(url, timeout=15)

            if resp.status_code != 200:
                logger.warning(f"[TrendScout] Amazon {resp.status_code} for '{category}'")
                _polite_delay(2, 5)
                continue

            products = _parse_amazon_bestsellers(resp.text, category)
            all_products.extend(products[:max_per_page])

            logger.info(f"[TrendScout] Found {len(products)} products in '{category}'")
            _polite_delay(2, 5)

        except Exception as e:
            logger.error(f"[TrendScout] Amazon error for '{category}': {e}")
            continue

    logger.info(f"[TrendScout] Amazon total: {len(all_products)} products")
    return all_products


def _parse_amazon_bestsellers(html: str, category: str) -> list[dict]:
    """Parse Amazon India bestseller page HTML."""
    soup = BeautifulSoup(html, 'html.parser')
    products = []

    # Amazon bestseller items are in zg-grid-general-faceout or similar containers
    items = soup.select('.zg-grid-general-faceout, .a-list-item .zg-item-immersion, [data-asin]')

    for rank, item in enumerate(items, 1):
        try:
            # Title
            title_el = item.select_one('.p13n-sc-truncate, ._cDEzb_p13n-sc-css-line-clamp-3_g3dy1, .a-link-normal span')
            title = title_el.get_text(strip=True) if title_el else ''

            if not title or len(title) < 5:
                continue

            # Price
            price_el = item.select_one('.p13n-sc-price, ._cDEzb_p13n-sc-price_3mJ9Z, .a-price .a-offscreen')
            price = price_el.get_text(strip=True) if price_el else ''

            # Rating
            rating_el = item.select_one('.a-icon-alt, [data-rating]')
            rating = ''
            if rating_el:
                rating_text = rating_el.get_text(strip=True) if rating_el.name != 'input' else rating_el.get('value', '')
                rating_match = re.search(r'([\d.]+)', rating_text)
                rating = float(rating_match.group(1)) if rating_match else 0

            # Review count
            review_el = item.select_one('.a-size-small span:last-child')
            reviews = review_el.get_text(strip=True) if review_el else '0'
            reviews = re.sub(r'[^\d]', '', reviews) or '0'

            # Image
            img_el = item.select_one('img')
            image_url = img_el.get('src', '') if img_el else ''

            # Product URL
            link_el = item.select_one('a.a-link-normal[href*="/dp/"]')
            product_url = ''
            if link_el:
                href = link_el.get('href', '')
                if href.startswith('/'):
                    href = f'https://www.amazon.in{href}'
                product_url = href

            # ASIN extraction
            asin = ''
            asin_match = re.search(r'/dp/([A-Z0-9]{10})', product_url)
            if asin_match:
                asin = asin_match.group(1)

            products.append({
                'rank': rank,
                'title': title,
                'price': price,
                'rating': float(rating) if rating else 0.0,
                'reviews': int(reviews),
                'image_url': image_url,
                'product_url': product_url,
                'asin': asin,
                'category': category,
                'source': 'amazon_in',
                'score': max(0.1, 1.0 - (rank / 50)),  # Higher rank = higher score
            })

        except Exception as e:
            logger.debug(f"[TrendScout] Amazon item parse error: {e}")
            continue

    return products


# ═══════════════════════════════════════════════════════════════════
#  MAIN ENTRY POINT
# ═══════════════════════════════════════════════════════════════════

def run_trend_scan(app) -> dict:
    """
    Full trend scan: Pinterest + Amazon.
    Saves results to night_trends table.
    Returns summary dict.
    """
    with app.app_context():
        from models import db, NightTrend

        scan_time = datetime.now()
        pinterest_trends = scan_pinterest_trends()
        amazon_products = scan_amazon_bestsellers()

        # Save to DB
        saved_count = 0
        for item in pinterest_trends + amazon_products:
            try:
                trend = NightTrend(
                    source=item.get('source', 'unknown'),
                    category=item.get('category', '') or item.get('query', ''),
                    trend_data=json.dumps(item, ensure_ascii=False),
                    score=item.get('score', 0.0),
                    scanned_at=scan_time,
                )
                db.session.add(trend)
                saved_count += 1
            except Exception as e:
                logger.error(f"[TrendScout] DB save error: {e}")
                continue

        db.session.commit()
        logger.info(f"[TrendScout] Saved {saved_count} trends to DB")

        return {
            'pinterest_count': len(pinterest_trends),
            'amazon_count': len(amazon_products),
            'total_saved': saved_count,
            'scan_time': scan_time.isoformat(),
            'top_pinterest': pinterest_trends[:5],
            'top_amazon': amazon_products[:5],
        }
