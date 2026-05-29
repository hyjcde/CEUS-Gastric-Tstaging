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
}

function buildPayload(body: AnalyzeRequestBody) {
  const { patient, dataset, cohortYear, treatmentType, sessionId } = body;
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
    ...resolvedPaths,
  };
}

export async function POST(request: NextRequest) {
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
          env: {
            ...process.env,
            GASTRIC_ROOT: PROJECT_ROOT,
            PYTHONPATH: `${PROJECT_ROOT}/pipeline${process.env.PYTHONPATH ? `:${process.env.PYTHONPATH}` : ''}`,
            AGENT_STREAM_EVENTS: '1',
          },
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
