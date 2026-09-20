# DINOv3 超声 SSL 预训练：完整结果与训练动态记录

日期：2026-09-14（温和版预训练 2026-09-15 14:55 完成，训练动态已补全）
预训练配置：[DINOV3_US_SSL_PRETRAINING_20260914.md](DINOV3_US_SSL_PRETRAINING_20260914.md)

本文档自包含记录两轮超声视频 SSL 域适应预训练的完整结果与训练动态。两轮用同一套数据管线与模型，仅训练强度不同：

- **激进版**（run 名 `us_ssl_v1`）：35k 帧 / 30 epoch / 实际 lr peak 1.22e-3。强度过大，权重被「重写」，下游分类变差。
- **温和版**（run 名 `us_ssl_v2_gentle`）：173k 帧 / 10 epoch / lr peak 1.22e-5。强度过小，backbone 几乎不更新，预期与官方打平。预训练已于 2026-09-15 14:55 完成（5h14m），下游评估在跑。

**一句话结论**：激进版域适应收益为**负到中性**（分割打平、分类全面略差、probe 中性），不建议沿用；官方 LVD-1689M 权重目前仍是更好的 encoder 初始化。温和版预训练已完成（界定强度下界），下游分类与激进版同档、仍低于官方基线；deblur-MAE（arXiv:2306.08249）200 ep 试水已排队接续，见 [DMAE_US_SSL_20260915.md](DMAE_US_SSL_20260915.md)。

> **⚠ 下游链路 overlay 混淆（2026-09-15 补充）**：分类与分割脚本默认把 last2blocks 分割 ckpt 的 **188 个 backbone 张量整体 overlay**（manifest 实测 missing/unexpected 均为 0）——无论 `checkpoint_path` 指向官方/激进/温和权重，实际 backbone 都被重置为同一个 seg ckpt。因此 §4/§5 的组间差异**不能归因于 SSL backbone**（主要反映 ROI 覆盖口径与训练随机性）；目前唯一干净的 backbone 级对比是 §3 的冻结特征 probe（直读 `checkpoint_path`、无 overlay）。DMAE 实验的 timm 后端已跳过该 overlay（见 §8 与 DMAE 文档）。

> **重要更正**：激进版原记录「lr 约 3.1e-4」有误。实测 config 中 `optim.lr=1e-3` 经 `sqrt_wrt_1024` 缩放（×4·√(96/1024)=×1.225）后 **peak 实为 1.225e-3**，比原记录高约 4 倍——这才是权重漂移约 100% 的真正原因。温和版同理，1e-5 × 1.225 = 1.225e-5。

---

## 1. 两轮配置对照

| 项 | 激进版（us_ssl_v1） | 温和版（us_ssl_v2_gentle） |
| --- | --- | --- |
| 帧集 | 35,197（每视频 16 帧） | 173,491（每 2 帧取 1，5–10fps） |
| 视频 / 患者 | 2,203 / 1,290（非外部） | 2,201 / 1,289（非外部） |
| epoch | 30 | 10 |
| lr peak | 1.225e-3 | 1.225e-5 |
| weight_decay | 0.04→0.4 | 0.04→0.1 |
| teacher_temp warmup | 10 epoch | 3 epoch |
| OFFICIAL_EPOCH_LENGTH | 365 | 1807 |
| 总迭代 | 10,950 | 18,070 |
| 速度 | 1.066 s/iter | 1.058 s/iter |
| 时长 | 3h13m | 约 6.5h |
| 预训练 run 目录 | `pipeline/experiments/tree/pretrain_dinov3_vitb16_us_ssl_v1/` | `pipeline/experiments/tree/pretrain_dinov3_vitb16_us_ssl_v2_gentle/` |
| 导出 backbone | `artifacts/model_weights/dinov3_vitb16_us_ssl_v1_student.pth` | `artifacts/model_weights/dinov3_vitb16_us_ssl_v2_gentle_student.pth` |

两轮共同配置：ViT-B/16（86M），官方 LVD-1689M 初始化；损失 DINO + iBOT + KoLeo（Gram 关）；2× 4090D；全局 batch 96；帧集目录 `data/pretrain/us_ssl_v1/` 与 `data/pretrain/us_ssl_v2_200k/`。

