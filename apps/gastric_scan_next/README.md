# MM-GCS: Multimodal Gastric Cancer Staging System

Research-grade workstation for gastric cancer T-staging using Multimodal Ultrasound and Concept Bottleneck Models.

## Features

- **Dark Mode Workstation UI**: Optimized for radiology reading rooms.
- **Real-time Data Integration**: Reads directly from the current repository `dataset/` tree, with optional legacy dataset fallbacks.
- **Concept Reasoning**: Interactive sliders to perform counterfactual analysis on pathological features (Serosa, Stiffness, etc.).
- **Interactive segmentation / boundary edit**: Case viewer launcher **边界编辑** — polygon vertex edit, optional SAM click (proxied to `:8767`), **video follow** (scrub + SAM track-on-play), persist overrides under `data/mask_overrides.json`, and feed them into Agent analyze as mask/ROI overrides.
- **nnInteractive refinement**: Optional official nnInteractive v1 remote inference can use the doctor-confirmed SAM mask as an initial mask, then refine the lesion with positive or negative clicks, freehand scribbles, or lassos.
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

- Workbench: `http://<LAN_IP>:3000/`（当前唯一医生入口；左上 **辅助中心** 聚合 Next 内部功能）
- **In-app Reader Agent**: `http://<LAN_IP>:3000/reader`（SAM + nnInteractive + 分层 + 文字报告）
- Direction annotation: `http://<LAN_IP>:3000/annotate`（已合并进 Next 工作台）
- DeepSeek status: `http://<LAN_IP>:8766/api/llm/status`
- Requirements checklist: `docs/mainline/PRODUCT_REQUIREMENTS_CHECKLIST.md`（U1–U3）

In **边界编辑**, switch to **视频跟随** to scrub video, enable **播放时 SAM 跟随**, then save overrides (stores `video_time_sec`).

### Optional nnInteractive refinement

The workbench keeps the official nnInteractive model outside the Next.js
process. The original prompt API is preserved: positive and negative points,
freehand scribbles, and closed lasso prompts are sent to nnInteractive. If the
server is unavailable, the workbench reports that state and does not silently
switch these prompts to SAM3.1.

1. On the GPU host, download the official source and install its dependencies.
   The repository checkout used by this workbench is `external/nnInteractive`:

   ```bash
   cd /data/research/gastric/GastricTstaging
   test -d external/nnInteractive || \
     git clone https://github.com/MIC-DKFZ/nnInteractive.git external/nnInteractive
   python3 -m venv --system-site-packages .venv-nninteractive
   .venv-nninteractive/bin/pip install --no-deps nnunetv2==2.7.0
   .venv-nninteractive/bin/pip install --no-deps -e external/nnInteractive
   .venv-nninteractive/bin/pip install --no-deps -e external/nnInteractive/client
   ```

2. Start the official server through the repository wrapper. The wrapper keeps
   the original nnInteractive server and interaction methods, while using a
   smaller startup patch for a 24 GiB workstation GPU:

   ```bash
   NNINTERACTIVE_PATCH_SIZE=128 \
     .venv-nninteractive/bin/python scripts/serve_nninteractive_server.py \
     --model nnInteractive_v1.0 --host 127.0.0.1 --port 1527 \
     --device cuda:0 --no-torch-compile
   ```

3. On the workstation running this app, install the lightweight remote client
   and start the bridge:

   ```bash
   export NN_INTERACTIVE_SERVER_URL=http://127.0.0.1:1527
   export NN_INTERACTIVE_API_KEY=<server-api-key>
   .venv-nninteractive/bin/python scripts/serve_nninteractive_agent.py \
     --host 127.0.0.1 --port 8770
   ```

4. Set `NNINTERACTIVE_UPSTREAM=http://127.0.0.1:8770` in the Next.js
   environment and restart Next.js.

In the video boundary editor, first generate a lesion mask, then choose
**nnInteractive**. The toolbar exposes positive point, negative point,
freehand scribble, and lasso prompts. The refined contour continues through
the existing save and Agent analysis paths. This integration is single-frame
refinement; video propagation remains on the existing SAM workflow.

#### Self-hosted GPU deployment

Yes. No official hosted service is required. The GPU inference server can run
on the same workstation or on a private GPU host, and the bridge can point to
that private address. The browser still needs an inference server process:
`nninteractive-client` is only a remote client and does not run the model by
itself.

