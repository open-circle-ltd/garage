#!/usr/bin/python
# -*- coding: utf-8 -*-
# GNU General Public License v2.0+ (see LICENSES/GPL-2.0-or-later.txt)

from __future__ import absolute_import, division, print_function
__metaclass__ = type

DOCUMENTATION = r'''
---
module: garage_key
short_description: Manage Garage S3 access keys
description:
  - Create, update, or delete S3 access keys via the Garage Admin API v2.
  - On creation the module returns C(secret_access_key). This value is only
    available at creation time — subsequent runs will not return it.
  - To look up an existing key, supply either C(key_id) or C(name). When both
    are omitted a new key is always created on C(state=present).
options:
  state:
    description:
      - C(present) ensures the key exists and matches the given parameters.
      - C(absent) ensures the key is deleted.
    type: str
    choices: [present, absent]
    default: present
  key_id:
    description:
      - The access key ID. Use this to target an existing key for update or
        deletion. When omitted with C(state=present) the module will search
        by C(name), and create a new key if none is found.
    type: str
  name:
    description:
      - Human-friendly label for the key. Used to search for an existing key
        when C(key_id) is not provided.
    type: str
  allow_create_bucket:
    description:
      - Whether the key is allowed to create new buckets.
    type: bool
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
  - C(secret_access_key) is only returned when the key is first created.
    Store it immediately (e.g. with C(register)) as it cannot be retrieved
    later.
'''

EXAMPLES = r'''
- name: Create an S3 key allowed to create buckets
  occ.garage.garage_key:
    api_url: http://garage.example.com:3903
    api_token: "{{ garage_admin_token }}"
    name: backup-key
    allow_create_bucket: true
    state: present
  register: key_result

- name: Print the secret (only available on first creation)
  ansible.builtin.debug:
    msg: "ID={{ key_result.key.access_key_id }} SECRET={{ key_result.key.secret_access_key }}"
  when: key_result.key.secret_access_key is not none

- name: Remove a key by ID
  occ.garage.garage_key:
    api_url: http://garage.example.com:3903
    api_token: "{{ garage_admin_token }}"
    key_id: GK1234567890abcdef
    state: absent
'''

RETURN = r'''
key:
  description: Current state of the access key.
  returned: when state=present
  type: dict
  contains:
    access_key_id:
      description: The key's access ID.
      type: str
    secret_access_key:
      description: The secret key. Only populated on initial creation.
      type: str
    name:
      description: Human-friendly label.
      type: str
    allow_create_bucket:
      description: Whether the key may create buckets.
      type: bool
'''

from ansible.module_utils.basic import AnsibleModule
from ansible_collections.occ.garage.plugins.module_utils.garage_api import (
    GarageAPI,
    GarageAPIError,
    GARAGE_API_ARGS,
)


def _key_permissions(allow_create_bucket):
    return {'createBucket': bool(allow_create_bucket)}


def _find_key_by_name(api, name):
    """Return the first key whose name matches exactly, or None."""
    keys = api.list_keys()
    for k in keys:
        if k.get('name') == name:
            return k
    return None


def _normalise(raw):
    """Map API response fields to snake_case for the return value."""
    return {
        'access_key_id': raw.get('accessKeyId'),
        'secret_access_key': raw.get('secretAccessKey'),
        'name': raw.get('name'),
        'allow_create_bucket': (raw.get('permissions') or {}).get('createBucket', False),
    }


def run_module():
    argument_spec = dict(
        state=dict(type='str', default='present', choices=['present', 'absent']),
        key_id=dict(type='str'),
        name=dict(type='str'),
        allow_create_bucket=dict(type='bool'),
    )
    argument_spec.update(GARAGE_API_ARGS)

    module = AnsibleModule(
        argument_spec=argument_spec,
        supports_check_mode=True,
    )

    state = module.params['state']
    key_id = module.params['key_id']
    name = module.params['name']
    allow_create_bucket = module.params['allow_create_bucket']

    api = GarageAPI(module.params['api_url'], module.params['api_token'], module.params['validate_certs'])

    try:
        # ----------------------------------------------------------
        # Resolve existing key
        # ----------------------------------------------------------
        existing = None
        if key_id:
            try:
                existing = api.get_key_info(key_id=key_id)
            except GarageAPIError as e:
                if e.status == 404:
                    existing = None
                else:
                    module.fail_json(msg=str(e))
        elif name:
            match = _find_key_by_name(api, name)
            if match:
                existing = api.get_key_info(key_id=match['id'])

        # ----------------------------------------------------------
        # state=absent
        # ----------------------------------------------------------
        if state == 'absent':
            if existing is None:
                module.exit_json(changed=False)
            if module.check_mode:
                module.exit_json(changed=True)
            api.delete_key(existing['accessKeyId'])
            module.exit_json(changed=True)

        # ----------------------------------------------------------
        # state=present — create
        # ----------------------------------------------------------
        if existing is None:
            if module.check_mode:
                module.exit_json(changed=True, key={
                    'access_key_id': None,
                    'secret_access_key': None,
                    'name': name,
                    'allow_create_bucket': allow_create_bucket,
                })
            perms = _key_permissions(allow_create_bucket) if allow_create_bucket is not None else None
            created = api.create_key(name=name, permissions=perms)
            module.exit_json(changed=True, key=_normalise(created))

        # ----------------------------------------------------------
        # state=present — update if needed
        # ----------------------------------------------------------
        current_create_bucket = (existing.get('permissions') or {}).get('createBucket', False)
        needs_name = name is not None and existing.get('name') != name
        needs_perms = allow_create_bucket is not None and current_create_bucket != allow_create_bucket

        if not needs_name and not needs_perms:
            module.exit_json(changed=False, key=_normalise(existing))

        if module.check_mode:
            module.exit_json(changed=True, key=_normalise(existing))

        updated = api.update_key(
            existing['accessKeyId'],
            name=name if needs_name else None,
            permissions=_key_permissions(allow_create_bucket) if needs_perms else None,
        )
        module.exit_json(changed=True, key=_normalise(updated))

    except GarageAPIError as e:
        module.fail_json(msg=str(e))


def main():
    run_module()


if __name__ == '__main__':
    main()