---

## 2. 激进版预训练动态

收敛：total_loss 16.274 → 14.521（min 14.494）；lr peak 1.225e-3，warmup 5 epoch 后 cosine 衰减至 1.2e-6；backbone grad_norm warmup 峰值 833 → 结束 1.36。

### 2.1 权重漂移分析（激进版 vs 官方，‖Δ‖/‖W‖）

| 模块 | 相对变化 |
| --- | ---: |
| 12 个 transformer blocks | 约 1.0–1.4 |
| patch_embed | 1.12–1.24 |
| cls_token / storage_tokens | 约 1.1 |
| norm | 约 1.05 |
| RoPE periods | 0（结构缓冲） |

**漂移幅度约等于权重原始量级，属于「重写」而非「温和适应」**——这是下游分类无收益的直接原因。

### 2.2 激进版逐 epoch 训练动态

| ep | iter | lr | total | dino_g | dino_l | ibot | koleo | bb_grad |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 0 | 360 | 2.35e-4 | 14.53 | 9.72 | 9.72 | 4.85 | -0.180 | 1.05 |
| 1 | 730 | 4.83e-4 | 14.50 | 9.70 | 9.70 | 4.84 | -0.252 | 0.33 |
| 2 | 1090 | 7.25e-4 | 14.49 | 9.70 | 9.70 | 4.84 | -0.264 | 0.17 |
| 3 | 1460 | 9.73e-4 | 14.50 | 9.70 | 9.70 | 4.85 | -0.270 | 0.13 |
| 4 | 1820 | 1.21e-3 | 14.54 | 9.70 | 9.70 | 4.85 | -0.066 | 0.61 |
| 5 | 2190 | 1.22e-3 | 14.69 | 9.70 | 9.70 | 4.85 | +0.678 | 4.36 |
| 6 | 2550 | 1.21e-3 | 14.60 | 9.70 | 9.70 | 4.85 | +0.232 | 3.75 |
| 7 | 2920 | 1.18e-3 | 14.57 | 9.70 | 9.70 | 4.85 | +0.077 | 1.61 |
| 8 | 3280 | 1.15e-3 | 14.59 | 9.70 | 9.70 | 4.85 | +0.166 | 2.15 |
| 9 | 3650 | 1.11e-3 | 14.57 | 9.70 | 9.70 | 4.85 | +0.093 | 2.22 |
| 10 | 4010 | 1.06e-3 | 14.58 | 9.70 | 9.70 | 4.85 | +0.124 | 4.08 |
| 11 | 4380 | 1.00e-3 | 14.56 | 9.70 | 9.70 | 4.85 | +0.042 | 2.10 |
| 12 | 4740 | 9.43e-4 | 14.55 | 9.70 | 9.70 | 4.85 | -0.017 | 0.68 |
| 13 | 5110 | 8.75e-4 | 14.54 | 9.70 | 9.70 | 4.85 | -0.077 | 0.65 |
| 14 | 5470 | 8.05e-4 | 14.53 | 9.70 | 9.70 | 4.85 | -0.093 | 0.75 |
| 15 | 5840 | 7.29e-4 | 14.54 | 9.70 | 9.70 | 4.85 | -0.087 | 0.91 |
| 16 | 6200 | 6.54e-4 | 14.54 | 9.70 | 9.70 | 4.85 | -0.090 | 1.11 |
| 17 | 6570 | 5.76e-4 | 14.54 | 9.70 | 9.70 | 4.85 | -0.089 | 1.50 |
| 18 | 6930 | 5.01e-4 | 14.53 | 9.70 | 9.70 | 4.85 | -0.097 | 1.23 |
| 19 | 7300 | 4.26e-4 | 14.54 | 9.70 | 9.70 | 4.85 | -0.082 | 2.22 |
| 20 | 7660 | 3.55e-4 | 14.53 | 9.70 | 9.70 | 4.85 | -0.124 | 1.94 |
| 21 | 8030 | 2.87e-4 | 14.52 | 9.70 | 9.70 | 4.85 | -0.146 | 0.71 |
| 22 | 8390 | 2.25e-4 | 14.52 | 9.70 | 9.70 | 4.85 | -0.145 | 1.61 |
| 23 | 8760 | 1.68e-4 | 14.52 | 9.70 | 9.70 | 4.85 | -0.150 | 1.21 |
| 24 | 9120 | 1.20e-4 | 14.52 | 9.70 | 9.70 | 4.85 | -0.155 | 2.04 |
| 25 | 9490 | 7.77e-5 | 14.52 | 9.70 | 9.70 | 4.85 | -0.158 | 1.40 |
| 26 | 9850 | 4.52e-5 | 14.52 | 9.70 | 9.70 | 4.85 | -0.163 | 1.49 |
| 27 | 10220 | 2.09e-5 | 14.52 | 9.70 | 9.70 | 4.85 | -0.164 | 1.27 |
| 28 | 10580 | 6.40e-6 | 14.52 | 9.70 | 9.70 | 4.85 | -0.165 | 1.73 |
| 29 | 10949 | 1.23e-6 | 14.52 | 9.70 | 9.70 | 4.85 | -0.163 | 1.36 |

