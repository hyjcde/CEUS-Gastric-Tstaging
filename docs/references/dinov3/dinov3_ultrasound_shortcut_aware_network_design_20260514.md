# 面向胃癌充盈超声 T 分期的 DINOv3 深度结合与 Shortcut-Aware 网络设计

## 1. 目的

当前项目已经证明：

- `frame-level clinical/anatomic RandomForest + patient aggregation` 是强基线。
- 静态 DINO scalar / embedding 拼接不能稳定提升 4 类 AUC。
- DINO self-discovery 特征对 T2/T3 有信号，但不应被简单压成表格特征。
- 旧 ConvNeXt contrastive 图像网络没有跑过表格 RF。
- 单纯 MLP / FT-Transformer 在静态数值特征上不稳定。

因此，下一步不能只是“换一个更大的分类模型”。需要重新理解 DINOv3 的特性，并结合胃癌充盈超声的临床诊断逻辑，设计一个 **shortcut-aware、病人级、多帧、多证据融合** 网络。

## 2. DINOv3 的真正强项

### 2.1 Dense feature map，而不是普通分类向量

DINOv3 论文的核心之一是 dense feature。它通过 Gram anchoring 缓解长训练中 dense feature map 退化的问题，使 patch-level 表征在高分辨率下仍然清晰。

这对本项目的意义：

```text
T 分期不是只问“图像像不像胃癌”
而是问“病灶是否侵犯到壁层外侧/浆膜侧”
```

所以 DINOv3 的价值不是一个 `CLS token` 分类向量，而是：

```text
lesion token
outer wall token
inner control token
boundary token
bridge token
top salient token
patch similarity graph
```

### 2.2 Frozen backbone + task-specific decoder

DINOv3 论文中的 detection、segmentation、depth 等复杂任务，通常是 frozen backbone + 下游 decoder/head，而不是直接全量 fine-tune。

这给我们的启发：

```text
第一阶段不要全量微调 DINOv3。
应该冻结 DINOv3，用小的 wall-evidence decoder / attention head 读取 dense token。
```

### 2.3 高分辨率和 RoPE 对超声边界有价值

DINOv3 支持高分辨率推理，并强调高分辨率下 local feature 更清晰。

胃癌充盈超声中的 T2/T3/T4+ 证据通常很细：

- 胃壁分层是否连续。
- 病灶外侧是否突破。
- 外侧浆膜面是否毛糙。
- 病灶与周边组织之间是否有异常桥接。

这些都比单纯 ROI 分类更需要高分辨率 dense token。

### 2.4 DINOv3 不等于 segmentation

当前我们容易误会：

```text
DINOv3 = DINO mask
```

这是不完整的。DINOv3 可以同时提供：

| DINO 信息 | 作用 |
| --- | --- |
| mask-guided token | 根据已有 lesion/wall mask 提取区域证据 |
| non-mask salient token | 当 mask 不准时发现潜在异常区域 |
| CLS/global token | 全图质量、切面、整体上下文 |
| patch similarity graph | lesion、outer wall、inner control 的相似关系 |
| frame-to-frame similarity | 同一病人多帧一致性/关键帧发现 |

一句话：

```text
mask 是 DINO 的引导，不是 DINO 的边界。
```

## 3. 胃癌充盈超声任务的特殊性

### 3.1 医生不是看单张图

医生扫查时会综合多个切面：

- 病灶最大厚度切面。
- 胃壁最不连续切面。
- 外侧浆膜最可疑切面。
- 充盈状态较好的切面。
- 伪影较少的切面。

因此模型必须是：

```text
frame-level evidence
-> patient-level MIL aggregation
```

不能先把一个病人的多帧平均成一个向量。

### 3.2 T2/T3 是壁层突破边界

T2/T3 的本质不是普通分类，而是：

```text
病灶是否突破肌层/浆膜方向
```

适合的证据：

- outer wall band 是否异常。
- outer wall 与 lesion token 是否相似。
- boundary ring 是否连续。
- outer wall 与 inner control 是否差异大。
- top salient token 是否落在外侧壁方向。

