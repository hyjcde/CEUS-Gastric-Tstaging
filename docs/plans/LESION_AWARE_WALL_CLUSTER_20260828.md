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
| 帧 | `pipeline/data/zml_reader_v150_frozen_20260827/images/` |
| 病灶 | zml 关键帧 `lesionPolygon` |
| 走行线 | 现网若有 `wallPolygon` 则用医生线；本轮四例都没有，写入 `provisional_lesion_axis` |

`provisional_lesion_axis` 是沿病灶长轴、略偏深面、并向两侧伸出的临时线，**不是医生走行线**。医生评分表可以对照拼图，但不能当一致率。医生用现网画线并保存后，重新跑 pack 即可替换。

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

```bash
python3 scripts/test_wall_lesion_aware_cluster.py
python3 scripts/eval_lesion_aware_wall_cluster_v1.py
```

报告：`pipeline/experiments/reports/lesion_aware_wall_cluster_v1/`

层色：浅层黄，固有肌蓝，浆膜绿，灶红半透明。实线是正常段中心；虚线延伸和四态中断下一阶段再做。

## 本轮观察（临时线，不能当成绩）

合成条带上，排除灶后暗层中心不再被肿块灰度拉低，并能聚出 bright-dark-bright。

四例临时线上，排除 d=5 后 P019、P076 出现 bright-dark-bright，完整笔刷没有。P008、P040 两臂都未形成稳定三层，先查笔刷宽度和胃腔侧，不要上 DINO。

## 不做

不改 `InteractiveSegPanel`，不 deploy，不把草稿送进 Assist，不换冻结四分类权重，不把 v150 交互并回训练。

## 过门以后

1. 医生在这四例上画真实预期线，再 pack / eval
2. 曲率约束延伸，灶内只画虚线
3. 四态连续性（连续 / 融合 / 中断 / 无法判断）
4. 同一排除规则上的 DINO M1