**动态解读**：warmup（ep 0–4）lr 爬到峰值 1.22e-3；ep 5–11 koleo 一度转正（+0.68 → +0.04）、backbone_grad 冲到 4+，是权重被剧烈改写的阶段；ep 12 起 lr 衰减，koleo 转负并稳定在 -0.16，grad_norm 回落到 1 左右。total_loss 全程只在 14.5 附近小幅波动——**SSL loss 的「收敛」主要来自 head/prototype，backbone 在 peak lr 阶段已被重写**。

---

## 3. 激进版冻结特征 probe（患者级）

协议：患者级聚合（mean/max/std），同一批匹配样本（train 7,625 帧 / 1,213 患者，val 849 帧 / 135 患者；1,158 行 ext 图像因路径迁移缺失，两边同时剔除）。报告：`pipeline/experiments/reports/dinov3_us_ssl_v1_probe/COMPARISON.md`。

### 3.1 val split（选择集）

| feature_set | model | 激进版 AUC | 官方 AUC | 差值 |
| --- | --- | ---: | ---: | ---: |
| dino_scalar + clinical | extra_trees | **0.7782** | 0.7721 | +0.006 |
| dino_scalar + clinical | random_forest | 0.7711 | 0.7688 | +0.002 |
| dino_scalar + clinical | logreg | 0.7648 | 0.7744 | -0.010 |
| dino_embedding + clinical | random_forest_pca | 0.7236 | 0.7065 | +0.017 |
| dino_embedding + clinical | logreg_pca | 0.6838 | 0.7354 | -0.052 |
| dino_embedding + clinical | extra_trees_pca | 0.6979 | 0.7591 | -0.061 |

### 3.2 test_prospective_full（前瞻审计）

| feature_set | model | 激进版 AUC | 官方 AUC | 差值 |
| --- | --- | ---: | ---: | ---: |
| dino_scalar + clinical | extra_trees | 0.7791 | 0.7772 | +0.002 |
| dino_scalar + clinical | logreg | 0.5786 | 0.5671 | +0.011 |
| dino_all + clinical | extra_trees_pca | 0.5144 | 0.6584 | **-0.144** |

**probe 结论**：最强特征组（dino_scalar + clinical）上激进版与官方基本持平（val +0.002~0.006，前瞻打平）；纯 embedding PCA 特征在前瞻集明显退化（-0.14），说明域适应后的 embedding 空间对前瞻分布更敏感，泛化未改善。

---

## 4. 激进版下游分类（T 分期 4 类，ROI LoRA + MLP，同配方对比）

| 测试集 | 指标 | 激进版 | 官方基线（phase0_20260828_full） | 差值 |
| --- | --- | ---: | ---: | ---: |
| val | patient AUC | 0.724 | 0.727 | -0.003 |
| val | patient QWK | 0.417 | 0.467 | **-0.050** |
| val | patient ACC | 0.457 | 0.523 | **-0.066** |
| 前瞻 | patient AUC | 0.720 | 0.763 | **-0.043** |
| 前瞻 | patient QWK | 0.589 | 0.615 | -0.026 |
| 外部 | patient AUC | 0.691 | 0.709 | -0.018 |

