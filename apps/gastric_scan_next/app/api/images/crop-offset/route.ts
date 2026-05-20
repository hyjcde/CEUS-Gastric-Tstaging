import { NextRequest, NextResponse } from 'next/server';
import { spawn } from 'child_process';
import fs from 'fs';
import path from 'path';
import { getDatasetPaths, parseCohortYear, TreatmentType } from '@/lib/config';

export const runtime = 'nodejs';

const offsetCache = new Map<string, Record<string, unknown>>();

function runCropOffsetCli(originalPath: string, cropPath: string): Promise<Record<string, unknown>> {
  const cliScript = path.join(process.cwd(), 'scripts/compute_crop_offset.py');
  return new Promise((resolve, reject) => {
    const proc = spawn('python3', [cliScript, '--original', originalPath, '--crop', cropPath]);
    let stdout = '';
    let stderr = '';
    proc.stdout.on('data', (chunk) => { stdout += chunk.toString(); });
    proc.stderr.on('data', (chunk) => { stderr += chunk.toString(); });
    proc.on('close', (code) => {
      try {
        const parsed = JSON.parse(stdout.trim() || '{}');
        if (code === 0 && !parsed.error) {
          resolve(parsed);
          return;
        }
        reject(new Error(parsed.error || stderr || `crop offset CLI failed (${code})`));
      } catch {
        reject(new Error(stderr || stdout || 'Failed to parse crop offset output'));
      }
    });
  });
}

export async function GET(request: NextRequest) {
  const { searchParams } = new URL(request.url);
  const filename = searchParams.get('filename');
  const cohortYear = parseCohortYear(searchParams.get('cohort'));
  const treatmentType: TreatmentType = searchParams.get('treatment') === 'nac' ? 'nac' : 'surgery';

  if (!filename) {
    return NextResponse.json({ error: 'filename is required' }, { status: 400 });
  }

  const safeFilename = path.basename(decodeURIComponent(filename));
  const cacheKey = `${cohortYear}:${treatmentType}:${safeFilename}`;
  if (offsetCache.has(cacheKey)) {
    return NextResponse.json(offsetCache.get(cacheKey));
  }

  const originalPaths = getDatasetPaths('original', cohortYear, treatmentType);
  const croppedPaths = getDatasetPaths('cropped', cohortYear, treatmentType);
  const originalPath = path.join(originalPaths.images, safeFilename);
  const cropPath = path.join(croppedPaths.images, safeFilename);

  if (!fs.existsSync(originalPath) || !fs.existsSync(cropPath)) {
    return NextResponse.json({ error: 'Original or crop_ui image not found' }, { status: 404 });
  }

  try {
    const offset = await runCropOffsetCli(originalPath, cropPath);
    offsetCache.set(cacheKey, offset);
    return NextResponse.json(offset);
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Failed to compute crop offset';
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
