# -*- coding: utf-8 -*-
# GNU General Public License v2.0+ (see LICENSES/GPL-2.0-or-later.txt)

from __future__ import absolute_import, division, print_function
__metaclass__ = type

import json

from ansible.module_utils.urls import open_url
from ansible.module_utils.six.moves.urllib.error import HTTPError, URLError

GARAGE_API_ARGS = dict(
    api_url=dict(type='str', required=True),
    api_token=dict(type='str', required=True, no_log=True),
    validate_certs=dict(type='bool', default=True),
)


class GarageAPIError(Exception):
    """Raised when the Garage admin API returns an error."""

    def __init__(self, status, message):
        self.status = status
        self.message = message
        super(GarageAPIError, self).__init__('HTTP {0}: {1}'.format(status, message))


class GarageAPI(object):
    """Thin wrapper around the Garage Admin API v2."""

    def __init__(self, api_url, api_token, validate_certs=True):
        self.base_url = api_url.rstrip('/')
        self.validate_certs = validate_certs
        self.headers = {
            'Authorization': 'Bearer {0}'.format(api_token),
            'Content-Type': 'application/json',
            'Accept': 'application/json',
        }

    def _url(self, path):
        return '{0}/v2/{1}'.format(self.base_url, path)

    def _request(self, method, path, data=None, params=None):
        url = self._url(path)
        if params:
            query = '&'.join('{0}={1}'.format(k, v) for k, v in params.items() if v is not None)
            if query:
                url = '{0}?{1}'.format(url, query)

        body = json.dumps(data).encode('utf-8') if data is not None else None

        try:
            resp = open_url(
                url,
                data=body,
                headers=self.headers,
                method=method,
                validate_certs=self.validate_certs,
            )
            raw = resp.read()
            if not raw:
                return {}
            text = raw.decode('utf-8', errors='replace').strip()
            if not text:
                return {}
            return json.loads(text)
        except HTTPError as e:
            raw = e.read()
            try:
                msg = json.loads(raw)
            except Exception:
                msg = raw.decode('utf-8', errors='replace') if raw else str(e)
            raise GarageAPIError(e.code, msg)
        except URLError as e:
            raise GarageAPIError(0, str(e.reason))

    # ------------------------------------------------------------------
    # Key operations
    # ------------------------------------------------------------------

    def list_keys(self):
        return self._request('GET', 'ListKeys')

    def get_key_info(self, key_id=None, search=None, show_secret=False):
        params = {}
        if key_id:
            params['id'] = key_id
        if search:
            params['search'] = search
        if show_secret:
            params['showSecretKey'] = 'true'
        return self._request('GET', 'GetKeyInfo', params=params)

    def create_key(self, name=None, permissions=None):
        body = {}
        if name is not None:
            body['name'] = name
        if permissions is not None:
            body['permissions'] = permissions
        return self._request('POST', 'CreateKey', data=body)

    def update_key(self, key_id, name=None, permissions=None):
        body = {}
        if name is not None:
            body['name'] = name
        if permissions is not None:
            body['permissions'] = permissions
        return self._request('POST', 'UpdateKey', data=body, params={'id': key_id})

    def delete_key(self, key_id):
        return self._request('POST', 'DeleteKey', params={'id': key_id})

    # ------------------------------------------------------------------
    # Bucket operations
    # ------------------------------------------------------------------

    def list_buckets(self):
        return self._request('GET', 'ListBuckets')

    def get_bucket_info(self, bucket_id=None, global_alias=None):
        params = {}
        if bucket_id:
            params['id'] = bucket_id
        elif global_alias:
            params['globalAlias'] = global_alias
        return self._request('GET', 'GetBucketInfo', params=params)

    def create_bucket(self, global_alias=None, local_alias=None):
        body = {}
        if global_alias is not None:
            body['globalAlias'] = global_alias
        if local_alias is not None:
            body['localAlias'] = local_alias
        return self._request('POST', 'CreateBucket', data=body)

    def update_bucket(self, bucket_id, website_access=None, website_config=None, quotas=None):
        body = {}
        if website_access is not None:
            body['websiteAccess'] = website_access
            if website_access and website_config:
                body['websiteConfig'] = website_config
        if quotas is not None:
            body['quotas'] = quotas
        return self._request('POST', 'UpdateBucket', data=body, params={'id': bucket_id})

    def delete_bucket(self, bucket_id):
        return self._request('POST', 'DeleteBucket', params={'id': bucket_id})

    def add_bucket_alias(self, bucket_id, global_alias=None, local_alias=None, access_key_id=None):
        body = {'bucketId': bucket_id}
        if global_alias is not None:
            body['globalAlias'] = global_alias
        else:
            body['localAlias'] = local_alias
            body['accessKeyId'] = access_key_id
        return self._request('POST', 'AddBucketAlias', data=body)

    def remove_bucket_alias(self, bucket_id, global_alias=None, local_alias=None, access_key_id=None):
        body = {'bucketId': bucket_id}
        if global_alias is not None:
            body['globalAlias'] = global_alias
        else:
            body['localAlias'] = local_alias
            body['accessKeyId'] = access_key_id
        return self._request('POST', 'RemoveBucketAlias', data=body)

    # ------------------------------------------------------------------
    # Bucket-key permission operations
    # ------------------------------------------------------------------

    def allow_bucket_key(self, bucket_id, access_key_id, permissions):
        body = {
            'bucketId': bucket_id,
            'accessKeyId': access_key_id,
            'permissions': permissions,
        }
        return self._request('POST', 'AllowBucketKey', data=body)

    def deny_bucket_key(self, bucket_id, access_key_id, permissions):
        body = {
            'bucketId': bucket_id,
            'accessKeyId': access_key_id,
            'permissions': permissions,
        }
        return self._request('POST', 'DenyBucketKey', data=body)
