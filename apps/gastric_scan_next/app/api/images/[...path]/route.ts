import { NextRequest, NextResponse } from 'next/server';
import fs from 'fs';
import path from 'path';
import {
  getDatasetPaths,
  getBenignDatasetPaths,
  getExternalDatasetPaths,
  DatasetType,
  TreatmentType,
  parseCohortYear,
  DEFAULT_DATASET,
} from '@/lib/config';
import { isExternalQueue, parseWorkbenchQueueId } from '@/lib/cohort';

function getTargetDirectory(paths: ReturnType<typeof getDatasetPaths>, type: string): string {
  switch (type) {
    case 'images':
      return paths.images;
    case 'overlays':
      return paths.overlays;
    case 'lymph_node_analysis':
      return paths.overlaysTransparent;
    case 'annotations':
      return paths.annotations;
    case 'roi':
      return paths.roi;
    default:
      return '';
  }
}

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
) {
  const resolvedParams = await params;
  const pathSegments = resolvedParams.path;
  const { searchParams } = new URL(request.url);
  const cohortYearParam = searchParams.get('cohort') || '2025';
  const treatmentTypeParam = searchParams.get('treatment') || 'surgery';
  const cohortYear = parseCohortYear(cohortYearParam);
  const treatmentType: TreatmentType = (treatmentTypeParam === 'nac') ? 'nac' : 'surgery';
  const queueParam = searchParams.get('queue');
  const queueId = queueParam ? parseWorkbenchQueueId(queueParam) : null;
  
  // Expecting: [dataset, type, filename] e.g. /api/images/original/images/file.jpg
  // Or fallback: [type, filename] (default to crop_ui / cropped)
  
  let dataset: DatasetType = DEFAULT_DATASET;
  let type = '';
  let filename = '';

  if (pathSegments && pathSegments.length === 3) {
      // New format: /api/images/[dataset]/[type]/[filename]
      const ds = pathSegments[0];
      if (ds === 'original' || ds === 'cropped') {
          dataset = ds as DatasetType;
      }
      type = pathSegments[1];
      filename = pathSegments[2];
  } else if (pathSegments && pathSegments.length === 2) {
      // Old format fallback: /api/images/[type]/[filename]
      type = pathSegments[0];
      filename = pathSegments[1];
  } else {
    return NextResponse.json({ error: 'Invalid path' }, { status: 400 });
  }

  const externalCenterId = queueId && isExternalQueue(queueId) && queueId.startsWith('external:')
    ? queueId.slice('external:'.length)
    : null;
  const benignCenterId = queueId?.startsWith('benign:')
    ? queueId.slice('benign:'.length)
    : null;
  const paths = benignCenterId
    ? getBenignDatasetPaths(dataset, benignCenterId)
    : externalCenterId
      ? getExternalDatasetPaths(dataset, externalCenterId)
      : getDatasetPaths(dataset, cohortYear, treatmentType);
  if (!paths) {
    return NextResponse.json({ error: 'Unknown data queue' }, { status: 404 });
  }
  const targetDir = getTargetDirectory(paths, type);
  if (!targetDir) {
    return NextResponse.json({ error: 'Invalid type' }, { status: 400 });
  }

  // Security check: prevent directory traversal
  // Decode URL-encoded filename (e.g., %2813%29 -> (13))
  const decodedFilename = decodeURIComponent(filename);
  const safeFilename = path.basename(decodedFilename);
  let filePath = path.join(targetDir, safeFilename);

  // If file not found in primary directory, try the other dataset directory
  if (!fs.existsSync(filePath)) {
      const otherDataset: DatasetType = dataset === 'original' ? 'cropped' : 'original';
      const pathsOther = benignCenterId
        ? getBenignDatasetPaths(otherDataset, benignCenterId)
        : externalCenterId
          ? getExternalDatasetPaths(otherDataset, externalCenterId)
          : getDatasetPaths(otherDataset, cohortYear, treatmentType);
      const targetDirOther = pathsOther ? getTargetDirectory(pathsOther, type) : '';
      
      if (targetDirOther) {
          const altPath = path.join(targetDirOther, safeFilename);
          if (fs.existsSync(altPath)) {
              filePath = altPath;
          }
      }
  }

  if (!fs.existsSync(filePath)) {
      return NextResponse.json({ error: `File not found: ${safeFilename}`, path: filePath }, { status: 404 });
  }

  const fileBuffer = fs.readFileSync(filePath);
  
  // Determine Content-Type
  let contentType = 'application/octet-stream';
  if (filename.toLowerCase().endsWith('.jpg') || filename.toLowerCase().endsWith('.jpeg')) {
    contentType = 'image/jpeg';
  } else if (filename.toLowerCase().endsWith('.png')) {
    contentType = 'image/png';
  } else if (filename.toLowerCase().endsWith('.webp')) {
    contentType = 'image/webp';
  } else if (filename.toLowerCase().endsWith('.json')) {
    contentType = 'application/json';
  }

  return new NextResponse(fileBuffer, {
    headers: {
      'Content-Type': contentType,
      'Cache-Control': 'public, max-age=31536000, immutable',
      // Allow reader Agent (:8767) to drawImage / SAM from workbench frames
      'Access-Control-Allow-Origin': '*',
      'Cross-Origin-Resource-Policy': 'cross-origin',
    },
  });
}

export async function OPTIONS() {
  return new NextResponse(null, {
    status: 204,
    headers: {
      'Access-Control-Allow-Origin': '*',
      'Access-Control-Allow-Methods': 'GET,OPTIONS',
      'Access-Control-Allow-Headers': 'Content-Type',
      'Access-Control-Max-Age': '86400',
    },
  });
}
