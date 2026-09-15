# Deblurring MAE 超声 SSL 预训练：方案与配置

日期：2026-09-15
对照实验史：[DINOV3_US_SSL_RESULTS_20260914.md](DINOV3_US_SSL_RESULTS_20260914.md)（DINOv3 域适应：激进版负收益、温和版界定下界）

## 0. 一句话

按 MICCAI 2023《Deblurring Masked Autoencoder is Better Recipe for Ultrasound Image Recognition》（arXiv:2306.08249，Kang et al.）的配方，在自有 173k 胃超声帧上预训练 **deblur-MAE ViT-B/16**（先 200 epoch 试水），用与 DINOv3 系完全同口径的下游链路（ROI LoRA + MLP 分类 / LoRA seg 分割）评估，回答：MIM 生成式 SSL 是否比 DINOv3 判别式 SSL 域适应更适合我们的数据。

## 1. 论文配方要点（严格复现）

| 项 | 值 | 出处 |
| --- | --- | --- |
| 模糊算子 | 灰度图 → `cv2.GaussianBlur((0,0), σ=1.1)` → 存 jpg | 官方 `blurred_images.py` |
| 顺序 | 原图 x → 模糊 xb → 随机 mask 75% → encoder → decoder → 重建**原图 x** | 论文 Eq.1 |
| 损失 | MSE，**所有 patch** 上计算（非仅 masked） | `models_dmae.py forward_loss`（masked-mean 行被注释） |
| norm_pix_loss | False | `main_pretrain.py` 默认 |
| 架构 | ViT-B/16 encoder（86M）+ decoder 512d×8 | `dmae_vit_base_patch16` |
| 优化 | AdamW，blr 1.5e-4（eff = blr × global_batch/256），wd 0.05，β(0.9,0.95)，cosine | 论文附录 Table 1 |
| 增广 | RandomResizedCrop(0.2–1.0, bicubic) + hflip；corr/orig 对用同一随机种子保证**同一裁剪** | `util/dataset_us.py CorruptDataset` |
| **迁移协议** | 下游输入同样先模糊（σ=1.1）再进 encoder，防分布偏移 | 论文 §2.2 Eq.4 + README |
| 论文预算 | 12000 ep × 10,675 图 ≈ 1.28e8 样本 | 论文 §3.1 |

## 2. 我们的实例化（200 ep 试水）

| 项 | 值 |
| --- | --- |
| 数据 | `data/pretrain/us_ssl_v2_200k/`（173,491 帧，2,201 视频 / 1,289 患者，非外部）→ 配对副本 `data/pretrain/us_ssl_v2_mae_deblur/`（orig=软链，blurred=实文件；train 172,979 / val 512，seed 0） |
| epoch | 200（≈3.5e7 样本，论文等效预算 ~740 ep 的 1/4；曲线好再 `--resume` 续训） |
| 全局 batch | 256（128 × 2 卡）→ 有效 lr = 1.5e-4 |
| warmup | 5 ep（对齐 MAE 40/1600 = 2.5% 比例） |
| 硬件 | 工作站 2×4090D，预计 ~13–18h |
| run 目录 | `pipeline/experiments/tree/pretrain_dmae_vitb16_us200/` |
| 导出 encoder | `artifacts/model_weights/dmae_vitb16_us200_encoder.pth`（timm 格式，150 tensors，strict 校验） |

## 3. 下游接入：timm 平行后端（关键决策）

MAE 权重是 timm 风格 ViT-B/16（学习式 pos_embed），与 DINOv3 hub（RoPE + 4 storage tokens + LayerScale + bias_mask，188 keys strict）**结构不兼容**。选择新增 timm 平行后端而非硬转 DINOv3 格式（硬转需丢 pos_embed、零初始化 storage tokens，科学上有损）。

改动（工作站仓 `scripts/`）：

