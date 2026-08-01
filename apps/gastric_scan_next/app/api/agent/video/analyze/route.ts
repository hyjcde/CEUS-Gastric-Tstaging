import { spawn } from 'child_process';
import crypto from 'crypto';
import fs from 'fs';
import path from 'path';
import { NextRequest, NextResponse } from 'next/server';
import { PROJECT_ROOT } from '@/lib/config';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

const PYTHON_BIN = process.env.PYTHON_BIN || 'python';
const ANALYZE_SCRIPT = path.join(PROJECT_ROOT, 'pipeline', 'agent', 'product', 'analyze_case.py');
const UPLOAD_ROOT = path.join(PROJECT_ROOT, 'tmp', 'video_agent_uploads');
const MAX_FRAMES = 5;

type ExtractedFrame = {
  image_path: string;
  frame_index: number;
  timestamp_sec: number;
  quality_score: number;
  sharpness: number;
  brightness: number;
  motion_score: number;
  contrast: number;
};

type ExtractedVideo = {
  frameCount: number;
  fps: number;
  durationSec: number;
  frames: ExtractedFrame[];
  candidateCount: number;
  selectionMethod: string;
};

type StageProbabilities = Record<string, number>;

type RuntimeInvocation = {
  component?: string;
  called?: boolean;
  status?: string;
  forward_pass?: boolean;
  api_kind?: string;
  checkpoint?: string;
  error?: string;
  skip_reason?: string;
};

type RuntimeVerificationPayload = {
  all_core_models_called?: boolean;
  integrity_status?: 'verified' | 'degraded' | 'failed' | string;
  required_components?: string[];
  failed_required_components?: string[];
  degraded_components?: string[];
  proxy_visual_notes?: string[];
  invocations?: RuntimeInvocation[];
};

function safeFileStem(filename: string) {
  return path
    .basename(filename, path.extname(filename))
    .replace(/[^\w.-]+/g, '_')
    .slice(0, 80) || 'uploaded_video';
}

function runProcess(command: string, args: string[], options: { cwd?: string; env?: NodeJS.ProcessEnv; input?: string; timeoutMs?: number } = {}) {
  return new Promise<{ stdout: string; stderr: string }>((resolve, reject) => {
    const child = spawn(command, args, {
      cwd: options.cwd,
      env: options.env,
      stdio: ['pipe', 'pipe', 'pipe'],
    });

    const stdoutChunks: Buffer[] = [];
    const stderrChunks: Buffer[] = [];
    const timer = windowlessTimeout(() => {
      child.kill('SIGTERM');
      reject(new Error(`${path.basename(command)} timed out`));
    }, options.timeoutMs ?? 300000);

    child.stdout.on('data', (chunk) => stdoutChunks.push(Buffer.from(chunk)));
    child.stderr.on('data', (chunk) => stderrChunks.push(Buffer.from(chunk)));
    child.on('error', (error) => {
      clearTimeout(timer);
      reject(error);
    });
    child.on('close', (code) => {
      clearTimeout(timer);
      const stdout = Buffer.concat(stdoutChunks).toString('utf-8');
      const stderr = Buffer.concat(stderrChunks).toString('utf-8');
      if (code !== 0) {
        reject(new Error(stderr || stdout || `${path.basename(command)} exited with code ${code}`));
        return;
      }
      resolve({ stdout, stderr });
    });

    if (options.input) child.stdin.write(options.input);
    child.stdin.end();
  });
}

function windowlessTimeout(callback: () => void, ms: number) {
  return setTimeout(callback, ms);
}

