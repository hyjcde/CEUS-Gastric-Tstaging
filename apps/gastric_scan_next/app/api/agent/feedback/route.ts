import { spawn } from 'child_process';
import { NextRequest, NextResponse } from 'next/server';
import { PROJECT_ROOT } from '@/lib/config';
import { buildPythonAgentEnv } from '@/lib/agent-python-env';
import { proxyAgentRequest } from '@/lib/agent-upstream';

const PYTHON_BIN = process.env.PYTHON_BIN || 'python';
const APPLY_FEEDBACK_SCRIPT = `${PROJECT_ROOT}/pipeline/agent/product/apply_feedback.py`;

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

function runPythonFeedback(payload: unknown): Promise<string> {
  return new Promise((resolve, reject) => {
    const child = spawn(PYTHON_BIN, [APPLY_FEEDBACK_SCRIPT, '--stdin'], {
      cwd: PROJECT_ROOT,
      env: buildPythonAgentEnv(),
      stdio: ['pipe', 'pipe', 'pipe'],
    });

    const stdoutChunks: Buffer[] = [];
    const stderrChunks: Buffer[] = [];
    const timer = setTimeout(() => {
      child.kill('SIGTERM');
      reject(new Error('Feedback apply timed out'));
    }, 60000);

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
        reject(new Error(stderr || `apply_feedback exited with code ${code}`));
        return;
      }
      resolve(stdout);
    });

    child.stdin.write(JSON.stringify(payload));
    child.stdin.end();
  });
}

interface FeedbackRequestBody {
  patient_id: string;
  case_id?: string;
  session_id?: string;
  memory_store?: string;
  memory_store_path?: string;
  action?: 'accept' | 'reject' | 'defer';
  record_id?: string;
  predicted_t_stage?: string;
  recommended_t_stage?: string;
  final_t_stage?: string;
  gold_t_stage?: string;
  feedback_type?: 'doctor_correction' | 'pathology_result' | 'quality_review';
  review_action?: 'accept' | 'modify' | 'reject' | 'request_more_evidence';
  correction_text?: string;
  error_type?: string;
  quality_flags?: string[];
  accepted_evidence?: string[];
  rejected_evidence?: string[];
  confidence?: string;
  reviewer?: string;
}

export async function POST(request: NextRequest) {
  const forwarded = await proxyAgentRequest(request);
  if (forwarded) return forwarded;

  try {
    const body = await request.json() as FeedbackRequestBody;
    if (!body.patient_id) {
      return NextResponse.json({ error: 'Missing patient_id' }, { status: 400 });
    }
    if (!body.action && !body.final_t_stage && !body.gold_t_stage) {
      return NextResponse.json(
        { error: 'Provide action+record_id or final_t_stage/gold_t_stage for correction feedback' },
        { status: 400 },
      );
    }

    const stdout = await runPythonFeedback(body);
    const parsed = JSON.parse(stdout);
    return NextResponse.json(parsed);
  } catch (error) {
    console.error('Agent feedback route failed', error);
    return NextResponse.json(
      { error: error instanceof Error ? error.message : 'Feedback apply failed' },
      { status: 500 },
    );
  }
}
