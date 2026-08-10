import { spawn } from 'node:child_process';
import { NextRequest, NextResponse } from 'next/server';
import { PROJECT_ROOT } from '@/lib/config';
import { buildPythonAgentEnv } from '@/lib/agent-python-env';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';
export const maxDuration = 180;

type SegmentationRequest = {
  frame_png_b64?: string;
  model?: 'dinov3' | 'convnext' | 'sam31';
  threshold?: number;
  image_width?: number;
  image_height?: number;
  box?: { x1: number; y1: number; x2: number; y2: number } | null;
  clicks?: Array<{ x: number; y: number; label?: 'positive' | 'negative' | string }>;
};

const PYTHON_BIN = process.env.PYTHON_BIN || 'python3';

const PYTHON_SCRIPT = String.raw`
import base64
import cv2
import json
import os
import sys
import tempfile
import time
from pathlib import Path

import numpy as np


def decode_frame(value):
    raw = str(value or "")
    if "," in raw and raw.split(",", 1)[0].lower().startswith("data:"):
        raw = raw.split(",", 1)[1]
    image = cv2.imdecode(np.frombuffer(base64.b64decode(raw), dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError("Could not decode frame image")
    return image


def soft_box(box, width, height):
    if not isinstance(box, dict):
        return None
    x1 = int(np.clip(round(min(float(box.get("x1", 0)), float(box.get("x2", 0)))), 0, width - 1))
    x2 = int(np.clip(round(max(float(box.get("x1", 0)), float(box.get("x2", 0)))), 0, width - 1))
    y1 = int(np.clip(round(min(float(box.get("y1", 0)), float(box.get("y2", 0)))), 0, height - 1))
    y2 = int(np.clip(round(max(float(box.get("y1", 0)), float(box.get("y2", 0)))), 0, height - 1))
    ratio = min(max(float(os.getenv("DINO_BOX_PADDING_RATIO", "0.08")), 0.0), 0.25)
    pad_x = max(4, int(round((x2 - x1) * ratio)))
    pad_y = max(4, int(round((y2 - y1) * ratio)))
    return (
        max(0, x1 - pad_x),
        min(width - 1, x2 + pad_x),
        max(0, y1 - pad_y),
        min(height - 1, y2 + pad_y),
    )


def apply_prompt_gate(mask, box, clicks):
    height, width = mask.shape[:2]
    clipped = mask.astype(np.uint8)
    expanded = soft_box(box, width, height)
    if expanded is not None:
        x1, x2, y1, y2 = expanded
        gate = np.zeros_like(clipped)
        gate[y1 : y2 + 1, x1 : x2 + 1] = 1
        clipped = clipped & gate

    positive = [
        item for item in (clicks or [])
        if str(item.get("label", "positive")).lower() != "negative"
    ]
    negative = [
        item for item in (clicks or [])
        if str(item.get("label", "positive")).lower() == "negative"
    ]
    chosen = set()
    if positive and clipped.any():
        count, labels, stats, centroids = cv2.connectedComponentsWithStats(clipped, connectivity=8)
        ys, xs = np.where(clipped > 0)
        for point in positive:
            px = float(point.get("x", 0))
            py = float(point.get("y", 0))
            ix = int(np.clip(round(px), 0, width - 1))
            iy = int(np.clip(round(py), 0, height - 1))
            label = int(labels[iy, ix])
            if label == 0 and len(xs):
                nearest = int(np.argmin((xs - ix) ** 2 + (ys - iy) ** 2))
                label = int(labels[ys[nearest], xs[nearest]])
            if label > 0:
                chosen.add(label)
        if chosen:
            clipped = np.isin(labels, list(chosen)).astype(np.uint8)

    if negative:
        radius = max(5, int(round(min(width, height) * 0.025)))
        for point in negative:
            ix = int(np.clip(round(float(point.get("x", 0))), 0, width - 1))
            iy = int(np.clip(round(float(point.get("y", 0))), 0, height - 1))
            cv2.circle(clipped, (ix, iy), radius, 0, -1)
    if clipped.any():
        count, labels, stats, _ = cv2.connectedComponentsWithStats(clipped, connectivity=8)
        largest = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA])) if count > 1 else 1
        candidate_labels = chosen or {largest}
        largest_area = int(stats[largest, cv2.CC_STAT_AREA]) if count > 1 else int(clipped.sum())
        min_area = max(16, int(largest_area * 0.08))
        keep = {
            label for label in candidate_labels
            if 0 < label < count and int(stats[label, cv2.CC_STAT_AREA]) >= min_area
        }
        if not keep:
            keep = {largest}
        clipped = np.isin(labels, list(keep)).astype(np.uint8)
    return clipped.astype(bool)


def polygon_from_mask(mask):
    contours, _ = cv2.findContours((mask.astype(np.uint8) * 255), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    if not contours:
        return []
    contour = max(contours, key=cv2.contourArea).reshape(-1, 2)
    height, width = mask.shape[:2]
    if len(contour) > 2048:
        contour = cv2.approxPolyDP(contour.astype(np.float32), 0.5, True).reshape(-1, 2)
    return [[round(float(x) / width, 6), round(float(y) / height, 6)] for x, y in contour]


def overlay_data_url(image, mask, polygon):
    overlay = image.copy()
    if mask.any():
        color = np.zeros_like(overlay)
        color[:, :] = (80, 205, 105)
        alpha = 0.46
        active = mask > 0
        overlay[active] = (overlay[active] * (1.0 - alpha) + color[active] * alpha).astype(np.uint8)
    if len(polygon) >= 3:
        height, width = image.shape[:2]
        points = np.array([[round(x * width), round(y * height)] for x, y in polygon], dtype=np.int32)
        cv2.polylines(overlay, [points], True, (80, 245, 120), 2, cv2.LINE_AA)
    ok, encoded = cv2.imencode(".png", overlay)
    if not ok:
        return ""
    return "data:image/png;base64," + base64.b64encode(encoded.tobytes()).decode("ascii")


def main():
    started = time.time()
    request = json.load(sys.stdin)
    image = decode_frame(request.get("frame_png_b64"))
    height, width = image.shape[:2]
    model_name = str(request.get("model") or "dinov3").lower()
    threshold = float(request.get("threshold", 0.5))
    clicks = request.get("clicks") if isinstance(request.get("clicks"), list) else []
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as handle:
        temp_path = Path(handle.name)
    try:
        cv2.imwrite(str(temp_path), image)
        if model_name == "convnext":
            from agent.tools.segmentation_tool import SegmentationTool
            tool = SegmentationTool()
            backend_id = "ConvNeXt-Base UNet / segmentation_fulldata"
        else:
            from agent.tools.dinov3_segmentation_tool import DINOv3SegmentationTool
            tool = DINOv3SegmentationTool()
            backend_id = "DINOv3 ViT-B/16 lesion segmentation candidate"
        result = tool.execute(str(temp_path), threshold=threshold)
        mask = tool.get_cached_mask(str(temp_path))
        if mask is None:
            mask = np.zeros((height, width), dtype=np.uint8)
        binary = apply_prompt_gate(mask > 127, request.get("box"), clicks)
        polygon = polygon_from_mask(binary)
        foreground = int(binary.sum())
        response = {
            "ok": True,
            "available": bool(result.get("available")),
            "mask_available": bool(polygon),
            "model": model_name,
            "backend_id": result.get("backend_id") or backend_id,
            "roi_source": result.get("roi_source") or "model_prediction",
            "roi_bbox": result.get("roi_bbox"),
            "lesion_area_ratio": round(foreground / max(height * width, 1), 6),
            "image_width": width,
            "image_height": height,
            "mask_polygon": polygon,
            "mask_overlay_png": overlay_data_url(image, binary, polygon),
            "validation_summary": result.get("validation_summary"),
            "prompt": {"box": request.get("box"), "click_count": len(clicks)},
            "elapsed_ms": int((time.time() - started) * 1000),
            "error": result.get("error"),
        }
        print(json.dumps(response, ensure_ascii=False))
    finally:
        temp_path.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
`;

