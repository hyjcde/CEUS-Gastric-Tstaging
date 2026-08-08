import fs from 'fs';
import path from 'path';
import { VideoInfo } from '@/types';
import { PROJECT_ROOT } from '@/lib/config';
import { streamUrlForAbs, isVideoFilename, VIDEO_STREAM_ROOTS } from '@/lib/video-stream';

const PUBLIC_VIDEO_ROOT = path.join(process.cwd(), 'public', 'videos');

function extractPatientIdFromVideo(filename: string): string {
  const stem = filename.replace(/\.[^.]+$/i, '');
  // 676059_(1) / 1034135-2 / 1048931-1
  const paren = stem.match(/^(.+?)_\((\d+)\)$/);
  if (paren) return paren[1];
  const dash = stem.match(/^(.+?)-(\d+)$/);
  if (dash) return dash[1];
  const leading = stem.match(/^([A-Za-z]?\d+)/);
  return leading ? leading[1] : stem;
}

function inferTreatment(relOrDir: string): VideoInfo['treatment'] {
  const s = relOrDir.toLowerCase();
  if (s.includes('neoadjuvant') || s.includes('nac') || s.includes('新辅助')) return 'neoadjuvant';
  return 'direct_surgery';
}

function inferWaterFilled(name: string): boolean {
  return /water|喝水|充盈/i.test(name);
}

function videoPriority(video: VideoInfo): number {
  let decodedUrl = video.url;
  try {
    decodedUrl = decodeURIComponent(video.url);
  } catch {
    /* keep raw URL */
  }
  if (decodedUrl.includes('/dataset/') && decodedUrl.includes('/crop_ui/')) return 0;
  if (path.extname(video.filename).toLowerCase() === '.mp4') return 1;
  return 2;
}

