===================================
occ_automation.garage Release Notes
===================================

.. contents:: Topics

v1.0.2
======

Release Summary
---------------

Diagnostics release. API responses that are not JSON now produce an actionable error.

Bugfixes
--------

- A non-JSON response body with a 2xx status no longer escapes as an unhandled ``json.decoder.JSONDecodeError`` (``Expecting value: line 1 column 1 (char 0)``). It is raised as a ``GarageAPIError`` reporting the status, request URL, ``Content-Type`` and the first 300 characters of the body, which identifies cases where a proxy, ingress or the S3 endpoint answered instead of the Garage admin API.
- Connection failures now name the request URL alongside the underlying reason.

v1.0.1
======

Release Summary
---------------

Bugfix release completing the rename to the ``occ_automation`` namespace.

Bugfixes
--------

- Fixed the ``module_utils`` imports in all modules, which still referenced the pre-rename ``occ.garage`` collection and caused ``unable to locate collection occ.garage`` at task runtime.
- Updated the FQCNs in the module ``EXAMPLES`` blocks to ``occ_automation.garage.*``.

v1.0.0
======

Release Summary
---------------

Initial release. Provides modules to manage Garage S3 keys, buckets, and bucket-key permissions via the Garage Admin API v2.

New Modules
-----------

- ``occ_automation.garage.garage_key`` - Manage S3 access keys.
- ``occ_automation.garage.garage_bucket`` - Manage S3 buckets.
- ``occ_automation.garage.garage_bucket_key`` - Grant or revoke S3 access key permissions on a bucket.
