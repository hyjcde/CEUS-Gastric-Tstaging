---
description: Run repo path and root checks after structural changes. Use when moving files, updating registries, or user asks to verify repository layout.
disable-model-invocation: true
allowed-tools: Bash Read
---

## Verify repository

Run from repo root:

!`python scripts/check_repo_root.py 2>&1; echo "---"; python scripts/verify_repo_paths.py 2>&1`

If either fails, summarize errors and point to `MAINTENANCE.md` / `data/metadata/path_migration_log.csv`.

If user changed scripts or registries, also suggest:

```bash
python scripts/build_script_registry.py
python scripts/build_asset_manifest.py
```

Do not auto-fix failures without user confirmation.
