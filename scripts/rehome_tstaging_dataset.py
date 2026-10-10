#!/usr/bin/env python3
"""Move frozen T-staging cohorts into dataset/train, dataset/val, and dataset/test.

Prospective and external hospital trees move as directories. Retrospective
train and val share year folders, so those files move one by one. Every old
path becomes a relative symlink. Frozen CSV bytes are not rewritten.

Files in the 2018-2024 tree that are not on the frozen train or val list move
to data/processed/tstaging_outside_freeze/ so they are not added to train or val.
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "dataset"
FREEZE = DATASET / "task_datasets" / "t_staging" / "wadi_research_freeze_v20260827"
LOG = ROOT / "data" / "metadata" / "path_migration_log.csv"
DATE = "2026-10-10"

TRAIN_TABLE_KEYS = (
    "internal_2018",
    "internal_2019",
    "internal_2020_2023",
    "internal_2024",
)
PROSPECTIVE_TABLE_KEYS = ("internal_2025",)


def load_roles() -> tuple[dict[str, str], dict[str, str]]:
    stems: dict[str, str] = {}
    patients: dict[str, str] = {}
    sources = {
        "train": FREEZE / "development" / "train_maincenter_1062.csv",
        "val": FREEZE / "development" / "dev_maincenter_128.csv",
    }
    for role, path in sources.items():
        with path.open(newline="", encoding="utf-8-sig") as handle:
            for row in csv.DictReader(handle):
                patient = row["patient_id"].strip()
                previous = patients.get(patient)
                if previous and previous != role:
                    raise SystemExit(f"patient {patient} is in both {previous} and {role}")
                patients[patient] = role
                for column in ("image_path", "crop_ui_path", "gt_lesion_mask_path"):
                    value = row.get(column) or ""
                    if not value:
                        continue
                    stem = Path(value).stem
                    previous_stem = stems.get(stem)
                    if previous_stem and previous_stem != role:
                        raise SystemExit(f"stem {stem} is in both {previous_stem} and {role}")
                    stems[stem] = role
    return stems, patients


def role_for_name(name: str, stems: dict[str, str], patients: dict[str, str]) -> str | None:
    stem = Path(name).stem
    if stem.endswith("_overlay"):
        stem = stem[: -len("_overlay")]
    role = stems.get(stem)
    if role:
        return role
    marker = name.rfind("__")
    if marker < 0:
        return None
    token = name[marker + 2 :]
    for suffix in ("-0", "-1", "-2", "-3", "-4", "-5", "-6", "-7", "-8", "-9"):
        if suffix in token:
            token = token.split(suffix, 1)[0]
            break
    token = token.split(".", 1)[0].split("_", 1)[0]
    if len(token) < 5:
        return None
    return patients.get(token)


def append_log(rows: list[tuple[str, str, str, str]]) -> None:
    with LOG.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        for old, new, action, notes in rows:
            writer.writerow([old, new, action, DATE, "yes", notes])


def relink(src: Path, dst: Path) -> str:
    if src.is_symlink():
        return "skip_symlink"
    if not src.exists():
        return "missing"
    if dst.exists() or dst.is_symlink():
        return "dest_exists"
    dst.parent.mkdir(parents=True, exist_ok=True)
    os.rename(src, dst)
    src.symlink_to(os.path.relpath(dst, src.parent))
    return "moved"


def remove_symlink_shell(path: Path) -> None:
    if not path.exists():
        return
    for dirpath, dirnames, filenames in os.walk(path, followlinks=False, topdown=False):
        current = Path(dirpath)
        for name in filenames:
            item = current / name
            if not item.is_symlink():
                raise SystemExit(f"refusing to remove regular file {item}")
            item.unlink()
        for name in dirnames:
            item = current / name
            if item.is_symlink():
                item.unlink()
            elif item.exists() and any(item.iterdir()):
                raise SystemExit(f"refusing to remove non-empty directory {item}")
            elif item.exists():
                item.rmdir()
        if current != path and current.exists():
            current.rmdir()
    if path.exists():
        path.rmdir()


def plan_retrospective(stems: dict[str, str], patients: dict[str, str]) -> list[tuple[Path, Path, str]]:
    base = DATASET / "internal" / "training_2018_2024"
    planned: list[tuple[Path, Path, str]] = []
    for dirpath, _dirnames, filenames in os.walk(base, followlinks=False):
        folder = Path(dirpath)
        for name in filenames:
            src = folder / name
            if src.is_symlink():
                continue
            relative = src.relative_to(base)
            role = role_for_name(name, stems, patients)
            if role in {"train", "val"}:
                dst = DATASET / role / relative
            else:
                dst = ROOT / "data" / "processed" / "tstaging_outside_freeze" / "training_2018_2024" / relative
                role = "outside_freeze"
            planned.append((src, dst, role))
    return planned


def directory_moves() -> list[tuple[Path, Path, str]]:
    moves: list[tuple[Path, Path, str]] = [
        (
            DATASET / "internal" / "prospective_2025",
            DATASET / "test" / "prospective",
            "prospective cohort directory",
        ),
        (
            DATASET / "videos" / "internal" / "prospective_2025",
            DATASET / "test" / "prospective" / "videos",
            "prospective video directory",
        ),
    ]
    external = DATASET / "external"
    for child in sorted(external.iterdir()):
        if not child.is_dir() or child.is_symlink() or child.name.startswith("_"):
            continue
        moves.append(
            (
                child,
                DATASET / "test" / "external" / child.name,
                "external hospital directory",
            )
        )
    videos = DATASET / "videos" / "external"
    if videos.is_dir():
        for child in sorted(videos.iterdir()):
            if not child.is_dir() or child.is_symlink():
                continue
            moves.append(
                (
                    child,
                    DATASET / "test" / "external" / child.name / "videos",
                    "external hospital videos",
                )
            )
    return moves


def table_moves() -> list[tuple[Path, Path, str]]:
    moves: list[tuple[Path, Path, str]] = []
    tables = DATASET / "tables"
    master = tables / "patient_clinical_master.csv"
    if master.exists() and not master.is_symlink():
        moves.append((master, DATASET / "patient_clinical_master.csv", "shared clinical master"))
    for folder_name in ("by_source", "by_queue"):
        folder = tables / folder_name
        if not folder.is_dir():
            continue
        for item in sorted(folder.iterdir()):
            if item.is_symlink() or not item.is_file():
                continue
            key = item.name.split("__", 1)[0].replace(".json", "").replace(".csv", "")
            if key.endswith("_direct_surgery"):
                key = key[: -len("_direct_surgery")]
            if any(key == prefix or key.startswith(prefix + "_") for prefix in TRAIN_TABLE_KEYS):
                dst = DATASET / "train" / "tables" / folder_name / item.name
                note = "retrospective clinical table"
            elif any(key == prefix or key.startswith(prefix + "_") for prefix in PROSPECTIVE_TABLE_KEYS):
                dst = DATASET / "test" / "prospective" / "tables" / folder_name / item.name
                note = "prospective clinical table"
            elif key.startswith("external_"):
                dst = DATASET / "test" / "external" / "tables" / folder_name / item.name
                note = "external clinical table"
            else:
                continue
            moves.append((item, dst, note))
    return moves


def apply_moves(
    moves: list[tuple[Path, Path, str]],
    label: str,
    *,
    log_each: bool,
) -> dict[str, int]:
    counts: dict[str, int] = {}
    log_rows: list[tuple[str, str, str, str]] = []
    for index, (src, dst, note) in enumerate(moves, start=1):
        will_move = src.exists() and not src.is_symlink() and not (dst.exists() or dst.is_symlink())
        if will_move and log_each:
            log_rows.append(
                (
                    str(src.relative_to(ROOT)),
                    str(dst.relative_to(ROOT)),
                    "mv+symlink",
                    note,
                )
            )
            append_log(log_rows[-1:])
        status = relink(src, dst)
        counts[status] = counts.get(status, 0) + 1
        if status == "dest_exists":
            print(f"dest exists, left in place: {src}", file=sys.stderr)
        if index % 10000 == 0:
            print(f"{label}: {index}/{len(moves)}")
    print(f"{label}: {counts} logged {len(log_rows)}")
    return counts


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    stems, patients = load_roles()
    print(f"freeze stems {len(stems)} patients {len(patients)}")
    retrospective = plan_retrospective(stems, patients)
    by_role: dict[str, int] = {}
    for _src, _dst, role in retrospective:
        by_role[role] = by_role.get(role, 0) + 1
    print("retrospective files", by_role)
    directories = directory_moves()
    tables = table_moves()
    print(f"directory moves {len(directories)} table moves {len(tables)}")
    if not args.apply:
        for src, dst, note in directories + tables:
            print(f"PLAN {note}: {src.relative_to(ROOT)} -> {dst.relative_to(ROOT)}")
        return 0

    dataset_dev = os.stat(DATASET).st_dev
    processed = ROOT / "data" / "processed"
    processed.mkdir(parents=True, exist_ok=True)
    if os.stat(processed).st_dev != dataset_dev:
        raise SystemExit("data/processed is not on the same filesystem as dataset")

    append_log(
        [
            (
                "dataset/internal/training_2018_2024",
                "dataset/train|dataset/val|data/processed/tstaging_outside_freeze/training_2018_2024",
                "mv+symlink",
                (
                    "retrospective files split by frozen train 1062 and val 128 stems; "
                    f"planned train {by_role.get('train', 0)}, val {by_role.get('val', 0)}, "
                    f"outside_freeze {by_role.get('outside_freeze', 0)}"
                ),
            )
        ]
    )
    apply_moves(retrospective, "retrospective files", log_each=False)
    apply_moves(directories, "cohort directories", log_each=True)
    apply_moves(tables, "clinical tables", log_each=True)
    for shell in (DATASET / "internal" / "train", DATASET / "internal" / "prospective"):
        remove_symlink_shell(shell)
        print(f"removed symlink shell {shell.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
