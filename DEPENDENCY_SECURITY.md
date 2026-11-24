# Dependency security review — 7 November 2026

The release uses `backend/requirements.lock` and npm lockfiles. Runtime patches
are regression-tested before the release lock is regenerated. The application
uses PyJWT for token verification; python-jose and its unused ecdsa dependency
are removed from the clean release environment.

Chroma 1.5.9 has four reviewed server-path advisories without a published fix:
PYSEC-2026-311, PYSEC-2026-3814, PYSEC-2026-3815 and PYSEC-2026-3813.
These concern Chroma server collection endpoints and server authorization.
JobPilot creates only an in-process PersistentClient; it does not run a Chroma
HTTP server, expose those routes, accept model repositories from clients, or
enable remote model code. Optional model preparation requires a pinned revision,
and inference uses local files with remote code disabled.

`scripts/check_audit.py` accepts only these exact advisory IDs for this exact
package version, until 7 December 2026. New findings, other packages, other
versions and an expired review fail CI. This is a reachability assessment,
not a claim that the package is vulnerability-free. Recheck before deployment;
upgrade/remove Chroma when an appropriate fix is available. Do not enable a
Chroma network service under this exception.

Reviewed advisory records: [model repository injection](https://github.com/advisories/GHSA-f4j7-r4q5-qw2c),
[collection update injection](https://github.com/advisories/GHSA-36p7-vc44-83pf),
[RBAC scope](https://github.com/advisories/GHSA-xph7-9rjv-w5fr),
[collection authorization](https://github.com/advisories/GHSA-2wm9-hf6c-p5cr).
The non-reachability conclusion is an assessment of JobPilot's code and deployment
shape, not an upstream fix. Re-evaluate it if exposed routes or model loading change.

The baseline lock has 165 exact distributions; clean-environment `pip check` passes.
Frontend/extension npm audits returned zero findings on 7 November. Optional ML
dependencies are outside the baseline image: a dry-run resolves successfully, but
they still need platform-specific locking/auditing before experiments are enabled.
