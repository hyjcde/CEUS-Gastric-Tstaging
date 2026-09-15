#!/usr/bin/env bash
# GPU queue: Deblurring-MAE US pretraining (200 ep trial) + downstream chain.
# Waits for the us_ssl_v2 gentle queue (queue_us_ssl_v2_tonight.sh) to finish,
# then:
#   1) build blurred dataset copy (if missing)
#   2) dmae_vit_base_patch16 pretraining on 173k gastric US frames
#   3) export timm encoder
#   4) T-stage classification (timm backend, blurred input sigma=1.1)
#   5) lesion segmentation (timm backend, blurred input sigma=1.1)
# setsid+nohup safe. Base miniconda env.
set -euo pipefail
ROOT=/data/research/gastric/GastricTstaging
cd "$ROOT"
export PATH="/home/hyj/miniconda3/bin:$PATH"
PY=/home/hyj/miniconda3/bin/python3

TAG=dmae_us200
LOG=logs/queue_${TAG}.log
mkdir -p logs
echo "[queue-$TAG] started $(date '+%F %T')" | tee -a "$LOG"

# --- 0) wait for the v2 gentle queue to finish ---------------------------
while ! grep -q "ALL DONE" logs/queue_gentle_cont.log 2>/dev/null; do
    echo "[queue-$TAG] waiting for us_ssl_v2 queue ... $(date '+%T')" | tee -a "$LOG"
    sleep 300
done
while pgrep -f "train_dinov3_roi_lora_seg.py|train_dinov3_roi_lora_mlp.py|pretrain_dinov3_us_ssl.py" >/dev/null 2>&1; do
    echo "[queue-$TAG] waiting for running train proc ... $(date '+%T')" | tee -a "$LOG"
    sleep 60
done
echo "[queue-$TAG] GPUs free $(date '+%F %T')" | tee -a "$LOG"
sleep 5

# --- 1) blurred dataset copy ---------------------------------------------
if [ ! -f data/pretrain/us_ssl_v2_mae_deblur/blur_manifest.json ]; then
    echo "[queue-$TAG] building blurred dataset $(date '+%F %T')" | tee -a "$LOG"
    nice -n 19 "$PY" scripts/make_us_ssl_blurred_copy.py >>"$LOG" 2>&1
fi

# --- 2) deblur-MAE pretraining -------------------------------------------
PRE_OUT=pipeline/experiments/tree/pretrain_dmae_vitb16_us200
echo "[queue-$TAG] pretrain -> $PRE_OUT $(date '+%F %T')" | tee -a "$LOG"
bash scripts/pretrain_dmae_us.sh 200 "$PRE_OUT" >>"$LOG" 2>&1
echo "[queue-$TAG] pretrain done $(date '+%F %T')" | tee -a "$LOG"

# --- 3) export timm encoder ----------------------------------------------
CKPT=$(ls "$PRE_OUT"/checkpoint-*.pth | sed 's/.*checkpoint-\([0-9]*\)\.pth/\1 &/' | sort -n | tail -1 | cut -d' ' -f2)
WEIGHTS=artifacts/model_weights/dmae_vitb16_us200_encoder.pth
echo "[queue-$TAG] export $CKPT -> $WEIGHTS $(date '+%F %T')" | tee -a "$LOG"
"$PY" scripts/export_dmae_encoder.py --ckpt "$CKPT" --output "$WEIGHTS" >>"$LOG" 2>&1

# --- 4) downstream: classification then segmentation ----------------------
STAMP=$(date +%Y%m%d)
CLS_OUT="pipeline/experiments/reports/dinov3_roi_lora_mlp/${TAG}_${STAMP}"
echo "[queue-$TAG] classification -> $CLS_OUT $(date '+%F %T')" | tee -a "$LOG"
"$PY" scripts/train_dinov3_roi_lora_mlp.py \
    --config configs/segmentation/dinov3/vitb16_${TAG}.yaml \
    --output-dir "$CLS_OUT" >>"$LOG" 2>&1

echo "[queue-$TAG] segmentation $(date '+%F %T')" | tee -a "$LOG"
"$PY" scripts/train_dinov3_roi_lora_seg.py \
    --config configs/segmentation/dinov3/vitb16_roi_lora_mlp_512_m025_all12_${TAG}.yaml \
    --exp-name "${TAG}_${STAMP}" \
    --data-parallel --batch-size 4 >>"$LOG" 2>&1

echo "[queue-$TAG] ALL DONE $(date '+%F %T')" | tee -a "$LOG"
