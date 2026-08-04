import crypto from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import { spawn } from 'node:child_process';
import { NextRequest, NextResponse } from 'next/server';
import { PROJECT_ROOT } from '@/lib/config';
import type { GcUsReportState } from '@/lib/gc-us-report-template';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

const PYTHON_BIN = process.env.PYTHON_BIN || 'python';
const ANALYZE_SCRIPT = path.join(PROJECT_ROOT, 'pipeline', 'agent', 'product', 'analyze_case.py');
const INPUT_ROOT = path.join(PROJECT_ROOT, 'tmp', 'reader_agent_inputs');
const MAX_FRAMES = 8;
const MAX_FRAME_BYTES = 8 * 1024 * 1024;
const INPUT_RETENTION_MS = 24 * 60 * 60 * 1000;

type ReaderFrameInput = {
  frame_png_b64?: string;
  frame_id?: string | null;
  frame_index?: number;
  timestamp_sec?: number | null;
  quality_score?: number | null;
};

type ReaderAgentRequest = {
  case_id: string;
  patient_id?: string;
  reader_id?: string;
  round?: string;
  study_mode?: string;
  frame_id?: string | null;
  frame_time?: number | null;
  frame_png_b64?: string;
  frames?: ReaderFrameInput[];
  clinical?: Record<string, unknown>;
  report_text?: Record<string, unknown>;
  gc_us_report?: GcUsReportState;
  mask_override?: Record<string, unknown>;
};

function safeSegment(value: string, fallback: string): string {
  const safe = value.replace(/[^A-Za-z0-9_-]+/g, '_').slice(0, 100);
  return safe || fallback;
}
function decodeFrame(value: string): Buffer {
  const raw = value.replace(/^data:image\/[^;]+;base64,/, '');
  const buffer = Buffer.from(raw, 'base64');
  if (!buffer.length || buffer.length > MAX_FRAME_BYTES) {
    throw new Error('reader frame payload is empty or too large');
  }
  return buffer;
}

function scheduleInputCleanup(inputDir: string) {
  const timer = setTimeout(() => {
    try {
      fs.rmSync(inputDir, { recursive: true, force: true });
    } catch {
      // Best-effort retention cleanup.
    }
  }, INPUT_RETENTION_MS);
  timer.unref?.();
}

function runPython(payload: Record<string, unknown>): Promise<Record<string, unknown>> {
  return new Promise((resolve, reject) => {
    const child = spawn(PYTHON_BIN, [ANALYZE_SCRIPT], {
      cwd: PROJECT_ROOT,
      env: {
        ...process.env,
        AGENT_STREAM_EVENTS: '0',
        PYTHONPATH: `${PROJECT_ROOT}/pipeline:${PROJECT_ROOT}/scripts${process.env.PYTHONPATH ? `:${process.env.PYTHONPATH}` : ''}`,
      },
      stdio: ['pipe', 'pipe', 'pipe'],
    });
    const stdout: Buffer[] = [];
    const stderr: Buffer[] = [];
    const timer = setTimeout(() => {
      child.kill('SIGTERM');
      reject(new Error('reader Agent analysis timed out'));
    }, 600_000);
    child.stdout.on('data', (chunk) => stdout.push(Buffer.from(chunk)));
    child.stderr.on('data', (chunk) => stderr.push(Buffer.from(chunk)));
    child.on('error', (error) => {
      clearTimeout(timer);
      reject(error);
    });
    child.on('close', (code) => {
      clearTimeout(timer);
      const out = Buffer.concat(stdout).toString('utf8').trim();
      if (code !== 0) {
        reject(new Error(Buffer.concat(stderr).toString('utf8').trim() || `Agent exited with code ${code}`));
        return;
      }
      try {
        resolve(JSON.parse(out) as Record<string, unknown>);
      } catch {
        reject(new Error(`Agent returned invalid JSON: ${out.slice(-500)}`));
      }
    });
    child.stdin.end(JSON.stringify(payload));
  });
}

export async function POST(request: NextRequest) {
  let body: ReaderAgentRequest;
  try {
    body = await request.json() as ReaderAgentRequest;
  } catch {
    return NextResponse.json({ ok: false, error: 'Invalid JSON request' }, { status: 400 });
  }
  if (!body.case_id) {
    return NextResponse.json({ ok: false, error: 'case_id is required' }, { status: 400 });
  }

  const incoming = [
    ...(body.frames || []),
    ...(body.frame_png_b64 ? [{
      frame_png_b64: body.frame_png_b64,
      frame_id: body.frame_id,
      frame_index: 0,
      timestamp_sec: body.frame_time,
      quality_score: 1,
    }] : []),
  ].filter((frame) => Boolean(frame.frame_png_b64)).slice(0, MAX_FRAMES);
  if (!incoming.length) {
    return NextResponse.json({ ok: false, error: 'At least one frame is required' }, { status: 400 });
  }

  const runId = `reader_${Date.now()}_${crypto.randomBytes(4).toString('hex')}`;
  const inputDir = path.join(
    INPUT_ROOT,
    safeSegment(body.case_id, 'case'),
    runId,
  );
  fs.mkdirSync(inputDir, { recursive: true });
  try {
    const frames = incoming.map((frame, index) => {
      const imagePath = path.join(inputDir, `frame_${String(index).padStart(2, '0')}.jpg`);
      fs.writeFileSync(imagePath, decodeFrame(String(frame.frame_png_b64)));
      return {
        image_path: imagePath,
        frame_id: frame.frame_id || `reader_frame_${index}`,
        frame_index: Number(frame.frame_index ?? index),
        timestamp_sec: frame.timestamp_sec == null ? null : Number(frame.timestamp_sec),
        quality_score: frame.quality_score == null ? 1 : Number(frame.quality_score),
      };
    });
    const payload = {
      session_id: runId,
      case_token: `reader_v150:${body.case_id}`,
      patient_id: body.patient_id || body.case_id,
      data_source: 'reader_study_v150',
      cohort_year: 'reader_v150',
      treatment_type: 'surgery',
      input_mode: 'frontend',
      frame_count: frames.length,
      max_frames: frames.length,
      frames,
      image_path: frames[0].image_path,
      clinical: body.clinical || {},
      report_text: body.report_text || {},
      gc_us_report: body.gc_us_report,
      use_mask_override: Boolean(body.mask_override),
      mask_override: body.mask_override,
      reader_context: {
        case_id: body.case_id,
        reader_id: body.reader_id || 'unknown_reader',
        round: body.round || 'round2',
        study_mode: body.study_mode || 'unknown',
        bridge: 'reader_v150_to_unified_agent_v1',
        frame_input_dir: inputDir,
        frame_input_retention_hours: 24,
      },
    };
    const result = await runPython(payload);
    return NextResponse.json({
      ok: true,
      bridge_schema_version: 'reader_unified_agent_bridge_v1',
      run_id: runId,
      case_id: body.case_id,
      result,
    });
  } catch (error) {
    return NextResponse.json({
      ok: false,
      run_id: runId,
      error: error instanceof Error ? error.message : 'Reader Agent analysis failed',
    }, { status: 500 });
  } finally {
    scheduleInputCleanup(inputDir);
  }
}
