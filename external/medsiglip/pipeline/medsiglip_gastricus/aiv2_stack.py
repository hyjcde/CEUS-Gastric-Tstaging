"""AI-v2 E1-E3: patient-level OOF ensembles. Situation A: never fit or select on held-out.

Members: default (4.1x5.3x6.1), best (5.1x6.2), clinical_only TabPFN.
Stacker weights are fit on train 5-fold OOF only. Held-out numbers are reported after lock.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import numpy as np
import torch
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedKFold
from torch.optim.lr_scheduler import LambdaLR
from torch.utils.data import DataLoader

from .constants import (
    AIV2_REPORT_DIR,
    CACHE_DIR,
    CLASS_NAMES,
    N_CLASSES,
    PLAN_COMPLETE_REPORT_DIR,
)
from .metrics import confusion, md_confusion, score_arrays
from .model import GastricUSFromScratch
from .tabpfn_clinical import (
    _align_proba,
    _make_tabpfn,
    _patient_table,
    load_tabpfn_map,
)
from .train import (
    PatientBagDataset,
    _clinical_batch,
    _cosine_warmup,
    _jsonable,
    collate,
    ordinal_rank_loss,
)

FOLDS = 5
FOLD_SEED = 20260821
MEMBERS = ("default", "best", "clinical_only")
MEMBER_SPEC = {
    "default": {"head": "mlp", "fusion": "concat", "pool": "gated", "clinical_dim": 22, "pool_proj": True},
    "best": {"head": "tabpfn", "fusion": "concat", "pool": "mean_views", "clinical_dim": 4, "pool_proj": False},
}
FULL_CKPT = {
    "default": PLAN_COMPLETE_REPORT_DIR / "mlp_concat_gated" / "best_model.pt",
    "best": PLAN_COMPLETE_REPORT_DIR / "tabpfn_concat_mean" / "best_model.pt",
}
E1_COMBOS = (
    ("best", "default"),
    ("best", "clinical_only"),
    ("best", "default", "clinical_only"),
)


def _train_ids() -> tuple[np.ndarray, np.ndarray]:
    pids, _x, y = _patient_table(CACHE_DIR / "train_embeddings.npz")
    return pids, y


def _folds(pids: np.ndarray, y: np.ndarray) -> list[tuple[np.ndarray, np.ndarray]]:
    kf = StratifiedKFold(n_splits=FOLDS, shuffle=True, random_state=FOLD_SEED)
    return list(kf.split(np.zeros(len(pids)), y))


def _tabpfn_on_pids(
    fit_pids: set[str],
    device: str,
    seed: int,
) -> dict[str, np.ndarray]:
    all_pids, x, y = _patient_table(CACHE_DIR / "train_embeddings.npz")
    index = {pid: i for i, pid in enumerate(all_pids)}
    fit_idx = np.asarray([index[pid] for pid in sorted(fit_pids) if pid in index], dtype=int)
    clf = _make_tabpfn(device, 8, seed)
    clf.fit(x[fit_idx], y[fit_idx])
    out = {}
    for split in ("train", "val", "test_prospective", "test_external"):
        pids, xx, _y = _patient_table(CACHE_DIR / f"{split}_embeddings.npz")
        proba = _align_proba(clf, clf.predict_proba(xx))
        for pid, row in zip(pids, proba):
            out[str(pid)] = row.astype(np.float32)
    return out


@torch.no_grad()
def _predict(model, loader, device: str, clinical_dim: int, clinical: str) -> dict[str, np.ndarray]:
    model.eval()
    ys, pids, logits_all = [], [], []
    for batch in loader:
        logits = model(
            batch["e_full"].to(device),
            batch["e_roi"].to(device),
            batch["valid"].to(device),
            _clinical_batch(batch, device, clinical_dim, clinical=clinical),
        )
        logits_all.append(logits.detach().cpu().numpy())
        ys.extend(batch["label"].cpu().numpy().astype(int).tolist())
        pids.extend(batch["patient_id"])
    logits = np.concatenate(logits_all, axis=0)
    proba = torch.softmax(torch.from_numpy(logits), dim=-1).numpy().astype(np.float32)
    return {
        "patient_id": np.asarray(pids).astype(str),
        "y": np.asarray(ys, dtype=int),
        "pred": proba.argmax(axis=1).astype(int),
        "proba": proba,
        "logits": logits.astype(np.float32),
    }


def _loader(split: str, keep_pids: set[str] | None, tabpfn_map, batch_size: int, seed: int) -> DataLoader:
    return DataLoader(
        PatientBagDataset(
            CACHE_DIR / f"{split}_embeddings.npz",
            max_frames=16,
            tabpfn_map=tabpfn_map,
            seed=seed,
            keep_pids=keep_pids,
        ),
        batch_size=batch_size,
        shuffle=split == "train" and keep_pids is not None,
        collate_fn=collate,
    )


def _train_member(
    name: str,
    train_pids: set[str],
    device: str,
    seed: int,
    tabpfn_map,
    epochs: int = 80,
    batch_size: int = 16,
    lr: float = 2e-4,
) -> torch.nn.Module:
    spec = MEMBER_SPEC[name]
    train_loader = _loader("train", train_pids, tabpfn_map if spec["head"] == "tabpfn" else None, batch_size, seed)
    val_loader = _loader("val", None, tabpfn_map if spec["head"] == "tabpfn" else None, batch_size, seed)
    model = GastricUSFromScratch(
        clinical_dim=int(spec["clinical_dim"]),
        fusion=str(spec["fusion"]),
        pool=str(spec["pool"]),
        size="xlarge",
        residual=True,
        pool_proj=bool(spec["pool_proj"]),
    ).to(device)
    opt = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=2e-4)
    scheduler = LambdaLR(opt, lambda epoch: _cosine_warmup(epoch, epochs, 8))
    labels = train_loader.dataset.labels()
    counts = Counter(labels)
    weights = [len(labels) / (N_CLASSES * max(counts.get(i, 1), 1)) for i in range(N_CLASSES)]
    loss_fn = torch.nn.CrossEntropyLoss(
        weight=torch.tensor(weights, dtype=torch.float32, device=device),
        label_smoothing=0.05,
    )
    best_acc = -1.0
    best_state = None
    stale = 0
    torch.manual_seed(seed)
    np.random.seed(seed)
    print(f"aiv2-oof {name} n_train={len(train_pids)} seed={seed}", flush=True)
    for epoch in range(1, epochs + 1):
        model.train()
        for batch in train_loader:
            opt.zero_grad(set_to_none=True)
            labels_b = batch["label"].to(device)
            logits = model(
                batch["e_full"].to(device),
                batch["e_roi"].to(device),
                batch["valid"].to(device),
                _clinical_batch(batch, device, int(spec["clinical_dim"])),
            )
            loss = loss_fn(logits, labels_b) + 0.5 * ordinal_rank_loss(logits, labels_b)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step()
        scheduler.step()
        val = _predict(model, val_loader, device, int(spec["clinical_dim"]), "raw")
        acc = float(np.mean(val["y"] == val["pred"]))
        if acc > best_acc:
            best_acc = acc
            best_state = {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}
            stale = 0
        else:
            stale += 1
            if stale >= 25:
                print(f"aiv2-oof {name} stop epoch={epoch} val_acc={best_acc:.4f}", flush=True)
                break
    model.load_state_dict(best_state)
    return model


def _clinical_only_block() -> dict[str, dict[str, np.ndarray]]:
    mapping = load_tabpfn_map(CACHE_DIR)
    out = {}
    for split in ("train", "val", "test_prospective", "test_external"):
        pids, _x, y = _patient_table(CACHE_DIR / f"{split}_embeddings.npz")
        proba = np.stack([mapping[str(pid)] for pid in pids], axis=0)
        out[split] = {
            "patient_id": np.asarray(pids).astype(str),
            "y": y.astype(int),
            "pred": proba.argmax(axis=1).astype(int),
            "proba": proba.astype(np.float32),
        }
    return out


def _dump_full_member(name: str, device: str) -> dict[str, dict[str, np.ndarray]]:
    spec = MEMBER_SPEC[name]
    ckpt = torch.load(FULL_CKPT[name], map_location=device, weights_only=False)
    tabpfn_map = load_tabpfn_map(CACHE_DIR) if spec["head"] == "tabpfn" else None
    model = GastricUSFromScratch(
        clinical_dim=int(spec["clinical_dim"]),
        fusion=str(spec["fusion"]),
        pool=str(spec["pool"]),
        size="xlarge",
        residual=True,
        pool_proj=bool(spec["pool_proj"]),
    ).to(device)
    model.load_state_dict(ckpt["model"])
    out = {}
    for split in ("val", "test_prospective", "test_external"):
        loader = _loader(split, None, tabpfn_map, 16, FOLD_SEED)
        out[split] = _predict(model, loader, device, int(spec["clinical_dim"]), "raw")
    return out


def _align_by_pid(blocks: dict[str, dict[str, np.ndarray]]) -> tuple[np.ndarray, dict[str, np.ndarray]]:
    names = list(blocks)
    pid_sets = [set(blocks[n]["patient_id"].tolist()) for n in names]
    keep = sorted(set.intersection(*pid_sets))
    y0 = None
    proba = {}
    for name in names:
        order = {pid: i for i, pid in enumerate(blocks[name]["patient_id"].tolist())}
        idx = np.asarray([order[pid] for pid in keep], dtype=int)
        yy = blocks[name]["y"][idx]
        if y0 is None:
            y0 = yy
        elif not np.array_equal(y0, yy):
            raise ValueError(f"label mismatch for {name}")
        proba[name] = blocks[name]["proba"][idx]
    return y0, proba


def _score(y: np.ndarray, pred: np.ndarray) -> dict[str, float]:
    return score_arrays(y, pred)


def _e1(probas: list[np.ndarray]) -> np.ndarray:
    return np.mean(np.stack(probas, axis=0), axis=0)


def _e2(y: np.ndarray, members: list[np.ndarray]) -> tuple[np.ndarray, np.ndarray]:
    stacked = np.stack(members, axis=0)
    n_m = stacked.shape[0]

    def nll(raw: np.ndarray) -> float:
        w = np.exp(raw - raw.max())
        w = w / w.sum()
        p = np.clip(np.tensordot(w, stacked, axes=(0, 0)), 1e-8, 1.0)
        return float(-np.mean(np.log(p[np.arange(len(y)), y])))

    best_w = np.ones(n_m) / n_m
    best = nll(np.zeros(n_m))
    rng = np.random.default_rng(FOLD_SEED)
    for _ in range(200):
        cand = rng.normal(size=n_m)
        val = nll(cand)
        if val < best:
            best = val
            w = np.exp(cand - cand.max())
            best_w = w / w.sum()
    p = np.clip(np.tensordot(best_w, stacked, axes=(0, 0)), 1e-8, 1.0)
    return best_w.astype(np.float32), p.astype(np.float32)


def _e3(y: np.ndarray, members: list[np.ndarray]) -> tuple[LogisticRegression, np.ndarray]:
    x = np.concatenate([np.log(np.clip(p, 1e-6, 1.0)) for p in members], axis=1)
    clf = LogisticRegression(
        penalty="l2",
        C=0.5,
        max_iter=400,
        class_weight="balanced",
        solver="lbfgs",
    )
    clf.fit(x, y)
    return clf, clf.predict_proba(x).astype(np.float32)


def _apply_e3(clf: LogisticRegression, members: list[np.ndarray]) -> np.ndarray:
    x = np.concatenate([np.log(np.clip(p, 1e-6, 1.0)) for p in members], axis=1)
    return clf.predict_proba(x).astype(np.float32)


def _temperature(y: np.ndarray, proba: np.ndarray) -> float:
    logits = np.log(np.clip(proba, 1e-6, 1.0))

    def nll(t: float) -> float:
        z = logits / max(t, 0.05)
        z = z - z.max(axis=1, keepdims=True)
        p = np.exp(z)
        p = p / p.sum(axis=1, keepdims=True)
        return float(-np.mean(np.log(np.clip(p[np.arange(len(y)), y], 1e-8, 1.0))))

    grid = np.linspace(0.5, 3.0, 26)
    return float(min(grid, key=nll))


def _apply_temp(proba: np.ndarray, temp: float) -> np.ndarray:
    logits = np.log(np.clip(proba, 1e-6, 1.0)) / max(temp, 0.05)
    logits = logits - logits.max(axis=1, keepdims=True)
    p = np.exp(logits)
    return (p / p.sum(axis=1, keepdims=True)).astype(np.float32)


def _oracle(y: np.ndarray, a: np.ndarray, b: np.ndarray) -> dict[str, float]:
    pa, pb = a.argmax(1), b.argmax(1)
    return {
        "both_right": float(np.mean((pa == y) & (pb == y))),
        "both_wrong": float(np.mean((pa != y) & (pb != y))),
        "a_only": float(np.mean((pa == y) & (pb != y))),
        "b_only": float(np.mean((pa != y) & (pb == y))),
        "oracle": float(np.mean((pa == y) | (pb == y))),
    }


def _fmt(x: float, d: int = 4) -> str:
    return f"{x:.{d}f}"


def _write_report(dest: Path, payload: dict) -> str:
    oof = payload["oof_scores"]
    held = payload["heldout"]
    lines = [
        "# AI-v2 E1-E3 OOF 集成（情况 A）",
        "",
        "前瞻 425 / 外部 485 **不进训练、不参与选模**。集成权重只看训练 1062 人的 5 折患者级 OOF。",
        "成员：default、best、clinical_only。不要把这里的持有集数字当成选模依据。",
        "",
        "## 训练 OOF 成员",
        "",
        "| 成员 | OOF ACC | T2 | T3 | off2 |",
        "|------|--------:|---:|---:|-----:|",
    ]
    for name in MEMBERS:
        s = oof[name]
        lines.append(f"| {name} | {_fmt(s['acc'])} | {_fmt(s['recall_T2'], 3)} | {_fmt(s['recall_T3'], 3)} | {_fmt(s['off2'], 3)} |")
    lines += ["", "## 互补（训练 OOF）", ""]
    lines += ["| A vs B | 都对 | 都错 | 仅 A | 仅 B | oracle |", "|--------|-----:|-----:|-----:|-----:|-------:|"]
    for key, row in payload["oracle"].items():
        lines.append(
            f"| {key} | {_fmt(row['both_right'])} | {_fmt(row['both_wrong'])} | "
            f"{_fmt(row['a_only'])} | {_fmt(row['b_only'])} | {_fmt(row['oracle'])} |"
        )
    lines += ["", "## 集成器（用 OOF 锁定，再往持有集上套）", ""]
    lines += [
        "| 模型 | 选模面 | ACC | T2 | T3 | off2 |",
        "|------|--------|----:|---:|---:|-----:|",
    ]
    for name, block in payload["stackers"].items():
        s = block["oof"]
        lines.append(
            f"| {name} | train OOF | {_fmt(s['acc'])} | {_fmt(s['recall_T2'], 3)} | "
            f"{_fmt(s['recall_T3'], 3)} | {_fmt(s['off2'], 3)} |"
        )
    lines += ["", "## 持有集（锁模后报告，不回头改权重）", ""]
    lines += [
        "| 模型 | 前瞻 ACC | 前瞻 T2 / T3 | 外部 ACC | 外部 T2 / T3 |",
        "|------|--------:|-------------:|--------:|-------------:|",
    ]
    for name, block in held.items():
        p, e = block["test_prospective"], block["test_external"]
        lines.append(
            f"| {name} | {_fmt(p['acc'])} | {_fmt(p['recall_T2'], 3)} / {_fmt(p['recall_T3'], 3)} | "
            f"{_fmt(e['acc'])} | {_fmt(e['recall_T2'], 3)} / {_fmt(e['recall_T3'], 3)} |"
        )
    lines += [
        "",
        "## 锁模门槛对照",
        "",
        "- 四类 ACC 不低于当前 best 单点，或 ACC 掉不超过 0.005 但 T2 / off2 明显更好。",
        "- T2 召回至少回到 default OOF，或前瞻不低于 0.20，且不能靠把 T3 大量报成 T2。",
        "- 不在前瞻 / 外部上挑种子或挑集成器。",
        "",
        "## 能说 / 不能说",
        "",
        "- 能说：这是情况 A 下的 OOF 集成，成员在 T2 / T3 上是否互补。",
        "- 不能说：已经到 0.75。选中了某个集成器当 CLI。人机研究可以拿当前前瞻/外部再训一版。",
        "",
    ]
    text = "\n".join(lines) + "\n"
    (dest / "COMPARE.md").write_text(text, encoding="utf-8")
    (dest / "SUMMARY.md").write_text(text, encoding="utf-8")
    return text


def run_aiv2_stack(device: str = "cuda:0", tabpfn_device: str = "cpu") -> dict[str, object]:
    dest = AIV2_REPORT_DIR
    dest.mkdir(parents=True, exist_ok=True)
    pids, y_all = _train_ids()
    oof_store = {name: {"patient_id": [], "y": [], "proba": []} for name in MEMBERS}
    clin = _clinical_only_block()
    clin_train = {pid: i for i, pid in enumerate(clin["train"]["patient_id"].tolist())}

    for fold, (tr, te) in enumerate(_folds(pids, y_all), start=1):
        fit_pids = {str(pids[i]) for i in tr}
        hold_pids = [str(pids[i]) for i in te]
        print(f"aiv2 fold {fold}/{FOLDS} hold={len(hold_pids)}", flush=True)
        tab_map = _tabpfn_on_pids(fit_pids, tabpfn_device, FOLD_SEED + fold)
        for name in ("default", "best"):
            model = _train_member(
                name,
                fit_pids,
                device,
                FOLD_SEED + fold,
                tab_map if name == "best" else None,
            )
            spec = MEMBER_SPEC[name]
            loader = _loader("train", set(hold_pids), tab_map if name == "best" else None, 16, FOLD_SEED)
            pred = _predict(model, loader, device, int(spec["clinical_dim"]), "raw")
            oof_store[name]["patient_id"].extend(pred["patient_id"].tolist())
            oof_store[name]["y"].extend(pred["y"].tolist())
            oof_store[name]["proba"].append(pred["proba"])
            del model
            torch.cuda.empty_cache()
        for pid in hold_pids:
            oof_store["clinical_only"]["patient_id"].append(pid)
            idx = clin_train[pid]
            oof_store["clinical_only"]["y"].append(int(clin["train"]["y"][idx]))
            oof_store["clinical_only"]["proba"].append(clin["train"]["proba"][idx][None, :])

    oof_blocks = {}
    for name in MEMBERS:
        order = np.argsort(np.asarray(oof_store[name]["patient_id"]))
        proba = np.concatenate(oof_store[name]["proba"], axis=0)[order]
        oof_blocks[name] = {
            "patient_id": np.asarray(oof_store[name]["patient_id"])[order],
            "y": np.asarray(oof_store[name]["y"], dtype=int)[order],
            "proba": proba,
            "pred": proba.argmax(1),
        }
    y_oof, proba_oof = _align_by_pid(oof_blocks)
    oof_scores = {name: _score(y_oof, proba_oof[name].argmax(1)) for name in MEMBERS}
    oracle = {
        "default vs best": _oracle(y_oof, proba_oof["default"], proba_oof["best"]),
        "best vs clinical_only": _oracle(y_oof, proba_oof["best"], proba_oof["clinical_only"]),
        "default vs clinical_only": _oracle(y_oof, proba_oof["default"], proba_oof["clinical_only"]),
    }

    stackers = {}
    for combo in E1_COMBOS:
        p = _e1([proba_oof[n] for n in combo])
        key = "e1_" + "+".join(combo)
        stackers[key] = {"kind": "e1", "members": combo, "oof": _score(y_oof, p.argmax(1)), "temp": _temperature(y_oof, p)}

    e2_names = ("best", "default", "clinical_only")
    w, p2 = _e2(y_oof, [proba_oof[n] for n in e2_names])
    stackers["e2_convex3"] = {
        "kind": "e2",
        "members": e2_names,
        "weights": {n: float(v) for n, v in zip(e2_names, w)},
        "oof": _score(y_oof, p2.argmax(1)),
        "temp": _temperature(y_oof, p2),
    }
    clf3, p3 = _e3(y_oof, [proba_oof[n] for n in e2_names])
    stackers["e3_logit3"] = {
        "kind": "e3",
        "members": e2_names,
        "oof": _score(y_oof, p3.argmax(1)),
        "temp": _temperature(y_oof, p3),
    }

    def _lock_key(name: str) -> tuple[float, float, float]:
        s = stackers[name]["oof"]
        t2_ok = float(s["recall_T2"] >= max(0.20, 0.95 * oof_scores["default"]["recall_T2"]))
        return (t2_ok, float(s["acc"]), float(s["recall_T2"]))

    pick = max(stackers, key=_lock_key)

    full_blocks = {
        "clinical_only": {k: clin[k] for k in ("val", "test_prospective", "test_external")},
        "default": _dump_full_member("default", device),
        "best": _dump_full_member("best", device),
    }
    heldout = {}
    for name, spec in stackers.items():
        heldout[name] = {}
        for split in ("val", "test_prospective", "test_external"):
            y, probs = _align_by_pid({m: full_blocks[m][split] for m in spec["members"]})
            if spec["kind"] == "e1":
                p = _e1([probs[m] for m in spec["members"]])
            elif spec["kind"] == "e2":
                ww = np.asarray([spec["weights"][m] for m in spec["members"]], dtype=np.float32)
                p = np.clip(np.tensordot(ww, np.stack([probs[m] for m in spec["members"]], 0), (0, 0)), 1e-8, 1.0)
            else:
                p = _apply_e3(clf3, [probs[m] for m in spec["members"]])
            p = _apply_temp(p, float(spec["temp"]))
            heldout[name][split] = _score(y, p.argmax(1))
            heldout[name][split]["confusion"] = confusion(y, p.argmax(1))

    payload = {
        "situation": "A",
        "n_train": int(len(y_oof)),
        "oof_scores": oof_scores,
        "oracle": oracle,
        "stackers": {k: {kk: vv for kk, vv in v.items() if kk != "clf"} for k, v in stackers.items()},
        "picked_on_oof": pick,
        "heldout": heldout,
        "e2_weights": stackers["e2_convex3"].get("weights"),
    }
    (dest / "aiv2.json").write_text(json.dumps(_jsonable(payload), indent=2), encoding="utf-8")
    _write_report(dest, payload)
    np.savez_compressed(
        dest / "oof_probas.npz",
        patient_id=oof_blocks["default"]["patient_id"],
        y=y_oof,
        **{f"p_{k}": proba_oof[k] for k in MEMBERS},
    )
    return {
        "report": str(dest),
        "picked_on_oof": pick,
        "oof": {k: float(v["acc"]) for k, v in oof_scores.items()},
        "heldout_best_cell": {
            split: {k: float(heldout[pick][split][k]) for k in ("acc", "recall_T2", "recall_T3")}
            for split in ("test_prospective", "test_external")
        },
    }
