# Next Agent 工作台开发流（Mac ↔ 工作站）

> 原则：**代码与数据在工作站改/跑；Mac 只做轻量文档与 HTML 阅片包。**  
> 不要把整个 `GastricTstaging` 拷到 Mac。

## 为什么在工作站改

| 因素 | 工作站 | Mac 整仓复制 |
|------|--------|--------------|
| `dataset/` + 视频 | `/data` 约 9T，项目主盘 | 本地只有部分 static_images |
| SAM / Agent / GPU | 已在跑 `:8767` / `:3000` | 需再搭一套，易漂 |
| 内存与批处理 | 大内存 + 双 4090 | 不适合作全库分析 |
| 实验互不干扰 | 用独立 git 分支 | 双真相源最易乱 |

## 推荐操作

1. Cursor：**Remote-SSH → `ws` / `hyj-z790-d`**  
   打开文件夹：`/data/research/gastric/GastricTstaging`
2. 分支：`feat/next-agent-workbench`（Next + `pipeline/agent`）  
   实验/训练仍可留在原分支或别的 worktree，**勿把 experiments 大树塞进 Next 提交**
3. 医生入口：`http://10.13.199.162:3000/`  
   三件套：`bash scripts/run_lan_merged_system.sh status`
4. 重算力任务：`CUDA_VISIBLE_DEVICES=1`（或空闲卡），避免冲掉 SAM（默认 GPU0）
5. Mac 仓 `gastric-ultrasound-reader`：只维护 HTML 阅片包 / 公网部署；成熟模块再 vendor 进 Next（已有 `public/vendor/human-assist/`）

## 已有分析资产（接入 Next 的原料）

- GradCAM / 面板：`pipeline/agent/visualization/gradcam.py` 等
- 壁层剖面：`artifacts/results/wall_layer_profiles/`
- 穿透分析：`artifacts/results/wall_penetration_analysis/`
- 旧医生 GradCAM：`pipeline/experiments_legacy_*/doctor_gradcam_validation`
- 前端雷达/概念：`apps/gastric_scan_next/components/RadarChart.tsx`、`ExplainableAnalysis.tsx`

下一刀：在 Reader/Agent 面板挂「壁层剖面 / GradCAM / 长轴接触」只读卡片，读上述产物路径，不重训。

## 提交纪律

- Next/Agent 改完 → **立刻 commit 到本分支**（可先不 push）
- 禁止提交：`clinical_data*.json`、`keyframe_tmp/`、`store_data/`、权重、密钥
- 训练 run 只更新 `experiments/registry.csv` + 小报告，不整树 commit
