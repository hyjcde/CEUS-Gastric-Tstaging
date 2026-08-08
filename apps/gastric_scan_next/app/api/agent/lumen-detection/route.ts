import { spawn } from 'node:child_process';
import { NextRequest, NextResponse } from 'next/server';
import { PROJECT_ROOT } from '@/lib/config';
import { buildPythonAgentEnv } from '@/lib/agent-python-env';
import { proxyAgentRequest } from '@/lib/agent-upstream';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';
export const maxDuration = 120;

type LumenDetectionRequest = {
  frame_png_b64?: string;
  conf?: number;
  imgsz?: number;
  image_width?: number;
  image_height?: number;
};

const PYTHON_BIN = process.env.PYTHON_BIN || 'python3';

const PYTHON_SCRIPT = String.raw`
import base64
import json
import sys
import tempfile
import time
from pathlib import Path

import cv2
import numpy as np


def decode_frame(value):
    raw = str(value or "")
    if "," in raw and raw.split(",", 1)[0].lower().startswith("data:"):
        raw = raw.split(",", 1)[1]
    image = cv2.imdecode(np.frombuffer(base64.b64decode(raw), dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError("Could not decode frame image")
    return image


def main():
    started = time.time()
    request = json.load(sys.stdin)
    image = decode_frame(request.get("frame_png_b64"))
    height, width = image.shape[:2]
    conf = request.get("conf")
    imgsz = request.get("imgsz")
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as handle:
        temp_path = Path(handle.name)
    try:
        cv2.imwrite(str(temp_path), image)
        from agent.tools.lumen_detection_tool import LumenDetectionTool

        tool = LumenDetectionTool()
        kwargs = {"image_path": str(temp_path)}
        if conf is not None:
            kwargs["conf"] = float(conf)
        if imgsz is not None:
            kwargs["imgsz"] = int(imgsz)
        result = tool.execute(**kwargs)
        response = {
            "ok": True,
            "available": bool(result.get("available")),
            "lumen_detected": bool(result.get("lumen_detected")),
            "lumen_bbox": result.get("lumen_bbox"),
            "lumen_mask_type": result.get("lumen_mask_type") or "bbox_proxy",
            "lumen_confidence": result.get("lumen_confidence"),
            "lumen_area_ratio": result.get("lumen_area_ratio"),
            "lumen_geometry": result.get("lumen_geometry"),
            "roi_source": result.get("roi_source"),
            "image_width": int(result.get("image_width") or width),
            "image_height": int(result.get("image_height") or height),
            "backend_id": "yolo_lumen_locator_cropui_combined_plus_zip2_20260417",
            "runtime_invocation": result.get("runtime_invocation"),
            "error": result.get("error"),
            "elapsed_ms": int((time.time() - started) * 1000),
        }
        print(json.dumps(response, ensure_ascii=False))
    finally:
        temp_path.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
`;

function runPython(payload: LumenDetectionRequest): Promise<{ code: number; stdout: string; stderr: string }> {
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
  const forwarded = await proxyAgentRequest(request);
  if (forwarded) return forwarded;

  try {
    const body = await request.json() as LumenDetectionRequest;
    if (!body.frame_png_b64) {
      return NextResponse.json({ ok: false, error: 'frame_png_b64 is required' }, { status: 400 });
    }
    const result = await runPython(body);
    if (result.code !== 0) {
      return NextResponse.json(
        { ok: false, available: false, error: result.stderr || `lumen detection process exit ${result.code}` },
        { status: 500 },
      );
    }
    const parsed = JSON.parse(result.stdout.trim().split('\n').pop() || '{}') as Record<string, unknown>;
    return NextResponse.json(parsed);
  } catch (error) {
    return NextResponse.json(
      { ok: false, available: false, error: error instanceof Error ? error.message : 'lumen detection failed' },
      { status: 500 },
    );
  }
}