### 3.3 T3/T4+ 是更深外侵边界

T4+ 错分成 T3 是当前可视化中常见问题。

T4+ 需要更深证据：

- outer band 之外是否仍有异常 token。
- bridge/context 区域是否连接到邻近组织。
- wall-side top salient token 是否扩展到 mask 外。
- DINO self-discovery 是否发现 mask 外高风险区域。

这说明 T4+ 不能只靠 lesion mask 内部或外侧薄 band。

### 3.4 超声有强 shortcut 风险

医学影像 shortcut 文献指出，模型可能利用非病理因素：

- 设备/中心差异。
- 图像边框、文字、UI 残留。
- 探头频率、增益、深度。
- 医生截图习惯。
- ROI 裁剪大小。
- 标注/后处理产生的固定形态。

在本项目中尤其要警惕：

| 可能 shortcut | 例子 |
| --- | --- |
| 中心 shortcut | `ext/putian_2024` 和 `ext/zhongliu` 风格差异 |
| 年份 shortcut | 2018/2019/2024/2025 图像处理不同 |
| ROI shortcut | crop_roi 大小或位置与分期相关 |
| mask shortcut | predicted mask 面积/形状直接泄露标签 |
| clinical shortcut | 肿瘤厚径、长径过强，图像分支变成摆设 |
| frame count shortcut | T4+ 病人可能有更多图 |

因此专门网络必须设计 anti-shortcut 机制。

## 4. 为什么之前神经网络没有超过 RandomForest

### 4.1 普通 MLP 不够

MLP 只看表格特征，不看原始图像和 DINO token map。它没有比 RF 更强的 inductive bias。

### 4.2 FT-Transformer 仍是静态特征模型

FT-Transformer 把数值特征变成 token，但输入仍是：

```text
post-hoc scalar
```

它没有看到：

- DINO token map。
- 图像局部纹理。
- mask 外侧区域。
- 多帧空间关系。

### 4.3 Frozen image embedding 拼接不够

冻结 ConvNeXt embedding 后拼接到表格特征，性能下降，说明：

- frozen embedding 噪声较大。
- 图像特征没有被任务监督调优。
- 模型无法知道哪些图像 patch 对 T 分期关键。

### 4.4 旧 contrastive ConvNeXt 训练不对目标

旧图像训练主要是 frame-level 分类和 contrastive loss，没有直接优化：

```text
patient-level MIL
T2/T3 boundary
T3/T4+ deep invasion
RF teacher distillation
DINO dense token interaction
```

所以效果低于 RF。

## 5. 新网络：DinoWall-MIL++

建议升级模型名：

```text
DinoWall-MIL++
```

完整结构：

```text
Patient Bag
  ├─ Frame 1
  ├─ Frame 2
  ├─ ...
  └─ Frame N

Each Frame
  ├─ Ultrasound image branch
  ├─ Lesion/Wall patch branch
  ├─ DINOv3 dense token branch
  ├─ DINO self-discovery branch
  ├─ Clinical/anatomic branch
  └─ Shortcut-control metadata branch

Patient Aggregator
  ├─ top-k high-risk frames
  ├─ gated attention MIL
  ├─ frame consistency regularization
  └─ patient-level T stage head
```

## 6. 分支设计

### 6.1 Ultrasound Image Branch

输入：

```text
crop_ui image
crop_roi image
wall patch
context patch
control wall patch
```

推荐 backbone：

```text
ConvNeXtV2-T/S 或 ConvNeXt-S
```

原因：

- 超声 speckle 和局部纹理更适合卷积/ConvNeXt。
- 当前 ConvNeXt pipeline 已经成熟。
- 直接 ViT 图像分类可能数据不足。

训练策略：

```text
先冻结低层，训练最后 stage + fusion head
再视情况解冻更多层
```

### 6.2 DINO Mask-Guided Branch

输入：

```text
DINOv3 ViT-B/16 token map
lesion mask
outer wall mask
inner control mask
boundary ring
bridge/context mask
```

