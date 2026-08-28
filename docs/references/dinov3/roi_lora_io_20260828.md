# DINOv3 ROI LoRA：全部输入与输出

日期：2026-08-28。研究线。公网框选病灶可选 DINO 分割，画完后辅助分析与 SAM 相同；不替换 Dual 四分类权重，不替换 UNet `segmentation_primary`。

仓库里现在有两条 ROI LoRA 线，不要混报。

| 实验 | 任务 | 监督 | 主指标 | 状态 |
|------|------|------|--------|------|
| `dinov3_roi_lora_mlp_phase0_20260828` | T 分期四分类 | `class_label` | ACC / AUC | 已结束；任务理解错了 |
| `dinov3_vitb16_roi_lora_mlp_512_20260828_full` | **病灶分割** | ROI 上的二值 mask（外扩 0.75 / 32） | **Dice** | 已结束；epoch 22 best，30 早停 |
| `dinov3_vitb16_roi_lora_mlp_512_m025_20260828_full` | **病灶分割** | ROI 上的二值 mask（更紧 0.25 / 16） | **Dice** | 已结束；epoch 23 best，31 早停 |
| `dinov3_roi_lora_mlp/phase0_m025_frozen_20260828` | T 分期四分类 | 冻结 m025 embedding + MLP | ACC / AUC | 已结束；prosp ACC 0.541 AUC 0.744 |
| `beta_m025_phase0_fulltab_20260828` | T 分期四分类 | 冻结 m025 1536-d + clin-11，无 PCA，官方 BETA | ACC / AUC | 已结束；train 1234；prosp ACC 0.485 AUC 0.780；不替换 Assist |
| `dinov3_roi_lora_mlp/phase0_m025_continue_fullcov_20260828` | T 分期四分类 | 接着训 m025 LoRA + 新 MLP；全覆盖 ROI | ACC / AUC | 已结束；prosp ACC 0.522 AUC 0.727；过拟合；不替换 Assist |
| `dino_gatec_tab_beta_20260828` | T 分期四分类 | Gate C 灶内/周边池化 + 探针 / TabPFN-2.5 / BETA | ACC / AUC | **训练中**；同一张表；不替换 Assist |
| `sam_dino_roi_expand10_20260828` | 分割对照 | SAM oracle / 全图 DINO / ROI m025，再测框 x1.10 | Dice | 已结束；拼图 + 外部/前瞻 |

下面先写**尺寸怎么统一**和 **LoRA 怎么接**，再写分割线完整输入输出。分类线对照放最后，避免再把 T 标签当成分割监督。

---

## 0. 尺寸统一：磁盘上不改尺寸，进网才 letterbox 512

拼图里看到的每一格都是正方形，**那是展示/训练时 pad 出来的**。磁盘上的 `gt_lesion_crop_upper_bound_v1/**/img/*.png` 仍是各图自己的裁剪宽高，长短不一，没有先 resize 成正方形再存盘。

统一发生在 `RoiSegDataset.__getitem__` → `letterbox_pair`（`scripts/train_dinov3_roi_lora_seg.py`）。分类线用同一套规则的 `letterbox_rgb`。

### 0.1 规则（不拉伸）

对一张宽 `W`、高 `H` 的 ROI 和它的 mask：

```text
scale = min(512 / W, 512 / H)
nw, nh = round(W * scale), round(H * scale)
image  -> bilinear 缩到 (nw, nh)
mask   -> nearest  缩到 (nw, nh)
canvas = 512 x 512 黑底（图像 0；mask 0）
贴到中心: ox = (512 - nw) // 2, oy = (512 - nh) // 2
```

| 要点 | 做法 | 不做 |
|------|------|------|
| 长边贴满 512 | 短边按同一 `scale` | 把矩形直接拉成 512×512 |
| 空位 | 居中黑边 | 随机 crop、反射 pad、tile |
| 图像插值 | bilinear | 先 squish 再 pad |
| mask 插值 | nearest，避免灰边 | bilinear 出 0–1 中间值 |
| 增强时机 | 先亮度/对比度，再 letterbox | 左右翻转（`hflip_prob: 0`） |

正方形病灶裁剪会几乎铺满 512；细长裁剪会上下或左右留黑条。ViT-B/16 的 token 网格固定是 `512/16 = 32×32`，所以必须先变成 512。

