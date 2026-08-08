# Project Changelog

This file records material project changes, their validation, and deployment state. Do not add patient identifiers, credentials, tokens, private URLs, or sensitive clinical data.

## 2026-08-09, Complete mask editing and persistence

- Scope: `apps/gastric_scan_next` mask editing, video tracking persistence, mask history, and remote Next deployment.
- Reason: Ensure doctors can edit lesion, wall, lumen, and tracked video-frame masks, then preserve the complete result after tracking.
- Key changes: Added mask history storage and restore UI, automatic saves for doctor edits and tracking completion, validation for wall, lumen, and frame boxes, and a serialized save queue so a final tracking save is not dropped behind an earlier edit save.
- Validation: TypeScript check, ESLint, isolated production build, local history API smoke test, and remote service health check.
- Deployment: The remote `gastric-next` service was updated atomically. The previous release was retained for rollback, and the public bundle excluded internal data, logs, and public video assets.
- Follow-up: Continue manual browser verification of freehand, lasso, positive and negative point editing, and history restore with a logged-in reader account.
