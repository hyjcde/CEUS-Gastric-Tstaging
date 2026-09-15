#!/usr/bin/env bash
# GPU queue: continue gentle DINOv3 US-SSL from the 10-epoch checkpoint to
# 30 epochs total (same peak lr 1e-5 per user instruction 2026-09-15 21:48;
# cosine schedule recomputed over the longer horizon), then chain the
# downstream eval (export backbone -> T-stage cls -> lesion seg).
# setsid+nohup safe. Base miniconda env.
set -euo pipefail
ROOT=/data/research/gastric/GastricTstaging
cd "$ROOT"
export PATH="/home/hyj/miniconda3/bin:$PATH"

TAG=gentle_cont
LOG=logs/queue_${TAG}.log
mkdir -p logs
echo "[queue-$TAG] started $(date '+%F %T')" | tee -a "$LOG"

# --- wait for any running train/eval proc (v2 gentle seg) to free the GPUs
while pgrep -f "train_dinov3_roi_lora_seg.py|train_dinov3_roi_lora_mlp.py|pretrain_dinov3_us_ssl.py" >/dev/null 2>&1; do
    echo "[queue-$TAG] waiting for running train proc ... $(date '+%T')" | tee -a "$LOG"
    sleep 60
done

echo "[queue-$TAG] launching gentle continuation (30 ep total, auto-resume) $(date '+%F %T')" | tee -a "$LOG"
torchrun --nproc_per_node=2 scripts/pretrain_dinov3_us_ssl.py \
    --config-file configs/pretrain/dinov3_vitb16_us_ssl_v2_gentle_cont.yaml \
    --output-dir pipeline/experiments/tree/pretrain_dinov3_vitb16_us_ssl_v2_gentle \
    >> logs/pretrain_us_ssl_v2_gentle_cont.log 2>&1

echo "[queue-$TAG] pretrain done, chaining downstream eval $(date '+%F %T')" | tee -a "$LOG"
bash scripts/run_us_ssl_downstream_eval.sh \
    pipeline/experiments/tree/pretrain_dinov3_vitb16_us_ssl_v2_gentle \
    us_ssl_v2_gentle_cont >> logs/queue_${TAG}.log 2>&1

echo "[queue-$TAG] ALL DONE $(date '+%F %T')" | tee -a "$LOG"
