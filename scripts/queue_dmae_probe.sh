#!/usr/bin/env bash
# Probe queue: after the dmae_us200 chain finishes, run the section-3-style
# frozen-feature probe (NO seg-ckpt overlay -- the clean backbone-level read) for
#   1) dmae_us200 encoder (timm backend, blurred input sigma=1.1 per transfer protocol)
#   2) us_ssl_v2_gentle student (dinov3 hub, no blur) -- completes the gentle record
# Then run the trainset feature eval for both and drop reports under
# pipeline/experiments/reports/{dmae_us200_probe,us_ssl_v2_gentle_probe}/.
set -euo pipefail
ROOT=/data/research/gastric/GastricTstaging
cd "$ROOT"
export PATH="/home/hyj/miniconda3/bin:$PATH"
PY=/home/hyj/miniconda3/bin/python3

LOG=logs/queue_dmae_probe.log
mkdir -p logs
echo "[queue-probe] started $(date '+%F %T')" | tee -a "$LOG"

# --- 0) wait for the dmae chain ------------------------------------------
while ! grep -q "ALL DONE" logs/queue_dmae_us200.log 2>/dev/null; do
    echo "[queue-probe] waiting for dmae chain ... $(date '+%T')" | tee -a "$LOG"
    sleep 300
done
while pgrep -f "train_dinov3_roi_lora_seg.py|train_dinov3_roi_lora_mlp.py|main_pretrain.py" >/dev/null 2>&1; do
    echo "[queue-probe] waiting for running proc ... $(date '+%T')" | tee -a "$LOG"
    sleep 60
done
echo "[queue-probe] GPUs free $(date '+%F %T')" | tee -a "$LOG"
sleep 5

# --- 1) filter clinical CSVs to rows with existing images -----------------
REGION_DIR=pipeline/data/tstaging_4class_region_contrastive_full/regions
PROSP_DIR=pipeline/data/tstaging_4class_prospective_full_anatomic/regions
WORK=pipeline/experiments/reports/dmae_probe_inputs
mkdir -p "$WORK"
"$PY" - <<'EOF' >>"$LOG" 2>&1
import pandas as pd
from pathlib import Path
ROOT = Path("/data/research/gastric/GastricTstaging")
WORK = ROOT / "pipeline/experiments/reports/dmae_probe_inputs"
pairs = {
    "train": ROOT / "pipeline/data/tstaging_4class_region_contrastive_full/regions/train_clinical.csv",
    "val": ROOT / "pipeline/data/tstaging_4class_region_contrastive_full/regions/val_clinical.csv",
    "test": ROOT / "pipeline/data/tstaging_4class_prospective_full_anatomic/regions/test_prospective_full_clinical.csv",
}
for name, src in pairs.items():
    df = pd.read_csv(src, low_memory=False)
    def ok(p):
        p = Path(str(p))
        return p.exists() or (ROOT / p).exists()
    keep = df["image_path"].map(ok)
    out = WORK / f"{name}_existing.csv"
    df.loc[keep].to_csv(out, index=False)
    print(f"[filter] {name}: {int(keep.sum())}/{len(df)} rows with existing images -> {out}", flush=True)
EOF

FEAT=pipeline/data/dinov3_tstaging_region_features
DMAE_CFG=configs/segmentation/dinov3/vitb16_dmae_us200.yaml
GENTLE_CFG=configs/segmentation/dinov3/vitb16_us_ssl_v2_gentle.yaml

cache () {  # cache <tag> <config> <split> <input_csv>
    local TAG=$1 CFG=$2 SPLIT=$3 CSV=$4
    local OUT=$FEAT/${SPLIT}_${TAG}
    if [ -f "$OUT/frame_dinov3_region_features.npz" ]; then
        echo "[queue-probe] cache exists, skip: $OUT" | tee -a "$LOG"
        return
    fi
    echo "[queue-probe] cache $TAG $SPLIT $(date '+%T')" | tee -a "$LOG"
    "$PY" scripts/cache_dinov3_tstaging_region_features.py \
        --input-csv "$CSV" --config "$CFG" --output-dir "$OUT" \
        --batch-size 8 --num-workers 4 >>"$LOG" 2>&1
}

# --- 2) dmae probe features (blurred input via config) ---------------------
cache dmae_us200 "$DMAE_CFG" train "$WORK/train_existing.csv"
cache dmae_us200 "$DMAE_CFG" val "$WORK/val_existing.csv"
cache dmae_us200 "$DMAE_CFG" internal_prospective_full "$WORK/test_existing.csv"

# --- 3) gentle probe features (dinov3 hub, no blur) ------------------------
cache us_ssl_v2_gentle "$GENTLE_CFG" train "$WORK/train_existing.csv"
cache us_ssl_v2_gentle "$GENTLE_CFG" val "$WORK/val_existing.csv"
cache us_ssl_v2_gentle "$GENTLE_CFG" internal_prospective_full "$WORK/test_existing.csv"

# --- 4) evals ---------------------------------------------------------------
for TAG in dmae_us200 us_ssl_v2_gentle; do
    echo "[queue-probe] eval $TAG $(date '+%T')" | tee -a "$LOG"
    "$PY" scripts/run_dinov3_trainset_feature_eval.py \
        --train-feature-dir "$FEAT/train_${TAG}" \
        --val-feature-dir "$FEAT/val_${TAG}" \
        --test-feature-dir "$FEAT/internal_prospective_full_${TAG}" \
        --output-dir "pipeline/experiments/reports/${TAG}_probe" >>"$LOG" 2>&1
done

echo "[queue-probe] ALL DONE $(date '+%F %T')" | tee -a "$LOG"
