#!/usr/bin/python
# -*- coding: utf-8 -*-
# GNU General Public License v2.0+ (see LICENSES/GPL-2.0-or-later.txt)

from __future__ import absolute_import, division, print_function
__metaclass__ = type

DOCUMENTATION = r'''
---
module: garage_bucket_key
short_description: Manage Garage S3 bucket-key permissions
description:
  - Grant or revoke read/write/owner permissions for an S3 access key on a
    specific bucket via the Garage Admin API v2.
  - C(state=present) calls C(AllowBucketKey) to activate the listed
    permission flags. Flags not mentioned are left unchanged.
  - C(state=absent) calls C(DenyBucketKey) to revoke the listed permission
    flags. Flags not mentioned are left unchanged.
  - To fully revoke all permissions, set all three flags and C(state=absent).
options:
  bucket_id:
    description:
      - Internal Garage bucket ID.
        Either C(bucket_id) or C(bucket_alias) must be supplied.
    type: str
  bucket_alias:
    description:
      - Global alias of the bucket. Used to resolve the C(bucket_id) when
        the internal ID is unknown.
    type: str
  access_key_id:
    description:
      - The S3 access key ID to grant/revoke permissions for.
    type: str
    required: true
  read:
    description:
      - Include the C(read) permission in the allow/deny operation.
    type: bool
    default: false
  write:
    description:
      - Include the C(write) permission in the allow/deny operation.
    type: bool
    default: false
  owner:
    description:
      - Include the C(owner) permission in the allow/deny operation.
      - Owner grants full control including bucket settings.
    type: bool
    default: false
  state:
    description:
      - C(present) calls C(AllowBucketKey) for the specified permissions.
      - C(absent) calls C(DenyBucketKey) for the specified permissions.
    type: str
    choices: [present, absent]
    default: present
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
  - At least one of C(read), C(write), or C(owner) must be C(true).
  - The module is idempotent: it reads the current permissions first and
    only calls the API if a change is actually required.
'''

EXAMPLES = r'''
- name: Grant read+write on a bucket to a key
  occ.garage.garage_bucket_key:
    api_url: http://garage.example.com:3903
    api_token: "{{ garage_admin_token }}"
    bucket_alias: my-backups
    access_key_id: "{{ key_result.key.access_key_id }}"
    read: true
    write: true
    state: present

- name: Grant owner permission (full control)
  occ.garage.garage_bucket_key:
    api_url: http://garage.example.com:3903
    api_token: "{{ garage_admin_token }}"
    bucket_alias: my-backups
    access_key_id: "{{ key_result.key.access_key_id }}"
    read: true
    write: true
    owner: true
    state: present

- name: Revoke all permissions from a key
  occ.garage.garage_bucket_key:
    api_url: http://garage.example.com:3903
    api_token: "{{ garage_admin_token }}"
    bucket_alias: my-backups
    access_key_id: GK1234567890abcdef
    read: true
    write: true
    owner: true
    state: absent
'''

RETURN = r'''
bucket:
  description: Updated bucket info including all key permissions.
  returned: when a change was made
  type: dict
  contains:
    id:
      description: Internal bucket ID.
      type: str
    keys:
      description: All keys with access to this bucket.
      type: list
      elements: dict
'''

from ansible.module_utils.basic import AnsibleModule
from ansible_collections.occ.garage.plugins.module_utils.garage_api import (
    GarageAPI,
    GarageAPIError,
    GARAGE_API_ARGS,
)


def _current_perms(bucket_info, access_key_id):
    """Return the current permission dict for a key on a bucket, or all-false."""
    for k in bucket_info.get('keys', []):
        if k.get('accessKeyId') == access_key_id:
            return k.get('permissions', {})
    return {'read': False, 'write': False, 'owner': False}


def run_module():
    argument_spec = dict(
        bucket_id=dict(type='str'),
        bucket_alias=dict(type='str'),
        access_key_id=dict(type='str', required=True),
        read=dict(type='bool', default=False),
        write=dict(type='bool', default=False),
        owner=dict(type='bool', default=False),
        state=dict(type='str', default='present', choices=['present', 'absent']),
    )
    argument_spec.update(GARAGE_API_ARGS)

    module = AnsibleModule(
        argument_spec=argument_spec,
        required_one_of=[['bucket_id', 'bucket_alias']],
        supports_check_mode=True,
    )

    bucket_id = module.params['bucket_id']
    bucket_alias = module.params['bucket_alias']
    access_key_id = module.params['access_key_id']
    want_read = module.params['read']
    want_write = module.params['write']
    want_owner = module.params['owner']
    state = module.params['state']

    if not (want_read or want_write or want_owner):
        module.fail_json(msg='At least one of read, write, or owner must be true.')

    api = GarageAPI(module.params['api_url'], module.params['api_token'], module.params['validate_certs'])

    try:
        # ----------------------------------------------------------
        # Resolve bucket ID from alias when needed
        # ----------------------------------------------------------
        if not bucket_id:
            try:
                bucket_info = api.get_bucket_info(global_alias=bucket_alias)
                bucket_id = bucket_info['id']
            except GarageAPIError as e:
                module.fail_json(msg='Could not resolve bucket alias "{0}": {1}'.format(bucket_alias, e))
        else:
            bucket_info = api.get_bucket_info(bucket_id=bucket_id)

        current = _current_perms(bucket_info, access_key_id)

        # ----------------------------------------------------------
        # Determine which flags actually need changing
        # ----------------------------------------------------------
        perms_to_change = {}
        if want_read:
            desired = (state == 'present')
            if current.get('read', False) != desired:
                perms_to_change['read'] = True
        if want_write:
            desired = (state == 'present')
            if current.get('write', False) != desired:
                perms_to_change['write'] = True
        if want_owner:
            desired = (state == 'present')
            if current.get('owner', False) != desired:
                perms_to_change['owner'] = True

        if not perms_to_change:
            module.exit_json(changed=False)

        if module.check_mode:
            module.exit_json(changed=True)

        # ----------------------------------------------------------
        # Apply the change
        # ----------------------------------------------------------
        if state == 'present':
            result = api.allow_bucket_key(bucket_id, access_key_id, perms_to_change)
        else:
            result = api.deny_bucket_key(bucket_id, access_key_id, perms_to_change)

        module.exit_json(changed=True, bucket={
            'id': result.get('id'),
            'global_aliases': result.get('globalAliases', []),
            'keys': result.get('keys', []),
        })

    except GarageAPIError as e:
        module.fail_json(msg=str(e))


def main():
    run_module()


if __name__ == '__main__':
    main()
