"""方案 6.2: TabPFN 只读临床，一行一个患者，不看 1152 维影像。

公式: [z_image, TabPFN(clinical)] -> MLP。
这里只产生 TabPFN(clinical): 临床 11 项（缺失为 NaN）-> 4 类概率。
训练患者用 5-fold OOF，验证 / 前瞻 / 外部用全训练集 fit 一次再 query。
影像与概率的拼接在 train.PatientHead（--head tabpfn）。
TIME-192 / tabpfn_both 是方案 6.2 的另一读法，不是原文。
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from sklearn.model_selection import StratifiedKFold

from .constants import CACHE_DIR, CLINICAL_FIELDS, N_CLASSES, PREOP_DROP_FIELDS

CAT_FIELDS = ("sex", "lauren_type", "differentiation", "tumor_location", "cea_binary", "ca199_binary")
TABPFN_CACHE = CACHE_DIR / "tabpfn_clin11_oof.npz"


def clinical22_to_nan11(clinical: np.ndarray) -> np.ndarray:
    """把仓库 22 个数（norm+missing）还原成 TabPFN 用的 11 维，缺失为 NaN。"""
    vec = np.asarray(clinical, dtype=np.float32).reshape(-1)
    if vec.size != 22:
        raise ValueError(f"clinical_22 must have 22 numbers, got {vec.size}")
    out = np.zeros(11, dtype=np.float32)
    for i in range(11):
        norm = float(vec[2 * i])
        missing = float(vec[2 * i + 1])
        out[i] = np.nan if missing >= 0.5 else norm
    return out


def _make_tabpfn(device: str, n_estimators: int, seed: int):
    from tabpfn import TabPFNClassifier
    from tabpfn.constants import ModelVersion

    cat_idx = [CLINICAL_FIELDS.index(name) for name in CAT_FIELDS]
    return TabPFNClassifier.create_default_for_version(
        ModelVersion.V2_5,
        device=device,
        random_state=seed,
        n_estimators=n_estimators,
        balance_probabilities=True,
        ignore_pretraining_limits=True,
        memory_saving_mode="auto",
        categorical_features_indices=cat_idx,
        show_progress_bar=False,
    )


def _align_proba(model, raw: np.ndarray) -> np.ndarray:
    out = np.zeros((len(raw), N_CLASSES), dtype=np.float32)
    classes = getattr(model, "classes_", np.arange(raw.shape[1]))
    for src, cls in enumerate(classes):
        idx = int(cls)
        if 0 <= idx < N_CLASSES:
            out[:, idx] = raw[:, src]
    return out


def _patient_table(
    npz_path: Path,
    drop_fields: tuple[str, ...] = (),
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    with np.load(npz_path, allow_pickle=True) as data:
        pids = np.asarray(data["patient_id"]).astype(str)
        clinical = np.asarray(data["clinical"])
        labels = np.asarray(data["label"])
    by_pid: dict[str, dict[str, list]] = {}
    for i, pid in enumerate(pids):
        rec = by_pid.setdefault(pid, {"clin": [], "y": []})
        rec["clin"].append(clinical[i])
        rec["y"].append(int(labels[i]))
    ordered = sorted(by_pid)
    drop_idx = [CLINICAL_FIELDS.index(name) for name in drop_fields]
    rows = []
    for pid in ordered:
        vec = clinical22_to_nan11(np.mean(by_pid[pid]["clin"], axis=0))
        for idx in drop_idx:
            vec[idx] = np.nan
        rows.append(vec)
    x = np.stack(rows, axis=0)
    y = np.asarray([int(max(set(by_pid[pid]["y"]), key=by_pid[pid]["y"].count)) for pid in ordered], dtype=np.int64)
    return np.asarray(ordered), x, y


def build_tabpfn_cache(
    cache_dir: Path = CACHE_DIR,
    device: str = "cpu",
    n_estimators: int = 8,
    folds: int = 5,
    seed: int = 20260821,
    force: bool = False,
) -> Path:
    """方案 6.2: 缓存患者级 4 类概率。训练=OOF，其余 split=train-fit。"""
    out = cache_dir / "tabpfn_clin11_oof.npz"
    if out.is_file() and not force:
        return out
    cache_dir.mkdir(parents=True, exist_ok=True)
    train_pids, x_train, y_train = _patient_table(cache_dir / "train_embeddings.npz")
    oof = np.zeros((len(train_pids), N_CLASSES), dtype=np.float32)
    kf = StratifiedKFold(n_splits=folds, shuffle=True, random_state=seed)
    print(f"tabpfn clin11 OOF folds={folds} n={len(train_pids)}", flush=True)
    for fold, (tr, te) in enumerate(kf.split(x_train, y_train), start=1):
        print(f"tabpfn fold {fold}/{folds}", flush=True)
        clf = _make_tabpfn(device, n_estimators, seed + fold)
        clf.fit(x_train[tr], y_train[tr])
        oof[te] = _align_proba(clf, clf.predict_proba(x_train[te]))
    full = _make_tabpfn(device, n_estimators, seed)
    full.fit(x_train, y_train)
    all_pids = [train_pids]
    all_split = [np.full(len(train_pids), "train")]
    all_proba = [oof]
    for split in ("val", "test_prospective", "test_external"):
        path = cache_dir / f"{split}_embeddings.npz"
        if not path.is_file():
            continue
        pids, x, _y = _patient_table(path)
        print(f"tabpfn {split} n={len(pids)}", flush=True)
        proba = _align_proba(full, full.predict_proba(x))
        all_pids.append(pids)
        all_split.append(np.full(len(pids), split))
        all_proba.append(proba)
    np.savez_compressed(
        out,
        patient_id=np.concatenate(all_pids),
        split=np.concatenate(all_split),
        proba=np.concatenate(all_proba, axis=0),
        fields=np.asarray(CLINICAL_FIELDS),
        meta=json.dumps(
            {
                "model": "TabPFN-2.5",
                "input": "clinical-11 with NaN for missing",
                "output": "4-class OOF/train-fit probabilities",
                "folds": folds,
                "n_estimators": n_estimators,
            }
        ),
    )
    return out


def load_tabpfn_map(cache_dir: Path = CACHE_DIR) -> dict[str, np.ndarray]:
    path = cache_dir / "tabpfn_clin11_oof.npz"
    with np.load(path, allow_pickle=True) as data:
        pids = np.asarray(data["patient_id"]).astype(str)
        proba = np.asarray(data["proba"], dtype=np.float32)
    return {pid: proba[i] for i, pid in enumerate(pids)}


TIME192_CACHE = "tabpfn_clin11_time192.npz"
TIME192_PREOP_CACHE = "tabpfn_clin11_time192_preop.npz"


def _mean_embed(raw) -> np.ndarray:
    arr = np.asarray(raw, dtype=np.float32)
    if arr.ndim == 3:
        arr = arr.mean(axis=0)
    return arr


def build_time192_cache(
    cache_dir: Path = CACHE_DIR,
    device: str = "cpu",
    n_estimators: int = 8,
    folds: int = 5,
    seed: int = 20260821,
    force: bool = False,
    drop_fields: tuple[str, ...] = (),
    cache_name: str | None = None,
) -> Path:
    """Official TabPFNEmbedding OOF tokens. Dim is 192 in TabPFN-2.5 / TIME."""
    out = cache_dir / (cache_name or TIME192_CACHE)
    if out.is_file() and not force:
        return out
    from tabpfn import TabPFNClassifier
    from tabpfn.constants import ModelVersion
    from tabpfn_extensions.embedding import TabPFNEmbedding

    train_pids, x_train, y_train = _patient_table(
        cache_dir / "train_embeddings.npz",
        drop_fields=drop_fields,
    )
    tag = "preop " if drop_fields else ""
    print(f"tabpfn TIME-192 {tag}n_train={len(train_pids)} folds={folds}", flush=True)
    model = TabPFNClassifier.create_default_for_version(
        ModelVersion.V2_5,
        device=device,
        random_state=seed,
        n_estimators=n_estimators,
        balance_probabilities=True,
        ignore_pretraining_limits=True,
        memory_saving_mode="auto",
        categorical_features_indices=[CLINICAL_FIELDS.index(name) for name in CAT_FIELDS],
        show_progress_bar=False,
    )
    extractor = TabPFNEmbedding(n_fold=folds, shuffle=True, random_state=seed, model=model)
    train_e = _mean_embed(extractor.fit_transform(x_train, y_train))
    all_pids = [train_pids]
    all_split = [np.full(len(train_pids), "train")]
    all_emb = [train_e]
    for split in ("val", "test_prospective", "test_external"):
        path = cache_dir / f"{split}_embeddings.npz"
        if not path.is_file():
            continue
        pids, x, _y = _patient_table(path, drop_fields=drop_fields)
        print(f"tabpfn TIME-192 {split} n={len(pids)} d={train_e.shape[1]}", flush=True)
        emb = _mean_embed(extractor.transform(x))
        all_pids.append(pids)
        all_split.append(np.full(len(pids), split))
        all_emb.append(emb)
    stacked = np.concatenate(all_emb, axis=0).astype(np.float32)
    np.savez_compressed(
        out,
        patient_id=np.concatenate(all_pids),
        split=np.concatenate(all_split),
        embedding=stacked,
        fields=np.asarray(CLINICAL_FIELDS),
        meta=json.dumps(
            {
                "model": "TabPFN-2.5 TabPFNEmbedding",
                "input": "clinical-11 with NaN for missing"
                + (f"; dropped {','.join(drop_fields)}" if drop_fields else ""),
                "output": f"{stacked.shape[1]}-d OOF/train-fit TIME token",
                "folds": folds,
                "n_estimators": n_estimators,
            }
        ),
    )
    return out


def load_time192_map(cache_dir: Path = CACHE_DIR, cache_name: str = TIME192_CACHE) -> dict[str, np.ndarray]:
    path = cache_dir / cache_name
    with np.load(path, allow_pickle=True) as data:
        pids = np.asarray(data["patient_id"]).astype(str)
        emb = np.asarray(data["embedding"], dtype=np.float32)
    return {pid: emb[i] for i, pid in enumerate(pids)}


def time192_dim(cache_dir: Path = CACHE_DIR, cache_name: str = TIME192_CACHE) -> int:
    path = cache_dir / cache_name
    with np.load(path, allow_pickle=True) as data:
        return int(np.asarray(data["embedding"]).shape[1])


def load_tabpfn_both_map(cache_dir: Path = CACHE_DIR) -> dict[str, np.ndarray]:
    """Frozen plan 6.2 vector: TIME-192 plus 4-class OOF. Image tokens stay out."""
    time_map = load_time192_map(cache_dir, cache_name=TIME192_CACHE)
    proba_map = load_tabpfn_map(cache_dir)
    common = sorted(set(time_map) & set(proba_map))
    return {
        pid: np.concatenate([time_map[pid], proba_map[pid]], axis=0).astype(np.float32)
        for pid in common
    }
