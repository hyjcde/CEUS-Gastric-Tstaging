import fs from 'fs';
import path from 'path';
import { PROJECT_ROOT } from '@/lib/config';

let cachedTails: Set<string> | undefined;

function loadScreenedTails(): Set<string> {
  if (cachedTails) return cachedTails;
  const tails = new Set<string>();
  const dir = path.join(PROJECT_ROOT, 'runtime/public_screen');
  const screenPath = path.join(dir, 'cohort_screen_20261029.json');
  if (!fs.existsSync(screenPath)) {
    cachedTails = tails;
    return tails;
  }
  const screen = JSON.parse(fs.readFileSync(screenPath, 'utf-8')) as { excluded?: Record<string, unknown> };
  const excluded = new Set(Object.keys(screen.excluded || {}));
  for (const name of ['manifest.json', 'manifest_bm.json']) {
    const filePath = path.join(dir, name);
    if (!fs.existsSync(filePath)) continue;
    const manifest = JSON.parse(fs.readFileSync(filePath, 'utf-8')) as {
      patients?: Array<{ key?: string; frames?: Array<{ n?: number; label?: string }> }>;
    };
    for (const patient of manifest.patients || []) {
      for (const frame of patient.frames || []) {
        const key = `${patient.key}/${frame.n}`;
        if (!excluded.has(key)) continue;
        const label = String(frame.label || '').trim().toLowerCase();
        if (!label) continue;
        tails.add(label);
        tails.add(label.split('__').pop() || label);
      }
    }
  }
  cachedTails = tails;
  return tails;
}

export function isScreenedImage(filename: string): boolean {
  const stem = String(filename || '').replace(/\.[^.]+$/i, '').trim().toLowerCase();
  if (!stem) return false;
  const tails = loadScreenedTails();
  return tails.has(stem) || tails.has(stem.split('__').pop() || stem);
}

export function countScreenedImages(filenames: string[]): number {
  return filenames.reduce((count, name) => count + (isScreenedImage(name) ? 1 : 0), 0);
}