拼图脚本 `scripts/render_dinov3_roi_crop_panel.py` 的 `fit_cell` 是同一套「等比缩 + 黑边居中」，只是格子更小（280 / 220），方便看，不是训练输入。

### 0.2 和 Dice 的关系

val Dice 在 **letterbox 之后的 512×512** 上算，不是磁盘原生分辨率，也不是 `crop_ui` 全图。黑边两侧都是 0：GT 没有病灶，模型若也不在黑边上喷假阳性，黑边不进 `|P|` / `|G|`，几乎不影响 Dice。模型若把黑边画成病灶，会罚假阳性。

要把 512 预测映回磁盘 ROI 或全图，需要记下 `(scale, ox, oy)` 再去掉 pad、反缩放；当前训练脚本**不写**这组坐标。

---

## 0b. LoRA 怎么实现

不是 PEFT / HuggingFace `lora` 包。自写在 `scripts/train_dinov3_roi_lora_mlp.py`：`LoRALinear` + `inject_lora`。分割线 `train_dinov3_roi_lora_seg.py` 原样 import。

### 0b.1 注入顺序

```text
1. torch.hub 装官方 ViT-B/16（LVD-1689M）
2. 用 20260511 全图分割 ckpt 覆盖 backbone.*（约 188 个张量）
3. 全部 backbone.requires_grad = False
4. inject_lora：只改 blocks 的最后 4 个
5. 包上 SegDino MLP decoder（新建，可训）
```

ViT-B 共 12 个 block（下标 0–11）。`target_blocks: 4` 只动 **8, 9, 10, 11**。decoder 取层 `[2, 5, 8, 11]`，因此浅层 2、5 仍是冻住的 20260511 特征；LoRA 只改后两档。

每个被选 block 里：

| 模块 | 动作 |
|------|------|
| `attn.qkv`（`Linear` 768→2304） | 换成 `LoRALinear`，原 `W,b` 冻结 |
| `attn.proj`（`Linear` 768→768） | 同上 |
| `mlp.fc1` / `mlp.fc2` | 不动 |
| `norm1` / `norm2` | 解开 `requires_grad`，无 LoRA |

4 block × 2 个 Linear = **8 个 LoRA 模块**。yaml 里 `trainable_blocks: 0` 表示不整块解冻，只靠 LoRA 和这 8 条 LayerNorm。

DINOv3 的 `Attention` 会读 `self.qkv.in_features`，所以 `LoRALinear` 必须把 `in_features` / `out_features` 暴露出来，不能只包一层不转发属性。

### 0b.2 前向公式

标准低秩增量（Hu et al.），`ΔW = B A`，`A ∈ R^{r×in}`，`B ∈ R^{out×r}`：

```text
y = W x + b + (α / r) * B A dropout(x)
```

代码：

```python
delta = dropout(x) @ lora_A.t() @ lora_B.t()
return self.linear(x) + delta * (alpha / rank)
```

| 项 | 本 run |
|----|--------|
| rank `r` | 8 |
| alpha `α` | 16 → `scale = 2.0` |
| dropout | 0.05，只打在 LoRA 支路 |
| `A` 初始化 | Kaiming uniform（`a=√5`） |
| `B` 初始化 | **全 0**，开训时 `ΔW=0`，输出等于冻住的原 `W` |
| 原 `Linear` | 权重冻结，仍走完整前向 |

每个 `qkv` LoRA：`A` 8×768 + `B` 2304×8 = 24576；每个 `proj`：`A` 8×768 + `B` 768×8 = 12288。8 个模块合计约 **0.15M**。可训总量约 **1.28M / 86.9M**，其余几乎全是新建 decoder。

### 0b.3 优化器怎么分组

decoder 参数一组，lr `1e-4`。名字里带 `lora` 或落在后 4 个 block 的 `norm1`/`norm2` 的参数另一组，lr 也是 `1e-4`（配置里的 `backbone_lr: 5e-5` 在「整块解冻」为 0 时基本用不上）。AdamW，wd `1e-4`，AMP。

`best.pt` 里会看到 `backbone.blocks.8.attn.qkv.lora_A` 这类键；推理时必须用带 `LoRALinear` 的同一结构加载，不能只把官方 ViT 权重 load 进去。

