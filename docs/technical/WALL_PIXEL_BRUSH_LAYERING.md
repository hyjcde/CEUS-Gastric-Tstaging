# 画笔像素胃壁分层：当前算法说明

日期：2026-08-29。本文写的是**此刻仓库里正在跑的像素分层**，不是公网工作台现网，也不是 DINO 走廊计划的最终产品。不定 cT。

配套：

- 离线固定袋与排除病灶规则：[LESION_AWARE_WALL_CLUSTER_20260828.md](../plans/LESION_AWARE_WALL_CLUSTER_20260828.md)
- DINO 对照计划（本轮图上的 C 已停）：[DINO_WALL_LAYER_EMBEDDING_20260828.md](../plans/DINO_WALL_LAYER_EMBEDDING_20260828.md)
- 医生线是先验：[浆膜预期走行线协议](../meetings/2026-08-28_浆膜预期走行线协议.md)
- 核心库：`scripts/wall_lesion_aware_cluster.py`
- 出图：`scripts/render_wall_pixel_vs_dino_cluster.py`
- 单测：`scripts/test_wall_lesion_aware_cluster.py`
- 固定袋：`pipeline/data/wall_layer_fixtures/v1/CASE-*/`

一句话：医生画一条走行线。程序沿这条线的**法向**（墙的厚度）读灰度，找到两条最陡的亮暗跳变，把线两侧比画笔更宽的一条走廊涂成黄 / 红 / 绿三带。带是顺着墙走的，不是竖着切图像列，也不是整图 k-means。

---

## 1. 这是什么，不是什么

### 1.1 是什么

离线 M0：在四例固定帧上，用医生走行线当走廊，把走廊像素标成最多三层，并画出层带和两条分界。用来看「像素能不能自然分成三层」，以及层带在肿块旁边还在不在。

### 1.2 不是什么

| 不是 | 说明 |
|------|------|
| 不是 cT | `fates` / 图上的 lost / fused 只是灰度旁证，不能解锁确定分期 |
| 不是公网工作台 | 医生站仍是走行线草稿 + 四档芯片；本文算法没有接到 `InteractiveSegPanel` |
| 不是病理五层 | 三层名 shallow / muscularis / serosa 是工作台 1 / 2 / 3 的对照名，不是黏膜到浆膜的金标准标注 |
| 不是平行偏移假层次 | 薄带几何图 `render_wall_layer_thin_bands.py` 是另一条出图；当前像素主线不靠法向等距条带冒充层 |
| 不是 DINO 分层 | `CorridorDino` 还在脚本里，当前出图不跑 C 图 |
| 不是现网 56x28 亮度分堆 | 现网 `clarifyDeepestEcho` 仍按最深点小窗亮度聚；本文是整条画笔走廊 |

### 1.3 当前主路径（2026-08-29 下午）

出图脚本调用：

```text
cluster_brush_band(
    ...,
    brush_radius=12,          # A 图上的细画笔
    label_pad_px=16,          # 真正采点/涂色比画笔每侧再宽 16 px
    k=3,
    dilate_px=0,
    exclude_lesion=True,
    method="kmeans1d_gray",   # prefer_strips 时特征几乎不用
    fit_side="right",         # 只影响 fate 的种子侧，不再切层
    assign_lesion=False,      # 病灶像素不贴层号
    prefer_strips=True,       # 走 assign_natural_y_bands
)
```

`prefer_strips=True` 时：先在走行线的**法向**上读灰度（眼睛看到的分层是顺着墙厚，不是竖着的图像列），用灰度跳变定两刀；再投影回每一列，从上到下涂成 0 / 1 / 2，黄绿不交叉。

---

## 2. 文件与入口

| 角色 | 路径 |
|------|------|
| 算法库 | `scripts/wall_lesion_aware_cluster.py` |
| 单测（合成亮-暗-亮条带） | `scripts/test_wall_lesion_aware_cluster.py` |
| 像素出图（A 完整画笔，B 右侧放大） | `scripts/render_wall_pixel_vs_dino_cluster.py` |
| 旧薄带几何图（对照，不是当前像素 SSOT） | `scripts/render_wall_layer_thin_bands.py` |
| 固定袋打包 | `scripts/pack_wall_layer_fixture_v1.py` |
| 固定袋数据 | `pipeline/data/wall_layer_fixtures/v1/` |
| 出图落盘 | `pipeline/experiments/reports/lesion_aware_wall_cluster_v1/pixel_vs_dino/` |
| 方便打开的拷贝 | `results/visualizations/error_cases/CASE-*_pixel_vs_dino.png` |

