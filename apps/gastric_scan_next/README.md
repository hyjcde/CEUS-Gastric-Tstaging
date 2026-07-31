# MM-GCS: Multimodal Gastric Cancer Staging System

Research-grade workstation for gastric cancer T-staging using Multimodal Ultrasound and Concept Bottleneck Models.

## Features

- **Dark Mode Workstation UI**: Optimized for radiology reading rooms.
- **Real-time Data Integration**: Reads directly from the current repository `dataset/` tree, with optional legacy dataset fallbacks.
- **Concept Reasoning**: Interactive sliders to perform counterfactual analysis on pathological features (Serosa, Stiffness, etc.).
- **Interactive segmentation / boundary edit**: Case viewer launcher **边界编辑** — polygon vertex edit, optional SAM click (proxied to `:8767`), **video follow** (scrub + SAM track-on-play), persist overrides under `data/mask_overrides.json`, and feed them into Agent analyze as mask/ROI overrides.
- **VLM Reporting**: Simulated multimodal AI report generation.
- **Multimodal Viewer**: Support for switching between Original B-Mode, Segmentation Overlay, and XAI Heatmap.

## Tech Stack

- **Framework**: Next.js 15 (App Router)
- **Styling**: Tailwind CSS v4
- **Icons**: Lucide React
- **Backend**: Next.js API Routes (Node.js fs module)

## Setup & Run

1. Install dependencies:
   ```bash
   npm install
   ```

2. Run development server:
   ```bash
   npm run dev
   ```

3. Open [http://localhost:3000](http://localhost:3000)

### LAN full stack (auth + SAM + Next)

```bash
bash scripts/run_lan_merged_system.sh start
bash scripts/test_lan_full_stack.sh   # automated acceptance
```

- Workbench: `http://<LAN_IP>:3000/`（推荐医生书签；左上 **辅助中心** 聚合入口，顶栏原按钮保留）
- **In-app Reader Agent**: `http://<LAN_IP>:3000/reader` (SAM + 分层 + 文字报告，融合 HTML 阅片能力)
- Reader HTML fallback: `http://<LAN_IP>:8767/interactive_video_agent.html`
- Human-assist HTML: `http://<LAN_IP>:8767/direction_demo.html`（深链带 callback 可回写工作台）
- DeepSeek status: `http://<LAN_IP>:8766/api/llm/status`
- Requirements checklist: `docs/mainline/PRODUCT_REQUIREMENTS_CHECKLIST.md`（U1–U3）

In **边界编辑**, switch to **视频跟随** to scrub video, enable **播放时 SAM 跟随**, then save overrides (stores `video_time_sec`).

### Interactive boundary edit → Agent analyze

1. Select a case, click **边界编辑** (bottom-left of the viewer).
2. Move / add / delete polygon vertices, or use **SAM click** if the SAM server is running:
   `python3 scripts/serve_interactive_sam_agent.py --port 8767`
3. **保存覆盖** → stored in `apps/gastric_scan_next/data/mask_overrides.json`.
4. Run Agent analyze — the launcher notes when an override is active; `LesionSegAgent` uses the edited mask (`roi_source=doctor_override`) and classification uses the edited ROI bbox (or disk doctor ROI when ROI mode = doctor).

If the app cannot auto-detect the repository root, set:

```bash
export GASTRIC_ROOT=/data/research/gastric/GastricTstaging
export GASTRIC_DATASET_ROOT=/data/research/gastric/GastricTstaging/dataset
```

## Directory Structure

- `/app/api`: Backend API routes to read the dataset.
- `/components`: UI Components (PatientList, Viewer, Reasoning, etc.).
- `/lib`: Configuration and helpers.
