import fs from 'fs';
import path from 'path';
import { PROJECT_ROOT } from '@/lib/config';

/** Allowed roots (relative to PROJECT_ROOT) for no-upload video streaming. */
export const VIDEO_STREAM_ROOTS = [
  'apps/gastric_scan_next/public/videos',
  'dataset/internal/prospective_2025/2025/crop_ui/videos',
  'dataset/external/crop_ui/videos',
  'data/raw/qualified_reader_videos',
  'data/raw/patient_videos_2025',
  'docs/clinical_validation/reader_study_v150',
] as const;

const VIDEO_EXTS = new Set(['.mp4', '.webm', '.mov', '.mkv', '.avi']);

export function toProjectRel(absPath: string): string {
  const abs = path.resolve(absPath);
  const root = path.resolve(PROJECT_ROOT);
  if (!abs.startsWith(root + path.sep) && abs !== root) {
    throw new Error('path outside project root');
  }
  return path.relative(root, abs).split(path.sep).join('/');
}

export function streamUrlForAbs(absPath: string): string {
  return `/api/patients/videos/stream?rel=${encodeURIComponent(toProjectRel(absPath))}`;
}

export function isUnderAllowedRoot(absPath: string): boolean {
  const abs = path.resolve(absPath);
  for (const rel of VIDEO_STREAM_ROOTS) {
    const root = path.resolve(PROJECT_ROOT, rel);
    if (abs === root || abs.startsWith(root + path.sep)) return true;
  }
  return false;
}

/** Resolve stream/public video URL to absolute filesystem path. */
export function resolvePlayableVideoPath(videoUrl: string): string | null {
  if (!videoUrl) return null;

  try {
    const u = new URL(videoUrl, 'http://local.invalid');
    if (u.pathname.includes('/api/patients/videos/stream')) {
      const rel = u.searchParams.get('rel') || '';
      if (!rel) return null;
      const abs = path.resolve(PROJECT_ROOT, rel);
      if (!isUnderAllowedRoot(abs) || !fs.existsSync(abs)) return null;
      return abs;
    }
  } catch {
    /* fall through */
  }

  if (videoUrl.startsWith('/') && !videoUrl.startsWith('//')) {
    // Strip query for public paths
    const clean = videoUrl.split('?')[0];
    const pub = path.join(process.cwd(), 'public', clean.replace(/^\//, ''));
    if (fs.existsSync(pub)) return pub;
  }

  if (fs.existsSync(videoUrl)) {
    const abs = path.resolve(videoUrl);
    return isUnderAllowedRoot(abs) ? abs : null;
  }

  const absFromRoot = path.resolve(PROJECT_ROOT, videoUrl.replace(/^\//, ''));
  if (fs.existsSync(absFromRoot) && isUnderAllowedRoot(absFromRoot)) return absFromRoot;
  return null;
}

export function isVideoFilename(name: string): boolean {
  return VIDEO_EXTS.has(path.extname(name).toLowerCase());
}