跑法：

```bash
python3 scripts/test_wall_lesion_aware_cluster.py
python3 scripts/render_wall_pixel_vs_dino_cluster.py --brush 12 --index
# 只跑一例
python3 scripts/render_wall_pixel_vs_dino_cluster.py --brush 12 --case P040
```

库本身不读盘。调用方先准备灰度图、走行折线、病灶 mask，再调用 `cluster_brush_band`。

---

## 3. 固定袋输入（从磁盘到函数）

每例一个目录，例如 `CASE-040/`：

| 文件 | 内容 |
|------|------|
| `frame.jpg` | 走行线时刻从 cine 抽的那一帧 |
| `meta.json` | 几何、来源、病理旁证 |
| `preview.jpg` | 打包预览，算法不用 |

`meta.json` 里和分层有关的字段：

| 字段 | 类型 | 用途 |
|------|------|------|
| `case_id` | 字符串 | `CASE-008` / `019` / `040` / `076` |
| `display_id` | 字符串 | 图上写 P008 等 |
| `time_sec` | 数 | 抽帧时刻 |
| `frame_path` | 相对仓库根的路径 | 读图 |
| `wall_polygon` | `[[x,y], ...]` | **画笔中心线**，图像像素坐标 |
| `lesion_polygon` | `[[x,y], ...]` | 病灶轮廓；可空 |
| `lesion_source` | 字符串 | 灶从哪来，见下 |
| `lumen_polygon` | `[[x,y], ...]` | 胃腔，可空 |
| `cavity_side_source` | 字符串 | `lumen` / `heuristic`；当前主路径几乎不用 |
| `pT_ref` | 字符串 | 病理旁证 T1–T4，只写在图题，不进聚类 |
| `zml_pixel_readout` | 对象 | 工作台旧 ticks，**不是**本算法输出 |

`lesion_source` 约定（打包脚本，不是聚类器）：

| 前缀 / 值 | 含义 |
|-----------|------|
| `same_frame` | 同一关键帧医生灶 |
| `nearest_kf_..._dt0.xxx` | 邻近关键帧，`|Δt|` 已收进袋 |
| `redrawn_on_...` | 用旧框当位置先验，在本帧重画 |
| `other_kf_..._not_used` | 太远，打包时不用 |

配对规则在 packer：`NEAR_LESION_SEC = 0.60`。不要用远处帧发明一个灶。

当前四例（显示号 / 走行时刻 / 灶）：

| 显示 | 走行 | 灶 | 备注 |
|------|------|----|------|
| P008 T1 | 0.35 s | 同帧重画 | heading 是来回涂的涂鸦，约 1100 点 |
| P019 T2 | 3.924 s | 无近邻医生灶 | 出图可走模型 ROI 兜底 |
| P040 T3 | 1.85 s | 近邻 1.95 s 医生多边形 | 线从右侧 `(787, 455)` 往左画 |
| P076 T4 | 0.179 s | 由 0.728 s 框先验后重画 | 右侧隆起处浆膜常「没有了」 |

出图前 `prepare_crop` 还会：

1. 按走行线和灶做紧 ROI（`tight_roi`）
2. 必要时用 ROI LoRA 在本帧重画灶（只改轮廓，**不用适配器特征做聚类**）
3. 把 `wall_polygon` / 灶 / 胃腔中心平移到 crop 坐标

然后：

```text
gray = to_gray(crop)          # BGR -> float32 灰度, 0–255
lesion_mask = 栅格化灶多边形     # HxW uint8, 灶内 > 0
wall = wall_crop               # Nx2
```

---

## 4. `cluster_brush_band` 的函数输入