### 0b.4 明确没做的

- 没有 LoRA 到 MLP、patch embed、最后的 `norm`
- 没有 QLoRA / 量化
- 没有把 `ΔW` merge 回 `W` 再导出
- 没有对 decoder 做 LoRA（decoder 是从头训的 1×1 conv）

---

## 1. 分割线：一句话数据流

```text
crop_ui 全图 JPG
+ crop_ui/roi_masks PNG
        |
        v
GT mask 包围框，按长边 0.75 外扩（min_margin=32, min_size=96）
        |
        v
gt_lesion_crop_upper_bound_v1/{img,label} PNG 对
        |
        v
letterbox 到 512 x 512，ImageNet 归一化
        |
        v
冻结 DINOv3 ViT-B/16（先加载官方权重，再覆盖 20260511 全图分割 backbone）
+ 后 4 个 block 的 attn qkv/proj LoRA (r=8, alpha=16)
+ SegDINO MLP decoder（层 2,5,8,11）
        |
        v
32 x 32 logits 双线性上采样到 512 x 512
        |
        v
损失：0.5 Dice + 0.5 BCE
评估：threshold 0.5 的逐图 Dice / zero-Dice
```

评估框来自 **GT mask**。这是上限实验，**不能部署**。

---

## 2. 分割线：输入

### 2.1 命令与配置

```bash
python3 scripts/train_dinov3_roi_lora_seg.py \
  --config configs/segmentation/dinov3/vitb16_roi_lora_mlp_512.yaml \
  --device cuda:0 \
  --exp-name dinov3_vitb16_roi_lora_mlp_512_20260828_full
```

| 输入 | 路径 | 作用 |
|------|------|------|
| 训练脚本 | `scripts/train_dinov3_roi_lora_seg.py` | 读 SMS 记录、LoRA、Dice 训练与评估 |
| 配置 | `configs/segmentation/dinov3/vitb16_roi_lora_mlp_512.yaml` | 数据根、尺寸、LoRA、损失、epoch |
| 模型构造 | `scripts/run_dinov3_segmentation.py` | `SegDinoModel` / `SegDinoMlpDecoder` |
| 记录与 Dice | `scripts/run_unet2d_segmentation_baseline.py` | `load_records`、`split_train_val`、`dice_loss_from_logits` |
| LoRA 实现 | `scripts/train_dinov3_roi_lora_mlp.py` | `LoRALinear`、`inject_lora` |
| DINOv3 代码 | `external/dinov3/dinov3` | `torch.hub.load(..., source="local")` |
| 官方预训练 | `external/dinov3/weights/dinov3_vitb16_pretrain_lvd1689m-73cec8be.pth` | 先装结构 |
| 全图分割初始化 | `experiments/segmentation/segmentation_dinov3_vitb16_last2blocks_holdout_cropui_dataset_v20260409_20260511_r001/checkpoints/best.pt` | 覆盖 `backbone.*`（188 个张量） |

CLI 覆盖项：`--epochs`、`--batch-size`、`--num-workers`、`--max-train-samples`、`--max-eval-samples`、`--skip-full-eval`。冒烟用后三个。

### 2.2 原始影像与 mask（裁剪前）

来源清单：`data/processed/sms/baseline_2d_unet_holdout_crop_ui/dataset_manifest.json`。

每条记录一对：

| 字段 | 内容 | 例 |
|------|------|-----|
| `original_image` | `dataset/.../crop_ui/images/*.jpg` | 去 UI 后的整幅扇扫 |
| `original_label` | `dataset/.../crop_ui/roi_masks/*.png` | 同一帧上的病灶二值 mask |

`crop_ui` 是全图，不是 DualBranch 的 `crop_roi`。官方 `dataset/**/crop_roi/images` **不进**这条分割训练。

### 2.3 已裁好的 ROI 集（训练真正读的文件）

根目录：`data/processed/sms/gt_lesion_crop_upper_bound_v1/`

生成脚本：

```bash
python3 scripts/prepare_gt_lesion_crop_segmentation_dataset.py \
  --input-manifest data/processed/sms/baseline_2d_unet_holdout_crop_ui/dataset_manifest.json \
  --output-root data/processed/sms/gt_lesion_crop_upper_bound_v1
```