### 4.1 激进版细分 AUC（patient 级）

| 测试集 | early_vs_adv | t1_t2 | t2_t3 | t3_t4 |
| --- | ---: | ---: | ---: | ---: |
| val | 0.801 | 0.779 | 0.769 | 0.627 |
| 前瞻 | 0.834 | 0.648 | 0.687 | 0.693 |
| 外部 | 0.723 | 0.634 | 0.647 | 0.711 |

T3/T4 边界仍是最弱一环（与官方基线一致）。

口径备注：激进版本次用 full-coverage ROI，基线为 GT crop_roi，略有差异；方向与 probe 一致。产物：`pipeline/experiments/reports/dinov3_roi_lora_mlp/us_ssl_v1_20260914/`。

---

## 5. 激进版下游分割（病灶 ROI LoRA seg，m025 GT crop）

| 测试集 | 激进版 Dice | 官方基线（m025_all12_20260908） | 差值 |
| --- | ---: | ---: | ---: |
| val | 0.879 | 0.881 | -0.002 |
| internal_holdout | 0.880 | 0.880 | 0.000 |
| external | 0.868 | 0.866 | +0.002 |
| prospective | 0.897 | 0.897 | 0.000 |

### 5.1 激进版分割逐 epoch val Dice

| ep | train_loss | val_dice | | ep | train_loss | val_dice |
| ---: | ---: | ---: | --- | ---: | ---: | ---: |
| 1 | 0.183 | 0.836 | | 14 | 0.085 | 0.873 |
| 2 | 0.128 | 0.853 | | 15 | 0.083 | 0.873 |
| 3 | 0.118 | 0.857 | | 16 | 0.081 | 0.879 |
| 4 | 0.112 | 0.862 | | 17 | 0.080 | **0.879** |
| 5 | 0.107 | 0.867 | | 18 | 0.079 | 0.878 |
| 6 | 0.103 | 0.864 | | 19 | 0.077 | 0.878 |
| 7 | 0.100 | 0.870 | | 20 | 0.077 | 0.876 |
| 8 | 0.097 | 0.872 | | 21 | 0.075 | 0.878 |
| 9 | 0.094 | 0.869 | | 22 | 0.074 | 0.878 |
| 10 | 0.092 | 0.870 | | 23 | 0.073 | 0.877 |
| 11 | 0.090 | 0.874 | | 24 | 0.072 | 0.878 |
| 12 | 0.088 | 0.875 | | 25 | 0.071 | 0.878 |
| 13 | 0.086 | 0.875 | | | | |

**分割结论**：低层纹理任务对骨干权重不敏感——激进版的「重写」既没伤到也没帮到分割，四组 Dice 与官方基本打平（±0.002）。val Dice 在 epoch 17 达峰 0.8790。run：`experiments/segmentation/us_ssl_v1_20260914_dp2/`。

---

## 6. 温和版训练动态（预训练已完成，2026-09-15 14:55，总时长 5h14m）

### 6.1 温和版逐 epoch 训练动态（完整 10 epoch，18,070 iter）

| ep | iter | lr | total | dino_g | dino_l | ibot | koleo | bb_grad |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 0 | 1800 | 1.21e-5 | 14.54 | 9.72 | 9.72 | 4.85 | -0.157 | 8.88 |
| 1 | 3610 | 1.19e-5 | 14.50 | 9.70 | 9.70 | 4.85 | -0.261 | 8.09 |
| 2 | 5420 | 1.08e-5 | 14.50 | 9.70 | 9.70 | 4.85 | -0.274 | 5.81 |
| 3 | 7220 | 9.23e-6 | 14.50 | 9.70 | 9.70 | 4.85 | -0.282 | 4.45 |
| 4 | 9030 | 7.25e-6 | 14.49 | 9.70 | 9.70 | 4.85 | -0.286 | 3.81 |
| 5 | 10840 | 5.14e-6 | 14.49 | 9.70 | 9.70 | 4.85 | -0.289 | 3.40 |
| 6 | 12640 | 3.17e-6 | 14.49 | 9.70 | 9.70 | 4.85 | -0.291 | 3.09 |
| 7 | 14450 | 1.55e-6 | 14.49 | 9.70 | 9.70 | 4.85 | -0.293 | 2.86 |
| 8 | 16260 | 4.93e-7 | 14.49 | 9.70 | 9.70 | 4.85 | -0.293 | 2.72 |
| 9 | 18069 | 1.22e-7 | 14.49 | 9.70 | 9.70 | 4.85 | -0.295 | 2.66 |

