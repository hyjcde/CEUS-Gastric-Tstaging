#!/usr/bin/env python3
"""Long GastricUS run: fine-tune the 5.1 x 6.2 MedSigLIP baseline.

Plan (`# GastricUS实验方案.md`):
  2.1 / 2.2  crop_ui + 20% ROI, official 448 processor
  5.1        patient mean of full and ROI embeddings -> 2304-d image
  6.2        [image, TabPFN(clinical) OOF probabilities] -> MLP
             Image tokens never enter TabPFN.

The WADI 1062/128 patient membership is checked against the clinical sidecar
before training. Prospective/external audits are not loaded unless explicitly
requested after model lock.

This is the 10-plus-hour job: last 12 of 27 vision blocks stay in the graph
and encode up to 8 frames x 2 views every step. Frozen-head MLP is minutes;
this run is hours because the ViT runs every bag.

Does not change scripts/run_medsiglip_gastricus.py defaults.
Does not overwrite the 20% black cache or the default xlarge report.

Example:
  python3 scripts/run_medsiglip_gastricus_longrun.py --help
  python3 scripts/run_medsiglip_gastricus_longrun.py --device cuda:0
  python3 scripts/run_medsiglip_gastricus_longrun.py --device cuda:0 --resume
  python3 scripts/run_medsiglip_gastricus_longrun.py --device cuda:0 --last-n 8 --max-frames 6
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import torch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "pipeline") not in sys.path:
    sys.path.insert(0, str(ROOT / "pipeline"))

from medsiglip_gastricus.constants import CACHE_DIR, LONGRUN_REPORT_DIR, WEIGHT_DIR  # noqa: E402
from medsiglip_gastricus.longrun import train_longrun  # noqa: E402

ARCH = {
    "plan": "5.1 mean full/ROI views, 6.2 TabPFN clinical OOF",
    "encoder": "MedSigLIP-448, full FT last N vision blocks, no LoRA",
    "pool": "separate patient mean of full and ROI embeddings -> 2304",
    "clinical": "frozen TabPFN 4-class OOF probabilities, no image tokens",
    "head": "xlarge 2308 -> 1024 -> 512 -> 4, warm-started from 5.1 x 6.2",
    "loss": "balanced CE + LS 0.05 + 0.5 rank SmoothL1 + 0.4 T2 severe-error penalty",
    "lock": "WADI dev exact ACC subject to T2 recall >= 0.20",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--epochs", type=int, default=48, help="About 10-15 hours at last-12 / 8 frames.")
    parser.add_argument("--last-n", type=int, default=12, help="Unfreeze last N vision blocks. SigLIP-448 has 27.")
    parser.add_argument("--max-frames", type=int, default=8)
    parser.add_argument("--encoder-lr", type=float, default=5e-6, help="Lower than the last-8 run that drifted at 2e-5.")
    parser.add_argument("--head-lr", type=float, default=1e-4)
    parser.add_argument("--weight-decay", type=float, default=2e-4)
    parser.add_argument("--accum", type=int, default=4)
    parser.add_argument("--warmup-epochs", type=int, default=4)
    parser.add_argument("--patience", type=int, default=16)
    parser.add_argument("--expand", type=float, default=0.20)
    parser.add_argument("--lock", choices=("acc", "adj", "qwk", "macro"), default="acc")
    parser.add_argument("--ordinal-weight", type=float, default=0.5)
    parser.add_argument("--seed", type=int, default=20260821)
    parser.add_argument("--tabpfn-device", default="cpu")
    parser.add_argument(
        "--clinical",
        choices=("tabpfn", "tabpfn_both", "raw"),
        default="tabpfn",
        help="tabpfn reproduces 5.1 x 6.2. Both alternatives are ablations.",
    )
    parser.add_argument("--pool", choices=("mean_views", "gated"), default="mean_views")
    parser.add_argument("--size", choices=("xlarge", "xxlarge"), default="xlarge")
    parser.add_argument("--num-workers", type=int, default=0, help="Keep 0 unless loaders are built before CUDA.")
    parser.add_argument("--log-every", type=int, default=50)
    parser.add_argument("--no-warm-fusion", action="store_true")
    parser.add_argument("--resume", action="store_true", help="Continue from last.pt in the report folder.")
    parser.add_argument("--report-dir", default="", help="Override the auto folder under longrun_tabpfn_20260823.")
    parser.add_argument(
        "--t2-off2-weight",
        type=float,
        default=0.4,
        help="Penalty on true T2 predicted as T1 or T4+.",
    )
    parser.add_argument("--clinical-dropout", type=float, default=0.15)
    parser.add_argument("--min-t2-recall", type=float, default=0.20)
    parser.add_argument(
        "--evaluate-audits",
        action="store_true",
        help="After model lock, evaluate prospective/external audits. Off by default.",
    )
    return parser.parse_args()


def _preflight(device: str) -> None:
    print(json.dumps({"architecture": ARCH}, ensure_ascii=True), flush=True)
    print(f"weights={WEIGHT_DIR}", flush=True)
    print(f"cache={CACHE_DIR}", flush=True)
    print(f"ledger_parent={LONGRUN_REPORT_DIR}", flush=True)
    if not device.startswith("cuda"):
        return
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA requested but torch.cuda.is_available() is False")
    index = int(device.split(":")[1]) if ":" in device else 0
    free, total = torch.cuda.mem_get_info(index)
    print(f"cuda:{index} free_gb={free / 1024 ** 3:.1f} total_gb={total / 1024 ** 3:.1f}", flush=True)
    if free < 10 * 1024 ** 3:
        raise RuntimeError(f"{device} has less than 10 GB free; pick another GPU or drop --last-n / --max-frames")


def main() -> int:
    args = parse_args()
    _preflight(args.device)
    report_dir = Path(args.report_dir) if args.report_dir else None
    result = train_longrun(
        device=args.device,
        epochs=args.epochs,
        max_frames=args.max_frames,
        last_n=args.last_n,
        encoder_lr=args.encoder_lr,
        head_lr=args.head_lr,
        weight_decay=args.weight_decay,
        expand=args.expand,
        warmup_epochs=args.warmup_epochs,
        patience=args.patience,
        accum=args.accum,
        lock=args.lock,
        ordinal_weight=args.ordinal_weight,
        seed=args.seed,
        tabpfn_device=args.tabpfn_device,
        clinical=args.clinical,
        pool=args.pool,
        size=args.size,
        report_dir=report_dir,
        warm_fusion=not args.no_warm_fusion,
        resume=args.resume,
        num_workers=args.num_workers,
        log_every=args.log_every,
        command=list(sys.argv),
        t2_off2_weight=args.t2_off2_weight,
        clinical_dropout=args.clinical_dropout,
        min_t2_recall=args.min_t2_recall,
        evaluate_audits=args.evaluate_audits,
    )
    print("longrun", result, flush=True)
    print(f"report={result['report']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