裁剪规则（写进 `dataset_manifest.json`）：

1. 从 GT mask 取包围框 `gt_lesion_box = (x1,y1,x2,y2)`，右下开区间。
2. `margin = max(round(max(lesion_w, lesion_h) * 0.75), 32)`。
3. 以病灶中心扩到至少 `min_size=96`，再夹回图像边界。
4. 图像和 mask 用同一 `crop_box` 裁切，存 PNG。空 mask 本集为 0。

| 子集 | `target_split` | 磁盘 | 张数 |
|------|----------------|------|-----:|
| 可训全集 | `training` | `training/img` + `training/label` | 7376 |
| 内部 holdout | `test` | `test/img` + `test/label` | 853 |
| 外部 | `external_eval` | `eval_sources/external_eval/{img,label}` | 2856 |
| 前瞻 | `prospective_eval` | `eval_sources/prospective_eval/{img,label}` | 2430 |
| 合计 | | `dataset_manifest.json` | 13515 |

训练时再按患者切 10% val（`seed=666`）：

| | 患者 | 图像 |
|--|-----:|-----:|
| train | 1424 | 6622 |
| val | 158 | 754 |

患者 ID：`case_id` 去掉 `lumen_` 后再去掉最后一段帧号。例如 `lumen_2018直接手术_直接手术_1000012_1` → `2018直接手术_直接手术_1000012`。同一患者不会同时进 train 和 val。holdout / external / prospective 不进训练。

`dataset_manifest.json` 每条训练样本的字段：

| 字段 | 含义 |
|------|------|
| `case_id` | 裁剪后文件名（无后缀） |
| `sample_id` | 原始 sample 名 |
| `original_image` / `original_label` | 裁剪前 crop_ui 图 / mask |
| `prepared_image` / `prepared_label` | 本集 PNG 对，训练只读这两列 |
| `original_width` / `original_height` | 裁剪前尺寸 |
| `gt_lesion_box` | GT 病灶框 |
| `crop_box` | 实际裁剪框（记录里右下是闭区间） |
| `view_type` | 固定 `gt_lesion_crop_upper_bound` |

### 2.4 进网络的张量

尺寸怎么变成 512：见上面 **§0**。磁盘 PNG 保持裁剪原尺寸；这里只做 letterbox。

每张 `prepared_image` + `prepared_label`：

1. RGB / L 读取。
2. 训练增强（仅 train）：亮度 ±0.10、对比度 ±0.10。**不做左右翻转**（`hflip_prob: 0`）。
3. `letterbox_pair`：等比缩 + 居中黑边 → 512×512（不拉伸）。
4. 图像：`/255`，再减 ImageNet mean `[0.485, 0.456, 0.406]`，除 std `[0.229, 0.224, 0.225]`。
5. mask：`>0` → `{0,1}`。

| 张量 | 形状 | dtype | 范围 |
|------|------|-------|------|
| `image` | `B, 3, 512, 512` | float32 | ImageNet 归一化 |
| `mask` | `B, 1, 512, 512` | float32 | 0 / 1 |
| `case_id` / `patient_id` | 字符串 | | 只用于记录，不算损失 |

batch size 默认 2。

### 2.5 模型输入（权重侧）

| 项 | 值 |
|----|-----|
| backbone | DINOv3 ViT-B/16，`patch_size=16`，`embed_dim=768` |
| token 网格 | 512/16 = 32×32 |
| 取层 | `get_intermediate_layers(n=[2,5,8,11], reshape=True, norm=True)` → 4 个 `B,768,32,32` |
| 冻结 | 全部 backbone 参数 `requires_grad=False`，然后再注入 LoRA |
| LoRA | 见 **§0b**。后 4 个 block（8–11）的 `attn.qkv`、`attn.proj`；rank 8，alpha 16，dropout 0.05；这 4 个 block 的 LayerNorm 可训 |
| decoder | 每层 1×1 到 256 通道，拼接后 1×1 fuse，再 1×1 出 1 通道 |
| 可训参数 | 约 1.28M / 总约 86.9M |
| 优化 | AdamW；decoder lr `1e-4`；LoRA/LN lr `1e-4`；wd `1e-4`；AMP |
| 最多 | 40 epoch，patience 8（val Dice 不升就停） |