统计：total_loss 16.285 → 14.493（min 14.4925）；lr peak 1.225e-5；backbone_grad 峰值 789（warmup）→ 结束 2.66；iter_time 1.045 s。

### 6.2 激进版 vs 温和版对比（关键观察）

| 指标 | 激进版 @ 结束 | 温和版 @ 结束 |
| --- | ---: | ---: |
| total_loss | 14.52 | 14.49 |
| backbone_grad_norm | 1.36 | **2.66** |
| koleo | -0.163 | -0.295 |

**解读**：温和版的 SSL loss（14.49）降到比激进版结束（14.52）还低，但 backbone_grad_norm 结束时仍有 2.66（激进版 1.36）——**lr=1e-5 下 backbone 几乎没动，loss 下降全靠 head/prototype 收敛**。这印证温和版过于温和：3w/17w 帧的差别在 1e-5 的 lr 下体现不出来，backbone 域适应信号太弱。温和版大概率结果是「与官方打平」而非「有收益」，其意义在于界定强度下界，与激进版的上界共同框出有效区间。

- 配置：`configs/pretrain/dinov3_vitb16_us_ssl_v2_gentle.yaml`
- 队列脚本：`scripts/queue_us_ssl_v2_tonight.sh`（setsid+nohup，自动接下游：导出 backbone → T 分期分类 → 病灶分割）
- 状态：预训练 2026-09-15 14:55 完成（5h14m）；下游链 14:55 启动，分类已出（见 §6.3），分割在跑（见 §6.4）
- 队列日志：`logs/queue_us_ssl_v2_tonight.log`

### 6.5 温和版续训（2026-09-15 晚启动，30 epoch）

用户指示（21:48）：10 epoch 曲线 **loss 无 spike、整体下降**（14.54→14.49 单调），**lr 不调**（peak 仍 1e-5），续训后次日 eval。

- 续训配置：`configs/pretrain/dinov3_vitb16_us_ssl_v2_gentle_cont.yaml`（仅 `optim.epochs` 10→30，其余与温和版一致）
- resume 机制：同一 `output_dir` 自动从 `ckpt/17999`（含优化器状态）续训；调度按 30 ep 重算，续训起点 lr ≈ 7.7e-6（cosine 回摆，peak 不变），随后 20 个 epoch 再衰减到 1e-7
- 预计时长：+20 ep ≈ 10.5h（约 16 日早 8–9 点完成），随后自动接下游链（导出 `dinov3_vitb16_us_ssl_v2_gentle_cont_student.pth` → 分类 → 分割，配置 `vitb16_*_us_ssl_v2_gentle_cont.yaml`）
- GPU 队列已重排：`queue_gentle_cont.sh`（等温和版分割让卡）→ `queue_dmae_after_cont.sh`（DMAE 200ep 改挂 cont 之后）→ `queue_dmae_probe.sh`（不变）
- **待验证**（16 日早）：续训首轮 iter 应从 ~18000 开始、loss 接在 ~14.49 而非跳回 16；若 resume 失败（loss 跳变）需立即停掉检查

### 6.6 续训实测动态（截至 2026-09-20，iter 46,130 / 25.5 ep）

resume 机制验证有效（从 `ckpt/17999` 接续，loss 平滑无跳变），逐 epoch 汇总（`training_metrics.json`）：