Because the full package currently excludes some PyTorch versions used by the
SAM services, install it in a separate environment on the GPU host:

```bash
cd /data/research/gastric/GastricTstaging
python3 -m venv --system-site-packages .venv-nninteractive
.venv-nninteractive/bin/pip install --no-deps nnunetv2==2.7.0
.venv-nninteractive/bin/pip install --no-deps -e external/nnInteractive
.venv-nninteractive/bin/pip install --no-deps -e external/nnInteractive/client
export NN_INTERACTIVE_API_KEY="$(openssl rand -hex 32)"
.venv-nninteractive/bin/python scripts/serve_nninteractive_server.py \
  --model nnInteractive_v1.0 --host 0.0.0.0 --port 1527 \
  --api-key "$NN_INTERACTIVE_API_KEY"
```

Or use the official GPU container without installing the Python stack:

```bash
docker run --gpus all --rm -p 1527:1527 \
  -e NN_INTERACTIVE_API_KEY="$(openssl rand -hex 32)" \
  ghcr.io/mic-dkfz/nninteractive-server:latest
```

Then point the local bridge at that private server:

```bash
export NN_INTERACTIVE_SERVER_URL=http://<PRIVATE_GPU_HOST>:1527
export NN_INTERACTIVE_API_KEY=<optional-server-api-key>
.venv-nninteractive/bin/python scripts/serve_nninteractive_agent.py --host 127.0.0.1 --port 8770
```

Keep port `1527` restricted to the private network or an authenticated tunnel.
The model checkpoint is licensed CC BY-NC-SA 4.0, so confirm that the license
fits the intended research or clinical deployment.

The official model checkpoint is licensed CC BY-NC-SA 4.0. Confirm that its
non-commercial research terms fit the intended deployment before exposing the
feature beyond the research workstation.

### Scientific Agent workbench

The main workbench (`/`) is the canonical local entry for the unified research
Agent. `reader_v150` cases can send the current video window to the same
evidence pipeline used by the historical workbench; `/reader` remains a
compatibility route for the standalone Reader UI.

```bash
cd /data/research/gastric/GastricTstaging/apps/gastric_scan_next
export GASTRIC_ROOT=/data/research/gastric/GastricTstaging
export GASTRIC_PROJECT_ROOT=/data/research/gastric/GastricTstaging
export GASTRIC_DATASET_ROOT=/data/research/gastric/GastricTstaging/dataset
export PYTHON_BIN=/home/hyj/miniconda3/bin/python
export AGENT_ENABLE_DINO=1
npm run dev -- --webpack -H 0.0.0.0 -p 3000
```

Open `http://127.0.0.1:3000/`, select `Reader task · Round 1 · 150 cases`,
open the video evidence editor, and choose **Unified Agent**. The right
evidence panel should show the case belief state, frame provenance, DINO
shadow status, seven-sign/report state, conflicts, and the next active action.

### Public reader-only build

The public edge exposes only the `reader_v150` queue. Build it with:

```bash
NEXT_PUBLIC_READER_ONLY=1 NEXT_DIST_DIR=.next-aliyun npm run build
```

Agent/DINO/SAM requests are forwarded to the workstation through the
authenticated reverse tunnel; the public host does not need the model stack.

### Round2 research identity and case order

Formal Round2 traffic must use `environment=research`. The Next server does
not trust a URL or browser body `reader_id` for research events. The
authenticated reverse proxy must inject:

```text
x-authenticated-reader-id: Doctor_XX
x-authenticated-reader-signature: HMAC-SHA256(READER_AUTH_PROXY_SECRET, Doctor_XX)
```

Configure the same secret only in the server environment:

```bash
export READER_AUTH_PROXY_SECRET='<server-side-secret>'
```

For a signed reader ID, the proxy can compute the hexadecimal digest with:

```bash
printf '%s' "$READER_ID" | openssl dgst -sha256 -hmac "$READER_AUTH_PROXY_SECRET" -hex
```

Open the formal study queue with `?environment=research`. The server then
verifies the proxy identity, applies that reader's frozen Round2 order from
`data/registry/reader_round2_case_order_20260810.csv`, and writes the
authenticated ID plus freeze and version fields into every accepted audit
event. Local QA or staging runs must use `environment=qa` or
`environment=staging`; they are excluded from clinical analysis.

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