### 2.6 明确不是输入

- T1–T4 / pT / 临床表 / CEA / Lauren
- TabPFN / BETA
- 官方 `crop_roi` 目录
- 预测 mask 扩框（本线用 GT 框）
- 病理文本

---

## 3. 分割线：输出

### 3.1 前向输出

| 张量 | 形状 | 含义 |
|------|------|------|
| decoder logits | `B, 1, 32, 32` | patch 网格 |
| 上采样 logits | `B, 1, 512, 512` | 与 mask 对齐，`bilinear` |
| `sigmoid(logits)` | 同 512 | 病灶概率 |
| `prob >= 0.5` | 同 512 | 评估用二值 mask |

损失（batch 均值）：

```text
L = 0.5 * (1 - Dice(sigmoid(logits), mask)) + 0.5 * BCEWithLogits(logits, mask)
```

逐图 Dice（评估，硬阈值 0.5）：

```text
dice_i = (2 * |P∩G| + eps) / (|P| + |G| + eps)
split_dice = mean_i dice_i
zero_dice = mean_i [dice_i < 1e-6]
```

### 3.2 训练过程输出（stdout）

每个 epoch 一行 JSON：

```json
{"epoch": 6, "train_loss": 0.1025, "val_dice": 0.8061, "val_zero_dice": 0.0013}
```

早停时再打：`{"early_stop": true, "epoch": ..., "best_val_dice": ...}`。

全量 run 已结束（约 28.5 min，epoch 30 早停）。best 是 **epoch 22，val Dice 0.8195**。正式表：

| split | n | Dice | zero-Dice |
|-------|--:|-----:|----------:|
| val | 754 | 0.8195 | 0.0040 |
| internal_holdout | 853 | 0.8225 | 0.0000 |
| external_eval | 2856 | 0.8144 | 0.0018 |
| prospective_eval | 2430 | 0.8482 | 0.0004 |

相对冻结 GT-crop MLP（20260515：0.800 / 0.790 / 0.830）：holdout +0.023，external +0.025，prospective +0.018。仍是 GT 框上限，不能部署。

### 3.3 落盘目录

实验目录：

`experiments/segmentation/dinov3_vitb16_roi_lora_mlp_512_20260828_full/`

| 文件 | 内容 |
|------|------|
| `checkpoints/best.pt` | val Dice 最好的 `model_state_dict` + `epoch` + `best_val_dice` + `config` |
| `training_history.csv` | `epoch,train_loss,val_dice,val_zero_dice` |
| `dinov3_run_manifest.json` | 数据根、划分、初始化、最终各 split Dice |

报告目录：

`pipeline/experiments/reports/dinov3_vitb16_roi_lora_mlp_512_20260828_full/`

| 文件 | 内容 |
|------|------|
| `manifest.json` | 与上面 manifest 相同 |
| `README.md` | 各 split n / Dice / zero-Dice 表 |

`best.pt` 里的 state 键：

- `backbone.*`：ViT + 已注入的 `lora_A` / `lora_B`
- `decoder.projections.*` / `decoder.fuse.*` / `decoder.head.*`

已写出的 split 行：

```json
{"split": "internal_holdout", "n": 853, "dice": 0.8225, "zero_dice": 0.0}
{"split": "external_eval", "n": 2856, "dice": 0.8144, "zero_dice": 0.0018}
{"split": "prospective_eval", "n": 2430, "dice": 0.8482, "zero_dice": 0.0004}
```

本脚本训练时**不写** `inference/*/predictions_png`。看效果用：

```bash
python3 scripts/render_dinov3_roi_lora_pred_panel.py --split external_eval
```

`external_eval` 与 val / holdout / prospective 同一套：GT mask 扩框后的 ROI，不是全图、也不是检测框。图落在 `results/visualizations/segmentation/dinov3_roi_lora_external_pred_panel.png`。

三种协议并排拼图，以及 ROI 外扩 10%（当前框的宽高 ×1.10）见 `scripts/compare_sam_dino_roi_panel_expand10.py` 与 `pipeline/experiments/reports/sam_dino_roi_expand10_20260828/`。不要把 0.855 和 0.854 写成谁赢。DINO ROI x1.10：外部 0.831，前瞻 0.863。SAM oracle x1.10 患者均值：外部 0.860，前瞻 0.881。

