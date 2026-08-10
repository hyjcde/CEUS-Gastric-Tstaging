import crypto from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import { spawn } from 'node:child_process';
import { NextRequest, NextResponse } from 'next/server';
import { PROJECT_ROOT } from '@/lib/config';
import { proxyAgentRequest } from '@/lib/agent-upstream';
import { buildPythonAgentEnv } from '@/lib/agent-python-env';
import type { GcUsReportState } from '@/lib/gc-us-report-template';
import {
  READER_ROUND2_AGENT_VERSION,
  READER_ROUND2_FREEZE_ID,
  READER_ROUND2_MANIFEST_VERSION,
  READER_ROUND2_MODEL_VERSION,
  READER_ROUND2_PROMPT_VERSION,
  READER_ROUND2_RULE_VERSION,
  READER_ROUND2_SOFTWARE_VERSION,
} from '@/lib/reader/study-contract';
import { assertResearchCaseAccess } from '@/lib/reader/research-gate';

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
  authenticated_reader_id?: string;
  session_id?: string;
  round?: string;
  condition?: string;
  study_mode?: string;
  environment?: string;
  freeze_id?: string;
  software_version?: string;
  agent_version?: string;
  model_version?: string;
  rule_version?: string;
  prompt_version?: string;
  manifest_version?: string;
  frame_id?: string | null;
  frame_time?: number | null;
  frame_png_b64?: string;
  frames?: ReaderFrameInput[];
  clinical?: Record<string, unknown>;
  report_text?: Record<string, unknown>;
  gc_us_report?: GcUsReportState;
  mask_override?: Record<string, unknown>;
  lumen_override?: Record<string, unknown>;
  use_lumen_override?: boolean;
  contour_context?: Record<string, unknown>;
  workflow_trace?: Array<Record<string, unknown>>;
  /** contour_anchored_fast skips DINO/RAG/binary + remote LLM for Assist latency */
  assist_profile?: string;
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