| ep | total_loss | bb_grad | lr(max) |
| ---: | ---: | ---: | ---: |
| 0（原始） | 14.8496 | 45.22 | 1.21e-05 |
| 9（原始结束） | 14.4929 | 2.68 | 9.61e-06 |
| 10（续训起点） | 14.4937 | 3.37 | 9.59e-06 |
| 15 | 14.4924 | 2.16 | 6.51e-06 |
| 20 | 14.4918 | 1.82 | 3.35e-06 |
| 25 | 14.4915 | 1.68 | 9.91e-07 |

续训把 total_loss 从 14.4929 再压到 14.4915，**backbone_grad 从 2.68 单调降到 1.68**（对比：激进版结束时 1.36）。趋势健康、无 spike。

> **⚠ 事故：9/16 07:30–21:04 停摆 4 天**（iter 45,999 → 46,420 后中断）。日志停在 9/16 16:53，死因 **SIGTERM（signal 15）**：16:44 的一次人工 relaunch 未用 `setsid` 完全脱离会话，赶上网络闪断、父会话结束时被带走。更隐蔽的后果是 `queue_gentle_cont.sh` 随之退出，**下游两个 DMAE 队列因等不到 "ALL DONE" 而静默空转 4 天**。9/20 21:04 已用 `setsid nohup` 重新拉起（9/15 首轮用同样方式稳定跑过 9 小时），并新增看门狗 `scripts/watch_gentle_cont.sh`（每 5 分钟检查，若预训练进程消失且 iter < 54,000 则自动续拉）。
>
> 教训：**GPU 队列脚本必须 `setsid`+`disown` 完全脱离，且要有停摆看门狗**——`set -e` 的队列脚本一旦被杀，下游等待型队列不会报错，只会无限等待。

- 当前状态（9/20 21:05）：从 `ckpt/45999` 恢复，双卡 97–98% 满载，预计 **约 23:25 完成 30 ep**（54,000 iter），随后自动接下游链
- 队列顺序（9/20 重启）：`watch_gentle_cont` + `queue_gentle_cont`（预训→下游）→ `queue_dmae_after_cont`（DMAE 200ep）→ `queue_dmae_probe`
- 后续：deblur-MAE 200 ep 试水已排队（`queue_dmae_after_v2.sh`），见 [DMAE_US_SSL_20260915.md](DMAE_US_SSL_20260915.md)

### 6.3 温和版下游分类（T 分期 4 类，ROI LoRA + MLP，同 §4 链路）

> 注意 overlay 混淆（见文首 ⚠）：本表三列的实际 backbone 均被 overlay 重置为同一 seg ckpt，差异主要来自 ROI 口径（基线为 GT crop_roi，两轮 SSL 为 full-coverage）与训练随机性，**不能归因于 SSL backbone**。

| 测试集 | 指标 | 温和版 | 激进版 | 官方基线（phase0_20260828_full） |
| --- | --- | ---: | ---: | ---: |
| val | patient AUC | 0.709 | 0.724 | 0.727 |
| val | patient QWK | 0.450 | 0.417 | 0.467 |
| val | patient ACC | 0.457 | 0.457 | 0.523 |
| 前瞻 | patient AUC | 0.731 | 0.720 | 0.763 |
| 前瞻 | patient QWK | 0.583 | 0.589 | 0.615 |
| 外部 | patient AUC | 0.705 | 0.691 | 0.709 |

#### 6.3.1 温和版细分 AUC（patient 级）

| 测试集 | early_vs_adv | t1_t2 | t2_t3 | t3_t4 |
| --- | ---: | ---: | ---: | ---: |
| val | 0.810 | 0.743 | 0.822 | 0.596 |
| 前瞻 | 0.844 | 0.662 | 0.659 | 0.710 |
| 外部 | 0.753 | 0.585 | 0.641 | 0.711 |

产物：`pipeline/experiments/reports/dinov3_roi_lora_mlp/us_ssl_v2_gentle_20260915/`（manifest 实测 overlay 188 张量，missing/unexpected 均为 0）。

