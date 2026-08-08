# Project Changelog

This file records material project changes, their validation, and deployment state. Do not add patient identifiers, credentials, tokens, private URLs, or sensitive clinical data.

## 2026-08-09, Complete mask editing and persistence

- Scope: `apps/gastric_scan_next` mask editing, video tracking persistence, mask history, and remote Next deployment.
- Reason: Ensure doctors can edit lesion, wall, lumen, and tracked video-frame masks, then preserve the complete result after tracking.
- Key changes: Added mask history storage and restore UI, automatic saves for doctor edits and tracking completion, validation for wall, lumen, and frame boxes, and a serialized save queue so a final tracking save is not dropped behind an earlier edit save.
- Validation: TypeScript check, ESLint, isolated production build, local history API smoke test, and remote service health check.
- Deployment: The remote `gastric-next` service was updated atomically. The previous release was retained for rollback, and the public bundle excluded internal data, logs, and public video assets.
- Follow-up: Continue manual browser verification of freehand, lasso, positive and negative point editing, and history restore with a logged-in reader account.

## 2026-08-09, Complete video-frame snapshots

- Scope: `VideoMaskFrameOverride`, video tracking frame mapping, mask persistence normalization, and frame validation.
- Reason: Make the saved `video_frames` data explicitly complete for review and restoration.
- Key changes: Preserve tracker-provided frame indices, retain lesion segmentation with `roi_bbox`, retain lumen segmentation with `lumen_bbox`, and derive missing boxes from saved polygons before validation and response.
- Validation: TypeScript check, ESLint, production build, and mask history API smoke test.

## 2026-08-09, On-demand history viewing

- Scope: Interactive mask history panel and saved-lumen messaging.
- Reason: Keep historical versions closed and unloaded at case start while allowing doctors to inspect and restore them on demand.
- Key changes: Removed the automatic saved-lumen notification, hid history counts while the panel is closed, added viewable snapshot summaries for lesion and lumen masks and boxes, kept the panel open after restore, and refreshed the list after restore.
- Follow-up: Confirm the view and restore flow with a logged-in browser session.