```text
cluster_brush_band(
    gray,                 # HxW float32，整张 crop 的灰度
    wall,                 # Nx2，画笔中心线，像素 xy
    lesion_mask,          # HxW uint8，与 gray 同尺寸
    brush_radius=8,       # 走廊半宽，像素；出图常用 12
    k=3,                  # 层数，主路径固定 3
    dilate_px=0,          # 排除灶时再膨胀几圈；出图为 0
    exclude_lesion=True,  # True：灶内像素不当正常壁
    method="kmeans",      # 见第 8 节；prefer_strips 时忽略
    lumen_center=None,    # 2, 胃腔中心；只给 across 定向用
    lesion_poly=None,     # Mx2，算最深点；只给 across 定向用
    cavity_side_source="heuristic",
    fit_side="all",       # all / right / left
    assign_lesion=True,   # False：灶内标签保持 -1
    sensitive=False,      # 旧灰度敏感走线；prefer_strips 会关掉
    extra_features=None,  # 每像素 DINO 等；主路径为 None
    prefer_strips=True,   # True：当前主路径
) -> ClusterArm
```

坐标约定：`x` 向右，`y` 向下，原点在图像左上。与 OpenCV 一致。

---

## 5. 从画笔到像素：几何走廊

下面每一步都在 `cluster_brush_band` 里按顺序发生。

### 5.1 加密中心线

```text
wall = densify_polyline(wall, step=3.0)
```

相邻两点距离超过 3 px 就插入中间点。后面的「最近线段下标」`along_idx` 就是这段折线的段号。

### 5.2 画笔 mask（走廊）

```text
brush = rasterize_brush(gray.shape, wall, brush_radius)
```

用 `cv2.polylines` 沿中心线画一条实心带子：

```text
thickness = round(2 * brush_radius + 1)
```

`brush_radius=12` 时带宽约 25 px。带内所有像素都是候选。这就是「画笔范围」。

图 A 上半透明黄带就是这个 mask；中间细黄线是完整 `wall`，包括穿过病灶的一段。

### 5.3 挖掉病灶

```text
lesion_d = dilate(lesion_mask, dilate_px)   # 出图 dilate_px=0，不膨胀
keep_pixel = (brush > 0) and (lesion_d == 0)   # exclude_lesion=True 时
```

侧段：中心线按是否落入膨胀灶，切成 left / right / full，记弧长。排除灶后若

- 有效像素 `< 40`，或
- 最长侧弧长 `< 12 px`

则直接返回 `status=insufficient_normal_wall`，不分层。

### 5.4 采样：每个笔刷像素的五元组

`sample_band_pixels` 取出 `brush > 0` 的全部像素（先包括灶内，后面再用 `keep` 挡掉）：

| 数组 | 含义 |
|------|------|
| `xs`, `ys` | 像素整数坐标 |
| `gray` | 该点灰度 0–255 |
| `along_idx` | 该点投影到中心线上最近的**折线段下标** |
| `across` | 有符号法向深度 / `brush_radius`，大约在 `[-1, 1]` |

`across` 怎么算：

1. 点投到最近折线段，得到切向
2. 法向 = 切向左转 90 度
3. 若有胃腔中心，让法向指向「离开胃腔」；否则用病灶最深点方向
4. `across = 点到中心线的有符号距离 / brush_radius`

**贴标签用 `across`（到走行线的法向距离）。** 涂色走廊是画笔半径再加 16 px。A 图仍只画细画笔，方便对照医生线。

`along_idx` 当前主路径也不切层，只留在 `ClusterArm` 里给旧 fate / 中心线函数用。

---

## 6. 当前贴标签：`assign_across_gray_bands`

这是 2026-08-29 下午的像素分层核心。`prefer_strips=True` 时由 `assign_natural_y_bands` 转进来。

### 6.1 为什么不按图像竖列切

胃壁亮暗带平行于走行线。按同一 `x` 从上往下切，墙一斜就会斜着穿过三层，肉眼很清楚的亮带/暗带会被平均掉。

正确的尺子是**法向距离**（点到走行线的有符号距离，代码里的 `across`）。

### 6.2 步骤（从线到三色带）

```text
1. 医生走行线加密，每隔约 3 px 一个站位
2. 每个站位沿法向左右各读 ACROSS_SEARCH_PX=36 px 的灰度
3. 相邻 ALONG_AVG=9 个站位平均，压掉超声斑点
4. 在剖面上找梯度峰：灰度跳得最陡的两个位置，至少相距 5 px
5. 右侧走廊比较「中亮两侧暗」和「中暗两侧亮」，整条线锁定同一种
6. 两条切点沿走行线做中值+平滑
7. 走廊像素（画笔半径 + LABEL_PAD_PX=16，比 A 上细画笔更宽）按到中心线的距离贴 0 / 1 / 2
```

