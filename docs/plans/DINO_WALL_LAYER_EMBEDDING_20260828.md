# 用 DINOv3 embedding 做胃壁层次特征（研究计划）

日期：2026-08-28。绑定公网医生工作台已有对象，不新开画线工具，不换 Assist 权重，不定 cT。

配套：

- 产品拍板：[胃壁分层与相邻分期纪要](../meetings/2026-08-27_胃壁分层与相邻分期_会议纪要.md)
- 医生线是先验：[浆膜预期走行线协议](../meetings/2026-08-28_浆膜预期走行线协议.md)
- 工作台中栏：`apps/gastric_scan_next/components/InteractiveSegPanel.tsx`
- 工作台右侧：`apps/gastric_scan_next/components/ReaderStudyQueuePanel.tsx`
- 现网灰度聚类：`apps/gastric_scan_next/lib/wall-echo-clarify.ts`、`wall-layer-interrupt.ts`
- 文案 / 四档类型：`apps/gastric_scan_next/lib/reader/wall-prompt.ts`、`adjacent-stage-lock.ts`
- DINO I/O：[roi_lora_io_20260828.md](../references/dinov3/roi_lora_io_20260828.md)

公网医生站是 [http://47.106.33.102](http://47.106.33.102)（根页工作台），不是 LAN `:3000`，也不是 `/reader` 旧台。

---

## 一句话

工作台对象只回答「在哪画、分几层、清不清楚」。**真正的分层必须从走廊里的实际像素，或 DINO 特征，做聚类得到层带**，不能靠平行偏移冒充层次。灰度聚类和 DINO 聚类同场对照；过门以后写进现有 1/2/3 线和四档芯片，不定 cT。

工作台已有按钮 **ROI DINO层**：框灶后可看当前帧 peri-lesion ROI 上 DINOv3 L2 / L5 / L8 / L11 的病灶亲和图和壁相对灶图。这是检查特征，还不是聚类出层带。

---

## 0. 先对齐工作台，再谈 embedding

公网医生真正用的是根页 `app/page.tsx`：中间 `InteractiveSegPanel`，右侧 `ReaderStudyQueuePanel`。`/reader` 的 `ReaderWorkbench` 没有走行线，不要当本计划入口。旧坞「壁层」`WallFeatureAnalysisCard` 是 ContactGeom 贴壁 / 剩余厚度，和 8 月 27 日走行线草稿是两套读数，**不要接**。

右侧已经写死的 7 步（`T_STAGING_TRIAL_STEPS_ZH`）就是本计划的挂点：

```text
1 选大约 2–3 个关键帧
2 框灶；多灶点「再框一灶」
3 不把 T1–T4 输给模型
4 画浆膜预期走行线，一笔穿过可疑区
5 看不清标看不清，不等于中断
6 最多 3 个分析焦点；看右侧四档草稿
   └── 本计划从这里取走廊和 k，在网格上做像素或 DINO 聚类
7 邻帧相近位置还在不在（单帧中断更像伪像）
8 点「辅助分析」（冻结四分类 + 旁路胃壁文案）
```

第一版主任务已经是 **浆膜预期走行线（档位 1）**。1 / 2 / 3 芯片的含义是「分析哪条界面」，不是「已经到了哪一层」。教程原句：分层是草稿，不是病理五层，也不解锁确定 cT。

### 0.1 已经有的对象（必须复用）

| 医生看到的 | 代码里的名字 | 在哪 | 分层时它只定什么 | 层本身从哪来 |
|------------|--------------|------|------------------|--------------|
| 预期走行线 | `wallPoints` / `DoctorKeyframe.wallPolygon` | 中栏笔刷；`doctor_keyframes[]`；`wall_polygon` | **在哪采走廊**（切向脊柱） | 走廊网格上的像素或 token 聚类 |
| 浆膜 / 固有肌 / 浅层 | `wallLayerTarget` = `1 \| 2 \| 3` | 中栏芯片 | **聚成几簇**（k），以及簇排好后贴什么解剖名 | 不是「已经到了哪一层」的答案 |
| 清楚 / 模糊 / 看不清 | `wallVisibility` | 右侧 | 看不清则不聚类、直接 `cannot_judge` | 模糊时簇只准报到 `suspected` |
| 双侧锚定 / 单侧延伸 / 本帧看不清 | `serosaAnchorMode` | 右侧 | 哪些列能当「正常壁」种子；本帧看不清则停 | 种子用来给簇命名，不代替聚类 |
| 最多 3 个分析焦点 | `analysisFocusPoints` | 中栏点击 | 查询段哪些列加重看簇是否丢掉 | **不是**突破点，不当标签 |
| 连续 / 疑似 / 中断 / 无法判断 | `InterruptVerdict` | 右侧芯片 | 聚类之后的读数格式 | 沿每一层带看簇是否断裂或被肿块簇换掉 |
| 最深窄带亮-中-暗图 | `clarifyDeepestEcho` | 中栏坞 | 现网像素聚类对照（M0） | 现在只按亮度分，要升级成按层带分 |
| 亮-暗-亮中断 | `detectBrightDarkInterrupt` | 画线后重核 | M0 沿层带的旧读数 | DINO 簇用「簇标签是否还在」替代纯亮度 |
| 传到其他关键帧、邻帧黄字 | `keyframe-propagate` + `compareKeyframeContinuity` | 中栏 / 右侧 | 每帧自己聚；单帧断邻帧还在则降成疑似 | 各帧走廊像素/token 分别聚类 |
| 灶周矩形 | `periLesionRoi` | 已进请求 | 只给冻结四分类看形态 | **太宽，不当聚类网格** |
| 多灶 | `extraLesionPolygons` | 「再框一灶」 | 主灶定最深点 | 仍只在一条走行走廊里聚类 |

几何函数已经在 `lib/wall-polyline.ts`：`densifySmooth`、`closestOnPoly`、`offsetAlongNormals`、`centroidPts`。最深点已经在 `deepestInvasionPoint`。装草稿已经在 `attachLayerInterrupts` / `applyWallPromptMeta` / `recheckWallInterruptDraft`。右侧只听事件 `WALL_ASSIST_DRAFT_EVENT`，类型是 `WallAssistDraftDetail`。

**不要新建**第二套浆膜线类型、新画线工具、新五层 mask、新右侧卡片、新四档名词。

### 0.2 工作台已经送到分析、但还缺什么

点「辅助分析」：`InteractiveSegPanel.runUnifiedAgent` → `page.tsx` `handleReaderUnifiedAgent` → `POST /api/reader/agent/analyze` → `pipeline/agent/product/analyze_case.py`。公网写死 `assist_profile: 'contour_anchored_fast'`，sidecar 走 `_analyze_classify_only`，**整条壁证据图和 DINO 分割都 skip**。

现在请求里**已经有**（字符串 / 布尔，不是几何）：

- `contour_context.wall_target_layers`
- `contour_context.wall_interrupts` / `wall_ticks` / `wall_note`
- `contour_context.echo_pattern` / `echo_note`（例如 `亮-暗-亮`）
- `contour_context.keyframe_interrupts[]`（每帧 `timeSec` + interrupts）
- `contour_context.peri_lesion_roi`、`extra_lesion_count`
- `frames[]`：图、主灶 `mask_polygon`、胃腔

`analyze_case_lib._wall_draft_from_contour` 只把这些收成旁路句子，并且 `_WALL_DRAFT_CONTEXT_KEYS` 保证**不能**拿它们解锁确定 cT。这层约束本计划必须保留。

现在请求里**没有**（字段在工作台里已经存在，只是没送出去）：

| 已有但没进 Assist | 存在哪 | 后果 |
|-------------------|--------|------|
| 走行折线 | `wallPoints`、`DoctorKeyframe.wallPolygon`、保存遮罩时的 `wall_polygon` | sidecar 看不到走廊，线上做不了 M2 |
| 分析焦点坐标 | `analysisFocusPoints` | 只能看到 `focusCount` 文案 |
| 可见度 / 锚定 | `wallVisibility` / `serosaAnchorMode` | sidecar 看不见「看不清」 |
| 四档里的 `suspected` / `cannot_judge` | `LayerInterrupt.verdict` | sidecar 只读 `interrupted` 布尔 |
| `adjacent_lock` | `DoctorCaseState`；`UnifiedAgentCapture` 类型写了、组包没填 | 锁只改大字显示，不进模型（保持这样） |
| 窄带伪彩像素 | `WallEchoClarify.original` / `clarified` | 只送了中文 pattern |

`page.tsx` 组 `mask_override` 时只有 `mask_polygon` + `roi_bbox`。全量管线其实已经会读 `mask_override.wall_polygon`（`pipeline_adapter.py`），但公网根本没带上，而且公网也不走全量管线。

所以：**缺的不是工作台对象，是「折线没进分析」+「1/2/3 线主要靠平行偏移，还没有用像素或 DINO 特征把走廊聚成层带」。**

### 0.3 不要接的现成接口

| 看起来像 DINO / 胃壁 | 实际是什么 | 为什么不接 |
|----------------------|------------|------------|
| `/api/agent/dino/features` | 全图 / ROI 池化 | 正是「全图 512 token」，分层必死 |
| `cache_dinov3_tstaging_rich_scalars.py` | lesion / wall 整区平均 | 走行被抹掉 |
| Gate C mask pooling / TabPFN | 问 T 几 | 对象是分期向量，不是层图 |
| `WallFeatureAnalysisCard` | 旧 ContactGeom 五层回声 | 和走行线草稿抢语义 |
| 分类器第 5 通道 wall SDF | P0.2 已 FAIL | 不要再把壁压成一张图 |

---

## 1. 分层引擎：先验定走廊，聚类出层带

医生画的线和档位**不是层**。层是走廊网格里「哪些采样点属于同一条回声带」。8 月 27 日会上说的也是这句话：人眼大致亮 / 中 / 暗，AI 用区域聚类，目的是分层，不是普通超分。

### 1.1 现网差在哪（必须说清楚）

工作台现在其实是三套东西叠在一起，不要混报：

| 现网函数 | 实际在做什么 | 算不算「特征聚类分层」 |
|----------|--------------|------------------------|
| `clusterLayersAlongWall` | 沿灶缘做 1/2/3 条**平行偏移**；只有 `layerCount=3` 时才用灰度梯度微调间距 | **不算。** 层间距是几何，不是把像素聚成层 |
| `traceWallLayersFromPaint` | 笔刷条带上找灰度梯度峰，再平行外推 | **半算。** 用了像素梯度，但没有对特征做 k-means，峰不够就回退成均匀间距 |
| `clarifyDeepestEcho` | 最深窄带 56 x 28 上对**灰度**做 1D k-means，k=2 或 3 | **算像素聚类。** 但簇按亮度叫暗 / 中 / 亮，**不按解剖层**排序 |
| `detectBrightDarkInterrupt` | 沿线看两端亮、中间暗 | 中断读数，不是出层带 |

所以现网「1/2/3 分层」看起来像层，多数时候是平行线；现网「聚类」出的是亮暗图，不是浆膜 / 固有肌 / 浅层。本计划要把这两步并成一步：

```text
wallPolygon + wallLayerTarget(k) + 可见度
    -> 同一块走廊网格（沿 x 跨，对齐现网 56 x 28）
    -> 每个采样点一个特征向量
         像素：灰度，可选再加沿法向深度
         DINO：插值 token，先 PCA 到 8–32 维
         可选拼接： [gray, depth, token_pca]
    -> k-means / GMM，k = wallLayerTarget（看不清则不聚）
    -> 簇按「沿法向的平均深度」从腔侧排到浆膜侧
    -> 再贴解剖名：k=1 浆膜；k=2 固有肌, 浆膜；k=3 浅层, 固有肌, 浆膜
    -> 每条层带沿走行看簇是否连续
    -> 写成现有 ticks + InterruptVerdict
```

**排序必须用法向深度，不能用亮度。** 浆膜和界面都可以亮；固有肌和肿块都可以暗。按亮暗命名会回到现网 M0 的上限。

锚定段（`serosaAnchorMode`）只做两件事：给聚好的簇起名字（两端最外侧簇 = 浆膜），以及提供「正常壁」种子。它不代替聚类，也不在查询段空想平行线。

### 1.2 走廊网格（复用现网采样，不新造坐标系）

和 `clarifyDeepestEcho` 同一套：

- 原点：`deepestInvasionPoint` 落到 `wallPolygon` 上
- 切向 / 法向：现网已经会朝胃腔外侧翻法向
- 网格：沿约 56，跨约 28；跨向半宽跟笔刷走（现网 `acrossHalf`）
- 每个格子记下：图像坐标、灰度、沿法向深度、可选 DINO token

档位 2 / 3 时不要另开第二套网格，只是把 k 从 1 改成 2 或 3，让聚类在**同一块厚度**上多分几带。k=1 时聚 2 簇也可以：一层「还像浆膜」，一层「其他」（肿块 / 腔 / 伪像），中断看浆膜簇在查询段还在不在。

### 1.3 像素聚类（M0 升级）和 DINO 聚类（M1）必须同场

| 代号 | 每个格子的特征 | 和现网的关系 | 角色 |
|------|----------------|--------------|------|
| **M0** | 灰度，或 `[灰度, 法向深度]` | 现网 `kmeans1d` 只吃灰度。升级后 k 跟 `wallLayerTarget` 走，簇按深度排序 | 像素聚类基线，界面先留着亮-中-暗图作对照 |
| **M1** | DINO token（PCA 后），或 `[灰度, 深度, token_pca]` | 还没有。网格必须和 M0 对齐 | **主候选。** 分层看的是「像不像同一层组织」，不是亮不亮 |
| **M2** | 锚定段簇中心当本例模板，查询段逐点算到各层中心的距离 | 协议里的模板匹配 | 聚类之后的辅助读数：中断 / 换层，不单独出层带 |

默认出层带看 M1，M0 并列对照，M2 只写连续 / 中断。医生改芯片仍然覆盖两者。

可见度规则抄工作台：

```text
wallVisibility == unseen  或  serosaAnchorMode == unanalyzable
    -> 不聚类，verdict = cannot_judge
wallVisibility == blurry
    -> 仍聚类出层带，但中断最多 suspected
只有 1 帧某层簇断了、邻帧同层还在
    -> 降成 suspected
```

分析焦点只加重查询段里那几列「浆膜簇还在不在」，不把焦点坐标写成突破点。

### 1.4 从簇到工作台线 / 芯片

聚完之后才能画现在中栏那些层线：

1. 每个簇沿切向取厚度中位数，得到一条折线，写入现有 `wallLayerBands`（不要新类型）。
2. 查询段里该簇面积掉到锚定段的一小半，或格子改判成病灶 mask 内的「其他」簇 → 该层 `interrupted` / `absent`，后面改假想线（现网 `imaginary` 已有）。
3. `ticks` 的 `present / thinned / absent / imaginary / unseen` 继续用。
4. `LayerInterrupt.verdict` 仍是四档。

伪代码（说明用）：

```python
k = wallLayerTarget                    # 1 / 2 / 3，医生选的是簇数
grid = sample_corridor(wallPolygon)    # 56 x 28，与 clarifyDeepestEcho 对齐

if wallVisibility == "unseen" or serosaAnchorMode == "unanalyzable":
    return ticks_unseen, verdict="cannot_judge"

# M0：像素；M1：DINO 或像素+DINO
feat_m0 = [gray] or [gray, depth]
feat_m1 = pca(token) or [gray, depth, pca(token)]
labels = kmeans(feat, k=k)             # 或 k+1，多一簇给「其他/肿块」

# 按法向平均深度排序：0 = 最靠腔，k-1 = 最靠浆膜
order = argsort([mean_depth(cluster) for cluster in labels])
names = {1: ["浆膜"], 2: ["固有肌", "浆膜"], 3: ["浅层", "固有肌", "浆膜"]}[k]

bands = [median_curve(cluster) for cluster in order]   # -> wallLayerBands
verdicts = [interrupt_if_cluster_drops(cluster, foci) for cluster in order]
```

---

## 2. Embedding 在这条工作台链路里是什么

一张关键帧进 DINOv3 ViT-B/16（512）会得到 32 x 32 个 token，每个 768 维。不是亮度，是「这一小块长得像什么」。

对照分层三句话：

1. 像素聚类：每个格子 1 个（或 2 个）数，只能按亮暗和深浅分带。
2. DINO 聚类：每个格子变成一小段向量，浆膜亮线和肝包膜亮线可以进不同簇。
3. 右侧四档仍然够用。聚类负责出层带和「这层还在不在」；芯片格式不改。

以前仓库里的 DINO 问「这例是 T 几」。本计划问「**这条走廊里的格子，聚成几条还在的层带**」。

---

## 3. 为什么不再把模板匹配当主方法

M2（两端像不像）对 T3/T4 浆膜连续性仍然有用，但它**不出层**。档位 2 / 3 要的是厚度方向上几条不同组织，必须靠聚类。主方法改成 M0 / M1 聚类出带，M2 只辅助判中断。

---

## 4. 决定成败的一刀：走廊裁剪，不要工作台里的大框冒充

`periLesionRoi` 已经把走行线扩进灶周矩形（margin 48），这个框是给冻结四分类看形态的，**太宽**，不能当 DINO 分层输入。全图 512 更不行：一个 token 大约 20–25 个原图像素，薄壁挤在半个 token 里。

必须从 `wallPolygon` 做窄走廊（切向加长、法向约一倍笔刷），再 letterbox 到 512，记下 `(scale, ox, oy)` 和 `token_px_in_original`。目标：每个 token 大约 2–4 个原图像素。采样点双线性插回 32 x 32 网格，和 M0 的沿 / 跨方向对齐，方便并排伪彩。

两个 backbone 对照（同一条工作台折线）：

1. 官方 LVD-1689M
2. 20260511 last-2 adapter（胃超声分割最好数字；可能把壁压成背景）

层 2 / 5 / 8 / 11 都缓存。浅层更像回声条带，深层更像壁 vs 肿块。不要先只用 last-block。

---

## 5. 输入从工作台哪读，输出写回哪

### 5.1 离线探针（Gate 0–2，先做这个）

数据源按这个顺序，**禁止**用合成浆膜报成绩：

1. 病例草稿 `doctor_case_state.json` → `doctor_keyframes[].wallPolygon`（医生当晚画的线）
2. 遮罩历史 `mask_overrides.json` → `wall_polygon`（医生保存过的线）
3. 都没有 → 只出 smoke 拼图，不写一致率

同帧还要带上工作台已经存好的：`lesionPolygon`、`lumenPolygon`、`analysisFocusPoints`、`wallVisibility`、`serosaAnchorMode`、`wallLayerReadout.interrupts`（医生改过的四档）、`timeSec`（多帧）。

图用工作台当时那一帧，不要另找 Phase-0 `crop_roi`。

### 5.2 输出形状必须能塞进现有 UI

报告：`pipeline/experiments/reports/dino_wall_layer_probe_v1/`

| 字段 | 对齐工作台 |
|------|------------|
| `m0_verdict` / `m1_verdict` | `InterruptVerdict` 四档 |
| `m0_bands` / `m1_bands` | 与 `wallLayerBands` 同形的折线 |
| `cluster_map` | 56 x 28 簇号图，按法向深度着色，不是按亮度 |
| `m2_query_sim_min` | 可选，只辅助中断 |
| `multi_frame_agree` | 抄 `compareKeyframeContinuity` |
| `token_px_in_original` | 防止全图 512 混进来 |
| `backbone` / `layer` | `lvd1689m` 或 `adapter_20260511`；2 / 5 / 8 / 11 |

拼图四列：工作台原图 + 走行线、现网亮-中-暗图、M0 按深度着色的像素簇、M1 的 DINO 簇。进产品时 M1 簇图放在「最深窄带回声」坞旁边，层线仍写进现有 `wallLayerBands`。黑底、Times New Roman；标题不要用中间点。

### 5.3 线上怎么挂（Gate 3 才做，分两刀）

**第一刀，不跑 DINO：** 把工作台已有字段补进 Assist 请求。没有折线，后面任何走廊模型都是空话。

- `page.tsx` 的 `mask_override` 加上 `wall_polygon`（和保存遮罩同一套坐标）
- `contour_context` 加上 `analysis_focus_points`、`wall_visibility`、`serosa_anchor_mode`
- `wall_interrupts` 带上 `verdict`，不要只留 `interrupted`
- 这些键继续放进 `_WALL_DRAFT_CONTEXT_KEYS`，仍然不能解锁 cT
- `adjacent_lock` 继续只改大字，**不要**填进模型输入
- 改了请求包装必须 `bash scripts/deploy_public_next.sh`，记下 BUILD，提醒硬刷新

**第二刀，过 Gate 2 以后：** 在 `_analyze_classify_only` **之后**、拼 `supporting_evidence` **之前**，加可选一步 `dino_wall_corridor`。

- 复用 sidecar 已加载的冻结 ViT，不要前端跑模型，不要改成 `assist_profile: 'full'`
- 输入就是上一刀补上的折线 + 焦点 + 可见度
- 输出：`wallLayerBands` + 与 `LayerInterrupt` 同形的四档，事件仍走 `WALL_ASSIST_DRAFT_EVENT`
- 中栏并列「像素簇 / DINO 簇」；右侧芯片仍是同一套四档，医生点改仍然有效
- 大字仍是冻结四分类

### 5.4 脚本（还没写）

```text
scripts/extract_dino_wall_corridor_tokens.py
    从 doctor_keyframes / mask_overrides 读 wallPolygon
    走廊裁剪 + 冻结 DINO + 采样点缓存

scripts/eval_dino_wall_corridor_methods.py
    同一网格跑像素聚类 M0、DINO 聚类 M1、可选 M2 中断

scripts/render_dino_wall_corridor_panel.py
    工作台线 + 亮暗图 + 像素簇 + DINO 簇（按法向深度着色）
```

缓存：`pipeline/data/dino_wall_corridor_tokens/v1/`（大文件，只索引）。不要改 `dinov3_tstaging_region_scalars` 的 schema。先 `--help`，再进 `scripts/script_registry.csv`。

---

## 6. 门控

患者级划分。阈值不在 Reader v150 上扫。医生改过的芯片是对照，不是拿病理 T 反训。

### Gate 0 — 工作台折线够不够、token 够不够细

有真实 `wallPolygon` 的 10–20 帧上算 `token_px_in_original`。没有线就停，不要用 ContactGeom 假线凑数。

- 走廊裁剪后每个 token ≤ 约 4 原图像素 → 往下
- 仍 ≥ 12 → 先改走廊宽度 / 进网边长，不要开聚类

### Gate 1 — 簇看起来像不像层带

双侧锚定、可见度清楚、医生选了 k 的帧：

1. 厚度方向上应能看出约 k 条沿走行延伸的带，而不是沿切向切成一段段。
2. 最外侧带应落在医生线附近，不要贴到肝包膜。
3. 同一亮度、不同组织（浆膜 vs 肝缘 vs 肿块亮边）在 M1 里应尽量进不同簇；若 M1 和亮度图几乎一样，说明 token 没有多给信息。
4. k=2 / 3 时，簇的平均法向深度应单调排开，不要交叉成碎片。

LVD 与 20260511、层 2 与 11 各出一套。过门：人能从 M1 簇图读出层带，且明显不同于「只按亮暗上色」。不过门：先查网格和 k，不要 LoRA。

### Gate 2 — 和医生改过的层线 / 芯片比

金标准两层：医生拖过的 `wallLayerBands`（如果有），以及右侧点过的 `InterruptVerdict`。另册，不在同一 150 例上自评自涨。

主指标：层带与医生线的法向距离、四档一致率、假中断、漏中断。对照纯平行偏移、M0 像素簇、M1 DINO 簇、以及「两家都中断才报中断」。病理 T3/T4 只作弱旁证。

过门：M1 层带比平行偏移更贴医生线，或假中断低于 M0 且漏中断不升。不过门：界面继续用现网平行线 + 亮暗图。

### Gate 3 — 才改 sidecar / Next

先补折线请求（5.3 第一刀），再加 `dino_wall_corridor`（第二刀）。改了 Next 必须部署公网。

### Gate 4 — 伪标签与可选 LoRA（后做）

医生短线 + 算法路径 + 芯片确认 → A/C 级。A 级才可作走廊标签。监督是「像壁 / 不像壁」，不是 T1–T4。

---

## 7. 和现网两条线怎么相处

```text
公网工作台（已上线，明晚验收的主线）
  7 步 + 走行线 + 灰度 M0 + 右侧四档 + 冻结四分类旁路
  先不要改芯片文案和画线手感

本计划
  同一走廊网格
  像素聚类 M0 对照，DINO 聚类 M1 出层带
  过门 → 请求补折线 → sidecar 把簇线写回 wallLayerBands

分类研究（Gate C / TabPFN）
  继续问 T 几
  以后可以吃本计划的中断标量
  现在不要把走廊 token 拼进四分类表
```

---

## 8. 明确不要做

1. 不要新画线工具、新折线类型、新右侧卡片、新五层 GT。也不要用平行偏移冒充分层。
2. 不要接 `WallFeatureAnalysisCard` 或 `/api/agent/dino/features`。
3. 不要用全图 512 region scalar 或 Dual `crop_roi` 冒充分层。
4. 不要把 `periLesionRoi` 大框当成走廊。
5. 不要把公网 `assist_profile` 改成 `full` 只为了加载 DINO。
6. 不要把看不清写成中断，也不要忽略工作台已有的可见度 / 锚定。
7. 不要把医生 T 或 `adjacent_lock` 送进 DINO。
8. 不要在同一 150 例上扫阈值、换 Assist、写 self-evolving。
9. 不要还没做 Gate 0 就训 LoRA。
10. 标题和轴不要用中间点。

---

## 9. 建议工期

| 顺序 | 工作 | 大约 |
|------|------|------|
| 1 | 从 `doctor_keyframes` / `mask_overrides` 读线，走廊裁剪 + Gate 0 | 1 天 |
| 2 | 同一网格跑像素簇 M0 与 DINO 簇 M1，出按深度着色的拼图（Gate 1） | 1–2 天 |
| 3 | LVD vs 20260511、层 2 vs 11 | 0.5 天 |
| 4 | 等医生在工作台上改过的芯片，做 Gate 2 | 有标签再排 |
| 5 | 请求体补 `wall_polygon`（产品小补丁，即使 DINO 不过门也该做） | 0.5 天 + 公网部署 |
| 6 | Gate 2 过了再加 sidecar 并列草稿 | 不预支 |

第一周交付：脚本骨架、有真实走行线的拼图、Gate 0/1 书面结论。不承诺公网分层变准。第 5 步「折线进请求」可以单独做，因为它只是把工作台已有字段送出去。

---

## 10. 对医生 / 合作者怎么讲

**对医生：** 你画的线告诉 AI 沿哪走、大概分几层。层带本身由走廊里的回声（灰度或 DINO）聚类出来，不是平行描边。右侧四档仍可改。看不清继续标看不清。

**对合作者：** 工作台先验只定走廊和 k。分层是同一网格上的像素聚类 vs DINO 特征聚类。输出必须是现有 `wallLayerBands` + `InterruptVerdict`。

**对论文：** 人给出走行和层数先验，AI 在最深窄带做区域聚类得到残存层。灰度是对照，DINO 是同网格的第二种特征。没有工作台折线，不要把探针拼图写成性能。

---

## 11. 开放风险

- 分割 adapter 可能抑制壁纹理，必须和 LVD 对照。
- 工作台笔刷很细，走廊太窄会裁掉外缘，太宽会混进肝和腔。Gate 0 要扫宽度，并对照现网 `acrossHalf`（约笔刷的一半）。
- k-means 对薄壁很碎；必须加「沿切向平滑 / 多数表决」（现网 M0 已有 3x3 表决），否则层带会断成斑块。
- 分析焦点是点不是段；加权过度会把医生「想看的地方」直接判成中断。焦点只加重查询列，不改标签定义。
- 只按亮度排序簇，会把浆膜和肝缘合成一层。必须用法向深度排序。
- sidecar 现在只认 `interrupted` 布尔。线上并列之前必须先把 `verdict` 送出去，否则 DINO 的「无法判断」会被吃成连续。
- 前端跑不动 ViT；产品路径只能走分析隧道。
- 没有折线的历史训练集不能假装有分层 GT。
