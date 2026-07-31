import { spawn } from 'child_process';
import { NextRequest, NextResponse } from 'next/server';
import {
  resolvePatientAgentPaths,
  resolvePatientFramePaths,
  mapClinicalToAgentInput,
  mapReportToAgentInput,
} from '@/lib/agent-server';
import { DatasetType, CohortYear, TreatmentType, PROJECT_ROOT } from '@/lib/config';
import { Patient } from '@/types';
import { buildPythonAgentEnv } from '@/lib/agent-python-env';
const PYTHON_BIN = process.env.PYTHON_BIN || 'python';
const ANALYZE_SCRIPT = `${PROJECT_ROOT}/pipeline/agent/product/analyze_case.py`;

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

function runPythonAgent(payload: unknown): Promise<string> {
  return new Promise((resolve, reject) => {
    const child = spawn(PYTHON_BIN, [ANALYZE_SCRIPT], {
      cwd: PROJECT_ROOT,
      env: buildPythonAgentEnv(),
      stdio: ['pipe', 'pipe', 'pipe'],
    });

    const stdoutChunks: Buffer[] = [];
    const stderrChunks: Buffer[] = [];
    const timer = setTimeout(() => {
      child.kill('SIGTERM');
      reject(new Error('Agent analysis timed out'));
    }, 300000);

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
      if (stderr.trim()) {
        console.warn(stderr);
      }
      if (code !== 0) {
        reject(new Error(stderr || `Python agent exited with code ${code}`));
        return;
      }
      resolve(stdout);
    });

    child.stdin.write(JSON.stringify(payload));
    child.stdin.end();
  });
}

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
}

export async function POST(request: NextRequest) {
  try {
    const body = await request.json() as AnalyzeRequestBody;
    const {
      patient, dataset, cohortYear, treatmentType, sessionId, memory_enabled, memory_store,
      use_mask_override, mask_override, roi_mode,
    } = body;

    if (!patient) {
      return NextResponse.json({ error: 'Missing patient payload' }, { status: 400 });
    }

    const resolvedPaths = resolvePatientAgentPaths(patient, cohortYear, treatmentType, dataset);
    if (!resolvedPaths.image_path) {
      return NextResponse.json({ error: 'Could not resolve patient image path' }, { status: 400 });
    }

    const frames = resolvePatientFramePaths(patient, cohortYear, treatmentType, dataset, 3);
    const payload = {
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
      ...resolvedPaths,
    };

    const stdout = await runPythonAgent(payload);
    const parsed = JSON.parse(stdout);
    return NextResponse.json(parsed);
  } catch (error) {
    console.error('Agent analyze route failed', error);
    return NextResponse.json(
      { error: error instanceof Error ? error.message : 'Agent analysis failed' },
      { status: 500 },
    );
  }
}