```text
across < 切点1     -> 标签 0  浅层 / 黄
切点1 到 切点2    -> 标签 1  固有肌 / 红
across > 切点2     -> 标签 2  浆膜 / 绿
```

中间带可以比两侧薄或厚。黄绿是否「上下」取决于法向：约定 `+across` 朝图像下方，黄在较上的一侧。

对比太弱时退回人数三等分，只当兜底。

### 6.3 走廊比画笔宽

A 图仍画医生细画笔（半径 12）。  
真正采点和涂色用 `sample_radius = 12 + 16 = 28`，所以色带可以比黄笔更宽，盖住画笔外那一截肉眼分层。

灶内（`assign_lesion=False`）不涂色。`fit_side` / `features` 不参与切层。

### 6.4 标签语义

| 标签 | 英文 id | 中文名 | 出图色 |
|------|---------|--------|--------|
| -1 | （无） | 未标：灶内或笔刷外圈 | 不涂 |
| 0 | shallow | 浅层 | 黄 / 橄榄 |
| 1 | muscularis | 固有肌层 | 红 / 褐 |
| 2 | serosa | 浆膜层 | 绿 |

名称是工作台 1/2/3 的对照，不是病理证明「这就是黏膜」。

灰度模式只是事后统计，不反过来改标签：

```text
若 mean(gray_0) > mean(gray_1) 且 mean(gray_2) > mean(gray_1)
    pattern = bright-dark-bright
若 mean(gray_1) > mean(gray_0) 且 mean(gray_1) > mean(gray_2)
    pattern = dark-bright-dark
否则
    pattern = shallow-muscularis-serosa
```

医生描述「一层暗、一层亮、一层暗」对应 `dark-bright-dark`：上暗、中亮、下暗。合成单测条带是上亮、中暗、下亮，应对 `bright-dark-bright`。

---

## 7. 分界折线：`interfaces_from_y_bands`

在已经贴好 0/1/2 之后，再描两条线，不是再聚类一次。

对每个 `x` 列，按 `y` 看标签，找到第一次 `0 -> 1` 和第一次 `1 -> 2`，取两像素中点。得到两条点列，再经 `_split_interface_runs`：

- 只在 heading 大缺口（站号跳超过 8，或空间跳超过 40 px）切开
- 丢掉突然偏离的 across 尖点（这条路径 across 存的是 0）
- 每段拟一条二次曲线（`gentle_curve`），去掉锯齿，保留墙的大弧
- 同侧小缺口、转角小于约 22 度时用接近直线接上
- 短于 16 px 的碎段丢掉

输出：`[{edge: 0, points: [[x,y], ...]}, {edge: 1, points: ...}]`  
`edge=0` 黄线（浅层 / 肌层），`edge=1` 红线（肌层 / 浆膜）。没有第三条绿「外皮」线，三条带本身用颜色表示浆膜。

---

## 8. 函数输出：`ClusterArm`

| 字段 | 类型 | 含义 |
|------|------|------|
| `name` | 字符串 | 例如 `exclude_kmeans1d_gray_k3_d0_right_strips` |
| `status` | 字符串 | `ok` 或 `insufficient_normal_wall` |
| `skip_reason` | 字符串 | 失败时等于 `insufficient_normal_wall` |
| `k` | 整数 | 请求的层数 |
| `method` | 字符串 | 请求的方法名；strips 路径下不等于「真的做了 k-means」 |
| `n_pixels` | 整数 | 笔刷内像素数（含灶内） |
| `n_valid` | 整数 | `keep` 为真的点数 |
| `dilate_px` | 整数 | 排除灶时的膨胀 |
| `cavity_side_source` | 字符串 | 有胃腔中心则为 `lumen` |
| `pattern` | 字符串 | 见 6.5 |
| `bright_dark_bright` | 布尔 | `pattern == bright-dark-bright` |
| `classes` | 列表 | 每层 `id, name_zh, mean_gray, mean_across, count`，只统计 `keep` 上的标签 |
| `flanks` | 列表 | `{side, points, arc_px}` 左右正常段 |
| `xs`, `ys` | 整数列表 | 与 `labels` 等长，笔刷内每个点 |
| `labels` | 整数列表 | `-1 / 0 / 1 / 2`，与 `xs` 对齐 |
| `layer_polylines` | 字典 | 每层沿 `along_idx` 的中心折线，给旧图用 |
| `fates` | 列表 | 每层 present / vanished / fused / uncertain，**不是 cT** |
| `interfaces` | 列表 | `{edge, points}` 两条分界 |

