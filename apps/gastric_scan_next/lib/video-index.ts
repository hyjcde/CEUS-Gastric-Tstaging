import fs from 'fs';
import path from 'path';
import { VideoInfo } from '@/types';

const VIDEO_ROOT = path.join(process.cwd(), 'public', 'videos');

function extractPatientIdFromVideo(filename: string): string {
  const stem = filename.replace(/\.[^.]+$/i, '');
  const match = stem.match(/^([A-Za-z]?\d+)/);
  return match ? match[1] : stem;
}

function scanDirectory(
  dir: string,
  urlPrefix: string,
  treatment: VideoInfo['treatment'],
  waterFilled: boolean,
  bucket: Map<string, VideoInfo[]>,
) {
  if (!fs.existsSync(dir)) return;
  for (const entry of fs.readdirSync(dir)) {
    if (!entry.toLowerCase().endsWith('.mp4')) continue;
    const patientId = extractPatientIdFromVideo(entry);
    const list = bucket.get(patientId) ?? [];
    list.push({
      url: `${urlPrefix}/${entry}`,
      filename: entry,
      treatment,
      water_filled: waterFilled,
    });
    bucket.set(patientId, list);
  }
}

let cachedMap: Map<string, VideoInfo[]> | null = null;

export function getVideoMap(): Map<string, VideoInfo[]> {
  if (cachedMap) return cachedMap;

  const map = new Map<string, VideoInfo[]>();
  scanDirectory(path.join(VIDEO_ROOT, 'direct_surgery'), '/videos/direct_surgery', 'direct_surgery', false, map);
  scanDirectory(path.join(VIDEO_ROOT, 'direct_surgery', 'water_filled'), '/videos/direct_surgery/water_filled', 'direct_surgery', true, map);
  scanDirectory(path.join(VIDEO_ROOT, 'neoadjuvant'), '/videos/neoadjuvant', 'neoadjuvant', false, map);
  scanDirectory(path.join(VIDEO_ROOT, 'neoadjuvant', 'water_filled'), '/videos/neoadjuvant/water_filled', 'neoadjuvant', true, map);

  for (const [key, videos] of map.entries()) {
    videos.sort((a, b) => a.filename.localeCompare(b.filename, undefined, { numeric: true }));
    map.set(key, videos);
  }

  cachedMap = map;
  return map;
}

export function getVideosForPatient(patientId: string): VideoInfo[] {
  const normalized = patientId.replace(/^0+/, '');
  const map = getVideoMap();
  return map.get(patientId) ?? map.get(normalized) ?? [];
}
