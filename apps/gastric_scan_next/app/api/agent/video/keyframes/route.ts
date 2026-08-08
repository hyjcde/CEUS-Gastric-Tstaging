import fs from 'fs';
import path from 'path';
import { spawn } from 'child_process';
import { NextRequest, NextResponse } from 'next/server';
import { PROJECT_ROOT } from '@/lib/config';
import { buildPythonAgentEnv } from '@/lib/agent-python-env';
import { resolvePlayableVideoPath } from '@/lib/video-stream';
import { proxyAgentRequest } from '@/lib/agent-upstream';
import { legacyAppDataFile, runtimeDataFile } from '@/lib/runtime-data';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

const PYTHON_BIN = process.env.PYTHON_BIN || 'python3';

function resolveVideoPath(videoUrl: string): string | null {
  return resolvePlayableVideoPath(videoUrl);
}

function runPython(script: string, args: string[]): Promise<{ code: number; stdout: string; stderr: string }> {
  return new Promise((resolve) => {
    const child = spawn(PYTHON_BIN, ['-c', script, ...args], {
      cwd: PROJECT_ROOT,
      env: buildPythonAgentEnv(),
      stdio: ['ignore', 'pipe', 'pipe'],
    });
    const out: Buffer[] = [];
    const err: Buffer[] = [];
    child.stdout.on('data', (c) => out.push(Buffer.from(c)));
    child.stderr.on('data', (c) => err.push(Buffer.from(c)));
    child.on('close', (code) => {
      resolve({
        code: code ?? 1,
        stdout: Buffer.concat(out).toString('utf-8'),
        stderr: Buffer.concat(err).toString('utf-8'),
      });
    });
  });
}

const KEYFRAME_SCRIPT = `
import cv2, json, sys, math
from pathlib import Path

sys.path.insert(0, str(Path.cwd() / 'scripts'))
from agent.pipeline.keyframe_selection import select_visual_keyframes

video_path = sys.argv[1]
anchor = float(sys.argv[2])
window = float(sys.argv[3])
top_k = int(sys.argv[4])
out_dir = Path(sys.argv[5])
out_dir.mkdir(parents=True, exist_ok=True)

cap = cv2.VideoCapture(video_path)
if not cap.isOpened():
    print(json.dumps({"ok": False, "error": "cannot open video"}))
    raise SystemExit(0)

fps = float(cap.get(cv2.CAP_PROP_FPS) or 25.0)
nframes = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
duration = nframes / fps if fps > 0 else 0.0
t0 = max(0.0, anchor - window)
t1 = min(duration, anchor + window) if duration > 0 else anchor + window
# sample ~12 candidates in window
sample_n = max(top_k * 3, 12)
times = []
if t1 <= t0:
    times = [anchor]
else:
    step = (t1 - t0) / max(sample_n - 1, 1)
    times = [t0 + i * step for i in range(sample_n)]

candidates = []
prev_gray = None
for t in times:
    frame_idx = int(round(t * fps))
    cap.set(cv2.CAP_PROP_POS_FRAMES, max(frame_idx, 0))
    ok, frame = cap.read()
    if not ok or frame is None:
        continue
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    sharp = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    contrast = float(gray.std())
    brightness = float(gray.mean())
    brightness_bal = 1.0 - min(abs(brightness - 110.0) / 110.0, 1.0)
    motion = 0.0
    if prev_gray is not None:
        motion = float(cv2.absdiff(gray, prev_gray).mean())
    prev_gray = gray
    dist = abs(t - anchor)
    dist_pen = 1.0 / (1.0 + dist)
    sharp_n = min(sharp / 400.0, 1.0)
    contrast_n = min(contrast / 60.0, 1.0)
    motion_n = min(motion / 35.0, 1.0)
    score = 0.40 * sharp_n + 0.25 * contrast_n + 0.15 * brightness_bal + 0.10 * motion_n + 0.10 * dist_pen
    reasons = []
    if sharp_n > 0.55: reasons.append("sharp")
    if contrast_n > 0.45: reasons.append("contrast")
    if brightness_bal > 0.55: reasons.append("exposure_ok")
    if dist < 0.35: reasons.append("near_anchor")
    if not reasons: reasons.append("usable")
    thumb = out_dir / f"kf_{frame_idx:06d}.jpg"
    cv2.imwrite(str(thumb), frame, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
    candidates.append({
        "timestamp_sec": round(float(t), 3),
        "frame_index": int(frame_idx),
        "score": round(float(score), 4),
        "sharpness": round(sharp, 2),
        "contrast": round(contrast, 2),
        "motion": round(motion, 2),
        "reasons": reasons,
        "thumb_path": str(thumb),
    })

cap.release()
top = select_visual_keyframes(
    candidates,
    n_key=top_k,
    min_gap=max(2, int(round(max(fps, 25.0) * 0.5))),
)
for item in top:
    item["score"] = item.get("quality_score", item.get("score", 0.0))
print(json.dumps({
    "ok": True,
    "fps": fps,
    "duration_sec": round(duration, 3),
    "anchor_sec": anchor,
    "window_sec": window,
    "candidate_count": len(candidates),
    "keyframes": top,
}, ensure_ascii=False))
`;

