import { NextRequest, NextResponse } from 'next/server';
import { spawn } from 'child_process';
import path from 'path';
import fs from 'fs';
import { DatasetType, CohortYear, TreatmentType, parseCohortYear, PROJECT_ROOT } from '@/lib/config';
import { resolvePatientAgentPaths } from '@/lib/agent-server';
import { Patient } from '@/types';

export const runtime = 'nodejs';

interface AnalyzeBody {
  patient: Patient;
  dataset?: DatasetType;
  cohortYear?: CohortYear;
  treatmentType?: TreatmentType;
}

function runExplainableCli(imagePath: string, annotationPath: string, patientId: string): Promise<Record<string, unknown>> {
  const cliScript = path.join(process.cwd(), 'scripts/explainable_analyze_cli.py');
  return new Promise((resolve, reject) => {
    const proc = spawn(
      'python3',
      [cliScript, '--image', imagePath, '--annotation', annotationPath, '--patient-id', patientId],
      {
        cwd: process.cwd(),
        env: { ...process.env, PYTHONPATH: PROJECT_ROOT },
      },
    );

    let stdout = '';
    let stderr = '';
    proc.stdout.on('data', (chunk) => { stdout += chunk.toString(); });
    proc.stderr.on('data', (chunk) => { stderr += chunk.toString(); });
    proc.on('close', (code) => {
      try {
        const parsed = JSON.parse(stdout.trim() || '{}');
        if (code === 0 && parsed.success) {
          resolve(parsed);
          return;
        }
        reject(new Error(parsed.error || stderr || `Explainable CLI exited with code ${code}`));
      } catch {
        reject(new Error(stderr || stdout || 'Failed to parse explainable CLI output'));
      }
    });
  });
}

export async function POST(request: NextRequest) {
  try {
    const body = (await request.json()) as AnalyzeBody;
    const { patient, dataset = 'cropped', cohortYear = '2025', treatmentType = 'surgery' } = body;
    if (!patient) {
      return NextResponse.json({ success: false, error: 'patient is required' }, { status: 400 });
    }

    const cohort = parseCohortYear(cohortYear);
    const resolved = resolvePatientAgentPaths(patient, cohort, treatmentType, dataset);
    const imagePath = resolved.image_path;
    const annotationPath = resolved.annotation_path;

    if (!imagePath || !fs.existsSync(imagePath)) {
      return NextResponse.json({ success: false, patient_id: patient.patient_id, error: 'Image path not resolved' }, { status: 404 });
    }
    if (!annotationPath || !fs.existsSync(annotationPath)) {
      return NextResponse.json({
        success: false,
        patient_id: patient.patient_id,
        error: 'Annotation JSON not found for this frame. LabelMe annotation is required for boundary analysis.',
      }, { status: 404 });
    }

    const result = await runExplainableCli(imagePath, annotationPath, patient.patient_id || patient.id);
    return NextResponse.json(result);
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Explainable analysis failed';
    return NextResponse.json({ success: false, error: message }, { status: 500 });
  }
}