`summary()` 会丢掉完整 `xs/ys/labels`，并抽稀 `interfaces` 和 `flanks`，方便写 JSON。

### 8.1 `fates` 怎么来（旁证，不切层）

`walk_layer_fate` 比较：

- **种子**：`fit` 上已标记的像素（出图 `fit_side=right`，即 x 较大的那一侧）
- **灶周环**：膨胀 16 px 减去膨胀 5 px 的环上、且仍是 `keep` 的像素
- **灶内**：仅当 `assign_lesion` 曾给灶内标过号，或用种子灰度去硬套

规则摘要：

- 灶内若 70% 以上像某一层种子灰度 → 该层 `fused`，其余 `vanished`
- 否则若某层在环上的点数远少于种子 → `vanished`
- 环上与邻层灰度差突然变小 → `fused`
- 种子太少 → `uncertain`

图上的 Mucosa lost 等来自这里。它**不修改** `labels`。与医生 ticks、病理 T 都可能不一致。

---

## 9. 出图输入输出

`render_wall_pixel_vs_dino_cluster.py` 当前：

| 项 | 值 |
|----|-----|
| A | 紧 ROI + 蓝灶 + **完整画笔黄带** + 整条 heading |
| B | 右侧 heading 窗口，8 倍放大；原分辨率涂标签，最近邻放大，避免黄绿糊在一起 |
| C | 不跑、不画 |
| 画笔半径 | `--brush`，默认 12 |
| 标签透明度 | `PIXEL_BLEND = 0.28` |
| 线宽 | 1 px |

B 的窗口：走行线 `x` 大于 55% 分位的那段，外扩 `brush + 16`，并尽量带一点灶的右缘。

落盘：

```text
pipeline/experiments/reports/lesion_aware_wall_cluster_v1/pixel_vs_dino/
    CASE-008_pixel_vs_dino.png
    CASE-019_pixel_vs_dino.png
    CASE-040_pixel_vs_dino.png
    CASE-076_pixel_vs_dino.png
    index.png
    summary.json
results/visualizations/error_cases/   # 同名拷贝，方便 IDE 打开
```

文件名仍带 `pixel_vs_dino`，是历史名字；内容已是像素两图。

---

## 10. 库里还留着、但出图不用的路径

这些函数还在，单测和旧 eval 会走到。**不要和当前主路径搞混。**

| 开关 | 函数 | 在做什么 |
|------|------|----------|
| `prefer_strips=False` 且 `sensitive=False` | `cluster_features` | 在 `fit` 上对灰度（或灰度+across）做 k-means / GMM / Ward / FCM，再按 `across` 均值把簇排成 0/1/2 |
| `sensitive=True` | `assign_from_across_profile` + 沿 heading 走 | 用法向剖面找亮-暗-亮谷，再一列列往左走 |
| `extra_features=` | 同上，特征换成 DINO PCA | 出图已停 |
| `trace_gray_interfaces` | 沿 across 找灰度梯度峰 | `prefer_strips` 时不用，改走 `interfaces_from_y_bands` |
| `kmeans1d_across` | 只按法向深度切三带 | 旧对照 |

`features_for_method`：

| method | 特征 |
|--------|------|
| `kmeans1d_gray` | `[gray/255]` |
| `kmeans1d_across` | `[across * 0.60]` |
| 其他 | `[gray/255, across * 0.60]` |

旧路径必须用 `across` 给簇排序，否则两个暗簇会对调。这也是黄绿夹杂的根因，所以主路径不再走它。

---

## 11. 常量（主路径真正用到的）

| 名字 | 值 | 作用 |
|------|----|------|
| `MIN_VALID_PIXELS` | 40 | 少于此不聚类 |
| `MIN_FLANK_ARC_PX` | 12 | 排除灶后侧段太短则放弃 |
| `DEFAULT_BRUSH` | 8 | 库默认半宽；出图覆盖为 12 |
| `STRIP_SMOOTH` | 9 | 分界中值窗口下限；贴标签时用 `max(9, 15)=15` |
| `across` 核心阈值 | 0.92 | 丢掉笔刷外圈 |
| 法向搜索 | 36 px | 每个站位沿墙厚左右各读一截 |
| 涂色外扩 | 16 px | 比 A 上细画笔每侧更宽，盖住画笔外的分层 |
| `JOIN_*` / `gentle_curve` | 见库顶 | 只平滑分界折线，不改标签 |