function runPython(
  payload: Record<string, unknown>,
  envOverrides: Record<string, string> = {},
): Promise<Record<string, unknown>> {
  return new Promise((resolve, reject) => {
    const child = spawn(PYTHON_BIN, [ANALYZE_SCRIPT], {
      cwd: PROJECT_ROOT,
      env: {
        ...buildPythonAgentEnv(),
        AGENT_STREAM_EVENTS: '0',
        PYTHONPATH: `${PROJECT_ROOT}/pipeline:${PROJECT_ROOT}/scripts${process.env.PYTHONPATH ? `:${process.env.PYTHONPATH}` : ''}`,
        ...envOverrides,
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

function validPolygon(value: unknown): boolean {
  return Array.isArray(value)
    && value.length >= 3
    && value.every((point) => (
      Array.isArray(point)
      && point.length >= 2
      && Number.isFinite(Number(point[0]))
      && Number.isFinite(Number(point[1]))
    ));
}

function validBox(value: unknown): boolean {
  if (!value || typeof value !== 'object') return false;
  const box = value as Record<string, unknown>;
  const x1 = Number(box.x1);
  const y1 = Number(box.y1);
  const x2 = Number(box.x2);
  const y2 = Number(box.y2);
  return [x1, y1, x2, y2].every(Number.isFinite) && x2 > x1 && y2 > y1;
}

export async function POST(request: NextRequest) {
  let body: ReaderAgentRequest;
  try {
    body = await request.clone().json() as ReaderAgentRequest;
  } catch {
    return NextResponse.json({ ok: false, error: 'Invalid JSON request' }, { status: 400 });
  }
  const environment = body.environment || (body.round === 'qa' ? 'qa' : 'staging');
  let researchVersions = {
    freeze_id: body.freeze_id || READER_ROUND2_FREEZE_ID,
    software_version: body.software_version || READER_ROUND2_SOFTWARE_VERSION,
    agent_version: body.agent_version || READER_ROUND2_AGENT_VERSION,
    model_version: body.model_version || READER_ROUND2_MODEL_VERSION,
    rule_version: body.rule_version || READER_ROUND2_RULE_VERSION,
    prompt_version: body.prompt_version || READER_ROUND2_PROMPT_VERSION,
    manifest_version: body.manifest_version || READER_ROUND2_MANIFEST_VERSION,
  };
  if (environment === 'research') {
    if (!body.case_id) {
      return NextResponse.json({ ok: false, error: 'case_id is required' }, { status: 400 });
    }
    const access = await assertResearchCaseAccess({
      headers: request.headers,
      requestedReaderId: body.reader_id,
      caseId: body.case_id,
      round: body.round,
      versions: {
        freeze_id: body.freeze_id,
        software_version: body.software_version,
        agent_version: body.agent_version,
        model_version: body.model_version,
        rule_version: body.rule_version,
        prompt_version: body.prompt_version,
        manifest_version: body.manifest_version,
      },
      requireInitialJudgment: true,
      sessionId: body.session_id,
    });
    if (!access.ok) {
      return NextResponse.json(
        { ok: false, error: access.message, code: access.code },
        { status: access.status },
      );
    }
    if (body.authenticated_reader_id && body.authenticated_reader_id !== access.readerId) {
      return NextResponse.json(
        { ok: false, error: 'authenticated_reader_id does not match the trusted proxy identity' },
        { status: 403 },
      );
    }
    body.reader_id = access.readerId;
    body.authenticated_reader_id = access.readerId;
    researchVersions = access.versions;
  }
  if (!validPolygon(body.mask_override?.mask_polygon)) {
    return NextResponse.json(
      { ok: false, error: 'Agent requires a confirmed lesion segmentation polygon', code: 'geometry_gate' },
      { status: 422 },
    );
  }
  if (!validPolygon(body.lumen_override?.lumen_polygon) && !validBox(body.lumen_override?.lumen_bbox)) {
    return NextResponse.json(
      { ok: false, error: 'Agent requires a confirmed lumen polygon or bounding box', code: 'geometry_gate' },
      { status: 422 },
    );
  }
  const forwarded = await proxyAgentRequest(request);
  if (forwarded) return forwarded;
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
  ].filter((frame) => Boolean(frame.frame_png_b64));
  const assistProfile = String(body.assist_profile || '').trim().toLowerCase();
  const contourFast = ['contour_anchored_fast', 'assist_fast', 'fast'].includes(assistProfile);
  // Assist fast path: only the primary/current frame; full profile keeps up to MAX_FRAMES.
  const selectedFrames = (contourFast ? incoming.slice(0, 1) : incoming).slice(0, MAX_FRAMES);
  if (!selectedFrames.length) {
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
    const frames = selectedFrames.map((frame, index) => {
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
    const lumenPresent = Boolean(body.lumen_override);
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
      workflow_trace: Array.isArray(body.workflow_trace) ? body.workflow_trace.slice(-160) : [],
      use_mask_override: Boolean(body.mask_override),
      mask_override: body.mask_override,
      use_lumen_override: Boolean((body.use_lumen_override ?? true) && lumenPresent),
      lumen_override: body.lumen_override,
      assist_profile: assistProfile || undefined,
      contour_context: body.contour_context && typeof body.contour_context === 'object'
        ? body.contour_context
        : undefined,
      reader_context: {
        case_id: body.case_id,
        reader_id: body.reader_id || 'unknown_reader',
        authenticated_reader_id: body.authenticated_reader_id || null,
        round: body.round || 'round2',
        condition: body.condition || 'ai_assisted',
        study_mode: body.study_mode || 'unknown',
        environment,
        ...researchVersions,
        bridge: 'reader_v150_to_unified_agent_v1',
        assist_profile: assistProfile || null,
        frame_input_dir: inputDir,
        frame_input_retention_hours: 24,
        workflow_trace_count: Array.isArray(body.workflow_trace) ? body.workflow_trace.length : 0,
      },
    };
    const envOverrides: Record<string, string> = {};
    // Contour Assist: full per-step remote LLM (DeepSeek-V4-Flash) when ASSIST_KEEP_LLM=1;
    // otherwise one final synthesis only. Set ASSIST_LLM_MODE=heuristic to disable remote.
    if (contourFast) {
      const assistMode = process.env.ASSIST_LLM_MODE
        || (process.env.ASSIST_KEEP_LLM === '1' ? 'deepseek' : 'assist_deepseek');
      envOverrides.AGENT_LLM_MODE = assistMode;
      envOverrides.DEEPSEEK_MODEL = process.env.DEEPSEEK_MODEL
        || process.env.AGENT_LLM_MODEL
        || process.env.ASSIST_LLM_MODEL
        || 'deepseek-v4-flash';
      envOverrides.AGENT_LLM_MODEL = envOverrides.DEEPSEEK_MODEL;
      if (process.env.DEEPSEEK_BASE_URL || process.env.ASSIST_LLM_BASE_URL) {
        envOverrides.DEEPSEEK_BASE_URL = process.env.ASSIST_LLM_BASE_URL
          || process.env.DEEPSEEK_BASE_URL
          || 'https://api.deepseek.com';
        envOverrides.AGENT_LLM_BASE_URL = envOverrides.DEEPSEEK_BASE_URL;
      }
    }
    const result = await runPython(payload, envOverrides);
    return NextResponse.json({
      ok: true,
      bridge_schema_version: 'reader_unified_agent_bridge_v1',
      run_id: runId,
      case_id: body.case_id,
      assist_profile: assistProfile || null,
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
