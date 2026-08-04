import { spawn } from 'child_process';
import { NextRequest } from 'next/server';
import {
  resolvePatientAgentPaths,
  resolvePatientFramePaths,
  mapClinicalToAgentInput,
  mapReportToAgentInput,
} from '@/lib/agent-server';
import { DatasetType, CohortYear, TreatmentType, PROJECT_ROOT } from '@/lib/config';
import { Patient } from '@/types';
import { buildPythonAgentEnv } from '@/lib/agent-python-env';
import type { GcUsReportState } from '@/lib/gc-us-report-template';
import { proxyAgentRequest } from '@/lib/agent-upstream';

const PYTHON_BIN = process.env.PYTHON_BIN || 'python';
const ANALYZE_SCRIPT = `${PROJECT_ROOT}/pipeline/agent/product/analyze_case.py`;

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

interface AnalyzeRequestBody {
  patient: Patient;
  dataset: DatasetType;
  cohortYear: CohortYear;
  treatmentType: TreatmentType;
  sessionId?: string;
  memory_enabled?: boolean;
  memory_store?: string;
  use_mask_override?: boolean;
  mask_override?: {
    mask_polygon?: number[][];
    roi_bbox?: { x1: number; y1: number; x2: number; y2: number };
    image_width?: number;
    image_height?: number;
    source?: string;
  };
  roi_mode?: 'predicted' | 'doctor' | 'auto';
  gc_us_report?: GcUsReportState;
}

function buildPayload(body: AnalyzeRequestBody) {
  const {
    patient, dataset, cohortYear, treatmentType, sessionId, memory_enabled, memory_store,
    use_mask_override, mask_override, roi_mode, gc_us_report,
  } = body;
  const resolvedPaths = resolvePatientAgentPaths(patient, cohortYear, treatmentType, dataset);
  if (!resolvedPaths.image_path) {
    throw new Error('Could not resolve patient image path');
  }

  const frames = resolvePatientFramePaths(patient, cohortYear, treatmentType, dataset, 3);

  return {
    session_id: sessionId,
    patient_id: patient.patient_id,
    case_token: patient.agent_report.case_token,
    cohort_year: cohortYear,
    treatment_type: treatmentType,
    dataset,
    data_source: patient.source_label || patient.agent_report.data_source,
    frame_count: frames.length || patient.frame_count,
    max_frames: 3,
    frames: frames.length > 0 ? frames : undefined,
    clinical: mapClinicalToAgentInput(patient),
    report_text: mapReportToAgentInput(patient),
    segmentation: patient.segmentation,
    memory_enabled: memory_enabled ?? process.env.AGENT_MEMORY_ENABLED === '1',
    memory_store: memory_store ?? process.env.AGENT_MEMORY_STORE,
    use_mask_override: Boolean(use_mask_override && mask_override),
    mask_override: use_mask_override ? mask_override : undefined,
    roi_mode: roi_mode || 'predicted',
    gc_us_report: gc_us_report || undefined,
    ...resolvedPaths,
  };
}

export async function POST(request: NextRequest) {
  const forwarded = await proxyAgentRequest(request);
  if (forwarded) return forwarded;

  const encoder = new TextEncoder();

  try {
    const body = await request.json() as AnalyzeRequestBody;
    if (!body.patient) {
      return new Response(
        encoder.encode(JSON.stringify({ event: 'error', error: 'Missing patient payload' }) + '\n'),
        { status: 400, headers: { 'Content-Type': 'application/x-ndjson; charset=utf-8' } },
      );
    }

    const payload = buildPayload(body);

    const stream = new ReadableStream<Uint8Array>({
      start(controller) {
        const child = spawn(PYTHON_BIN, [ANALYZE_SCRIPT], {
          cwd: PROJECT_ROOT,
          env: buildPythonAgentEnv({ AGENT_STREAM_EVENTS: '1' }),
          stdio: ['pipe', 'pipe', 'pipe'],
        });

        const timer = setTimeout(() => {
          child.kill('SIGTERM');
          controller.enqueue(encoder.encode(JSON.stringify({ event: 'error', error: 'Agent analysis timed out' }) + '\n'));
          controller.close();
        }, 600000);

        child.stdout.on('data', (chunk: Buffer) => {
          controller.enqueue(chunk);
        });

        child.stderr.on('data', (chunk: Buffer) => {
          const message = chunk.toString('utf-8').trim();
          if (message) {
            controller.enqueue(encoder.encode(JSON.stringify({ event: 'log', message }) + '\n'));
          }
        });

        child.on('error', (error) => {
          clearTimeout(timer);
          controller.enqueue(encoder.encode(JSON.stringify({ event: 'error', error: error.message }) + '\n'));
          controller.close();
        });

        child.on('close', (code) => {
          clearTimeout(timer);
          if (code !== 0) {
            controller.enqueue(encoder.encode(JSON.stringify({ event: 'error', error: `Python agent exited with code ${code}` }) + '\n'));
          }
          controller.close();
        });

        child.stdin.write(JSON.stringify(payload));
        child.stdin.end();
      },
    });

    return new Response(stream, {
      headers: {
        'Content-Type': 'application/x-ndjson; charset=utf-8',
        'Cache-Control': 'no-store',
      },
    });
  } catch (error) {
    return new Response(
      encoder.encode(JSON.stringify({ event: 'error', error: error instanceof Error ? error.message : 'Agent analysis failed' }) + '\n'),
      { status: 500, headers: { 'Content-Type': 'application/x-ndjson; charset=utf-8' } },
    );
  }
}
