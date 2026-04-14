#!/usr/bin/python
# -*- coding: utf-8 -*-
# GNU General Public License v2.0+ (see LICENSES/GPL-2.0-or-later.txt)

from __future__ import absolute_import, division, print_function
__metaclass__ = type

DOCUMENTATION = r'''
---
module: garage_bucket
short_description: Manage Garage S3 buckets
description:
  - Create, update, or delete S3 buckets via the Garage Admin API v2.
  - Buckets are identified by their global alias (C(name)) or their internal
    C(bucket_id). At least one must be provided.
  - A bucket can only be deleted when it is empty.
options:
  state:
    description:
      - C(present) ensures the bucket exists and matches the given parameters.
      - C(absent) ensures the bucket is deleted. Fails if the bucket is not empty.
    type: str
    choices: [present, absent]
    default: present
  name:
    description:
      - Global alias for the bucket. Used as the bucket name seen by S3 clients.
        Either C(name) or C(bucket_id) (or both) must be supplied.
    type: str
  bucket_id:
    description:
      - Internal Garage bucket ID. Use this to target a bucket that has no
        global alias, or to avoid an alias lookup.
    type: str
  website_access:
    description:
      - Enable static website hosting for the bucket.
      - When C(true), C(website_index_document) is required.
    type: bool
  website_index_document:
    description:
      - The index document served for the website (e.g. C(index.html)).
      - Required when C(website_access=true).
    type: str
  website_error_document:
    description:
      - Optional custom error document path for the website.
    type: str
  quota_max_size:
    description:
      - Maximum total size in bytes. Set to C(0) to remove the quota.
    type: int
  quota_max_objects:
    description:
      - Maximum number of objects. Set to C(0) to remove the quota.
    type: int
  api_url:
    description:
      - Base URL of the Garage admin API (e.g. C(http://localhost:3903)).
    type: str
    required: true
  api_token:
    description:
      - Bearer token for the Garage admin API.
    type: str
    required: true
    no_log: true
  validate_certs:
    description:
      - Whether to validate TLS certificates.
      - Set to C(false) to allow self-signed certificates.
    type: bool
    default: true
notes:
  - Quotas: both C(quota_max_size) and C(quota_max_objects) must be set or
    unset together. To remove quotas set both to C(0).
'''

EXAMPLES = r'''
- name: Create a bucket with a global alias
  occ.garage.garage_bucket:
    api_url: http://garage.example.com:3903
    api_token: "{{ garage_admin_token }}"
    name: my-backups
    state: present
  register: bucket

- name: Enable website hosting
  occ.garage.garage_bucket:
    api_url: http://garage.example.com:3903
    api_token: "{{ garage_admin_token }}"
    name: my-static-site
    website_access: true
    website_index_document: index.html
    website_error_document: error.html
    state: present

- name: Apply size and object quotas
  occ.garage.garage_bucket:
    api_url: http://garage.example.com:3903
    api_token: "{{ garage_admin_token }}"
    name: my-backups
    quota_max_size: 107374182400  # 100 GiB
    quota_max_objects: 1000000
    state: present

- name: Delete an empty bucket
  occ.garage.garage_bucket:
    api_url: http://garage.example.com:3903
    api_token: "{{ garage_admin_token }}"
    name: my-backups
    state: absent
'''

RETURN = r'''
bucket:
  description: Current state of the bucket.
  returned: when state=present
  type: dict
  contains:
    id:
      description: Internal Garage bucket ID.
      type: str
    global_aliases:
      description: List of global aliases for this bucket.
      type: list
      elements: str
    website_access:
      description: Whether static website hosting is enabled.
      type: bool
    quota_max_size:
      description: Size quota in bytes, or null if unset.
      type: int
    quota_max_objects:
      description: Object count quota, or null if unset.
      type: int
    objects:
      description: Number of objects in the bucket.
      type: int
    bytes:
      description: Total size of objects in bytes.
      type: int
'''

from ansible.module_utils.basic import AnsibleModule
from ansible_collections.occ.garage.plugins.module_utils.garage_api import (
    GarageAPI,
    GarageAPIError,
    GARAGE_API_ARGS,
)


def _normalise(raw):
    quotas = raw.get('quotas') or {}
    return {
        'id': raw.get('id'),
        'global_aliases': raw.get('globalAliases', []),
        'local_aliases': raw.get('localAliases', []),
        'website_access': raw.get('websiteAccess', False),
        'quota_max_size': quotas.get('maxSize'),
        'quota_max_objects': quotas.get('maxObjects'),
        'objects': raw.get('objects', 0),
        'bytes': raw.get('bytes', 0),
    }