处理：

```text
region query tokens attend to DINO patch tokens
```

输出：

```text
z_lesion
z_outer
z_inner
z_boundary
z_bridge
z_outer_minus_inner
z_boundary_minus_lesion
```

作用：

- T2/T3 boundary。
- 外侧壁侵犯。
- boundary continuity。

### 6.3 DINO Self-Discovery Branch

输入：

```text
DINO patch tokens without mask
CLS token
top-k salient tokens
PCA foreground tokens
patch similarity graph
```

输出：

```text
z_dino_global
z_salient
z_pca_foreground
z_patch_graph
```

作用：

- mask 错误时 fallback。
- 发现 mask 外高风险区域。
- 提供全图结构和图像质量判断。

### 6.4 Clinical-Anatomic Branch

输入：

```text
age, sex
tumor length/thickness/location
CEA, CA19-9
Lauren type
differentiation
anatomic area / distance / texture delta
missing flags
```

推荐：

```text
FT-Transformer or MLP + feature dropout
```

特殊处理：

- 对 clinical/anatomic 加 feature dropout，防止网络完全依赖临床。
- 对图像分支加 RF distillation，学习 RF 的稳定规则。

### 6.5 Shortcut-Control Branch

显式输入或记录：

```text
source / center
year group
image size
frame count
view quality score
mask quality score
```

用途不是直接分类，而是：

- 做 domain adversarial loss。
- 做 source-aware batch normalization。
- 做分层评估。

## 7. Anti-Shortcut 训练策略

### 7.1 Source-balanced sampling

每个 batch 不只 class-balanced，还要 source-balanced：

```text
batch = multiple patients from different source/year groups
```

避免模型把中心风格当分期。

### 7.2 Feature dropout

随机 drop 掉部分强特征：

```text
drop clinical branch
drop anatomic numeric branch
drop ROI-only image branch
drop mask-guided DINO branch
```

逼模型学多种证据，防止单一路径 shortcut。

### 7.3 Mask perturbation

训练时轻微扰动 mask：

```text
dilate / erode / shift / dropout outer band
```

防止模型记住 mask 形状，而是学 wall evidence。

### 7.4 Domain adversarial head

从 fused frame embedding 预测 source：

```text
source classifier + gradient reversal
```

目标：

```text
T stage 可预测
source 不可预测
```

### 7.5 RF distillation

RF 是强 teacher：

```text
student learns hard label + RF soft probabilities
```

但不能只蒸馏 RF，否则网络不会超越 RF。

建议：

```text
distill_weight = 0.3-0.5
```

### 7.6 Patient-level supervision

同时训练：

```text
frame-level CE
patient-level CE
top-k patient CE
T2/T3 auxiliary CE
T3/T4+ auxiliary CE
```

## 8. Loss 设计

```text
L =
  1.0 * L_patient_4class
  + 0.5 * L_frame_4class
  + 0.3 * L_early_vs_advanced
  + 0.3 * L_T2_T3
  + 0.2 * L_T3_T4
  + 0.3 * L_RF_distill
  + 0.1 * L_source_adversarial
  + 0.05 * L_frame_consistency
```

解释：

- patient loss 是主目标。
- frame loss 保证每帧有监督。
- adjacent losses 强化临床边界。
- RF distill 学稳定结构化规则。
- source adversarial 控制中心 shortcut。
- consistency 控制多帧冲突。

## 9. 训练计划

### Phase A：无 DINO token，先做 MIL 图像+临床网络

目的：验证 patient bag 训练框架。

输入：

```text
ConvNeXt image branches
clinical/anatomic branch
```

目标：

```text
内部 full prospective >= 0.80
外部 >= 0.81
```

### Phase B：加入 DINO mask-guided token attention

目的：提升 T2/T3 和 T3/T4+。

输入：

```text
DINO lesion/outer/inner/boundary/bridge token attention
```

目标：

```text
T2/T3 AUC > 0.80
T3/T4+ AUC 不下降
```

### Phase C：加入 DINO self-discovery