出图另有 `A_SCALE=3`，`B_SCALE=8`，`BRUSH_BLEND=0.20`。

---

## 12. 最小调用例子

```python
import cv2
from wall_lesion_aware_cluster import (
    as_xy, cluster_brush_band, rasterize_polygon, to_gray,
)

image = cv2.imread("pipeline/data/wall_layer_fixtures/v1/CASE-040/frame.jpg")
gray = to_gray(image)
wall = as_xy(meta["wall_polygon"])          # Nx2
lesion = as_xy(meta["lesion_polygon"])      # Mx2
lesion_mask = rasterize_polygon(gray.shape, lesion)
lumen = as_xy(meta.get("lumen_polygon"))
lumen_center = lumen.mean(axis=0) if len(lumen) >= 3 else None

arm = cluster_brush_band(
    gray, wall, lesion_mask,
    brush_radius=12, k=3, dilate_px=0,
    exclude_lesion=True,
    method="kmeans1d_gray",
    lumen_center=lumen_center,
    lesion_poly=lesion,
    fit_side="right",
    assign_lesion=False,
    prefer_strips=True,
)

# arm.status == "ok"
# arm.xs[i], arm.ys[i], arm.labels[i]  是第 i 个笔刷像素
# arm.labels[i] in {-1, 0, 1, 2}
# arm.interfaces[j]["points"]  是第 j 条分界折线
# arm.fates  不是 cT
```

---

## 13. 数据流总图

```text
frame.jpg + meta.wall_polygon + meta.lesion_polygon
        |
        v
  tight_roi / 可选重画灶
        |
        v
  gray, wall_crop, lesion_mask
        |
        v
  densify wall -> rasterize_brush(radius)
        |
        +-- 减灶 --> keep 像素
        |
        v
  sample_band_pixels: xs, ys, gray, across, along_idx
        |
        v
  assign_natural_y_bands
        每列 y 排序 -> 按灰度找中亮或中暗
        -> 沿法向读 24 px，梯度峰定两刀，再投影回列
        -> 法向梯度两刀，沿 heading 抹顺
        -> 宽走廊按 across 贴 0/1/2
        |
        +-- interfaces_from_y_bands --> 两条分界线
        +-- walk_layer_fate ----------> lost / fused 旁证
        |
        v
  ClusterArm
        |
        v
  A: 完整画笔    B: 右侧 8x 层带
```

---

## 14. 已知限制

1. **「从上到下」假设墙大致水平。** P040 右侧成立。走行线很斜（P019）或竖着走时，图像列不再等于墙厚，三带会切歪。那时应改回沿 `across` 切，而不是图像 `y`。
2. **P008 heading 是涂鸦。** 完整画笔在 A 上会缠成一团，B 的「右侧」窗口也会脏。这是笔画问题，不是三等分公式错了。
3. **中段外扩最多 12 px 仍不是解剖金标准。** 只是让色带盖住肉眼看到的那条灰带。对比度不够时才退回三等分。
4. **`fates` 常和医生 ticks、病理不一致。** 只写在图底，不当分期。
5. **P019 无同帧医生灶；P076 重画灶不是 0.179 s 的原笔。** 挖灶不完整时，暗肿块仍可能进走廊。
6. **DINO 对照、完整 Gate 0–3 走廊脚本还没按计划写完。** 不要把本文件当成 DINO 产品说明。
7. **公网未接。** 改本文算法不要 deploy Next。

---

## 15. 和旧文档的关系

[LESION_AWARE_WALL_CLUSTER_20260828.md](../plans/LESION_AWARE_WALL_CLUSTER_20260828.md) 里「特征 = 灰度 + 0.60*across，再 k-means」是 **8 月 28 日第一版**。那一版在两层暗回声上会把黄和绿搅在一起。

**以本文第 6 节为准。** 排除病灶、固定袋、不定 cT、不接工作台，那几条仍然有效。