def run_module():
    argument_spec = dict(
        state=dict(type='str', default='present', choices=['present', 'absent']),
        name=dict(type='str'),
        bucket_id=dict(type='str'),
        website_access=dict(type='bool'),
        website_index_document=dict(type='str'),
        website_error_document=dict(type='str'),
        quota_max_size=dict(type='int'),
        quota_max_objects=dict(type='int'),
    )
    argument_spec.update(GARAGE_API_ARGS)

    module = AnsibleModule(
        argument_spec=argument_spec,
        required_one_of=[['name', 'bucket_id']],
        required_if=[
            ('website_access', True, ['website_index_document']),
        ],
        supports_check_mode=True,
    )

    state = module.params['state']
    name = module.params['name']
    bucket_id = module.params['bucket_id']
    website_access = module.params['website_access']
    website_index = module.params['website_index_document']
    website_error = module.params['website_error_document']
    quota_max_size = module.params['quota_max_size']
    quota_max_objects = module.params['quota_max_objects']

    # Quota consistency check
    if (quota_max_size is None) != (quota_max_objects is None):
        module.fail_json(msg='quota_max_size and quota_max_objects must both be set or both be omitted.')

    api = GarageAPI(module.params['api_url'], module.params['api_token'], module.params['validate_certs'])

    try:
        # ----------------------------------------------------------
        # Resolve existing bucket
        # ----------------------------------------------------------
        existing = None
        if bucket_id:
            try:
                existing = api.get_bucket_info(bucket_id=bucket_id)
            except GarageAPIError as e:
                if e.status == 404:
                    existing = None
                else:
                    module.fail_json(msg=str(e))
        elif name:
            try:
                existing = api.get_bucket_info(global_alias=name)
            except GarageAPIError as e:
                if e.status == 404:
                    existing = None
                else:
                    module.fail_json(msg=str(e))

        # ----------------------------------------------------------
        # state=absent
        # ----------------------------------------------------------
        if state == 'absent':
            if existing is None:
                module.exit_json(changed=False)
            if module.check_mode:
                module.exit_json(changed=True)
            api.delete_bucket(existing['id'])
            module.exit_json(changed=True)

        # ----------------------------------------------------------
        # state=present — create
        # ----------------------------------------------------------
        if existing is None:
            if module.check_mode:
                module.exit_json(changed=True, bucket={'id': None, 'global_aliases': [name] if name else []})
            created = api.create_bucket(global_alias=name)
            bucket_id = created['id']

            # Apply settings that cannot be set at creation time
            needs_update = website_access is not None or quota_max_size is not None
            if needs_update:
                website_cfg = None
                if website_access:
                    website_cfg = {'indexDocument': website_index}
                    if website_error:
                        website_cfg['errorDocument'] = website_error

                quotas = None
                if quota_max_size is not None:
                    quotas = {
                        'maxSize': quota_max_size if quota_max_size > 0 else None,
                        'maxObjects': quota_max_objects if quota_max_objects > 0 else None,
                    }

                created = api.update_bucket(
                    bucket_id,
                    website_access=website_access,
                    website_config=website_cfg,
                    quotas=quotas,
                )

            module.exit_json(changed=True, bucket=_normalise(created))

        # ----------------------------------------------------------
        # state=present — check for required updates
        # ----------------------------------------------------------
        current = _normalise(existing)
        changed = False
        update_kwargs = {}

        # Website
        if website_access is not None and current['website_access'] != website_access:
            changed = True
            update_kwargs['website_access'] = website_access
            if website_access:
                update_kwargs['website_config'] = {'indexDocument': website_index}
                if website_error:
                    update_kwargs['website_config']['errorDocument'] = website_error

        # Quotas
        if quota_max_size is not None:
            desired_size = quota_max_size if quota_max_size > 0 else None
            desired_objs = quota_max_objects if quota_max_objects > 0 else None
            if current['quota_max_size'] != desired_size or current['quota_max_objects'] != desired_objs:
                changed = True
                update_kwargs['quotas'] = {'maxSize': desired_size, 'maxObjects': desired_objs}

        if not changed:
            module.exit_json(changed=False, bucket=current)

        if module.check_mode:
            module.exit_json(changed=True, bucket=current)

        bid = existing['id']
        updated = api.update_bucket(bid, **update_kwargs)
        module.exit_json(changed=True, bucket=_normalise(updated))

    except GarageAPIError as e:
        module.fail_json(msg=str(e))


def main():
    run_module()


if __name__ == '__main__':
    main()
