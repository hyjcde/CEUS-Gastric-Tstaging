#!/usr/bin/env bash
# Deblurring MAE (MICCAI 2023, arXiv:2306.08249) pretraining on gastric US frames.
#
# Recipe (paper + official repo MembrAI/DeblurringMIM):
#   Gaussian blur sigma=1.1 applied BEFORE random masking; reconstruct the
#   ORIGINAL clean image; MSE over ALL patches (models_dmae forward_loss).
#   ViT-B/16, mask 0.75, input 224, AdamW blr 1.5e-4 (eff = blr * global_batch/256),
#   wd 0.05, betas (0.9, 0.95), cosine, RandomResizedCrop(0.2-1.0) + hflip.
# Paper used 12000 ep on 10.7k images (~1.28e8 samples); 200 ep on 173k frames
# is ~3.5e7 samples -- a budgeted trial; extend with --resume if the curve pays off.
#
# Usage:
#   bash scripts/pretrain_dmae_us.sh [epochs] [out_dir]
set -euo pipefail
ROOT=/data/research/gastric/GastricTstaging
cd "$ROOT"
export PATH="/home/hyj/miniconda3/bin:$PATH"

EPOCHS=${1:-200}
OUT=${2:-pipeline/experiments/tree/pretrain_dmae_vitb16_us200}
DATA=data/pretrain/us_ssl_v2_mae_deblur

mkdir -p "$OUT"
torchrun --nproc_per_node=2 external/DeblurringMIM/main_pretrain.py \
    --model dmae_vit_base_patch16 \
    --data_path_blurred "$DATA/blurred" \
    --data_path_orig "$DATA/orig" \
    --input_size 224 \
    --mask_ratio 0.75 \
    --batch_size 128 \
    --blr 1.5e-4 \
    --weight_decay 0.05 \
    --warmup_epochs 5 \
    --epochs "$EPOCHS" \
    --num_workers 10 \
    --output_dir "$OUT" \
    2>&1 | tee -a "$OUT/pretrain_log.txt"