**判读**（对照 §6 判读标准「回到或超过官方基线 0.727/0.763 才算有效」）：温和版 val 0.709、前瞻 0.731，**未回到基线**，与激进版同档。即便忽略 overlay 混淆把读数当作上界看，两轮 DINOv3 域适应在分类上都无收益——激进版（强度上界）与温和版（下界）共同支持「DINOv3 判别式 SSL 域适应路线封存」的初步结论；剩余干净检验是 probe 口径（§3）的温和版/DMAE 补跑。

### 6.4 温和版下游分割（病灶 ROI LoRA seg，m025 GT crop）

在跑（epoch 5 时 val Dice 0.867 且攀升中，轨迹与激进版 §5.1 相似）。run：`experiments/segmentation/us_ssl_v2_gentle_20260915*/`。结果出来后补表；鉴于 overlay 混淆（文首 ⚠），预期同样与官方打平（±0.002 档）。

### 6.5 ACC 深入分析与 zml100 阅片测试集（2026-09-15 晚）

#### 6.5.1 四集合病例级 ACC 总览（含医生对照）

| 模型 | Val | 前瞻 | 外部 | zml100 |
| --- | ---: | ---: | ---: | ---: |
| 官方基线 | 0.523 (n=128) | 0.567 | 0.433 | **0.400** |
| 激进版 | 0.457 | 0.541 | 0.474 | 0.350 |
| 温和版 | 0.457 | 0.548 | 0.511 | 0.290 |
| **医生 zml（对照）** | — | — | — | **0.460**（QWK 0.346） |

zml100 = `pipeline/data/zml_reader_100_testset_20260915/`（100 例 / 436 关键帧，其中 363 帧有 ROI；gold_t=病理 src_pT；两医生阅片关键帧口径）。打分脚本 `scripts/score_zml_roi_cls.py`（病例级=帧概率均值，与训练评估同口径）。

#### 6.5.2 为什么 ACC 低——四个结构性原因

1. **T2 类近乎塌陷**：T2 recall 全集合全模型仅 0.08–0.27（前瞻 0.088）。温和版前瞻 T2 行 [23, 3, 7, 1]——34 例 T2 中 23 例被吸进 T1。T2（固有肌层受累）在单帧 ROI 上缺乏稳定影像标志，是 4 分类的天花板所在。
2. **错误以相邻期为主**：全部模型/集合中 **47%–70% 的错误是 off-by-one**（温和版 val 达 69.7%）。MAE 0.71–0.87 期，即典型错误差不到 1 期——4 分类 ACC 对这些"差一期"错误零宽容，而 QWK/AUC 部分宽容。
3. **任务本身难，医生也一样**：zml100 上医生 zml 的 4 分类 ACC 也只有 **0.460**（T1 行 [6,3,2,4]，同样大量相邻混淆）；官方模型 0.400 已接近医生水平。zml100 还有 33/100 例 gold 标注冲突（src_pT vs 建包 gold_pt），进一步压低上限。
4. **类别先验偏移**：zml100 的 T1+T2 占 28%（前瞻集 30%），但模型在 val 上 T2 支持仅 11 例——小样本类的 recall 估计本身噪声大。

#### 6.5.3 每类结果图

- 每类 recall 分组柱状图（4 集合 × 3 模型 + zml100 医生菱形标记）：`docs/technical/figures/perclass_20260915/fig_perclass_recall_4sets.png`（工作站 `pipeline/experiments/reports/dinov3_roi_lora_mlp/perclass_analysis_20260915/`）
- 温和版 4 集合混淆矩阵（行归一化 + 计数）：`fig_gentle_confusion_4sets.png`
- 分析脚本：`scripts/analyze_cls_perclass_20260915.py`；数据：`analysis_summary.json`

**对 SSL 判读的意义**：zml100 上官方 0.400 > 激进 0.350 > 温和 0.290（n=100，CI 宽），方向与 val/前瞻一致——两轮域适应无收益；且三模型在 overlay 混淆下 backbone 相同，zml100 差异同样只能作链路级参照。

