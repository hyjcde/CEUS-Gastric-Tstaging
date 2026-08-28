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

工作台已经能画浆膜预期走行线、用灰度算出四档草稿、再点辅助分析。DINO 不要另起一套分层，只做**同一条走廊上的第二种读数**：记住两端正常壁的 token，问中间还像不像。过门以后写进现有芯片和旁路文案，不解锁确定 cT。

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
   └── 本计划从这里读线、读焦点、读可见度
7 邻帧相近位置还在不在（单帧中断更像伪像）
8 点「辅助分析」（冻结四分类 + 旁路胃壁文案）
```

第一版主任务已经是 **浆膜预期走行线（档位 1）**。1 / 2 / 3 芯片的含义是「分析哪条界面」，不是「已经到了哪一层」。教程原句：分层是草稿，不是病理五层，也不解锁确定 cT。

### 0.1 已经有的对象（必须复用）

| 医生看到的 | 代码里的名字 | 在哪 | 本计划怎么用 |
|------------|--------------|------|--------------|
| 预期走行线 | `wallPoints` / `DoctorKeyframe.wallPolygon` | 中栏笔刷；病例草稿 `doctor_keyframes[]`；遮罩历史 `MaskBoundaryOverride.wall_polygon` | **走廊先验**。M2 的锚定段 / 查询段都从这条线来 |
| 浆膜 / 固有肌 / 浅层 | `WallAnatomyTarget` = `1 \| 2 \| 3`，state `wallLayerTarget` | 中栏芯片；`DoctorCaseState.wall_target_layers` | 读哪条界面。第一刀只做 `1`（浆膜） |
| 清楚 / 模糊 / 看不清 | `WallVisibility` | 右侧；`DoctorKeyframe.wallVisibility` | `unseen` → 强制 `cannot_judge`；`blurry` → 最多 `suspected` |
| 双侧锚定 / 单侧延伸 / 本帧看不清 | `SerosaAnchorMode` | 右侧；`DoctorKeyframe.serosaAnchorMode` | `bilateral` 才做双侧模板；`unanalyzable` → 无法判断 |
| 分析焦点（最多 3 点） | `analysisFocusPoints` | 中栏点击；`DoctorKeyframe.analysisFocusPoints` | 查询段加权，**不是**突破点 |
| 连续 / 疑似中断 / 中断 / 无法判断 | `InterruptVerdict`；`LayerInterrupt` | 右侧芯片，可点改；`wallLayerReadout.interrupts` | DINO 必须吐**同一套四档**，不要新标签 |
| 最深窄带原图 + 亮-中-暗伪彩 | `WallEchoClarify`（`patternZh`、`clarified`） | 中栏坞「最深窄带回声（草稿）」 | **M0 基线**，界面先留着 |
| 亮-暗-亮中断 | `detectBrightDarkInterrupt` / `attachLayerInterrupts` | 画线后自动重核 | M0 的 verdict 来源 |
| 传到其他关键帧 | `keyframe-propagate.ts` + `DoctorKeyframe` | 中栏 | 各帧自己的 `wallPolygon` / readout |
| 邻帧连续性黄字 | `compareKeyframeContinuity` | 右侧 `WallAssistDraftDetail.keyframes` | 单帧断、邻帧还在 → 疑似伪像。DINO 必须服从这套规则 |
| 灶周矩形 | `periLesionRoi({ lesion, extras, wall })` | 已进 `contour_context.peri_lesion_roi` | 只是大框。走廊裁剪要比它更贴线 |
| 多灶 | `extraLesionPolygons`（最多再加 4 个） | 中栏「再框一灶」 | 主灶 + 走行线；不要为每个灶新画一套层 |

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

所以：**缺的不是工作台对象，是「折线没进分析」+「走廊里还在比灰度」。**

### 0.3 不要接的现成接口

| 看起来像 DINO / 胃壁 | 实际是什么 | 为什么不接 |
|----------------------|------------|------------|
| `/api/agent/dino/features` | 全图 / ROI 池化 | 正是「全图 512 token」，分层必死 |
| `cache_dinov3_tstaging_rich_scalars.py` | lesion / wall 整区平均 | 走行被抹掉 |
| Gate C mask pooling / TabPFN | 问 T 几 | 对象是分期向量，不是层图 |
| `WallFeatureAnalysisCard` | 旧 ContactGeom 五层回声 | 和走行线草稿抢语义 |
| 分类器第 5 通道 wall SDF | P0.2 已 FAIL | 不要再把壁压成一张图 |

---

## 1. 现网灰度（M0）为什么够用当对照、不够用当终点

中栏已经在做的事（`clarifyDeepestEcho`）：

```text
病灶 + 走行线
  -> deepestInvasionPoint 落到壁上
  -> 切向 x 法向采约 56 x 28 窄带
  -> 灰度 1D k-means（对比度大则 k=3，否则 k=2）
  -> 厚度方向压成 暗 / 中 / 亮
  -> detectBrightDarkInterrupt：两端亮、中间暗 → 疑似中断
  -> attachLayerInterrupts 写成 InterruptVerdict
  -> 事件推到右侧同一套芯片