async function extractVideoFrames(videoPath: string, outputDir: string, maxFrames: number): Promise<ExtractedVideo> {
  const script = `
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path.cwd() / 'scripts'))
from agent.pipeline.keyframe_selection import select_visual_keyframes

import cv2
import numpy as np

video_path = sys.argv[1]
output_dir = Path(sys.argv[2])
max_frames = int(sys.argv[3])
output_dir.mkdir(parents=True, exist_ok=True)

cap = cv2.VideoCapture(video_path)
if not cap.isOpened():
    raise SystemExit("Could not open uploaded video")

frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
duration_sec = float(frame_count / fps) if fps > 0 and frame_count > 0 else 0.0

if frame_count > 0:
    sample_count = min(max(max_frames * 4, 12), frame_count)
    positions = sorted(set(int(round((frame_count - 1) * (i + 0.5) / sample_count)) for i in range(sample_count)))
else:
    positions = [i * 30 for i in range(max(max_frames * 4, 12))]

def score_frame(frame, prev_gray):
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    sharpness = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    brightness = float(gray.mean())
    contrast = float(gray.std())
    if prev_gray is None:
        motion_score = 0.0
    else:
        motion_score = float(cv2.absdiff(gray, prev_gray).mean())

    return {
        "gray": gray,
        "sharpness": sharpness,
        "brightness": brightness,
        "contrast": contrast,
        "motion_score": motion_score,
    }

candidates = []
prev_gray = None
for index, pos in enumerate(positions):
    cap.set(cv2.CAP_PROP_POS_FRAMES, max(pos, 0))
    ok, frame = cap.read()
    if not ok or frame is None:
        continue
    metrics = score_frame(frame, prev_gray)
    prev_gray = metrics["gray"]
    candidates.append({
        "frame": frame,
        "frame_index": int(pos),
        "timestamp_sec": float(pos / fps) if fps > 0 else 0.0,
        "sharpness": metrics["sharpness"],
        "brightness": metrics["brightness"],
        "contrast": metrics["contrast"],
        "motion_score": metrics["motion_score"],
    })

if not candidates:
    cap.release()
    print(json.dumps({"frame_count": frame_count, "fps": fps, "duration_sec": duration_sec, "frames": [], "candidate_count": 0}, ensure_ascii=False))
    raise SystemExit(0)

selected = select_visual_keyframes(
    candidates,
    n_key=max_frames,
    min_gap=max(2, int(round(max(fps, 25.0) * 0.5))),
)

frames = []
for index, item in enumerate(selected):
    out_path = output_dir / f"frame_{index + 1:02d}.jpg"
    cv2.imwrite(str(out_path), item["frame"])
    frames.append({
        "image_path": str(out_path),
        "frame_index": item["frame_index"],
        "timestamp_sec": round(item["timestamp_sec"], 3),
        "quality_score": round(item["quality_score"], 4),
        "sharpness": round(item["sharpness"], 2),
        "brightness": round(item["brightness"], 2),
        "motion_score": round(item["motion_score"], 2),
    })

cap.release()
print(json.dumps({
    "frame_count": frame_count,
    "fps": fps,
    "duration_sec": duration_sec,
    "frames": frames,
    "candidate_count": len(candidates),
    "selection_method": "visual_quality_temporal_diverse_topk_v1",
}, ensure_ascii=False))
`;

  const { stdout } = await runProcess(PYTHON_BIN, ['-c', script, videoPath, outputDir, String(maxFrames)], {
    cwd: PROJECT_ROOT,
    env: {
      ...process.env,
      PYTHONPATH: `${PROJECT_ROOT}/pipeline:${PROJECT_ROOT}/scripts${process.env.PYTHONPATH ? `:${process.env.PYTHONPATH}` : ''}`,
    },
    timeoutMs: 300000,
  });

  const parsed = JSON.parse(stdout.trim() || '{}') as {
    frame_count?: number;
    fps?: number;
    duration_sec?: number;
    frames?: ExtractedFrame[];
    candidate_count?: number;
    selection_method?: string;
  };
  return {
    frameCount: parsed.frame_count ?? 0,
    fps: parsed.fps ?? 0,
    durationSec: parsed.duration_sec ?? 0,
    frames: parsed.frames ?? [],
    candidateCount: parsed.candidate_count ?? 0,
    selectionMethod: parsed.selection_method ?? 'quality_motion_topk_temporal_order',
  };
}

async function runAgent(payload: Record<string, unknown>) {
  const { stdout, stderr } = await runProcess(PYTHON_BIN, [ANALYZE_SCRIPT], {
    cwd: PROJECT_ROOT,
    env: {
      ...process.env,
      GASTRIC_ROOT: PROJECT_ROOT,
      PYTHONPATH: `${PROJECT_ROOT}/pipeline:${PROJECT_ROOT}/scripts${process.env.PYTHONPATH ? `:${process.env.PYTHONPATH}` : ''}`,
    },
    input: JSON.stringify(payload),
    timeoutMs: 600000,
  });

  if (stderr.trim()) {
    console.warn(stderr);
  }
  return JSON.parse(stdout);
}