目的：防止 mask 错误导致失败。

输入：

```text
CLS/global token
top-k salient token
PCA foreground token
patch graph summary
```

目标：

```text
错误病例中减少 T3->T1、T4+->T3
```

### Phase D：source-adversarial + mask perturbation

目的：抗 shortcut。

目标：

```text
外部各 source AUC 更均衡
ext/zhongliu BAcc 提升
```

### Phase E：DINO LoRA/Adapter

仅当前面有效后再做：

```text
DINO last2 blocks LoRA
rank 4/8
lr 1e-5
```

## 10. 评估必须分层

以后每次训练都必须报告：

### 整体

```text
internal full prospective patient AUC
external patient AUC
```

### 相邻边界

```text
T1/T2
T2/T3
T3/T4+
```

### source-level

```text
ext/putian_2024
ext/putian_2025_07_09
ext/zhongliu
small external sources
```

### shortcut checks

```text
source prediction from embedding
frame count correlation
mask area-only baseline
clinical-only baseline
image-only baseline
mask perturbation robustness
```

## 11. 推荐第一版实现

第一版不要写太大。建议先实现：

```text
PatientBagDataset
FrameImageEncoder: ConvNeXt-S shared for ROI/wall/control
ClinicalAnatomicFT
GatedAttentionMIL
RF distillation
```

暂时不接 DINO token。

如果这个能稳定接近/超过 RF，再接：

```text
DINO Mask-Guided Token Attention
DINO Self-Discovery Token Attention
```

原因：

```text
先证明 patient-level 神经训练框架有效
再证明 DINO token 带来增益
```

## 12. 参考文献（经典脉络）

仍需保留的顶层设计文献：

- DINOv3: dense patch 特征、Gram anchoring、frozen backbone + 轻量 decoder（本项目与其医学基准结论一致：宜作强 prior，但医学域缩放律不稳定，需任务内验证分辨率与尺度）。
- Attention MIL（Ilse et al.）；CLAM；TransMIL：病人级 bags、注意力与 Transformer 聚合仍是合理基线类别。
- 胃癌充盈超声术前分期与传统影像：口服造影超声、CT、EUS 等临床对照文献（用于写法与分期定义对齐）。

## 13. 新近文献与对 DinoWall-MIL++ 的启发（2024–2026）

以下为**可核对 DOI/arXiv 的代表性新近工作**，重点不是堆引用，而是把可迁移的机制映射到本项目。

### 13.1 DINO / 通用 ViT 在医学上的系统性结论

- **Chen et al., «Does DINOv3 Set a New Medical Vision Standard?»**（arXiv:2509.06467，2025）  
  - **要点**：跨 2D/3D 分类与分割大基准；DINOv3 可作强 off-the-shelf encoder，但在 WSI、EM、PET 等强域专用任务上特征会退化；**医学域上模型尺度与分辨率提升并不单调带来收益**。  
  - **本项目启发**：不要盲目加大 DINO 尺度或拉高分辨率而不做消融；宜用**多分辨率 / 多块大小**做小网格搜索； dense 特征优先给 **wall/band decoder**，CLS 只做辅助。

### 13.2 超声上的病人级 MIL 与多模态融合（任务形态接近）

- 甲状腺等：**病人级 Attention MIL + 多尺度超声特征融合**（如 *Frontiers in Oncology* / PMC 上与甲状腺癌病人级 MIL 相关报道，可作写法与结构设计参照）。  
- 乳腺：**MIL + 迁移学习**在 BUS 数据上持续提升 AUC 类指标（多篇 2024 工作）。  
- 软组织肿瘤等：**灰阶 + 多普勒 + 临床指标** 双流或双模态，前瞻性验证优于单图像（说明**临床向量与成像模态并联**在临床论文里可审稿）。  

**本项目启发**：Patient-level MIL 叙事充分；可增强 **multi-scale ROI**（厚径最大层 vs 外层 band）作为 bag 内 instance 分型，而非仅「一张图一例」。

### 13.3 Shortcut / 泛化估计（与多中心外部验证直接相关）