```

几何脚手架是对的。上限是特征只有亮度。浆膜、肝包膜、气体界面、伪像都可以「看起来亮」；固有肌、胃腔、坏死灶都可以「看起来暗」。工作台已经让医生画出「这例自己的正常壁在哪」，灰度却没有把两端当成**本例模板**。

DINO 要补的正是工作台已经给了、灰度用不上的那一步：锚定段（`SerosaAnchorMode = bilateral` 的两端）提取模板，查询段（线的中段，可被 `analysisFocusPoints` 加重）问像不像。

---

## 2. Embedding 在这条工作台链路里是什么

一张关键帧进 DINOv3 ViT-B/16（512）会得到 32 x 32 个 token，每个 768 维。不是亮度，是「这一小块长得像什么」。

对照工作台三句话：

1. 灰度 M0 已经在窄带上按区域分亮 / 中 / 暗。token 也是区域表示，只是每个点从 1 个数变成 768 个数。
2. 医生两端画的是可见正常浆膜（锚定）。同一条线上两端 token 应该像；中间被肿块占住即使仍亮，也应该不像。
3. 右侧四档已经够用。DINO 只替换或并列 `LayerInterrupt.verdict`，不发明第五档。

以前仓库里的 DINO 问「这例是 T 几」。本计划问「**这条 `wallPolygon` 上，哪一段还像壁**」。

---

## 3. 三种方法，全部吃工作台同一条线

| 代号 | 走廊里比什么 | 工作台现成函数 | 角色 |
|------|----------------|----------------|------|
| **M0** | 灰度 1D k-means + 亮-暗-亮 | `clarifyDeepestEcho`、`detectBrightDarkInterrupt`、`recheckWallInterruptDraft` | **产品基线，界面不撤** |
| **M1** | token 先 PCA 再到 k-means / GMM，用锚定段把簇标成壁样 / 肿块样 / 其他 | 还没有；采样网格应对齐 M0 的 56 x 28 | 研究作图 |
| **M2** | 锚定段平均 token = 本例模板，查询段逐点余弦 | 协议第 3–5 步；工作台有线、有锚定、还没做成模板 | **主候选** |

默认读 M2，M1 出拼图，M0 始终并列。医生改芯片（`cycleInterruptVerdict` / `toggleDoctorInterrupt`）仍然是金标准覆盖，DINO 不得锁死。

可见度规则必须抄工作台，不要自己发明：

```text
wallVisibility == unseen  或  serosaAnchorMode == unanalyzable
    -> verdict = cannot_judge
wallVisibility == blurry
    -> 最多 suspected，不得报 interrupted
只有 1 帧 interrupted、邻帧 continuous（compareKeyframeContinuity）
    -> 降成 suspected（伪像）
```

第一刀只做档位 1（浆膜）。档位 2 / 3 等医生真的在工作台上画固有肌 / 浅层线再开。

M2 伪代码（说明用；输出必须能塞进现有 `LayerInterrupt`）：

```python
line = DoctorKeyframe.wallPolygon          # 已有
foci = DoctorKeyframe.analysisFocusPoints  # 已有，最多 3
vis  = DoctorKeyframe.wallVisibility
anchor = DoctorKeyframe.serosaAnchorMode

if vis == "unseen" or anchor == "unanalyzable":
    return LayerInterrupt(verdict="cannot_judge")

# 走廊：沿 line 用 densifySmooth + offsetAlongNormals
# 进网：走廊裁剪 letterbox 512，不要 crop_ui 全图，不要 Dual crop_roi
v = interpolate_tokens(line_samples)       # 亚 token

if anchor == "bilateral":
    template = mean(v on both flanks if vis == "clear")
else:
    template = mean(v on the one visible flank)

sim(s) = cosine(v(s), template)
# 可选：再减病灶 mask 内靠近查询段的 lesion_template

verdict = same_four_labels_as_M0(sim, foci_weight=foci)
```

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
| `m0_verdict` / `m2_verdict` | `InterruptVerdict` 四档 |
| `m2_anchor_sim_mean` / `m2_query_sim_min` | 新标量，只进报告 |
| `m2_end_minus_mid` | 对现网 `detectBrightDarkInterrupt` 的 `delta` |
| `multi_frame_agree` | 抄 `compareKeyframeContinuity` |
| `token_px_in_original` | 防止全图 512 混进来 |
| `backbone` / `layer` | `lvd1689m` 或 `adapter_20260511`；2 / 5 / 8 / 11 |

拼图三列即可：工作台原图 + 走行线、现网 M0 窄带伪彩、M2 相似度热条。热条将来如果进产品，放在中栏坞「最深窄带回声（草稿）」**旁边第二张图**，不要新开卡片。黑底、Times New Roman；标题不要用中间点。

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
- 输出一个和 `LayerInterrupt` 同形的草稿，事件仍走 `WALL_ASSIST_DRAFT_EVENT`
- 右侧同一排芯片并列「灰度 / DINO」，医生点改仍然有效
- 大字仍是冻结四分类

### 5.4 脚本（还没写）

```text
scripts/extract_dino_wall_corridor_tokens.py
    从 doctor_keyframes / mask_overrides 读 wallPolygon
    走廊裁剪 + 冻结 DINO + 采样点缓存