function summarizeVideoIntelligence(result: unknown, extracted: ExtractedVideo) {
  const typed = result as {
    tool_evidence?: {
      classification?: {
        probabilities?: StageProbabilities;
        top1_stage?: string;
        top1_prob?: number;
        top2_stage?: string;
        top2_prob?: number;
        uncertainty?: number;
        frame_aggregation?: string;
        aggregated_frame_count?: number;
      };
    };
    report?: {
      rag_gate?: {
        rag_weight?: number;
        rag_gate_reason?: string;
      };
      similar_case_summary?: {
        majority_stage?: string;
      };
      uncertainty_flags?: string[];
      conflicting_evidence?: string[];
    };
    similar_cases?: unknown[];
    runtime_verification?: RuntimeVerificationPayload;
  };
  const classification = typed.tool_evidence?.classification;
  const top1 = Number(classification?.top1_prob ?? 0);
  const top2 = Number(classification?.top2_prob ?? 0);
  const margin = Math.max(top1 - top2, 0);
  const temporalConsistency = margin >= 0.25
    ? 'stable'
    : margin >= 0.12
      ? 'borderline'
      : 'unstable';

  return {
    mode: 'video_multiframe_agent_rag_dino',
    selected_frame_count: extracted.frames.length,
    candidate_frame_count: extracted.candidateCount,
    selection_method: extracted.selectionMethod,
    duration_sec: Math.round(extracted.durationSec * 10) / 10,
    fps: Math.round(extracted.fps * 10) / 10,
    temporal_consistency: temporalConsistency,
    classifier_margin: Math.round(margin * 1000) / 1000,
    aggregation: classification?.frame_aggregation ?? 'single_frame',
    aggregated_frame_count: classification?.aggregated_frame_count ?? extracted.frames.length,
    rag_weight: typed.report?.rag_gate?.rag_weight ?? 0,
    rag_reason: typed.report?.rag_gate?.rag_gate_reason ?? 'unknown',
    similar_case_count: typed.similar_cases?.length ?? 0,
    similar_case_majority: typed.report?.similar_case_summary?.majority_stage ?? 'unknown',
    review_priority: temporalConsistency === 'unstable' || (typed.report?.conflicting_evidence?.length ?? 0) > 0
      ? 'high'
      : temporalConsistency === 'borderline' || (typed.report?.uncertainty_flags?.length ?? 0) > 1
        ? 'medium'
        : 'standard',
    frame_quality: extracted.frames.map((frame) => ({
      frame_index: frame.frame_index,
      timestamp_sec: frame.timestamp_sec,
      quality_score: frame.quality_score,
      sharpness: frame.sharpness,
      motion_score: frame.motion_score,
    })),
  };
}

function buildSystemIntegrity(result: unknown, extracted: ExtractedVideo) {
  const typed = result as { runtime_verification?: RuntimeVerificationPayload };
  const verification = typed.runtime_verification;
  const invocations = verification?.invocations ?? [];
  const required = verification?.required_components ?? [
    'nextjs_stream_route',
    'segmentation',
    'classification',
    'dino_feature_panel',
  ];
  const failedRequired = verification?.failed_required_components
    ?? required.filter((component) => !invocations.some((item) => item.component === component && item.called));
  const proxyNotes = verification?.proxy_visual_notes ?? [];
  const degraded = verification?.degraded_components
    ?? invocations
      .filter((item) => item.called && item.status && !['ok', 'completed'].includes(item.status))
      .map((item) => String(item.component));
  const status = verification?.integrity_status
    ?? (failedRequired.length > 0 ? 'failed' : proxyNotes.length > 0 || degraded.length > 0 ? 'degraded' : 'verified');

  return {
    status,
    not_mock: failedRequired.length === 0,
    source_endpoint: '/api/agent/video/analyze',
    analyzer_script: 'pipeline/agent/product/analyze_case.py',
    required_components: required,
    failed_required_components: failedRequired,
    degraded_components: degraded,
    proxy_visual_notes: proxyNotes,
    selected_frame_count: extracted.frames.length,
    candidate_frame_count: extracted.candidateCount,
    components: invocations.map((item) => ({
      component: item.component,
      called: Boolean(item.called),
      status: item.status ?? 'unknown',
      forward_pass: Boolean(item.forward_pass),
      api_kind: item.api_kind,
      checkpoint: item.checkpoint,
      error: item.error,
      skip_reason: item.skip_reason,
    })),
  };
}