function runPython(payload: SegmentationRequest): Promise<{ code: number; stdout: string; stderr: string }> {
  return new Promise((resolve) => {
    const child = spawn(PYTHON_BIN, ['-c', PYTHON_SCRIPT], {
      cwd: PROJECT_ROOT,
      env: buildPythonAgentEnv(),
      stdio: ['pipe', 'pipe', 'pipe'],
    });
    const stdout: Buffer[] = [];
    const stderr: Buffer[] = [];
    child.stdout.on('data', (chunk) => stdout.push(Buffer.from(chunk)));
    child.stderr.on('data', (chunk) => stderr.push(Buffer.from(chunk)));
    child.on('close', (code) => resolve({
      code: code ?? 1,
      stdout: Buffer.concat(stdout).toString('utf-8'),
      stderr: Buffer.concat(stderr).toString('utf-8'),
    }));
    child.stdin.write(JSON.stringify(payload));
    child.stdin.end();
  });
}

export async function POST(request: NextRequest) {
  try {
    const body = await request.json() as SegmentationRequest;
    if (!body.frame_png_b64) {
      return NextResponse.json({ ok: false, error: 'frame_png_b64 is required' }, { status: 400 });
    }
    if (body.model === 'sam31') {
      const upstream = String(process.env.SAM31_UPSTREAM || 'http://127.0.0.1:8768').replace(/\/+$/, '');
      try {
        const response = await fetch(`${upstream}/api/sam31/static-segment`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body),
          cache: 'no-store',
          signal: AbortSignal.timeout(180_000),
        });
        const text = await response.text();
        let payload: unknown;
        try {
          payload = JSON.parse(text);
        } catch {
          payload = { ok: false, error: text.slice(0, 500) };
        }
        if (payload && typeof payload === 'object' && !Array.isArray(payload)) {
          const enriched = payload as Record<string, unknown>;
          if (!enriched.backend_id) {
            enriched.backend_id = 'sam31_gastric_lora_full_components_5epoch_run2';
          }
          if (!enriched.trust_label) {
            enriched.trust_label = 'caution';
          }
          enriched.agent_primary_remains = 'lesion_segmentation_unet_fulldata_convnext_base';
          payload = enriched;
        }
        return NextResponse.json(payload, { status: response.ok ? 200 : 502 });
      } catch (error) {
        return NextResponse.json(
          {
            ok: false,
            available: false,
            error: error instanceof Error ? error.message : 'SAM3.1 static backend unavailable',
            hint: 'Start with: bash apps/gastric_scan_next/scripts/dev_all.sh',
          },
          { status: 503 },
        );
      }
    }
    const result = await runPython(body);
    if (result.code !== 0) {
      return NextResponse.json({ ok: false, error: result.stderr || `segmentation process exit ${result.code}` }, { status: 500 });
    }
    const parsed = JSON.parse(result.stdout.trim().split('\n').pop() || '{}') as Record<string, unknown>;
    return NextResponse.json(parsed);
  } catch (error) {
    return NextResponse.json(
      { ok: false, error: error instanceof Error ? error.message : 'lesion segmentation failed' },
      { status: 500 },
    );
  }
}
