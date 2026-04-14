# opencircle.garage

Ansible collection for managing [Garage S3](https://garagehq.deuxfleurs.fr/) via the Garage Admin API v2.

Provides modules to create and manage S3 access keys, buckets, and bucket-key permissions — the same operations you would otherwise run with the `garage` CLI.

## Requirements

- Ansible >= 2.13
- Python >= 3.9
- A running Garage instance with the admin API enabled and an admin token

## Installation

```bash
ansible-galaxy collection install opencircle.garage
```

Or from source:

```bash
git clone https://github.com/open-circle-ltd/garage.git
ansible-galaxy collection install garage/ --force
```

## Authentication

All modules require an admin API token. Generate one with the Garage CLI:

```bash
garage admin-token create --name ansible
```

Pass the token via the `api_token` parameter (mark it `no_log: true` or store it in Vault/an encrypted variable file).

---

## Modules

### `opencircle.garage.garage_key`

Manage S3 access keys.

| Parameter            | Required | Type | Default   | Description                                                                 |
|----------------------|----------|------|-----------|-----------------------------------------------------------------------------|
| `api_url`            | yes      | str  |           | Base URL of the Garage admin API (e.g. `http://localhost:3903`)             |
| `api_token`          | yes      | str  |           | Bearer token for the admin API                                              |
| `state`              | no       | str  | `present` | `present` to create/update, `absent` to delete                              |
| `name`               | no       | str  |           | Human-friendly label. Used to look up an existing key when `key_id` is omitted |
| `key_id`             | no       | str  |           | Exact access key ID. Use to target a specific existing key                  |
| `allow_create_bucket`| no       | bool |           | Whether the key may create new buckets                                      |

**Return value** (`key`):

| Field              | Description                                                      |
|--------------------|------------------------------------------------------------------|
| `access_key_id`    | The key's access ID                                              |
| `secret_access_key`| Secret key — **only populated on initial creation**             |
| `name`             | Human-friendly label                                             |
| `allow_create_bucket` | Whether the key may create buckets                            |

> The `secret_access_key` is returned once on creation. Use `register` and persist it to a secrets manager immediately — it cannot be retrieved again.

---

### `opencircle.garage.garage_bucket`

Manage S3 buckets.

| Parameter                 | Required | Type | Default   | Description                                                        |
|---------------------------|----------|------|-----------|--------------------------------------------------------------------|
| `api_url`                 | yes      | str  |           | Base URL of the Garage admin API                                   |
| `api_token`               | yes      | str  |           | Bearer token for the admin API                                     |
| `state`                   | no       | str  | `present` | `present` to create/update, `absent` to delete                     |
| `name`                    | no*      | str  |           | Global alias for the bucket (the S3 bucket name). Required if `bucket_id` is omitted |
| `bucket_id`               | no*      | str  |           | Internal Garage bucket ID. Required if `name` is omitted           |
| `website_access`          | no       | bool |           | Enable static website hosting                                      |
| `website_index_document`  | no       | str  |           | Index document for website hosting (required when `website_access: true`) |
| `website_error_document`  | no       | str  |           | Custom error document for website hosting                          |
| `quota_max_size`          | no       | int  |           | Maximum total size in bytes. Set to `0` to remove the quota        |
| `quota_max_objects`       | no       | int  |           | Maximum number of objects. Set to `0` to remove the quota          |

*At least one of `name` or `bucket_id` is required.

> `quota_max_size` and `quota_max_objects` must always be set together or not at all (Garage API constraint). To remove quotas set both to `0`.

**Return value** (`bucket`):

| Field             | Description                              |
|-------------------|------------------------------------------|
| `id`              | Internal Garage bucket ID                |
| `global_aliases`  | List of global aliases                   |
| `website_access`  | Whether website hosting is enabled       |
| `quota_max_size`  | Size quota in bytes, or `null`           |
| `quota_max_objects` | Object count quota, or `null`          |
| `objects`         | Current object count                     |
| `bytes`           | Current total size in bytes              |

---

### `opencircle.garage.garage_bucket_key`

Grant or revoke S3 access key permissions on a bucket.

| Parameter      | Required | Type | Default   | Description                                                                   |
|----------------|----------|------|-----------|-------------------------------------------------------------------------------|
| `api_url`      | yes      | str  |           | Base URL of the Garage admin API                                               |
| `api_token`    | yes      | str  |           | Bearer token for the admin API                                                 |
| `state`        | no       | str  | `present` | `present` to grant permissions, `absent` to revoke                            |
| `bucket_id`    | no*      | str  |           | Internal bucket ID. Required if `bucket_alias` is omitted                     |
| `bucket_alias` | no*      | str  |           | Global bucket alias. Required if `bucket_id` is omitted                       |
| `access_key_id`| yes      | str  |           | The access key ID to grant/revoke permissions for                              |
| `read`         | no       | bool | `false`   | Include the `read` permission in the operation                                 |
| `write`        | no       | bool | `false`   | Include the `write` permission in the operation                                |
| `owner`        | no       | bool | `false`   | Include the `owner` permission (full bucket control) in the operation          |

*At least one of `bucket_id` or `bucket_alias` is required. At least one permission flag must be `true`.

The module operates additively: only the flags set to `true` are affected. Unspecified flags are left unchanged.

---

## Example Playbook

The following playbook mirrors the typical manual workflow — create a key, create a bucket, grant the key access:

```yaml
- name: Provision Garage S3 backup storage
  hosts: localhost
  gather_facts: false
  vars:
    garage_api_url: http://garage.example.com:3903
    garage_admin_token: "{{ vault_garage_admin_token }}"

  tasks:
    - name: Create backup access key
      opencircle.garage.garage_key:
        api_url: "{{ garage_api_url }}"
        api_token: "{{ garage_admin_token }}"
        name: backup-key
        allow_create_bucket: false
        state: present
      register: key_result

    - name: Print credentials (only shown on first creation)
      ansible.builtin.debug:
        msg: "ID={{ key_result.key.access_key_id }} SECRET={{ key_result.key.secret_access_key }}"
      when: key_result.key.secret_access_key is not none

    - name: Create backup bucket
      opencircle.garage.garage_bucket:
        api_url: "{{ garage_api_url }}"
        api_token: "{{ garage_admin_token }}"
        name: my-backups
        state: present

    - name: Grant key read+write on the bucket
      opencircle.garage.garage_bucket_key:
        api_url: "{{ garage_api_url }}"
        api_token: "{{ garage_admin_token }}"
        bucket_alias: my-backups
        access_key_id: "{{ key_result.key.access_key_id }}"
        read: true
        write: true
        state: present
```

### With quotas and website hosting

```yaml
- name: Create a public static site bucket with a 10 GiB quota
  opencircle.garage.garage_bucket:
    api_url: "{{ garage_api_url }}"
    api_token: "{{ garage_admin_token }}"
    name: my-static-site
    website_access: true
    website_index_document: index.html
    website_error_document: error.html
    quota_max_size: 10737418240   # 10 GiB
    quota_max_objects: 100000
    state: present
```

### Remove all permissions and delete a bucket

```yaml
- name: Revoke all key permissions
  opencircle.garage.garage_bucket_key:
    api_url: "{{ garage_api_url }}"
    api_token: "{{ garage_admin_token }}"
    bucket_alias: my-backups
    access_key_id: GK1234567890abcdef
    read: true
    write: true
    owner: true
    state: absent

- name: Delete the bucket (must be empty)
  opencircle.garage.garage_bucket:
    api_url: "{{ garage_api_url }}"
    api_token: "{{ garage_admin_token }}"
    name: my-backups
    state: absent
```

---

## License

GNU General Public License v2.0 or later. See [LICENSES/GPL-2.0-or-later.txt](LICENSES/GPL-2.0-or-later.txt).