export async function POST(request: NextRequest) {
  try {
    const formData = await request.formData();
    const file = formData.get('video');
    if (!(file instanceof File)) {
      return NextResponse.json({ error: 'Missing video file' }, { status: 400 });
    }

    const extension = path.extname(file.name || '').toLowerCase() || '.mp4';
    if (!['.mp4', '.mov', '.avi', '.mkv', '.webm', '.mpeg', '.mpg'].includes(extension)) {
      return NextResponse.json({ error: 'Unsupported video format' }, { status: 400 });
    }

    const uploadId = crypto.randomUUID();
    const fileStem = safeFileStem(file.name || uploadId);
    const uploadDir = path.join(UPLOAD_ROOT, uploadId);
    const frameDir = path.join(uploadDir, 'frames');
    fs.mkdirSync(uploadDir, { recursive: true });

    const videoPath = path.join(uploadDir, `${fileStem}${extension}`);
    const buffer = Buffer.from(await file.arrayBuffer());
    fs.writeFileSync(videoPath, buffer);

    const extracted = await extractVideoFrames(videoPath, frameDir, MAX_FRAMES);
    if (!extracted.frames.length) {
      return NextResponse.json({ error: 'No readable frames extracted from uploaded video' }, { status: 422 });
    }

    const patientId = String(formData.get('patientId') || `upload_${uploadId.slice(0, 8)}`);
    const notes = String(formData.get('notes') || '');
    const sessionId = String(formData.get('sessionId') || `video_${uploadId}`);
    const primaryFrame = extracted.frames.reduce((best, frame) => (
      frame.quality_score > best.quality_score ? frame : best
    ), extracted.frames[0]);
    const payload = {
      session_id: sessionId,
      source_endpoint: '/api/agent/video/analyze',
      patient_id: patientId,
      case_token: fileStem,
      cohort_year: 'uploaded_video',
      treatment_type: 'video',
      dataset: 'uploaded',
      data_source: 'uploaded_video',
      video_path: videoPath,
      uploaded_filename: file.name,
      frame_count: extracted.frames.length,
      original_video_frame_count: extracted.frameCount,
      video_fps: extracted.fps,
      video_duration_sec: extracted.durationSec,
      video_frame_selection: {
        method: extracted.selectionMethod,
        candidate_count: extracted.candidateCount,
        selected_frames: extracted.frames.map((frame) => ({
          frame_index: frame.frame_index,
          timestamp_sec: frame.timestamp_sec,
          quality_score: frame.quality_score,
        })),
      },
      max_frames: MAX_FRAMES,
      frames: extracted.frames.map((frame) => ({
        image_path: frame.image_path,
        frame_index: frame.frame_index,
        timestamp_sec: frame.timestamp_sec,
        quality_score: frame.quality_score,
        sharpness: frame.sharpness,
        brightness: frame.brightness,
        contrast: frame.contrast,
        motion_score: frame.motion_score,
      })),
      image_path: primaryFrame.image_path,
      clinical: {},
      report_text: {
        ultrasound_report: [
          notes,
          `Video upload summary: ${extracted.frames.length} quality-ranked frames selected from ${extracted.candidateCount} candidates; duration ${extracted.durationSec.toFixed(1)} sec; fps ${extracted.fps.toFixed(1)}.`,
        ].filter(Boolean).join('\n'),
        ultrasound_findings: notes,
        report_source: 'frontend_video_upload',
      },
      segmentation: {
        source: 'uploaded_video',
        has_annotation: false,
        has_overlay: false,
        has_roi: false,
        annotation_count: 0,
        frame_count: extracted.frames.length,
      },
    };

    const result = await runAgent(payload);
    const videoIntelligence = summarizeVideoIntelligence(result, extracted);
    const systemIntegrity = buildSystemIntegrity(result, extracted);
    return NextResponse.json({
      ...result,
      video_intelligence: videoIntelligence,
      system_integrity: systemIntegrity,
      upload: {
        upload_id: uploadId,
        filename: file.name,
        video_path: videoPath,
        extracted_frame_count: extracted.frames.length,
        original_video_frame_count: extracted.frameCount,
        duration_sec: extracted.durationSec,
        fps: extracted.fps,
        candidate_frame_count: extracted.candidateCount,
        selection_method: extracted.selectionMethod,
        frames: extracted.frames,
        frame_indices: extracted.frames.map((frame) => frame.frame_index),
      },
    });
  } catch (error) {
    console.error('Video agent analyze route failed', error);
    return NextResponse.json(
      { error: error instanceof Error ? error.message : 'Video analysis failed' },
      { status: 500 },
    );
  }
}