/**
 * B8: neighborhood AI keyframe candidates around an anchor time.
 * POST { video_url, anchor_sec, window_sec?, top_k? }
 */
export async function POST(request: NextRequest) {
  const forwarded = await proxyAgentRequest(request);
  if (forwarded) return forwarded;

  try {
    const body = await request.json();
    const videoUrl = String(body.video_url || body.videoUrl || '');
    const anchor = Number(body.anchor_sec ?? body.anchorSec ?? 0);
    const windowSec = Number(body.window_sec ?? body.windowSec ?? 2.0);
    const topK = Math.min(Math.max(Number(body.top_k ?? body.topK ?? 5), 1), 12);

    const videoPath = resolveVideoPath(videoUrl);
    if (!videoPath) {
      return NextResponse.json({ ok: false, error: 'video not found', video_url: videoUrl }, { status: 404 });
    }

    const outDir = path.join(runtimeDataFile('keyframe_tmp'), `job_${Date.now()}`);
    fs.mkdirSync(outDir, { recursive: true });

    const { code, stdout, stderr } = await runPython(KEYFRAME_SCRIPT, [
      videoPath,
      String(anchor),
      String(windowSec),
      String(topK),
      outDir,
    ]);

    if (code !== 0) {
      return NextResponse.json({ ok: false, error: stderr || `python exit ${code}` }, { status: 500 });
    }

    let parsed: {
      ok?: boolean;
      error?: string;
      keyframes?: Array<Record<string, unknown>>;
      [k: string]: unknown;
    };
    try {
      parsed = JSON.parse(stdout.trim().split('\n').pop() || '{}');
    } catch {
      return NextResponse.json({ ok: false, error: 'invalid python json', raw: stdout.slice(0, 500) }, { status: 500 });
    }

    if (!parsed.ok) {
      return NextResponse.json(parsed, { status: 422 });
    }

    const keyframes = (parsed.keyframes || []).map((kf) => {
      const thumbPath = String(kf.thumb_path || '');
      const resolvedThumbPath = path.resolve(thumbPath);
      const allowedRoots = [
        path.resolve(runtimeDataFile('keyframe_tmp')),
        path.resolve(legacyAppDataFile('keyframe_tmp')),
      ];
      const isAllowedThumb = allowedRoots.some((root) => {
        const relative = path.relative(root, resolvedThumbPath);
        return relative && relative !== '..' && !relative.startsWith(`..${path.sep}`) && !path.isAbsolute(relative);
      });
      const rel = isAllowedThumb
        ? `/api/patients/keyframes/file?path=${encodeURIComponent(thumbPath)}`
        : '';
      return {
        ...kf,
        thumb_url: rel,
      };
    });

    return NextResponse.json({
      requirement_id: 'B8',
      ok: true,
      video_path: videoPath,
      ...parsed,
      keyframes,
    });
  } catch (error) {
    return NextResponse.json(
      { ok: false, error: error instanceof Error ? error.message : 'keyframe failed' },
      { status: 500 },
    );
  }
}
