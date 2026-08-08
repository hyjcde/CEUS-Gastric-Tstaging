import { NextRequest, NextResponse } from 'next/server';
import { spawn } from 'child_process';
import path from 'path';
import fs from 'fs';
import os from 'os';
import { DatasetType, CohortYear, TreatmentType, parseCohortYear, PROJECT_ROOT } from '@/lib/config';
import { getPatientDatasetPaths, resolvePatientAgentPaths } from '@/lib/agent-server';
import { Patient } from '@/types';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';
export const maxDuration = 180;

interface AnalyzeBody {
  patient?: Patient;
  dataset?: DatasetType;
  cohortYear?: CohortYear;
  treatmentType?: TreatmentType;
  /** Reader / current-frame mode: full-frame PNG base64 (no LabelMe on disk). */
  frame_png_b64?: string;
  mask_polygon?: number[][];
  image_width?: number;
  image_height?: number;
  lumen_polygon?: number[][];
  lumen_bbox?: { x1: number; y1: number; x2: number; y2: number };
  frame_time?: number;
  patient_id?: string;
  case_id?: string;
}

function decodePngBase64(value: string): Buffer {
  const raw = value.replace(/^data:image\/[^;]+;base64,/, '');
  const buffer = Buffer.from(raw, 'base64');
  if (!buffer.length) throw new Error('frame_png_b64 is empty');
  if (buffer.length > 40 * 1024 * 1024) throw new Error('frame_png_b64 is too large');
  return buffer;
}

function isValidPolygon(value: unknown): value is number[][] {
  if (!Array.isArray(value) || value.length < 3) return false;
  return value.every(
    (pt) => Array.isArray(pt)
      && pt.length >= 2
      && Number.isFinite(Number(pt[0]))
      && Number.isFinite(Number(pt[1])),
  );
}

function isValidLumenBBox(value: unknown): value is { x1: number; y1: number; x2: number; y2: number } {
  if (!value || typeof value !== 'object') return false;
  const box = value as Record<string, unknown>;
  const coords = ['x1', 'y1', 'x2', 'y2'].map((key) => Number(box[key]));
  return coords.every(Number.isFinite) && coords[2] > coords[0] && coords[3] > coords[1];
}

function runExplainableCli(
  imagePath: string,
  annotationPath: string,
  patientId: string,
  lumenPolygon?: number[][],
  lumenBBox?: { x1: number; y1: number; x2: number; y2: number },
): Promise<Record<string, unknown>> {
  const cliScript = path.join(process.cwd(), 'scripts/explainable_analyze_cli.py');
  const args = [cliScript, '--image', imagePath, '--annotation', annotationPath, '--patient-id', patientId];
  if (isValidPolygon(lumenPolygon)) {
    args.push('--lumen-polygon', JSON.stringify(lumenPolygon));
  }
  if (isValidLumenBBox(lumenBBox)) {
    args.push('--lumen-bbox', JSON.stringify(lumenBBox));
  }
  return new Promise((resolve, reject) => {
    const proc = spawn(
      'python3',
      args,
      {
        cwd: process.cwd(),
        env: {
          ...process.env,
          PYTHONPATH: `${PROJECT_ROOT}${process.env.PYTHONPATH ? `:${process.env.PYTHONPATH}` : ''}`,
        },
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

function writeTempFrameInputs(body: AnalyzeBody): { imagePath: string; annotationPath: string; cleanup: () => void } {
  if (!body.frame_png_b64) throw new Error('frame_png_b64 is required');
  if (!isValidPolygon(body.mask_polygon)) throw new Error('mask_polygon with at least 3 points is required');

  const png = decodePngBase64(body.frame_png_b64);
  const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), 'explainable-frame-'));
  const isJpeg = png.length >= 3 && png[0] === 0xff && png[1] === 0xd8;
  const imageName = isJpeg ? 'frame.jpg' : 'frame.png';
  const imagePath = path.join(tmpDir, imageName);
  const annotationPath = path.join(tmpDir, 'frame.json');
  fs.writeFileSync(imagePath, png);

  const width = Math.max(0, Math.round(Number(body.image_width) || 0));
  const height = Math.max(0, Math.round(Number(body.image_height) || 0));
  if (width < 8 || height < 8) {
    throw new Error('image_width and image_height are required for current-frame analysis');
  }
  const points = body.mask_polygon.map((pt) => [Number(pt[0]), Number(pt[1])]);
  const labelme = {
    version: '5.0.1',
    flags: {},
    shapes: [
      {
        label: 'lesion',
        points,
        group_id: null,
        shape_type: 'polygon',
        flags: {},
      },
    ],
    imagePath: imageName,
    imageData: null,
    imageHeight: height,
    imageWidth: width,
  };
  fs.writeFileSync(annotationPath, JSON.stringify(labelme));

  return {
    imagePath,
    annotationPath,
    cleanup: () => {
      try {
        fs.rmSync(tmpDir, { recursive: true, force: true });
      } catch {
        /* ignore */
      }
    },
  };
}

export async function POST(request: NextRequest) {
  let cleanup: (() => void) | null = null;
  try {
    const body = (await request.json()) as AnalyzeBody;
    const patientId = body.patient?.patient_id
      || body.patient?.id
      || body.patient_id
      || body.case_id
      || 'unknown';

    // Current-frame mode (reader video / workbench): no on-disk LabelMe required.
    if (body.frame_png_b64 && body.mask_polygon) {
      const temp = writeTempFrameInputs(body);
      cleanup = temp.cleanup;
      const result = await runExplainableCli(
        temp.imagePath,
        temp.annotationPath,
        patientId,
        body.lumen_polygon,
        body.lumen_bbox,
      );
      return NextResponse.json({
        ...result,
        analysis_mode: 'current_frame',
        frame_time: body.frame_time ?? null,
      });
    }

    const { patient, dataset = 'cropped', cohortYear = '2025', treatmentType = 'surgery' } = body;
    if (!patient) {
      return NextResponse.json({ success: false, error: 'patient is required (or provide frame_png_b64 + mask_polygon)' }, { status: 400 });
    }

    const cohort = parseCohortYear(cohortYear);
    const resolved = resolvePatientAgentPaths(patient, cohort, treatmentType, dataset);
    const originalPaths = getPatientDatasetPaths(patient, 'original', cohort, treatmentType);
    const imagePath = resolved.annotation_path && originalPaths.images
      ? (() => {
          const filename = path.basename(resolved.image_path || '');
          const originalImage = path.join(originalPaths.images, filename);
          return fs.existsSync(originalImage) ? originalImage : resolved.image_path;
        })()
      : resolved.image_path;
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
    return NextResponse.json({ ...result, analysis_mode: 'static_annotation' });
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Explainable analysis failed';
    return NextResponse.json({ success: false, error: message }, { status: 500 });
  } finally {
    cleanup?.();
  }
}