function scanPublicDirectory(
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

function pushUnique(bucket: Map<string, VideoInfo[]>, patientId: string, info: VideoInfo) {
  const list = bucket.get(patientId) ?? [];
  if (list.some((v) => v.filename === info.filename && v.url === info.url)) {
    bucket.set(patientId, list);
    return;
  }
  list.push(info);
  bucket.set(patientId, list);
}

/** Scan allowlisted dataset/raw trees into patient → videos map. */
function scanVideoDirectory(
  root: string,
  bucket: Map<string, VideoInfo[]>,
  treatment = inferTreatment(root),
) {
  if (!fs.existsSync(root)) return;
  let entries: string[] = [];
  try {
    entries = fs.readdirSync(root);
  } catch {
    return;
  }
  for (const entry of entries) {
    if (!isVideoFilename(entry)) continue;
    const abs = path.join(root, entry);
    let st: fs.Stats;
    try {
      st = fs.statSync(abs);
    } catch {
      continue;
    }
    if (!st.isFile()) continue;
    const patientId = extractPatientIdFromVideo(entry);
    pushUnique(bucket, patientId, {
      url: streamUrlForAbs(abs),
      filename: entry,
      treatment,
      water_filled: inferWaterFilled(entry),
    });
  }
}

function scanVideoTree(
  root: string,
  bucket: Map<string, VideoInfo[]>,
  treatment: VideoInfo['treatment'],
  depth = 0,
) {
  if (depth > 4 || !fs.existsSync(root)) return;
  let entries: string[] = [];
  try {
    entries = fs.readdirSync(root);
  } catch {
    return;
  }
  for (const entry of entries) {
    const abs = path.join(root, entry);
    let st: fs.Stats;
    try {
      st = fs.statSync(abs);
    } catch {
      continue;
    }
    if (st.isDirectory()) {
      scanVideoTree(abs, bucket, treatment, depth + 1);
    } else if (isVideoFilename(entry)) {
      const patientId = extractPatientIdFromVideo(entry);
      pushUnique(bucket, patientId, {
        url: streamUrlForAbs(abs),
        filename: entry,
        treatment,
        water_filled: inferWaterFilled(entry) || inferWaterFilled(root),
      });
    }
  }
}

function scanExternalRoots(bucket: Map<string, VideoInfo[]>) {
  const roots = [
    path.join(PROJECT_ROOT, 'dataset/internal/prospective_2025/2025/crop_ui/videos'),
    path.join(PROJECT_ROOT, 'data/raw/qualified_reader_videos'),
  ];

  for (const root of roots) {
    scanVideoDirectory(root, bucket);
  }
  scanVideoTree(
    path.join(PROJECT_ROOT, 'data/raw/legacy_external_direct_surgery'),
    bucket,
    'direct_surgery',
  );
  scanVideoTree(
    path.join(PROJECT_ROOT, 'data/raw/legacy_gastric_staging'),
    bucket,
    'direct_surgery',
  );

  // External videos are stored under dataset/external/<center>/crop_ui/videos,
  // not in one flat dataset/external/crop_ui/videos directory.
  const externalRoot = path.join(PROJECT_ROOT, 'dataset/external');
  if (fs.existsSync(externalRoot)) {
    try {
      for (const center of fs.readdirSync(externalRoot)) {
        scanVideoDirectory(path.join(externalRoot, center, 'crop_ui/videos'), bucket);
      }
    } catch {
      /* ignore unreadable centers */
    }
  }

  // Shallow-ish scan of 2025 raw (patient folders) — only match by folder/file tokens when building full map is expensive;
  // full recursive scan limited to depth-2 filenames containing digits.
  const raw2025 = path.join(PROJECT_ROOT, 'data/raw/patient_videos_2025');
  if (fs.existsSync(raw2025)) {
    try {
      for (const folder of fs.readdirSync(raw2025)) {
        const folderPath = path.join(raw2025, folder);
        let st: fs.Stats;
        try {
          st = fs.statSync(folderPath);
        } catch {
          continue;
        }
        if (!st.isDirectory()) continue;
        // Prefer numeric ids inside folder name e.g. XH0103… — skip if no digit patient key usable
        let files: string[] = [];
        try {
          files = fs.readdirSync(folderPath);
        } catch {
          continue;
        }
        for (const entry of files) {
          if (!isVideoFilename(entry)) continue;
          const abs = path.join(folderPath, entry);
          const patientId = extractPatientIdFromVideo(entry);
          // Only index when filename starts with a clear numeric/alphanumeric patient token
          if (!/^[A-Za-z]?\d{4,}/.test(patientId)) continue;
          pushUnique(bucket, patientId, {
            url: streamUrlForAbs(abs),
            filename: entry,
            treatment: 'direct_surgery',
            water_filled: inferWaterFilled(entry) || inferWaterFilled(folder),
          });
        }
      }
    } catch {
      /* ignore */
    }
  }

  void VIDEO_STREAM_ROOTS;
}

let cachedMap: Map<string, VideoInfo[]> | null = null;

export function getVideoMap(): Map<string, VideoInfo[]> {
  if (cachedMap) return cachedMap;

  const map = new Map<string, VideoInfo[]>();
  scanPublicDirectory(path.join(PUBLIC_VIDEO_ROOT, 'direct_surgery'), '/videos/direct_surgery', 'direct_surgery', false, map);
  scanPublicDirectory(path.join(PUBLIC_VIDEO_ROOT, 'direct_surgery', 'water_filled'), '/videos/direct_surgery/water_filled', 'direct_surgery', true, map);
  scanPublicDirectory(path.join(PUBLIC_VIDEO_ROOT, 'neoadjuvant'), '/videos/neoadjuvant', 'neoadjuvant', false, map);
  scanPublicDirectory(path.join(PUBLIC_VIDEO_ROOT, 'neoadjuvant', 'water_filled'), '/videos/neoadjuvant/water_filled', 'neoadjuvant', true, map);
  scanExternalRoots(map);

  for (const [key, videos] of map.entries()) {
    videos.sort((a, b) => (
      videoPriority(a) - videoPriority(b)
      || a.filename.localeCompare(b.filename, undefined, { numeric: true })
    ));
    const uniqueByFilename = videos.filter((video, index, all) => (
      all.findIndex((candidate) => candidate.filename === video.filename) === index
    ));
    map.set(key, uniqueByFilename);
  }

  cachedMap = map;
  return map;
}

/** Force rebuild after new videos appear on disk. */
export function invalidateVideoMapCache() {
  cachedMap = null;
}

export function getVideosForPatient(patientId: string): VideoInfo[] {
  const normalized = patientId.replace(/^0+/, '');
  const map = getVideoMap();
  const hit = map.get(patientId) ?? map.get(normalized) ?? [];
  if (hit.length) return hit;

  // Fast path for crop_ui filenames when cache miss (new file): glob by prefix
  const cropDirs = [
    path.join(PROJECT_ROOT, 'dataset/internal/prospective_2025/2025/crop_ui/videos'),
    path.join(PROJECT_ROOT, 'data/raw/qualified_reader_videos'),
  ];
  const externalRoot = path.join(PROJECT_ROOT, 'dataset/external');
  if (fs.existsSync(externalRoot)) {
    try {
      for (const center of fs.readdirSync(externalRoot)) {
        cropDirs.push(path.join(externalRoot, center, 'crop_ui/videos'));
      }
    } catch {
      /* ignore unreadable centers */
    }
  }
  const out: VideoInfo[] = [];
  const tokens = Array.from(new Set([patientId, normalized].filter(Boolean)));
  for (const dir of cropDirs) {
    if (!fs.existsSync(dir)) continue;
    let entries: string[] = [];
    try {
      entries = fs.readdirSync(dir);
    } catch {
      continue;
    }
    for (const entry of entries) {
      if (!isVideoFilename(entry)) continue;
      const pid = extractPatientIdFromVideo(entry);
      if (!tokens.some((t) => pid === t || pid.replace(/^0+/, '') === t)) continue;
      const abs = path.join(dir, entry);
      out.push({
        url: streamUrlForAbs(abs),
        filename: entry,
        treatment: inferTreatment(dir),
        water_filled: inferWaterFilled(entry),
      });
    }
  }
  out.sort((a, b) => a.filename.localeCompare(b.filename, undefined, { numeric: true }));
  return out;
}
