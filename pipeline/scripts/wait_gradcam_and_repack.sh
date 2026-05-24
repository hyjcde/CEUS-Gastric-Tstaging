#!/usr/bin/env bash
# Wait for prospective Grad-CAM to finish, resume remaining rows, rebuild folder bundle.
set -euo pipefail
ROOT="/data/research/gastric/GastricTstaging"
EXP="$ROOT/pipeline/experiments/tree/gastric_tstage_4class/classification/dual_mask4ch/tstaging_4class_dual_v2_mask4ch_clinical22_full_20260423_092301"
CSV="$EXP/gradcam_test_prospective_full/gradcam_results.csv"
TARGET=2430
LOG="/tmp/gradcam_repack_followup.log"

echo "[$(date -Is)] waiting for run_4class_gradcam to exit..." | tee -a "$LOG"
while pgrep -f "run_4class_gradcam.py.*gradcam_test_prospective_full" >/dev/null; do
  n=$(($(wc -l < "$CSV") - 1))
  echo "[$(date -Is)] progress: $n / $TARGET" | tee -a "$LOG"
  sleep 120
done

echo "[$(date -Is)] gradcam process finished" | tee -a "$LOG"
cd "$ROOT"

echo "[$(date -Is)] resume + repack..." | tee -a "$LOG"
python3 pipeline/scripts/batch_gradcam_test_sets_and_pack.py \
  --splits test_prospective \
  --resume \
  2>&1 | tee -a "$LOG"

python3 pipeline/scripts/batch_gradcam_test_sets_and_pack.py \
  --skip-run \
  --refresh-pack \
  2>&1 | tee -a "$LOG"

n=$(($(wc -l < "$CSV") - 1))
echo "[$(date -Is)] done. prospective rows=$n" | tee -a "$LOG"
echo "[$(date -Is)] deliverable folder: $EXP/gradcam_clinical_screening" | tee -a "$LOG"
echo "[$(date -Is)] open: $EXP/gradcam_clinical_screening/gradcam_screening.html" | tee -a "$LOG"
ls -la "$EXP/gradcam_clinical_screening/" | tee -a "$LOG"