### 3.4 对照数字（不是本 run 输出）

冻结 GT-crop MLP（无 LoRA，20260515）：

| split | Dice |
|-------|-----:|
| holdout | 0.7995 |
| external | 0.7895 |
| prospective | 0.8302 |

全图 crop_ui LoRA（20260515，不是 ROI）：ext 0.624，未超过 20260511 adapter 的 0.682。

---

## 4. 分类线对照（不要当成分割结果）

那次快，是因为只做 T 分期。

| | 值 |
|--|-----|
| 脚本 | `scripts/train_dinov3_roi_lora_mlp.py` |
| 划分 | `pipeline/data/tstaging_4class_screened_eval_phase0_xiehe_20260610/{train,val,test_prospective,test_external}.csv` |
| 图像 | 官方 `crop_roi`（CSV 旧路径失效，按 source+stem 重解析） |
| 标签 | `class_label` ∈ {0,1,2,3} = T1,T2,T3,T4+ |
| 网络输出 | `B,4` logits，CE |
| 报告 | `pipeline/experiments/reports/dinov3_roi_lora_mlp/phase0_20260828_full/` |
| 权重 | `best_roi_lora_mlp.pt` |
| 患者级 | prosp n=425 ACC 0.567 AUC 0.763；ext n=485 ACC 0.433 AUC 0.709 |

没有 mask，没有 Dice。

---

## 5. 复跑与重建数据

重建 ROI 裁剪集（已存在则要 `--overwrite`，会删整树）：

```bash
python3 scripts/prepare_gt_lesion_crop_segmentation_dataset.py --overwrite
```

再训分割：

```bash
python3 scripts/train_dinov3_roi_lora_seg.py --help
python3 scripts/train_dinov3_roi_lora_seg.py --device cuda:0 \
  --exp-name dinov3_vitb16_roi_lora_mlp_512_<新时间戳>
```

冒烟：

```bash
python3 scripts/train_dinov3_roi_lora_seg.py --device cuda:0 --epochs 1 \
  --max-train-samples 24 --max-eval-samples 12 --skip-full-eval \
  --exp-name dinov3_roi_lora_seg_smoke_<日期>
```

---

## 5b. BETA 对照（官方代码，不进 Assist）

入口：`python3 scripts/run_beta_m025_phase0.py`。实现不改 `external/BETA`。

| 项 | 值 |
|----|-----|
| 图像 | Phase-0 官方 `crop_roi`，letterbox 512，冻结 m025 LoRA 的 CLS+GAP（1536-d），患者均值 |
| 表 | 完整 1536-d CLS+GAP + clin-11（1547 列，无 PCA；BETA 内部再压到约 100 维） |
| 模型 | `external/BETA` `BetaMethod`，默认 `tabm-mini` k=16，seed_num=1 |
| 划分 | 同一套 train/val；前瞻与外部各写一份 test npy |
| 报告 | `pipeline/experiments/reports/beta_m025_phase0_20260828/` |

对照：冻结 MLP prosp ACC 0.541；TabPFN-2.5 Dual mix prosp ACC 0.704、四分类 AUC 0.845。mix 与 Dual/DINO 编码对照见 [`mix_w03_vs_dino_encoding_20260828.md`](mix_w03_vs_dino_encoding_20260828.md)。主线仍是 TabPFN-2.5。

本次数字：前瞻 n=425 ACC **0.485** AUC **0.780**；外部 n=485 ACC **0.474** AUC **0.748**。训练 1234 / 验证 140。官方按 val log-loss 选 epoch 2。不要替换 Assist。PCA-512 那次是 prosp ACC 0.438，仅作对照。

---

## 6. 读结果时不要写错的三句话

1. 本分割输入是 **GT 扩框后的 ROI 图和 ROI mask**，不是全图 `crop_ui` 训练，也不是 DualBranch 现成 `crop_roi` 目录。
2. 输出是 **512 上的病灶概率 / 二值 mask 和 Dice**，不是 T1–T4。
3. 即使 Dice 超过 0.80，也只说明「定位给定之后边界能不能画好」，不能替换全图 UNet，也不能写进公网。