scripts/eval_dino_wall_corridor_methods.py
    同一缓存跑 M0 / M1 / M2；M0 应能对上前端四档

scripts/render_dino_wall_corridor_panel.py
    工作台线 + M0 伪彩 + M2 热条
```

缓存：`pipeline/data/dino_wall_corridor_tokens/v1/`（大文件，只索引）。不要改 `dinov3_tstaging_region_scalars` 的 schema。先 `--help`，再进 `scripts/script_registry.csv`。

---

## 6. 门控

患者级划分。阈值不在 Reader v150 上扫。医生改过的芯片是对照，不是拿病理 T 反训。

### Gate 0 — 工作台折线够不够、token 够不够细

有真实 `wallPolygon` 的 10–20 帧上算 `token_px_in_original`。没有线就停，不要用 ContactGeom 假线凑数。

- 走廊裁剪后每个 token ≤ 约 4 原图像素 → 往下
- 仍 ≥ 12 → 先改走廊宽度 / 进网边长，不要开聚类

### Gate 1 — 同一条工作台线上，M2 热条人能不能看懂

双侧锚定、可见度清楚的帧：

1. 两端高相似
2. 分析焦点附近若医生标了中断，相似度应掉下去
3. 肝包膜 / 界面亮线不应吃成高相似

LVD 与 20260511、层 2 与 11 各出一套。过门：人能看出「两端像、中间不像」，且比「中间只是变暗」清楚。不过门：查线是不是裁歪、法向是不是朝腔。不要 LoRA。

### Gate 2 — 和医生改过的芯片比

金标准是工作台右侧医生点过的 `InterruptVerdict`（含看不清）。另册，不在同一 150 例上自评自涨。

主指标：四档一致率、假中断、漏中断、多帧后假中断是否下降。对照 M0、M2、以及「两家都中断才报中断」。病理 T3/T4 只作弱旁证。

过门：假中断低于 M0 且漏中断不升，或联合规则明显降假中断。不过门：灰度继续当产品。

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
  读同一条 wallPolygon
  离线 M2 → 过门 → 请求补折线 → sidecar 并列草稿

分类研究（Gate C / TabPFN）
  继续问 T 几
  以后可以吃本计划的中断标量
  现在不要把走廊 token 拼进四分类表
```

---

## 8. 明确不要做

1. 不要新画线工具、新折线类型、新右侧卡片、新五层 GT。
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
| 2 | 同一采样点复现 M0，出 M2 热条（Gate 1） | 1–2 天 |
| 3 | LVD vs 20260511、层 2 vs 11 | 0.5 天 |
| 4 | 等医生在工作台上改过的芯片，做 Gate 2 | 有标签再排 |
| 5 | 请求体补 `wall_polygon`（产品小补丁，即使 DINO 不过门也该做） | 0.5 天 + 公网部署 |
| 6 | Gate 2 过了再加 sidecar 并列草稿 | 不预支 |

第一周交付：脚本骨架、有真实走行线的拼图、Gate 0/1 书面结论。不承诺公网分层变准。第 5 步「折线进请求」可以单独做，因为它只是把工作台已有字段送出去。

---

## 10. 对医生 / 合作者怎么讲

**对医生：** 你现在画的线和右侧四档都保留。我们试的是让 AI 记住你两端正常壁长什么样，再到中间问还像不像。看不清你继续标看不清。辅助分析的大字还是原来的冻结结果。

**对合作者：** 这是工作台 few-shot 本例模板匹配。先验是 `wallPolygon` + 可见度 + 锚定 + 焦点，不是新网络。输出必须是现有 `InterruptVerdict`。

**对论文：** 人给出走行先验和相邻期锁定，AI 只读最深局部是否还像壁。灰度是工作台对照，DINO 是同走廊的第二种特征。没有工作台折线，不要把探针拼图写成性能。

---

## 11. 开放风险

- 分割 adapter 可能抑制壁纹理，必须和 LVD 对照。
- 工作台笔刷很细，走廊太窄会裁掉外缘，太宽会混进肝和腔。Gate 0 要扫宽度，并对照现网 `acrossHalf`（约笔刷的一半）。
- 分析焦点是点不是段；加权过度会把医生「想看的地方」直接判成中断。焦点只加权，不改标签定义。
- sidecar 现在只认 `interrupted` 布尔。线上并列之前必须先把 `verdict` 送出去，否则 DINO 的「无法判断」会被吃成连续。
- 前端跑不动 ViT；产品路径只能走分析隧道。
- 没有折线的历史训练集不能假装有分层 GT。
