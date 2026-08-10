# 平台（Apps）

七类资产中的 **平台** 层，详见 [../REPO_LAYOUT.md](../REPO_LAYOUT.md) §6。

内部归位：[INTERNAL_LAYOUT.md](INTERNAL_LAYOUT.md) · 开发笔记（已从 app 目录迁出）：[../docs/apps/gastric_scan_next/](../docs/apps/gastric_scan_next/)

当前仓库把两个 React/Next 应用统一放在 `apps/` 下：

- `apps/direction_annotator`：Next + Electron 的突破方向标注工具
- `apps/gastric_scan_next`：Next 全栈病例浏览与分期工作站

## Shared Data Roots

默认情况下，这两个应用都会自动向上查找当前仓库根目录，并优先复用以下现有目录：

- `dataset/`
- `data/`
- `configs/`
- `pipeline/`
- `scripts/`

如果自动识别失败，可以显式设置环境变量：

```bash
export GASTRIC_ROOT=/data/research/gastric/GastricTstaging
export GASTRIC_DATASET_ROOT=/data/research/gastric/GastricTstaging/dataset
```

## Run `direction_annotator`

```bash
cd /data/research/gastric/GastricTstaging/apps/direction_annotator
npm install
npm run dev:web
```

Web 模式默认使用 `3099` 端口。Electron 开发模式可用：

```bash
npm run dev
```

标注批次文件正式路径：`data/annotation/batches/direction_annotation_batch.json`（`_compat/` 下保留旧名 symlink）。若缺失，应用会提示先选择正确的数据根或先生成批次文件。

## Run `gastric_scan_next`

```bash
cd /data/research/gastric/GastricTstaging/apps/gastric_scan_next
npm install
npm run dev
```

默认端口是 `3000`。当前实现会直接读取本仓库的：

- `dataset/internal/prospective_2025/2025`
- `dataset/internal/training_2018_2024/2024`
- `apps/gastric_scan_next/data/clinical_data*.json`（版本见 [data/metadata/clinical_json_versions.csv](../data/metadata/clinical_json_versions.csv)）

Agent API 契约：[docs/mainline/agent_api_contract.md](../docs/mainline/agent_api_contract.md)。

需要在工作站 GPU 上同时启用 SAM2 LAN 推理时，使用：

```bash
bash scripts/dev_all.sh
```

该入口启动 Next `0.0.0.0:3000` 和 SAM2 `0.0.0.0:8767`。可设置 `SAM_AUTOSTART=0` 只启动 Next。

### Workstation boot services

On the GPU workstation, install the user-level systemd services once:

```bash
bash scripts/install_gastric_user_services.sh
```

This enables the canonical Next production workstation on `:3000`, keeps the existing SAM2 service on `:8767`, adds the SAM3.1 service on `127.0.0.1:8768`, and starts the official nnInteractive server plus bridge on `127.0.0.1:1527` and `127.0.0.1:8770`. User lingering is enabled so the services can start before an interactive shell is opened.

Status and logs:

```bash
systemctl --user status gastric-workstation.target gastric-sam-agent.service gastric-sam31.service gastric-next.service
journalctl --user -u gastric-sam31.service -f
```

The public edge worker on `:3300` is also managed by the workstation target and is the same standalone build as the canonical `:3000` worker. The reverse tunnel exposes only the public edge and keeps SAM2, SAM3.1, and nnInteractive on local upstreams.

`gist` 相关 legacy 数据如果本机仍保留旧目录，可继续通过环境变量显式指定。
