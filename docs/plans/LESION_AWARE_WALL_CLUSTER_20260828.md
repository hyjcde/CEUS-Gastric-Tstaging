# 病灶感知胃壁分层：离线 A/B（2026-08-28）

医生可以一笔穿过病灶。聚类只用病灶外的正常壁；病灶只在之后判断融合 / 中断。本轮只做离线固定袋和拼图，不改公网工作台，不定 cT，不接 DINO。

产品线仍是先验：[浆膜预期走行线协议](../meetings/2026-08-28_浆膜预期走行线协议.md)。本页是现网灰度 M0 的前置修正，也是 [DINO 走廊计划](./DINO_WALL_LAYER_EMBEDDING_20260828.md) 的 Gate 0.5。

## 为什么要排除病灶

现网 `clarifyDeepestEcho` 在最深浸润点采 56 x 28，最深点来自病灶顶点，低回声肿块会进 k-means。完整笔刷带若穿过病灶，暗层中心会被拉向肿块，亮-暗-亮会糊掉。

规则：

```text
L_valid = L_doctor - dilate(M_lesion, d)
```

两侧正常段分别保存。有效像素 < 40 或最长侧弧长 < 12 px 则 `insufficient_normal_wall`，不聚类。

## 固定袋 v1

病例由讨论指定：P008 / P019 / P040 / P076（现网 v150 的 CASE-008 / 019 / 040 / 076）。病理参考旁证：T1 / T2 / T3 / T4。部位：胃体，其余三例贲门/胃底。

| 输入 | 来源 |
|------|------|
| 帧 | 按 ZML 画线时间从 `reader_study_v150` cine 抽帧，不再用旧冻结时刻 |
| 走行线 | 公网 `zml` 草稿：`wallPolygon` 或 `mask_overrides.wall_polygon` |
| 病灶 | 同一关键帧或 `|Δt| ≤ 0.30 s` 才配对；更远的旧病灶不用 |

2026-08-28 22:34–22:45（CST）公网 ZML 对应：

| 显示号 | 走行线时刻 | 来源 | 病灶配对 | 工作台像素提示（不是医生 cT） |
|--------|------------|------|----------|------------------------------|
| P008 | 0.35 s | mask_overrides，1100 点 | 同帧 117 点 | 无分层 ticks |
| P019 | 3.924 s | keyframe `dkf_3.924_j1v8ij` | 旧灶在 8.395 s，Δt 4.47 s，不用 | 浅层连续，固有肌中断，浆膜连续 |
| P040 | 1.85 s | keyframe `dkf_1.850_s8gyvd` | 1.95 s 灶，Δt 0.10 s，配对 | 浅层连续，固有肌连续，浆膜中断 |
| P076 | 0.179 s | keyframe `dkf_0.179_q6hl53` | 旧灶在 0.728 s，Δt 0.55 s，不用 | 浅层中断，固有肌连续，浆膜连续 |

像素提示来自 `wallLayerReadout.ticks`，界面已写明：线是预期走向，不是医生给出的中断答案。不定 cT。

P040 早上还有 2.134 s 的 1 层旧线；本袋用当晚 3 层线。

本地工作台小队列（不进公网 150 例）：左侧选 **本地壁层实验, 4例**，或打开

```text
http://10.13.199.162:3000/?queue=reader:local_wall4
```

只出现 P008 / P019 / P040 / P076，顺序 T1 → T4。公网医生看不见这条队列。

打包：

```bash
python3 scripts/pack_wall_layer_fixture_v1.py --help
python3 scripts/pack_wall_layer_fixture_v1.py
```

## 算法

库：`scripts/wall_lesion_aware_cluster.py`

- 笔刷带栅格化，减去膨胀灶（0 / 3 / 5 / 10 px）
- 特征：`[gray/255, across_frac * 0.60]`
- k-means，k=3；簇按法向深度从胃腔排到浆膜：浅层 / 固有肌 / 浆膜
- 胃腔侧：有 `lumen_polygon` 或 `lumen_bbox` 就用；否则 heuristic
- 3x3 多数表决；本轮不加纹理、不加 DINO

对照臂：现网 56x28 按亮度命名；完整笔刷 k=3；排除病灶 k=3。

传统聚类再比一轮（仍只在灶外拟合，k=3，膨胀 5 px）：

| 方法 | 怎么聚 |
|------|--------|
| k-means | 现网同款，特征是灰度 + 法向深度 |
| GMM | 每个层当成一团高斯分布 |
| Ward | 层次聚类，相近像素先合并 |
| FCM | 模糊 C-means，像素可同时像两层 |
| 1D gray | 只按灰度聚，再按深度排序 |
| 1D across | 只按法向深度切成三带 |

```bash
python3 scripts/test_wall_lesion_aware_cluster.py
python3 scripts/eval_lesion_aware_wall_cluster_v1.py
python3 scripts/eval_lesion_aware_wall_cluster_trad.py
```

报告：`pipeline/experiments/reports/lesion_aware_wall_cluster_v1/`

层色：浅层黄，固有肌蓝，浆膜绿，灶红半透明。实线是正常段中心；虚线延伸和四态中断下一阶段再做。

## 本轮观察（已换成 ZML 线）

合成条带上，排除灶后暗层中心不再被肿块灰度拉低，并能聚出 bright-dark-bright。

ZML 真线上：只有 P040 同时有走行线和近邻灶（0.10 s），排除 d=5 出现 bright-dark-bright，完整笔刷没有。P008 同帧有灶，排除后像素从 6166 降到 4348，仍未形成亮-暗-亮。P019、P076 的线和灶不在同一帧，排除臂等于完整笔刷。这两例要等同帧灶，或先按「只聚正常壁」看分层。

传统对照（排除 d=5）：P040 六种方法都出现亮-暗-亮。P019 只有 Ward 出现，对比度 108.7。P008、P076 六种都没有。

诊断拼图（`render_wall_cluster_diagnostics.py`）看灰度-深度：

- P040：灶外像素在深度 0 附近有一条暗带，两侧更亮，翻转朝向也还在。这是真分层。
- P008：有胃腔框，箭头朝外合理；剖面是浅侧亮、深侧一路变暗，翻转也不是亮-暗-亮。
- P019：没有同帧灶，剖面从浅到深逐渐变亮，Ward 仍能拆出中间暗簇。
- P076：线穿过肿块，但本帧没有灶，12065 个像素全当正常壁，剖面单调变亮。先补同帧灶，再谈聚类器。

```bash
python3 scripts/render_wall_cluster_diagnostics.py
```

不要把像素 ticks 当成医生中断答案，也不要报一致率。

## 不做

不改 `InteractiveSegPanel`，不 deploy，不把草稿送进 Assist，不换冻结四分类权重，不把 v150 交互并回训练。

## 过门以后

1. 医生在这四例上画真实预期线，再 pack / eval
2. 曲率约束延伸，灶内只画虚线
3. 四态连续性（连续 / 融合 / 中断 / 无法判断）
4. 同一排除规则上的 DINO M1