- `train_dinov3_roi_lora_mlp.py` / `train_dinov3_roi_lora_seg.py`：新增 `model.backbone_family: timm_mae` 分支——`timm.create_model(vit_base_patch16_224, dynamic_img_size=True)` + strict 加载 encoder；**跳过 seg-ckpt overlay**（否则同名 key 会把 MAE 权重静默覆盖成 DINOv3 seg ckpt，实验作废）；LoRA 注入 `attn.qkv/proj` 与特征提取（`forward_features` / `get_intermediate_layers`）timm 均原生支持。
- `cache_dinov3_tstaging_region_features.py`：`build_model` 加 `timm_mae` 分支、数据集加输入模糊——§3 口径冻结 probe 复用于 DMAE（该 probe 直读 `checkpoint_path`、无 overlay，是**唯一干净的 backbone 级对比**；DINOv3 下游链路的 overlay 混淆见结果文档文首 ⚠）。
- 新增 `--input-blur-sigma` / 配置 `model.input_blur_sigma`：复现论文迁移协议（灰度高斯模糊 σ=1.1，在 letterbox 前的原始分辨率上施加）。
- 其余（数据划分、letterbox 512、LoRA rank8/α16/末 4 块（分类）/12 块（分割）、MLP 头、Dice+BCE、评估指标）与 DINOv3 系完全同口径。

配置：

- 分类 `configs/segmentation/dinov3/vitb16_dmae_us200.yaml`
- 分割 `configs/segmentation/dinov3/vitb16_roi_lora_mlp_512_m025_all12_dmae_us200.yaml`

## 4. 运行编排

- `scripts/queue_dmae_after_v2.sh`（setsid+nohup）：等 `queue_us_ssl_v2_tonight` 打出 ALL DONE 且 GPU 空闲 → 模糊副本（若缺）→ 200 ep 预训练 → 导出 encoder → 分类 → 分割。日志 `logs/queue_dmae_us200.log`。
- `scripts/queue_dmae_probe.sh`（setsid+nohup，已挂）：等上述 ALL DONE → 过滤临床 CSV（剔除图像缺失行）→ DMAE（带模糊）与温和版（不带模糊）各缓存 train/val/前瞻 probe 特征 → 跑 `run_dinov3_trainset_feature_eval.py` 出两份报告。日志 `logs/queue_dmae_probe.log`。

## 5. 判读标准（与既有基线同口径）

| 对比 | 指标 | 基线 |
| --- | --- | --- |
| 分类 val | patient AUC | 官方 DINOv3 0.727 / 激进版 0.724 / 温和版 0.709 |
| 分类前瞻 | patient AUC | 官方 0.763 / 激进版 0.720 / 温和版 0.731 |
| 分割 val / holdout / 外部 / 前瞻 | Dice | 官方 0.881 / 0.880 / 0.866 / 0.897 |
| **probe（§3 口径，overlay-free）** | val/前瞻 AUC（dino_scalar+clinical 等） | 官方 vs 激进版见结果文档 §3（中性） |

注：DINOv3 侧分类/分割基线受 overlay 混淆（backbone 实为同一 seg ckpt），DMAE 的 timm 路径无 overlay、测的是 backbone 本身——因此 **probe 行是 DMAE 与官方权重的首要干净对比**，分类/分割行作为同链路参照解读。

- deblur-MAE 明显超过官方 DINOv3 → MIM 路线成立，续训至论文等效预算（~740 ep）并补 vanilla MAE 对照
- 打平或更差 → 与 DINOv3 域适应结论合并：自有数据 SSL 两条路线均封存，encoder 维持官方权重

## 6. 产物与复现

- 预训练：`bash scripts/pretrain_dmae_us.sh 200 <out_dir>`（封装 `external/DeblurringMIM/main_pretrain.py`）
- 模糊副本：`python3 scripts/make_us_ssl_blurred_copy.py`（CPU，约 15–30 min）
- 导出：`python3 scripts/export_dmae_encoder.py --ckpt <checkpoint-N.pth> --output <encoder.pth>`
- probe：`scripts/queue_dmae_probe.sh` → 特征缓存 `pipeline/data/dinov3_tstaging_region_features/{train,val,internal_prospective_full}_{dmae_us200,us_ssl_v2_gentle}/`，报告 `pipeline/experiments/reports/{dmae_us200,us_ssl_v2_gentle}_probe/`
- vendored 代码补丁：`external/DeblurringMIM/util/pos_embed.py` 的 `np.float` → `float`（NumPy≥1.24 兼容，唯一一处）
- 注意：官方 repo 的 `CorruptDataset` 要求 `<root>/<train|val>/<class_dir>/` 结构，故副本数据集按 `train/all/`、`val/all/` 组织
