#!/usr/bin/env bash
# Watchdog for the gentle DINOv3 continuation (30 ep = 54,000 iters).
#
# 2026-09-15 的教训：queue_gentle_cont.sh 被 SIGHUP/SIGTERM 带走后，下游两个
# 队列会一直"等待 ALL DONE"而静默停摆 4 天。本脚本每 5 分钟检查一次：若
# 预训练进程消失、但 iter 尚未到 30 ep，则重新拉起队列（自动 resume 最新 ckpt）。
#
# 安全条件（三者同时满足才重启）：
#   1) 无 pretrain_dinov3_us_ssl.py 进程
#   2) 无 queue_gentle_cont.sh 进程
#   3) training_metrics 最新 iter < 54000
set -uo pipefail
ROOT=/data/research/gastric/GastricTstaging
cd "$ROOT"
LOG=logs/watch_gentle_cont.log
METRICS=pipeline/experiments/tree/pretrain_dinov3_vitb16_us_ssl_v2_gentle/training_metrics.json
TARGET_ITER=54000

echo "[watch] started $(date '+%F %T')" >> "$LOG"
while true; do
    sleep 300
    if pgrep -f "train_dinov3_roi_lora_seg.py|train_dinov3_roi_lora_mlp.py|pretrain_dinov3_us_ssl.py" >/dev/null 2>&1; then
        continue   # 训练或下游 eval 在跑，正常
    fi
    if pgrep -f "queue_gentle_cont.sh" >/dev/null 2>&1; then
        continue   # 队列脚本还在（可能在下游链路里），别插手
    fi
    LAST=$(tail -1 "$METRICS" 2>/dev/null | /home/hyj/miniconda3/bin/python3 -c "
import json,sys
try:
    print(json.loads(sys.stdin.read().strip().splitlines()[-1])['iteration'])
except Exception:
    print(0)
" 2>/dev/null || echo 0)
    if [ "${LAST:-0}" -ge "$TARGET_ITER" ]; then
        echo "[watch] iter $LAST >= $TARGET_ITER, 30 ep 已达，退出 $(date '+%F %T')" >> "$LOG"
        exit 0
    fi
    echo "[watch] 检测到停摆 (iter=$LAST)，重新拉起队列 $(date '+%F %T')" >> "$LOG"
    setsid nohup bash scripts/queue_gentle_cont.sh >/dev/null 2>&1 </dev/null &
    disown
    sleep 120
done
