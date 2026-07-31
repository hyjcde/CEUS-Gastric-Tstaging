# Direct-surgery video dataset v1

This is the dataset contract for the internal direct-surgery video corpus. It is a metadata entry point, not a second copy of the raw videos.

## Raw source

- `data/raw/legacy_gastric_staging/协和内部数据集/直接手术/`
- Original videos are immutable and remain outside Git.
- Canonical cohorts: `2018直接手术/`, `2024年直接手术/`, `2025直接手术/`.

## Registries

- `../video_assets_registry.csv` — video-level source and size registry.
- `../patient_media_registry.csv` — patient-level image/video linkage.
- `../video_tstaging_protocol/` — frozen dev/external/prospective evaluation queues.
- `../../metadata/mac_direct_surgery_video_20260731/` — Mac subset inventory.

## Derived data boundary

Derived frames, UI-cropped outputs, re-encoded videos and QC artifacts belong under:

`data/processed/direct_surgery_video/`

Every derived file must retain `source_video`, `processing_version`, `crop_profile`, and `qc_status`. No derived output may overwrite `data/raw/`.

## Current status

- Workstation internal raw videos: 1,736.
- Mac subset audited against workstation: 1,598/1,598 matched by basename and byte size.
- Patient-level and split registries exist on the workstation.
- Full-corpus UI-crop pipeline is not yet accepted.
- Do not call the UI-cropped or frame subset a training set until QC and patient-level split checks pass.
