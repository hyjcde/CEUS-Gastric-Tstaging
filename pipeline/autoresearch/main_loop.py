#!/usr/bin/env python3
"""Offline budget-constrained autoresearch main loop (NOT clinical Agent).

This loop explores module/hyperparameter combinations offline under a hard budget.
It must never update online clinical Agent weights or mutate frozen mainline runs.

Budget defaults:
  - max_trials = 30
  - max_epochs_per_trial = 2
  - selection on val only; external/prospective are final audit only

Usage:
  python3 -m pipeline.autoresearch.main_loop --dry-run
  python3 pipeline/autoresearch/main_loop.py --max-trials 5 --dry-run
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DEFAULT_OUT = ROOT / "pipeline/autoresearch/results/offline_loop"
DEFAULT_LEDGER = ROOT / "pipeline/autoresearch/results/trial_ledger.csv"
FROZEN_MAINLINE = "tstaging_4class_acc_boost2_multitask_screened_eval_20260603_162955"


MODULE_BANK = [
    "M1_convnext_logits",
    "M2_dino_nca",
    "M3_wall_border_delta",
    "M4_lumen_conf",
    "M5_clinical22",
    "M6_lesion_dice",
]


@dataclass
class TrialConfig:
    trial_id: str
    modules: List[str]
    lr: float
    boundary_cost: float
    rag_weight_cap: float
    seed: int
    warmstart_from: str = FROZEN_MAINLINE
    max_epochs: int = 2


@dataclass
class TrialResult:
    trial_id: str
    status: str
    val_macro_auc: Optional[float] = None
    val_patient_acc: Optional[float] = None
    notes: List[str] = field(default_factory=list)
    config: Dict[str, Any] = field(default_factory=dict)
    code_hash: str = ""
    created_at: str = ""


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _code_hash() -> str:
    files = [
        ROOT / "pipeline/autoresearch/main_loop.py",
        ROOT / "pipeline/agent/memory/evolver.py",
        ROOT / "pipeline/agent/tools/similarity_tool.py",
    ]
    h = hashlib.sha256()
    for path in files:
        if path.exists():
            h.update(path.read_bytes())
    return h.hexdigest()[:16]


class Proposer:
    def __init__(self, seed: int = 0):
        self.rng = random.Random(seed)

    def propose(self, trial_idx: int, history: List[TrialResult]) -> TrialConfig:
        # Prefer modules that appeared in better historical trials when available.
        ranked = sorted(
            [t for t in history if t.val_macro_auc is not None],
            key=lambda t: t.val_macro_auc or 0.0,
            reverse=True,
        )
        if ranked and self.rng.random() < 0.6:
            base_modules = list(ranked[0].config.get("modules") or ["M1_convnext_logits", "M5_clinical22"])
        else:
            k = self.rng.randint(2, min(4, len(MODULE_BANK)))
            base_modules = ["M1_convnext_logits"] + self.rng.sample(
                [m for m in MODULE_BANK if m != "M1_convnext_logits"], k - 1
            )
        # Mutate
        if self.rng.random() < 0.4:
            candidate = self.rng.choice(MODULE_BANK)
            if candidate not in base_modules and len(base_modules) < 5:
                base_modules.append(candidate)
        return TrialConfig(
            trial_id=f"AR_{datetime.now(timezone.utc).strftime('%Y%m%d')}_{trial_idx:03d}",
            modules=sorted(set(base_modules)),
            lr=self.rng.choice([1e-5, 3e-5, 1e-4]),
            boundary_cost=self.rng.choice([0.0, 0.1, 0.2]),
            rag_weight_cap=self.rng.choice([0.0, 0.1, 0.2]),
            seed=self.rng.randint(1, 10_000),
            max_epochs=2,
        )


class Trainer:
    """Dry-run trainer stub. Real training must be launched explicitly offline."""

    def run(self, config: TrialConfig, *, dry_run: bool = True) -> Dict[str, Any]:
        if dry_run:
            # Deterministic pseudo-metric from config for wiring tests only.
            score = 0.60 + 0.01 * len(config.modules) - 0.02 * config.rag_weight_cap
            score += 0.005 if "M3_wall_border_delta" in config.modules else 0.0
            score -= 0.01 if config.lr >= 1e-4 else 0.0
            return {
                "status": "dry_run",
                "val_macro_auc": round(score, 4),
                "val_patient_acc": round(score - 0.05, 4),
                "notes": [
                    "dry-run only; no weights written",
                    f"warmstart_from={config.warmstart_from}",
                    "frozen mainline remains immutable",
                ],
            }
        raise RuntimeError(
            "Live trainer is intentionally not enabled in this closure pass. "
            "Wire to pipeline/run_experiment.py under an explicit offline job."
        )


class Evaluator:
    def evaluate(self, train_out: Dict[str, Any], config: TrialConfig) -> TrialResult:
        return TrialResult(
            trial_id=config.trial_id,
            status=str(train_out.get("status", "unknown")),
            val_macro_auc=train_out.get("val_macro_auc"),
            val_patient_acc=train_out.get("val_patient_acc"),
            notes=list(train_out.get("notes") or []),
            config=asdict(config),
            code_hash=_code_hash(),
            created_at=_utc(),
        )


class Reflector:
    def reflect(self, history: List[TrialResult]) -> Dict[str, Any]:
        if not history:
            return {"advice": ["start with M1+M5", "keep rag_weight_cap <= 0.2"]}
        best = max(history, key=lambda t: t.val_macro_auc or -1.0)
        worst = min(history, key=lambda t: t.val_macro_auc or 1.0)
        advice = [
            f"best_trial={best.trial_id} val_macro_auc={best.val_macro_auc}",
            f"prefer_modules={best.config.get('modules')}",
            f"avoid_or_revisit={worst.config.get('modules')} (worst={worst.val_macro_auc})",
            "do not use external labels for selection",
            "clinical Agent path must remain frozen-weight",
        ]
        return {"advice": advice, "best_trial_id": best.trial_id}


class TrialMemory:
    def __init__(self, out_dir: Path):
        self.out_dir = out_dir
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.history_path = self.out_dir / "trial_history.jsonl"

    def append(self, result: TrialResult) -> None:
        with self.history_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(asdict(result), ensure_ascii=False) + "\n")

    def load(self) -> List[TrialResult]:
        if not self.history_path.exists():
            return []
        out: List[TrialResult] = []
        for line in self.history_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            raw = json.loads(line)
            out.append(TrialResult(**raw))
        return out


def run_loop(
    *,
    max_trials: int = 30,
    seed: int = 0,
    dry_run: bool = True,
    out_dir: Path = DEFAULT_OUT,
) -> Dict[str, Any]:
    if max_trials > 30:
        raise SystemExit("max_trials hard cap is 30 for this offline loop")

    proposer = Proposer(seed=seed)
    trainer = Trainer()
    evaluator = Evaluator()
    reflector = Reflector()
    memory = TrialMemory(out_dir)
    history = memory.load()

    for i in range(1, max_trials + 1):
        config = proposer.propose(len(history) + 1, history)
        config.max_epochs = min(config.max_epochs, 2)
        train_out = trainer.run(config, dry_run=dry_run)
        result = evaluator.evaluate(train_out, config)
        memory.append(result)
        history.append(result)

    reflection = reflector.reflect(history)
    best = max(history, key=lambda t: t.val_macro_auc or -1.0) if history else None
    summary = {
        "generated_at": _utc(),
        "dry_run": dry_run,
        "max_trials": max_trials,
        "max_epochs_per_trial": 2,
        "frozen_mainline": FROZEN_MAINLINE,
        "code_hash": _code_hash(),
        "n_history": len(history),
        "best_trial": asdict(best) if best else None,
        "reflection": reflection,
        "guardrails": [
            "Offline only; never writes clinical Agent active memory",
            "Never mutates frozen mainline checkpoint directories",
            "Val for selection only; external/prospective are final audit",
            "Budget: <=30 trials, <=2 epochs/trial",
        ],
        "out_dir": str(out_dir),
    }
    (out_dir / "LOOP_SUMMARY.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    (out_dir / "LOOP_SUMMARY.md").write_text(
        "\n".join(
            [
                "# Offline Autoresearch Loop Summary",
                "",
                f"- Generated: `{summary['generated_at']}`",
                f"- Dry-run: `{dry_run}`",
                f"- Trials in history: {summary['n_history']}",
                f"- Best trial: `{best.trial_id if best else 'n/a'}` val_macro_auc={best.val_macro_auc if best else 'n/a'}",
                f"- Code hash: `{summary['code_hash']}`",
                "",
                "## Reflection",
                "",
                *[f"- {a}" for a in reflection.get("advice", [])],
                "",
                "## Guardrails",
                "",
                *[f"- {g}" for g in summary["guardrails"]],
            ]
        ),
        encoding="utf-8",
    )
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Offline autoresearch main loop")
    parser.add_argument("--max-trials", type=int, default=5)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--dry-run", action="store_true", default=True)
    parser.add_argument("--live", action="store_true", help="Attempt live trainer (currently raises)")
    args = parser.parse_args()
    summary = run_loop(
        max_trials=args.max_trials,
        seed=args.seed,
        dry_run=not args.live,
        out_dir=args.out_dir,
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
