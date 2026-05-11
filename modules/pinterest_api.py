"""
Mr.Creative — Pinterest API v5 Wrapper
Handles: list boards, create pin, upload image.
"""

import requests
import os
import base64


class PinterestAPI:
    """Pinterest API v5 client."""

    BASE_URL = 'https://api.pinterest.com/v5'

    def __init__(self, access_token):
        self.access_token = access_token
        self.headers = {
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json',
        }

    def _get(self, endpoint, params=None):
        resp = requests.get(f'{self.BASE_URL}/{endpoint}', headers=self.headers, params=params)
        return resp.json()

    def _post(self, endpoint, data=None):
        resp = requests.post(f'{self.BASE_URL}/{endpoint}', headers=self.headers, json=data)
        return resp.status_code, resp.json()

    def list_boards(self):
        """Get all boards for the authenticated user."""
        result = self._get('boards', params={'page_size': 50})
        boards = []
        for b in result.get('items', []):
            boards.append({
                'id': b.get('id', ''),
                'name': b.get('name', ''),
                'description': b.get('description', ''),
                'pin_count': b.get('pin_count', 0),
                'privacy': b.get('privacy', 'PUBLIC'),
            })
        return boards

    def create_board(self, name, description=''):
        """Create a new board."""
        status, data = self._post('boards', {
            'name': name,
            'description': description,
            'privacy': 'PUBLIC',
        })
        if status in (200, 201):
            return {'id': data.get('id'), 'name': data.get('name')}
        return {'error': data.get('message', 'Failed to create board')}

    def create_pin(self, board_id, title, description, link='', image_path=None, image_url=None):
        """Create a pin on a board."""
        pin_data = {
            'board_id': board_id,
            'title': title[:100],
            'description': description[:500],
        }
        if link:
            pin_data['link'] = link

        # Image source
        if image_path and os.path.exists(image_path):
            with open(image_path, 'rb') as f:
                b64 = base64.b64encode(f.read()).decode('utf-8')
            content_type = 'image/jpeg'
            if image_path.lower().endswith('.png'):
                content_type = 'image/png'
            elif image_path.lower().endswith('.webp'):
                content_type = 'image/webp'
            pin_data['media_source'] = {
                'source_type': 'image_base64',
                'content_type': content_type,
                'data': b64,
            }
        elif image_url:
            pin_data['media_source'] = {
                'source_type': 'image_url',
                'url': image_url,
            }
        else:
            return 400, {'error': 'No image provided'}

        status, data = self._post('pins', pin_data)
        return status, data

    def test_connection(self):
        """Test if the access token is valid."""
        try:
            result = self._get('user_account')
            if 'username' in result:
                return {'success': True, 'username': result['username'], 'business_name': result.get('business_name', '')}
            return {'success': False, 'error': result.get('message', 'Unknown error')}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    def get_account_analytics(self, start_date, end_date, metric_types=None):
        params = {
            'start_date': start_date, 'end_date': end_date,
            'app_types': 'ALL', 'pin_format': 'ALL',
            'from_claimed_content': 'BOTH', 'split_field': 'NO_SPLIT',
        }
        if metric_types:
            params['metric_types'] = ','.join(metric_types)
        return self._get('user_account/analytics', params=params)

    def get_top_pins(self, start_date, end_date, sort_by='IMPRESSION', num_pins=10):
        params = {
            'start_date': start_date, 'end_date': end_date,
            'sort_by': sort_by, 'num_of_pins': min(num_pins, 25),
            'pin_format': 'ALL', 'app_types': 'ALL', 'from_claimed_content': 'BOTH',
        }
        return self._get('user_account/top_pins/analytics', params=params)

    def get_pin_analytics(self, pin_id, start_date, end_date, metric_types=None):
        params = {'start_date': start_date, 'end_date': end_date, 'app_types': 'ALL'}
        if metric_types:
            params['metric_types'] = ','.join(metric_types)
        return self._get(f'pins/{pin_id}/analytics', params=params)

    def get_board_pins(self, board_id, page_size=25):
        return self._get(f'boards/{board_id}/pins', params={'page_size': page_size})

    def get_user_account(self):
        return self._get('user_account')