- **Shortcut learning in medical AI hinders generalization**（*npj Digital Medicine*, 2024）：被动采集数据中的 **DAB（采集相关偏倚）** 可导致表观性能虚高；提出 **PEst** 类思路——在**无外部标签**时估计外推性能。  
- **Boland et al., «There Are No Shortcuts to Anywhere Worth Going»**（PMLR / MLHC 相关流程，2024）：用 **prediction depth、层间 KL** 等定位 shortcut 出现的层。  

**本项目启发**：除 source-adversarial 外，增加 **shortcut 审计面板**：按中心/年份分层、mask-only / clinical-only / image-only 对照、与 PEst 思想一致的**内部 hold-out 协议**，写进每次实验 report。

### 13.4 单源域泛化 + 大模型先验（TinyMIG、MEDU）

- **TinyMIG**（ICML 2025）：从 **视觉基础模型向单域医学数据** 迁移泛化，强调**轻量、对齐与蒸馏**，可用 DINO / SAM 等作 teacher side。  
- **MEDU**（MICCAI 2025）：**双编码器（如 CNN + SAM2）+ 扰动一致性**，面向**极少标注**下的单源域泛化分割。  

**本项目启发**：  
- **Phase E 前**可尝试 **TinyMIG 式「VFM 对齐支路」**：冻结 DINO 作一支，小 CNN（或轻量 adapter）作另一支，融合后再进 MIL，用于抗设备差异。  
- **训练增广**：在帧级加入 **consistency across perturbation**（仿 MEDU 的层次一致性），与现有 `L_frame_consistency` 可合并设计。

### 13.5 超声领域基础模型（与 DINO 的互补）

若需第二视觉先验或联合蒸馏，可关注（均为预印本或 2025 发表，实施前请核对最终版本）：

- **USF-MAE**（arXiv:2510.22990）：大规模 MAE 式超声预训练。  
- **OpenUS**（arXiv:2511.11510）：开源超声基础模型与对比学习。  
- **UltraFedFM / federated ultrasound FM**（*npj Digital Medicine* 等，2025 附近）：联邦/多中心预训练叙事，与本项目外部队列泛化话术一致。

**本项目启发**：DINO 管「通用结构与纹理」；超声 FM 管「探头域与散斑统计」——可作 **双流 late fusion + 门禁（gating）**，避免单一 backbone 死记某中心增益。

### 13.6 可解释自监督 + 语义检索（与病例面板一致）

- 基于 **DINOv2 + 语义检索** 的可解释诊断框架（PMC，2025 附近）：与张量热图并列的 **case retrieval** 可增强临床可读性。

**本项目启发**：前瞻/外部的 **「相似病理 T 分期历史病例」** 可作为第二层输出（不必进主梯度），强化 MA-Staging 叙事。

## 14. 最重要结论

下一版网络要解决三个问题：

```text
1. 不能浪费多帧：patient-level MIL
2. 不能只靠表格：trainable image branch
3. 不能把 DINO 限制在 mask：mask-guided + self-discovery dense token attention
```

如果还只是 frozen embedding / scalar 拼接，基本不会明显超过 RF。

### 14.1 基于新近文献优先级的四条改进（建议写入下一版实验 backlog）

| 优先级 | 改进项 | 依据 |
| :--- | :--- | :--- |
| P0 | **多分辨率 DINO dense 消融**（固定算力_budget 下网格搜索），避免无脑上大模型 | arXiv:2509.06467 医学缩放非单调 |
| P0 | **Shortcut 仪表板**：分层 AUC + PEst 类内部估计 + 层诊断（prediction depth） | npj Digit. Med. 2024；Boland et al. 2024 |
| P1 | **扰动一致性 + 双支路对齐**（DINO + 轻量超声专用编码或 TinyMIG 思想） | MEDU MICCAI 2025；TinyMIG ICML 2025 |
| P2 | **可选第二先验**：USF-MAE/OpenUS 等超声 FM 特征与 DINO late-fusion | 超声 FM 预印本群 |