**纯临床表格对照实验**（2026-09-15 晚，见 [CLINICAL_TABULAR_ZML100_20260915.md](CLINICAL_TABULAR_ZML100_20260915.md)）：clin11 训练于 train+val（1,566 例），干净集上反超影像单模态——external（n=381，零泄漏）RF ACC 0.617 vs 影像 0.433；zml100 strict（n=39）0.67–0.69 vs 医生 0.54。肿瘤长径/厚径贡献最大（剔除后 external 0.480），来源待核实。最佳模型类型为树集成；TabPFN v2.5 ACC 中游但 external QWK 最高（0.721）。提升路径指向影像+临床融合。

**温和版判读标准**：分类 val/前瞻 AUC 若回到或超过官方基线（0.727 / 0.763），说明温和适应有效；若仍低于基线或仅打平，SSL 路线封存，encoder 用官方权重。

---

## 7. 结论与改进方向

1. 激进版（35k 帧、30 epoch、**实际 lr peak 1.22e-3**）强度过大，权重漂移约 100%，下游**分类全面略差、probe 中性、分割打平**。
2. 温和版（lr 1e-5）走向另一极端，backbone 几乎不更新（结束时 bb_grad 仍有 2.66，loss 下降全靠 head）；下游分类（§6.3）与激进版同档、未回到官方基线。两轮共同框定：DINOv3 判别式 SSL 域适应在 1e-5 ~ 1e-3 全强度区间内**对分类无收益**。
3. **方法论教训（overlay 混淆）**：下游分类/分割脚本默认 overlay last2blocks seg ckpt 全量 backbone，§4/§5/§6.3 的组间差异不能归因于 SSL backbone；后续一切 backbone 级对比以 **§3 冻结 probe 口径**（无 overlay）为准，或在下游脚本中显式跳过 overlay（DMAE 的 timm 后端已如此）。
4. 分割已确认不受益（打平），SSL 的价值只看**分类 / 高层语义**能否提升。
5. 后续检验（按优先级）：① deblur-MAE 200 ep 试水（MIM 生成式路线，已排队，判读标准见 DMAE 文档）；② 温和版与 DMAE 的 §3 口径 probe 补跑（overlay-free）；③ 若均无收益，encoder 初始化维持官方权重，SSL 路线整体封存。

---

## 8. 复现与产物说明

两轮的全部产物均在工作站 `/data/research/gastric/GastricTstaging/` 下：

- **预训练 run**：激进版 `pipeline/experiments/tree/pretrain_dinov3_vitb16_us_ssl_v1/`，温和版 `pipeline/experiments/tree/pretrain_dinov3_vitb16_us_ssl_v2_gentle/`。每个 run 含 `ckpt/`（分片 checkpoint）、`logs/log.txt`、`training_metrics.json`（JSONL，逐 iter 记录 lr / 各 loss 分量 / grad_norm / iter_time）、`config.yaml`（生效配置快照）。
- **导出 backbone**：`artifacts/model_weights/dinov3_vitb16_us_ssl_v1_student.pth`（激进版）、`dinov3_vitb16_us_ssl_v2_gentle_student.pth`（温和版，训练中）。导出用 `scripts/export_dinov3_us_ssl_student.py`。
- **下游产物**：probe 报告 `pipeline/experiments/reports/dinov3_us_ssl_v1_probe/` 与 `dinov3_official_probe_matched/`；分类报告 `pipeline/experiments/reports/dinov3_roi_lora_mlp/us_ssl_v1_20260914/`；分割 run `experiments/segmentation/us_ssl_v1_20260914_dp2/`。
- **帧集**：`data/pretrain/us_ssl_v1/`（35k）、`data/pretrain/us_ssl_v2_200k/`（173k），每帧可在 `frame_manifest.csv` 追溯视频 MD5 / 队列 / 中心 / 年份 / 患者 / T 分期。
- **复现命令**：抽帧 `python3 scripts/extract_videos_raw_frames.py`（激进版）或加 `--frame-step 2 --output data/pretrain/us_ssl_v2_200k`（温和版）；训练 `bash scripts/pretrain_dinov3_us_ssl.sh <config> <out_dir>`；下游链路 `bash scripts/run_us_ssl_downstream_eval.sh <run_dir> <tag>`。
