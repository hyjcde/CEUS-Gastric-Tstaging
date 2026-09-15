#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np
import pandas as pd
import torch
import yaml
from PIL import Image
from torch.utils.data import DataLoader, Dataset


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = (
    PROJECT_ROOT
    / "pipeline"
    / "data"
    / "tstaging_4class_prospective_full_anatomic"
    / "regions"
    / "test_prospective_full_clinical.csv"
)
DEFAULT_CONFIG = PROJECT_ROOT / "configs" / "segmentation" / "dinov3" / "vitb16_last2blocks_mlp_decoder.yaml"
DEFAULT_OUTPUT = (
    PROJECT_ROOT
    / "pipeline"
    / "data"
    / "dinov3_tstaging_region_features"
    / "internal_prospective_full_vitb16_last"
)
IMAGENET_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
IMAGENET_STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Cache DINOv3 region-pooled token features for T-staging classification.")
    parser.add_argument("--input-csv", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--device", default="cuda:0" if torch.cuda.is_available() else "cpu")
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--num-workers", type=int, default=4)
    parser.add_argument("--image-size", type=int, default=None)
    parser.add_argument("--layer-indices", nargs="+", type=int, default=[11])
    parser.add_argument("--max-rows", type=int, default=None)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument(
        "--input-blur-sigma",
        type=float,
        default=None,
        help="Gaussian blur sigma on input (deblur-MAE transfer protocol). Overrides config model.input_blur_sigma.",
    )
    return parser.parse_args()


def load_yaml(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        payload = yaml.safe_load(handle) or {}
    if not isinstance(payload, dict):
        raise ValueError(f"Expected mapping YAML: {path}")
    return payload


def resolve_path(value: object) -> Path | None:
    if value is None or pd.isna(value) or not str(value).strip():
        return None
    path = Path(str(value))
    if path.exists():
        return path
    if not path.is_absolute():
        candidate = PROJECT_ROOT / path
        if candidate.exists():
            return candidate
    return None


def build_model(config: dict, device: torch.device):
    paths_cfg = config.get("paths", {})
    model_cfg = config.get("model", {})
    checkpoint_path = resolve_path(paths_cfg.get("checkpoint_path"))
    family = str(model_cfg.get("backbone_family", "dinov3"))
    if family == "timm_mae":
        # MAE-style encoder (deblur-MAE etc.): timm ViT-B/16, strict load, no dinov3 hub.
        if checkpoint_path is None:
            raise FileNotFoundError("Missing checkpoint_path for timm_mae backbone")
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from train_dinov3_roi_lora_mlp import load_timm_mae_backbone

        model = load_timm_mae_backbone(model_cfg, checkpoint_path)
        return model.to(device).eval(), str(model_cfg.get("timm_model", "vit_base_patch16_224"))
    repo_dir = resolve_path(paths_cfg.get("dinov3_repo"))
    if repo_dir is None or checkpoint_path is None:
        raise FileNotFoundError("Missing DINOv3 repo or checkpoint path in config.")
    hub_model = str(model_cfg.get("hub_model", "dinov3_vitb16"))
    model = torch.hub.load(str(repo_dir), hub_model, source="local", weights=str(checkpoint_path))
    return model.to(device).eval(), hub_model


class RegionFeatureDataset(Dataset):
    def __init__(self, df: pd.DataFrame, image_size: int, blur_sigma: float = 0.0) -> None:
        self.df = df.reset_index(drop=True)
        self.image_size = int(image_size)
        self.blur_sigma = float(blur_sigma)

    def __len__(self) -> int:
        return len(self.df)

    def __getitem__(self, index: int) -> dict:
        row = self.df.iloc[index]
        image_path = resolve_path(row.get("image_path"))
        if image_path is None:
            raise FileNotFoundError(row.get("image_path"))
        image = Image.open(image_path).convert("RGB")
        if self.blur_sigma > 0:
            # DeblurringMIM protocol: grayscale -> cv2.GaussianBlur((0,0), sigma) -> RGB
            gray = np.asarray(image.convert("L"), dtype=np.uint8)
            image = Image.fromarray(cv2.GaussianBlur(gray, (0, 0), self.blur_sigma), mode="L").convert("RGB")
        image = image.resize((self.image_size, self.image_size), Image.BILINEAR)
        arr = np.asarray(image, dtype=np.float32) / 255.0
        arr = (arr - IMAGENET_MEAN) / IMAGENET_STD
        tensor = torch.from_numpy(arr).permute(2, 0, 1).contiguous()
        return {
            "index": index,
            "image": tensor,
        }


def collate(batch: list[dict]) -> dict:
    return {
        "indices": [item["index"] for item in batch],
        "images": torch.stack([item["image"] for item in batch], dim=0),
    }


def load_mask_grid(path_value: object, grid_hw: tuple[int, int]) -> np.ndarray | None:
    path = resolve_path(path_value)
    if path is None:
        return None
    mask = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    if mask is None:
        return None
    grid_h, grid_w = grid_hw
    small = cv2.resize((mask > 127).astype(np.uint8), (grid_w, grid_h), interpolation=cv2.INTER_NEAREST)
    return small.astype(bool)


def boundary_grid(mask: np.ndarray | None) -> np.ndarray | None:
    if mask is None or not mask.any():
        return None
    mask_u8 = mask.astype(np.uint8)
    kernel = np.ones((3, 3), dtype=np.uint8)
    dilated = cv2.dilate(mask_u8, kernel, iterations=1)
    eroded = cv2.erode(mask_u8, kernel, iterations=1)
    ring = (dilated - eroded).astype(bool)
    return ring if ring.any() else mask


def pool_mean(tokens: np.ndarray, mask: np.ndarray | None) -> np.ndarray:
    if mask is None or not mask.any():
        return tokens.mean(axis=0)
    return tokens[mask.reshape(-1)].mean(axis=0)


def cosine(a: np.ndarray, b: np.ndarray) -> float:
    denom = float(np.linalg.norm(a) * np.linalg.norm(b))
    if denom <= 1e-8:
        return 0.0
    return float(np.dot(a, b) / denom)


def region_features_for_row(feature_map: torch.Tensor, row: pd.Series, prefix: str) -> tuple[list[np.ndarray], list[str], dict[str, float]]:
    # feature_map: C x H x W
    feat = feature_map.detach().float().cpu().numpy()
    channels, height, width = feat.shape
    tokens = feat.reshape(channels, height * width).T

    lesion = load_mask_grid(row.get("lesion_pred_mask_path") or row.get("mask_path"), (height, width))
    outer = load_mask_grid(row.get("anatomic_outer_wall_mask_path") or row.get("breakthrough_mask_path"), (height, width))
    inner = load_mask_grid(row.get("anatomic_inner_lumen_mask_path") or row.get("control_arcband_strip_path"), (height, width))
    wall = load_mask_grid(row.get("lesion_lumen_wall_mask_path") or row.get("box_guided_focus_mask_path"), (height, width))
    boundary = boundary_grid(lesion)

    pooled = {
        "global": tokens.mean(axis=0),
        "lesion": pool_mean(tokens, lesion),
        "outer": pool_mean(tokens, outer),
        "inner": pool_mean(tokens, inner),
        "wall": pool_mean(tokens, wall),
        "boundary": pool_mean(tokens, boundary),
    }
    vectors = [
        pooled["global"],
        pooled["lesion"],
        pooled["outer"],
        pooled["inner"],
        pooled["wall"],
        pooled["boundary"],
        pooled["outer"] - pooled["inner"],
        pooled["boundary"] - pooled["lesion"],
        pooled["outer"] - pooled["lesion"],
    ]
    names = [
        "global",
        "lesion",
        "outer",
        "inner",
        "wall",
        "boundary",
        "outer_minus_inner",
        "boundary_minus_lesion",
        "outer_minus_lesion",
    ]
    scalars = {
        f"{prefix}_cos_outer_inner": cosine(pooled["outer"], pooled["inner"]),
        f"{prefix}_cos_boundary_lesion": cosine(pooled["boundary"], pooled["lesion"]),
        f"{prefix}_cos_outer_lesion": cosine(pooled["outer"], pooled["lesion"]),
        f"{prefix}_lesion_token_fraction": float(0.0 if lesion is None else lesion.mean()),
        f"{prefix}_outer_token_fraction": float(0.0 if outer is None else outer.mean()),
        f"{prefix}_boundary_token_fraction": float(0.0 if boundary is None else boundary.mean()),
    }
    out_names = [f"{prefix}_{name}" for name in names]
    return [v.astype(np.float32) for v in vectors], out_names, scalars


def main() -> None:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    out_npz = args.output_dir / "frame_dinov3_region_features.npz"
    out_manifest = args.output_dir / "frame_feature_manifest.csv"
    if out_npz.exists() and not args.overwrite:
        raise FileExistsError(f"{out_npz} exists; pass --overwrite")

    config = load_yaml(args.config)
    image_size = int(args.image_size or config.get("model", {}).get("input_size", 512))
    df = pd.read_csv(args.input_csv, low_memory=False)
    if args.max_rows is not None:
        df = df.head(args.max_rows).copy()
    if "anatomic_status" in df.columns:
        df = df[df["anatomic_status"].astype(str).eq("ok")].copy()
    df = df.reset_index(drop=True)

    device = torch.device(args.device)
    blur_sigma = args.input_blur_sigma
    if blur_sigma is None:
        blur_sigma = float(config.get("model", {}).get("input_blur_sigma", 0.0) or 0.0)
    model, hub_model = build_model(config, device)
    dataset = RegionFeatureDataset(df, image_size, blur_sigma=blur_sigma)
    loader = DataLoader(
        dataset,
        batch_size=args.batch_size,
        shuffle=False,
        num_workers=args.num_workers,
        pin_memory=torch.cuda.is_available(),
        collate_fn=collate,
    )

    all_features: list[np.ndarray] = []
    scalar_rows: list[dict[str, float]] = []
    feature_names: list[str] | None = None
    with torch.no_grad():
        for step, batch in enumerate(loader, start=1):
            images = batch["images"].to(device=device, dtype=torch.float32, non_blocking=True)
            outputs = model.get_intermediate_layers(
                images,
                n=list(args.layer_indices),
                reshape=True,
                norm=True,
            )
            if not isinstance(outputs, (tuple, list)):
                outputs = [outputs]
            for item_pos, row_idx in enumerate(batch["indices"]):
                row = df.iloc[row_idx]
                vectors: list[np.ndarray] = []
                names: list[str] = []
                scalars: dict[str, float] = {}
                for layer_pos, layer_feature in zip(args.layer_indices, outputs):
                    layer_vectors, layer_names, layer_scalars = region_features_for_row(
                        layer_feature[item_pos],
                        row,
                        prefix=f"layer{layer_pos}",
                    )
                    vectors.extend(layer_vectors)
                    names.extend(layer_names)
                    scalars.update(layer_scalars)
                feature_vec = np.concatenate(vectors).astype(np.float32)
                all_features.append(feature_vec)
                scalar_rows.append(scalars)
                if feature_names is None:
                    names_expanded: list[str] = []
                    dim_per_vector = len(vectors[0])
                    for name in names:
                        names_expanded.extend([f"{name}_{dim}" for dim in range(dim_per_vector)])
                    feature_names = names_expanded
            if step % 20 == 0:
                print(f"[cache] batches={step}, rows={len(all_features)}/{len(df)}", flush=True)

    x = np.stack(all_features).astype(np.float32)
    scalar_df = pd.DataFrame(scalar_rows)
    manifest_cols = [
        "sample_id",
        "patient_id",
        "label",
        "class_label",
        "T_stage",
        "source",
        "split",
        "image_path",
    ]
    manifest = df[[col for col in manifest_cols if col in df.columns]].copy()
    manifest = pd.concat([manifest.reset_index(drop=True), scalar_df.reset_index(drop=True)], axis=1)
    np.savez_compressed(
        out_npz,
        features=x,
        feature_names=np.array(feature_names or [], dtype=object),
        sample_ids=manifest.get("sample_id", pd.Series(range(len(manifest)))).astype(str).to_numpy(),
        patient_ids=manifest.get("patient_id", pd.Series([""] * len(manifest))).astype(str).to_numpy(),
        labels=pd.to_numeric(manifest.get("class_label", manifest.get("label")), errors="coerce").fillna(-1).astype(int).to_numpy(),
    )
    manifest.to_csv(out_manifest, index=False)
    summary = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "input_csv": str(args.input_csv),
        "config": str(args.config),
        "hub_model": hub_model,
        "image_size": image_size,
        "layer_indices": args.layer_indices,
        "rows": int(len(df)),
        "feature_dim": int(x.shape[1]),
        "npz": str(out_npz),
        "manifest": str(out_manifest),
    }
    (args.output_dir / "feature_cache_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
