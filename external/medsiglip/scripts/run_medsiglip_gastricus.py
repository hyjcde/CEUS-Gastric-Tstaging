#!/usr/bin/env python3
"""GastricUS MedSigLIP-448 实验入口。对照 `GastricUS实验方案.md`。

方案路线与开关:
  2 / 3   encode                 preprocess.py + 冻 MedSigLIP，缓存 e_full / e_roi
  4.1     --fusion concat        MLP([e_full, e_roi])                 默认
  4.2     --fusion interact      MLP([full, roi, |full-roi|, full*roi])
  5.1     --pool mean_views      z = [mean(e_full), mean(e_roi)]，跳过 4.x 融合
  5.2     --pool stats           concat(mean, max, std) of u
  5.3     --pool gated           gated-attn + mean + max               默认
  6.1     --head mlp             [z_image, 临床 22] -> MLP             默认
  6.2     --head tabpfn          [z_image, TabPFN(临床 11)] -> MLP

默认一次 train = 4.1 + 5.3 + 6.1，--size xlarge。更深对照：--size deep。
对齐字面宽度: --size small --no-residual；5.3 维: --pool-out 64|128。
完整唯一格子: --plan-sweep（5.1 不走融合，故无 interact+mean）。
方案未写的扩展: --unfreeze-lora, --spatial, --layers, --t34-sweep 等，不要当成方案条目。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "pipeline") not in sys.path:
    sys.path.insert(0, str(ROOT / "pipeline"))

from medsiglip_gastricus.binary import train_binary_sweep  # noqa: E402
from medsiglip_gastricus.constants import AIV2_REPORT_DIR, BINARY_REPORT_DIR, BM_CACHE_DIR, BM_REPORT_DIR, CACHE_DIR, DEEP_REPORT_DIR, ENSEMBLE_REPORT_DIR, EXPAND15_REPORT_DIR, EXPAND25_REPORT_DIR, LARGECLF_REPORT_DIR, LAYERS_CACHE_DIR, LAYERS_REPORT_DIR, LEDGER_DIR, LOCKMACRO_REPORT_DIR, MASKCUT_CACHE_DIR, MASKCUT_REPORT_DIR, MASKVIEW_CACHE_DIR, MASKVIEW_REPORT_DIR, MASK_GEOM_CACHE, MASK_GEOM_REPORT_DIR, MULTI1525_CACHE_DIR, MULTI1525_REPORT_DIR, OPT_REPORT_DIR, PHASE1_REPORT_DIR, PHASE1_SEED_REPORT_DIR, PLAN_COMPLETE_REPORT_DIR, PLAN_LITERAL_REPORT_DIR, PREOP_REPORT_DIR, REPORT_DIR, RETRY_REPORT_DIR, SPATIAL_CACHE_DIR, SPATIAL_REPORT_DIR, STACK_REPORT_DIR, T2COST_REPORT_DIR, T2_ERROR_REPORT_DIR, T34_REPORT_DIR, TABPFN_BOTH_REPORT_DIR, TABPFN_REPORT_DIR, TABPFN_XLARGE_REPORT_DIR, TSTAGING_LORA_REPORT_DIR, UNFREEZE_REPORT_DIR, WEIGHT_DIR, cache_dir_for_expand, cache_dir_for_pad, report_dir_for_expand, report_dir_for_pad  # noqa: E402
from medsiglip_gastricus.encode import encode_all  # noqa: E402
from medsiglip_gastricus.ensemble import run_ensemble  # noqa: E402
from medsiglip_gastricus.mask_geom import build_mask_geom, load_mask_geom_map  # noqa: E402
from medsiglip_gastricus.mask_cut import encode_mask_cut  # noqa: E402
from medsiglip_gastricus.mask_view import encode_mask_view  # noqa: E402
from medsiglip_gastricus.stack import run_stack  # noqa: E402
from medsiglip_gastricus.t2_error import analyze_t2  # noqa: E402
from medsiglip_gastricus.plan_literal import train_plan_literal_sweep  # noqa: E402
from medsiglip_gastricus.resolve_frames import write_resolved  # noqa: E402
from medsiglip_gastricus.layers import encode_layers  # noqa: E402
from medsiglip_gastricus.multi_expand import merge_multi_expand  # noqa: E402
from medsiglip_gastricus.spatial import encode_spatial  # noqa: E402
from medsiglip_gastricus.aiv2_stack import run_aiv2_stack  # noqa: E402
from medsiglip_gastricus.phase1_boundary import run_phase1_audit, train_phase1_seeds  # noqa: E402
from medsiglip_gastricus.train import train, train_largeclf_compare, train_opt_sweep, train_plan_sweep, train_retry_sweep, train_t34_sweep  # noqa: E402
from medsiglip_gastricus.unfreeze import eval_unfreeze, train_unfreeze  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="GastricUS MedSigLIP-448. 对照 GastricUS实验方案.md: encode=2/3, --fusion=4.x, --pool=5.x, --head=6.x.",
    )
    parser.add_argument("command", choices=("prepare", "encode", "train", "ensemble", "stack", "t2-error", "ledger", "eval-unfreeze", "phase1", "aiv2", "bm", "all"))
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--batch-size", type=int, default=8, help="encode batch. 方案 3 预计算。")
    parser.add_argument("--train-batch-size", type=int, default=16)
    parser.add_argument("--epochs", type=int, default=80)
    parser.add_argument("--lr", type=float, default=2e-4)
    parser.add_argument(
        "--head",
        choices=("mlp", "tabpfn", "tabpfn_time", "tabpfn_both"),
        default="mlp",
        help="6.1 mlp | 6.2 tabpfn。tabpfn_time / tabpfn_both 方案未写。",
    )
    parser.add_argument(
        "--fusion",
        choices=("concat", "interact", "gate", "pair"),
        default="concat",
        help="4.1 concat | 4.2 interact | gate 门控混合 | pair 两 token 自注意力。",
    )
    parser.add_argument(
        "--pool",
        choices=("mean_views", "stats", "gated", "mean_u", "attn_only"),
        default="gated",
        help="5.1 mean_views | 5.2 stats | 5.3 gated | mean_u 先融合再均值 | attn_only。",
    )
    parser.add_argument(
        "--size",
        choices=("small", "large", "xlarge", "xxlarge", "deep", "wideclf", "mid"),
        default="xlarge",
        help="small=方案字面。默认 xlarge。mid=512 维加 2 层帧 Transformer。",
    )
    parser.add_argument("--warmup-epochs", type=int, default=8)
    parser.add_argument("--patience", type=int, default=25)
    parser.add_argument("--class-weight", choices=("none", "balanced"), default="balanced")
    parser.add_argument("--lock", choices=("acc", "adj", "qwk", "macro"), default="acc")
    parser.add_argument("--ordinal-weight", type=float, default=0.5)
    parser.add_argument("--ordinal-mode", choices=("rank", "cost"), default="rank")
    parser.add_argument("--t34-weight", type=float, default=0.0, help="Extra T3/T4+ pair-mass penalty.")
    parser.add_argument(
        "--t2-off2-weight",
        type=float,
        default=0.0,
        help="Extra T2-to-T1 and T2-to-T4-plus softmax mass penalty. Default 0.",
    )
    parser.add_argument("--aux-serosa-weight", type=float, default=0.0, help="BCE on T4+ vs not-T4+.")
    parser.add_argument("--pool-proj", action="store_true", help="方案 5.1: 把 2304 维均值压到 pool_out。默认直出。")
    parser.add_argument("--no-residual", action="store_true", help="去掉 4.x 融合残差，对齐方案字面 MLP。")
    parser.add_argument(
        "--clinical",
        choices=("raw", "none", "preop"),
        default="raw",
        help="raw=all 11 fields; none=image only; preop=drop Lauren and differentiation.",
    )
    parser.add_argument("--tabpfn-device", default="cpu")
    parser.add_argument(
        "--plan-sweep",
        action="store_true",
        help="方案 4.x / 5.x / 6.x 完整唯一网格（10 组）。5.1 跳过融合。",
    )
    parser.add_argument(
        "--largeclf-compare",
        action="store_true",
        help="冻 encoder：xlarge MLP、加宽 6.1 头、gated TabPFN、mean TabPFN。",
    )
    parser.add_argument(
        "--retry-sweep",
        action="store_true",
        help="15/25 ROI、混合 ROI、gate/pair 融合、mean_u/attn_only、mid 头。不改默认。",
    )
    parser.add_argument("--opt-sweep", action="store_true", help="Train optimized xlarge variants with ordinal loss.")
    parser.add_argument("--t34-sweep", action="store_true", help="Train T3/T4 lock, cost, pair, and serosa variants.")
    parser.add_argument("--binary-sweep", action="store_true", help="Train serosa and T3-vs-T4+ binary heads, then cascade.")
    parser.add_argument("--plan-literal-sweep", action="store_true", help="Clinical-only TabPFN, TIME-192, 64/128 gated, frame sample.")
    parser.add_argument("--expand", type=float, default=0.20, help="方案 2.2: mask bbox 外扩。15% / 20% / 25%。")
    parser.add_argument(
        "--pad",
        choices=("black", "reflect", "edge", "mean"),
        default="black",
        help="Square-pad fill for ROI. Default black. Other modes write a new cache.",
    )
    parser.add_argument(
        "--mask-bbox",
        choices=("all", "largest"),
        default="all",
        help="方案 2.2: all=当前 20% 缓存；largest=最大连通域，必须写新缓存。",
    )
    parser.add_argument("--frame-sample", choices=("prefix", "random", "area"), default="prefix")
    parser.add_argument("--pool-out", type=int, default=None, help="方案 5.3 影像维。方案写 64-128；xlarge 默认 512。")
    parser.add_argument("--no-reuse-full", action="store_true", help="Re-encode full frames instead of copying the 20%% cache.")
    parser.add_argument("--unfreeze-lora", action="store_true", help="LoRA last vision blocks on raw crop_ui (not the frozen cache).")
    parser.add_argument("--unfreeze-full", action="store_true", help="Full fine-tune last N vision blocks (no LoRA).")
    parser.add_argument("--lora-last-n", type=int, default=4)
    parser.add_argument("--lora-r", type=int, default=16)
    parser.add_argument("--max-frames", type=int, default=6)
    parser.add_argument("--encoder-lr", type=float, default=2e-5)
    parser.add_argument("--warm-head", action="store_true", help="Load the default concat-gated head before LoRA.")
    parser.add_argument("--spatial", action="store_true", help="Encode or train ROI-masked patch tokens (2304-d).")
    parser.add_argument(
        "--layers",
        action="store_true",
        help="Encode or train last-4 encoder layer patch means concatenated to 1152-d (5760-d).",
    )
    parser.add_argument(
        "--multi-expand",
        action="store_true",
        help="Merge 20%% full with 15%% and 25%% ROI tokens (2304-d). Does not overwrite those caches.",
    )
    parser.add_argument(
        "--mask-geom",
        action="store_true",
        help="Encode or append 10-d lesion-mask geometry. Sidecar only; does not overwrite embeddings.",
    )
    parser.add_argument(
        "--mask-view",
        action="store_true",
        help="Encode lesion-overlay third view and concat to 20%% tokens (2304-d). New cache only.",
    )
    parser.add_argument(
        "--mask-cut",
        action="store_true",
        help="Encode lesion-only RGB (background zeroed) and concat to 20%% tokens (2304-d). New cache only.",
    )
    parser.add_argument("--freeze-head-epochs", type=int, default=0, help="Train LoRA only for the first N epochs.")
    parser.add_argument("--ckpt", default="", help="Checkpoint for eval-unfreeze.")
    parser.add_argument("--seed", type=int, default=20260821)
    parser.add_argument(
        "--phase1-seeds",
        action="store_true",
        help="Retrain default and 5.1x6.2 on extra seeds, then re-run the phase-1 audit.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.command in {"prepare", "all"}:
        summary = write_resolved(CACHE_DIR)
        print("prepare", summary, flush=True)
    if args.command in {"encode", "all"}:
        if sum(bool(x) for x in (args.spatial, args.layers, args.multi_expand, args.mask_geom, args.mask_view, args.mask_cut)) > 1:
            raise SystemExit("use only one of --spatial, --layers, --multi-expand, --mask-geom, --mask-view, --mask-cut")
        if args.spatial:
            print("encode-spatial", encode_spatial(device=args.device, batch_size=args.batch_size), flush=True)
            print(f"cache={SPATIAL_CACHE_DIR}")
        elif args.layers:
            print("encode-layers", encode_layers(device=args.device, batch_size=args.batch_size), flush=True)
            print(f"cache={LAYERS_CACHE_DIR}")
        elif args.multi_expand:
            print("encode-multi-expand", merge_multi_expand(), flush=True)
            print(f"cache={MULTI1525_CACHE_DIR}")
        elif args.mask_geom:
            print("encode-mask-geom", build_mask_geom(), flush=True)
            print(f"cache={MASK_GEOM_CACHE}")
        elif args.mask_view:
            print("encode-mask-view", encode_mask_view(device=args.device, batch_size=args.batch_size), flush=True)
            print(f"cache={MASKVIEW_CACHE_DIR}")
        elif args.mask_cut:
            print("encode-mask-cut", encode_mask_cut(device=args.device, batch_size=args.batch_size), flush=True)
            print(f"cache={MASKCUT_CACHE_DIR}")
        else:
            print(
                "encode",
                encode_all(
                    device=args.device,
                    batch_size=args.batch_size,
                    expand=args.expand,
                    dest=cache_dir_for_pad(args.pad) if args.pad != "black" else cache_dir_for_expand(args.expand),
                    reuse_full=not args.no_reuse_full,
                    pad=args.pad,
                    bbox_mode=args.mask_bbox,
                ),
                flush=True,
            )
    if args.command == "stack":
        print("stack", run_stack(device=args.device), flush=True)
        print(f"report={STACK_REPORT_DIR}")
    if args.command == "t2-error":
        print("t2-error", analyze_t2(), flush=True)
        print(f"report={T2_ERROR_REPORT_DIR}")
    if args.command in {"ensemble", "all"}:
        print("ensemble", run_ensemble(), flush=True)
        print(f"report={ENSEMBLE_REPORT_DIR}")
    if args.command == "eval-unfreeze":
        ckpt = Path(args.ckpt) if args.ckpt else UNFREEZE_REPORT_DIR / "lora4_r16_warmhead" / "best_adapters.pt"
        print("eval-unfreeze", eval_unfreeze(ckpt, device=args.device, max_frames=args.max_frames), flush=True)
    if args.command == "ledger":
        import runpy

        runpy.run_path(str(Path(__file__).resolve().parents[0] / "sync_gastricus_ledger.py"), run_name="__main__")
        print(f"ledger={LEDGER_DIR}")
    if args.command == "phase1":
        if args.phase1_seeds:
            print(
                "phase1-seeds",
                train_phase1_seeds(device=args.device, tabpfn_device=args.tabpfn_device),
                flush=True,
            )
            print(f"report={PHASE1_SEED_REPORT_DIR}")
        else:
            print("phase1", run_phase1_audit(), flush=True)
            print(f"report={PHASE1_REPORT_DIR}")
    if args.command == "aiv2":
        print(
            "aiv2",
            run_aiv2_stack(device=args.device, tabpfn_device=args.tabpfn_device),
            flush=True,
        )
        print(f"report={AIV2_REPORT_DIR}")
    if args.command == "bm":
        from medsiglip_gastricus.constants import BM_LORA_REPORT_DIR
        from medsiglip_gastricus.prepare_bm import prepare_bm

        print("bm-prepare", prepare_bm(), flush=True)
        if args.unfreeze_lora:
            from medsiglip_gastricus.unfreeze_bm import train_unfreeze_bm

            print(
                "bm-lora",
                train_unfreeze_bm(
                    device=args.device,
                    epochs=min(args.epochs, 20),
                    max_frames=min(args.max_frames, 4),
                    last_n=2,
                    lora_r=args.lora_r,
                    encoder_lr=args.encoder_lr if args.encoder_lr != 2e-5 else 5e-6,
                    head_lr=args.lr if args.lr != 2e-4 else 1e-4,
                    expand=args.expand,
                    seed=args.seed,
                ),
                flush=True,
            )
            print(f"report={BM_LORA_REPORT_DIR}")
        else:
            from medsiglip_gastricus.encode_bm import encode_bm
            from medsiglip_gastricus.train_bm import train_bm

            need_encode = any(
                not (BM_CACHE_DIR / f"{split}_embeddings.npz").is_file()
                for split in ("train", "val", "test_prospective", "test_external")
            )
            if need_encode:
                print("bm-encode", encode_bm(device=args.device, batch_size=args.batch_size, expand=args.expand), flush=True)
            print(
                "bm-train",
                train_bm(
                    device=args.device,
                    epochs=args.epochs,
                    batch_size=args.train_batch_size,
                    lr=args.lr,
                    fusion=args.fusion,
                    pool=args.pool,
                    size=args.size,
                    seed=args.seed,
                ),
                flush=True,
            )
            print(f"cache={BM_CACHE_DIR}")
            print(f"report={BM_REPORT_DIR}")
    if args.command in {"train", "all"}:
        if args.unfreeze_lora or args.unfreeze_full:
            result = train_unfreeze(
                device=args.device,
                epochs=min(args.epochs, 40),
                last_n=args.lora_last_n,
                mode="full" if args.unfreeze_full else "lora",
                lora_r=args.lora_r,
                encoder_lr=args.encoder_lr,
                head_lr=args.lr,
                max_frames=args.max_frames,
                expand=args.expand,
                warmup_epochs=min(args.warmup_epochs, 3),
                patience=min(args.patience, 12),
                warm_head=args.warm_head,
                freeze_head_epochs=args.freeze_head_epochs,
                batch_size=4 if args.train_batch_size == 16 else args.train_batch_size,
                num_workers=4,
            )
            print(
                "unfreeze-lora",
                {name: float(block["acc"]) for name, block in result["eval"].items()},
                flush=True,
            )
            print(f"report={TSTAGING_LORA_REPORT_DIR}")
        elif args.plan_literal_sweep:
            print(
                "plan-literal-sweep",
                train_plan_literal_sweep(
                    device=args.device,
                    epochs=args.epochs,
                    batch_size=args.train_batch_size,
                    lr=args.lr,
                    tabpfn_device=args.tabpfn_device,
                    warmup_epochs=args.warmup_epochs,
                    patience=args.patience,
                ),
                flush=True,
            )
            print(f"report={PLAN_LITERAL_REPORT_DIR}")
        elif args.binary_sweep:
            print(
                "binary-sweep",
                train_binary_sweep(
                    device=args.device,
                    epochs=args.epochs,
                    batch_size=args.train_batch_size,
                    lr=args.lr,
                    size=args.size,
                    warmup_epochs=args.warmup_epochs,
                    patience=args.patience,
                ),
                flush=True,
            )
            print(f"report={BINARY_REPORT_DIR}")
        elif args.t34_sweep:
            print(
                "t34-sweep",
                train_t34_sweep(
                    device=args.device,
                    epochs=args.epochs,
                    batch_size=args.train_batch_size,
                    lr=args.lr,
                    size=args.size,
                    warmup_epochs=args.warmup_epochs,
                    patience=args.patience,
                ),
                flush=True,
            )
            print(f"report={T34_REPORT_DIR}")
        elif args.opt_sweep:
            print(
                "opt-sweep",
                train_opt_sweep(
                    device=args.device,
                    epochs=args.epochs,
                    batch_size=args.train_batch_size,
                    lr=args.lr,
                    size=args.size,
                    warmup_epochs=args.warmup_epochs,
                    patience=args.patience,
                    lock=args.lock,
                    ordinal_weight=args.ordinal_weight,
                ),
                flush=True,
            )
            print(f"report={OPT_REPORT_DIR}")
        elif args.retry_sweep:
            print(
                "retry-sweep",
                train_retry_sweep(
                    device=args.device,
                    epochs=args.epochs,
                    batch_size=args.train_batch_size,
                    lr=args.lr,
                    tabpfn_device=args.tabpfn_device,
                    warmup_epochs=args.warmup_epochs,
                    patience=args.patience,
                    lock=args.lock,
                    ordinal_weight=args.ordinal_weight,
                ),
                flush=True,
            )
            print(f"report={RETRY_REPORT_DIR}")
        elif args.largeclf_compare:
            print(
                "largeclf-compare",
                train_largeclf_compare(
                    device=args.device,
                    epochs=args.epochs,
                    batch_size=args.train_batch_size,
                    lr=args.lr,
                    tabpfn_device=args.tabpfn_device,
                    warmup_epochs=args.warmup_epochs,
                    patience=args.patience,
                    lock=args.lock,
                    ordinal_weight=args.ordinal_weight,
                ),
                flush=True,
            )
            print(f"report={LARGECLF_REPORT_DIR}")
        elif args.plan_sweep:
            print(
                "plan-sweep",
                train_plan_sweep(
                    device=args.device,
                    epochs=args.epochs,
                    batch_size=args.train_batch_size,
                    lr=args.lr,
                    tabpfn_device=args.tabpfn_device,
                    size="xlarge" if args.size == "deep" else args.size,
                    warmup_epochs=args.warmup_epochs,
                    patience=args.patience,
                    lock=args.lock,
                    ordinal_weight=args.ordinal_weight,
                    pool_proj=args.pool_proj,
                    residual=not args.no_residual,
                    clinical=args.clinical,
                ),
                flush=True,
            )
            print(f"report={PLAN_COMPLETE_REPORT_DIR}")
        else:
            dest = None
            cache = cache_dir_for_expand(args.expand)
            if sum(bool(x) for x in (args.spatial, args.layers, args.multi_expand, args.mask_geom, args.mask_view, args.mask_cut)) > 1:
                raise SystemExit("use only one of --spatial, --layers, --multi-expand, --mask-geom, --mask-view, --mask-cut")
            extra_map = None
            if args.spatial:
                dest = SPATIAL_REPORT_DIR / f"{args.head}_{args.fusion}_{args.pool}"
                cache = SPATIAL_CACHE_DIR
            elif args.layers:
                dest = LAYERS_REPORT_DIR / f"{args.head}_{args.fusion}_{args.pool}"
                cache = LAYERS_CACHE_DIR
            elif args.multi_expand:
                dest = MULTI1525_REPORT_DIR / f"{args.head}_{args.fusion}_{args.pool}"
                cache = MULTI1525_CACHE_DIR
            elif args.mask_view:
                dest = MASKVIEW_REPORT_DIR / f"{args.head}_{args.fusion}_{args.pool}"
                cache = MASKVIEW_CACHE_DIR
            elif args.mask_cut:
                dest = MASKCUT_REPORT_DIR / f"{args.head}_{args.fusion}_{args.pool}"
                cache = MASKCUT_CACHE_DIR
            elif args.mask_geom:
                dest = MASK_GEOM_REPORT_DIR / f"{args.head}_{args.fusion}_{args.pool}"
                extra_map = load_mask_geom_map()
            elif args.t2_off2_weight > 0:
                dest = T2COST_REPORT_DIR / f"{args.head}_{args.fusion}_{args.pool}"
            elif args.lock == "macro":
                tag = f"{args.head}_{args.fusion}_{args.pool}"
                if abs(args.expand - 0.20) > 1e-9:
                    tag = f"expand{int(round(args.expand * 100))}_{tag}"
                dest = LOCKMACRO_REPORT_DIR / tag
            elif args.pad != "black":
                dest = report_dir_for_pad(args.pad) / f"{args.head}_{args.fusion}_{args.pool}"
                cache = cache_dir_for_pad(args.pad)
            elif args.head == "tabpfn_both":
                tag = f"{args.head}_{args.fusion}_{args.pool}_{args.size}"
                if abs(args.expand - 0.20) > 1e-9:
                    tag = f"{tag}_expand{int(round(args.expand * 100))}"
                dest = TABPFN_BOTH_REPORT_DIR / tag
                cache = cache_dir_for_expand(args.expand)
            elif abs(args.expand - 0.20) > 1e-9:
                dest = report_dir_for_expand(args.expand) / f"{args.head}_{args.fusion}_{args.pool}"
            elif args.clinical == "preop":
                dest = PREOP_REPORT_DIR / f"{args.head}_{args.fusion}_{args.pool}"
            elif args.head == "tabpfn":
                dest = TABPFN_XLARGE_REPORT_DIR / f"{args.head}_{args.fusion}_{args.pool}"
            elif args.size == "deep":
                dest = DEEP_REPORT_DIR / f"{args.head}_{args.fusion}_{args.pool}"
            elif args.size == "wideclf":
                dest = LARGECLF_REPORT_DIR / f"{args.head}_{args.fusion}_{args.pool}"
            print(
                "train",
                train(
                    device=args.device,
                    epochs=args.epochs,
                    lr=args.lr,
                    batch_size=args.train_batch_size,
                    head=args.head,
                    tabpfn_device=args.tabpfn_device,
                    fusion=args.fusion,
                    pool=args.pool,
                    class_weight=args.class_weight,
                    size=args.size,
                    warmup_epochs=args.warmup_epochs,
                    patience=args.patience,
                    lock=args.lock,
                    ordinal_weight=args.ordinal_weight,
                    ordinal_mode=args.ordinal_mode,
                    t34_weight=args.t34_weight,
                    t2_off2_weight=args.t2_off2_weight,
                    aux_serosa_weight=args.aux_serosa_weight,
                    pool_proj=args.pool_proj,
                    residual=not args.no_residual,
                    clinical=args.clinical,
                    cache_dir=cache,
                    frame_sample=args.frame_sample,
                    pool_out=args.pool_out,
                    report_dir=dest,
                    extra_map=extra_map,
                    seed=args.seed,
                ),
                flush=True,
            )
            if dest is not None:
                print(f"report={dest}")
            else:
                print(f"report={TABPFN_REPORT_DIR if args.head.startswith('tabpfn') else REPORT_DIR}")
    print(f"weights={WEIGHT_DIR}")
    print(f"cache={CACHE_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
