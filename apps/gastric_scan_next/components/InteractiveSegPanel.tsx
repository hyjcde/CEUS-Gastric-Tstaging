'use client';

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import {
  BrainCircuit, Brain, Check, CircleMinus, CirclePlus, Crosshair, Droplets, Eraser, FileText, Flag, History, Layers, Loader2, MoreHorizontal, MousePointer2, PanelTop, Pause, Pencil, Pentagon, Play, Plus, RotateCcw, Save, ScanLine, ScanSearch, Share2, SkipBack, SkipForward, Sparkles, Spline, Trash2, Undo2, Video, Workflow, X, ZoomIn, Brush,
} from 'lucide-react';
import type { LumenOverride, MaskBoundaryOverride, MaskHistoryEntry, Patient, VideoInfo, VideoMaskFrameOverride } from '@/types';
import type { SamReport } from '@/lib/reader/types';
import { bboxFromPolygon, periLesionRoi } from '@/lib/mask-override';
import { attachRoiOverlays, clampDinoRoiBox, scaleDinoRoiBox, type DinoRoiBox } from '@/lib/dino-roi-preview';
import { normalizeLumenBBox, type LumenBBox } from '@/lib/lumen-override';
import { useSettings } from '@/contexts/SettingsContext';
import { patientDisplayLabel } from '@/lib/patient-display';
import { CaseGoldReveal } from '@/components/CaseGoldReveal';
import { useDoctorAccount } from '@/contexts/DoctorAccountContext';
import { useOpsRecorder } from '@/contexts/OperationRecorderContext';
import { useViewingTraceRecorder } from '@/components/viewing-trace/useViewingTraceRecorder';
import { ViewingTraceDock } from '@/components/viewing-trace/ViewingTraceDock';
import { CineSpeedSelect } from '@/components/CineSpeedSelect';
import { ASSIST_ANALYSIS_STEPS, AssistAnalysisModal } from '@/components/reader/AssistAnalysisModal';
import { DinoRoiLayerDialog } from '@/components/DinoRoiLayerDialog';
import { WallFeatureAnalysisCard } from '@/components/WallFeatureAnalysisCard';
import { ExplainableAnalysis, type ExplainableFramePayload } from '@/components/ExplainableAnalysis';
import type { ExplainableAnalysisResult } from '@/lib/concept-agent-merge';
import type { LayerAnalyzeResult } from '@/lib/human-assist/load-contact-geom';
import { computeLesionLumenGeometry, lumenBoxToPolygon, type LesionLumenGeometry } from '@/lib/lesion-lumen-geometry';
import { canAutoJoinWall, extendWallThroughLesion } from '@/lib/wall-extension';
import { extendWallByPixels } from '@/lib/wall-pixel-extend';
import {
  clusterLayersAlongWall,
  judgeWallLayerBreach,
  type WallLayerReadout,
} from '@/lib/wall-layer-breach';
import { readoutFromTrace, traceWallLayersFromPaint } from '@/lib/wall-layer-trace';
import { clarifyDeepestEcho, grayCropToDataUrl, type WallEchoClarify } from '@/lib/wall-echo-clarify';
import { applyWallPromptMeta, attachLayerInterrupts, doctorClinicalIds, recheckWallInterruptDraft, ticksFromInterrupts, toggleDoctorInterrupt } from '@/lib/wall-layer-interrupt';
import {
  DEFAULT_CINE_FPS,
  cineFrameIndex,
  estimateCineFpsFromMediaTimes,
  formatCineLabel,
  formatKeyframeTime,
  snapCineTimeToFrame,
  stepCineTime,
} from '@/lib/reader/cine-time';
import type { WallLayerTarget } from '@/lib/reader/cine-time';
import {
  ADJACENT_LOCK_EVENT,
  WALL_ASSIST_DRAFT_EVENT,
  WALL_INTERRUPT_OVERRIDE_EVENT,
  WALL_PROMPT_META_EVENT,
  DEPTH_SCREEN_EVENT,
  pairMeta,
  parseAdjacentPair,
  parseWallLayerTarget,
  type AdjacentLockEventDetail,
  type AdjacentPair,
  type DepthScreenEventDetail,
  type WallInterruptOverrideDetail,
  type WallPromptMetaDetail,
} from '@/lib/reader/adjacent-stage-lock';
import {
  SEROSA_ANCHOR_OPTIONS,
  WALL_ANATOMY_TARGETS,
  WALL_VISIBILITY_OPTIONS,
  addAnalysisFocusPoint,
  analysisFocusHint,
  anatomyTargetMeta,
  paintLineHint,
  paintToolLabel,
  suggestedAnatomyFromScreen,
  verdictLabel,
  type SerosaAnchorMode,
  type WallVisibility,
} from '@/lib/reader/wall-prompt';
import { buildReportEvidenceImages } from '@/lib/report-evidence-images';
import type { GcUsReportImage } from '@/lib/gc-us-report-template';
import {
  LESION_CONTOUR_MAX_POINTS,
  LESION_CTRL_COUNT,
  LESION_SIMPLIFY_TARGET,
  LESION_SOFT_SIGMA,
  LUMEN_CONTOUR_MAX_POINTS,
  LUMEN_CTRL_COUNT,
  LUMEN_SOFT_SIGMA,
  WALL_CONTOUR_MAX_POINTS,
  WALL_CTRL_COUNT,
  WALL_SIMPLIFY_TARGET,
  WALL_SOFT_SIGMA,
  adaptiveHandleCount,
  boxToClosedPolygon,
  clonePoly,
  controlIndices,
  pickOrInsertOnContour,
  pickSoftAnchor,
  pickVisibleHandle,
  prepareEditableContour,
  softDeform,
  translatePolygon,
  VISIBLE_HANDLE_COUNT,
} from '@/lib/human-assist/contour-edit';
import {
  applyPaintToPolygon,
  type PaintOp,
} from '@/lib/human-assist/mask-paint';
import {
  appendFinalPromptPoint,
  appendPromptPoint,
  prepareSubmitPromptStroke,
  strokeClosedPolyline,
} from '@/lib/human-assist/prompt-stroke';
import { DoctorKeyframeStrip } from '@/components/reader/DoctorKeyframeStrip';
import { CineScrubBar } from '@/components/reader/CineScrubBar';
import {
  canAddDoctorKeyframe,
  findDoctorKeyframe,
  findDoctorKeyframeById,
  isDoctorKeyframeOpen,
  laterUnrefinedKeyframes,
  toggleDeepestInvasion,
  newDoctorKeyframeId,
  pickAnalysisKeyframes,
  pickPropagateSource,
  snapshotKeyframesForAnalysis,
  sortDoctorKeyframes,
  keyframeAnalysisQuality,
  uncorrectedContourNote,
  type DoctorKeyframe,
  DOCTOR_KEYFRAME_DEDUP_SEC,
  DOCTOR_KEYFRAME_MAX,
  DOCTOR_KEYFRAME_OPEN_EPS_SEC,
} from '@/lib/reader/doctor-keyframes';
import {
  applyPropagateHits,
  propagateContoursToKeyframes,
} from '@/lib/reader/keyframe-propagate';
import {
  captureDoctorFrameFromVideo,
  presegDoctorKeyframeFromFrame,
  scalePolyToFull,
  type CapturedDoctorFrame,
} from '@/lib/reader/doctor-keyframe-preseg';

type EditMode = 'soft' | 'hard' | 'add' | 'delete' | 'sam' | 'brush' | 'polygon';
type MediaMode = 'image' | 'video';
type ContourLayer = 'lesion' | 'wall';
type DragLayer = ContourLayer | 'lumen' | 'band';
type RefineTarget = 'lesion' | 'lumen';
type LumenSculptMode = 'brush-add' | 'brush-sub';
type LesionSegmentationModel = 'sabm_sam2_guided' | 'sam31' | 'dinov3' | 'convnext';
type LumenBoxHandle = 'move' | 'nw' | 'ne' | 'sw' | 'se';
type ActiveSamPromptMode = 'point' | 'box' | 'scribble' | 'lasso';
type ActiveSamPromptLabel = 'positive' | 'negative';
type ActiveSamStroke = {
  points: number[][];
  label: ActiveSamPromptLabel;
  kind: 'scribble' | 'lasso';
  width: number;
  target?: 'lesion' | 'lumen';
};
type PersistOverrideOptions = {
  silent?: boolean;
};

type MaskAuditEventType = 'mask_event' | 'mask_saved' | 'model_trace' | 'error';

export type WorkflowTraceStep = {
  trace_id: string;
  step_id: string;
  action: string;
  status: 'started' | 'completed' | 'error' | 'skipped';
  source: 'doctor' | 'model' | 'agent' | 'system';
  frame_time_sec?: number | null;
  input?: Record<string, unknown>;
  output?: Record<string, unknown>;
  error?: string;
  recorded_at: string;
};

function formatHistoryBox(box: LumenBBox | null | undefined): string {
  if (!box) return '—';
  return `${Math.round(box.x1)}, ${Math.round(box.y1)} - ${Math.round(box.x2)}, ${Math.round(box.y2)}`;
}

function summarizeMaskForAudit(override: MaskBoundaryOverride | null | undefined) {
  const frames = override?.video_frames || [];
  const lastFrame = frames[frames.length - 1];
  return {
    mask_points: override?.mask_polygon?.length || 0,
    wall_points: override?.wall_polygon?.length || 0,
    roi_box_present: Boolean(override?.roi_bbox),
    video_frame_count: frames.length,
    frames_with_lesion_box: frames.filter((frame) => Boolean(frame.roi_bbox)).length,
    frames_with_lumen_mask: frames.filter((frame) => (frame.lumen_polygon?.length || 0) >= 3).length,
    frames_with_lumen_box: frames.filter((frame) => Boolean(frame.lumen_bbox)).length,
    last_frame_index: lastFrame?.frame_index,
    last_frame_time_sec: lastFrame?.timestamp_sec,
    source: override?.source,
    model_version: override?.model_version,
    video_present: Boolean(override?.video_url),
  };
}

function capturePointerSafely(target: HTMLCanvasElement, pointerId: number): void {
  try {
    target.setPointerCapture(pointerId);
  } catch {
    // Synthetic or already-ended pointer events may not have an active capture target.
  }
}

function formatCineTime(sec: number, fps = DEFAULT_CINE_FPS): string {
  return formatCineLabel(sec, fps);
}

function applyProgressSlider(bar: HTMLElement | null, timeSec: number, durationSec: number) {
  if (!bar) return;
  const pct = durationSec > 0 ? Math.min(100, Math.max(0, (timeSec / durationSec) * 100)) : 0;
  bar.style.setProperty('--progress', `${pct.toFixed(3)}%`);
  if (bar.getAttribute('role') === 'slider') {
    bar.setAttribute('aria-valuenow', timeSec.toFixed(3));
    bar.setAttribute('aria-valuetext', formatCineTime(timeSec));
  }
}

const DINO_LAYER_INDICES = [2, 5, 8, 11] as const;

async function readJsonPayload<T>(response: Response, operation: string): Promise<T> {
  const text = await response.text();
  try {
    return JSON.parse(text) as T;
  } catch {
    const contentType = response.headers.get('content-type') || 'unknown content type';
    const prefix = text.replace(/\s+/g, ' ').trim().slice(0, 140);
    throw new Error(
      `${operation} returned HTTP ${response.status} as ${contentType}, not JSON`
        + (prefix ? `: ${prefix}` : ''),
    );
  }
}

type KeyframeCandidate = {
  timestamp_sec: number;
  frame_index?: number | null;
  frame_id?: string | null;
  image_width?: number | null;
  image_height?: number | null;
  score: number;
  reasons?: string[];
  thumb_url?: string;
  predicted_polygon?: number[][];
  prediction_status?: 'pending' | 'predicted' | 'needs_roi' | 'failed';
  prediction_error?: string;
};

type NnInteractiveSessionState = {
  key: string;
  id: string;
  initialized: boolean;
};

export type DinoLayerResult = {
  available?: boolean;
  model?: string;
  layer_index?: number;
  input_size?: number;
  token_grid?: [number, number];
  feature_dim?: number;
  feature_vector?: number[];
  feature_names?: string[];
  scalars?: Record<string, number>;
  vector_stats?: {
    mean?: number;
    std?: number;
    l2_norm?: number;
  };
  feature_overlay_png?: string;
  wall_evidence_overlay_png?: string;
  roi_feature_overlay_png?: string;
  roi_wall_evidence_overlay_png?: string;
  roi_box?: DinoRoiBox | null;
  error?: string;
};

export type DinoFeatureResult = DinoLayerResult & {
  available?: boolean;
  case_id?: string;
  frame_time?: number;
  layer_indices?: number[];
  layers?: DinoLayerResult[];
  roi_box?: DinoRoiBox | null;
};
interface InteractiveSegPanelProps {
  patient: Patient | null;
  override: MaskBoundaryOverride | null;
  onOverrideChange: (next: MaskBoundaryOverride | null) => void;
  /** Doctor-confirmed gastric lumen box / SAM3.1 contour for Agent geometry. */
  lumenOverride?: LumenOverride | null;
  onLumenOverrideChange?: (next: LumenOverride | null) => void;
  /** Optional: wall-layer + GC-US assist payload for DiagnosisPanel */
  onImagingAssist?: (payload: ImagingAssistPayload | null) => void;
  /** Current-frame system evidence shown in the AI-assisted task panel. */
  onSystemReport?: (report: SamReport | null) => void;
  /** Current-frame DINO region feature result shown in the workbench evidence panel. */
  onDinoFeatures?: (result: DinoFeatureResult | null) => void;
  /** Route the current video evidence into the unified research Agent. */
  onUnifiedAgentRun?: (capture: UnifiedAgentCapture) => Promise<void> | void;
  unifiedAgentBusy?: boolean;
  /** Receive normalized doctor and model trace steps for the unified Agent. */
  onWorkflowStep?: (step: WorkflowTraceStep) => void;
  /** Merge explainable boundary analysis into concept / diagnosis state (same as UltrasoundViewer). */
  onExplainableComplete?: (result: ExplainableAnalysisResult) => void;
  /** Emit report images generated from the current segmentation and keyframes. */
  onReportEvidenceImages?: (images: GcUsReportImage[], caseId?: string | null) => void;
  inline?: boolean;
}

export type UnifiedAgentFrame = {
  frame_png_b64: string;
  frame_id: string;
  frame_index: number;
  timestamp_sec: number;
  quality_score: number;
  mask_polygon?: number[][];
  lumen_polygon?: number[][];
  lumen_bbox?: LumenBBox | null;
  keyframe_id?: string;
};

export type UnifiedAgentCapture = {
  frames: UnifiedAgentFrame[];
  current_time: number;
  image_width: number;
  image_height: number;
  mask_polygon: number[][];
  roi_bbox?: { x1: number; y1: number; x2: number; y2: number };
  lumen_bbox?: LumenBBox;
  lumen_polygon?: number[][];
  workflow_trace?: WorkflowTraceStep[];
  /** contour_anchored_fast (default Assist) | full */
  assist_profile?: 'contour_anchored_fast' | 'full';
  /** Contour-anchored diagnosis context assembled before Assist. */
  contour_context?: {
    lesion_confirmed: boolean;
    lumen_mask_type: 'sam31_polygon' | 'bbox_proxy' | 'missing';
    geometry_relation?: string;
    geometry_quality?: string;
    layer_label?: string | null;
    layer_pixel_based?: boolean;
    in_contact?: boolean | null;
    prepared_actions?: string[];
    adjacent_lock?: AdjacentPair | null;
    doctor_t_excluded?: boolean;
    wall_target_layers?: 1 | 2 | 3 | null;
    wall_interrupts?: Array<{ layer: number; nameZh: string; interrupted: boolean }>;
    wall_ticks?: Array<{ layer: number; nameZh: string; nameEn?: string; status?: string }>;
    wall_note?: string | null;
    echo_pattern?: string | null;
    echo_note?: string | null;
    extra_lesion_count?: number;
    keyframe_interrupts?: Array<{
      timeSec: number;
      interrupts?: Array<{ layer: number; nameZh?: string; interrupted?: boolean }>;
    }>;
    peri_lesion_roi?: { x1: number; y1: number; x2: number; y2: number } | null;
  };
};

export type ImagingAssistPayload = {
  layerResult: LayerAnalyzeResult | null;
  lesionPolygon: number[][];
  wallPolygon: number[][];
  frameSize: { width: number; height: number } | null;
  frameDataUrl?: string | null;
  lumenBBox?: LumenBBox | null;
  lumenPolygon?: number[][];
};

function dist2(a: number[], b: number[]) {
  const dx = a[0] - b[0];
  const dy = a[1] - b[1];
  return dx * dx + dy * dy;
}

function nearestVertex(points: number[][], imgPt: number[], thresholdPx: number): number {
  let best = -1;
  let bestD = thresholdPx * thresholdPx;
  for (let i = 0; i < points.length; i += 1) {
    const d = dist2(points[i], imgPt);
    if (d <= bestD) {
      bestD = d;
      best = i;
    }
  }
  return best;
}

function nearestEdgeInsert(points: number[][], imgPt: number[], thresholdPx: number): number {
  if (points.length < 2) return -1;
  let bestEdge = -1;
  let bestD = thresholdPx * thresholdPx;
  for (let i = 0; i < points.length; i += 1) {
    const a = points[i];
    const b = points[(i + 1) % points.length];
    const abx = b[0] - a[0];
    const aby = b[1] - a[1];
    const apx = imgPt[0] - a[0];
    const apy = imgPt[1] - a[1];
    const ab2 = abx * abx + aby * aby || 1;
    const t = Math.max(0, Math.min(1, (apx * abx + apy * aby) / ab2));
    const cx = a[0] + t * abx;
    const cy = a[1] + t * aby;
    const d = dist2([cx, cy], imgPt);
    if (d <= bestD) {
      bestD = d;
      bestEdge = i;
    }
  }
  return bestEdge;
}

async function videoOrImageToSamFrame(
  video: HTMLVideoElement | null,
  img: HTMLImageElement | null,
  preferVideo: boolean,
  maxSide = 1024,
): Promise<{ b64: string; width: number; height: number; fullWidth: number; fullHeight: number; scale: number }> {
  let fullW = 0;
  let fullH = 0;
  const draw = (ctx: CanvasRenderingContext2D, dw: number, dh: number) => {
    if (preferVideo && video && video.videoWidth > 0) {
      ctx.drawImage(video, 0, 0, dw, dh);
      return;
    }
    if (!img) throw new Error('no frame');
    ctx.drawImage(img, 0, 0, dw, dh);
  };
  if (preferVideo && video && video.videoWidth > 0) {
    fullW = video.videoWidth;
    fullH = video.videoHeight;
  } else if (img) {
    fullW = img.naturalWidth || img.width;
    fullH = img.naturalHeight || img.height;
  } else {
    throw new Error('no frame');
  }
  const scale = Math.min(1, maxSide / Math.max(fullW, fullH));
  const width = Math.max(1, Math.round(fullW * scale));
  const height = Math.max(1, Math.round(fullH * scale));
  const c = document.createElement('canvas');
  c.width = width;
  c.height = height;
  const ctx = c.getContext('2d');
  if (!ctx) throw new Error('canvas unavailable');
  draw(ctx, width, height);
  const b64 = c.toDataURL('image/jpeg', 0.92).replace(/^data:image\/jpeg;base64,/, '');
  return { b64, width, height, fullWidth: fullW, fullHeight: fullH, scale };
}

async function dataUrlToSamFrame(dataUrl: string, maxSide = 1024) {
  const img = new Image();
  await new Promise<void>((resolve, reject) => {
    img.onload = () => resolve();
    img.onerror = () => reject(new Error('thumb decode failed'));
    img.src = dataUrl;
  });
  return videoOrImageToSamFrame(null, img, false, maxSide);
}

function captureFromHiddenVideo(videoUrl: string, timeSec: number, maxSide = 1024) {
  return new Promise<{ b64: string; width: number; height: number; fullWidth: number; fullHeight: number; scale: number }>((resolve, reject) => {
    const hidden = document.createElement('video');
    hidden.muted = true;
    hidden.playsInline = true;
    hidden.preload = 'auto';
    const cleanup = () => {
      hidden.removeAttribute('src');
      hidden.load();
    };
    const fail = (error: unknown) => {
      cleanup();
      reject(error instanceof Error ? error : new Error('hidden video capture failed'));
    };
    hidden.onerror = () => fail(new Error('hidden video load failed'));
    hidden.onloadeddata = () => {
      try {
        if (Math.abs((hidden.currentTime || 0) - timeSec) < 0.04 && hidden.readyState >= 2) {
          hidden.onseeked?.(new Event('seeked'));
          return;
        }
        hidden.currentTime = timeSec;
      } catch (error) {
        fail(error);
      }
    };
    hidden.onseeked = () => {
      videoOrImageToSamFrame(hidden, null, true, maxSide)
        .then((frame) => {
          cleanup();
          resolve(frame);
        })
        .catch(fail);
    };
    hidden.src = videoUrl;
  });
}

async function captureKeyframeStill(opts: {
  video: HTMLVideoElement;
  videoUrl: string;
  timeSec: number;
  thumbDataUrl?: string | null;
}) {
  if (Math.abs((opts.video.currentTime || 0) - opts.timeSec) <= 0.08 && opts.video.videoWidth > 0) {
    return videoOrImageToSamFrame(opts.video, null, true, 1024);
  }
  if (opts.thumbDataUrl) {
    try {
      return await dataUrlToSamFrame(opts.thumbDataUrl);
    } catch {
      // Fall through to an off-screen seek so the visible playhead never moves.
    }
  }
  return captureFromHiddenVideo(opts.videoUrl, opts.timeSec);
}

function polygonCentroid(points: number[][]): number[] | null {
  if (!points.length) return null;
  let sx = 0;
  let sy = 0;
  for (const p of points) {
    sx += p[0];
    sy += p[1];
  }
  return [sx / points.length, sy / points.length];
}

function polygonAreaAbs(points: number[][]): number {
  if (!points || points.length < 3) return 0;
  let area = 0;
  for (let i = 0; i < points.length; i += 1) {
    const a = points[i];
    const b = points[(i + 1) % points.length] || a;
    area += a[0] * b[1] - b[0] * a[1];
  }
  return Math.abs(area) / 2;
}

function pointInPolygon(pt: number[], poly: number[][]): boolean {
  if (!poly || poly.length < 3) return false;
  let inside = false;
  for (let i = 0, j = poly.length - 1; i < poly.length; j = i, i += 1) {
    const xi = poly[i][0];
    const yi = poly[i][1];
    const xj = poly[j][0];
    const yj = poly[j][1];
    const intersect = ((yi > pt[1]) !== (yj > pt[1]))
      && (pt[0] < ((xj - xi) * (pt[1] - yi)) / ((yj - yi) || 1e-9) + xi);
    if (intersect) inside = !inside;
  }
  return inside;
}

function hitWholeShape(pt: number[], poly: number[][], pad = 0): boolean {
  if (!poly || poly.length < 3) return false;
  if (pointInPolygon(pt, poly)) return true;
  const box = bboxFromPolygon(poly);
  if (!box) return false;
  return pt[0] >= box.x1 - pad
    && pt[0] <= box.x2 + pad
    && pt[1] >= box.y1 - pad
    && pt[1] <= box.y2 + pad;
}

const BOX_DRAW_CURSOR_LESION = 'crosshair';
const BOX_DRAW_CURSOR_LUMEN = 'crosshair';

function minDist2ToPolygon(pt: number[], poly: number[][]): number {
  if (!poly.length) return Number.POSITIVE_INFINITY;
  let best = Number.POSITIVE_INFINITY;
  for (let i = 0; i < poly.length; i += 1) {
    const a = poly[i];
    const b = poly[(i + 1) % poly.length] || a;
    best = Math.min(best, dist2(pt, a));
    const abx = b[0] - a[0];
    const aby = b[1] - a[1];
    const apx = pt[0] - a[0];
    const apy = pt[1] - a[1];
    const denom = abx * abx + aby * aby;
    if (denom <= 1e-9) continue;
    const t = Math.max(0, Math.min(1, (apx * abx + apy * aby) / denom));
    const cx = a[0] + abx * t;
    const cy = a[1] + aby * t;
    const d = (pt[0] - cx) ** 2 + (pt[1] - cy) ** 2;
    if (d < best) best = d;
  }
  return best;
}

function polygonHit(pt: number[], poly: number[][], edgeThrPx: number): boolean {
  if (!poly || poly.length < 3) return false;
  if (pointInPolygon(pt, poly)) return true;
  return minDist2ToPolygon(pt, poly) <= edgeThrPx * edgeThrPx;
}

function selectTopAreaKeyframes(
  frames: VideoMaskFrameOverride[],
  topK = 5,
  minGapSec = 0.5,
): KeyframeCandidate[] {
  const ranked = frames
    .filter((frame) => Array.isArray(frame.mask_polygon) && frame.mask_polygon.length >= 3)
    .map((frame) => ({
      frame,
      area: polygonAreaAbs(frame.mask_polygon),
    }))
    .filter((item) => item.area > 1)
    .sort((a, b) => b.area - a.area);

  const picked: Array<{ frame: VideoMaskFrameOverride; area: number }> = [];
  for (const item of ranked) {
    if (picked.length >= topK) break;
    if (picked.some((sel) => Math.abs(sel.frame.timestamp_sec - item.frame.timestamp_sec) < minGapSec)) {
      continue;
    }
    picked.push(item);
  }
  picked.sort((a, b) => a.frame.timestamp_sec - b.frame.timestamp_sec);

  return picked.map((item) => {
    const width = Math.max(1, item.frame.imageWidth || 1);
    const height = Math.max(1, item.frame.imageHeight || 1);
    return {
      timestamp_sec: item.frame.timestamp_sec,
      frame_index: item.frame.frame_index ?? null,
      frame_id: item.frame.frame_id ?? null,
      image_width: width,
      image_height: height,
      score: Number((item.area / 1000).toFixed(2)),
      reasons: [`area_px=${Math.round(item.area)}`, `gap>=${minGapSec}s`],
      predicted_polygon: item.frame.mask_polygon.map((point) => [
        Number((point[0] / width).toFixed(6)),
        Number((point[1] / height).toFixed(6)),
      ]),
      prediction_status: 'predicted' as const,
    };
  });
}

type PropagateApiFrame = {
  frame_index?: number;
  frame_time: number;
  direction?: string;
  mask_polygon?: number[][];
  quality_score?: number;
};

type PropagateApiResult = {
  status?: string;
  needs_reanchor?: boolean;
  accepted_frames?: number;
  num_frames?: number;
  propagation_mode?: string;
  frames?: PropagateApiFrame[];
};

function mapPropagateFramesToOverrides(
  frames: PropagateApiFrame[],
  imageWidth: number,
  imageHeight: number,
  source: VideoMaskFrameOverride['source'] = 'video_track',
): VideoMaskFrameOverride[] {
  return frames
    .filter((frame) => Array.isArray(frame.mask_polygon) && frame.mask_polygon.length >= 3)
    .map((frame) => {
      const maskPolygon = frame.mask_polygon!.map((point) => [Number(point[0]), Number(point[1])]);
      return {
        frame_index: Number.isFinite(Number(frame.frame_index))
          ? Number(frame.frame_index)
          : undefined,
        timestamp_sec: Number(Number(frame.frame_time).toFixed(3)),
        imageWidth,
        imageHeight,
        mask_polygon: maskPolygon,
        roi_bbox: bboxFromPolygon(maskPolygon),
        source,
        propagation_status: frame.direction === 'seed' ? 'seed' as const : 'accepted' as const,
        quality_score: Number(frame.quality_score ?? 0),
      };
    });
}

function nearestOverrideFrame(
  frames: VideoMaskFrameOverride[],
  timestampSec: number,
  maxDeltaSec = 0.35,
): VideoMaskFrameOverride | null {
  if (!frames.length) return null;
  // Propagate frames are time-ordered; binary search keeps scrub/playback redraws cheap.
  let lo = 0;
  let hi = frames.length - 1;
  while (lo < hi) {
    const mid = (lo + hi) >> 1;
    if (frames[mid].timestamp_sec < timestampSec) lo = mid + 1;
    else hi = mid;
  }
  let bestIdx = lo;
  if (lo > 0) {
    const prev = frames[lo - 1];
    const curr = frames[lo];
    if (Math.abs(prev.timestamp_sec - timestampSec) <= Math.abs(curr.timestamp_sec - timestampSec)) {
      bestIdx = lo - 1;
    }
  }
  const nearest = frames[bestIdx];
  if (Math.abs(nearest.timestamp_sec - timestampSec) > maxDeltaSec) return null;
  return nearest;
}

function mergeLumenIntoLesionFrames(
  lesionFrames: VideoMaskFrameOverride[],
  lumenFrames: VideoMaskFrameOverride[],
  seedLumen?: { polygon?: number[][]; box?: { x1: number; y1: number; x2: number; y2: number } | null },
  seedTimeSec?: number,
): VideoMaskFrameOverride[] {
  let carryPoly = seedLumen?.polygon && seedLumen.polygon.length >= 3
    ? seedLumen.polygon
    : undefined;
  const seedBox = seedLumen?.box || (carryPoly ? bboxFromPolygon(carryPoly) : undefined);
  const seedPoly = carryPoly && carryPoly.length >= 3 ? carryPoly : undefined;
  // Clamp runaway lumen tracking: do not let a tracked contour drift far from the
  // doctor-confirmed seed box, otherwise it paints the whole frame.
  const clampToSeed = (poly: number[][]) => {
    if (!seedBox) return poly;
    const bbox = bboxFromPolygon(poly);
    if (!bbox) return poly;
    const seedCx = (seedBox.x1 + seedBox.x2) / 2;
    const seedCy = (seedBox.y1 + seedBox.y2) / 2;
    const seedW = Math.max(24, seedBox.x2 - seedBox.x1);
    const seedH = Math.max(24, seedBox.y2 - seedBox.y1);
    const maxDx = seedW * 1.8;
    const maxDy = seedH * 1.8;
    const cx = (bbox.x1 + bbox.x2) / 2;
    const cy = (bbox.y1 + bbox.y2) / 2;
    const w = bbox.x2 - bbox.x1;
    const h = bbox.y2 - bbox.y1;
    const drifted = Math.abs(cx - seedCx) > maxDx
      || Math.abs(cy - seedCy) > maxDy
      || w > seedW * 3.5
      || h > seedH * 3.5;
    // Drifted → carry previous valid contour instead of the runaway one.
    return drifted ? (carryPoly && carryPoly.length >= 3 ? carryPoly : poly) : poly;
  };
  // Frame-to-frame continuity: adjacent frames of a filled lumen should change
  // smoothly. Reject sudden jumps relative to the previous accepted contour,
  // not only relative to the seed.
  const bboxIou = (
    a: { x1: number; y1: number; x2: number; y2: number },
    b: { x1: number; y1: number; x2: number; y2: number },
  ) => {
    const ix1 = Math.max(a.x1, b.x1);
    const iy1 = Math.max(a.y1, b.y1);
    const ix2 = Math.min(a.x2, b.x2);
    const iy2 = Math.min(a.y2, b.y2);
    const inter = Math.max(0, ix2 - ix1) * Math.max(0, iy2 - iy1);
    const areaA = Math.max(1, (a.x2 - a.x1) * (a.y2 - a.y1));
    const areaB = Math.max(1, (b.x2 - b.x1) * (b.y2 - b.y1));
    return inter / Math.max(1, areaA + areaB - inter);
  };
  const clampWithPrev = (poly: number[][]) => {
    const seeded = clampToSeed(poly);
    if (seeded !== poly) return seeded; // already replaced by carry
    if (!carryPoly || carryPoly.length < 3) return poly;
    const prevBox = bboxFromPolygon(carryPoly);
    const bbox = bboxFromPolygon(poly);
    if (!prevBox || !bbox) return poly;
    const prevCx = (prevBox.x1 + prevBox.x2) / 2;
    const prevCy = (prevBox.y1 + prevBox.y2) / 2;
    const prevW = Math.max(24, prevBox.x2 - prevBox.x1);
    const prevH = Math.max(24, prevBox.y2 - prevBox.y1);
    const cx = (bbox.x1 + bbox.x2) / 2;
    const cy = (bbox.y1 + bbox.y2) / 2;
    const w = bbox.x2 - bbox.x1;
    const h = bbox.y2 - bbox.y1;
    const jump = Math.abs(cx - prevCx) > prevW * 0.6
      || Math.abs(cy - prevCy) > prevH * 0.6
      || w > prevW * 1.8
      || h > prevH * 1.8
      || w < prevW * 0.45
      || h < prevH * 0.45
      || bboxIou(bbox, prevBox) < 0.25;
    return jump ? carryPoly : poly;
  };
  // The seed frame must keep the doctor-segmented lumen contour exactly;
  // the tracker only propagates to other frames.
  const seedFrame = seedPoly && typeof seedTimeSec === 'number'
    ? nearestOverrideFrame(lesionFrames, seedTimeSec, 0.6)
    : null;
  // Carry-forward logic assumes chronological order.
  const ordered = [...lesionFrames].sort((a, b) => a.timestamp_sec - b.timestamp_sec);
  return ordered.map((frame) => {
    if (seedPoly && seedFrame && frame.timestamp_sec === seedFrame.timestamp_sec) {
      return {
        ...frame,
        lumen_polygon: seedPoly.map((point) => [point[0], point[1]]),
        lumen_bbox: undefined,
      };
    }
    const matched = nearestOverrideFrame(lumenFrames, frame.timestamp_sec, 0.4);
    if (matched?.mask_polygon?.length) {
      carryPoly = clampWithPrev(matched.mask_polygon);
    }
    if (!carryPoly || carryPoly.length < 3) return frame;
    return {
      ...frame,
      lumen_polygon: carryPoly.map((point) => [point[0], point[1]]),
      // Once a mask exists, drop the box so the view shows contour only.
      lumen_bbox: undefined,
    };
  });
}

async function requestVideoPropagate(body: Record<string, unknown>): Promise<PropagateApiResult> {
  const response = await fetch('/api/agent/video/propagate', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  const payload = await readJsonPayload<{
    ok?: boolean;
    error?: string;
    result?: PropagateApiResult;
  }>(response, 'Video propagation endpoint');
  if (!response.ok || !payload.ok || !payload.result) {
    throw new Error(payload.error || 'video propagation failed');
  }
  return payload.result;
}

/** Lumen-side preference vector for estimated wall offset (from lesion toward lumen). */
function lumenPreferVector(
  lesion: number[][],
  lumenPoly: number[][],
  lumenBox: LumenBBox | null,
): [number, number] | undefined {
  const lesionC = polygonCentroid(lesion);
  if (!lesionC) return undefined;
  let lumenC: number[] | null = null;
  if (lumenPoly.length >= 3) lumenC = polygonCentroid(lumenPoly);
  else if (lumenBox) {
    lumenC = [(lumenBox.x1 + lumenBox.x2) / 2, (lumenBox.y1 + lumenBox.y2) / 2];
  }
  if (!lumenC) return undefined;
  const dx = lumenC[0] - lesionC[0];
  const dy = lumenC[1] - lesionC[1];
  const len = Math.hypot(dx, dy) || 1;
  return [dx / len, dy / len];
}

function geometryRelationText(geometry: LesionLumenGeometry, zh: boolean): string {
  if (geometry.relation === 'overlap') {
    return zh
      ? '状态: 重叠 — 重点看病灶与胃腔壁接触处（突破分析关键区）'
      : 'Status: overlap — focus on lesion-to-lumen-wall contact (breakthrough zone)';
  }
  if (geometry.relation === 'near_lumen') {
    return zh
      ? '状态: 邻近胃腔壁 — 接触带为突破分析关键区'
      : 'Status: near lumen wall — contact band is the breakthrough analysis zone';
  }
  if (geometry.relation === 'separated') {
    return zh
      ? '状态: 分离, 病灶似在胃腔外 — 请扩大胃腔框使其包含胃壁与肿块后再分析'
      : 'Status: separated — lesion may be outside the lumen; expand the lumen to include wall and mass before analysis';
  }
  return zh ? '状态: 未评估' : 'Status: unknown';
}

function geometryQualityText(geometry: LesionLumenGeometry, zh: boolean): string {
  if (geometry.quality === 'high') return zh ? '轮廓质量较好' : 'Good contour quality';
  if (geometry.quality === 'moderate') return zh ? '轮廓质量中等' : 'Moderate contour quality';
  return zh ? '轮廓点较少' : 'Sparse contour points';
}

type ViewFocusBox = { x1: number; y1: number; x2: number; y2: number };
type ViewFocusMode = 'roi' | 'overlap';

function clampViewOffset(size: number, canvas: number, scale: number, offset: number): number {
  const drawn = size * scale;
  if (drawn <= canvas) return (canvas - drawn) / 2;
  return Math.min(0, Math.max(canvas - drawn, offset));
}

function computeDisplayTransform(
  iw: number,
  ih: number,
  cw: number,
  ch: number,
  focus: ViewFocusBox | null,
  viewZoom = 1,
  viewCenter: { x: number; y: number } | null = null,
): { scale: number; dx: number; dy: number } {
  const zoom = Math.max(1, Math.min(8, viewZoom || 1));
  if (focus && zoom <= 1.02) {
    const pad = 0.22;
    const bw0 = Math.max(8, focus.x2 - focus.x1);
    const bh0 = Math.max(8, focus.y2 - focus.y1);
    const bx = Math.max(0, focus.x1 - bw0 * pad);
    const by = Math.max(0, focus.y1 - bh0 * pad);
    const bw = Math.min(iw - bx, bw0 * (1 + 2 * pad));
    const bh = Math.min(ih - by, bh0 * (1 + 2 * pad));
    const scale = Math.min(cw / bw, ch / bh, 4);
    return {
      scale,
      dx: (cw - bw * scale) / 2 - bx * scale,
      dy: (ch - bh * scale) / 2 - by * scale,
    };
  }
  const fit = Math.min(cw / iw, ch / ih);
  const scale = fit * zoom;
  const cx = viewCenter && Number.isFinite(viewCenter.x) ? viewCenter.x : iw / 2;
  const cy = viewCenter && Number.isFinite(viewCenter.y) ? viewCenter.y : ih / 2;
  const dx = clampViewOffset(iw, cw, scale, cw / 2 - cx * scale);
  const dy = clampViewOffset(ih, ch, scale, ch / 2 - cy * scale);
  return { scale, dx, dy };
}

// Distinct contour colors: muted so the ultrasound lesion stays readable.
const COLOR_LESION_FILL = 'transparent';
const COLOR_LESION_STROKE = 'rgba(94, 184, 196, 0.58)';
const COLOR_WALL_FILL = 'transparent';
const COLOR_WALL_STROKE = 'rgba(217, 140, 72, 0.55)';
const COLOR_LUMEN_FILL = 'transparent';
const COLOR_LUMEN_STROKE = 'rgba(196, 128, 204, 0.50)';
const COLOR_LUMEN_BOX_FILL = 'transparent';
const COLOR_LUMEN_BOX_STROKE = 'rgba(196, 128, 204, 0.40)';
const COLOR_LUMEN_HANDLE = 'rgba(196, 128, 204, 0.22)';
const COLOR_LESION_HANDLE = 'rgba(94, 184, 196, 0.22)';
const COLOR_WALL_HANDLE = 'rgba(217, 140, 72, 0.22)';
const CONTOUR_LINE_WIDTH = 1;
const HANDLE_STROKE = 'rgba(248, 250, 252, 0.70)';

function bboxFromPointsOrBox(
  points: number[][],
  box: LumenBBox | null | undefined,
): ViewFocusBox | null {
  const fromPoly = bboxFromPolygon(points);
  if (fromPoly) return fromPoly;
  if (box) return normalizeLumenBBox(box);
  return null;
}

function bboxFromPath(points: number[][], padding = 0): ViewFocusBox | null {
  if (!points || points.length < 2) return null;
  const valid = points.filter((point) => (
    Number.isFinite(Number(point[0])) && Number.isFinite(Number(point[1]))
  ));
  if (valid.length < 2) return null;
  const x1 = Math.min(...valid.map((point) => Number(point[0]))) - padding;
  const y1 = Math.min(...valid.map((point) => Number(point[1]))) - padding;
  const x2 = Math.max(...valid.map((point) => Number(point[0]))) + padding;
  const y2 = Math.max(...valid.map((point) => Number(point[1]))) + padding;
  if (x2 <= x1 || y2 <= y1) return null;
  return { x1, y1, x2, y2 };
}

function promptModeText(mode: ActiveSamPromptMode, zh: boolean): string {
  if (mode === 'point') return zh ? '正/负点' : 'Positive/negative points';
  if (mode === 'box') return zh ? '框选' : 'Box';
  if (mode === 'scribble') return zh ? '自由涂鸦' : 'Freehand scribble';
  return zh ? '套索' : 'Lasso';
}

function oppositePromptLabel(label: ActiveSamPromptLabel): ActiveSamPromptLabel {
  return label === 'positive' ? 'negative' : 'positive';
}

function explicitPromptLabel(label: ActiveSamPromptLabel, shiftKey: boolean): ActiveSamPromptLabel {
  return shiftKey ? oppositePromptLabel(label) : label;
}

function unionFocusBoxes(...boxes: Array<ViewFocusBox | null | undefined>): ViewFocusBox | null {
  const valid = boxes.filter(Boolean) as ViewFocusBox[];
  if (!valid.length) return null;
  return {
    x1: Math.min(...valid.map((b) => b.x1)),
    y1: Math.min(...valid.map((b) => b.y1)),
    x2: Math.max(...valid.map((b) => b.x2)),
    y2: Math.max(...valid.map((b) => b.y2)),
  };
}

function segmentIntersectionPoint(
  firstStart: number[],
  firstEnd: number[],
  secondStart: number[],
  secondEnd: number[],
): number[] | null {
  const rx = firstEnd[0] - firstStart[0];
  const ry = firstEnd[1] - firstStart[1];
  const sx = secondEnd[0] - secondStart[0];
  const sy = secondEnd[1] - secondStart[1];
  const denominator = rx * sy - ry * sx;
  if (Math.abs(denominator) < 1e-8) return null;
  const qx = secondStart[0] - firstStart[0];
  const qy = secondStart[1] - firstStart[1];
  const t = (qx * sy - qy * sx) / denominator;
  const u = (qx * ry - qy * rx) / denominator;
  if (t < -1e-6 || t > 1 + 1e-6 || u < -1e-6 || u > 1 + 1e-6) return null;
  return [firstStart[0] + t * rx, firstStart[1] + t * ry];
}

function overlapFocusBox(
  lesion: number[][],
  lumen: number[][],
  lumenBox: LumenBBox | null | undefined,
  geometry: LesionLumenGeometry,
): ViewFocusBox | null {
  if (lesion.length < 3) return null;
  const lumenShape = lumen.length >= 3 ? lumen : lumenBoxToPolygon(lumenBox);
  if (lumenShape.length < 3) return null;

  const points: number[][] = [];
  lesion.forEach((point) => {
    if (pointInPolygon(point, lumenShape)) points.push(point);
  });
  lumenShape.forEach((point) => {
    if (pointInPolygon(point, lesion)) points.push(point);
  });
  for (let i = 0; i < lesion.length; i += 1) {
    const lesionStart = lesion[i];
    const lesionEnd = lesion[(i + 1) % lesion.length];
    for (let j = 0; j < lumenShape.length; j += 1) {
      const hit = segmentIntersectionPoint(
        lesionStart,
        lesionEnd,
        lumenShape[j],
        lumenShape[(j + 1) % lumenShape.length],
      );
      if (hit) points.push(hit);
    }
  }

  if (points.length) {
    const padded = points.length === 1
      ? [...points, [points[0][0] + 1, points[0][1] + 1]]
      : points;
    return bboxFromPath(padded, 18);
  }
  if (geometry.relation === 'near_lumen' && geometry.closestLesionPoint && geometry.closestLumenPoint) {
    return bboxFromPath(
      [geometry.closestLesionPoint, geometry.closestLumenPoint],
      24,
    );
  }
  return null;
}

function sleep(ms: number) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function seekVideoForAgent(video: HTMLVideoElement, time: number): Promise<void> {
  return new Promise((resolve) => {
    let settled = false;
    const done = () => {
      if (settled) return;
      settled = true;
      video.removeEventListener('seeked', done);
      resolve();
    };
    video.addEventListener('seeked', done, { once: true });
    video.currentTime = time;
    window.setTimeout(done, 1200);
  });
}

function sanitizeSystemCopy(value: unknown): string {
  return String(value ?? '')
    .replace(/\bSAM(?:2)?\b/gi, 'system analysis')
    .replace(/\bSegment Anything(?: Model)?\b/gi, 'system analysis');
}

function segmentationModelName(model: LesionSegmentationModel, zh: boolean): string {
  if (model === 'sabm_sam2_guided') return zh ? 'SABM-GUS 引导式模型' : 'SABM-GUS guided model';
  if (model === 'sam31') return zh ? 'SAM 3.1' : 'SAM 3.1';
  if (model === 'dinov3') return 'DINO';
  return 'ConvNeXt-UNet';
}

const READER_SEG_MODEL_KEY = 'gastric_reader_lesion_seg_model';

function readStoredLesionSegModel(): LesionSegmentationModel {
  if (typeof window === 'undefined') return 'sam31';
  try {
    return window.localStorage.getItem(READER_SEG_MODEL_KEY) === 'dinov3' ? 'dinov3' : 'sam31';
  } catch {
    return 'sam31';
  }
}

function publicLesionSegModel(model: LesionSegmentationModel): 'sam31' | 'dinov3' {
  return model === 'dinov3' ? 'dinov3' : 'sam31';
}

export function buildModelAssistReport(
  patient: Patient,
  polygon: number[][],
  frameWidth: number,
  frameHeight: number,
  model: LesionSegmentationModel,
  areaRatio?: number,
  zh = true,
): SamReport {
  const clinicalText = [
    patient.report?.ultrasound_findings,
    patient.report?.ultrasound_impression,
    patient.report?.ct_findings,
    patient.report?.ct_impression,
    patient.report?.enhanced_ct_report,
    patient.report?.endoscopy_report,
  ].filter(Boolean).join(' ');
  const text = clinicalText.toLowerCase();
  const bbox = bboxFromPolygon(polygon);
  const lengthPx = bbox ? Math.max(bbox.x2 - bbox.x1, bbox.y2 - bbox.y1) : 0;
  const thicknessPx = bbox ? Math.min(bbox.x2 - bbox.x1, bbox.y2 - bbox.y1) : 0;
  void lengthPx;
  void thicknessPx;
  const shape = zh ? '形态待医生勾选' : 'Morphology pending physician tick';
  const boundary = zh ? '边界待医生勾选' : 'Boundary pending physician tick';
  const layer = /突破肌层|侵犯肌层|固有肌层.*(破坏|受累)/.test(text)
    ? (zh ? '固有肌层受累/结构破坏' : 'Muscularis propria involved / disrupted')
    : /层次.*(完整|清晰)|肌层结构完整/.test(text)
      ? (zh ? '胃壁层次结构相对完整' : 'Wall layers relatively preserved')
      : (zh ? '当前帧层次显示有限，需多切面复核' : 'Limited layer visibility on this frame; multi-plane review needed');
  const serosa = /浆膜.*(中断|破坏|侵犯|不完整)/.test(text)
    ? (zh ? '浆膜高回声带中断或不可见' : 'Serosal bright band interrupted or not visible')
    : /浆膜.*(完整|连续|光滑)/.test(text)
      ? (zh ? '浆膜高回声带连续' : 'Serosal bright band continuous')
      : (zh ? '浆膜：看不清（待医生勾选）' : 'Serosa: unclear (pending physician tick)');
  const perigastric = /胃周|脂肪间隙|邻近器官/.test(text)
    ? (zh ? '已从影像文字资料纳入胃周组织评估' : 'Perigastric tissues assessed from imaging text')
    : (zh ? '当前帧未能确认胃周组织' : 'Perigastric tissues not confirmed on this frame');
  // Text-derived draft only when clinical text supports it; otherwise leave empty (no invented T3/T4).
  const stageDraft = /浆膜.*(中断|破坏|侵犯|不完整)/.test(text)
    ? 'T4+'
    : /突破肌层|侵犯肌层|浆膜下/.test(text)
      ? 'T3'
      : /固有肌层.*(受累|侵犯)|肌层.*受累/.test(text)
        ? 'T2'
        : /黏膜下|肌层结构完整/.test(text)
          ? 'T1'
          : '';
  const stage = stageDraft;
  const location = patient.clinical?.location || (zh ? '胃' : 'Stomach');
  // Length / thickness are table clinical fields (fixed). tumorSize is stored in cm.
  const clinicalLengthCm = patient.clinical?.tumorSize?.length;
  const clinicalThicknessCm = patient.clinical?.tumorSize?.thickness;
  const lengthText = clinicalLengthCm != null
    ? `${Math.round(clinicalLengthCm * 10)} mm`
    : (zh ? '见临床表格' : 'See clinical table');
  const thicknessText = clinicalThicknessCm != null
    ? `${Math.round(clinicalThicknessCm * 10)} mm`
    : (zh ? '见临床表格' : 'See clinical table');
  const modelLabel = model === 'dinov3'
    ? 'DINOv3 lesion candidate'
    : model === 'convnext'
      ? 'ConvNeXt-Base UNet'
      : segmentationModelName(model, false);
  const layerUncertain = zh ? /当前帧/.test(layer) : /Limited layer|this frame/i.test(layer);
  const serosaUncertain = zh ? /当前帧/.test(serosa) : /not confirmed|this frame/i.test(serosa);
  const perigastricUncertain = zh ? /未能/.test(perigastric) : /not confirmed/i.test(perigastric);
  const signs = {
    size: {
      length: {
        value: lengthText,
        status: clinicalLengthCm != null ? 'suggested' : 'uncertain',
        source: 'clinical_data',
        confidence: clinicalLengthCm != null ? 0.9 : 0.2,
        evidence_ref: ['clinical.tumor_size'],
      },
      thickness: {
        value: thicknessText,
        status: clinicalThicknessCm != null ? 'suggested' : 'uncertain',
        source: 'clinical_data',
        confidence: clinicalThicknessCm != null ? 0.9 : 0.2,
        evidence_ref: ['clinical.tumor_size'],
      },
    },
    layer_structure: { value: layer, status: layerUncertain ? 'uncertain' : 'suggested', source: layerUncertain ? 'limited_frame' : 'clinical_text', confidence: 0.5, evidence_ref: ['clinical.imaging_text'] },
    morphology: { value: shape, status: 'suggested', source: 'mask_geometry', confidence: 0.58, evidence_ref: ['lesion_mask.solidity', 'lesion_mask.aspect_ratio'] },
    boundary: { value: boundary, status: 'suggested', source: 'mask_geometry', confidence: 0.55, evidence_ref: ['lesion_mask.boundary'] },
    growth_pattern: { value: shape, status: 'suggested', source: 'mask_geometry', confidence: 0.45, evidence_ref: ['lesion_mask.shape'] },
    serosa_change: { value: serosa, status: serosaUncertain ? 'uncertain' : 'suggested', source: serosaUncertain ? 'limited_frame' : 'clinical_text', confidence: 0.45, evidence_ref: ['clinical.imaging_text'] },
    perigastric_tissue: { value: perigastric, status: perigastricUncertain ? 'uncertain' : 'suggested', source: perigastricUncertain ? 'limited_frame' : 'clinical_text', confidence: 0.4, evidence_ref: ['clinical.imaging_text'] },
  } as unknown as NonNullable<SamReport['signs']>;
  const areaText = areaRatio != null ? `${(areaRatio * 100).toFixed(2)}%` : (zh ? '未返回' : 'n/a');
  const stageLine = stageDraft
    ? (zh
      ? `辅助分期 c${stageDraft}（provisional，待医生确认壁层/浆膜证据后签出）。`
      : `Assist stage c${stageDraft} (provisional, pending physician-confirmed wall/serosa evidence).`)
    : (zh
      ? '辅助分期待医生判断（当前无壁层/浆膜显式证据，不自动给出分期）。'
      : 'Assist stage pending physician (no explicit wall/serosa evidence).');
  const prose = zh
    ? `【超声所见】${location}见低回声占位性病变，大小约${lengthText}，最大厚度${thicknessText}。病灶呈${shape}，${boundary}。胃壁层次：${layer}；浆膜：${serosa}；胃周组织：${perigastric}。\n\n【辅助分析】${modelLabel} 当前帧病灶面积占比 ${areaText}。该结果为模型辅助证据，需医生在关键帧上修正。\n\n【分期倾向草稿】${stageLine}`
    : `[Ultrasound findings] ${location}: hypoechoic lesion, size about ${lengthText}, max thickness ${thicknessText}. Morphology ${shape}; ${boundary}. Wall layers: ${layer}; serosa: ${serosa}; perigastric: ${perigastric}.\n\n[Assist analysis] ${modelLabel}; lesion area ratio on this frame ${areaText}. Model assist only; physician should correct on key frames.\n\n[Stage draft] ${stageLine}`;
  return {
    recommended_stage: stage,
    recommendation_status: 'uncertain',
    signs,
    calibrated_confidence: 0.4,
    summary: prose,
    template_id: 'gc_us_t_report_template_v1',
    schema_version: 'gc_us_report_signs_v1',
    source_doc: '胃癌T分期自进化智能辅助诊断_报告模板_讨论版.docx',
    template_prose: prose,
    evidence: [
      { title: zh ? '病灶分割' : 'Lesion segmentation', detail: `${modelLabel}, ${polygon.length} contour points`, status: 'suggested', source: modelLabel },
      { title: zh ? '形态与边界' : 'Morphology and boundary', detail: `${shape}, ${boundary}`, status: 'suggested', source: 'mask_geometry' },
      { title: zh ? '层次与浆膜' : 'Layers and serosa', detail: `${layer}, ${serosa}`, status: 'uncertain', source: 'clinical_text_or_limited_frame' },
      { title: zh ? '文本分期草稿' : 'Text stage draft', detail: stageDraft, status: 'uncertain', source: 'clinical_text_draft_only' },
    ],
  };
}

function ToolRailButton({
  icon,
  label,
  hint,
  onClick,
  disabled = false,
  active = false,
  side = 'left',
  tone = 'cyan',
  showLabel = true,
  prominent = false,
}: {
  icon: React.ReactNode;
  label: string;
  hint: string;
  onClick: () => void;
  disabled?: boolean;
  active?: boolean;
  side?: 'left' | 'right';
  tone?: 'cyan' | 'fuchsia' | 'emerald' | 'amber' | 'violet' | 'orange' | 'sky' | 'rose' | 'lime' | 'slate';
  showLabel?: boolean;
  prominent?: boolean;
}) {
  const toneClasses: Record<typeof tone, string> = {
    cyan: active
      ? 'bg-cyan-400/60 text-white ring-2 ring-cyan-100'
      : 'text-cyan-200/85 hover:bg-white/10 hover:text-cyan-50',
    fuchsia: active
      ? 'bg-fuchsia-400/60 text-white ring-2 ring-fuchsia-100'
      : 'text-fuchsia-200/85 hover:bg-white/10 hover:text-fuchsia-50',
    emerald: active
      ? 'bg-emerald-500/30 text-emerald-100'
      : 'text-emerald-200/85 hover:bg-white/10 hover:text-emerald-50',
    amber: active
      ? 'bg-amber-500/30 text-amber-100'
      : 'text-amber-200/85 hover:bg-white/10 hover:text-amber-50',
    violet: active
      ? 'bg-violet-500/30 text-violet-100'
      : 'text-violet-200/85 hover:bg-white/10 hover:text-violet-50',
    orange: active
      ? 'bg-orange-500/30 text-orange-100'
      : 'text-orange-200/85 hover:bg-white/10 hover:text-orange-50',
    sky: active
      ? 'bg-sky-500/30 text-sky-100'
      : 'text-sky-200/85 hover:bg-white/10 hover:text-sky-50',
    rose: active
      ? 'bg-rose-500/30 text-rose-100'
      : 'text-rose-200/85 hover:bg-white/10 hover:text-rose-50',
    lime: active
      ? 'bg-lime-500/30 text-lime-100'
      : 'text-lime-200/85 hover:bg-white/10 hover:text-lime-50',
    slate: active
      ? 'bg-white/20 text-white ring-2 ring-white/70'
      : 'bg-transparent text-slate-400 hover:bg-white/10 hover:text-slate-200',
  };
  // Keep hover hints outside the ultrasound canvas so they do not cover the lesion.
  const tooltipPosition = side === 'left'
    ? 'right-full mr-2 top-1/2 -translate-y-1/2'
    : 'left-full ml-2 top-1/2 -translate-y-1/2';
  return (
    <div className="group relative w-full">
      <button
        type="button"
        aria-label={`${label}. ${hint}`}
        aria-pressed={active}
        title={`${label}: ${hint}`}
        disabled={disabled}
        onClick={onClick}
        className={`flex w-full items-center justify-center rounded-md transition-all focus:outline-none disabled:cursor-not-allowed disabled:opacity-35 ${
          showLabel
            ? 'min-h-10 flex-col gap-0.5 px-1 py-1.5 sm:min-h-[2.75rem]'
            : 'h-9 w-9'
        } ${toneClasses[tone]} ${
          prominent && active
            ? 'ring-2 ring-cyan-100 ring-offset-1 ring-offset-black'
            : ''
        }`}
      >
        {icon}
        {showLabel ? (
          <span className="max-w-full text-center text-[11px] font-semibold leading-tight tracking-tight sm:text-xs">
            {label}
          </span>
        ) : null}
      </button>
      <span className={`tool-rail-hint pointer-events-none absolute z-[260] w-44 rounded-md border border-white/15 bg-slate-950/95 px-2 py-1.5 text-[10px] leading-relaxed text-slate-200 opacity-0 shadow-xl transition-opacity group-hover:opacity-100 group-focus-within:opacity-100 ${tooltipPosition}`}>
        <span className="font-semibold text-white">{label}</span>
        <span className="mt-0.5 block text-slate-400">{hint}</span>
      </span>
    </div>
  );
}

function ToolRailDivider() {
  return <div className="tool-rail-divider mx-auto my-0.5 h-px w-[85%] bg-white/15" aria-hidden="true" />;
}

function ToolRailSectionTitle({ children }: { children: React.ReactNode }) {
  return (
    <div className="px-1 pt-1 pb-0.5 text-center text-[9px] font-semibold uppercase tracking-wide text-slate-400">
      {children}
    </div>
  );
}


function FloatingToolGroup({
  children,
  accent = 'default',
}: {
  children: React.ReactNode;
  accent?: 'default' | 'cyan' | 'sky' | 'violet' | 'amber';
}) {
  const accentBorder =
    accent === 'cyan' ? 'border-cyan-400/25'
      : accent === 'sky' ? 'border-sky-400/30'
        : accent === 'violet' ? 'border-violet-400/25'
          : accent === 'amber' ? 'border-amber-400/25'
            : 'border-white/10';
  return (
    <div className={`pointer-events-auto flex items-center gap-0.5 rounded-lg border ${accentBorder} bg-black/70 px-1 py-0.5 backdrop-blur-md`}>
      {children}
    </div>
  );
}

function FloatingToolButton({
  icon,
  label,
  title,
  onClick,
  disabled = false,
  active = false,
  tone = 'slate',
  emphasize = false,
}: {
  icon: React.ReactNode;
  label: string;
  title: string;
  onClick: () => void;
  disabled?: boolean;
  active?: boolean;
  tone?: 'slate' | 'amber' | 'violet' | 'sky' | 'cyan';
  emphasize?: boolean;
}) {
  const toneActive: Record<typeof tone, string> = {
    slate: 'bg-white/20 text-white',
    amber: 'bg-amber-500/30 text-amber-100',
    violet: 'bg-violet-500/55 text-white',
    sky: 'bg-sky-500/45 text-white',
    cyan: 'bg-cyan-500/30 text-cyan-100',
  };
  const toneIdle: Record<typeof tone, string> = {
    slate: 'text-gray-400 hover:bg-white/10 hover:text-white',
    amber: 'text-amber-200/90 hover:bg-amber-400/15 hover:text-amber-50',
    violet: 'text-violet-200/90 hover:bg-violet-400/15 hover:text-violet-50',
    sky: 'text-sky-100 hover:bg-sky-400/20 hover:text-white',
    cyan: 'text-cyan-200/90 hover:bg-cyan-400/15 hover:text-cyan-50',
  };
  return (
    <button
      type="button"
      title={title}
      aria-label={title}
      disabled={disabled}
      onClick={onClick}
      className={`inline-flex items-center gap-1 rounded-md px-1.5 py-1.5 transition-all disabled:cursor-not-allowed disabled:opacity-40 ${
        emphasize ? 'px-2.5 text-[11px] font-extrabold max-md:min-h-11 max-md:px-3.5 max-md:text-[13px]' : 'text-[10px] font-semibold'
      } ${active ? toneActive[tone] : toneIdle[tone]}`}
    >
      {icon}
      <span>{label}</span>
    </button>
  );
}

function HistoryMaskThumbnail({
  entry,
  frameDataUrl,
  mediaMode,
  videoTime,
  zh = true,
}: {
  entry: MaskHistoryEntry;
  frameDataUrl: string | null;
  mediaMode: MediaMode;
  videoTime: number;
  zh?: boolean;
}) {
  const [thumbnail, setThumbnail] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    if (!frameDataUrl) {
      return () => {
        cancelled = true;
      };
    }
    const image = new Image();
    image.onload = () => {
      if (cancelled) return;
      const canvas = document.createElement('canvas');
      canvas.width = 320;
      canvas.height = 180;
      const context = canvas.getContext('2d');
      if (!context) return;
      context.fillStyle = '#050608';
      context.fillRect(0, 0, canvas.width, canvas.height);
      const scale = Math.min(canvas.width / image.naturalWidth, canvas.height / image.naturalHeight);
      const drawWidth = image.naturalWidth * scale;
      const drawHeight = image.naturalHeight * scale;
      const offsetX = (canvas.width - drawWidth) / 2;
      const offsetY = (canvas.height - drawHeight) / 2;
      context.drawImage(image, offsetX, offsetY, drawWidth, drawHeight);

      const historicalFrame = mediaMode === 'video'
        ? nearestOverrideFrame(entry.override.video_frames || [], videoTime, Number.POSITIVE_INFINITY)
        : null;
      const lesionPolygon = historicalFrame?.mask_polygon || entry.override.mask_polygon || [];
      const lumenPolygon = historicalFrame?.lumen_polygon || entry.lumen_override?.lumen_polygon || [];
      const lumenBox = historicalFrame?.lumen_bbox || entry.lumen_override?.lumen_bbox;
      const sourceWidth = historicalFrame?.roi_bbox
        ? entry.override.imageWidth
        : entry.override.imageWidth || image.naturalWidth;
      const sourceHeight = entry.override.imageHeight || image.naturalHeight;
      const drawPolygon = (polygon: number[][], stroke: string) => {
        if (polygon.length < 3) return;
        context.beginPath();
        polygon.forEach(([x, y], index) => {
          const px = offsetX + (Number(x) / sourceWidth) * drawWidth;
          const py = offsetY + (Number(y) / sourceHeight) * drawHeight;
          if (index === 0) context.moveTo(px, py);
          else context.lineTo(px, py);
        });
        context.closePath();
        context.strokeStyle = stroke;
        context.lineWidth = 2;
        context.stroke();
      };
      drawPolygon(lesionPolygon, '#22d3ee');
      drawPolygon(lumenPolygon, '#e879f9');
      if (lumenBox) {
        context.strokeStyle = '#f0abfc';
        context.setLineDash([5, 3]);
        context.strokeRect(
          offsetX + (lumenBox.x1 / sourceWidth) * drawWidth,
          offsetY + (lumenBox.y1 / sourceHeight) * drawHeight,
          ((lumenBox.x2 - lumenBox.x1) / sourceWidth) * drawWidth,
          ((lumenBox.y2 - lumenBox.y1) / sourceHeight) * drawHeight,
        );
        context.setLineDash([]);
      }
      setThumbnail(canvas.toDataURL('image/jpeg', 0.78));
    };
    image.onerror = () => {
      if (!cancelled) setThumbnail(null);
    };
    image.src = frameDataUrl;
    return () => {
      cancelled = true;
    };
  }, [entry, frameDataUrl, mediaMode, videoTime]);

  return frameDataUrl && thumbnail ? (
    <img
      src={thumbnail}
      alt={zh ? '历史遮罩预览' : 'History mask preview'}
      className="h-20 w-32 shrink-0 rounded border border-white/10 bg-black object-contain"
    />
  ) : (
    <div className="flex h-20 w-32 shrink-0 items-center justify-center rounded border border-white/10 bg-black/40 text-[9px] text-slate-500">
      {zh ? '暂无预览' : 'No preview'}
    </div>
  );
}

export function InteractiveSegPanel({
  patient,
  override,
  onOverrideChange,
  lumenOverride = null,
  onLumenOverrideChange,
  onImagingAssist,
  onSystemReport,
  onDinoFeatures,
  onUnifiedAgentRun,
  unifiedAgentBusy = false,
  onWorkflowStep,
  onExplainableComplete,
  onReportEvidenceImages,
  inline = false,
}: InteractiveSegPanelProps) {
  const { language } = useSettings();
  const zh = language !== 'en';
  const { readerId: accountReaderId, authHeaders } = useDoctorAccount();
  const { recordOp, setOpsCase } = useOpsRecorder();
  const {
    record: recordViewingTrace,
    sessionId: viewingTraceSessionId,
    eventCount: viewingTraceEventCount,
    actions: viewingTraceActions,
    refreshActions: refreshViewingTraceActions,
    submitReview: submitViewingTraceReview,
  } = useViewingTraceRecorder({
    patient,
    component: 'InteractiveSegPanel',
    readerId: accountReaderId || undefined,
    authHeaders,
  });
  const viewingTraceRef = useRef(recordViewingTrace);
  viewingTraceRef.current = recordViewingTrace;
  const recordOpRef = useRef(recordOp);
  recordOpRef.current = recordOp;
  useEffect(() => {
    setOpsCase(patient?.id || patient?.patient_id || null, patient?.patient_id || null);
  }, [patient?.id, patient?.patient_id, setOpsCase]);
  const simpleVideoMode = inline && patient?.phase === 'reader_v150';
  const [simplePromptMode, setSimplePromptMode] = useState<ActiveSamPromptMode>('box');
  const [lesionBoxArmed, setLesionBoxArmed] = useState(false);
  const lesionBoxArmedRef = useRef(false);
  const armLesionBox = useCallback((next: boolean) => {
    lesionBoxArmedRef.current = next;
    setLesionBoxArmed(next);
  }, []);
  const [boxAutoSegBusy, setBoxAutoSegBusy] = useState(false);
  const [simpleEditMode, setSimpleEditMode] = useState(false);
  const [simpleEditLayer, setSimpleEditLayer] = useState<ContourLayer>('lesion');
  const [refineTarget, setRefineTarget] = useState<RefineTarget>('lesion');
  const [simpleToolsOpen, setSimpleToolsOpen] = useState(true);
  const [railMoreOpen, setRailMoreOpen] = useState(false);
  const [workflowBusy, setWorkflowBusy] = useState(false);
  const [workflowStepLabel, setWorkflowStepLabel] = useState<string | null>(null);
  const [lesionAutoBusy, setLesionAutoBusy] = useState(false);
  const [simplePromptBox, setSimplePromptBox] = useState<{ x1: number; y1: number; x2: number; y2: number } | null>(null);
  const [activeSamPromptLabel, setActiveSamPromptLabel] = useState<ActiveSamPromptLabel>('positive');
  const [showExplainable, setShowExplainable] = useState(false);
  const [open, setOpen] = useState(false);
  const [mode, setMode] = useState<EditMode>('soft');
  const [mediaMode, setMediaMode] = useState<MediaMode>('image');
  const [activeLayer, setActiveLayer] = useState<ContourLayer>('lesion');
  const [points, setPoints] = useState<number[][]>([]);
  const [wallPoints, setWallPoints] = useState<number[][]>([]);
  const [wallExtensionNote, setWallExtensionNote] = useState('');
  const [wallExtensionStats, setWallExtensionStats] = useState<{
    overshootPx: number | null;
    remainPx: number | null;
    source: string;
  } | null>(null);
  const [wallPickMode, setWallPickMode] = useState(false);
  const [wallPickFlanks, setWallPickFlanks] = useState<number[][]>([]);
  const [wallPaintMode, setWallPaintMode] = useState(false);
  const [wallPaintStroke, setWallPaintStroke] = useState<number[][]>([]);
  const [wallLayerReadout, setWallLayerReadout] = useState<WallLayerReadout | null>(null);
  const [wallLayerBands, setWallLayerBands] = useState<number[][][]>([]);
  const [wallLayerImaginary, setWallLayerImaginary] = useState<boolean[][]>([]);
  const [wallBrushRadius, setWallBrushRadius] = useState(8);
  const [wallLayerTarget, setWallLayerTarget] = useState<WallLayerTarget>(1);
  const [analysisFocusMode, setAnalysisFocusMode] = useState(false);
  const [analysisFocusPoints, setAnalysisFocusPoints] = useState<number[][]>([]);
  const [wallVisibility, setWallVisibility] = useState<WallVisibility>('clear');
  const [serosaAnchorMode, setSerosaAnchorMode] = useState<SerosaAnchorMode>('bilateral');
  const [adjacentPair, setAdjacentPair] = useState<AdjacentPair | null>(null);
  const [wallEchoClarify, setWallEchoClarify] = useState<WallEchoClarify | null>(null);
  const [extraLesionPolygons, setExtraLesionPolygons] = useState<number[][][]>([]);
  const [keepExtraLesion, setKeepExtraLesion] = useState(false);
  const [videoFps, setVideoFps] = useState(DEFAULT_CINE_FPS);
  const [imgLoaded, setImgLoaded] = useState(false);
  const [dragIndex, setDragIndex] = useState<number | null>(null);
  const [dragLayer, setDragLayer] = useState<DragLayer | null>(null);
  const [saving, setSaving] = useState(false);
  const [completeMaskAutosaved, setCompleteMaskAutosaved] = useState(false);
  const completeMaskAutosaveTimerRef = useRef<number | null>(null);
  const lastCompleteMaskSigRef = useRef('');
  const scheduleCompleteMaskAutosaveRef = useRef<(action?: string) => void>(() => undefined);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [historyBusy, setHistoryBusy] = useState(false);
  const [maskHistory, setMaskHistory] = useState<MaskHistoryEntry[]>([]);
  const [historyPreviewId, setHistoryPreviewId] = useState<string | null>(null);
  const [samBusy, setSamBusy] = useState(false);
  const [samReport, setSamReport] = useState<SamReport | null>(null);
  const [dinoBusy, setDinoBusy] = useState(false);
  const [dinoResult, setDinoResult] = useState<DinoFeatureResult | null>(null);
  const [dinoDockOpen, setDinoDockOpen] = useState(false);
  const [activeDinoLayer, setActiveDinoLayer] = useState<number>(11);
  const dinoCacheRef = useRef<Map<string, DinoFeatureResult>>(new Map());
  const [segmentationModel, setSegmentationModel] = useState<LesionSegmentationModel>(readStoredLesionSegModel);
  const [segmentationBusy, setSegmentationBusy] = useState(false);
  const [segmentationModelResult, setSegmentationModelResult] = useState<{
    model?: string;
    lesion_area_ratio?: number;
    validation_summary?: Record<string, unknown>;
    error?: string;
  } | null>(null);
  const [samClicks, setSamClicks] = useState<Array<{ x: number; y: number; label: 'positive' | 'negative' }>>([]);
  const [promptStrokes, setPromptStrokes] = useState<ActiveSamStroke[]>([]);
  const [activePromptStroke, setActivePromptStroke] = useState<ActiveSamStroke | null>(null);
  const [nnInteractiveClicks, setNnInteractiveClicks] = useState<Array<{ x: number; y: number; label: 'positive' | 'negative' }>>([]);
  const [samBoxPreview, setSamBoxPreview] = useState<{ x1: number; y1: number; x2: number; y2: number } | null>(null);
  const [samAvailable, setSamAvailable] = useState<boolean | null>(null);
  const [nnInteractiveBusy, setNnInteractiveBusy] = useState(false);
  const [nnInteractiveMode, setNnInteractiveMode] = useState(false);
  const [nnInteractiveTarget, setNnInteractiveTarget] = useState<'lesion' | 'lumen'>('lesion');
  const [sam31RefineTarget, setSam31RefineTarget] = useState<'lesion' | 'lumen' | null>(null);
  const [nnInteractiveAvailable, setNnInteractiveAvailable] = useState<boolean | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const chooseLesionSegModel = useCallback((next: 'sam31' | 'dinov3') => {
    setSegmentationModel(next);
    try {
      window.localStorage.setItem(READER_SEG_MODEL_KEY, next);
    } catch {
      // Keep the in-memory choice if storage is blocked.
    }
    if (next === 'dinov3') {
      void fetch('/api/agent/lesion-segmentation', { cache: 'no-store' }).catch(() => undefined);
    } else {
      void fetch('/api/agent/sam-interactive', { cache: 'no-store' }).catch(() => undefined);
    }
    setMessage(
      next === 'dinov3'
        ? (zh ? '框选病灶将用 DINO 画 mask，随后辅助分析相同' : 'Box lesion will use DINO; Assist stays the same after the mask')
        : (zh ? '框选病灶将用 SAM 3.1 画 mask，随后辅助分析相同' : 'Box lesion will use SAM 3.1; Assist stays the same after the mask'),
    );
  }, [zh]);
  const [roiMode, setRoiMode] = useState<'predicted' | 'doctor' | 'auto'>('predicted');
  const [lumenBox, setLumenBox] = useState<LumenBBox | null>(null);
  const [lumenPolygon, setLumenPolygon] = useState<number[][]>([]);
  const [lumenConfidence, setLumenConfidence] = useState<number | null>(null);
  const [lumenBusy, setLumenBusy] = useState(false);
  const [lumenSamBusy, setLumenSamBusy] = useState(false);
  const [lumenEditMode, setLumenEditMode] = useState(false);
  const [lumenSculptMode, setLumenSculptMode] = useState<LumenSculptMode | null>(null);
  const [sculptLayer, setSculptLayer] = useState<'lesion' | 'lumen'>('lumen');
  const [paintRadius, setPaintRadius] = useState(16);
  const [lumenSaving, setLumenSaving] = useState(false);
  const [lumenResultMeta, setLumenResultMeta] = useState<{
    detector_backend_id?: string;
    sam_backend_id?: string;
    sam_score?: number;
    source?: LumenOverride['source'];
    error?: string;
  } | null>(null);
  const [videos, setVideos] = useState<VideoInfo[]>([]);
  const [videoUrl, setVideoUrl] = useState<string>('');
  const [videoTime, setVideoTime] = useState(0);
  const [videoDuration, setVideoDuration] = useState(0);
  const [videoPlaybackRate, setVideoPlaybackRate] = useState<number>(1);
  const videoPlaybackRateRef = useRef<number>(1);
  videoPlaybackRateRef.current = videoPlaybackRate;
  const [isPlaying, setIsPlaying] = useState(false);
  const [trackOnPlay, setTrackOnPlay] = useState(false);
  const [trackingPrepared, setTrackingPrepared] = useState(false);
  const [precomputeBusy, setPrecomputeBusy] = useState(false);
  const [precomputeProgress, setPrecomputeProgress] = useState<string | null>(null);
  /** Global long-task progress (tracking / assist); shown as a page-level bar, not only button text. */
  const [taskProgress, setTaskProgress] = useState<{
    label: string;
    step: number;
    totalSteps: number;
    detail?: string | null;
  } | null>(null);
  const [keyCandidates, setKeyCandidates] = useState<KeyframeCandidate[]>([]);
  const [keyBusy, setKeyBusy] = useState(false);
  const [doctorKeyframes, setDoctorKeyframes] = useState<DoctorKeyframe[]>([]);
  const [activeDoctorKeyframeId, setActiveDoctorKeyframeId] = useState<string | null>(null);
  const [analysisContourUnrefined, setAnalysisContourUnrefined] = useState(false);
  const [assistOverlayOpen, setAssistOverlayOpen] = useState(false);
  const [propagateToKeyframesBusy, setPropagateToKeyframesBusy] = useState(false);
  const [polygonDraft, setPolygonDraft] = useState<number[][]>([]);
  const doctorKeyframeSessionRef = useRef(0);
  const doctorKeyframesRef = useRef<DoctorKeyframe[]>([]);
  const activeDoctorKeyframeIdRef = useRef<string | null>(null);
  const lastAutoPropagateSigRef = useRef('');
  const selectDoctorKeyframeRef = useRef<(kf: DoctorKeyframe) => void | Promise<void>>(() => undefined);
  const requireOpenKeyframeForBoxRef = useRef<() => boolean>(() => true);
  const persistOpenKeyframeContoursRef = useRef<(opts?: { refined?: boolean; clearWall?: boolean; refOnly?: boolean }) => void>(() => undefined);
  const clearKeyframeOverlayRef = useRef<() => void>(() => undefined);
  const maybeAutoPropagateRef = useRef<(sourceId: string) => void>(() => undefined);
  const runPropagateToOtherKeyframesRef = useRef<(opts?: { sourceId?: string; auto?: boolean }) => Promise<void>>(async () => undefined);
  const [pendingOpenVideoSam, setPendingOpenVideoSam] = useState(false);
  const [pendingKeyframeRequest, setPendingKeyframeRequest] = useState(false);
  /** Freeze display frame while editing vertices / after SAM — prevents click refresh flicker. */
  const [frameFrozen, setFrameFrozen] = useState(false);
  const [propagateBusy, setPropagateBusy] = useState(false);
  const [propagateProgress, setPropagateProgress] = useState<string | null>(null);
  const [videoFrameOverrides, setVideoFrameOverrides] = useState<VideoMaskFrameOverride[]>([]);
  const [frameDataUrl, setFrameDataUrl] = useState<string | null>(null);
  const [layerResult, setLayerResult] = useState<LayerAnalyzeResult | null>(null);
  const [wallAnalysisOpen, setWallAnalysisOpen] = useState(false);
  const [wallDockEl, setWallDockEl] = useState<HTMLElement | null>(null);
  const [viewFocusBox, setViewFocusBox] = useState<ViewFocusBox | null>(null);
  const [viewFocusMode, setViewFocusMode] = useState<ViewFocusMode | null>(null);
  const [viewZoom, setViewZoom] = useState(1);
  const [viewCenter, setViewCenter] = useState<{ x: number; y: number } | null>(null);
  /** Mouse-follow circular magnifier (meeting B6); position kept in a ref to avoid React churn. */
  const [magnifierOn, setMagnifierOn] = useState(false);
  const magnifierPosRef = useRef<{ cx: number; cy: number; ix: number; iy: number } | null>(null);
  const viewZoomRef = useRef(1);
  const viewCenterRef = useRef<{ x: number; y: number } | null>(null);
  const viewPanDragRef = useRef<{ x: number; y: number; cx: number; cy: number } | null>(null);
  const [layerPick, setLayerPick] = useState<{ x: number; y: number } | null>(null);
  const [undoLen, setUndoLen] = useState(0);
  const [hasOriginal, setHasOriginal] = useState(false);
  const trackingClientIdRef = useRef(`tab_${Math.random().toString(36).slice(2)}`);
  const trackingSessionId = useMemo(() => {
    if (mediaMode !== 'video' || !videoUrl || !patient) return '';
    const raw = `${trackingClientIdRef.current}__${patient.patient_id || patient.id}__${videoUrl}`;
    return raw.replace(/[^A-Za-z0-9_-]+/g, '_').slice(0, 160);
  }, [mediaMode, patient, videoUrl]);

  useEffect(() => {
    if (!inline || patient?.phase !== 'reader_v150') return;
    setOpen(true);
    setPendingOpenVideoSam(true);
    setMediaMode('video');
    setMode('sam');
    setSimpleToolsOpen(true);
    setViewFocusBox(null);
    setViewFocusMode(null);
    viewZoomRef.current = 1;
    viewCenterRef.current = null;
    setViewZoom(1);
    setViewCenter(null);
    setAdjacentPair(null);
    setWallEchoClarify(null);
  }, [inline, patient?.id, patient?.phase]);

  const canvasRef = useRef<HTMLCanvasElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const imgRef = useRef<HTMLImageElement | null>(null);
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const trackBusyRef = useRef(false);
  const lastTrackAtRef = useRef(0);
  const pointsRef = useRef<number[][]>([]);
  // Keep the latest successful model contour available to redraw callbacks.
  // Video pause/resize callbacks can briefly run with an older React closure.
  const generatedLesionRef = useRef<number[][]>([]);
  const generatedLesionPatientRef = useRef<string | null>(null);
  const initializedPatientRef = useRef<string | null>(null);
  const initializedLumenPatientRef = useRef<string | null>(null);
  const contourInteractionRef = useRef(false);
  const wallPointsRef = useRef<number[][]>([]);
  const wallExtensionMaskRef = useRef<boolean[]>([]);
  const wallPickModeRef = useRef(false);
  const wallPickFlanksRef = useRef<number[][]>([]);
  const wallPaintModeRef = useRef(false);
  const wallPaintStrokeRef = useRef<number[][] | null>(null);
  const wallLayerReadoutRef = useRef<WallLayerReadout | null>(null);
  const wallLayerBandsRef = useRef<number[][][]>([]);
  const wallLayerImaginaryRef = useRef<boolean[][]>([]);
  const dragIndexRef = useRef<number | null>(null);
  const dragLayerRef = useRef<DragLayer | null>(null);
  const dragBandIndexRef = useRef<number | null>(null);
  const dragSoftRef = useRef(true);
  const frameFrozenRef = useRef(false);
  const videoFrameOverridesRef = useRef<VideoMaskFrameOverride[]>([]);
  const captureCanvasRef = useRef<HTMLCanvasElement | null>(null);
  const undoStackRef = useRef<Array<{
    lesion: number[][];
    wall: number[][];
    lumen: number[][];
    lumenBox: LumenBBox | null;
    extras: number[][][];
  }>>([]);
  const originalRef = useRef<{ lesion: number[][]; wall: number[][]; lumen: number[][] } | null>(null);
  const sculptLayerRef = useRef<'lesion' | 'lumen'>('lumen');
  const playbackRafRef = useRef<number | null>(null);
  const lastPolyClickRef = useRef<{ t: number; pt: number[] } | null>(null);
  const applyAreaKeyframesRef = useRef<(frames: VideoMaskFrameOverride[]) => Promise<void>>(async () => {});
  const playbackUiAtRef = useRef(0);
  const playbackStateAtRef = useRef(0);
  const autoplayAttemptRef = useRef('');
  const scrubbingRef = useRef(false);
  const scrubPreviewRafRef = useRef<number | null>(null);
  const lastScrubRedrawAtRef = useRef(0);
  const videoProgressRefs = useRef<Array<HTMLDivElement | null>>([]);
  const pendingScrubTimeRef = useRef<number | null>(null);
  const scrubSeekRafRef = useRef<number | null>(null);
  const lastScrubSeekAtRef = useRef(0);
  const scrubSeekTimerRef = useRef<number | null>(null);
  const videoTimeLabelRefs = useRef<Array<HTMLSpanElement | null>>([]);
  const taskProgressStartedAtRef = useRef<number | null>(null);
  const [taskElapsedSec, setTaskElapsedSec] = useState(0);
  const predictKeyframesRef = useRef<(candidates: KeyframeCandidate[]) => Promise<void>>(async () => {});
  const reportEvidenceGenerationRef = useRef(0);
  const runLesionModelRef = useRef<
    (
      imgPt: number[] | null,
      box: { x1: number; y1: number; x2: number; y2: number } | null,
      clicks: Array<{ x: number; y: number; label: 'positive' | 'negative' }>,
      modelOverride?: LesionSegmentationModel,
    ) => Promise<number[][] | null>
  >(async () => null);
  const samAbortRef = useRef<AbortController | null>(null);
  const samGenRef = useRef(0);
  const draggingRef = useRef(false);
  const samBusyRef = useRef(false);
  const samClicksRef = useRef<Array<{ x: number; y: number; label: 'positive' | 'negative' }>>([]);
  const promptStrokesRef = useRef<ActiveSamStroke[]>([]);
  const activePromptStrokeRef = useRef<ActiveSamStroke | null>(null);
  const pendingPromptPointRef = useRef<number[] | null>(null);
  const promptStrokeRafRef = useRef<number | null>(null);
  const samBoxDragRef = useRef<{ x0: number; y0: number; x1: number; y1: number } | null>(null);
  const contourPrepActionsRef = useRef<string[]>([]);
  const nnInteractiveSessionRef = useRef<NnInteractiveSessionState>({
    key: '',
    id: '',
    initialized: false,
  });
  const savingRef = useRef(false);
  const persistChainRef = useRef<Promise<boolean>>(Promise.resolve(true));
  const maskAuditSessionRef = useRef('');
  const maskAuditSequenceRef = useRef(0);
  const workflowTraceRef = useRef<WorkflowTraceStep[]>([]);
  const canvasWorkflowLabelRef = useRef(false);
  const maskAuditRef = useRef<
    (eventType: MaskAuditEventType, payload: Record<string, unknown>) => void
  >(() => {});
  const persistOverrideRef = useRef<
    (action: string, options?: PersistOverrideOptions) => Promise<boolean>
  >(async () => false);
  const persistLumenOverrideRef = useRef<(silent?: boolean) => Promise<boolean>>(async () => false);
  const nnInteractiveRequestRef = useRef(0);
  const nnInteractiveAbortRef = useRef<AbortController | null>(null);
  const lumenBoxRef = useRef<LumenBBox | null>(null);
  const lumenPolygonRef = useRef<number[][]>([]);
  const lumenBoxDragRef = useRef<{
    handle: LumenBoxHandle;
    start: LumenBBox;
    origin: number[];
  } | null>(null);
  const lumenBoxFreshDrawRef = useRef(false);
  const polyMoveRef = useRef<{ layer: DragLayer; start: number[][]; origin: number[] } | null>(null);
  const lumenPaintStrokeRef = useRef<number[][] | null>(null);
  const lumenPaintBaseRef = useRef<number[][] | null>(null);
  const pendingDragPtRef = useRef<number[] | null>(null);
  const dragRafRef = useRef<number | null>(null);
  const paintRafRef = useRef<number | null>(null);
  const paintRadiusRef = useRef(16);
  paintRadiusRef.current = paintRadius;
  const wallBrushRadiusRef = useRef(8);
  wallBrushRadiusRef.current = wallBrushRadius;
  const wallLayerTargetRef = useRef<WallLayerTarget>(1);
  wallLayerTargetRef.current = wallLayerTarget;
  const analysisFocusModeRef = useRef(false);
  analysisFocusModeRef.current = analysisFocusMode;
  const analysisFocusPointsRef = useRef<number[][]>([]);
  analysisFocusPointsRef.current = analysisFocusPoints;
  const wallVisibilityRef = useRef<WallVisibility>('clear');
  wallVisibilityRef.current = wallVisibility;
  const serosaAnchorModeRef = useRef<SerosaAnchorMode>('bilateral');
  serosaAnchorModeRef.current = serosaAnchorMode;
  const extraLesionPolygonsRef = useRef<number[][][]>([]);
  extraLesionPolygonsRef.current = extraLesionPolygons;
  const keepExtraLesionRef = useRef(false);
  keepExtraLesionRef.current = keepExtraLesion;
  const persistCaseDraftRef = useRef<(patch: Record<string, unknown>) => void>(() => undefined);
  persistCaseDraftRef.current = (patch) => {
    if (!accountReaderId || !patient?.id) return;
    void fetch('/api/reader/case-state', {
      method: 'PUT',
      headers: authHeaders({ 'Content-Type': 'application/json' }),
      body: JSON.stringify({
        account_id: accountReaderId,
        case_id: patient.id,
        patient_id: patient.patient_id,
        study_mode: patient.study_mode || undefined,
        progress: 'in_progress',
        ...patch,
      }),
    }).catch(() => {});
  };
  const adjacentPairRef = useRef<AdjacentPair | null>(null);
  adjacentPairRef.current = adjacentPair;
  const wallEchoClarifyRef = useRef<WallEchoClarify | null>(null);
  wallEchoClarifyRef.current = wallEchoClarify;
  const videoFpsRef = useRef(DEFAULT_CINE_FPS);
  videoFpsRef.current = videoFps;
  const lumenSculptModeRef = useRef<LumenSculptMode | null>(null);
  lumenSculptModeRef.current = lumenSculptMode;
  const paintCursorRef = useRef<number[] | null>(null);

  const suggestLayersFromAdjacentLock = useCallback((pair: AdjacentPair) => {
    const layers = pairMeta(pair).layers;
    if (wallPointsRef.current.length >= 3) {
      if (wallLayerTargetRef.current !== layers) {
        setMessage(zh
          ? `已锁 ${pairMeta(pair).zh}。请画${anatomyTargetMeta(layers).lineZh}；您已画过，目标仍是${anatomyTargetMeta(wallLayerTargetRef.current).shortZh}`
          : `Locked ${pairMeta(pair).en}. Draw the ${anatomyTargetMeta(layers).lineEn}; painted trajectory kept at ${anatomyTargetMeta(wallLayerTargetRef.current).shortEn}`);
      }
      return;
    }
    setWallLayerTarget(layers);
    wallLayerTargetRef.current = layers;
    persistCaseDraftRef.current({ wall_target_layers: layers });
  }, [zh]);

  const applyAdjacentLock = useCallback((pair: AdjacentPair | null, source = 'overlay') => {
    const before = adjacentPairRef.current;
    setAdjacentPair(pair);
    adjacentPairRef.current = pair;
    if (pair) suggestLayersFromAdjacentLock(pair);
    recordOpRef.current('adjacent_lock', {
      op: 'adjacent_lock',
      value: pair || '',
      after_value: pair || '',
      before_value: before || '',
      layer: pair ? String(pairMeta(pair).layers) : null,
      source,
    }, {
      page: 'workbench',
    });
    window.dispatchEvent(new CustomEvent(ADJACENT_LOCK_EVENT, {
      detail: { pair, source } satisfies AdjacentLockEventDetail,
    }));
    if (source !== 'restore') persistCaseDraftRef.current({ adjacent_lock: pair });
  }, [suggestLayersFromAdjacentLock]);

  useEffect(() => {
    const onLock = (event: Event) => {
      const detail = (event as CustomEvent<AdjacentLockEventDetail>).detail;
      if (!detail || detail.source === 'overlay') return;
      setAdjacentPair(detail.pair);
      adjacentPairRef.current = detail.pair;
      if (detail.pair) suggestLayersFromAdjacentLock(detail.pair);
    };
    window.addEventListener(ADJACENT_LOCK_EVENT, onLock);
    return () => window.removeEventListener(ADJACENT_LOCK_EVENT, onLock);
  }, [suggestLayersFromAdjacentLock]);

  useEffect(() => {
    const onScreen = (event: Event) => {
      const detail = (event as CustomEvent<DepthScreenEventDetail>).detail;
      if (!detail?.screen) return;
      const next = suggestedAnatomyFromScreen(detail.screen);
      if (wallPointsRef.current.length >= 3) return;
      setWallLayerTarget(next);
      wallLayerTargetRef.current = next;
      persistCaseDraftRef.current({ wall_target_layers: next });
    };
    window.addEventListener(DEPTH_SCREEN_EVENT, onScreen);
    return () => window.removeEventListener(DEPTH_SCREEN_EVENT, onScreen);
  }, []);

  useEffect(() => {
    if (!simpleVideoMode) return;
    window.dispatchEvent(new CustomEvent(WALL_ASSIST_DRAFT_EVENT, {
      detail: {
        targetLayers: wallLayerTarget,
        visibility: wallVisibility,
        anchorMode: serosaAnchorMode,
        focusCount: analysisFocusPoints.length,
        ticks: wallLayerReadout?.ticks,
        interrupts: wallLayerReadout?.interrupts,
        noteZh: wallLayerReadout?.noteZh,
        noteEn: wallLayerReadout?.noteEn,
        echoPatternZh: wallEchoClarify?.patternZh,
        echoPatternEn: wallEchoClarify?.patternEn,
        echoNoteZh: wallEchoClarify?.noteZh,
        echoNoteEn: wallEchoClarify?.noteEn,
        keyframeCount: doctorKeyframes.length,
        keyframes: doctorKeyframes.map((kf) => ({
          timeSec: kf.timeSec,
          interrupts: kf.wallLayerReadout?.interrupts,
          ticks: kf.wallLayerReadout?.ticks,
        })),
      },
    }));
  }, [analysisFocusPoints.length, doctorKeyframes, serosaAnchorMode, simpleVideoMode, wallEchoClarify, wallLayerReadout, wallLayerTarget, wallVisibility]);

  const recordDoctorOp = useCallback((
    eventType: string,
    payload: Record<string, unknown>,
  ) => {
    const videoTimeSec = videoRef.current?.currentTime ?? null;
    const knownTrace = [
      'lumen_edit', 'lesion_edit', 'wall_edit', 'contour_drag', 'lumen_paint',
      'tool_switch', 'keyframe_mark', 'polygon_edit',
      'cine_play', 'cine_pause', 'cine_scrub_start', 'cine_scrub', 'cine_scrub_end',
      'cine_frame_step', 'frame_freeze', 'zoom_roi', 'zoom_overlap',
      'layer_pick', 'layer_switch',
    ].includes(eventType);
    if (knownTrace) {
      viewingTraceRef.current(eventType as 'lumen_edit' | 'lesion_edit' | 'wall_edit' | 'contour_drag' | 'lumen_paint' | 'tool_switch' | 'keyframe_mark' | 'polygon_edit' | 'cine_play' | 'cine_pause' | 'cine_scrub_start' | 'cine_scrub' | 'cine_scrub_end' | 'cine_frame_step' | 'frame_freeze' | 'zoom_roi' | 'zoom_overlap' | 'layer_pick' | 'layer_switch', {
        video_time_sec: typeof payload.video_time_sec === 'number' ? payload.video_time_sec : videoTimeSec,
        layer: (payload.layer as 'lesion' | 'lumen' | 'wall' | null) || null,
        point_count: typeof payload.point_count === 'number' ? payload.point_count : null,
        tool: typeof payload.tool === 'string' ? payload.tool : null,
        op: typeof payload.op === 'string' ? payload.op : null,
        radius: typeof payload.radius === 'number' ? payload.radius : null,
        keyframe_id: typeof payload.keyframe_id === 'string' ? payload.keyframe_id : null,
        image_x: typeof payload.image_x === 'number' ? payload.image_x : null,
        image_y: typeof payload.image_y === 'number' ? payload.image_y : null,
        playing: typeof payload.playing === 'boolean' ? payload.playing : null,
        frozen: typeof payload.frozen === 'boolean' ? payload.frozen : null,
        step: typeof payload.step === 'number' ? payload.step : null,
        scale: typeof payload.scale === 'number' ? payload.scale : null,
      });
    }
    maskAuditRef.current('mask_event', {
      operation: String(payload.operation || eventType),
      outcome: String(payload.outcome || payload.status || 'completed'),
      source: 'doctor',
      frame_time_sec: videoTimeSec,
      input: payload,
    });
    recordOpRef.current(eventType, {
      ...payload,
      video_time_sec: typeof payload.video_time_sec === 'number' ? payload.video_time_sec : videoTimeSec,
      op: typeof payload.op === 'string' ? payload.op : (typeof payload.operation === 'string' ? payload.operation : eventType),
    }, {
      caseId: patient?.id || patient?.patient_id || undefined,
      patientId: patient?.patient_id || undefined,
      page: 'workbench',
    });
  }, [patient?.id, patient?.patient_id]);
  const recordDoctorOpRef = useRef(recordDoctorOp);
  recordDoctorOpRef.current = recordDoctorOp;
  // Keep playback listeners attached while React redraws the canvas or tracks a frame.
  // Re-running the source effect on every state change would call video.load() and pause playback.
  const redrawRef = useRef<() => void>(() => {});
  const maybeTrackWhilePlayingRef = useRef<() => Promise<void>>(async () => {});
  const trackOnPlayRef = useRef(false);
  useEffect(() => {
    if (dragIndexRef.current !== null && dragLayerRef.current === 'lesion') return;
    pointsRef.current = points;
  }, [points]);
  useEffect(() => {
    window.dispatchEvent(new CustomEvent('gastric:lesion-ready', {
      detail: { ready: points.length >= 3 },
    }));
  }, [points.length, patient?.id]);
  useEffect(() => () => {
    window.dispatchEvent(new CustomEvent('gastric:lesion-ready', { detail: { ready: false } }));
  }, [patient?.id]);
  useEffect(() => {
    promptStrokesRef.current = promptStrokes;
  }, [promptStrokes]);
  useEffect(() => {
    if (dragIndexRef.current !== null && dragLayerRef.current === 'wall') return;
    wallPointsRef.current = wallPoints;
  }, [wallPoints]);
  useEffect(() => {
    if (dragIndexRef.current !== null && dragLayerRef.current === 'band') return;
    wallLayerBandsRef.current = wallLayerBands;
    wallLayerImaginaryRef.current = wallLayerImaginary;
  }, [wallLayerBands, wallLayerImaginary]);
  useEffect(() => {
    wallPickModeRef.current = wallPickMode;
  }, [wallPickMode]);
  useEffect(() => {
    wallPickFlanksRef.current = wallPickFlanks;
  }, [wallPickFlanks]);
  useEffect(() => {
    wallPaintModeRef.current = wallPaintMode;
  }, [wallPaintMode]);
  useEffect(() => {
    lumenBoxRef.current = lumenBox;
  }, [lumenBox]);
  useEffect(() => {
    if (dragIndexRef.current !== null && dragLayerRef.current === 'lumen') return;
    lumenPolygonRef.current = lumenPolygon;
  }, [lumenPolygon]);
  useEffect(() => {
    dragIndexRef.current = dragIndex;
  }, [dragIndex]);
  useEffect(() => {
    dragLayerRef.current = dragLayer;
  }, [dragLayer]);
  useEffect(() => {
    frameFrozenRef.current = frameFrozen;
  }, [frameFrozen]);
  useEffect(() => {
    trackOnPlayRef.current = trackOnPlay;
  }, [trackOnPlay]);
  useEffect(() => {
    if (!isPlaying) return;
    setViewFocusBox(null);
    setViewFocusMode(null);
  }, [isPlaying]);

  useEffect(() => {
    if (!patient?.id) {
      maskAuditSessionRef.current = '';
      maskAuditSequenceRef.current = 0;
      workflowTraceRef.current = [];
      maskAuditRef.current = () => {};
      return;
    }
    const params = typeof window !== 'undefined'
      ? new URLSearchParams(window.location.search)
      : null;
    const sessionId = `mask_${patient.id}_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
    const caseId = patient.id;
    const patientId = patient.patient_id;
    const readerId = accountReaderId || params?.get('reader_id') || 'workbench_reader';
    const round = params?.get('round') || 'round2';
    maskAuditSessionRef.current = sessionId;
    maskAuditSequenceRef.current = 0;
    workflowTraceRef.current = [];
    maskAuditRef.current = (eventType, payload) => {
      if (maskAuditSessionRef.current !== sessionId) return;
      const eventId = `${sessionId}:${++maskAuditSequenceRef.current}:${eventType}`;
      const operation = String(payload.operation || eventType);
      const outcome = String(payload.outcome || 'completed');
      const workflowStep: WorkflowTraceStep = {
        trace_id: String(payload.trace_id || eventId),
        step_id: operation,
        action: operation,
        status: outcome === 'error' ? 'error' : outcome === 'started' ? 'started' : 'completed',
        source: payload.source === 'doctor' || payload.source === 'doctor_workflow' || operation.includes('workflow')
          ? 'doctor'
          : operation.includes('segmentation') || operation.includes('detection') || operation.includes('propagation')
            ? 'model'
            : 'system',
        frame_time_sec: typeof payload.frame_time_sec === 'number' ? payload.frame_time_sec : null,
        input: payload.input && typeof payload.input === 'object' ? payload.input as Record<string, unknown> : undefined,
        output: payload.output && typeof payload.output === 'object' ? payload.output as Record<string, unknown> : undefined,
        error: typeof payload.error === 'string' ? payload.error : undefined,
        recorded_at: new Date().toISOString(),
      };
      workflowTraceRef.current = [...workflowTraceRef.current, workflowStep].slice(-160);
      onWorkflowStep?.(workflowStep);
      void fetch('/api/reader-audit/events', {
        method: 'POST',
        headers: authHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({
          event_id: eventId,
          event_type: eventType,
          session_id: sessionId,
          case_id: caseId,
          reader_id: readerId,
          round,
          patient_id: patientId,
          payload: {
            component: 'InteractiveSegPanel',
            ...payload,
          },
          client_recorded_at: new Date().toISOString(),
        }),
        keepalive: true,
      }).catch(() => {
        // Audit recording must not interrupt the reading workflow.
      });
    };
    return () => {
      maskAuditRef.current = () => {};
    };
  }, [accountReaderId, authHeaders, onWorkflowStep, patient?.id, patient?.patient_id]);

  useEffect(() => {
    const video = videoRef.current;
    if (playbackRafRef.current !== null) {
      cancelAnimationFrame(playbackRafRef.current);
      playbackRafRef.current = null;
    }
    video?.pause();
    if (video) {
      video.removeAttribute('src');
      video.load();
    }
    setIsPlaying(false);
    autoplayAttemptRef.current = '';
    setVideoTime(0);
    setVideoDuration(0);
    setVideoUrl('');
    setVideos([]);
    setImgLoaded(false);
  }, [patient?.id]);

  const snapshotOriginal = useCallback((lesion: number[][], wall: number[][]) => {
    originalRef.current = {
      lesion: clonePoly(lesion),
      wall: clonePoly(wall),
      lumen: clonePoly(lumenPolygonRef.current),
    };
    undoStackRef.current = [];
    setUndoLen(0);
    setHasOriginal(true);
  }, []);

  const pushEditUndo = useCallback(() => {
    undoStackRef.current.push({
      lesion: clonePoly(pointsRef.current),
      wall: clonePoly(wallPointsRef.current),
      lumen: clonePoly(lumenPolygonRef.current),
      lumenBox: lumenBoxRef.current ? { ...lumenBoxRef.current } : null,
      extras: extraLesionPolygonsRef.current.map((poly) => clonePoly(poly)),
    });
    if (undoStackRef.current.length > 40) undoStackRef.current.shift();
    setUndoLen(undoStackRef.current.length);
  }, []);

  const undoEdit = useCallback(() => {
    const prev = undoStackRef.current.pop();
    if (!prev) return;
    pointsRef.current = prev.lesion;
    wallPointsRef.current = prev.wall;
    lumenPolygonRef.current = prev.lumen;
    lumenBoxRef.current = prev.lumenBox;
    extraLesionPolygonsRef.current = prev.extras || [];
    setPoints(prev.lesion);
    setWallPoints(prev.wall);
    setLumenPolygon(prev.lumen);
    setLumenBox(prev.lumenBox);
    setExtraLesionPolygons(prev.extras || []);
    setUndoLen(undoStackRef.current.length);
    recordDoctorOp('contour_drag', {
      layer: prev.lumen.length ? 'lumen' : 'lesion',
      operation: 'doctor_undo',
      tool: 'undo',
      point_count: prev.lesion.length,
    });
    void persistOverrideRef.current('doctor_undo', { silent: true });
    setMessage(zh ? '已撤销上一步轮廓编辑' : 'Undid last contour edit');
  }, [recordDoctorOp, zh]);

  const restoreOriginal = useCallback(() => {
    const orig = originalRef.current;
    if (!orig) return;
    pushEditUndo();
    pointsRef.current = clonePoly(orig.lesion);
    wallPointsRef.current = clonePoly(orig.wall);
    lumenPolygonRef.current = clonePoly(orig.lumen);
    setPoints(clonePoly(orig.lesion));
    setWallPoints(clonePoly(orig.wall));
    setLumenPolygon(clonePoly(orig.lumen));
    recordDoctorOp('contour_drag', {
      layer: 'lesion',
      operation: 'doctor_restore_original',
      tool: 'restore',
      point_count: orig.lesion.length,
    });
    void persistOverrideRef.current('doctor_restore_original', { silent: true });
    setMessage(zh ? '已恢复分割原始轮廓' : 'Restored original SAM/LabelMe contour');
  }, [pushEditUndo, recordDoctorOp, zh]);

  const activePoints = activeLayer === 'wall' ? wallPoints : points;
  const historyPreview = historyPreviewId
    ? maskHistory.find((entry) => entry.id === historyPreviewId) || null
    : null;

  useEffect(() => {
    const patientKey = patient ? `${patient.id}:${patient.patient_id}` : null;
    const patientChanged = initializedPatientRef.current !== patientKey;
    if (patientChanged) {
      initializedPatientRef.current = patientKey;
      generatedLesionPatientRef.current = patientKey;
      generatedLesionRef.current = [];
      contourInteractionRef.current = false;
      lastCompleteMaskSigRef.current = '';
      setCompleteMaskAutosaved(false);
    }
    if (!patientChanged && contourInteractionRef.current) return;
    if (!patient) {
      setSamReport(null);
      setPoints([]);
      setWallPoints([]);
      samClicksRef.current = [];
      setSamClicks([]);
      promptStrokesRef.current = [];
      activePromptStrokeRef.current = null;
      setPromptStrokes([]);
      setActivePromptStroke(null);
      nnInteractiveAbortRef.current?.abort();
      nnInteractiveAbortRef.current = null;
      nnInteractiveRequestRef.current += 1;
      setNnInteractiveBusy(false);
      videoFrameOverridesRef.current = [];
      setVideoFrameOverrides([]);
      setImgLoaded(false);
      pointsRef.current = [];
      wallPointsRef.current = [];
      wallExtensionMaskRef.current = [];
      setWallExtensionNote('');
      setWallExtensionStats(null);
      originalRef.current = null;
      setHasOriginal(false);
      setViewFocusBox(null);
      setViewFocusMode(null);
      return;
    }
    if (!(inline && patient.phase === 'reader_v150')) setOpen(false);
    setSamReport(null);
    setDinoResult(null);
    setDinoDockOpen(false);
    dinoCacheRef.current.clear();
    setSegmentationModelResult(null);
    setSegmentationBusy(false);
    onDinoFeatures?.(null);
    samClicksRef.current = [];
    setSamClicks([]);
    setSimplePromptMode('box');
    armLesionBox(false);
    setActiveSamPromptLabel('positive');
    setSimpleEditMode(false);
    setNnInteractiveBusy(false);
    setNnInteractiveClicks([]);
    nnInteractiveAbortRef.current?.abort();
    nnInteractiveAbortRef.current = null;
    nnInteractiveRequestRef.current += 1;
    setPromptStrokes([]);
    promptStrokesRef.current = [];
    activePromptStrokeRef.current = null;
    setActivePromptStroke(null);
    setNnInteractiveMode(false);
    setNnInteractiveTarget('lesion');
    nnInteractiveSessionRef.current = { key: '', id: '', initialized: false };
    setSimpleToolsOpen(true);
    setSimplePromptBox(null);
    setLumenEditMode(false);
    pointsRef.current = [];
    wallPointsRef.current = [];
    originalRef.current = null;
    setPoints([]);
    setWallPoints([]);
    setHasOriginal(false);
    setUndoLen(0);
    videoFrameOverridesRef.current = [];
    setVideoFrameOverrides([]);
    setKeyCandidates([]);
    setPendingKeyframeRequest(false);
    setTrackingPrepared(false);
    setPrecomputeBusy(false);
    setPrecomputeProgress(null);
    setRoiMode('predicted');
    if (patientChanged) return;
    if (override?.mask_polygon?.length || override?.wall_polygon?.length) {
      const lesion = override?.mask_polygon?.length
        ? prepareEditableContour(
          override.mask_polygon.map((p) => [Number(p[0]), Number(p[1])]),
          LESION_CONTOUR_MAX_POINTS,
        )
        : [];
      const wall = override?.wall_polygon?.length
        ? prepareEditableContour(
          override.wall_polygon.map((p) => [Number(p[0]), Number(p[1])]),
          WALL_CONTOUR_MAX_POINTS,
        )
        : [];
      setPoints(lesion);
      setWallPoints(wall);
      snapshotOriginal(lesion, wall);
      return;
    }
  }, [inline, patient, patient?.id, patient?.patient_id, patient?.phase, override?.updated_at, override?.mask_polygon, override?.wall_polygon, snapshotOriginal, onDinoFeatures]);

  useEffect(() => {
    setHistoryOpen(false);
    setHistoryBusy(false);
    setMaskHistory([]);
    setHistoryPreviewId(null);
  }, [patient?.id]);

  useEffect(() => {
    const patientKey = patient ? `${patient.id}:${patient.patient_id}` : null;
    const patientChanged = initializedLumenPatientRef.current !== patientKey;
    if (patientChanged) {
      initializedLumenPatientRef.current = patientKey;
      setLumenBox(null);
      setLumenPolygon([]);
      setLumenConfidence(null);
      setLumenEditMode(false);
      setLumenResultMeta(null);
      lumenBoxRef.current = null;
      lumenPolygonRef.current = [];
      return;
    }
    if (!patient) {
      setLumenBox(null);
      setLumenPolygon([]);
      setLumenConfidence(null);
      setLumenEditMode(false);
      setLumenResultMeta(null);
      return;
    }
    setLumenBox(lumenOverride?.lumen_bbox ? normalizeLumenBBox(lumenOverride.lumen_bbox) : null);
    setLumenPolygon(lumenOverride?.lumen_polygon ? clonePoly(lumenOverride.lumen_polygon) : []);
    setLumenConfidence(lumenOverride?.lumen_confidence ?? null);
    setLumenEditMode(false);
    setViewFocusBox(null);
    setViewFocusMode(null);
    setLumenResultMeta(lumenOverride ? {
      detector_backend_id: lumenOverride.detector_backend_id,
      sam_backend_id: lumenOverride.sam_backend_id,
      sam_score: lumenOverride.sam_score,
      source: lumenOverride.source,
    } : null);
  }, [patient, patient?.id, patient?.patient_id, lumenOverride, lumenOverride?.updated_at, lumenOverride?.lumen_bbox, lumenOverride?.lumen_polygon, lumenOverride?.lumen_confidence, lumenOverride?.detector_backend_id, lumenOverride?.sam_backend_id, lumenOverride?.sam_score, lumenOverride?.source]);

  const refreshNnInteractiveStatus = useCallback(async (): Promise<boolean> => {
    try {
      const res = await fetch('/api/agent/nninteractive', { cache: 'no-store' });
      const payload = await res.json() as { available?: boolean };
      const available = payload.available === true;
      setNnInteractiveAvailable(available);
      return available;
    } catch {
      setNnInteractiveAvailable(false);
      return false;
    }
  }, []);

  useEffect(() => {
    void refreshNnInteractiveStatus();
  }, [refreshNnInteractiveStatus]);

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch('/api/agent/sam-interactive');
        const data = await res.json();
        if (!cancelled) setSamAvailable(Boolean(data.available));
      } catch {
        if (!cancelled) setSamAvailable(false);
      }
      // Keep both box-lesion maskers warm so the first drag is not a cold load.
      void fetch('/api/agent/lesion-segmentation', { cache: 'no-store' }).catch(() => undefined);
      void fetch('/api/agent/dino/features', { cache: 'no-store' }).catch(() => undefined);
    })();
    return () => { cancelled = true; };
  }, [open]);

  useEffect(() => {
    if (!open || !patient) return;
    let cancelled = false;
    (async () => {
      // Always resolve from disk index (crop_ui / qualified / public) — no upload.
      const fromPatient = patient.video_urls || [];
      let list = fromPatient;
      // Reader-study media is already case-resolved. Other queues can use the
      // allowlisted patient video catalog, including external centers.
      if (patient.phase !== 'reader_v150') {
        try {
          const res = await fetch(
            `/api/patients/videos?patientId=${encodeURIComponent(patient.patient_id)}&limit=40`,
          );
          const data = await res.json();
          const remote = (data.videos || []) as VideoInfo[];
          if (remote.length) {
            const seen = new Set(list.map((v) => v.url));
            list = [...list, ...remote.filter((v) => !seen.has(v.url))];
          }
        } catch {
          /* keep fromPatient */
        }
      }
      if (cancelled) return;
      setVideos(list);
      setVideoUrl((prev) => {
        if (prev && list.some((v) => v.url === prev)) return prev;
        return list[0]?.url || '';
      });
      if (pendingOpenVideoSam && list.length) {
        setPendingOpenVideoSam(false);
        setVideoUrl(list[0].url);
        setMediaMode('video');
        setMode('sam');
        if (!simpleVideoMode) {
          setMessage(
            zh
              ? `已打开对应视频：${list[0].filename}。空格先暂停，再按一次才标关键帧`
              : `Opened ${list[0].filename}. Space pauses first; press again to mark`,
          );
        }
      } else if (pendingOpenVideoSam && !list.length) {
        setPendingOpenVideoSam(false);
        setMessage(zh ? '未找到该病例对应视频（crop_ui/阅片库）' : 'No matching patient video on disk');
      }
    })();
    return () => { cancelled = true; };
  }, [open, patient?.patient_id, patient?.video_urls, pendingOpenVideoSam, simpleVideoMode, zh]);

  const openPatientVideoSam = useCallback(() => {
    if (!videos.length) {
      setMessage(zh ? '未找到该病例对应视频（crop_ui/阅片库）' : 'No matching patient video on disk');
      return;
    }
    const url = videoUrl || videos[0].url;
    setVideoUrl(url);
    setMediaMode('video');
    setMode('sam');
    if (!simpleVideoMode) {
      setMessage(
        zh
          ? `已打开对应视频：${videos.find((v) => v.url === url)?.filename || 'video'}。空格先暂停，再按一次才标关键帧`
          : `Opened patient video. Space pauses first; press again to mark`,
      );
    }
  }, [simpleVideoMode, videos, videoUrl, zh]);

  const scoreKeyframes = useCallback(async () => {
    if (!videoUrl || keyBusy) return;
    setKeyBusy(true);
    setMessage(zh ? '邻域关键帧打分中…' : 'Scoring neighborhood keyframes…');
    try {
      const res = await fetch('/api/agent/video/keyframes', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          video_url: videoUrl,
          anchor_sec: videoTime,
          window_sec: 2.0,
          top_k: 5,
        }),
      });
      const data = await res.json() as { ok?: boolean; error?: string; keyframes?: KeyframeCandidate[] };
      if (!res.ok || !data.ok) throw new Error(data.error || 'keyframe failed');
      const candidates = (data.keyframes || []).map((candidate) => ({
        ...candidate,
        prediction_status: pointsRef.current.length >= 3 ? 'pending' as const : 'needs_roi' as const,
      }));
      setKeyCandidates(candidates);
      if (pointsRef.current.length < 3) {
        setMessage(
          zh
            ? `已选出 ${candidates.length} 个关键帧；请先框选病灶，再生成对应病灶预测`
            : `${candidates.length} keyframes selected; draw an ROI box first to predict the lesion on each frame`,
        );
      } else {
        await predictKeyframesRef.current(candidates);
      }
    } catch (err) {
      setMessage(err instanceof Error ? err.message : 'keyframe failed');
    } finally {
      setKeyBusy(false);
    }
  }, [keyBusy, videoTime, videoUrl, zh]);

  const applyAreaKeyframesFromFrames = useCallback(async (frames: VideoMaskFrameOverride[]) => {
    const candidates = selectTopAreaKeyframes(frames, 5, 0.5);
    setKeyCandidates(candidates);
    if (!candidates.length) {
      setMessage(
        zh
          ? '跟踪扩散完成，但未能按病灶面积选出关键帧'
          : 'Tracking finished, but no area-based keyframes were selected',
      );
      return;
    }
    setMessage(
      zh
        ? `跟踪完成；算法附带 ${candidates.length} 个面积关键帧（仅辅助）。请医生 scrub 自选关键帧后分析`
        : `Tracking done; ${candidates.length} area keyframes are optional hints — scrub and pick frames yourself for analysis`,
    );
    const video = videoRef.current;
    if (!video?.videoWidth) return;
    const restore = video.currentTime || 0;
    const wasFrozen = frameFrozenRef.current;
    video.pause();
    setFrameFrozen(true);
    frameFrozenRef.current = true;
    try {
      for (const candidate of candidates) {
        await seekVideoForAgent(video, candidate.timestamp_sec);
        const canvas = document.createElement('canvas');
        canvas.width = Math.max(1, Math.round(video.videoWidth / 4));
        canvas.height = Math.max(1, Math.round(video.videoHeight / 4));
        const ctx = canvas.getContext('2d');
        if (!ctx) continue;
        ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
        const thumb = canvas.toDataURL('image/jpeg', 0.72);
        setKeyCandidates((current) => current.map((item) => (
          item.timestamp_sec === candidate.timestamp_sec
            ? { ...item, thumb_url: thumb }
            : item
        )));
      }
    } finally {
      await seekVideoForAgent(video, restore);
      setVideoTime(restore);
      setFrameFrozen(wasFrozen);
      frameFrozenRef.current = wasFrozen;
      redrawRef.current();
    }
  }, [zh]);

  useEffect(() => {
    applyAreaKeyframesRef.current = applyAreaKeyframesFromFrames;
  }, [applyAreaKeyframesFromFrames]);

  useEffect(() => {
    if (!pendingKeyframeRequest || mediaMode !== 'video' || !videoUrl || keyBusy) return;
    setPendingKeyframeRequest(false);
    void scoreKeyframes();
  }, [keyBusy, mediaMode, pendingKeyframeRequest, scoreKeyframes, videoUrl]);

  const dinoCacheKey = useCallback(() => {
    const time = mediaMode === 'video'
      ? Number(videoRef.current?.currentTime ?? videoTime)
      : 0;
    const lesion = pointsRef.current;
    const wall = wallPointsRef.current;
    const tip = (poly: number[][]) => (
      poly.length
        ? `${poly[0][0].toFixed(0)},${poly[0][1].toFixed(0)},${poly[poly.length - 1][0].toFixed(0)}`
        : '0'
    );
    return [
      patient?.patient_id || patient?.id || '',
      time.toFixed(2),
      String(lesion.length),
      String(wall.length),
      tip(lesion),
      tip(wall),
    ].join('|');
  }, [mediaMode, patient?.id, patient?.patient_id, videoTime]);

  useEffect(() => {
    if (!simpleVideoMode) return;
    void fetch('/api/agent/dino/features?load=1', { cache: 'no-store' }).catch(() => undefined);
  }, [simpleVideoMode]);

  const extractDinoFeatures = useCallback(async (opts?: { compact?: boolean }) => {
    if (!patient || dinoBusy) return;
    const compact = Boolean(opts?.compact);
    setDinoBusy(true);
    if (compact) {
      setDinoResult(null);
    } else {
      setMessage(zh ? 'DINO 特征提取中，首次加载可能较慢…' : 'Extracting DINO features; first load may take longer…');
    }
    try {
      const frame = await videoOrImageToSamFrame(
        videoRef.current,
        imgRef.current,
        mediaMode === 'video',
        compact ? 512 : 1024,
      );
      const scale = frame.scale || 1;
      const displayRoi = periLesionRoi({
        lesion: pointsRef.current,
        extras: extraLesionPolygonsRef.current,
        wall: wallPointsRef.current,
        width: videoRef.current?.videoWidth || imgRef.current?.naturalWidth || frame.width,
        height: videoRef.current?.videoHeight || imgRef.current?.naturalHeight || frame.height,
        margin: 48,
      });
      const frameRoi = clampDinoRoiBox(
        scaleDinoRoiBox(displayRoi, scale),
        frame.width,
        frame.height,
      );
      const response = await fetch('/api/agent/dino/features', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          case_id: patient.patient_id,
          frame_time: mediaMode === 'video'
            ? Number(videoRef.current?.currentTime ?? videoTime)
            : 0,
          frame_png_b64: frame.b64,
          image_width: frame.width,
          image_height: frame.height,
          lesion_polygon: pointsRef.current.map((point) => [point[0] * scale, point[1] * scale]),
          wall_polygon: wallPointsRef.current.map((point) => [point[0] * scale, point[1] * scale]),
          roi_bbox: frameRoi,
          layer_index: 11,
          layer_indices: DINO_LAYER_INDICES,
          compact,
        }),
      });
      const payload = await response.json() as { ok?: boolean; result?: DinoFeatureResult; error?: string };
      if (!response.ok || !payload.ok || !payload.result?.available) {
        throw new Error(payload.error || payload.result?.error || 'DINO feature extraction unavailable');
      }
      const cropBox = payload.result.roi_box || frameRoi;
      const sourceLayers = payload.result.layers?.length ? payload.result.layers : [payload.result];
      const layers = compact
        ? sourceLayers
        : await Promise.all(sourceLayers.map((layer) => attachRoiOverlays(layer, cropBox)));
      const next: DinoFeatureResult = {
        ...payload.result,
        ...layers[layers.length - 1],
        layers,
        roi_box: cropBox,
      };
      dinoCacheRef.current.set(dinoCacheKey(), next);
      setDinoResult(next);
      setDinoDockOpen(true);
      setActiveDinoLayer(next.layer_indices?.[next.layer_indices.length - 1] ?? 11);
      onDinoFeatures?.(next);
      if (!compact && displayRoi) {
        setViewFocusBox(displayRoi);
        setViewFocusMode('roi');
      }
      if (!compact) {
        setMessage(
          zh
            ? `已查看 ROI 附近 DINO 层特征：${layers.length} 层（L${(next.layer_indices || DINO_LAYER_INDICES).join(', L')}）。草稿，不定 cT。`
            : `ROI DINO layer features: ${layers.length} layers (L${(next.layer_indices || DINO_LAYER_INDICES).join(', L')}). Draft only.`,
        );
      }
    } catch (error) {
      const failure: DinoFeatureResult = {
        available: false,
        error: error instanceof Error ? error.message : 'DINO feature extraction failed',
      };
      setDinoResult(failure);
      onDinoFeatures?.(failure);
      setMessage(failure.error || 'DINO feature extraction failed');
    } finally {
      setDinoBusy(false);
    }
  }, [dinoBusy, dinoCacheKey, mediaMode, onDinoFeatures, patient, videoTime, zh]);

  const toggleRoiDinoLayers = useCallback(() => {
    if (pointsRef.current.length < 3) {
      setMessage(zh ? '请先框选当前帧病灶，再看 ROI 附近的 DINO 层特征' : 'Box the lesion first, then inspect ROI DINO layers');
      return;
    }
    if (dinoDockOpen) {
      setDinoDockOpen(false);
      return;
    }
    setDinoDockOpen(true);
    const cached = dinoCacheRef.current.get(dinoCacheKey());
    if (cached?.available) {
      setDinoResult(cached);
      return;
    }
    void extractDinoFeatures({ compact: true });
  }, [dinoCacheKey, dinoDockOpen, extractDinoFeatures, zh]);

  const captureFrameDataUrl = useCallback(() => {
    const video = videoRef.current;
    if (mediaMode === 'video' && video && video.videoWidth) {
      const c = document.createElement('canvas');
      c.width = video.videoWidth;
      c.height = video.videoHeight;
      const ctx = c.getContext('2d');
      if (!ctx) return null;
      ctx.drawImage(video, 0, 0);
      const url = c.toDataURL('image/jpeg', 0.92);
      setFrameDataUrl(url);
      return url;
    }
    const img = imgRef.current;
    if (img?.naturalWidth) {
      const c = document.createElement('canvas');
      c.width = img.naturalWidth;
      c.height = img.naturalHeight;
      const ctx = c.getContext('2d');
      if (!ctx) return null;
      ctx.drawImage(img, 0, 0);
      const url = c.toDataURL('image/jpeg', 0.92);
      setFrameDataUrl(url);
      return url;
    }
    return null;
  }, [mediaMode]);

  const frameSize = useMemo(() => {
    const video = videoRef.current;
    if (mediaMode === 'video' && video?.videoWidth) {
      return { width: video.videoWidth, height: video.videoHeight };
    }
    const img = imgRef.current;
    if (img?.naturalWidth) return { width: img.naturalWidth, height: img.naturalHeight };
    return null;
  }, [mediaMode, videoTime, imgLoaded, points.length]);

  useEffect(() => {
    if (!onImagingAssist || points.length < 3 || !frameSize) return;
    onImagingAssist({
      layerResult,
      lesionPolygon: points,
      wallPolygon: wallPoints,
      frameSize,
      lumenBBox: lumenBox,
      lumenPolygon: lumenPolygon.length >= 3 ? lumenPolygon : undefined,
    });
  }, [
    frameSize,
    layerResult,
    lumenBox,
    lumenPolygon,
    onImagingAssist,
    points,
    wallPoints,
  ]);

  const emitReportEvidenceImages = useCallback(async () => {
    const liveFrameDataUrl = frameDataUrl || captureFrameDataUrl();
    if (
      !onReportEvidenceImages
      || !liveFrameDataUrl
      || !frameSize
      || pointsRef.current.length < 3
    ) return;
    const generation = ++reportEvidenceGenerationRef.current;
    const keyframes = keyCandidates
      .filter((candidate) => (
        Boolean(candidate.thumb_url)
        && Array.isArray(candidate.predicted_polygon)
        && candidate.predicted_polygon.length >= 3
      ))
      .map((candidate, index) => ({
        frameDataUrl: candidate.thumb_url as string,
        maskPolygon: candidate.predicted_polygon as number[][],
        frameWidth: candidate.image_width || frameSize.width,
        frameHeight: candidate.image_height || frameSize.height,
        frameTime: candidate.timestamp_sec,
        frameIndex: candidate.frame_index ?? index,
        normalizedMask: true,
        sourceFrameId: candidate.frame_id || `${patient?.id || 'case'}:${candidate.timestamp_sec.toFixed(3)}`,
        sourceVideoUrl: videoUrl || null,
        label: zh
          ? `关键帧 ${index + 1}, t=${candidate.timestamp_sec.toFixed(3)}s, 实际分割`
          : `Key frame ${index + 1}, t=${candidate.timestamp_sec.toFixed(3)}s, actual segmentation`,
      }));
    try {
      const images = await buildReportEvidenceImages({
        current: {
          frameDataUrl: liveFrameDataUrl,
          maskPolygon: pointsRef.current,
          frameWidth: frameSize.width,
          frameHeight: frameSize.height,
          frameTime: mediaMode === 'video' ? videoTime : 0,
        },
        wallPolygon: wallPointsRef.current,
        lumenPolygon: lumenPolygonRef.current,
        lumenBBox: lumenBoxRef.current,
        keyframes,
        zh,
      });
      if (generation === reportEvidenceGenerationRef.current) {
        onReportEvidenceImages(images, patient?.id);
      }
    } catch (error) {
      console.warn('report evidence render failed', error);
      if (generation === reportEvidenceGenerationRef.current) {
        setMessage(zh ? '证据帧渲染失败，请重试勾画或刷新当前帧' : 'Evidence-frame render failed; re-draw or refresh the current frame');
      }
    }
  }, [
    captureFrameDataUrl,
    frameDataUrl,
    frameSize,
    keyCandidates,
    mediaMode,
    onReportEvidenceImages,
    patient?.id,
    videoTime,
    videoUrl,
    zh,
  ]);

  useEffect(() => {
    // frameDataUrl may be null until the first capture; the emitter falls back
    // to a live canvas capture, so gate only on having a drawable contour.
    if (points.length < 3) return;
    if (!frameDataUrl && mediaMode !== 'video' && !imgLoaded) return;
    const timer = window.setTimeout(() => {
      void emitReportEvidenceImages();
    }, 350);
    return () => window.clearTimeout(timer);
  }, [
    emitReportEvidenceImages,
    frameDataUrl,
    imgLoaded,
    keyCandidates,
    lumenBox,
    lumenPolygon,
    mediaMode,
    points,
    wallPoints,
  ]);

  const persistOpenKeyframeContours = useCallback((opts?: { refined?: boolean; clearWall?: boolean; refOnly?: boolean }) => {
    const currentTime = videoRef.current?.currentTime ?? videoTime;
    const open = isDoctorKeyframeOpen(
      doctorKeyframesRef.current,
      activeDoctorKeyframeIdRef.current,
      currentTime,
      false,
    );
    if (!open) return;
    const lesion = pointsRef.current.length >= 3 ? clonePoly(pointsRef.current) : null;
    const extras = extraLesionPolygonsRef.current.filter((poly) => poly.length >= 3).map((poly) => clonePoly(poly));
    const lumen = lumenPolygonRef.current.length >= 3 ? clonePoly(lumenPolygonRef.current) : null;
    const wall = wallPointsRef.current.length >= 3 ? clonePoly(wallPointsRef.current) : null;
    const focus = analysisFocusPointsRef.current.filter((point) => point.length >= 2).map((point) => point.slice());
    const bands = wallLayerBandsRef.current.filter((band) => band.length >= 2).map((band) => clonePoly(band));
    const imaginary = wallLayerImaginaryRef.current.map((mask) => mask.slice());
    const apply = (prev: typeof doctorKeyframesRef.current) => prev.map((kf) => (
      kf.id === open.id
        ? {
            ...kf,
            lesionPolygon: lesion || kf.lesionPolygon,
            extraLesionPolygons: extras.length ? extras : kf.extraLesionPolygons,
            lumenPolygon: lumen || kf.lumenPolygon,
            lumenBox: lumenBoxRef.current || kf.lumenBox,
            wallPolygon: opts?.clearWall ? null : (wall || kf.wallPolygon),
            analysisFocusPoints: opts?.clearWall ? [] : (focus.length ? focus : kf.analysisFocusPoints),
            wallVisibility: wallVisibilityRef.current,
            serosaAnchorMode: serosaAnchorModeRef.current,
            wallLayerReadout: opts?.clearWall ? null : (wallLayerReadoutRef.current || kf.wallLayerReadout),
            wallLayerBands: opts?.clearWall ? [] : (bands.length ? bands : kf.wallLayerBands),
            wallLayerImaginary: opts?.clearWall ? [] : (imaginary.length ? imaginary : kf.wallLayerImaginary),
            segStatus: lesion || (kf.lesionPolygon && kf.lesionPolygon.length >= 3) ? 'ready' : kf.segStatus,
            refined: opts?.refined ?? kf.refined,
          }
        : kf
    ));
    if (opts?.refOnly) {
      doctorKeyframesRef.current = apply(doctorKeyframesRef.current);
      return;
    }
    setDoctorKeyframes((prev) => {
      const next = apply(prev);
      doctorKeyframesRef.current = next;
      return next;
    });
  }, [videoTime]);
  persistOpenKeyframeContoursRef.current = persistOpenKeyframeContours;

  const clearWallDraftOnFrame = useCallback(() => {
    wallPointsRef.current = [];
    wallExtensionMaskRef.current = [];
    setWallPoints([]);
    setWallLayerReadout(null);
    wallLayerReadoutRef.current = null;
    setWallEchoClarify(null);
    setWallLayerBands([]);
    wallLayerBandsRef.current = [];
    setWallLayerImaginary([]);
    wallLayerImaginaryRef.current = [];
    analysisFocusPointsRef.current = [];
    setAnalysisFocusPoints([]);
    wallPaintStrokeRef.current = null;
    setWallPaintStroke([]);
    wallPickFlanksRef.current = [];
    setWallPickFlanks([]);
    persistOpenKeyframeContours({ clearWall: true });
    setMessage(zh ? '已清除本帧胃壁辅助线' : 'Cleared wall guides on this frame');
    redrawRef.current?.();
  }, [persistOpenKeyframeContours, zh]);

  const saveWallDraftOnFrame = useCallback(() => {
    const currentTime = videoRef.current?.currentTime ?? videoTime;
    const open = isDoctorKeyframeOpen(
      doctorKeyframesRef.current,
      activeDoctorKeyframeIdRef.current,
      currentTime,
      false,
    );
    if (!open) {
      setMessage(zh ? '请先停在关键帧上，再保存本帧胃壁线' : 'Pause on a keyframe first, then save the wall line');
      return;
    }
    if (wallPointsRef.current.length < 3 && !wallLayerBandsRef.current.length && !analysisFocusPointsRef.current.length) {
      setMessage(zh ? '本帧还没有可保存的胃壁线' : 'No wall line on this frame to save');
      return;
    }
    persistOpenKeyframeContours({ refined: true });
    setMessage(zh ? '已保存本帧胃壁辅助线' : 'Saved wall guides on this frame');
  }, [persistOpenKeyframeContours, videoTime, zh]);

  useEffect(() => {
    const onOverride = (event: Event) => {
      const layer = Number((event as CustomEvent<WallInterruptOverrideDetail>).detail?.layer);
      const current = wallLayerReadoutRef.current;
      if (!Number.isFinite(layer) || !current?.interrupts?.some((item) => item.layer === layer)) return;
      const interrupts = toggleDoctorInterrupt(current.interrupts, layer);
      const target = wallLayerTargetRef.current;
      const ticks = ticksFromInterrupts(interrupts, target);
      const flipped = interrupts.find((item) => item.layer === layer);
      const next = {
        ...current,
        interrupts,
        ticks,
        noteZh: flipped
          ? `医生已把${flipped.nameZh}改成${verdictLabel(flipped.verdict, true)}。不定 cT。`
          : current.noteZh,
        noteEn: flipped
          ? `Doctor marked ${flipped.nameEn} as ${verdictLabel(flipped.verdict, false)}. Not a definite cT.`
          : current.noteEn,
      };
      setWallLayerReadout(next);
      wallLayerReadoutRef.current = next;
      persistOpenKeyframeContoursRef.current({ refined: true });
      recordDoctorOp('wall_interrupt_override', {
        op: 'wall_interrupt_override',
        layer: String(layer),
        value: flipped?.verdict || (flipped?.interrupted ? 'interrupted' : 'continuous'),
      });
      setMessage(zh
        ? `已按您的确认改成${verdictLabel(flipped?.verdict, true)}（不定 cT）`
        : `Marked ${verdictLabel(flipped?.verdict, false)} from your check (not a definite cT)`);
      redrawRef.current?.();
    };
    window.addEventListener(WALL_INTERRUPT_OVERRIDE_EVENT, onOverride);
    return () => window.removeEventListener(WALL_INTERRUPT_OVERRIDE_EVENT, onOverride);
  }, [recordDoctorOp, zh]);

  const applyPromptMetaLive = useCallback((
    visibility: WallVisibility,
    anchorMode: SerosaAnchorMode,
  ) => {
    setWallVisibility(visibility);
    wallVisibilityRef.current = visibility;
    setSerosaAnchorMode(anchorMode);
    serosaAnchorModeRef.current = anchorMode;
    persistCaseDraftRef.current({
      wall_visibility: visibility,
      serosa_anchor_mode: anchorMode,
    });
    const current = wallLayerReadoutRef.current;
    if (current) {
      const next = applyWallPromptMeta(current, { visibility, anchorMode });
      setWallLayerReadout(next);
      wallLayerReadoutRef.current = next;
      persistOpenKeyframeContoursRef.current({ refined: true });
    }
    redrawRef.current?.();
  }, []);

  useEffect(() => {
    const onMeta = (event: Event) => {
      const detail = (event as CustomEvent<WallPromptMetaDetail>).detail || {};
      const visibility = detail.visibility || wallVisibilityRef.current;
      const anchorMode = detail.anchorMode || serosaAnchorModeRef.current;
      applyPromptMetaLive(visibility, anchorMode);
      recordDoctorOp('wall_prompt_meta', {
        op: 'wall_prompt_meta',
        visibility,
        anchor_mode: anchorMode,
      });
    };
    window.addEventListener(WALL_PROMPT_META_EVENT, onMeta);
    return () => window.removeEventListener(WALL_PROMPT_META_EVENT, onMeta);
  }, [applyPromptMetaLive, recordDoctorOp]);

  const clearKeyframeOverlay = useCallback(() => {
    pointsRef.current = [];
    generatedLesionRef.current = [];
    setPoints([]);
    extraLesionPolygonsRef.current = [];
    setExtraLesionPolygons([]);
    lumenPolygonRef.current = [];
    setLumenPolygon([]);
    lumenBoxRef.current = null;
    setLumenBox(null);
    wallPointsRef.current = [];
    wallExtensionMaskRef.current = [];
    setWallPoints([]);
    setWallLayerReadout(null);
    wallLayerReadoutRef.current = null;
    setWallEchoClarify(null);
    setWallLayerBands([]);
    wallLayerBandsRef.current = [];
    setWallLayerImaginary([]);
    wallLayerImaginaryRef.current = [];
    analysisFocusPointsRef.current = [];
    setAnalysisFocusPoints([]);
    setAnalysisFocusMode(false);
    analysisFocusModeRef.current = false;
    setSimpleEditMode(false);
    setViewFocusBox(null);
    setViewFocusMode(null);
  }, []);
  clearKeyframeOverlayRef.current = clearKeyframeOverlay;

  const markActiveDoctorKeyframeRefined = useCallback(() => {
    if (!activeDoctorKeyframeId) return;
    persistOpenKeyframeContours({ refined: true });
    setAnalysisContourUnrefined(false);
    if (!simpleVideoMode) {
      queueMicrotask(() => maybeAutoPropagateRef.current(activeDoctorKeyframeId));
    }
  }, [activeDoctorKeyframeId, persistOpenKeyframeContours, simpleVideoMode]);

  const markDoctorKeyframeDeepest = useCallback((id: string) => {
    const wasDeepest = doctorKeyframesRef.current.some((kf) => kf.id === id && kf.deepestInvasion);
    const kf = doctorKeyframesRef.current.find((item) => item.id === id);
    setDoctorKeyframes((prev) => {
      const next = toggleDeepestInvasion(prev, id);
      doctorKeyframesRef.current = next;
      return next;
    });
    recordDoctorOp('deepest_frame', {
      operation: wasDeepest ? 'clear_deepest' : 'mark_deepest',
      op: wasDeepest ? 'clear_deepest' : 'mark_deepest',
      keyframe_id: id,
      video_time_sec: kf?.timeSec ?? null,
      status: wasDeepest ? 'cleared' : 'marked',
    });
    if (accountReaderId && patient?.id) {
      void fetch('/api/reader/case-state', {
        method: 'PUT',
        headers: authHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({
          account_id: accountReaderId,
          case_id: patient.id,
          patient_id: patient.patient_id,
          study_mode: patient.study_mode || undefined,
          progress: 'in_progress',
          activity_append: {
            id: `deep_${Date.now().toString(36)}`,
            at: new Date().toISOString(),
            type: 'deepest_frame',
            label_zh: wasDeepest
              ? `取消浸润最深 t=${Number(kf?.timeSec || 0).toFixed(2)}s`
              : `标浸润最深 t=${Number(kf?.timeSec || 0).toFixed(2)}s`,
            label_en: wasDeepest
              ? `Cleared deepest t=${Number(kf?.timeSec || 0).toFixed(2)}s`
              : `Marked deepest t=${Number(kf?.timeSec || 0).toFixed(2)}s`,
            detail: { keyframe_id: id, cleared: wasDeepest, time_sec: kf?.timeSec ?? null },
          },
        }),
      }).catch(() => {});
    }
    setMessage(wasDeepest
      ? (zh ? '已取消浸润最深标记' : 'Cleared deepest-invasion mark')
      : (zh ? '已标为浸润最深关键帧，分析将以此帧为主' : 'Marked as deepest-invasion keyframe; analysis prefers this frame'));
  }, [accountReaderId, authHeaders, patient?.id, patient?.patient_id, patient?.study_mode, recordDoctorOp, zh]);

  const ensureActiveDoctorKeyframeForAnalysis = useCallback(async (opts?: {
    seek?: boolean;
  }): Promise<DoctorKeyframe | null> => {
    if (mediaMode !== 'video') return null;
    if (pointsRef.current.length >= 3) {
      requireOpenKeyframeForBoxRef.current();
    }
    const kf = findDoctorKeyframe(doctorKeyframesRef.current, activeDoctorKeyframeIdRef.current)
      || findDoctorKeyframe(doctorKeyframes, activeDoctorKeyframeId);
    if (!kf) {
      setMessage(zh ? '请先框选病灶，当前帧会作为关键帧' : 'Box the lesion first; this frame becomes the keyframe');
      return null;
    }
    const hasBox = (kf.lesionPolygon && kf.lesionPolygon.length >= 3) || pointsRef.current.length >= 3;
    if (!hasBox) {
      setMessage(zh ? '请先框选病灶，再分析' : 'Draw a lesion box first, then analyze');
      return null;
    }
    if (opts?.seek !== false) {
      await selectDoctorKeyframeRef.current(kf);
    }
    return kf;
  }, [activeDoctorKeyframeId, doctorKeyframes, mediaMode, zh]);

  const runUnifiedAgent = useCallback(async (opts?: {
    multiFrame?: boolean;
    assistProfile?: 'contour_anchored_fast' | 'full';
  }) => {
    if (!onUnifiedAgentRun || !simpleVideoMode || mediaMode !== 'video' || unifiedAgentBusy) return;
    const video = videoRef.current;
    if (!video?.videoWidth || !video.videoHeight || !videoUrl) {
      setMessage(zh ? '视频帧尚未准备好' : 'Video frame is not ready');
      return;
    }
    const stayTime = Number.isFinite(video.currentTime) ? video.currentTime : 0;
    if (!video.paused) {
      video.pause();
      setIsPlaying(false);
    }
    const totalSteps = ASSIST_ANALYSIS_STEPS.length;
    setAssistOverlayOpen(true);
    setTaskProgress({
      label: zh ? '辅助分析' : 'Assisted analysis',
      step: 1,
      totalSteps,
      detail: zh ? ASSIST_ANALYSIS_STEPS[0].zh : ASSIST_ANALYSIS_STEPS[0].en,
    });
    const boundKeyframe = await ensureActiveDoctorKeyframeForAnalysis({ seek: false });
    if (!boundKeyframe) {
      setAssistOverlayOpen(false);
      setTaskProgress(null);
      return;
    }
    setAnalysisContourUnrefined(!boundKeyframe.refined);
    persistOpenKeyframeContours();
    const snapshot = snapshotKeyframesForAnalysis(
      doctorKeyframesRef.current,
      boundKeyframe.id,
      {
        lesionPolygon: pointsRef.current,
        extraLesionPolygons: extraLesionPolygonsRef.current,
        lumenPolygon: lumenPolygonRef.current,
        lumenBox: lumenBoxRef.current,
        wallPolygon: wallPointsRef.current,
        wallLayerReadout: wallLayerReadoutRef.current,
      },
    );
    const analysisKeyframes = pickAnalysisKeyframes(snapshot, boundKeyframe.id);
    const selectedKeyframes = analysisKeyframes.length
      ? analysisKeyframes
      : [snapshot.find((kf) => kf.id === boundKeyframe.id) || boundKeyframe];
    // 0817 §5.1: diagnosis uses doctor keyframes only; never send the full-clip profile.
    const assistProfile = 'contour_anchored_fast';
    try {
      const frames: UnifiedAgentFrame[] = [];
      for (const [index, kf] of selectedKeyframes.entries()) {
        const position = Number(kf.timeSec.toFixed(3));
        setTaskProgress({
          label: zh ? '辅助分析' : 'Assisted analysis',
          step: 1,
          totalSteps,
          detail: zh
            ? `读取关键帧 ${index + 1}/${selectedKeyframes.length}`
            : `Reading keyframe ${index + 1}/${selectedKeyframes.length}`,
        });
        const frame = await captureKeyframeStill({
          video,
          videoUrl,
          timeSec: position,
          thumbDataUrl: kf.thumbDataUrl,
        });
        const lesion = kf.lesionPolygon && kf.lesionPolygon.length >= 3 ? kf.lesionPolygon : undefined;
        const lumenPoly = kf.lumenPolygon && kf.lumenPolygon.length >= 3 ? kf.lumenPolygon : undefined;
        frames.push({
          frame_png_b64: frame.b64,
          frame_id: `${patient.id}:${position}`,
          frame_index: index,
          timestamp_sec: position,
          quality_score: keyframeAnalysisQuality(kf),
          mask_polygon: lesion,
          lumen_polygon: lumenPoly,
          lumen_bbox: kf.lumenBox || undefined,
          keyframe_id: kf.id,
        });
      }
      setTaskProgress({
        label: zh ? '辅助分析' : 'Assisted analysis',
        step: 2,
        totalSteps,
        detail: zh ? ASSIST_ANALYSIS_STEPS[1].zh : ASSIST_ANALYSIS_STEPS[1].en,
      });
      const geometry = computeLesionLumenGeometry(
        pointsRef.current,
        lumenPolygonRef.current,
        lumenBoxRef.current,
      );
      const lumenPoly = lumenPolygonRef.current.length >= 3 ? lumenPolygonRef.current : undefined;
      const engineStarted = Date.now();
      const engineTimer = window.setInterval(() => {
        const elapsed = (Date.now() - engineStarted) / 1000;
        const engineStep = elapsed < 3 ? 2 : elapsed < 12 ? 3 : 4;
        const phase = ASSIST_ANALYSIS_STEPS[engineStep - 1];
        setTaskProgress({
          label: zh ? '辅助分析' : 'Assisted analysis',
          step: engineStep,
          totalSteps,
          detail: zh ? phase.zh : phase.en,
        });
      }, 700);
      try {
        await onUnifiedAgentRun({
          frames,
          current_time: stayTime,
          image_width: video.videoWidth,
          image_height: video.videoHeight,
          mask_polygon: pointsRef.current,
          roi_bbox: periLesionRoi({
            lesion: pointsRef.current,
            extras: extraLesionPolygonsRef.current,
            wall: wallPointsRef.current,
            width: video.videoWidth,
            height: video.videoHeight,
            margin: 48,
          }) || bboxFromPolygon(pointsRef.current) || undefined,
          lumen_bbox: lumenBoxRef.current || undefined,
          lumen_polygon: lumenPoly,
          workflow_trace: workflowTraceRef.current,
          assist_profile: assistProfile,
          contour_context: {
            lesion_confirmed: pointsRef.current.length >= 3,
            lumen_mask_type: lumenPoly
              ? 'sam31_polygon'
              : (lumenBoxRef.current ? 'bbox_proxy' : 'missing'),
            geometry_relation: geometry.relation,
            geometry_quality: geometry.quality,
            layer_label: layerResult?.layer?.label || null,
            layer_pixel_based: Boolean(layerResult?.pixelBased),
            in_contact: layerResult?.inContact ?? null,
            prepared_actions: contourPrepActionsRef.current,
            doctor_t_excluded: true,
            wall_target_layers: wallLayerTargetRef.current,
            wall_interrupts: wallLayerReadoutRef.current?.interrupts,
            wall_ticks: wallLayerReadoutRef.current?.ticks,
            wall_note: wallLayerReadoutRef.current?.noteZh || null,
            echo_pattern: wallEchoClarifyRef.current?.patternZh || null,
            echo_note: wallEchoClarifyRef.current?.noteZh || null,
            extra_lesion_count: extraLesionPolygonsRef.current.filter((poly) => poly.length >= 3).length,
            keyframe_interrupts: doctorKeyframesRef.current.map((kf) => ({
              timeSec: kf.timeSec,
              interrupts: kf.wallLayerReadout?.interrupts || [],
            })),
            peri_lesion_roi: periLesionRoi({
              lesion: pointsRef.current,
              extras: extraLesionPolygonsRef.current,
              wall: wallPointsRef.current,
              width: video.videoWidth,
              height: video.videoHeight,
              margin: 48,
            }) || null,
          },
        });
      } finally {
        window.clearInterval(engineTimer);
      }
      setTaskProgress({
        label: zh ? '辅助分析' : 'Assisted analysis',
        step: totalSteps,
        totalSteps,
        detail: zh ? ASSIST_ANALYSIS_STEPS[4].zh : ASSIST_ANALYSIS_STEPS[4].en,
      });
      setMessage(
        boundKeyframe && !boundKeyframe.refined
          ? uncorrectedContourNote(zh)
          : (zh
            ? `辅助分析完成（${selectedKeyframes.length} 个关键帧），请复核形态、边界和生长方式`
            : `Assist finished on ${selectedKeyframes.length} keyframes; review morphology, margin, and growth`),
      );
    } catch (error) {
      setMessage(error instanceof Error ? error.message : (zh ? '辅助分析失败' : 'Assisted analysis failed'));
    } finally {
      setTaskProgress(null);
      setAssistOverlayOpen(false);
      if (Math.abs((videoRef.current?.currentTime || 0) - stayTime) > 0.05) {
        setVideoTime(stayTime);
      }
      videoRef.current?.pause();
      setIsPlaying(false);
    }
  }, [ensureActiveDoctorKeyframeForAnalysis, layerResult, mediaMode, onUnifiedAgentRun, persistOpenKeyframeContours, patient, simpleVideoMode, unifiedAgentBusy, videoUrl, zh]);

  const lumenPrefer = useMemo(
    () => lumenPreferVector(points, lumenPolygon, lumenBox),
    [points, lumenPolygon, lumenBox],
  );
  const lumenLesionGeometry = useMemo(
    () => computeLesionLumenGeometry(points, lumenPolygon, lumenBox),
    [points, lumenPolygon, lumenBox],
  );
  const overlapFocus = useMemo(
    () => overlapFocusBox(points, lumenPolygon, lumenBox, lumenLesionGeometry),
    [lumenLesionGeometry, lumenBox, lumenPolygon, points],
  );

  const toggleZoomRoi = useCallback(() => {
    if (viewFocusMode === 'roi' || viewZoomRef.current > 1.02) {
      viewZoomRef.current = 1;
      viewCenterRef.current = null;
      viewPanDragRef.current = null;
      setViewZoom(1);
      setViewCenter(null);
      setViewFocusBox(null);
      setViewFocusMode(null);
      setMessage(zh ? '已回到整帧' : 'Back to the full frame');
      return;
    }
    setMagnifierOn(false);
    magnifierPosRef.current = null;
    viewZoomRef.current = 1;
    viewCenterRef.current = null;
    setViewZoom(1);
    setViewCenter(null);
    const lesionBox = bboxFromPointsOrBox(pointsRef.current, null);
    const lumenFocus = bboxFromPointsOrBox(lumenPolygon, lumenBoxRef.current);
    const next = unionFocusBoxes(lesionBox, lumenFocus);
    if (!next) {
      setMessage(zh ? '请先有病灶或胃腔轮廓再放大' : 'Need lesion or lumen contour to zoom');
      return;
    }
    setViewFocusBox(next);
    setViewFocusMode('roi');
    setMessage(zh ? '已放大至病灶/胃腔 ROI' : 'Zoomed to lesion/lumen ROI');
    recordDoctorOpRef.current('zoom_roi', {
      video_time_sec: videoRef.current?.currentTime ?? null,
      view_focus_mode: 'roi',
      view_box: next,
    });
  }, [lumenPolygon, viewFocusMode, zh]);

  const toggleOverlapZoom = useCallback(() => {
    if (viewFocusMode === 'overlap') {
      setViewFocusBox(null);
      setViewFocusMode(null);
      setMessage(zh ? '已退出重叠区域放大' : 'Exited overlap zoom');
      return;
    }
    if (!overlapFocus) {
      setMessage(
        lumenLesionGeometry.relation === 'near_lumen'
          ? (zh ? '当前为邻近胃腔，未形成可放大的交叠区域' : 'The contours are near the lumen but have no overlap focus region')
          : (zh ? '需要病灶和胃腔轮廓后才能放大交叠区域' : 'Create both lesion and lumen contours to zoom the overlap region'),
      );
      return;
    }
    setMagnifierOn(false);
    magnifierPosRef.current = null;
    setViewFocusBox(overlapFocus);
    setViewFocusMode('overlap');
    setMessage(zh ? '已放大病灶与胃腔交叠区域' : 'Zoomed to the lesion-lumen overlap region');
    recordDoctorOpRef.current('zoom_overlap', {
      video_time_sec: videoRef.current?.currentTime ?? null,
      view_focus_mode: 'overlap',
      view_box: overlapFocus,
    });
  }, [lumenLesionGeometry.relation, overlapFocus, viewFocusMode, zh]);

  const toggleMagnifier = useCallback(() => {
    setMagnifierOn((on) => {
      const next = !on;
      if (next) {
        setViewFocusBox(null);
        setViewFocusMode(null);
        setMessage(zh ? '放大镜已开启：在影像上滑动查看局部高倍细节' : 'Magnifier on: move over the image for local high-zoom detail');
      } else {
        magnifierPosRef.current = null;
        setMessage(zh ? '已关闭放大镜' : 'Magnifier off');
      }
      return next;
    });
  }, [zh]);

  const freezeCurrentFrame = useCallback(() => {
    const video = videoRef.current;
    if (video && !video.paused) video.pause();
    setFrameFrozen(true);
    frameFrozenRef.current = true;
    setTrackOnPlay(false);
    captureFrameDataUrl();
    recordDoctorOpRef.current('frame_freeze', {
      video_time_sec: video?.currentTime ?? null,
      frozen: true,
      playing: false,
    });
  }, [captureFrameDataUrl]);

  useEffect(() => {
    const handler = (event: Event) => {
      const open = Boolean((event as CustomEvent<{ open?: boolean }>).detail?.open);
      setWallAnalysisOpen(open);
      if (open) {
        freezeCurrentFrame();
        setMessage(zh ? '已暂停当前帧，右侧查看壁层' : 'Frame paused; wall layers are on the right');
      } else {
        setMessage(zh ? '已收起壁层' : 'Wall layers closed');
      }
    };
    window.addEventListener('gastric:open-wall-layers', handler);
    return () => window.removeEventListener('gastric:open-wall-layers', handler);
  }, [freezeCurrentFrame, zh]);

  useEffect(() => {
    if (!wallAnalysisOpen || typeof document === 'undefined') {
      setWallDockEl(null);
      return;
    }
    let cancelled = false;
    const attach = () => {
      const el = document.getElementById('wall-layer-dock');
      if (el && !cancelled) setWallDockEl(el);
      return Boolean(el);
    };
    if (attach()) return undefined;
    const timer = window.setInterval(() => {
      if (attach()) window.clearInterval(timer);
    }, 40);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [wallAnalysisOpen]);

  // Tissue-layer observation must use the actual displayed frame pixels.
  useEffect(() => {
    if (!wallAnalysisOpen) return;
    const video = videoRef.current;
    if (mediaMode === 'video' && video && !video.paused) {
      video.pause();
      setFrameFrozen(true);
      frameFrozenRef.current = true;
      setTrackOnPlay(false);
    }
    captureFrameDataUrl();
  }, [wallAnalysisOpen]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!wallAnalysisOpen || mediaMode !== 'video') return;
    const video = videoRef.current;
    if (!video) return;
    const onSeeked = () => {
      captureFrameDataUrl();
    };
    video.addEventListener('seeked', onSeeked);
    return () => video.removeEventListener('seeked', onSeeked);
  }, [wallAnalysisOpen, mediaMode, captureFrameDataUrl]);

  const buildExplainableFramePayload = useCallback(async (): Promise<ExplainableFramePayload | null> => {
    if (!patient) return null;
    const poly = pointsRef.current;
    if (!poly || poly.length < 3) return null;
    const frame = await videoOrImageToSamFrame(
      videoRef.current,
      imgRef.current,
      mediaMode === 'video',
      8192,
    );
    return {
      frame_png_b64: frame.b64,
      mask_polygon: poly.map((p) => [Number(p[0]), Number(p[1])]),
      image_width: frame.fullWidth,
      image_height: frame.fullHeight,
      frame_time: mediaMode === 'video' ? Number(videoTime.toFixed(3)) : undefined,
      patient_id: patient.patient_id,
      case_id: patient.id,
      lumen_bbox: lumenBoxRef.current || undefined,
      lumen_polygon: lumenPolygonRef.current.length >= 3
        ? lumenPolygonRef.current.map((p) => [Number(p[0]), Number(p[1])])
        : undefined,
    };
  }, [mediaMode, patient, videoTime]);

  const openExplainableAnalysis = useCallback(() => {
    if (pointsRef.current.length < 3) {
      setMessage(zh ? '请先在当前帧框选或生成病灶轮廓，再运行边界分析' : 'Draw a lesion contour on the current frame first');
      return;
    }
    freezeCurrentFrame();
    setShowExplainable(true);
  }, [freezeCurrentFrame, zh]);

  const syncFrameFromVideo = useCallback((opts?: { force?: boolean }) => {
    if (!opts?.force && (frameFrozenRef.current || dragIndexRef.current !== null)) return;
    const video = videoRef.current;
    if (!video || !video.videoWidth) return;
    setVideoTime(video.currentTime || 0);
    setImgLoaded(true);
    const canvas = canvasRef.current;
    const container = containerRef.current;
    if (canvas && container) {
      const rect = container.getBoundingClientRect();
      const w = Math.max(320, Math.floor(rect.width));
      const h = Math.max(240, Math.floor(rect.height));
      if (canvas.width !== w || canvas.height !== h) {
        canvas.width = w;
        canvas.height = h;
      }
    }
  }, []);

  const paintProgressUi = useCallback((timeSec: number, _options?: { forceSlider?: boolean }) => {
    const text = formatCineTime(timeSec, videoFpsRef.current);
    for (const label of videoTimeLabelRefs.current) {
      if (label) label.textContent = text;
    }
    const durationSec = videoRef.current?.duration || videoDuration || 0;
    for (const slider of videoProgressRefs.current) {
      applyProgressSlider(slider, timeSec, durationSec);
    }
  }, [videoDuration]);

  const setOverlayCanvasVisible = useCallback((visible: boolean) => {
    const canvas = canvasRef.current;
    if (canvas) canvas.style.visibility = visible ? 'visible' : 'hidden';
  }, []);

  const cancelPendingScrubSeek = useCallback(() => {
    if (scrubSeekRafRef.current != null) {
      cancelAnimationFrame(scrubSeekRafRef.current);
      scrubSeekRafRef.current = null;
    }
    if (scrubSeekTimerRef.current != null) {
      window.clearTimeout(scrubSeekTimerRef.current);
      scrubSeekTimerRef.current = null;
    }
  }, []);

  const applyPendingScrubSeek = useCallback((force: boolean) => {
    const next = pendingScrubTimeRef.current;
    const video = videoRef.current;
    if (next == null || !video) return;
    const now = performance.now();
    if (!force && now - lastScrubSeekAtRef.current < 72) {
      if (scrubSeekTimerRef.current == null) {
        scrubSeekTimerRef.current = window.setTimeout(() => {
          scrubSeekTimerRef.current = null;
          applyPendingScrubSeek(false);
        }, 72 - (now - lastScrubSeekAtRef.current));
      }
      return;
    }
    lastScrubSeekAtRef.current = now;
    if (Math.abs((video.currentTime || 0) - next) > 0.001) {
      video.currentTime = next;
    }
  }, []);

  const beginVideoScrub = useCallback(() => {
    const video = videoRef.current;
    if (!video) return;
    scrubbingRef.current = true;
    persistOpenKeyframeContoursRef.current({ refOnly: true });
    video.pause();
    setOverlayCanvasVisible(false);
    if (frameFrozenRef.current) {
      frameFrozenRef.current = false;
      setFrameFrozen(false);
    }
    recordDoctorOpRef.current('cine_scrub_start', { video_time_sec: video.currentTime || 0, playing: false });
  }, [setOverlayCanvasVisible]);

  const scrubVideoTo = useCallback((nextTime: number) => {
    const video = videoRef.current;
    if (!video) return;
    const clamped = Math.max(0, Math.min(video.duration || nextTime, nextTime));
    pendingScrubTimeRef.current = clamped;
    paintProgressUi(clamped);
    if (scrubSeekRafRef.current == null) {
      scrubSeekRafRef.current = requestAnimationFrame(() => {
        scrubSeekRafRef.current = null;
        applyPendingScrubSeek(false);
      });
    }
  }, [applyPendingScrubSeek, paintProgressUi]);

  const endVideoScrub = useCallback(() => {
    if (!scrubbingRef.current) return;
    const video = videoRef.current;
    scrubbingRef.current = false;
    cancelPendingScrubSeek();
    if (scrubPreviewRafRef.current != null) {
      cancelAnimationFrame(scrubPreviewRafRef.current);
      scrubPreviewRafRef.current = null;
    }
    const t = pendingScrubTimeRef.current ?? video?.currentTime ?? 0;
    pendingScrubTimeRef.current = t;
    applyPendingScrubSeek(true);
    setOverlayCanvasVisible(true);
    setVideoTime(t);
    paintProgressUi(t);
    syncFrameFromVideo({ force: true });
    const activeId = activeDoctorKeyframeIdRef.current;
    const kf = findDoctorKeyframeById(doctorKeyframesRef.current, activeId);
    if (kf && Math.abs(t - kf.timeSec) > DOCTOR_KEYFRAME_OPEN_EPS_SEC) {
      const lesion = pointsRef.current.length >= 3 ? clonePoly(pointsRef.current) : null;
      const lumen = lumenPolygonRef.current.length >= 3 ? clonePoly(lumenPolygonRef.current) : null;
      const next = doctorKeyframesRef.current.map((item) => (
        item.id === kf.id
          ? {
              ...item,
              lesionPolygon: lesion || item.lesionPolygon,
              lumenPolygon: lumen || item.lumenPolygon,
              lumenBox: lumenBoxRef.current || item.lumenBox,
            }
          : item
      ));
      doctorKeyframesRef.current = next;
      setDoctorKeyframes(next);
      setActiveDoctorKeyframeId(null);
      activeDoctorKeyframeIdRef.current = null;
    } else {
      setDoctorKeyframes(doctorKeyframesRef.current);
    }
    redrawRef.current();
    recordDoctorOpRef.current('cine_scrub_end', { video_time_sec: t, playing: false });
  }, [applyPendingScrubSeek, cancelPendingScrubSeek, paintProgressUi, setOverlayCanvasVisible, syncFrameFromVideo]);

  const stepCineFrames = useCallback((deltaFrames: number) => {
    const video = videoRef.current;
    if (!video || !videoUrl) return;
    persistOpenKeyframeContoursRef.current();
    video.pause();
    setIsPlaying(false);
    setTrackOnPlay(false);
    setFrameFrozen(false);
    frameFrozenRef.current = false;
    const nextTime = stepCineTime(
      video.currentTime || 0,
      deltaFrames,
      videoFpsRef.current,
      video.duration || videoDuration,
    );
    if (Math.abs((video.currentTime || 0) - nextTime) > 0.0005) {
      video.currentTime = nextTime;
    }
    setVideoTime(nextTime);
    paintProgressUi(nextTime, { forceSlider: true });
    syncFrameFromVideo({ force: true });
    redrawRef.current();
    recordDoctorOpRef.current('cine_frame_step', {
      video_time_sec: nextTime,
      step: deltaFrames,
      playing: false,
    });
  }, [paintProgressUi, syncFrameFromVideo, videoDuration, videoUrl]);

  const onVideoProgressChange = useCallback((nextTime: number) => {
    if (!scrubbingRef.current) {
      // Keyboard / accessibility seeks do not fire pointerdown.
      const video = videoRef.current;
      if (!video) return;
      persistOpenKeyframeContoursRef.current();
      video.pause();
      video.currentTime = Math.max(0, Math.min(video.duration || nextTime, nextTime));
      const t = video.currentTime || 0;
      setVideoTime(t);
      paintProgressUi(t, { forceSlider: true });
      syncFrameFromVideo({ force: true });
      redrawRef.current();
      return;
    }
    scrubVideoTo(nextTime);
  }, [paintProgressUi, scrubVideoTo, syncFrameFromVideo]);

  useEffect(() => {
    if (scrubbingRef.current) return;
    paintProgressUi(videoTime);
  }, [paintProgressUi, videoTime]);

  useEffect(() => {
    const onWheel = (event: WheelEvent) => {
      event.preventDefault();
      stepCineFrames(event.deltaY > 0 ? 1 : -1);
    };
    const shells = videoProgressRefs.current.filter((node): node is HTMLDivElement => Boolean(node));
    for (const shell of shells) {
      shell.addEventListener('wheel', onWheel, { passive: false });
    }
    return () => {
      for (const shell of shells) {
        shell.removeEventListener('wheel', onWheel);
      }
    };
  }, [stepCineFrames, videoUrl]);

  useEffect(() => {
    if (!taskProgress && !assistOverlayOpen) {
      taskProgressStartedAtRef.current = null;
      setTaskElapsedSec(0);
      return;
    }
    if (taskProgressStartedAtRef.current == null) {
      taskProgressStartedAtRef.current = performance.now();
    }
    const tick = window.setInterval(() => {
      const started = taskProgressStartedAtRef.current;
      if (started == null) return;
      setTaskElapsedSec(Math.floor((performance.now() - started) / 1000));
    }, 250);
    return () => window.clearInterval(tick);
  }, [assistOverlayOpen, taskProgress]);

  const runSamAtPoint = useCallback(async (
    imgPt: number[] | null,
    opts?: {
      silent?: boolean;
      source?: MaskBoundaryOverride['source'];
      box?: { x1: number; y1: number; x2: number; y2: number };
      clicks?: Array<{ x: number; y: number; label: 'positive' | 'negative' }>;
      keepEditing?: boolean;
      stayInSam?: boolean;
      llmReport?: boolean;
      /** Override UI model for one call (e.g. sam2 for box auto-seg). */
      model?: LesionSegmentationModel | 'sam2';
    },
  ): Promise<number[][] | null> => {
    if (!patient) return null;
    const traceId = `sam_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
    const traceStartedAt = performance.now();
    const activeModel = opts?.model || segmentationModel;
    // Supersede in-flight interactive requests instead of dropping clicks.
    if (!opts?.silent) {
      samAbortRef.current?.abort();
      samGenRef.current += 1;
      samBusyRef.current = true;
      setSamBusy(true);
      setMessage(zh ? '系统分析中…' : 'Running SAM…');
    } else {
      samAbortRef.current?.abort();
    }
    const ac = new AbortController();
    samAbortRef.current = ac;
    const myGen = samGenRef.current;
    try {
      const frame = await videoOrImageToSamFrame(
        videoRef.current,
        imgRef.current,
        mediaMode === 'video',
        1024,
      );
      const scale = frame.scale || 1;
      const currentFrameTime = mediaMode === 'video'
        ? Number(videoRef.current?.currentTime ?? videoTime)
        : 0;
      const payload: Record<string, unknown> = {
        case_id: patient.patient_id,
        frame_png_b64: frame.b64,
        image_width: frame.width,
        image_height: frame.height,
        frame_time: currentFrameTime,
        model: activeModel === 'sabm_sam2_guided' ? 'sam2' : activeModel,
        video_url: mediaMode === 'video' ? videoUrl : undefined,
        tracking_session_id: trackingSessionId || undefined,
        tracking_enabled: mediaMode === 'video' && Boolean(trackingSessionId),
        tracking_reset: mediaMode === 'video'
          && opts?.source === 'sam'
          && !opts?.silent,
        llm_report: Boolean(opts?.llmReport),
        include_overlay: false,
      };
      const promptClicks = opts?.clicks?.length
        ? opts.clicks
        : imgPt
          ? [{ x: imgPt[0], y: imgPt[1], label: 'positive' as const }]
          : [];
      if (opts?.box) {
        payload.box = {
          x1: opts.box.x1 * scale,
          y1: opts.box.y1 * scale,
          x2: opts.box.x2 * scale,
          y2: opts.box.y2 * scale,
        };
      }
      if (promptClicks.length) {
        payload.clicks = promptClicks.map((c) => ({
          x: c.x * scale,
          y: c.y * scale,
          label: c.label,
        }));
        const firstPos = promptClicks.find((c) => c.label !== 'negative') || promptClicks[0];
        payload.click = {
          x: firstPos.x * scale,
          y: firstPos.y * scale,
          label: firstPos.label,
        };
      } else if (!opts?.box) {
        throw new Error('missing click/box');
      }
      const res = await fetch('/api/agent/sam-interactive', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
        signal: ac.signal,
      });
      const data = await readJsonPayload<{
        ok?: boolean;
        error?: string;
        result?: {
          mask_polygon?: number[][];
          prompt_meta?: Record<string, unknown>;
          message?: string;
          sam_score?: number;
          backend_id?: string;
          report?: SamReport;
        };
      }>(res, 'Interactive segmentation endpoint');
      if (!data.ok || !data.result?.mask_polygon) {
        throw new Error(data.error || data.result?.message || 'SAM returned no polygon');
      }
      const rawPoly = (data.result.mask_polygon as number[][]).map((p) => [Number(p[0]), Number(p[1])]);
      if (rawPoly.length < 3) {
        throw new Error(
          zh
            ? '系统分析未得到有效区域，请换一个关注点重试'
            : 'No valid region returned — try another point',
        );
      }
      const promptMeta = (data.result.prompt_meta || {}) as Record<string, unknown>;
      const maskArea = Number(promptMeta.mask_area_px);
      const maskAreaRatio = Number.isFinite(maskArea) && frame.width > 0 && frame.height > 0
        ? maskArea / (frame.width * frame.height)
        : null;
      const polyFull = scalePolyToFull(rawPoly, scale, frame.fullWidth, frame.fullHeight);
      const poly = prepareEditableContour(polyFull, LESION_CONTOUR_MAX_POINTS);
      maskAuditRef.current('model_trace', {
        trace_id: traceId,
        operation: 'interactive_segmentation',
        model: activeModel,
        source: opts?.source || 'manual_prompt',
        outcome: 'success',
        frame_time_sec: currentFrameTime,
        input: {
          has_box: Boolean(opts?.box),
          click_count: promptClicks.length,
          positive_clicks: promptClicks.filter((click) => click.label !== 'negative').length,
          negative_clicks: promptClicks.filter((click) => click.label === 'negative').length,
          silent: Boolean(opts?.silent),
          tracking_session_id: trackingSessionId || undefined,
        },
        output: {
          polygon_points: poly.length,
          mask_area_ratio: maskAreaRatio,
          score: Number.isFinite(Number(data.result.sam_score))
            ? Number(data.result.sam_score)
            : undefined,
          backend_id: data.result.backend_id,
        },
        duration_ms: Math.round(performance.now() - traceStartedAt),
      });
      const nextReport = (
        data.result.report
        || buildModelAssistReport(
          patient,
          poly,
          frame.fullWidth,
          frame.fullHeight,
          segmentationModel,
          maskAreaRatio ?? undefined,
          zh,
        )
      ) as SamReport;
      setSamReport(nextReport);
      onSystemReport?.(nextReport);
      const targetLayer = opts?.source === 'video_track' || opts?.source === 'video_propagate'
        ? 'lesion'
        : activeLayer;
      if (targetLayer === 'wall') {
        setWallPoints(poly);
        wallPointsRef.current = poly;
        snapshotOriginal(pointsRef.current, poly);
      } else {
        contourInteractionRef.current = true;
        generatedLesionRef.current = clonePoly(poly);
        setPoints(poly);
        pointsRef.current = poly;
        snapshotOriginal(poly, wallPointsRef.current);
      }

      if (opts?.keepEditing !== false && opts?.source !== 'video_track') {
        freezeCurrentFrame();
        if (opts?.stayInSam || opts?.source === 'sam') {
          setMode('sam');
        } else {
          setMode('soft');
        }
      }

      if (!opts?.silent) {
        const score = Number(data.result.sam_score);
        const scoreText = Number.isFinite(score) ? `, score ${score.toFixed(2)}` : '';
        const positiveCount = promptClicks.filter((click) => click.label !== 'negative').length;
        const negativeCount = promptClicks.filter((click) => click.label === 'negative').length;
        setMessage(
          zh
            ? `当前帧 ROI 已更新（${poly.length} 点${scoreText}），正点 ${positiveCount}，负点 ${negativeCount}`
            : `Current-frame ROI updated (${poly.length} points${scoreText}), positive ${positiveCount}, negative ${negativeCount}`,
        );
      } else {
        setMessage(
          zh
            ? `视频跟随 t=${(videoRef.current?.currentTime || 0).toFixed(2)}s, ${poly.length}pt`
            : `Video track t=${(videoRef.current?.currentTime || 0).toFixed(2)}s, ${poly.length}pt`,
        );
      }
      setSamAvailable(true);
      if (
        simpleVideoMode
        && targetLayer !== 'wall'
        && opts?.source !== 'video_track'
        && opts?.source !== 'video_propagate'
        && poly.length >= 3
      ) {
        scheduleCompleteMaskAutosaveRef.current('auto_save');
      }
      return poly;
    } catch (err) {
      const aborted = (err as Error)?.name === 'AbortError';
      maskAuditRef.current('model_trace', {
        trace_id: traceId,
        operation: 'interactive_segmentation',
        model: activeModel,
        source: opts?.source || 'manual_prompt',
        outcome: aborted ? 'aborted' : 'error',
        frame_time_sec: Number((videoRef.current?.currentTime ?? videoTime).toFixed(3)),
        input: {
          has_box: Boolean(opts?.box),
          click_count: opts?.clicks?.length || (imgPt ? 1 : 0),
          silent: Boolean(opts?.silent),
        },
        error: aborted
          ? undefined
          : err instanceof Error ? err.message.slice(0, 240) : 'System analysis failed',
        duration_ms: Math.round(performance.now() - traceStartedAt),
      });
      if (aborted) return null;
      if (!opts?.silent) {
        setSamAvailable(false);
        setMessage(err instanceof Error ? sanitizeSystemCopy(err.message) : 'System analysis failed');
      }
      return null;
    } finally {
      if (!opts?.silent && samGenRef.current === myGen) {
        samBusyRef.current = false;
        setSamBusy(false);
      }
    }
  }, [
    patient,
    zh,
    activeLayer,
    mediaMode,
    videoTime,
    videoUrl,
    trackingSessionId,
    segmentationModel,
    freezeCurrentFrame,
    snapshotOriginal,
    onSystemReport,
    simpleVideoMode,
  ]);

  const predictKeyframes = useCallback(async (candidates: KeyframeCandidate[]) => {
    const video = videoRef.current;
    const seed = clonePoly(pointsRef.current);
    const box = bboxFromPolygon(seed);
    const centroid = polygonCentroid(seed);
    if (!simpleVideoMode || mediaMode !== 'video' || !video?.videoWidth || !video.videoHeight || !box || !centroid) {
      setKeyCandidates((current) => current.map((candidate) => ({ ...candidate, prediction_status: 'needs_roi' })));
      setMessage(zh ? '请先框选病灶，再生成关键帧病灶预测' : 'Draw an ROI box first, then generate keyframe lesion predictions');
      return;
    }

    const originalTime = video.currentTime || videoTime;
    const wasFrozen = frameFrozenRef.current;
    let predictedCount = 0;
    video.pause();
    setFrameFrozen(true);
    frameFrozenRef.current = true;
    try {
      for (const [index, candidate] of candidates.entries()) {
        const timestamp = Number(candidate.timestamp_sec || 0);
        setMessage(
          zh
            ? `关键帧病灶预测 ${index + 1}/${candidates.length}…`
            : `Predicting lesion on keyframe ${index + 1}/${candidates.length}…`,
        );
        try {
          await seekVideoForAgent(video, timestamp);
          setVideoTime(timestamp);
          const poly = simpleVideoMode && segmentationModel === 'sabm_sam2_guided'
            ? await runSamAtPoint(centroid, {
                silent: true,
                source: 'video_track',
                box,
                keepEditing: false,
              })
            : simpleVideoMode
              ? await runLesionModelRef.current(centroid, box, samClicksRef.current)
              : await runSamAtPoint(centroid, {
                  silent: true,
                  source: 'video_track',
                  box,
                  keepEditing: false,
                });
          if (!poly || poly.length < 3) {
            setKeyCandidates((current) => current.map((item) => (
              item.timestamp_sec === candidate.timestamp_sec
                ? { ...item, prediction_status: 'failed', prediction_error: 'no polygon' }
                : item
            )));
            continue;
          }
          predictedCount += 1;
          const normalized = poly.map((point) => [
            Number((point[0] / video.videoWidth).toFixed(6)),
            Number((point[1] / video.videoHeight).toFixed(6)),
          ]);
          setKeyCandidates((current) => current.map((item) => (
            item.timestamp_sec === candidate.timestamp_sec
              ? { ...item, predicted_polygon: normalized, prediction_status: 'predicted' }
              : item
          )));
        } catch (error) {
          setKeyCandidates((current) => current.map((item) => (
            item.timestamp_sec === candidate.timestamp_sec
              ? {
                  ...item,
                  prediction_status: 'failed',
                  prediction_error: error instanceof Error ? error.message : 'prediction failed',
                }
              : item
          )));
        }
      }
    } finally {
      await seekVideoForAgent(video, originalTime);
      setVideoTime(originalTime);
      pointsRef.current = seed;
      setPoints(seed);
      setFrameFrozen(wasFrozen);
      frameFrozenRef.current = wasFrozen;
      redrawRef.current();
    }
    setMessage(
      zh
        ? `已完成 ${predictedCount}/${candidates.length} 个关键帧的病灶预测`
        : `Lesion predictions completed for ${predictedCount}/${candidates.length} keyframes`,
    );
  }, [mediaMode, runSamAtPoint, segmentationModel, simpleVideoMode, videoTime, zh]);

  useEffect(() => {
    predictKeyframesRef.current = predictKeyframes;
  }, [predictKeyframes]);

  const recordVideoFrameOverride = useCallback((poly: number[][], status: 'seed' | 'accepted' = 'accepted') => {
    if (mediaMode !== 'video') return;
    const video = videoRef.current;
    if (!video?.videoWidth || !video.videoHeight) return;
    const timestamp = Number((video.currentTime || 0).toFixed(3));
    const lumenPoly = lumenPolygonRef.current.length >= 3
      ? lumenPolygonRef.current
      : nearestOverrideFrame(videoFrameOverridesRef.current, timestamp, 0.35)?.lumen_polygon;
    const lumenBoxNow = lumenBoxRef.current || (lumenPoly ? bboxFromPolygon(lumenPoly) : undefined);
    const frame: VideoMaskFrameOverride = {
      timestamp_sec: timestamp,
      imageWidth: video.videoWidth,
      imageHeight: video.videoHeight,
      mask_polygon: poly.map((point) => [Math.round(point[0] * 10) / 10, Math.round(point[1] * 10) / 10]),
      roi_bbox: bboxFromPolygon(poly),
      lumen_polygon: lumenPoly?.length
        ? lumenPoly.map((point) => [Math.round(point[0] * 10) / 10, Math.round(point[1] * 10) / 10])
        : undefined,
      lumen_bbox: lumenBoxNow || undefined,
      source: 'video_track',
      propagation_status: status,
    };
    const next = [
      ...videoFrameOverridesRef.current.filter((item) => Math.abs(item.timestamp_sec - timestamp) > 0.12),
      frame,
    ].sort((a, b) => a.timestamp_sec - b.timestamp_sec);
    videoFrameOverridesRef.current = next;
    setVideoFrameOverrides(next);
  }, [mediaMode]);

  const resumeSimpleTracking = useCallback((poly: number[][] | null) => {
    if (!simpleVideoMode || !poly || poly.length < 3) return;
    recordVideoFrameOverride(poly, videoFrameOverridesRef.current.length ? 'accepted' : 'seed');
    setTrackingPrepared(false);
    setTrackOnPlay(false);
    setFrameFrozen(false);
    frameFrozenRef.current = false;
    setMessage(zh ? '当前帧轮廓已生成；请确认胃腔后点击“跟踪扩散”，将同时跟踪病灶与胃腔' : 'Contour ready; confirm lumen, then Track video for lesion + lumen');
  }, [recordVideoFrameOverride, simpleVideoMode, zh]);

  const getCurrentTrackedPolygon = useCallback((): number[][] => {
    if (mediaMode !== 'video' || !videoFrameOverridesRef.current.length) {
      return pointsRef.current;
    }
    const currentTime = videoRef.current?.currentTime || 0;
    const nearest = videoFrameOverridesRef.current.reduce((best, item) => (
      Math.abs(item.timestamp_sec - currentTime) < Math.abs(best.timestamp_sec - currentTime) ? item : best
    ), videoFrameOverridesRef.current[0]);
    return nearest?.mask_polygon?.length ? nearest.mask_polygon : pointsRef.current;
  }, [mediaMode]);

  const precomputeVideoTracking = useCallback(async () => {
    if (!simpleVideoMode || mediaMode !== 'video' || precomputeBusy) return;
    const video = videoRef.current;
    const seed = pointsRef.current;
    if (!video || !video.videoWidth || seed.length < 3) {
      setMessage(zh ? '请先在当前帧生成有效轮廓' : 'Generate a valid contour first');
      return;
    }
    const duration = video.duration || 0;
    const start = video.currentTime || 0;
    // Full-video tracking must cover frames before and after the seed, not only later frames.
    if (!duration || duration <= 0.1) {
      setMessage(zh ? '当前视频时长不可用' : 'Video duration unavailable');
      return;
    }
    const box = bboxFromPolygon(seed);
    const centroid = polygonCentroid(seed);
    if (!box || !centroid) {
      setMessage(zh ? '当前帧轮廓无法生成传播提示' : 'Could not create a propagation prompt');
      return;
    }
    // Require a real lumen contour (not just the YOLO/manual box) so tracking
    // starts only after both lesion and lumen segmentation are ready.
    const lumenSeedPoly = lumenPolygonRef.current.length >= 3 ? clonePoly(lumenPolygonRef.current) : [];
    const lumenSeedBox = (lumenSeedPoly.length >= 3 ? bboxFromPolygon(lumenSeedPoly) : null)
      || lumenBoxRef.current;
    const lumenCentroid = lumenSeedPoly.length >= 3
      ? polygonCentroid(lumenSeedPoly)
      : null;
    if (lumenSeedPoly.length < 3 || !lumenSeedBox || !lumenCentroid) {
      setMessage(zh ? '请先完成病灶与胃腔轮廓分割，再点「视频跟踪」同时跟踪两者' : 'Finish lesion and lumen contours first, then Track video for both together');
      return;
    }
    const traceId = `video_propagate_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
    const traceStartedAt = performance.now();
    video.pause();
    setTrackOnPlay(false);
    setFrameFrozen(true);
    frameFrozenRef.current = true;
    setPrecomputeBusy(true);
    setTrackingPrepared(false);
    try {
      setPrecomputeProgress(zh ? '病灶跟踪中…' : 'Tracking lesion…');
      setTaskProgress({
        label: zh ? '整段视频跟踪' : 'Full-video tracking',
        step: 1,
        totalSteps: 3,
        detail: zh ? '病灶跟踪中…' : 'Tracking lesion…',
      });
      const lesionResult = await requestVideoPropagate({
        case_id: patient?.patient_id || patient?.id || '',
        model: segmentationModel,
        video_url: videoUrl,
        frame_time: start,
        image_width: video.videoWidth,
        image_height: video.videoHeight,
        clicks: samClicksRef.current.length
          ? samClicksRef.current
          : [{ x: centroid[0], y: centroid[1], label: 'positive' }],
        box,
        direction: 'both',
        max_frames: Math.max(120, Math.ceil(duration * 120)),
        text_prompt: 'gastric lesion',
        use_lora: true,
      });
      const lesionFrames = mapPropagateFramesToOverrides(
        lesionResult.frames || [],
        video.videoWidth,
        video.videoHeight,
        'video_track',
      );
      if (!lesionFrames.length) throw new Error('full video precompute returned no lesion masks');

      setPrecomputeProgress(zh ? '胃腔跟踪中…' : 'Tracking lumen…');
      setTaskProgress({
        label: zh ? '整段视频跟踪' : 'Full-video tracking',
        step: 2,
        totalSteps: 3,
        detail: zh ? '胃腔跟踪中…' : 'Tracking lumen…',
      });
      let lumenFrames: VideoMaskFrameOverride[] = [];
      let lumenTracked = false;
      try {
        const lumenResult = await requestVideoPropagate({
          case_id: patient?.patient_id || patient?.id || '',
          model: segmentationModel,
          video_url: videoUrl,
          frame_time: start,
          image_width: video.videoWidth,
          image_height: video.videoHeight,
          clicks: [{ x: lumenCentroid[0], y: lumenCentroid[1], label: 'positive' }],
          box: lumenSeedBox,
          direction: 'both',
          max_frames: Math.max(120, Math.ceil(duration * 120)),
          text_prompt: 'gastric lumen cavity',
          use_lora: false,
        });
        lumenFrames = mapPropagateFramesToOverrides(
          lumenResult.frames || [],
          video.videoWidth,
          video.videoHeight,
          'video_track',
        );
        lumenTracked = lumenFrames.length > 0;
      } catch (lumenError) {
        console.warn('lumen video track failed', lumenError);
      }

      const cachedFrames = mergeLumenIntoLesionFrames(lesionFrames, lumenFrames, {
        polygon: lumenSeedPoly,
        box: lumenSeedBox,
      }, start);
      setPrecomputeProgress(`${cachedFrames.length}/${lesionResult.num_frames || cachedFrames.length}`);
      setTaskProgress({
        label: zh ? '整段视频跟踪' : 'Full-video tracking',
        step: 3,
        totalSteps: 3,
        detail: zh
          ? `合并并保存 ${cachedFrames.length}/${lesionResult.num_frames || cachedFrames.length} 帧`
          : `Merging and saving ${cachedFrames.length}/${lesionResult.num_frames || cachedFrames.length} frames`,
      });
      videoFrameOverridesRef.current = cachedFrames;
      setVideoFrameOverrides(cachedFrames);
      const nearest = nearestOverrideFrame(cachedFrames, start, 1.0) || cachedFrames[0];
      if (nearest?.mask_polygon?.length) {
        pointsRef.current = nearest.mask_polygon;
        setPoints(nearest.mask_polygon);
      }
      if (nearest?.lumen_polygon?.length) {
        lumenPolygonRef.current = nearest.lumen_polygon;
        setLumenPolygon(nearest.lumen_polygon);
        const nextBox = nearest.lumen_bbox || bboxFromPolygon(nearest.lumen_polygon);
        if (nextBox) {
          lumenBoxRef.current = nextBox;
          setLumenBox(nextBox);
        }
      }
      setVideoTime(start);
      setTrackingPrepared(true);
      setTrackOnPlay(true);
      setFrameFrozen(false);
      frameFrozenRef.current = false;
      await applyAreaKeyframesRef.current(cachedFrames);
      const persisted = await persistOverrideRef.current('video_tracking_complete');
      maskAuditRef.current('model_trace', {
        trace_id: traceId,
        operation: 'video_propagation',
        model: segmentationModel,
        source: 'video_propagate',
        outcome: 'success',
        frame_time_sec: start,
        input: {
          direction: 'both',
          requested_max_frames: Math.ceil(duration * 120),
          video_duration_sec: duration,
        },
        output: {
          lesion_frame_count: lesionFrames.length,
          lumen_frame_count: lumenFrames.length,
          merged_frame_count: cachedFrames.length,
          lumen_tracked: lumenTracked,
          persisted,
          frames_with_lesion_box: cachedFrames.filter((frame) => Boolean(frame.roi_bbox)).length,
          frames_with_lumen_mask: cachedFrames.filter((frame) => (frame.lumen_polygon?.length || 0) >= 3).length,
          frames_with_lumen_box: cachedFrames.filter((frame) => Boolean(frame.lumen_bbox)).length,
        },
        duration_ms: Math.round(performance.now() - traceStartedAt),
      });
      setMessage(
        zh
          ? `跟踪扩散完成：病灶 ${cachedFrames.length} 帧${lumenTracked ? `，胃腔 ${lumenFrames.length} 帧` : '（胃腔跟踪失败，已用当前胃腔种子）'}；${persisted ? '完整结果已保存' : '保存失败，请点击保存轮廓'}`
          : `Tracking done: lesion ${cachedFrames.length} frames${lumenTracked ? `, lumen ${lumenFrames.length} frames` : ' (lumen track failed, seed carried)'}; ${persisted ? 'complete result saved' : 'save failed, click Save complete masks'}`,
      );
    } catch (error) {
      maskAuditRef.current('model_trace', {
        trace_id: traceId,
        operation: 'video_propagation',
        model: segmentationModel,
        source: 'video_propagate',
        outcome: 'error',
        frame_time_sec: start,
        error: error instanceof Error ? error.message.slice(0, 240) : 'Precompute failed',
        duration_ms: Math.round(performance.now() - traceStartedAt),
      });
      setMessage(error instanceof Error ? error.message : (zh ? '预计算失败' : 'Precompute failed'));
    } finally {
      setPrecomputeBusy(false);
      setPrecomputeProgress(null);
      setTaskProgress(null);
    }
  }, [mediaMode, patient?.id, patient?.patient_id, precomputeBusy, segmentationModel, simpleVideoMode, videoUrl, zh]);

  const maybeTrackWhilePlaying = useCallback(async () => {
    if (!trackOnPlay || mediaMode !== 'video' || !isPlaying) return;
    if (simpleVideoMode && (simpleEditMode || trackingPrepared)) return;
    if (frameFrozenRef.current || dragIndexRef.current !== null) return;
    if (trackBusyRef.current || (!simpleVideoMode && samAvailable === false)) return;
    const now = Date.now();
    if (now - lastTrackAtRef.current < 500) return;
    const poly = pointsRef.current;
    if (poly.length < 3) return;
    const bbox = bboxFromPolygon(poly);
    const centroid = polygonCentroid(poly);
    if (!bbox || !centroid) return;
    trackBusyRef.current = true;
    lastTrackAtRef.current = now;
    try {
      const nextPoly = simpleVideoMode && segmentationModel !== 'sabm_sam2_guided'
        ? await runLesionModelRef.current(centroid, bbox, samClicksRef.current)
        : await runSamAtPoint(centroid, {
            silent: true,
            source: 'video_track',
            box: bbox,
            keepEditing: false,
          });
      if (nextPoly && nextPoly.length >= 3) recordVideoFrameOverride(nextPoly);
    } finally {
      trackBusyRef.current = false;
    }
  }, [trackOnPlay, mediaMode, isPlaying, samAvailable, runSamAtPoint, recordVideoFrameOverride, segmentationModel, simpleEditMode, simpleVideoMode, trackingPrepared]);


  const redraw = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas || !imgLoaded) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const video = videoRef.current;
    const img = imgRef.current;
    const useVideo =
      mediaMode === 'video'
      && !!video
      && video.videoWidth > 0
      && video.readyState >= 2;

    const iw = useVideo ? video!.videoWidth : (img?.naturalWidth || 0);
    const ih = useVideo ? video!.videoHeight : (img?.naturalHeight || 0);
    if (!iw || !ih) return;

    const cw = canvas.width;
    const ch = canvas.height;
    const { scale, dx, dy } = computeDisplayTransform(iw, ih, cw, ch, viewFocusBox, viewZoom, viewCenter);

    const nativeVideoPlayback = simpleVideoMode && useVideo && !viewFocusBox && viewZoom <= 1.02;
    ctx.clearRect(0, 0, cw, ch);
    if (!nativeVideoPlayback) {
      ctx.fillStyle = '#0a0a0a';
      ctx.fillRect(0, 0, cw, ch);
      if (useVideo) ctx.drawImage(video!, dx, dy, iw * scale, ih * scale);
      else if (img) ctx.drawImage(img, dx, dy, iw * scale, ih * scale);
    }

    const map = (x: number, y: number) => ({ x: dx + x * scale, y: dy + y * scale });
    const openedKeyframe = isDoctorKeyframeOpen(
      doctorKeyframes,
      activeDoctorKeyframeId,
      useVideo ? video!.currentTime : videoTime,
      isPlaying,
    );
    const hideKeyframeSeg = doctorKeyframes.length > 0 && !openedKeyframe;
    const trackingPlayback = Boolean(
      !hideKeyframeSeg
      && doctorKeyframes.length === 0
      && simpleVideoMode
      && useVideo
      && !frameFrozen
      && trackingPrepared
      && videoFrameOverrides.length > 1,
    );
    const trackedFrame = useVideo && videoFrameOverrides.length
      ? nearestOverrideFrame(
        videoFrameOverrides,
        video!.currentTime,
        trackingPlayback ? 0.35 : 0.12,
      )
      : null;
    const liveLesion = hideKeyframeSeg
      ? []
      : (pointsRef.current.length >= 3 ? pointsRef.current : generatedLesionRef.current);
    const liveWall = hideKeyframeSeg
      ? []
      : (wallPointsRef.current.length >= 3 ? wallPointsRef.current : wallPoints);
    const liveExtraLesions = hideKeyframeSeg ? [] : extraLesionPolygons;
    const liveLumen = lumenPolygonRef.current.length >= 3 ? lumenPolygonRef.current : lumenPolygon;
    const displayPoints = trackingPlayback && trackedFrame?.mask_polygon?.length
      ? trackedFrame.mask_polygon
      : liveLesion;
    const displayLumenPoly = hideKeyframeSeg
      ? []
      : lumenEditMode
        ? liveLumen
        : (trackingPlayback && trackedFrame?.lumen_polygon && trackedFrame.lumen_polygon.length >= 3)
          ? trackedFrame.lumen_polygon
          : liveLumen;
    // Once a lumen mask exists (current frame or tracked), drop the box prompt so the
    // canvas shows the true contour only — no lingering rectangle around the mask.
    const displayLumenBox = hideKeyframeSeg
      ? null
      : displayLumenPoly.length >= 3
        ? null
        : (!lumenEditMode && trackedFrame?.lumen_bbox)
          ? trackedFrame.lumen_bbox
          : (lumenBoxRef.current || lumenBox);
    const historyPreviewFrame = historyPreview && useVideo
      ? nearestOverrideFrame(
        historyPreview.override.video_frames || [],
        video!.currentTime,
        Number.POSITIVE_INFINITY,
      )
      : null;
    const historyPreviewPoints = historyPreviewFrame?.mask_polygon?.length
      ? historyPreviewFrame.mask_polygon
      : historyPreview?.override.mask_polygon || [];
    const historyPreviewRoiBox = historyPreviewFrame?.roi_bbox || historyPreview?.override.roi_bbox;
    const historyPreviewLumenPoly = historyPreviewFrame?.lumen_polygon?.length
      ? historyPreviewFrame.lumen_polygon
      : historyPreview?.lumen_override?.lumen_polygon || [];
    const historyPreviewLumenBox = historyPreviewFrame?.lumen_bbox || historyPreview?.lumen_override?.lumen_bbox;

    const drawPoly = (poly: number[][], fill: string, stroke: string, dashed = false) => {
      if (poly.length < 2) return;
      strokeClosedPolyline(ctx, poly, map);
      if (fill && fill !== 'transparent') {
        ctx.fillStyle = fill;
        ctx.fill();
      }
      ctx.strokeStyle = stroke;
      ctx.lineWidth = CONTOUR_LINE_WIDTH;
      ctx.setLineDash(dashed ? [7, 5] : []);
      ctx.stroke();
      ctx.setLineDash([]);
    };

    // Hairline beads: hit target stays much larger than the drawn radius.
    const hr = Math.max(1.05, Math.min(1.7, 1.25 / Math.sqrt(Math.max(scale, 0.15))));
    const handleCountFor = (poly: number[][], cap: number) => (
      adaptiveHandleCount(poly, Math.min(VISIBLE_HANDLE_COUNT, cap))
    );

    const drawHandles = (
      poly: number[][],
      count: number,
      fill: string,
      layer: DragLayer,
    ) => {
      if (poly.length < 3) return;
      controlIndices(poly.length, handleCountFor(poly, count)).forEach((i) => {
        const p = poly[i];
        if (!p) return;
        const { x, y } = map(p[0], p[1]);
        const active = dragLayerRef.current === layer && dragIndexRef.current === i;
        ctx.beginPath();
        ctx.arc(x, y, active ? hr + 0.8 : hr, 0, Math.PI * 2);
        if (active) {
          ctx.fillStyle = 'rgba(251, 191, 36, 0.88)';
          ctx.fill();
          ctx.strokeStyle = 'rgba(15, 23, 42, 0.85)';
          ctx.lineWidth = 1;
          ctx.stroke();
        } else {
          ctx.strokeStyle = layer === 'lumen'
            ? COLOR_LUMEN_STROKE
            : layer === 'wall'
              ? COLOR_WALL_STROKE
              : COLOR_LESION_STROKE;
          ctx.lineWidth = 1;
          ctx.stroke();
        }
      });
    };

    if (simpleVideoMode) {
      if (liveWall.length >= 3) {
        drawPoly(liveWall, COLOR_WALL_FILL, COLOR_WALL_STROKE);
      }
      drawPoly(displayPoints, COLOR_LESION_FILL, COLOR_LESION_STROKE);
      liveExtraLesions.forEach((poly) => {
        if (poly.length >= 3) drawPoly(poly, 'rgba(45, 212, 191, 0.10)', '#5eead4');
      });
      if (simpleEditMode || mode === 'hard' || mode === 'brush') {
        if (refineTarget === 'lumen' && displayLumenPoly.length >= 3) {
          drawHandles(displayLumenPoly, Math.min(VISIBLE_HANDLE_COUNT, LUMEN_CTRL_COUNT), COLOR_LUMEN_HANDLE, 'lumen');
        } else if (simpleEditLayer === 'wall' && liveWall.length >= 3) {
          drawHandles(liveWall, Math.min(VISIBLE_HANDLE_COUNT, WALL_CTRL_COUNT), COLOR_WALL_HANDLE, 'wall');
        } else if (displayPoints.length >= 3) {
          drawHandles(displayPoints, Math.min(VISIBLE_HANDLE_COUNT, LESION_CTRL_COUNT), COLOR_LESION_HANDLE, 'lesion');
        }
      }
      if (samBoxPreview) {
        const a = map(samBoxPreview.x1, samBoxPreview.y1);
        const b = map(samBoxPreview.x2, samBoxPreview.y2);
        ctx.fillStyle = 'rgba(94, 184, 196, 0.05)';
        ctx.fillRect(Math.min(a.x, b.x), Math.min(a.y, b.y), Math.abs(b.x - a.x), Math.abs(b.y - a.y));
        ctx.strokeStyle = COLOR_LESION_STROKE;
        ctx.lineWidth = 1;
        ctx.strokeRect(Math.min(a.x, b.x), Math.min(a.y, b.y), Math.abs(b.x - a.x), Math.abs(b.y - a.y));
      }
    } else {
      if (liveWall.length >= 3) {
        drawPoly(liveWall, COLOR_WALL_FILL, COLOR_WALL_STROKE);
      }
      drawPoly(displayPoints, COLOR_LESION_FILL, COLOR_LESION_STROKE);
      liveExtraLesions.forEach((poly) => {
        if (poly.length >= 3) drawPoly(poly, 'rgba(45, 212, 191, 0.10)', '#5eead4');
      });
      drawHandles(liveWall, WALL_CTRL_COUNT, COLOR_WALL_HANDLE, 'wall');
      drawHandles(displayPoints, LESION_CTRL_COUNT, COLOR_LESION_HANDLE, 'lesion');

      if (samBoxPreview) {
        const a = map(samBoxPreview.x1, samBoxPreview.y1);
        const b = map(samBoxPreview.x2, samBoxPreview.y2);
        ctx.strokeStyle = 'rgba(168, 85, 247, 0.95)';
        ctx.lineWidth = 1.5;
        ctx.setLineDash([4, 3]);
        ctx.strokeRect(
          Math.min(a.x, b.x),
          Math.min(a.y, b.y),
          Math.abs(b.x - a.x),
          Math.abs(b.y - a.y),
        );
        ctx.setLineDash([]);
      }
    }

    const drawPromptStroke = (stroke: ActiveSamStroke) => {
      if (stroke.points.length < 2) return;
      const first = map(stroke.points[0][0], stroke.points[0][1]);
      ctx.save();
      ctx.beginPath();
      ctx.moveTo(first.x, first.y);
      for (const point of stroke.points.slice(1)) {
        const mapped = map(point[0], point[1]);
        ctx.lineTo(mapped.x, mapped.y);
      }
      if (stroke.kind === 'lasso') ctx.closePath();
      ctx.strokeStyle = stroke.target === 'lumen'
        ? (stroke.label === 'negative' ? '#fb7185' : '#e879f9')
        : (stroke.label === 'negative' ? '#fb7185' : '#4ade80');
      ctx.lineWidth = Math.max(2, Math.min(8, stroke.width * scale));
      ctx.lineCap = 'round';
      ctx.lineJoin = 'round';
      ctx.setLineDash(stroke.kind === 'lasso' ? [8, 5] : []);
      ctx.stroke();
      ctx.setLineDash([]);
      ctx.beginPath();
      ctx.arc(first.x, first.y, 4, 0, Math.PI * 2);
      ctx.fillStyle = ctx.strokeStyle;
      ctx.fill();
      ctx.strokeStyle = '#f8fafc';
      ctx.lineWidth = 1;
      ctx.stroke();
      ctx.restore();
    };

    for (const stroke of promptStrokes) drawPromptStroke(stroke);
    if (activePromptStroke) drawPromptStroke(activePromptStroke);

    for (const c of samClicks) {
      const { x, y } = map(c.x, c.y);
      ctx.beginPath();
      ctx.arc(x, y, 5, 0, Math.PI * 2);
      ctx.fillStyle = c.label === 'negative' ? '#f43f5e' : '#22c55e';
      ctx.fill();
      ctx.strokeStyle = '#fff';
      ctx.lineWidth = 1.5;
      ctx.stroke();
    }

    for (const c of nnInteractiveClicks) {
      const { x, y } = map(c.x, c.y);
      const positive = c.label !== 'negative';
      ctx.save();
      ctx.beginPath();
      ctx.arc(x, y, 6, 0, Math.PI * 2);
      ctx.fillStyle = positive ? 'rgba(34, 197, 94, 0.9)' : 'rgba(244, 63, 94, 0.9)';
      ctx.fill();
      ctx.strokeStyle = '#fff';
      ctx.lineWidth = 1.5;
      ctx.stroke();
      ctx.beginPath();
      ctx.moveTo(x - 3, y);
      ctx.lineTo(x + 3, y);
      if (positive) {
        ctx.moveTo(x, y - 3);
        ctx.lineTo(x, y + 3);
      }
      ctx.strokeStyle = '#0f172a';
      ctx.lineWidth = 1.2;
      ctx.stroke();
      ctx.restore();
    }

    if (displayLumenPoly.length >= 3) {
      drawPoly(displayLumenPoly, COLOR_LUMEN_FILL, COLOR_LUMEN_STROKE);
    }
    const lumenBoxIsProxy = Boolean(displayLumenBox) && displayLumenPoly.length < 3;
    if (displayLumenBox) {
      const a = map(displayLumenBox.x1, displayLumenBox.y1);
      const b = map(displayLumenBox.x2, displayLumenBox.y2);
      const left = Math.min(a.x, b.x);
      const top = Math.min(a.y, b.y);
      const width = Math.abs(b.x - a.x);
      const height = Math.abs(b.y - a.y);
      if (COLOR_LUMEN_BOX_FILL !== 'transparent') {
        ctx.fillStyle = COLOR_LUMEN_BOX_FILL;
        ctx.fillRect(left, top, width, height);
      }
      ctx.strokeStyle = lumenEditMode ? COLOR_LUMEN_STROKE : COLOR_LUMEN_BOX_STROKE;
      ctx.lineWidth = lumenEditMode || lumenBoxIsProxy ? 1.35 : 1.05;
      // Solid box only — dashed proxy frame reads as unexplained orange/green clutter.
      ctx.setLineDash([]);
      ctx.strokeRect(left, top, width, height);
      if (lumenBoxIsProxy) {
        const label = zh ? '胃腔框代理' : 'Lumen box proxy';
        ctx.save();
        ctx.font = '10px ui-monospace, SFMono-Regular, Menlo, monospace';
        const labelWidth = ctx.measureText(label).width + 10;
        ctx.fillStyle = 'rgba(88, 28, 135, 0.72)';
        ctx.fillRect(left, Math.max(4, top - 16), labelWidth, 14);
        ctx.fillStyle = '#fdf4ff';
        ctx.fillText(label, left + 5, Math.max(14, top - 6));
        ctx.restore();
      }
      if (lumenEditMode) {
        for (const [x, y] of [
          [left, top],
          [left + width, top],
          [left, top + height],
          [left + width, top + height],
        ]) {
          ctx.beginPath();
          ctx.arc(x, y, hr, 0, Math.PI * 2);
          ctx.fillStyle = COLOR_LUMEN_HANDLE;
          ctx.fill();
          ctx.strokeStyle = HANDLE_STROKE;
          ctx.lineWidth = 1;
          ctx.stroke();
        }
      }
    }

    // Keep the ultrasound canvas clean: no green/orange LayerBridge dashes, contact arcs,
    // breakthrough rings, or outward arrows on the main view. Wall-layer graphics stay in
    // the side analysis card only (meeting: avoid "一眼乱分析" overlay clutter).
    if (polygonDraft.length >= 1) {
      ctx.beginPath();
      polygonDraft.forEach((pt, i) => {
        const p = map(pt[0], pt[1]);
        if (i === 0) ctx.moveTo(p.x, p.y);
        else ctx.lineTo(p.x, p.y);
      });
      ctx.strokeStyle = 'rgba(251, 191, 36, 0.95)';
      ctx.lineWidth = 1.5;
      ctx.setLineDash([5, 3]);
      ctx.stroke();
      ctx.setLineDash([]);
      polygonDraft.forEach((pt) => {
        const p = map(pt[0], pt[1]);
        ctx.beginPath();
        ctx.arc(p.x, p.y, 3.5, 0, Math.PI * 2);
        ctx.fillStyle = 'rgba(251, 191, 36, 0.95)';
        ctx.fill();
      });
    }

    const relationGeometry = computeLesionLumenGeometry(displayPoints, displayLumenPoly, displayLumenBox);
    if (relationGeometry.relation === 'overlap' && displayPoints.length >= 3) {
      const traceLesion = () => {
        strokeClosedPolyline(ctx, displayPoints, map);
      };
      const traceLumen = () => {
        if (displayLumenPoly.length >= 3) {
          strokeClosedPolyline(ctx, displayLumenPoly, map);
          return true;
        }
        if (!displayLumenBox) return false;
        const topLeft = map(displayLumenBox.x1, displayLumenBox.y1);
        const bottomRight = map(displayLumenBox.x2, displayLumenBox.y2);
        ctx.beginPath();
        ctx.rect(
          Math.min(topLeft.x, bottomRight.x),
          Math.min(topLeft.y, bottomRight.y),
          Math.abs(bottomRight.x - topLeft.x),
          Math.abs(bottomRight.y - topLeft.y),
        );
        return true;
      };
      if (traceLumen()) {
        // Soft overlap wash only — no hatch / dashed guides.
        ctx.save();
        ctx.clip();
        traceLesion();
        ctx.clip();
        ctx.fillStyle = 'rgba(251, 191, 36, 0.08)';
        ctx.fillRect(0, 0, cw, ch);
        ctx.restore();
      }
    }

    if (viewFocusMode === 'overlap' && overlapFocus) {
      const topLeft = map(overlapFocus.x1, overlapFocus.y1);
      const bottomRight = map(overlapFocus.x2, overlapFocus.y2);
      const left = Math.min(topLeft.x, bottomRight.x);
      const top = Math.min(topLeft.y, bottomRight.y);
      const width = Math.abs(bottomRight.x - topLeft.x);
      const height = Math.abs(bottomRight.y - topLeft.y);
      ctx.save();
      ctx.strokeStyle = '#fde68a';
      ctx.lineWidth = 2.5;
      ctx.setLineDash([7, 4]);
      ctx.strokeRect(left, top, width, height);
      ctx.setLineDash([]);
      const label = zh ? '接触/突破分析区放大' : 'Contact / breakthrough zoom';
      ctx.font = '600 10px ui-monospace, SFMono-Regular, Menlo, monospace';
      const labelWidth = ctx.measureText(label).width + 10;
      ctx.fillStyle = 'rgba(15, 23, 42, 0.72)';
      ctx.fillRect(left, Math.max(4, top - 17), labelWidth, 15);
      ctx.fillStyle = '#fde68a';
      ctx.fillText(label, left + 5, Math.max(15, top - 6));
      ctx.restore();
    }

    // Reader simple mode: keep the ultrasound canvas clean (no top-left status legend).
    // Non-simple / research mode still gets a compact geometry cue when useful.
    if (!simpleVideoMode && (displayPoints.length >= 3 || displayLumenPoly.length >= 3 || displayLumenBox) && relationGeometry.available) {
      const lumenSource = displayLumenPoly.length >= 3
        ? (zh ? '胃腔轮廓' : 'Lumen contour')
        : displayLumenBox
          ? (zh ? '胃腔框代理' : 'Lumen box proxy')
          : (zh ? '胃腔未标注' : 'Lumen missing');
      const legendLines = [
        lumenSource,
        geometryRelationText(relationGeometry, zh),
        geometryQualityText(relationGeometry, zh),
      ].filter(Boolean);
      ctx.save();
      ctx.font = '10px ui-monospace, SFMono-Regular, Menlo, monospace';
      const legendWidth = Math.max(...legendLines.map((line) => ctx.measureText(line).width)) + 16;
      const legendHeight = legendLines.length * 13 + 10;
      const legendX = 10;
      const legendY = 10;
      ctx.fillStyle = 'rgba(2, 6, 23, 0.84)';
      ctx.fillRect(legendX, legendY, legendWidth, legendHeight);
      ctx.strokeStyle = 'rgba(232, 121, 249, 0.35)';
      ctx.strokeRect(legendX, legendY, legendWidth, legendHeight);
      legendLines.forEach((line, index) => {
        ctx.fillStyle = '#f8fafc';
        ctx.fillText(line, legendX + 8, legendY + 14 + index * 13);
      });
      ctx.restore();
    }

    // Draw the lesion last so lumen fills, boxes, and wall marks stay behind it.
    // Keep this pass thin; a thick halo hides the ultrasound lesion.
    if (displayPoints.length >= 3 && (
      displayLumenPoly.length >= 3
      || displayLumenBox
      || points.length < 3
    )) {
      ctx.save();
      ctx.lineCap = 'round';
      ctx.lineJoin = 'round';
      strokeClosedPolyline(ctx, displayPoints, map);
      ctx.strokeStyle = 'rgba(15, 23, 42, 0.22)';
      ctx.lineWidth = 0.9;
      ctx.stroke();
      strokeClosedPolyline(ctx, displayPoints, map);
      ctx.strokeStyle = COLOR_LESION_STROKE;
      ctx.lineWidth = CONTOUR_LINE_WIDTH;
      ctx.stroke();
      if (simpleEditMode && simpleEditLayer === 'lesion') {
        drawHandles(displayPoints, Math.min(VISIBLE_HANDLE_COUNT, LESION_CTRL_COUNT), COLOR_LESION_HANDLE, 'lesion');
      }
      ctx.restore();
    }

    // Historical versions are preview-only: they are rendered with a dashed
    // yellow overlay and never replace the editable current mask.
    if (historyPreview && (
      historyPreviewPoints.length >= 3
      || historyPreviewRoiBox
      || historyPreviewLumenPoly.length >= 3
      || historyPreviewLumenBox
    )) {
      ctx.save();
      ctx.globalAlpha = 0.9;
      if (historyPreviewPoints.length >= 3) {
        drawPoly(historyPreviewPoints, 'rgba(250, 204, 21, 0.08)', '#facc15', true);
      }
      if (historyPreviewLumenPoly.length >= 3) {
        drawPoly(historyPreviewLumenPoly, 'rgba(244, 114, 182, 0.06)', '#f9a8d4', true);
      }
      if (historyPreviewRoiBox) {
        const a = map(historyPreviewRoiBox.x1, historyPreviewRoiBox.y1);
        const b = map(historyPreviewRoiBox.x2, historyPreviewRoiBox.y2);
        ctx.strokeStyle = '#fde68a';
        ctx.lineWidth = 1.5;
        ctx.setLineDash([5, 4]);
        ctx.strokeRect(
          Math.min(a.x, b.x),
          Math.min(a.y, b.y),
          Math.abs(b.x - a.x),
          Math.abs(b.y - a.y),
        );
        ctx.setLineDash([]);
      }
      if (historyPreviewLumenBox) {
        const a = map(historyPreviewLumenBox.x1, historyPreviewLumenBox.y1);
        const b = map(historyPreviewLumenBox.x2, historyPreviewLumenBox.y2);
        ctx.strokeStyle = '#f9a8d4';
        ctx.lineWidth = 1.5;
        ctx.setLineDash([5, 4]);
        ctx.strokeRect(
          Math.min(a.x, b.x),
          Math.min(a.y, b.y),
          Math.abs(b.x - a.x),
          Math.abs(b.y - a.y),
        );
        ctx.setLineDash([]);
      }
      const previewLabel = zh
        ? `历史预览: ${historyPreview.action || '版本'}`
        : `History preview: ${historyPreview.action || 'version'}`;
      ctx.font = '10px ui-monospace, SFMono-Regular, Menlo, monospace';
      const labelWidth = ctx.measureText(previewLabel).width + 12;
      ctx.fillStyle = 'rgba(120, 53, 15, 0.9)';
      ctx.fillRect(10, Math.max(10, ch - 28), labelWidth, 18);
      ctx.fillStyle = '#fef3c7';
      ctx.fillText(previewLabel, 16, Math.max(23, ch - 15));
      ctx.restore();
    }

    const lens = magnifierOn ? magnifierPosRef.current : null;
    const lensSource = useVideo ? video : img;
    if (lens && lensSource) {
      const lensR = Math.max(56, Math.min(96, Math.round(Math.min(cw, ch) * 0.12)));
      const zoom = 2.75;
      const magScale = scale * zoom;
      ctx.save();
      ctx.beginPath();
      ctx.arc(lens.cx, lens.cy, lensR, 0, Math.PI * 2);
      ctx.clip();
      ctx.fillStyle = '#0a0a0a';
      ctx.fillRect(lens.cx - lensR, lens.cy - lensR, lensR * 2, lensR * 2);
      ctx.drawImage(
        lensSource,
        lens.cx - lens.ix * magScale,
        lens.cy - lens.iy * magScale,
        iw * magScale,
        ih * magScale,
      );
      // Light contour cues inside the lens so breakthrough edges stay readable.
      if (displayPoints.length >= 3) {
        strokeClosedPolyline(ctx, displayPoints, (x, y) => ({
          x: lens.cx + (x - lens.ix) * magScale,
          y: lens.cy + (y - lens.iy) * magScale,
        }));
        ctx.strokeStyle = 'rgba(103, 232, 249, 0.85)';
        ctx.lineWidth = 1.5;
        ctx.stroke();
      }
      if (displayLumenPoly.length >= 3) {
        strokeClosedPolyline(ctx, displayLumenPoly, (x, y) => ({
          x: lens.cx + (x - lens.ix) * magScale,
          y: lens.cy + (y - lens.iy) * magScale,
        }));
        ctx.strokeStyle = 'rgba(232, 121, 249, 0.75)';
        ctx.lineWidth = 1.25;
        ctx.stroke();
      }
      ctx.restore();
      ctx.beginPath();
      ctx.arc(lens.cx, lens.cy, lensR, 0, Math.PI * 2);
      ctx.strokeStyle = 'rgba(255, 255, 255, 0.9)';
      ctx.lineWidth = 2;
      ctx.stroke();
      ctx.beginPath();
      ctx.arc(lens.cx, lens.cy, lensR + 3, 0, Math.PI * 2);
      ctx.strokeStyle = 'rgba(14, 165, 233, 0.55)';
      ctx.lineWidth = 2;
      ctx.stroke();
      ctx.font = '600 10px ui-monospace, SFMono-Regular, Menlo, monospace';
      const lensLabel = zh ? `放大镜 x${zoom.toFixed(1)}` : `Lens x${zoom.toFixed(1)}`;
      const labelW = ctx.measureText(lensLabel).width + 10;
      ctx.fillStyle = 'rgba(2, 6, 23, 0.82)';
      ctx.fillRect(lens.cx - labelW / 2, lens.cy + lensR + 6, labelW, 16);
      ctx.fillStyle = '#e0f2fe';
      ctx.fillText(lensLabel, lens.cx - labelW / 2 + 5, lens.cy + lensR + 17);
    }

    const sculpt = lumenSculptModeRef.current;
    const paintStrokePreview = lumenPaintStrokeRef.current;
    const brushPt = paintCursorRef.current;
    if (sculpt && (brushPt || paintStrokePreview?.length)) {
      const r = Math.max(3, paintRadiusRef.current * scale);
      const add = sculpt.endsWith('add');
      ctx.strokeStyle = add ? 'rgba(190, 242, 100, 0.72)' : 'rgba(251, 113, 133, 0.72)';
      ctx.fillStyle = add ? 'rgba(163, 230, 53, 0.18)' : 'rgba(251, 113, 133, 0.18)';
      ctx.lineWidth = r * 2;
      ctx.lineCap = 'round';
      ctx.lineJoin = 'round';
      if (paintStrokePreview && paintStrokePreview.length >= 2) {
        ctx.beginPath();
        paintStrokePreview.forEach((pt, i) => {
          const p = map(pt[0], pt[1]);
          if (i === 0) ctx.moveTo(p.x, p.y);
          else ctx.lineTo(p.x, p.y);
        });
        ctx.stroke();
      } else {
        const src = paintStrokePreview?.[0] || brushPt;
        if (src) {
          const p = map(src[0], src[1]);
          ctx.beginPath();
          ctx.arc(p.x, p.y, r, 0, Math.PI * 2);
          ctx.fill();
          ctx.lineWidth = 1.2;
          ctx.stroke();
        }
      }
    }

    const bandCols = ['#7dd3fc', '#c4b5fd', '#86efac', '#fcd34d', '#fb7185'];
    if (!hideKeyframeSeg && wallLayerBands.length) {
      wallLayerBands.forEach((band, index) => {
        if (band.length < 2) return;
        const mask = wallLayerImaginary[index] || [];
        let drawing = false;
        let dashed: boolean | null = null;
        ctx.strokeStyle = bandCols[index % bandCols.length];
        ctx.globalAlpha = 0.86;
        ctx.lineWidth = 0.8;
        ctx.lineCap = 'round';
        ctx.lineJoin = 'round';
        const flush = () => {
          if (drawing) ctx.stroke();
          drawing = false;
        };
        band.forEach((point, pointIndex) => {
          const mapped = map(point[0], point[1]);
          const nextDash = Boolean(mask[pointIndex]);
          if (dashed !== nextDash) {
            flush();
            ctx.beginPath();
            ctx.setLineDash(nextDash ? [3.2, 2.4] : []);
            ctx.moveTo(mapped.x, mapped.y);
            dashed = nextDash;
            drawing = true;
            return;
          }
          ctx.lineTo(mapped.x, mapped.y);
          drawing = true;
        });
        flush();
        ctx.setLineDash([]);
        ctx.globalAlpha = 1;
        if (!isPlaying) {
          const step = Math.max(1, Math.round(band.length / 8));
          for (let pointIndex = 0; pointIndex < band.length; pointIndex += step) {
            const handle = map(band[pointIndex][0], band[pointIndex][1]);
            ctx.beginPath();
            ctx.arc(handle.x, handle.y, 2.6, 0, Math.PI * 2);
            ctx.fillStyle = bandCols[index % bandCols.length];
            ctx.fill();
          }
        }
      });
    }

    if (!hideKeyframeSeg && wallEchoClarify?.available && wallEchoClarify.quad.length >= 4) {
      ctx.beginPath();
      wallEchoClarify.quad.forEach((point, index) => {
        const mapped = map(point[0], point[1]);
        if (index === 0) ctx.moveTo(mapped.x, mapped.y);
        else ctx.lineTo(mapped.x, mapped.y);
      });
      ctx.closePath();
      ctx.strokeStyle = 'rgba(244, 114, 182, 0.95)';
      ctx.lineWidth = 1.5;
      ctx.setLineDash([4, 3]);
      ctx.stroke();
      ctx.setLineDash([]);
      ctx.fillStyle = 'rgba(244, 114, 182, 0.12)';
      ctx.fill();
      const origin = map(wallEchoClarify.origin[0], wallEchoClarify.origin[1]);
      ctx.beginPath();
      ctx.arc(origin.x, origin.y, 4.2, 0, Math.PI * 2);
      ctx.fillStyle = 'rgba(251, 113, 133, 0.95)';
      ctx.fill();
    }
    const livePaint = hideKeyframeSeg ? [] : (wallPaintStrokeRef.current || wallPaintStroke);
    if (livePaint && livePaint.length) {
      ctx.beginPath();
      livePaint.forEach((point, index) => {
        const mapped = map(point[0], point[1]);
        if (index === 0) ctx.moveTo(mapped.x, mapped.y);
        else ctx.lineTo(mapped.x, mapped.y);
      });
      ctx.strokeStyle = 'rgba(251, 191, 36, 0.42)';
      ctx.lineWidth = Math.max(4, wallBrushRadiusRef.current * 2 * scale);
      ctx.lineCap = 'round';
      ctx.lineJoin = 'round';
      ctx.stroke();
    }

    const pickMarks = hideKeyframeSeg ? [] : wallPickFlanksRef.current;
    if (pickMarks.length) {
      pickMarks.forEach((point, index) => {
        const mapped = map(point[0], point[1]);
        ctx.beginPath();
        ctx.arc(mapped.x, mapped.y, 7, 0, Math.PI * 2);
        ctx.fillStyle = 'rgba(251, 191, 36, 0.95)';
        ctx.fill();
        ctx.strokeStyle = 'rgba(15, 23, 42, 0.9)';
        ctx.lineWidth = 1.4;
        ctx.stroke();
        ctx.fillStyle = 'rgba(15, 23, 42, 0.95)';
        ctx.font = '11px sans-serif';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText(String(index + 1), mapped.x, mapped.y + 0.5);
      });
    }

    const focusMarks = hideKeyframeSeg ? [] : analysisFocusPointsRef.current;
    if (focusMarks.length) {
      focusMarks.forEach((point, index) => {
        const mapped = map(point[0], point[1]);
        ctx.beginPath();
        ctx.moveTo(mapped.x, mapped.y - 7);
        ctx.lineTo(mapped.x + 6, mapped.y);
        ctx.lineTo(mapped.x, mapped.y + 7);
        ctx.lineTo(mapped.x - 6, mapped.y);
        ctx.closePath();
        ctx.fillStyle = 'rgba(251, 113, 133, 0.95)';
        ctx.fill();
        ctx.strokeStyle = 'rgba(15, 23, 42, 0.9)';
        ctx.lineWidth = 1.2;
        ctx.stroke();
        ctx.fillStyle = 'rgba(254, 226, 226, 0.95)';
        ctx.font = '10px sans-serif';
        ctx.textAlign = 'left';
        ctx.textBaseline = 'bottom';
        ctx.fillText(zh ? `分析${index + 1}` : `F${index + 1}`, mapped.x + 8, mapped.y - 4);
      });
    }

  }, [points, extraLesionPolygons, wallPoints, imgLoaded, dragIndex, dragLayer, mediaMode, frameFrozen, trackingPrepared, wallAnalysisOpen, samClicks, promptStrokes, activePromptStroke, nnInteractiveClicks, samBoxPreview, simpleVideoMode, simpleEditMode, simpleEditLayer, refineTarget, mode, videoFrameOverrides, lumenBox, lumenPolygon, lumenEditMode, viewFocusBox, viewFocusMode, overlapFocus, layerResult, historyPreview, magnifierOn, polygonDraft, zh, doctorKeyframes, activeDoctorKeyframeId, isPlaying, videoTime, lumenSculptMode, paintRadius, wallPickMode, wallPickFlanks, wallPaintMode, wallPaintStroke, wallLayerBands, wallLayerImaginary, wallBrushRadius, wallEchoClarify, viewZoom, viewCenter, analysisFocusPoints]);

  useEffect(() => {
    redrawRef.current = redraw;
  }, [redraw]);
  useEffect(() => {
    maybeTrackWhilePlayingRef.current = maybeTrackWhilePlaying;
  }, [maybeTrackWhilePlaying]);
  useEffect(() => {
    redraw();
  }, [redraw]);
  useEffect(() => {
    if (!open || mediaMode !== 'image' || !patient?.image_url) return;
    const img = new Image();
    img.crossOrigin = 'anonymous';
    img.onload = () => {
      imgRef.current = img;
      setImgLoaded(true);
      const canvas = canvasRef.current;
      const container = containerRef.current;
      if (canvas && container) {
        const rect = container.getBoundingClientRect();
        canvas.width = Math.max(320, Math.floor(rect.width));
        canvas.height = Math.max(240, Math.floor(rect.height));
      }
      try {
        const c = document.createElement('canvas');
        c.width = img.naturalWidth;
        c.height = img.naturalHeight;
        const ctx = c.getContext('2d');
        if (ctx) {
          ctx.drawImage(img, 0, 0);
          setFrameDataUrl(c.toDataURL('image/jpeg', 0.92));
        }
      } catch {
        /* CORS / tainted canvas — analysis without echo rays still works */
      }
      redraw();
    };
    img.onerror = () => {
      setMessage(zh ? '图像加载失败' : 'Failed to load image');
      setImgLoaded(false);
    };
    img.src = patient.image_url;
  }, [open, mediaMode, patient?.image_url, patient?.id, zh, redraw]);

  useEffect(() => {
    if (!open || mediaMode !== 'video' || !videoUrl) return;
    const video = videoRef.current;
    if (!video) return;
    setFrameFrozen(false);
    frameFrozenRef.current = false;
    const stopPlaybackLoop = () => {
      if (playbackRafRef.current !== null) {
        cancelAnimationFrame(playbackRafRef.current);
        playbackRafRef.current = null;
      }
    };
    const hasPlaybackOverlay = () => {
      if (doctorKeyframesRef.current.length > 0) return false;
      return (
        pointsRef.current.length >= 3
        || lumenPolygonRef.current.length >= 3
        || Boolean(lumenBoxRef.current)
        || videoFrameOverridesRef.current.length > 0
      );
    };
    const syncCanvasLayer = () => {
      const canvas = canvasRef.current;
      if (!canvas) return;
      const hide = !video.paused && !hasPlaybackOverlay();
      canvas.style.visibility = hide ? 'hidden' : 'visible';
    };
    const playbackTick = () => {
      playbackRafRef.current = null;
      if (video.paused || video.ended || scrubbingRef.current) return;
      const now = performance.now();
      const t = video.currentTime || 0;
      if (now - playbackUiAtRef.current >= 100) {
        playbackUiAtRef.current = now;
        paintProgressUi(t);
      }
      if (!hasPlaybackOverlay()) {
        syncCanvasLayer();
        return;
      }
      if (!frameFrozenRef.current && dragIndexRef.current === null) {
        if (now - lastScrubRedrawAtRef.current >= 80) {
          lastScrubRedrawAtRef.current = now;
          redrawRef.current();
        }
        if (trackOnPlayRef.current) void maybeTrackWhilePlayingRef.current();
      }
      playbackRafRef.current = requestAnimationFrame(playbackTick);
    };
    const startPlaybackLoop = () => {
      if (playbackRafRef.current === null) {
        playbackRafRef.current = requestAnimationFrame(playbackTick);
      }
    };
    const onMeta = () => {
      setVideoDuration(video.duration || 0);
      video.defaultPlaybackRate = videoPlaybackRateRef.current;
      video.playbackRate = videoPlaybackRateRef.current;
      syncFrameFromVideo({ force: true });
      redraw();
    };
    const onTime = () => {
      if (scrubbingRef.current) return;
      if (frameFrozenRef.current || dragIndexRef.current !== null) {
        if (dragIndexRef.current === null && video.paused) {
          const t = video.currentTime || 0;
          paintProgressUi(t);
          setVideoTime(t);
        }
        return;
      }
      const t = video.currentTime || 0;
      paintProgressUi(t);
      if (!video.paused && hasPlaybackOverlay()) startPlaybackLoop();
    };
    const onPlay = () => {
      persistOpenKeyframeContoursRef.current();
      if (doctorKeyframesRef.current.length > 0) {
        clearKeyframeOverlayRef.current();
      }
      setIsPlaying(true);
      setFrameFrozen(false);
      frameFrozenRef.current = false;
      syncCanvasLayer();
      if (hasPlaybackOverlay()) startPlaybackLoop();
      else paintProgressUi(video.currentTime || 0);
      recordDoctorOpRef.current('cine_play', { video_time_sec: video.currentTime || 0, playing: true, frozen: false });
    };
    const onPause = () => {
      if (scrubbingRef.current) {
        setIsPlaying(false);
        stopPlaybackLoop();
        return;
      }
      setIsPlaying(false);
      stopPlaybackLoop();
      const t = video.currentTime || 0;
      setVideoTime(t);
      paintProgressUi(t, { forceSlider: true });
      syncFrameFromVideo({ force: true });
      if (canvasRef.current) canvasRef.current.style.visibility = 'visible';
      redrawRef.current();
      recordDoctorOpRef.current('cine_pause', { video_time_sec: t, playing: false });
    };
    const onEnded = () => {
      setIsPlaying(false);
      stopPlaybackLoop();
      const t = video.currentTime || 0;
      setVideoTime(t);
      paintProgressUi(t, { forceSlider: true });
      if (videoFrameOverridesRef.current.length) {
        void persistOverrideRef.current('video_tracking_complete');
      }
    };
    video.addEventListener('loadedmetadata', onMeta);
    video.addEventListener('timeupdate', onTime);
    video.addEventListener('play', onPlay);
    video.addEventListener('pause', onPause);
    video.addEventListener('ended', onEnded);
    video.muted = true;
    video.playsInline = true;
    video.src = videoUrl;
    video.load();
    return () => {
      stopPlaybackLoop();
      video.removeEventListener('loadedmetadata', onMeta);
      video.removeEventListener('timeupdate', onTime);
      video.removeEventListener('play', onPlay);
      video.removeEventListener('pause', onPause);
      video.removeEventListener('ended', onEnded);
    };
  }, [open, mediaMode, paintProgressUi, videoUrl, syncFrameFromVideo]);

  useEffect(() => {
    if (!open || mediaMode !== 'video' || !videoUrl) return;
    const video = videoRef.current as (HTMLVideoElement & {
      requestVideoFrameCallback?: (cb: (now: number, meta: { mediaTime: number }) => void) => number;
      cancelVideoFrameCallback?: (handle: number) => void;
    } | null);
    if (!video?.requestVideoFrameCallback) return;
    setVideoFps(DEFAULT_CINE_FPS);
    const times: number[] = [];
    let handle = 0;
    let done = false;
    const onFrame = (_now: number, meta: { mediaTime: number }) => {
      if (done) return;
      times.push(meta.mediaTime);
      const fps = estimateCineFpsFromMediaTimes(times);
      if (fps && times.length >= 6) {
        done = true;
        setVideoFps(fps);
        return;
      }
      if (times.length < 16) {
        handle = video.requestVideoFrameCallback?.(onFrame) || 0;
      }
    };
    const start = () => {
      if (done) return;
      times.length = 0;
      handle = video.requestVideoFrameCallback?.(onFrame) || 0;
    };
    video.addEventListener('playing', start);
    if (!video.paused) start();
    return () => {
      done = true;
      video.removeEventListener('playing', start);
      if (handle && video.cancelVideoFrameCallback) video.cancelVideoFrameCallback(handle);
    };
  }, [open, mediaMode, videoUrl]);

  useEffect(() => {
    if (!open || mediaMode !== 'video' || !videoUrl) return;
    const video = videoRef.current;
    if (!video) return;
    const key = `${patient?.id || ''}::${videoUrl}`;
    const tryPlay = () => {
      if (autoplayAttemptRef.current === key) return;
      autoplayAttemptRef.current = key;
      video.muted = true;
      video.playsInline = true;
      void video.play().catch(() => {
        setMessage(
          zh
            ? '请点「播放」看视频。空格先暂停，再按一次才标关键帧，只看这一帧'
            : 'Tap Play to watch. Space pauses first; press again to mark',
        );
      });
    };
    if (video.readyState >= 3) {
      tryPlay();
      return undefined;
    }
    video.addEventListener('canplay', tryPlay, { once: true });
    return () => video.removeEventListener('canplay', tryPlay);
  }, [open, mediaMode, patient?.id, videoUrl, zh]);

  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;
    video.defaultPlaybackRate = videoPlaybackRate;
    video.playbackRate = videoPlaybackRate;
  }, [videoPlaybackRate, videoUrl]);

  useEffect(() => {
    if (!open) return;
    const resizeCanvas = () => {
      const canvas = canvasRef.current;
      const container = containerRef.current;
      if (!canvas || !container) return;
      const rect = container.getBoundingClientRect();
      const nextWidth = Math.max(320, Math.floor(rect.width));
      const nextHeight = Math.max(240, Math.floor(rect.height));
      if (canvas.width !== nextWidth || canvas.height !== nextHeight) {
        canvas.width = nextWidth;
        canvas.height = nextHeight;
      }
      redraw();
    };
    const observer = typeof ResizeObserver !== 'undefined'
      ? new ResizeObserver(() => requestAnimationFrame(resizeCanvas))
      : null;
    if (observer && containerRef.current) observer.observe(containerRef.current);
    window.addEventListener('resize', resizeCanvas);
    resizeCanvas();
    return () => {
      observer?.disconnect();
      window.removeEventListener('resize', resizeCanvas);
    };
  }, [open, redraw]);

  const canvasToImage = useCallback((e: { clientX: number; clientY: number }, options?: { clamp?: boolean }): number[] | null => {
    const canvas = canvasRef.current;
    if (!canvas) return null;
    const video = videoRef.current;
    const img = imgRef.current;
    const useVideo = mediaMode === 'video' && video && video.videoWidth > 0;
    const iw = useVideo ? video!.videoWidth : (img?.naturalWidth || 0);
    const ih = useVideo ? video!.videoHeight : (img?.naturalHeight || 0);
    if (!iw || !ih) return null;
    const rect = canvas.getBoundingClientRect();
    const scaleX = canvas.width / rect.width;
    const scaleY = canvas.height / rect.height;
    const cx = (e.clientX - rect.left) * scaleX;
    const cy = (e.clientY - rect.top) * scaleY;
    const { scale, dx, dy } = computeDisplayTransform(
      iw,
      ih,
      canvas.width,
      canvas.height,
      viewFocusBox,
      viewZoomRef.current,
      viewCenterRef.current,
    );
    const ix = (cx - dx) / scale;
    const iy = (cy - dy) / scale;
    if (ix < 0 || iy < 0 || ix > iw || iy > ih) {
      if (!options?.clamp) return null;
      return [Math.max(0, Math.min(iw, ix)), Math.max(0, Math.min(ih, iy))];
    }
    return [ix, iy];
  }, [mediaMode, viewFocusBox]);

  const resetViewZoom = useCallback(() => {
    viewZoomRef.current = 1;
    viewCenterRef.current = null;
    viewPanDragRef.current = null;
    setViewZoom(1);
    setViewCenter(null);
    setViewFocusBox(null);
    setViewFocusMode(null);
  }, []);

  const applyViewZoomAt = useCallback((imagePt: number[], nextZoom: number) => {
    const zoom = Math.max(1, Math.min(8, nextZoom));
    viewZoomRef.current = zoom;
    viewCenterRef.current = { x: imagePt[0], y: imagePt[1] };
    setViewZoom(zoom);
    setViewCenter({ x: imagePt[0], y: imagePt[1] });
    if (zoom > 1.02) {
      setViewFocusBox(null);
      setViewFocusMode(null);
    }
  }, []);

  const hitThreshold = useCallback(() => {
    const canvas = canvasRef.current;
    const video = videoRef.current;
    const img = imgRef.current;
    const useVideo = mediaMode === 'video' && video && video.videoWidth > 0;
    const iw = useVideo ? video!.videoWidth : (img?.naturalWidth || 1);
    const ih = useVideo ? video!.videoHeight : (img?.naturalHeight || 1);
    if (!canvas) return 24;
    const rect = canvas.getBoundingClientRect();
    // Hit target stays larger than the drawn handle so small/transparent handles remain grabable.
    const scale = Math.min(canvas.width / iw, canvas.height / ih) * (rect.width / Math.max(1, canvas.width));
    return Math.max(16, 12 / Math.max(scale, 1e-6));
  }, [mediaMode]);

  const invalidateNnInteractiveSession = useCallback((options: { abort?: boolean } = {}) => {
    if (options.abort !== false) {
      nnInteractiveAbortRef.current?.abort();
      nnInteractiveAbortRef.current = null;
    }
    nnInteractiveRequestRef.current += 1;
    setNnInteractiveBusy(false);
    nnInteractiveSessionRef.current = { key: '', id: '', initialized: false };
  }, []);

  const clearSamPrompts = useCallback(() => {
    samClicksRef.current = [];
    setSamClicks([]);
    setNnInteractiveClicks([]);
    invalidateNnInteractiveSession({ abort: true });
    if (promptStrokeRafRef.current != null) {
      cancelAnimationFrame(promptStrokeRafRef.current);
      promptStrokeRafRef.current = null;
    }
    pendingPromptPointRef.current = null;
    promptStrokesRef.current = [];
    activePromptStrokeRef.current = null;
    setPromptStrokes([]);
    setActivePromptStroke(null);
    samBoxDragRef.current = null;
    setSamBoxPreview(null);
  }, [invalidateNnInteractiveSession]);

  useEffect(() => () => {
    nnInteractiveAbortRef.current?.abort();
    nnInteractiveAbortRef.current = null;
    if (promptStrokeRafRef.current != null) {
      cancelAnimationFrame(promptStrokeRafRef.current);
      promptStrokeRafRef.current = null;
    }
    if (dragRafRef.current != null) {
      cancelAnimationFrame(dragRafRef.current);
      dragRafRef.current = null;
    }
  }, []);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const onWheel = (event: WheelEvent) => {
      if (wallPaintModeRef.current) {
        event.preventDefault();
        const step = event.deltaY > 0 ? -1 : 1;
        setWallBrushRadius((value) => Math.max(3, Math.min(22, value + step)));
        return;
      }
      if (lumenSculptModeRef.current) {
        event.preventDefault();
        const step = event.deltaY > 0 ? -2 : 2;
        setPaintRadius((r) => Math.max(6, Math.min(48, r + step)));
        return;
      }
      event.preventDefault();
      const imgPt = canvasToImage(event, { clamp: true });
      if (!imgPt) return;
      const factor = event.deltaY > 0 ? 0.86 : 1.16;
      applyViewZoomAt(imgPt, viewZoomRef.current * factor);
    };
    canvas.addEventListener('wheel', onWheel, { passive: false });
    return () => canvas.removeEventListener('wheel', onWheel);
  }, [applyViewZoomAt, canvasToImage, imgLoaded, mediaMode, videoUrl, open, simpleVideoMode]);

  const stopInteractivePrompt = useCallback(() => {
    invalidateNnInteractiveSession({ abort: true });
    setNnInteractiveMode(false);
    setNnInteractiveTarget('lesion');
    setSam31RefineTarget(null);
    setActiveSamPromptLabel('positive');
    clearSamPrompts();
  }, [clearSamPrompts, invalidateNnInteractiveSession]);

  const pauseVideoOnCurrentFrame = useCallback((opts?: { timeSec?: number }) => {
    if (mediaMode !== 'video') return;
    const video = videoRef.current;
    if (!video) return;
    const hold = opts?.timeSec != null && Number.isFinite(opts.timeSec)
      ? opts.timeSec
      : snapCineTimeToFrame(video.currentTime || 0, videoFpsRef.current);
    if (!video.paused) {
      video.pause();
    }
    setIsPlaying(false);
    setTrackOnPlay(false);
    if (Math.abs((video.currentTime || 0) - hold) > 0.04) {
      video.currentTime = hold;
    }
    setVideoTime(hold);
    if (canvasRef.current) canvasRef.current.style.visibility = 'visible';
  }, [mediaMode]);

  const requireOpenKeyframeForBox = useCallback((): boolean => {
    if (!simpleVideoMode || mediaMode !== 'video') return true;
    pauseVideoOnCurrentFrame();
    const video = videoRef.current;
    const currentTime = video?.currentTime ?? videoTime;
    const frames = doctorKeyframesRef.current;
    if (isDoctorKeyframeOpen(frames, activeDoctorKeyframeIdRef.current, currentTime, false)) {
      return true;
    }
    const nearby = frames.find((kf) => Math.abs(kf.timeSec - currentTime) <= DOCTOR_KEYFRAME_DEDUP_SEC);
    if (nearby) {
      setActiveDoctorKeyframeId(nearby.id);
      activeDoctorKeyframeIdRef.current = nearby.id;
      if (video && Math.abs((video.currentTime || 0) - nearby.timeSec) > DOCTOR_KEYFRAME_OPEN_EPS_SEC) {
        video.currentTime = nearby.timeSec;
        setVideoTime(nearby.timeSec);
      }
      return true;
    }
    if (!video?.videoWidth) {
      setMessage(zh ? '视频帧未就绪，稍后再框选' : 'Video frame not ready');
      return false;
    }
    const gate = canAddDoctorKeyframe(frames, currentTime);
    if (!gate.ok) {
      setMessage(
        gate.reason === 'full'
          ? (zh ? `关键帧已满（${DOCTOR_KEYFRAME_MAX}），请先点开一条再框选` : `Keyframe strip full (${DOCTOR_KEYFRAME_MAX}); open one first`)
          : (zh ? '该时刻已有关键帧，可直接框选' : 'This time already has a keyframe; draw the box'),
      );
      return gate.reason === 'duplicate';
    }
    const timeSec = Number((currentTime || 0).toFixed(3));
    const id = newDoctorKeyframeId(timeSec);
    const frame = captureDoctorFrameFromVideo(video);
    const hasLesion = pointsRef.current.length >= 3;
    const next: DoctorKeyframe = {
      id,
      timeSec,
      thumbDataUrl: frame?.thumbDataUrl || null,
      segStatus: hasLesion ? 'ready' : 'idle',
      lesionPolygon: hasLesion ? clonePoly(pointsRef.current) : undefined,
      lumenBox: lumenBoxRef.current || undefined,
      lumenPolygon: lumenPolygonRef.current.length >= 3 ? clonePoly(lumenPolygonRef.current) : undefined,
      wallPolygon: wallPointsRef.current.length >= 3 ? clonePoly(wallPointsRef.current) : undefined,
      wallLayerReadout: wallLayerReadoutRef.current,
      error: null,
    };
    persistOpenKeyframeContours();
    setDoctorKeyframes((prev) => {
      const sorted = sortDoctorKeyframes([...prev, next]);
      doctorKeyframesRef.current = sorted;
      return sorted;
    });
    setActiveDoctorKeyframeId(id);
    activeDoctorKeyframeIdRef.current = id;
    setSimpleToolsOpen(true);
    recordDoctorOp('keyframe_mark', {
      operation: 'keyframe_mark',
      tool: 'keyframe_mark',
      keyframe_id: id,
      source: 'box_lesion',
    });
    setMessage(zh ? '已将当前帧作为关键帧，请拖框选病灶' : 'This frame is now the keyframe; drag a box on the lesion');
    return true;
  }, [mediaMode, pauseVideoOnCurrentFrame, persistOpenKeyframeContours, recordDoctorOp, simpleVideoMode, videoTime, zh]);
  requireOpenKeyframeForBoxRef.current = requireOpenKeyframeForBox;

  const applyDoctorLesionBox = useCallback((box: { x1: number; y1: number; x2: number; y2: number }) => {
    const poly = boxToClosedPolygon(box, 8);
    const existing = pointsRef.current;
    const keepExtra = keepExtraLesionRef.current
      && existing.length >= 3
      && extraLesionPolygonsRef.current.length < 4;
    pushEditUndo();
    if (keepExtra) {
      const kept = [...extraLesionPolygonsRef.current, clonePoly(existing)];
      extraLesionPolygonsRef.current = kept;
      setExtraLesionPolygons(kept);
    }
    keepExtraLesionRef.current = false;
    setKeepExtraLesion(false);
    pointsRef.current = poly;
    generatedLesionRef.current = poly;
    setPoints(poly);
    setSimplePromptBox(box);
    setSimpleEditMode(false);
    setSimpleEditLayer('lesion');
    setActiveLayer('lesion');
    setLumenEditMode(false);
    persistOpenKeyframeContours({ refined: true });
    const extraCount = extraLesionPolygonsRef.current.length;
    setMessage(
      extraCount && keepExtra
        ? (zh ? `已保留上一处病灶，正在分割第 ${extraCount + 1} 处…` : `Kept the previous lesion; segmenting lesion ${extraCount + 1}…`)
        : (zh ? '已框选病灶，正在自动分割…' : 'Lesion box set; auto-segmenting…'),
    );
  }, [persistOpenKeyframeContours, pushEditUndo, zh]);

  const enterSimpleBoxPrompt = useCallback(() => {
    stopInteractivePrompt();
    setMode('sam');
    setSimplePromptMode('box');
    armLesionBox(true);
    setSimpleEditMode(false);
    setLumenEditMode(false);
    setLumenSculptMode(null);
    setSimpleEditLayer('lesion');
    setActiveLayer('lesion');
    setSimplePromptBox(null);
    setSam31RefineTarget(null);
    setTrackOnPlay(false);
    setBoxAutoSegBusy(false);
    let keyframeOk = true;
    try {
      keyframeOk = requireOpenKeyframeForBox();
    } catch {
      keyframeOk = false;
    }
    recordDoctorOp('tool_switch', { layer: 'lesion', operation: 'tool_switch', tool: 'box_lesion' });
    if (!keyframeOk) return;
    setMessage(
      pointsRef.current.length >= 3
        ? (keepExtraLesionRef.current
          ? (zh ? '再拖一个框会留下上一处病灶' : 'A new box keeps the previous lesion')
          : (zh ? '再拖一个框会替换当前病灶。多个灶请先点「再框一灶」' : 'A new box replaces this lesion. Tap Add lesion first for a second mass'))
        : (zh ? '请拖出矩形框选病灶' : 'Drag a box around the lesion'),
    );
  }, [armLesionBox, recordDoctorOp, requireOpenKeyframeForBox, stopInteractivePrompt, zh]);

  const enterSimpleContourEdit = useCallback((layer: ContourLayer) => {
    stopInteractivePrompt();
    if (simpleVideoMode && mediaMode === 'video' && videoFrameOverridesRef.current.length) {
      const currentTime = videoRef.current?.currentTime || videoTime;
      const trackedFrame = nearestOverrideFrame(videoFrameOverridesRef.current, currentTime, Number.POSITIVE_INFINITY);
      if (trackedFrame?.mask_polygon?.length) {
        pointsRef.current = clonePoly(trackedFrame.mask_polygon);
        setPoints(pointsRef.current);
      }
      if (trackedFrame?.lumen_polygon?.length) {
        lumenPolygonRef.current = clonePoly(trackedFrame.lumen_polygon);
        setLumenPolygon(lumenPolygonRef.current);
      }
      if (trackedFrame?.lumen_bbox) {
        lumenBoxRef.current = trackedFrame.lumen_bbox;
        setLumenBox(trackedFrame.lumen_bbox);
      }
    }
    setMode('soft');
    setSimplePromptMode('box');
    armLesionBox(false);
    setSimpleEditLayer(layer);
    setActiveLayer(layer);
    setSimpleEditMode(true);
    setLumenEditMode(false);
    setTrackOnPlay(false);
    setMessage('');
  }, [mediaMode, simpleVideoMode, stopInteractivePrompt, videoTime]);

  const toggleSimpleContourEdit = useCallback(() => {
    if (simpleEditMode) {
      setSimpleEditMode(false);
      setSimplePromptMode('box');
      void persistOverrideRef.current('doctor_edit', { silent: true });
      markActiveDoctorKeyframeRefined();
      setMessage(zh ? '已完成控制点编辑；可点顶中「辅助分析」生成证据' : 'Contour edit finished; use top Assist to generate evidence');
      return;
    }
    enterSimpleContourEdit(points.length >= 3 ? 'lesion' : 'wall');
  }, [enterSimpleContourEdit, markActiveDoctorKeyframeRefined, points.length, simpleEditMode, zh]);

  const applyWallExtension = useCallback((opts?: { silent?: boolean; doctorFlanks?: number[][] | null }) => {
    pauseVideoOnCurrentFrame();
    const lesion = pointsRef.current;
    if (lesion.length < 3) {
      if (!opts?.silent) {
        setMessage(zh ? '请先框选并分割病灶，再接胃壁' : 'Box and segment the lesion before joining the wall');
      }
      return false;
    }
    const doctorFlanks = (opts?.doctorFlanks && opts.doctorFlanks.length >= 2)
      ? opts.doctorFlanks
      : (wallPickFlanksRef.current.length >= 2 ? wallPickFlanksRef.current : null);
    if (!canAutoJoinWall({ flanks: doctorFlanks, paintedWall: wallPointsRef.current })) {
      if (!opts?.silent) {
        setMessage(zh
          ? '请先从邻近看得见的胃壁起笔，或点两侧再接。不要从肿块正中自动空想分层。'
          : 'Paint from adjacent visible wall, or mark both flanks first. Do not invent layers in the mass center.');
      }
      return false;
    }
    const result = extendWallThroughLesion({
      lesion,
      lumen: lumenPolygonRef.current,
      lumenBox: lumenBoxRef.current,
      existingWall: wallPointsRef.current.length >= 3 ? wallPointsRef.current : null,
      doctorFlanks,
    });
    if (!result.available) {
      if (!opts?.silent) setMessage(zh ? result.noteZh : result.noteEn);
      return false;
    }
    pushEditUndo();
    wallPointsRef.current = result.wall;
    wallExtensionMaskRef.current = result.wall.map(() => false);
    setWallPoints(result.wall);
    setWallExtensionNote(zh ? result.noteZh : result.noteEn);
    setWallExtensionStats({
      overshootPx: result.overshootPx,
      remainPx: result.remainPx,
      source: result.source,
    });
    setActiveLayer('wall');
    setSimpleEditLayer('wall');
    setSimpleEditMode(false);
    setLumenEditMode(false);
    setWallPickMode(false);
    wallPickModeRef.current = false;
    armLesionBox(false);
    recordDoctorOp('layer_switch', {
      layer: 'wall',
      operation: 'wall_extend',
      tool: result.source,
      doctor_flanks: doctorFlanks?.length || 0,
      overshoot_px: result.overshootPx,
      remain_px: result.remainPx,
    });
    const readout = judgeWallLayerBreach({
      remainPx: result.remainPx,
      overshootPx: result.overshootPx,
      thicknessPx: result.overshootPx != null && result.remainPx != null
        ? result.overshootPx + result.remainPx + 8
        : 12,
      source: 'geometry',
    });
    const frame = captureFrameGray();
    applyWallLayerVisuals(result.wall, readout, frame);
    refreshWallEchoClarify(frame);
    persistOpenKeyframeContours({ refined: true });
    if (!opts?.silent) {
      const live = wallLayerReadoutRef.current || readout;
      setMessage(zh ? `${result.noteZh} ${live.noteZh}` : `${result.noteEn} ${live.noteEn}`);
    }
    redrawRef.current?.();
    return true;
  }, [armLesionBox, pauseVideoOnCurrentFrame, persistOpenKeyframeContours, pushEditUndo, recordDoctorOp, zh]);

  const startWallExtensionTool = useCallback(() => {
    pauseVideoOnCurrentFrame();
    if (!requireOpenKeyframeForBox()) return;
    if (pointsRef.current.length < 3) {
      setMessage(zh ? '请先框选并分割病灶，再延长胃壁' : 'Box and segment the lesion before extending the wall');
      return;
    }
    if (wallPickModeRef.current) {
      wallPickModeRef.current = false;
      setWallPickMode(false);
      applyWallExtension();
      return;
    }
    armLesionBox(false);
    setLumenEditMode(false);
    setLumenSculptMode(null);
    setSimpleEditMode(false);
    wallPickFlanksRef.current = [];
    setWallPickFlanks([]);
    wallPickModeRef.current = true;
    setWallPickMode(true);
    setActiveLayer('wall');
    setSimpleEditLayer('wall');
    recordDoctorOp('tool_switch', { layer: 'wall', operation: 'tool_switch', tool: 'wall_flank_pick' });
    setMessage(zh
      ? `请点两侧看得见的正常${anatomyTargetMeta(wallLayerTargetRef.current).shortZh}。系统按${anatomyTargetMeta(wallLayerTargetRef.current).lineZh}接过去。再点一次则自动接。`
      : `Click the two visible flanks. Join uses your ${wallLayerTargetRef.current}-layer setting. Click again to auto-join.`);
    redrawRef.current?.();
  }, [applyWallExtension, armLesionBox, pauseVideoOnCurrentFrame, recordDoctorOp, requireOpenKeyframeForBox, zh]);

  const captureFrameGray = useCallback((): { gray: Float32Array; width: number; height: number } | null => {
    const video = videoRef.current;
    const img = imgRef.current;
    const width = mediaMode === 'video' && video?.videoWidth ? video.videoWidth : (img?.naturalWidth || 0);
    const height = mediaMode === 'video' && video?.videoHeight ? video.videoHeight : (img?.naturalHeight || 0);
    if (!width || !height) return null;
    const canvas = document.createElement('canvas');
    canvas.width = width;
    canvas.height = height;
    const ctx = canvas.getContext('2d');
    if (!ctx) return null;
    if (mediaMode === 'video' && video) ctx.drawImage(video, 0, 0);
    else if (img) ctx.drawImage(img, 0, 0);
    else return null;
    const pixels = ctx.getImageData(0, 0, width, height).data;
    const gray = new Float32Array(width * height);
    for (let index = 0; index < gray.length; index += 1) {
      const i = index * 4;
      gray[index] = 0.299 * pixels[i] + 0.587 * pixels[i + 1] + 0.114 * pixels[i + 2];
    }
    return { gray, width, height };
  }, [mediaMode]);

  const applyWallLayerVisuals = useCallback((
    wall: number[][],
    readout: WallLayerReadout,
    frame?: { gray: Float32Array; width: number; height: number } | null,
    traced?: { layer: 1 | 2 | 3 | 4 | 5; curve: number[][]; imaginaryMask: boolean[] }[] | null,
  ) => {
    const target = wallLayerTargetRef.current;
    let bands: number[][][] = [];
    if (traced && traced.length) {
      bands = traced.map((layer) => layer.curve);
      setWallLayerBands(bands);
      wallLayerBandsRef.current = bands;
      setWallLayerImaginary(traced.map((layer) => layer.imaginaryMask));
      wallLayerImaginaryRef.current = traced.map((layer) => layer.imaginaryMask);
    } else {
      const lumen = lumenPolygonRef.current;
      const center: [number, number] | null = lumen.length >= 3
        ? [
          lumen.reduce((sum, point) => sum + point[0], 0) / lumen.length,
          lumen.reduce((sum, point) => sum + point[1], 0) / lumen.length,
        ]
        : null;
      bands = clusterLayersAlongWall({
        wall,
        center,
        lesion: pointsRef.current,
        gray: frame?.gray || null,
        width: frame?.width,
        height: frame?.height,
        thicknessPx: readout.thicknessPx || 12,
        layerCount: target,
      });
      setWallLayerBands(bands);
      wallLayerBandsRef.current = bands;
      setWallLayerImaginary([]);
      wallLayerImaginaryRef.current = [];
    }
    const ids = traced?.length
      ? traced.map((layer) => layer.layer)
      : doctorClinicalIds(target);
    const curves = bands.map((curve, index) => ({
      layer: ids[index] || 5,
      curve,
    }));
    const next = attachLayerInterrupts(
      readout,
      frame?.gray,
      frame?.width,
      frame?.height,
      curves,
      target,
      {
        visibility: wallVisibilityRef.current,
        anchorMode: serosaAnchorModeRef.current,
      },
    );
    setWallLayerReadout(next);
    wallLayerReadoutRef.current = next;
  }, []);

  const applyWallLayerTarget = useCallback((count: WallLayerTarget) => {
    setWallLayerTarget(count);
    wallLayerTargetRef.current = count;
    persistCaseDraftRef.current({ wall_target_layers: count });
    const wall = wallPointsRef.current;
    const readout = wallLayerReadoutRef.current;
    if (wall.length < 3 || !readout) return;
    const frame = captureFrameGray();
    applyWallLayerVisuals(wall, readout, frame);
    persistOpenKeyframeContours({ refined: true });
    setMessage(zh
      ? `已改按${anatomyTargetMeta(count).lineZh}重算草稿（不定 cT）`
      : `Recomputed the draft on the ${anatomyTargetMeta(count).lineEn} (not a definite cT)`);
    redrawRef.current?.();
  }, [applyWallLayerVisuals, captureFrameGray, persistOpenKeyframeContours, zh]);

  const recheckKeyframesWallPixels = useCallback(async (ids: string[]) => {
    const video = videoRef.current;
    if (!video || !ids.length) return 0;
    const home = video.currentTime;
    const target = wallLayerTargetRef.current;
    let count = 0;
    for (const id of ids) {
      const kf = findDoctorKeyframeById(doctorKeyframesRef.current, id);
      if (!kf?.wallPolygon || kf.wallPolygon.length < 3) continue;
      await seekVideoForAgent(video, kf.timeSec);
      const frame = captureFrameGray();
      if (!frame) continue;
      const next = recheckWallInterruptDraft({
        wall: kf.wallPolygon,
        gray: frame.gray,
        width: frame.width,
        height: frame.height,
        targetLayers: kf.wallLayerReadout?.targetLayers || target,
        readout: kf.wallLayerReadout
          ? {
            ...judgeWallLayerBreach({
              remainPx: kf.wallLayerReadout.remainPx,
              source: 'propagated',
            }),
            layersBreached: kf.wallLayerReadout.layersBreached,
            deepestZh: kf.wallLayerReadout.deepestZh,
            deepestEn: kf.wallLayerReadout.deepestEn,
            ratio: kf.wallLayerReadout.ratio,
            source: 'propagated',
            thicknessPx: 12,
          }
          : judgeWallLayerBreach({ remainPx: null, source: 'propagated' }),
        bands: kf.wallLayerBands,
        lesion: kf.lesionPolygon,
        lumen: kf.lumenPolygon,
      });
      setDoctorKeyframes((prev) => {
        const frames = prev.map((item) => (
          item.id === id
            ? {
              ...item,
              wallLayerReadout: { ...next.readout, source: 'propagated' as const },
              wallLayerBands: next.bands,
            }
            : item
        ));
        doctorKeyframesRef.current = frames;
        return frames;
      });
      count += 1;
    }
    await seekVideoForAgent(video, home);
    syncFrameFromVideo({ force: true });
    return count;
  }, [captureFrameGray]);

  const dropLastExtraLesion = useCallback(() => {
    const extras = extraLesionPolygonsRef.current;
    if (!extras.length) return;
    pushEditUndo();
    const next = extras.slice(0, -1);
    extraLesionPolygonsRef.current = next;
    setExtraLesionPolygons(next);
    persistOpenKeyframeContours({ refined: true });
    setMessage(zh
      ? `已去掉一处额外病灶，还剩 ${next.length + (pointsRef.current.length >= 3 ? 1 : 0)} 处`
      : `Removed one extra lesion; ${next.length + (pointsRef.current.length >= 3 ? 1 : 0)} remain`);
    redrawRef.current?.();
  }, [persistOpenKeyframeContours, pushEditUndo, zh]);

  const refreshWallEchoClarify = useCallback((frame?: { gray: Float32Array; width: number; height: number } | null) => {
    const pixels = frame || captureFrameGray();
    if (!pixels || wallPointsRef.current.length < 3) {
      setWallEchoClarify(null);
      return null;
    }
    const next = clarifyDeepestEcho({
      gray: pixels.gray,
      width: pixels.width,
      height: pixels.height,
      lesion: pointsRef.current,
      lumen: lumenPolygonRef.current,
      wall: wallPointsRef.current,
      brushRadius: wallBrushRadiusRef.current,
    });
    setWallEchoClarify(next.available ? next : null);
    return next.available ? next : null;
  }, [captureFrameGray]);

  const echoPreview = useMemo(() => {
    if (!wallEchoClarify?.available) return { raw: null as string | null, clustered: null as string | null };
    return {
      raw: grayCropToDataUrl(wallEchoClarify.original, wallEchoClarify.cropW, wallEchoClarify.cropH),
      clustered: grayCropToDataUrl(wallEchoClarify.clarified, wallEchoClarify.cropW, wallEchoClarify.cropH),
    };
  }, [wallEchoClarify]);

  const hideWallOnOtherFrames = doctorKeyframes.length > 0 && !isDoctorKeyframeOpen(
    doctorKeyframes,
    activeDoctorKeyframeId,
    videoTime,
    isPlaying,
  );

  const commitWallPaintStroke = useCallback((stroke: number[][]) => {
    if (stroke.length < 4) {
      setMessage(zh ? '笔画太短。请沿看得见的正常胃壁再画一段，笔刷要能包住几层。' : 'Stroke too short. Paint a longer visible wall span so the brush wraps the layers.');
      return false;
    }
    const frame = captureFrameGray();
    if (!frame) {
      setMessage(zh ? '当前帧像素还没准备好，请稍后再画' : 'Frame pixels are not ready yet');
      return false;
    }
    const traced = traceWallLayersFromPaint({
      gray: frame.gray,
      width: frame.width,
      height: frame.height,
      stroke,
      brushRadius: wallBrushRadiusRef.current,
      lesion: pointsRef.current,
      lumen: lumenPolygonRef.current,
      targetLayers: wallLayerTargetRef.current,
    });
    const result = traced.available
      ? {
        available: true,
        wall: traced.wall,
        remainPx: traced.remainPx,
        overshootPx: traced.overshootPx,
        thicknessPx: traced.thicknessPx,
        noteZh: traced.noteZh,
        noteEn: traced.noteEn,
      }
      : extendWallByPixels({
        gray: frame.gray,
        width: frame.width,
        height: frame.height,
        stroke,
        lesion: pointsRef.current,
        lumen: lumenPolygonRef.current,
      });
    if (!result.available) {
      setMessage(zh ? result.noteZh : result.noteEn);
      return false;
    }
    pushEditUndo();
    wallPointsRef.current = result.wall;
    wallExtensionMaskRef.current = result.wall.map(() => false);
    setWallPoints(result.wall);
    const readout = traced.available
      ? readoutFromTrace(traced)
      : judgeWallLayerBreach({
        remainPx: result.remainPx,
        overshootPx: result.overshootPx,
        thicknessPx: result.thicknessPx,
        source: 'pixel',
      });
    applyWallLayerVisuals(result.wall, readout, frame, traced.available ? traced.layers : null);
    refreshWallEchoClarify(frame);
    setWallPaintMode(false);
    wallPaintModeRef.current = false;
    setWallPaintStroke([]);
    wallPaintStrokeRef.current = null;
    setActiveLayer('wall');
    setSimpleEditLayer('wall');
    setSimpleEditMode(false);
    persistOpenKeyframeContours({ refined: true });
    markActiveDoctorKeyframeRefined();
    void persistOverrideRef.current('doctor_edit', { silent: true });
    window.dispatchEvent(new CustomEvent('gastric:open-wall-layers', { detail: { open: true } }));
    recordDoctorOp('wall_edit', {
      layer: 'wall',
      operation: 'wall_paint_extend',
      tool: 'pixel_ridge',
      point_count: result.wall.length,
      remain_px: result.remainPx,
      overshoot_px: result.overshootPx,
      layers_breached: readout.layersBreached,
      painted_layers: readout.paintedLayers,
      mucosa_breached: readout.mucosaBreached,
    });
    setMessage(zh ? `${result.noteZh} ${readout.noteZh}` : `${result.noteEn} ${readout.noteEn}`);
    redrawRef.current?.();
    const openId = activeDoctorKeyframeIdRef.current;
    if (openId) maybeAutoPropagateRef.current?.(openId);
    return true;
  }, [applyWallLayerVisuals, captureFrameGray, markActiveDoctorKeyframeRefined, persistOpenKeyframeContours, pushEditUndo, recordDoctorOp, zh]);

  const startWallPaintTool = useCallback(() => {
    if (wallPaintModeRef.current) {
      wallPaintModeRef.current = false;
      setWallPaintMode(false);
      setWallPaintStroke([]);
      wallPaintStrokeRef.current = null;
      setMessage(zh ? '已取消预期走行线' : 'Expected-trajectory paint cancelled');
      return;
    }
    pauseVideoOnCurrentFrame();
    if (!requireOpenKeyframeForBox()) return;
    armLesionBox(false);
    setLumenEditMode(false);
    setLumenSculptMode(null);
    setWallPickMode(false);
    wallPickModeRef.current = false;
    setAnalysisFocusMode(false);
    analysisFocusModeRef.current = false;
    setSimpleEditMode(false);
    wallPaintModeRef.current = true;
    setWallPaintMode(true);
    setWallPaintStroke([]);
    wallPaintStrokeRef.current = null;
    setActiveLayer('wall');
    recordDoctorOp('tool_switch', { layer: 'wall', operation: 'tool_switch', tool: 'wall_paint' });
    setMessage(paintLineHint(wallLayerTargetRef.current, zh));
  }, [armLesionBox, pauseVideoOnCurrentFrame, recordDoctorOp, requireOpenKeyframeForBox, zh]);

  const startAnalysisFocusTool = useCallback(() => {
    if (analysisFocusModeRef.current) {
      analysisFocusModeRef.current = false;
      setAnalysisFocusMode(false);
      setMessage(zh ? '已取消分析焦点' : 'Analysis focus cancelled');
      return;
    }
    pauseVideoOnCurrentFrame();
    if (!requireOpenKeyframeForBox()) return;
    armLesionBox(false);
    setLumenEditMode(false);
    setWallPickMode(false);
    wallPickModeRef.current = false;
    setWallPaintMode(false);
    wallPaintModeRef.current = false;
    setSimpleEditMode(false);
    analysisFocusModeRef.current = true;
    setAnalysisFocusMode(true);
    recordDoctorOp('tool_switch', { layer: 'wall', operation: 'tool_switch', tool: 'analysis_focus' });
    setMessage(analysisFocusHint(zh));
  }, [armLesionBox, pauseVideoOnCurrentFrame, recordDoctorOp, requireOpenKeyframeForBox, zh]);

  const enterLumenBoxEdit = useCallback((reason?: string) => {
    pauseVideoOnCurrentFrame();
    if (!requireOpenKeyframeForBox()) return;
    stopInteractivePrompt();
    setMode('soft');
    setSimplePromptMode('box');
    armLesionBox(false);
    setSimpleEditMode(false);
    setLumenEditMode(true);
    setLumenSculptMode(null);
    setTrackOnPlay(false);
    // Next drag always starts a new box so a leftover/YOLO box covering the
    // frame cannot steal the gesture as a move.
    lumenBoxFreshDrawRef.current = true;
    recordDoctorOp('tool_switch', { layer: 'lumen', operation: 'tool_switch', tool: 'lumen_box' });
    setMessage(
      zh
        ? `已点亮「框选胃腔」：光标是拖框标记，拖出矩形后自动分割。${reason ? ` ${reason}` : ''}`
        : `Box lumen is armed: cursor is the drag marker; release auto-segments.${reason ? ` ${reason}` : ''}`,
    );
  }, [pauseVideoOnCurrentFrame, recordDoctorOp, requireOpenKeyframeForBox, stopInteractivePrompt, zh]);

  const toggleLumenBoxEdit = useCallback(() => {
    if (lumenEditMode) {
      setLumenEditMode(false);
      setSimplePromptMode('box');
      setMessage(zh ? '已退出胃腔框编辑；需要时可再点「调整框」继续改' : 'Left lumen box edit; tap Edit box again anytime to continue');
      return;
    }
    enterLumenBoxEdit();
  }, [enterLumenBoxEdit, lumenEditMode, zh]);

  const ensureLumenPolygonForRefine = useCallback((): number[][] => {
    if (lumenPolygonRef.current.length >= 3) return lumenPolygonRef.current;
    const box = lumenBoxRef.current || lumenBox;
    if (!box) return [];
    const seeded = boxToClosedPolygon(box, 32);
    lumenPolygonRef.current = seeded;
    setLumenPolygon(seeded);
    return seeded;
  }, [lumenBox]);

  const frameSizeForPaint = useCallback((): { width: number; height: number } | null => {
    const video = videoRef.current;
    const img = imgRef.current;
    if (mediaMode === 'video' && video?.videoWidth && video.videoHeight) {
      return { width: video.videoWidth, height: video.videoHeight };
    }
    if (img?.naturalWidth && img.naturalHeight) {
      return { width: img.naturalWidth, height: img.naturalHeight };
    }
    return null;
  }, [mediaMode]);

  const commitLayerPaint = useCallback((
    stroke: number[][],
    op: PaintOp,
    layer: 'lesion' | 'lumen',
    basePolygon?: number[][],
  ) => {
    const size = frameSizeForPaint();
    if (!size || stroke.length < 1) return false;
    const current = basePolygon && basePolygon.length >= 3
      ? basePolygon
      : (layer === 'lumen'
        ? (lumenPolygonRef.current.length >= 3
          ? lumenPolygonRef.current
          : ensureLumenPolygonForRefine())
        : pointsRef.current);
    if (op === 'subtract' && current.length < 3) return false;
    const next = applyPaintToPolygon(
      current,
      stroke,
      op,
      size.width,
      size.height,
      paintRadiusRef.current,
    );
    if (next.length < 3) {
      setMessage(
        layer === 'lumen'
          ? (zh ? '这次涂抹会把胃腔涂空，已保持原轮廓' : 'That stroke would erase the lumen; kept the previous contour')
          : (zh ? '这次涂抹会把病灶涂空，已保持原轮廓' : 'That stroke would erase the lesion; kept the previous contour'),
      );
      return false;
    }
    const prepared = prepareEditableContour(
      next,
      layer === 'lumen' ? LUMEN_CONTOUR_MAX_POINTS : LESION_CONTOUR_MAX_POINTS,
    );
    if (layer === 'lumen') {
      lumenPolygonRef.current = prepared;
      setLumenPolygon(prepared);
      const box = bboxFromPolygon(prepared);
      if (box) {
        lumenBoxRef.current = box;
        setLumenBox(box);
      }
    } else {
      pointsRef.current = prepared;
      generatedLesionRef.current = prepared;
      setPoints(prepared);
    }
    markActiveDoctorKeyframeRefined();
    redrawRef.current();
    return true;
  }, [ensureLumenPolygonForRefine, frameSizeForPaint, markActiveDoctorKeyframeRefined, zh]);

  const activateSculpt = useCallback((next: LumenSculptMode, layer: 'lesion' | 'lumen') => {
    stopInteractivePrompt();
    setNnInteractiveMode(false);
    setLumenEditMode(false);
    armLesionBox(false);
    setSimpleEditMode(false);
    setRefineTarget(layer);
    setMode('brush');
    sculptLayerRef.current = layer;
    setSculptLayer(layer);
    setLumenSculptMode(next);
    if (layer === 'lumen') ensureLumenPolygonForRefine();
    const adding = next.endsWith('add');
    const name = layer === 'lumen' ? (zh ? '胃腔' : 'lumen') : (zh ? '病灶' : 'lesion');
    recordDoctorOp('tool_switch', {
      layer,
      operation: 'tool_switch',
      tool: next,
      op: adding ? 'add' : 'subtract',
      radius: paintRadiusRef.current,
    });
    setMessage(
      zh
        ? (adding
          ? `图增${name}：按住拖过要并入的区域；滚轮或滑条调笔刷（当前 ${paintRadiusRef.current}）`
          : `图减${name}：按住拖过要挖掉的区域；滚轮或滑条调笔刷（当前 ${paintRadiusRef.current}）`)
        : (adding
          ? `Paint + ${name}: drag to include. Wheel or slider sets size (now ${paintRadiusRef.current}).`
          : `Paint - ${name}: drag to cut. Wheel or slider sets size (now ${paintRadiusRef.current}).`),
    );
  }, [ensureLumenPolygonForRefine, recordDoctorOp, stopInteractivePrompt, zh]);

  const activateLumenSculpt = useCallback((next: LumenSculptMode) => {
    activateSculpt(next, 'lumen');
  }, [activateSculpt]);

  const activateRefineTool = useCallback((nextMode: 'hard' | 'brush' | 'polygon', target: RefineTarget = refineTarget) => {
    stopInteractivePrompt();
    setNnInteractiveMode(false);
    setLumenSculptMode(null);
    setLumenEditMode(false);
    setRefineTarget(target);
    setMode(nextMode);
    setSimplePromptMode('box');
    setTrackOnPlay(false);
    if (target === 'lumen') {
      const poly = ensureLumenPolygonForRefine();
      if (poly.length < 3 && nextMode !== 'polygon') {
        setMessage(zh ? '请先有胃腔框或轮廓，再拖点精修' : 'Need a lumen box or contour before drag refine');
        return;
      }
    } else if (pointsRef.current.length < 3 && nextMode !== 'polygon') {
      setMessage(zh ? '请先有病灶轮廓，再拖点精修' : 'Need a lesion contour before drag refine');
      return;
    }
    if (nextMode === 'polygon') {
      setPolygonDraft([]);
      setSimpleEditMode(false);
      recordDoctorOp('tool_switch', { layer: target, operation: 'tool_switch', tool: 'polygon' });
      setMessage(
        target === 'lumen'
          ? (zh ? '多边形改胃腔：单击加点，双击或点回起点闭合' : 'Lumen polygon: click to add, double-click or click start to close')
          : (zh ? '多边形改病灶：单击加点，双击或点回起点闭合' : 'Lesion polygon: click to add, double-click or click start to close'),
      );
      return;
    }
    setSimpleEditMode(true);
    setSimpleEditLayer(target === 'lumen' ? 'lesion' : 'lesion');
    recordDoctorOp('tool_switch', {
      layer: target,
      operation: 'tool_switch',
      tool: 'contour_drag',
    });
    setMessage(
      target === 'lumen'
        ? (zh ? '按住胃腔轮廓推拉，附近边界跟着走' : 'Drag the lumen contour; nearby boundary follows')
        : (zh ? '按住病灶轮廓推拉，附近边界跟着走' : 'Drag the lesion contour; nearby boundary follows'),
    );
  }, [ensureLumenPolygonForRefine, recordDoctorOp, refineTarget, stopInteractivePrompt, zh]);

  const prepareLumenDetection = useCallback(() => {
    stopInteractivePrompt();
    setMode('soft');
    setSimplePromptMode('box');
    setSimpleEditMode(false);
    setLumenEditMode(false);
    setTrackOnPlay(false);
  }, [stopInteractivePrompt]);

  const runLesionModel = useCallback(async (
    imgPt: number[] | null,
    box: { x1: number; y1: number; x2: number; y2: number } | null = null,
    clicks: Array<{ x: number; y: number; label: 'positive' | 'negative' }> = [],
    modelOverride?: LesionSegmentationModel,
  ): Promise<number[][] | null> => {
    if (!patient || segmentationBusy) return null;
    const activeSegmentationModel = modelOverride || segmentationModel;
    const traceId = `lesion_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
    const traceStartedAt = performance.now();
    setSegmentationBusy(true);
    setSegmentationModelResult(null);
    setMessage(
      zh
        ? `${segmentationModelName(activeSegmentationModel, true)} 病灶预测中…`
        : `${segmentationModelName(activeSegmentationModel, false)} lesion prediction…`,
    );
    try {
      const frame = await videoOrImageToSamFrame(
        videoRef.current,
        imgRef.current,
        mediaMode === 'video',
        1024,
      );
      const scale = frame.scale || 1;
      const response = await fetch('/api/agent/lesion-segmentation', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          frame_png_b64: frame.b64,
          model: activeSegmentationModel,
          threshold: 0.5,
          image_width: frame.width,
          image_height: frame.height,
          use_lora: activeSegmentationModel === 'sam31',
          text_prompt: 'gastric lesion',
          box: box
            ? {
                x1: box.x1 * scale,
                y1: box.y1 * scale,
                x2: box.x2 * scale,
                y2: box.y2 * scale,
              }
            : undefined,
          clicks: clicks.length
            ? clicks.map((point) => ({
                x: point.x * scale,
                y: point.y * scale,
                label: point.label,
              }))
            : imgPt
              ? [{ x: imgPt[0] * scale, y: imgPt[1] * scale, label: 'positive' }]
              : [],
        }),
      });
      const data = await readJsonPayload<{
        ok?: boolean;
        error?: string;
        mask_polygon?: number[][];
        model?: string;
        lesion_area_ratio?: number;
        validation_summary?: Record<string, unknown>;
      }>(response, 'Lesion segmentation endpoint');
      if (!response.ok || !data.ok || !Array.isArray(data.mask_polygon) || data.mask_polygon.length < 3) {
        throw new Error(data.error || 'Lesion model returned no valid mask');
      }
      setSegmentationModelResult({
        model: data.model,
        lesion_area_ratio: data.lesion_area_ratio,
        validation_summary: data.validation_summary,
      });
      const polyFull = scalePolyToFull(data.mask_polygon, scale, frame.fullWidth, frame.fullHeight);
      const poly = prepareEditableContour(polyFull, LESION_CONTOUR_MAX_POINTS);
      maskAuditRef.current('model_trace', {
        trace_id: traceId,
        operation: 'lesion_segmentation',
        model: data.model || activeSegmentationModel,
        source: 'lesion_segmentation_endpoint',
        outcome: 'success',
        frame_time_sec: Number((videoRef.current?.currentTime ?? videoTime).toFixed(3)),
        input: {
          has_box: Boolean(box),
          click_count: clicks.length || (imgPt ? 1 : 0),
          positive_clicks: clicks.filter((click) => click.label !== 'negative').length
            || (imgPt && !clicks.length ? 1 : 0),
          negative_clicks: clicks.filter((click) => click.label === 'negative').length,
        },
        output: {
          polygon_points: poly.length,
          lesion_area_ratio: data.lesion_area_ratio,
          validation_summary: data.validation_summary,
        },
        duration_ms: Math.round(performance.now() - traceStartedAt),
      });
      contourInteractionRef.current = true;
      generatedLesionRef.current = clonePoly(poly);
      pointsRef.current = poly;
      setPoints(poly);
      snapshotOriginal(poly, wallPointsRef.current);
      const assistReport = buildModelAssistReport(
        patient,
        poly,
        frame.fullWidth,
        frame.fullHeight,
        activeSegmentationModel,
        data.lesion_area_ratio,
        zh,
      );
      setSamReport(assistReport);
      onSystemReport?.(assistReport);
      onImagingAssist?.({
        layerResult,
        lesionPolygon: poly,
        wallPolygon: wallPointsRef.current,
        frameSize: { width: frame.fullWidth, height: frame.fullHeight },
        lumenBBox: lumenBoxRef.current,
        lumenPolygon: lumenPolygonRef.current.length >= 3 ? lumenPolygonRef.current : undefined,
      });
      setMessage(
        zh
          ? `${segmentationModelName(activeSegmentationModel, true)} 已生成病灶 ROI（${poly.length} 点），正点 ${clicks.filter((click) => click.label !== 'negative').length || (imgPt && !clicks.length ? 1 : 0)}，负点 ${clicks.filter((click) => click.label === 'negative').length}`
          : `${segmentationModelName(activeSegmentationModel, false)} lesion ROI ready (${poly.length} points), positive ${clicks.filter((click) => click.label !== 'negative').length || (imgPt && !clicks.length ? 1 : 0)}, negative ${clicks.filter((click) => click.label === 'negative').length}`,
      );
      return poly;
    } catch (error) {
      const messageText = error instanceof Error ? error.message : 'Lesion model failed';
      maskAuditRef.current('model_trace', {
        trace_id: traceId,
        operation: 'lesion_segmentation',
        model: activeSegmentationModel,
        source: 'lesion_segmentation_endpoint',
        outcome: 'error',
        frame_time_sec: Number((videoRef.current?.currentTime ?? videoTime).toFixed(3)),
        input: {
          has_box: Boolean(box),
          click_count: clicks.length || (imgPt ? 1 : 0),
        },
        error: messageText.slice(0, 240),
        duration_ms: Math.round(performance.now() - traceStartedAt),
      });
      setSegmentationModelResult({ error: messageText });
      setMessage(messageText);
      return null;
    } finally {
      setSegmentationBusy(false);
    }
  }, [applyWallExtension, layerResult, mediaMode, onImagingAssist, onSystemReport, patient, segmentationBusy, segmentationModel, snapshotOriginal, videoTime, wallPointsRef, zh]);

  useEffect(() => {
    runLesionModelRef.current = runLesionModel;
  }, [runLesionModel]);

  const findLesionCandidate = useCallback(async (): Promise<number[][] | null> => {
    if (!runLesionModelRef.current) return null;
    let box: { x1: number; y1: number; x2: number; y2: number } | null = null;
    try {
      const frame = await videoOrImageToSamFrame(
        videoRef.current,
        imgRef.current,
        mediaMode === 'video',
        1024,
      );
      const scale = frame.scale || 1;
      const response = await fetch('/api/agent/lesion-detection', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          frame_png_b64: frame.b64,
          image_width: frame.width,
          image_height: frame.height,
        }),
      });
      const data = await readJsonPayload<{
        ok?: boolean;
        lesion_detected?: boolean;
        lesion_bbox?: { x1: number; y1: number; x2: number; y2: number };
      }>(response, 'Lesion detection endpoint');
      if (response.ok && data.ok && data.lesion_detected && data.lesion_bbox) {
        box = {
          x1: data.lesion_bbox.x1 / scale,
          y1: data.lesion_bbox.y1 / scale,
          x2: data.lesion_bbox.x2 / scale,
          y2: data.lesion_bbox.y2 / scale,
        };
      }
    } catch {
      // Warm YOLO is optional; SAM 3.1 text prompt still finds a candidate.
    }
    const centroid = box
      ? [(box.x1 + box.x2) / 2, (box.y1 + box.y2) / 2]
      : null;
    const publicModel = publicLesionSegModel(segmentationModel);
    if (publicModel === 'dinov3') {
      // Full-image DINO is the no-box number. Do not feed an oracle box into DINO auto-find.
      return runLesionModelRef.current(null, null, [], 'dinov3');
    }
    if (box && centroid) {
      const guided = await runSamAtPoint(centroid, {
        silent: true,
        source: 'sam',
        box,
        model: 'sam31',
        keepEditing: false,
      });
      if (guided && guided.length >= 3) return guided;
    }
    return runLesionModelRef.current(centroid, box, [], 'sam31');
  }, [mediaMode, runSamAtPoint, segmentationModel]);

  const runDoctorKeyframePreseg = useCallback(async (keyframeId: string, frame: CapturedDoctorFrame) => {
    const session = doctorKeyframeSessionRef.current;
    setDoctorKeyframes((prev) => {
      if (!prev.some((kf) => kf.id === keyframeId)) return prev;
      return prev.map((kf) => (
        kf.id === keyframeId
          ? { ...kf, segStatus: 'running' as const, error: null }
          : kf
      ));
    });
    setMessage(zh ? '关键帧已标记，正在自动分割病灶…' : 'Keyframe marked; auto-segmenting lesion…');
    try {
      const result = await presegDoctorKeyframeFromFrame(frame);
      if (session !== doctorKeyframeSessionRef.current) return;
      const ready = Boolean(
        (result.lesionPolygon && result.lesionPolygon.length >= 3)
        || result.lumenBox
        || (result.lumenPolygon && result.lumenPolygon.length >= 3),
      );
      setDoctorKeyframes((prev) => {
        if (!prev.some((kf) => kf.id === keyframeId)) return prev;
        const next = prev.map((kf) => (
          kf.id === keyframeId
            ? {
                ...kf,
                segStatus: ready ? 'ready' as const : 'failed' as const,
                lesionPolygon: result.lesionPolygon,
                lumenBox: result.lumenBox,
                lumenPolygon: result.lumenPolygon,
                error: ready
                  ? null
                  : (result.lesionBox ? 'lesion_seg_empty' : 'lesion_not_found'),
              }
            : kf
        ));
        doctorKeyframesRef.current = next;
        return next;
      });

      // Apply to canvas immediately when this keyframe is still open.
      if (activeDoctorKeyframeIdRef.current === keyframeId) {
        if (result.lesionPolygon && result.lesionPolygon.length >= 3) {
          const prepared = prepareEditableContour(result.lesionPolygon, LESION_CONTOUR_MAX_POINTS);
          pointsRef.current = prepared;
          generatedLesionRef.current = prepared;
          setPoints(prepared);
          if (result.lesionBox) {
            setSimplePromptBox(result.lesionBox);
          } else {
            const box = bboxFromPolygon(prepared);
            if (box) setSimplePromptBox(box);
          }
          setMode('soft');
          setSimplePromptMode('box');
          setSimpleEditMode(true);
          setSimpleEditLayer('lesion');
          setActiveLayer('lesion');
          setLumenEditMode(false);
          recordDoctorOp('detect_lesion', {
            layer: 'lesion',
            operation: 'keyframe_auto_seg',
            tool: result.lesionBackend || 'yolo_cascade_seg',
            status: 'ok',
            point_count: prepared.length,
            keyframe_id: keyframeId,
          });
          persistOpenKeyframeContoursRef.current?.({ refined: false });
          setMessage(
            zh
              ? '关键帧病灶已自动分割。请从邻近看得见的胃壁起笔，或点两侧再接。不要从肿块正中空想分层。'
              : 'Keyframe lesion auto-segmented. Paint from adjacent visible wall, or mark both flanks. Do not invent layers in the mass center.',
          );
        } else {
          recordDoctorOp('detect_lesion', {
            layer: 'lesion',
            operation: 'keyframe_auto_seg',
            tool: 'yolo_cascade_seg',
            status: 'error',
            keyframe_id: keyframeId,
          });
          armLesionBox(false);
          setMessage(
            zh
              ? '自动分割未找到病灶。请先点亮「框选病灶」，再拖出矩形'
              : 'Auto-segment found no lesion. Arm Box lesion, then drag',
          );
        }
        if (result.lumenPolygon && result.lumenPolygon.length >= 3) {
          lumenPolygonRef.current = result.lumenPolygon;
          setLumenPolygon(result.lumenPolygon);
          const derived = bboxFromPolygon(result.lumenPolygon);
          if (derived) {
            lumenBoxRef.current = derived;
            setLumenBox(derived);
          } else if (result.lumenBox) {
            lumenBoxRef.current = result.lumenBox;
            setLumenBox(result.lumenBox);
          }
        } else if (result.lumenBox) {
          lumenBoxRef.current = result.lumenBox;
          setLumenBox(result.lumenBox);
          const seeded = boxToClosedPolygon(result.lumenBox, 32);
          lumenPolygonRef.current = seeded;
          setLumenPolygon(seeded);
        }
        redrawRef.current();
      }
    } catch (error) {
      if (session !== doctorKeyframeSessionRef.current) return;
      setDoctorKeyframes((prev) => {
        if (!prev.some((kf) => kf.id === keyframeId)) return prev;
        return prev.map((kf) => (
          kf.id === keyframeId
            ? {
                ...kf,
                segStatus: 'failed' as const,
                error: error instanceof Error ? error.message.slice(0, 120) : 'preseg_failed',
              }
            : kf
        ));
      });
      if (activeDoctorKeyframeIdRef.current === keyframeId) {
        recordDoctorOp('detect_lesion', {
          layer: 'lesion',
          operation: 'keyframe_auto_seg',
          tool: 'yolo_cascade_seg',
          status: 'error',
          keyframe_id: keyframeId,
        });
        armLesionBox(false);
        setMessage(
          zh
            ? '自动分割失败。请先点亮「框选病灶」，再拖出矩形'
            : 'Auto-segment failed. Arm Box lesion, then drag',
        );
      }
    }
  }, [applyWallExtension, recordDoctorOp, zh]);

  const runPropagateToOtherKeyframes = useCallback(async (opts?: {
    sourceId?: string;
    auto?: boolean;
  }) => {
    const video = videoRef.current;
    const frames = doctorKeyframesRef.current;
    const source = opts?.sourceId
      ? findDoctorKeyframeById(frames, opts.sourceId)
      : (findDoctorKeyframeById(frames, activeDoctorKeyframeIdRef.current) || pickPropagateSource(frames));
    if (!source) {
      if (!opts?.auto) {
        setMessage(zh ? '请先打开已校正的关键帧' : 'Open a refined keyframe first');
      }
      return;
    }
    const liveLesion = (
      source.id === activeDoctorKeyframeIdRef.current && pointsRef.current.length >= 3
    )
      ? clonePoly(pointsRef.current)
      : (source.lesionPolygon && source.lesionPolygon.length >= 3 ? source.lesionPolygon : null);
    if (!liveLesion) {
      if (!opts?.auto) {
        setMessage(zh ? '当前关键帧没有可用病灶轮廓' : 'Active keyframe has no lesion contour');
      }
      return;
    }
    const liveLumen = (
      source.id === activeDoctorKeyframeIdRef.current && lumenPolygonRef.current.length >= 3
    )
      ? clonePoly(lumenPolygonRef.current)
      : (source.lumenPolygon || null);
    const liveWall = (
      source.id === activeDoctorKeyframeIdRef.current && wallPointsRef.current.length >= 3
    )
      ? clonePoly(wallPointsRef.current)
      : (source.wallPolygon || null);
    const liveWallLayer = (
      source.id === activeDoctorKeyframeIdRef.current && wallLayerReadoutRef.current
    )
      ? wallLayerReadoutRef.current
      : (source.wallLayerReadout || null);
    const targets = opts?.auto
      ? laterUnrefinedKeyframes(frames, source)
      : frames.filter((kf) => kf.id !== source.id && !kf.refined);
    if (!targets.length) {
      if (!opts?.auto) {
        setMessage(zh ? '没有可传播的目标关键帧' : 'No target keyframes to propagate to');
      }
      return;
    }
    if (!video?.videoWidth || !patient) {
      if (!opts?.auto) {
        setMessage(zh ? '视频帧尚未准备好' : 'Video frame is not ready');
      }
      return;
    }
    persistOpenKeyframeContours();
    setPropagateToKeyframesBusy(true);
    setMessage(
      zh
        ? `正在按光流传到 ${targets.length} 个关键帧…`
        : `Propagating by flow to ${targets.length} keyframes…`,
    );
    try {
      const result = await propagateContoursToKeyframes({
        caseId: patient.patient_id || patient.id,
        videoUrl,
        imageWidth: video.videoWidth,
        imageHeight: video.videoHeight,
        source,
        sourceLesion: liveLesion,
        sourceLumen: liveLumen,
        sourceWall: opts?.auto ? null : liveWall,
        sourceWallLayer: opts?.auto ? null : liveWallLayer,
        sourceWallBands: opts?.auto ? [] : wallLayerBandsRef.current,
        sourceWallImaginary: opts?.auto ? [] : wallLayerImaginaryRef.current,
        targets,
      });
      if (!result.hits.length) {
        if (!opts?.auto) {
          setMessage(zh ? '关键帧传播没有得到可用轮廓' : 'Keyframe propagate returned no contours');
        }
        return;
      }
      setDoctorKeyframes((prev) => {
        const next = applyPropagateHits(prev, source.id, result.hits);
        doctorKeyframesRef.current = next;
        return next;
      });
      const open = isDoctorKeyframeOpen(
        doctorKeyframesRef.current,
        activeDoctorKeyframeIdRef.current,
        video.currentTime || videoTime,
        Boolean(isPlaying),
      );
      const destIds = result.hits.map((hit) => hit.id);
      const rechecked = liveWall ? await recheckKeyframesWallPixels(destIds) : 0;
      if (open && result.hits.some((hit) => hit.id === open.id)) {
        const updated = findDoctorKeyframeById(doctorKeyframesRef.current, open.id);
        if (updated) void selectDoctorKeyframeRef.current(updated);
      }
      setMessage(
        zh
          ? `已${result.method === 'optical_flow' ? '按光流' : '按轮廓'}把病灶${liveWall ? '和胃壁' : ''}传到 ${result.hits.length} 个关键帧${rechecked ? `，并按 ${rechecked} 帧像素重核了中断` : ''}`
          : `${result.method === 'optical_flow' ? 'Flow' : 'Copy'} propagated${liveWall ? ' lesion and wall' : ''} to ${result.hits.length} keyframes${rechecked ? `; re-checked interrupt on ${rechecked} frames` : ''}`,
      );
    } catch (error) {
      if (!opts?.auto) {
        setMessage(error instanceof Error ? error.message : (zh ? '关键帧传播失败' : 'Keyframe propagation failed'));
      }
    } finally {
      setPropagateToKeyframesBusy(false);
    }
  }, [isPlaying, patient, persistOpenKeyframeContours, recheckKeyframesWallPixels, videoTime, videoUrl, zh]);
  runPropagateToOtherKeyframesRef.current = runPropagateToOtherKeyframes;

  const maybeAutoPropagate = useCallback((sourceId: string) => {
    const frames = doctorKeyframesRef.current;
    const source = findDoctorKeyframeById(frames, sourceId);
    if (!source?.refined || !source.lesionPolygon || source.lesionPolygon.length < 3) return;
    const targets = laterUnrefinedKeyframes(frames, source);
    if (!targets.length) return;
    const sig = `${sourceId}:${targets.map((kf) => kf.id).join(',')}`;
    if (lastAutoPropagateSigRef.current === sig) return;
    lastAutoPropagateSigRef.current = sig;
    void runPropagateToOtherKeyframesRef.current({ sourceId, auto: true });
  }, []);
  maybeAutoPropagateRef.current = maybeAutoPropagate;

  const markDoctorKeyframe = useCallback(() => {
    if (mediaMode !== 'video' || !videoUrl) return;
    const video = videoRef.current;
    if (!video?.videoWidth) {
      setMessage(zh ? '视频帧未就绪，稍后再标关键帧' : 'Video frame not ready');
      return;
    }
    pauseVideoOnCurrentFrame();
    const timeSec = Number((video.currentTime || 0).toFixed(3));
    const gate = canAddDoctorKeyframe(doctorKeyframes, timeSec);
    if (!gate.ok) {
      if (gate.reason === 'duplicate') {
        const nearby = doctorKeyframes.find((kf) => Math.abs(kf.timeSec - timeSec) <= DOCTOR_KEYFRAME_DEDUP_SEC);
        if (nearby) {
          void selectDoctorKeyframeRef.current(nearby);
          setMessage(zh
            ? `已暂停并打开关键帧 t=${nearby.timeSec.toFixed(2)}s，只看这一帧`
            : `Paused on keyframe t=${nearby.timeSec.toFixed(2)}s`);
          return;
        }
      }
      setMessage(
        gate.reason === 'full'
          ? (zh ? `关键帧已满（${DOCTOR_KEYFRAME_MAX}），请先删除再标` : `Keyframe strip full (${DOCTOR_KEYFRAME_MAX}); remove one first`)
          : (zh ? '该时刻已有关键帧' : 'Already marked near this time'),
      );
      return;
    }
    const id = newDoctorKeyframeId(timeSec);
    const frame = captureDoctorFrameFromVideo(video);
    const hasLesion = pointsRef.current.length >= 3;
    const hasLumen = lumenPolygonRef.current.length >= 3 || Boolean(lumenBoxRef.current);
    const next: DoctorKeyframe = {
      id,
      timeSec,
      thumbDataUrl: frame?.thumbDataUrl || null,
      segStatus: hasLesion ? 'ready' : 'idle',
      lesionPolygon: hasLesion ? clonePoly(pointsRef.current) : undefined,
      lumenBox: lumenBoxRef.current || undefined,
      lumenPolygon: lumenPolygonRef.current.length >= 3 ? clonePoly(lumenPolygonRef.current) : undefined,
      wallPolygon: wallPointsRef.current.length >= 3 ? clonePoly(wallPointsRef.current) : undefined,
      wallLayerReadout: wallLayerReadoutRef.current,
      error: null,
    };
    persistOpenKeyframeContours();
    if (!hasLesion) clearKeyframeOverlay();
    setDoctorKeyframes((prev) => {
      const sorted = sortDoctorKeyframes([...prev, next]);
      doctorKeyframesRef.current = sorted;
      return sorted;
    });
    setActiveDoctorKeyframeId(id);
    activeDoctorKeyframeIdRef.current = id;
    setAnalysisContourUnrefined(false);
    setSimpleToolsOpen(true);
    armLesionBox(false);
    recordDoctorOp('keyframe_mark', {
      operation: 'keyframe_mark',
      tool: 'keyframe_mark',
      keyframe_id: id,
      video_time_sec: timeSec,
    });
    setMessage(
      hasLesion
        ? (zh
          ? `已暂停并标记关键帧 t=${timeSec.toFixed(2)}s，只看这一帧；沿用当前病灶${hasLumen ? '与胃腔' : ''}。`
          : `Paused and marked keyframe t=${timeSec.toFixed(2)}s; kept the current contour.`)
        : (zh
          ? `已暂停并标记关键帧 t=${timeSec.toFixed(2)}s，只看这一帧。请点亮「框选病灶」后再拖框`
          : `Paused and marked keyframe t=${timeSec.toFixed(2)}s. Arm Box lesion, then drag`),
    );
  }, [
    clearKeyframeOverlay,
    doctorKeyframes,
    mediaMode,
    pauseVideoOnCurrentFrame,
    persistOpenKeyframeContours,
    recordDoctorOp,
    videoUrl,
    zh,
  ]);

  const toggleVideoPlayback = useCallback(() => {
    const video = videoRef.current;
    if (!video) return;
    if (video.paused) {
      void video.play();
      return;
    }
    pauseVideoOnCurrentFrame();
  }, [pauseVideoOnCurrentFrame]);

  const handleCineSpace = useCallback(() => {
    const video = videoRef.current;
    if (!video) return;
    if (!video.paused) {
      pauseVideoOnCurrentFrame();
      setMessage(zh ? '已暂停。再按空格标记此帧为关键帧' : 'Paused. Press Space again to mark this frame');
      return;
    }
    markDoctorKeyframe();
  }, [markDoctorKeyframe, pauseVideoOnCurrentFrame, zh]);

  const selectDoctorKeyframe = useCallback(async (kf: DoctorKeyframe) => {
    const video = videoRef.current;
    if (!video) return;
    persistOpenKeyframeContours();
    setActiveDoctorKeyframeId(kf.id);
    activeDoctorKeyframeIdRef.current = kf.id;
    pauseVideoOnCurrentFrame({ timeSec: kf.timeSec });
    if (Math.abs((video.currentTime || 0) - kf.timeSec) > 0.04) {
      await seekVideoForAgent(video, kf.timeSec);
    }
    setVideoTime(kf.timeSec);
    syncFrameFromVideo({ force: true });
    if (kf.lesionPolygon && kf.lesionPolygon.length >= 3) {
      const prepared = prepareEditableContour(kf.lesionPolygon, LESION_CONTOUR_MAX_POINTS);
      pointsRef.current = prepared;
      generatedLesionRef.current = prepared;
      setPoints(prepared);
      const extras = (kf.extraLesionPolygons || []).filter((poly) => poly.length >= 3);
      extraLesionPolygonsRef.current = extras;
      setExtraLesionPolygons(extras);
      setSimpleEditMode(true);
      setSimpleEditLayer('lesion');
      setMode('soft');
    } else {
      clearKeyframeOverlay();
    }
    if (kf.lumenPolygon && kf.lumenPolygon.length >= 3) {
      lumenPolygonRef.current = kf.lumenPolygon;
      setLumenPolygon(kf.lumenPolygon);
      const derivedLumen = bboxFromPolygon(kf.lumenPolygon);
      if (derivedLumen) {
        lumenBoxRef.current = derivedLumen;
        setLumenBox(derivedLumen);
      } else if (kf.lumenBox) {
        lumenBoxRef.current = kf.lumenBox;
        setLumenBox(kf.lumenBox);
      }
    } else if (kf.lumenBox) {
      lumenBoxRef.current = kf.lumenBox;
      setLumenBox(kf.lumenBox);
      const seeded = boxToClosedPolygon(kf.lumenBox, 32);
      lumenPolygonRef.current = seeded;
      setLumenPolygon(seeded);
    }
    const restoredFocus = (kf.analysisFocusPoints || []).filter((point) => point.length >= 2);
    analysisFocusPointsRef.current = restoredFocus;
    setAnalysisFocusPoints(restoredFocus);
    if (kf.wallVisibility) {
      setWallVisibility(kf.wallVisibility);
      wallVisibilityRef.current = kf.wallVisibility;
    }
    if (kf.serosaAnchorMode) {
      setSerosaAnchorMode(kf.serosaAnchorMode);
      serosaAnchorModeRef.current = kf.serosaAnchorMode;
    }
    if (kf.wallPolygon && kf.wallPolygon.length >= 3) {
      const preparedWall = prepareEditableContour(kf.wallPolygon, WALL_CONTOUR_MAX_POINTS);
      wallPointsRef.current = preparedWall;
      setWallPoints(preparedWall);
      if (kf.wallLayerReadout) {
        const restored = {
          ...judgeWallLayerBreach({
            remainPx: kf.wallLayerReadout.remainPx,
            source: kf.wallLayerReadout.source,
          }),
          layersBreached: kf.wallLayerReadout.layersBreached,
          deepestZh: kf.wallLayerReadout.deepestZh,
          deepestEn: kf.wallLayerReadout.deepestEn,
          ratio: kf.wallLayerReadout.ratio,
          source: kf.wallLayerReadout.source,
        };
        const destFrame = captureFrameGray();
        const storedBands = (kf.wallLayerBands || []).filter((band) => band.length >= 2);
        const ids = doctorClinicalIds(wallLayerTargetRef.current);
        applyWallLayerVisuals(
          preparedWall,
          restored,
          destFrame,
          storedBands.length
            ? storedBands.map((curve, index) => ({
              layer: ids[index] || 5,
              curve,
              imaginaryMask: kf.wallLayerImaginary?.[index] || [],
            }))
            : null,
        );
        refreshWallEchoClarify(destFrame);
        persistOpenKeyframeContours({ refined: true });
      }
    } else {
      wallPointsRef.current = [];
      wallExtensionMaskRef.current = [];
      setWallPoints([]);
      setWallLayerReadout(null);
      wallLayerReadoutRef.current = null;
      setWallLayerBands([]);
      wallLayerBandsRef.current = [];
      setWallLayerImaginary([]);
      wallLayerImaginaryRef.current = [];
    }
    setSimplePromptMode('box');
    armLesionBox(false);
    setLumenEditMode(false);
    setRefineTarget('lesion');
    setSimpleToolsOpen(true);
    setMagnifierOn(false);
    magnifierPosRef.current = null;
    setViewFocusBox(null);
    setViewFocusMode(null);
    redrawRef.current();

    setMessage(
      kf.lesionPolygon && kf.lesionPolygon.length >= 3
        ? (zh
          ? `已暂停并打开关键帧 ${formatKeyframeTime(kf.timeSec)} / 第${cineFrameIndex(kf.timeSec, videoFpsRef.current)}帧，只看这一帧；可整体拖动或精修`
          : `Paused on keyframe ${formatKeyframeTime(kf.timeSec)} / f${cineFrameIndex(kf.timeSec, videoFpsRef.current)}; drag the whole lesion or refine`)
        : (zh
          ? `已暂停并打开关键帧 ${formatKeyframeTime(kf.timeSec)} / 第${cineFrameIndex(kf.timeSec, videoFpsRef.current)}帧。请先点亮「框选病灶」，再拖出矩形`
          : `Paused on keyframe ${formatKeyframeTime(kf.timeSec)} / f${cineFrameIndex(kf.timeSec, videoFpsRef.current)}. Arm Box lesion, then drag`),
    );
    recordDoctorOp('keyframe_select', {
      operation: 'keyframe_select',
      op: 'keyframe_select',
      keyframe_id: kf.id,
      video_time_sec: kf.timeSec,
    });
  }, [applyWallLayerVisuals, captureFrameGray, clearKeyframeOverlay, pauseVideoOnCurrentFrame, persistOpenKeyframeContours, recordDoctorOp, refreshWallEchoClarify, zh]);
  selectDoctorKeyframeRef.current = selectDoctorKeyframe;

  const removeDoctorKeyframe = useCallback((id: string) => {
    const removed = doctorKeyframesRef.current.find((kf) => kf.id === id);
    setDoctorKeyframes((prev) => prev.filter((kf) => kf.id !== id));
    setActiveDoctorKeyframeId((cur) => (cur === id ? null : cur));
    recordDoctorOp('keyframe_delete', {
      operation: 'keyframe_delete',
      op: 'keyframe_delete',
      keyframe_id: id,
      video_time_sec: removed?.timeSec ?? null,
    });
    if (accountReaderId && patient?.id) {
      void fetch('/api/reader/case-state', {
        method: 'PUT',
        headers: authHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({
          account_id: accountReaderId,
          case_id: patient.id,
          patient_id: patient.patient_id,
          study_mode: patient.study_mode || undefined,
          progress: 'in_progress',
          activity_append: {
            id: `kfd_${Date.now().toString(36)}`,
            at: new Date().toISOString(),
            type: 'keyframe_delete',
            label_zh: `删除关键帧 t=${Number(removed?.timeSec || 0).toFixed(2)}s`,
            label_en: `Deleted keyframe t=${Number(removed?.timeSec || 0).toFixed(2)}s`,
            detail: { keyframe_id: id, time_sec: removed?.timeSec ?? null },
          },
        }),
      }).catch(() => {});
    }
  }, [accountReaderId, authHeaders, patient?.id, patient?.patient_id, patient?.study_mode, recordDoctorOp]);

  useEffect(() => {
    let cancelled = false;
    setDoctorKeyframes([]);
    setActiveDoctorKeyframeId(null);
    setAnalysisContourUnrefined(false);
    setAdjacentPair(null);
    adjacentPairRef.current = null;
    setWallLayerTarget(1);
    wallLayerTargetRef.current = 1;
    doctorKeyframeSessionRef.current += 1;
    const caseId = patient?.id;
    const accountId = accountReaderId;
    if (!caseId || !accountId || !simpleVideoMode) {
      return () => { cancelled = true; };
    }
    const session = doctorKeyframeSessionRef.current;
    void (async () => {
      try {
        const response = await fetch(
          `/api/reader/case-state?case_id=${encodeURIComponent(caseId)}`,
          { cache: 'no-store', headers: authHeaders() },
        );
        if (!response.ok || cancelled || doctorKeyframeSessionRef.current !== session) return;
        const data = await response.json() as {
          ok?: boolean;
          state?: {
            doctor_keyframes?: DoctorKeyframe[];
            active_keyframe_id?: string | null;
            adjacent_lock?: AdjacentPair | null;
            wall_target_layers?: 1 | 2 | 3 | null;
          } | null;
        };
        const restoredLock = parseAdjacentPair(data.state?.adjacent_lock);
        const restoredLayers = parseWallLayerTarget(data.state?.wall_target_layers);
        if (restoredLock) {
          setAdjacentPair(restoredLock);
          adjacentPairRef.current = restoredLock;
        }
        if (restoredLayers) {
          setWallLayerTarget(restoredLayers);
          wallLayerTargetRef.current = restoredLayers;
        }
        if (restoredLock) {
          window.dispatchEvent(new CustomEvent(ADJACENT_LOCK_EVENT, {
            detail: { pair: restoredLock, source: 'restore' } satisfies AdjacentLockEventDetail,
          }));
        }
        const frames = Array.isArray(data.state?.doctor_keyframes) ? data.state.doctor_keyframes : [];
        if (!frames.length || cancelled || doctorKeyframeSessionRef.current !== session) return;
        const sorted = sortDoctorKeyframes(frames);
        doctorKeyframesRef.current = sorted;
        setDoctorKeyframes(sorted);
        const activeId = data.state?.active_keyframe_id || sorted[0]?.id || null;
        setActiveDoctorKeyframeId(activeId);
        activeDoctorKeyframeIdRef.current = activeId;
        const active = findDoctorKeyframeById(sorted, activeId) || sorted[0];
        if (active) void selectDoctorKeyframeRef.current(active);
      } catch {
        // Restore is best effort.
      }
    })();
    return () => { cancelled = true; };
  }, [accountReaderId, authHeaders, patient?.id, patient?.patient_id, simpleVideoMode, videoUrl, zh]);

  useEffect(() => {
    if (!simpleVideoMode || !patient?.id || !accountReaderId) return;
    if (!doctorKeyframes.length && !activeDoctorKeyframeId) return;
    const timer = window.setTimeout(() => {
      const latestCount = doctorKeyframes.length;
      const prevCount = Number(sessionStorage.getItem(`kf_count_${patient.id}`) || '0');
      const shouldLog = latestCount !== prevCount;
      if (shouldLog) sessionStorage.setItem(`kf_count_${patient.id}`, String(latestCount));
      void fetch('/api/reader/case-state', {
        method: 'PUT',
        headers: authHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({
          account_id: accountReaderId,
          case_id: patient.id,
          patient_id: patient.patient_id,
          study_mode: patient.study_mode || undefined,
          progress: 'in_progress',
          doctor_keyframes: doctorKeyframes.map((kf) => ({
            ...kf,
            thumbDataUrl: kf.thumbDataUrl || null,
          })),
          active_keyframe_id: activeDoctorKeyframeId,
          keyframe_mark_count: latestCount,
          activity_append: shouldLog && latestCount > 0
            ? {
              id: `kf_${Date.now().toString(36)}`,
              at: new Date().toISOString(),
              type: 'keyframe_mark',
              label_zh: `关键帧已更新（共 ${latestCount} 帧）`,
              label_en: `Keyframes updated (${latestCount})`,
              detail: {
                count: latestCount,
                active_keyframe_id: activeDoctorKeyframeId,
              },
            }
            : null,
        }),
      }).catch(() => {
        // Persist must not interrupt reading.
      });
    }, 700);
    return () => window.clearTimeout(timer);
  }, [
    accountReaderId,
    activeDoctorKeyframeId,
    authHeaders,
    doctorKeyframes,
    patient?.id,
    patient?.patient_id,
    patient?.study_mode,
    simpleVideoMode,
  ]);

  useEffect(() => {
    doctorKeyframesRef.current = doctorKeyframes;
    activeDoctorKeyframeIdRef.current = activeDoctorKeyframeId;
  }, [activeDoctorKeyframeId, doctorKeyframes]);

  useEffect(() => {
    if (isPlaying || mediaMode !== 'video') return;
    if (lesionBoxArmedRef.current) return;
    const currentTime = videoRef.current?.currentTime ?? videoTime;
    const kf = isDoctorKeyframeOpen(doctorKeyframes, activeDoctorKeyframeId, currentTime, false);
    if (!kf || kf.segStatus !== 'ready') return;
    if (pointsRef.current.length >= 3 || lumenPolygonRef.current.length >= 3 || lumenBoxRef.current) return;
    void selectDoctorKeyframeRef.current(kf);
  }, [activeDoctorKeyframeId, doctorKeyframes, isPlaying, mediaMode, videoTime]);

  useEffect(() => {
    if (!open || mediaMode !== 'video') return;
    const onKey = (e: KeyboardEvent) => {
      const target = e.target;
      const typing = target instanceof HTMLTextAreaElement
        || target instanceof HTMLSelectElement
        || (target instanceof HTMLInputElement && target.type !== 'range');
      if (e.key === 'ArrowLeft' || e.key === 'ArrowRight') {
        if (typing) return;
        e.preventDefault();
        e.stopPropagation();
        stepCineFrames(e.key === 'ArrowLeft' ? -1 : 1);
        return;
      }
      if (e.code !== 'Space' && e.key !== ' ') return;
      // Allow Space on the scrubber (range) so pause-scrub-mark works.
      if (typing) return;
      e.preventDefault();
      e.stopPropagation();
      handleCineSpace();
      // Blur scrubber so the next Space is not eaten by the range control.
      if (target instanceof HTMLElement && typeof target.blur === 'function') {
        target.blur();
      }
      containerRef.current?.focus?.({ preventScroll: true });
    };
    window.addEventListener('keydown', onKey, true);
    return () => window.removeEventListener('keydown', onKey, true);
  }, [handleCineSpace, mediaMode, open, stepCineFrames]);

  const refineWithNnInteractive = useCallback(async (
    target: 'lesion' | 'lumen' = 'lesion',
    interaction?: { x: number; y: number; label: 'positive' | 'negative' },
    scribbles: ActiveSamStroke[] = [],
    additionalPoints: Array<{ x: number; y: number; label: 'positive' | 'negative' }> = [],
    prime = false,
  ) => {
    const lumenSeedBox = lumenBoxRef.current;
    const initialPolygon = target === 'lumen'
      ? (
        lumenPolygonRef.current.length >= 3
          ? lumenPolygonRef.current
          : lumenSeedBox
            ? [
              [lumenSeedBox.x1, lumenSeedBox.y1],
              [lumenSeedBox.x2, lumenSeedBox.y1],
              [lumenSeedBox.x2, lumenSeedBox.y2],
              [lumenSeedBox.x1, lumenSeedBox.y2],
            ]
            : []
      )
      : getCurrentTrackedPolygon();
    if (!patient || initialPolygon.length < 3 || (nnInteractiveBusy && !prime)) {
      if (!initialPolygon.length && patient) {
        setMessage(
          target === 'lumen'
            ? (zh ? '请先检测或分割胃腔，再启动胃腔边界辅助' : 'Detect or segment the lumen before boundary assistance')
            : (zh ? '请先框选病灶，再启动病灶边界辅助' : 'Create a lesion mask before boundary assistance'),
        );
      }
      return;
    }
    if (nnInteractiveAvailable !== true) {
      setNnInteractiveMode(false);
      setMessage(
        zh
          ? '边界辅助服务未连接，请启动辅助服务后点击状态图标重试'
          : 'Boundary assistance is offline; start the service and retry from the status icon',
      );
      return;
    }
    const traceId = `nninteractive_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
    const traceStartedAt = performance.now();
    nnInteractiveAbortRef.current?.abort();
    const abortController = new AbortController();
    nnInteractiveAbortRef.current = abortController;
    const requestId = nnInteractiveRequestRef.current + 1;
    nnInteractiveRequestRef.current = requestId;
    setNnInteractiveBusy(true);
    freezeCurrentFrame();
    try {
      const liveVideoTime = mediaMode === 'video'
        ? Number((videoRef.current?.currentTime ?? videoTime).toFixed(3))
        : 0;
      const frame = await videoOrImageToSamFrame(
        videoRef.current,
        imgRef.current,
        mediaMode === 'video',
        1024,
      );
      if (requestId !== nnInteractiveRequestRef.current || abortController.signal.aborted) return;
      const lumenKey = lumenSeedBox
        ? [lumenSeedBox.x1, lumenSeedBox.y1, lumenSeedBox.x2, lumenSeedBox.y2]
          .map((value) => Number(value).toFixed(1))
          .join(',')
        : 'nolumen';
      const frameKey = [
        patient.id,
        target,
        mediaMode,
        videoUrl,
        mediaMode === 'video' ? liveVideoTime.toFixed(3) : 'image',
        lumenKey,
      ].join(':');
      const sessionState = nnInteractiveSessionRef.current;
      if (sessionState.key !== frameKey || !sessionState.id) {
        sessionState.key = frameKey;
        sessionState.id = `gastric_${patient.id}_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
        sessionState.initialized = false;
        setNnInteractiveClicks([]);
        setPromptStrokes([]);
        promptStrokesRef.current = [];
      }
      const requestPoints = [
        ...additionalPoints,
        ...(interaction ? [interaction] : []),
      ];
      if (requestPoints.length) {
        setNnInteractiveClicks((previous) => [...previous, ...requestPoints]);
      }
      const scalePoint = (point: number[]) => [
        Number((point[0] * frame.scale).toFixed(2)),
        Number((point[1] * frame.scale).toFixed(2)),
      ];
      const scaleStroke = (stroke: ActiveSamStroke) => ({
        points: stroke.points.map((point) => {
          const [x, y] = scalePoint(point);
          return { x, y, label: stroke.label };
        }),
        label: stroke.label,
        width: Math.max(1, Math.round(stroke.width * frame.scale)),
      });
      const scaledScribbles = scribbles
        .filter((stroke) => stroke.kind === 'scribble')
        .map(scaleStroke);
      const scaledLassos = scribbles
        .filter((stroke) => stroke.kind === 'lasso')
        .map(scaleStroke);
      const response = await fetch('/api/agent/nninteractive', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          session_id: sessionState.id,
          case_id: patient.patient_id,
          frame_time: liveVideoTime,
          frame_png_b64: frame.b64,
          image_width: frame.width,
          image_height: frame.height,
          reset_session: !sessionState.initialized,
          initial_mask_polygon: !sessionState.initialized
            ? initialPolygon.map(scalePoint)
            : [],
          points: requestPoints.map((point) => ({
            x: Number((point.x * frame.scale).toFixed(2)),
            y: Number((point.y * frame.scale).toFixed(2)),
            label: point.label,
          })),
          scribbles: scaledScribbles,
          lassos: scaledLassos,
          prime_session: Boolean(prime) && requestPoints.length === 0 && scribbles.length === 0,
        }),
        signal: abortController.signal,
      });
      const data = await response.json() as {
        ok?: boolean;
        available?: boolean;
        error?: string;
        result?: {
          mask_polygon?: number[][];
          backend_id?: string;
          model?: string;
          prompt_meta?: Record<string, unknown>;
          error?: string;
        };
      };
      if (requestId !== nnInteractiveRequestRef.current || abortController.signal.aborted) return;
      if (!response.ok || !data.ok) {
        throw new Error(data.error || data.result?.error || 'Boundary assistance returned no valid mask');
      }
      sessionState.initialized = true;
      setNnInteractiveAvailable(true);
      if (prime && requestPoints.length === 0 && scribbles.length === 0) {
        maskAuditRef.current('model_trace', {
          trace_id: traceId,
          operation: 'nninteractive_prime',
          model: 'nninteractive',
          source: 'nninteractive',
          target,
          outcome: 'success',
          frame_time_sec: liveVideoTime,
          input: { session_id: sessionState.id, prime: true },
          duration_ms: Math.round(performance.now() - traceStartedAt),
        });
        setMessage(
          target === 'lumen'
            ? (zh ? '胃腔精修会话已就绪，请点漏/凸或涂一条要改的边' : 'Lumen refine session is ready; click or scribble to edit')
            : (zh ? '病灶精修会话已就绪，请点漏/凸或涂一条要改的边' : 'Lesion refine session is ready; click or scribble to edit'),
        );
        return;
      }
      if (!data.result?.mask_polygon?.length) {
        throw new Error(data.error || data.result?.error || 'Boundary assistance returned no valid mask');
      }
      const rawPolygon = data.result.mask_polygon.map((point) => [
        point[0] / frame.scale,
        point[1] / frame.scale,
      ]);
      if (rawPolygon.length < 3) {
        throw new Error('Boundary assistance returned an invalid contour');
      }
      const nextPolygon = prepareEditableContour(
        rawPolygon,
        target === 'lumen' ? LUMEN_CONTOUR_MAX_POINTS : LESION_CONTOUR_MAX_POINTS,
      );
      maskAuditRef.current('model_trace', {
        trace_id: traceId,
        operation: 'nninteractive_refine',
        model: data.result.model || 'nninteractive',
        backend_id: data.result.backend_id,
        source: 'nninteractive',
        target,
        outcome: 'success',
        frame_time_sec: liveVideoTime,
        input: {
          reset_session: !sessionState.initialized,
          point_count: requestPoints.length,
          positive_points: requestPoints.filter((point) => point.label !== 'negative').length,
          negative_points: requestPoints.filter((point) => point.label === 'negative').length,
          scribble_count: scaledScribbles.length,
          lasso_count: scaledLassos.length,
          session_id: sessionState.id,
        },
        output: {
          polygon_points: nextPolygon.length,
          prompt_meta: data.result.prompt_meta,
        },
        duration_ms: Math.round(performance.now() - traceStartedAt),
      });
      sessionState.initialized = true;
      setNnInteractiveAvailable(true);
      if (target === 'lumen') {
        lumenPolygonRef.current = nextPolygon;
        setLumenPolygon(nextPolygon);
        setLumenEditMode(false);
        setLumenResultMeta((previous) => ({
          ...previous,
          source: 'nninteractive',
          sam_backend_id: 'nninteractive_remote_v1',
          error: undefined,
        }));
      } else {
        contourInteractionRef.current = true;
        generatedLesionRef.current = clonePoly(nextPolygon);
        pointsRef.current = nextPolygon;
        setPoints(nextPolygon);
      }
      if (simpleVideoMode && mediaMode === 'video') {
        recordVideoFrameOverride(
          target === 'lesion' ? nextPolygon : getCurrentTrackedPolygon(),
          'accepted',
        );
        setTrackingPrepared(false);
        setTrackOnPlay(false);
      }
      if (simpleVideoMode && target === 'lesion' && nextPolygon.length >= 3) {
        scheduleCompleteMaskAutosaveRef.current('auto_save');
      }
      onImagingAssist?.({
        layerResult,
        lesionPolygon: target === 'lesion' ? nextPolygon : pointsRef.current,
        wallPolygon: wallPointsRef.current,
        frameSize: { width: frame.fullWidth, height: frame.fullHeight },
        lumenBBox: lumenBoxRef.current,
        lumenPolygon: lumenPolygonRef.current.length >= 3 ? lumenPolygonRef.current : undefined,
      });
      setMessage(
        zh
          ? `边界辅助已精修${target === 'lumen' ? '胃腔' : '病灶'}边界（${nextPolygon.length} 点），可继续用正/负点修正`
          : `Boundary assistance refined the ${target === 'lumen' ? 'lumen' : 'lesion'} contour (${nextPolygon.length} points); add positive or negative points to refine further`,
      );
    } catch (error) {
      const aborted = error instanceof DOMException && error.name === 'AbortError';
      maskAuditRef.current('model_trace', {
        trace_id: traceId,
        operation: 'nninteractive_refine',
        model: 'nninteractive',
        source: 'nninteractive',
        target,
        outcome: aborted ? 'aborted' : 'error',
        frame_time_sec: Number((videoRef.current?.currentTime ?? videoTime).toFixed(3)),
        input: {
          point_count: additionalPoints.length + (interaction ? 1 : 0),
          scribble_count: scribbles.filter((stroke) => stroke.kind === 'scribble').length,
          lasso_count: scribbles.filter((stroke) => stroke.kind === 'lasso').length,
          session_id: nnInteractiveSessionRef.current.id || undefined,
        },
        error: aborted
          ? undefined
          : error instanceof Error ? error.message.slice(0, 240) : 'Boundary assistance failed',
        duration_ms: Math.round(performance.now() - traceStartedAt),
      });
      if (requestId !== nnInteractiveRequestRef.current || abortController.signal.aborted) return;
      if (aborted) return;
      nnInteractiveSessionRef.current.initialized = false;
      const detail = error instanceof Error ? error.message : '';
      const serviceUnavailable = detail === 'fetch failed'
        || detail.includes('bridge')
        || detail.includes('NN_INTERACTIVE_SERVER_URL')
        || detail.toLowerCase().includes('nninteractive');
      if (serviceUnavailable) {
        setNnInteractiveAvailable(false);
      }
      setMessage(
        serviceUnavailable
          ? (target === 'lesion'
            ? (zh
              ? 'nnInteractive 边界辅助服务未连接，未切换到 SAM3.1；请启动服务后重试'
              : 'nnInteractive is unavailable; staying out of SAM3.1. Start the service and retry')
            : (zh
              ? '胃腔 nnInteractive 辅助服务未启动，请先启动辅助服务'
              : 'Lumen nnInteractive assistance is unavailable; start the service first'))
          : (detail || (zh ? '边界辅助失败' : 'Boundary assistance failed')),
      );
    } finally {
      if (nnInteractiveAbortRef.current === abortController) {
        nnInteractiveAbortRef.current = null;
      }
      if (requestId === nnInteractiveRequestRef.current) setNnInteractiveBusy(false);
    }
  }, [
    freezeCurrentFrame,
    getCurrentTrackedPolygon,
    layerResult,
    mediaMode,
    nnInteractiveAvailable,
    nnInteractiveBusy,
    onImagingAssist,
    patient,
    recordVideoFrameOverride,
    simpleVideoMode,
    videoTime,
    videoUrl,
    zh,
  ]);

  const activateNnInteractive = useCallback((target: 'lesion' | 'lumen') => {
    setLumenSculptMode(null);
    const hasMask = target === 'lesion'
      ? getCurrentTrackedPolygon().length >= 3
      : lumenPolygonRef.current.length >= 3 || Boolean(lumenBoxRef.current);
    if (!hasMask) {
      setMessage(
        target === 'lesion'
          ? (zh ? '请先框选或自动找到病灶，再精修' : 'Create a lesion contour before refining')
          : (zh ? '请先检测或分割胃腔，再精修' : 'Detect or segment the lumen before refining'),
      );
      return;
    }
    setSam31RefineTarget(null);
    setMode('sam');
    setSimplePromptMode('point');
    armLesionBox(false);
    setSimpleEditMode(false);
    setLumenEditMode(false);
    setTrackOnPlay(false);
    setActiveSamPromptLabel('positive');
    if (nnInteractiveAvailable !== true) {
      setNnInteractiveMode(false);
      setSam31RefineTarget(target);
      setMessage(
        target === 'lesion'
          ? (zh
            ? 'nnInteractive 未连接，已改用 SAM 3.1 正/负点；正点并入，负点排除'
            : 'nnInteractive is offline; using SAM 3.1 points. Positive keeps, negative excludes')
          : (zh
            ? 'nnInteractive 未连接，已改用 SAM 3.1 精修胃腔'
            : 'nnInteractive is offline; using SAM 3.1 to refine the lumen'),
      );
      void refreshNnInteractiveStatus();
      return;
    }
    const switching = nnInteractiveMode && nnInteractiveTarget !== target;
    if (switching) {
      invalidateNnInteractiveSession({ abort: true });
    }
    setNnInteractiveTarget(target);
    setNnInteractiveMode(true);
    freezeCurrentFrame();
    setMessage(
      target === 'lesion'
        ? (zh
          ? '病灶精修已开启：点漏/凸为正，Shift 或负点排除伪影与壁；也可涂鸦或套索。首次载入会话可能需几秒。'
          : 'Lesion refine is on: click leaks/bulges to keep, Shift-click artifacts or wall to cut; scribble and lasso also work. The first session load can take a few seconds.')
        : (zh
          ? '胃腔精修已开启：点要包含的区域，Shift 排除贴壁或伪影；也可涂鸦或套索。首次载入会话可能需几秒。'
          : 'Lumen refine is on: click regions to keep, Shift-click wall or artifact to cut; scribble and lasso also work. The first session load can take a few seconds.'),
    );
    const shouldPrime = switching || !nnInteractiveSessionRef.current.initialized;
    if (shouldPrime) {
      void refineWithNnInteractive(target, undefined, [], [], true);
    }
  }, [
    freezeCurrentFrame,
    getCurrentTrackedPolygon,
    invalidateNnInteractiveSession,
    nnInteractiveAvailable,
    nnInteractiveMode,
    nnInteractiveTarget,
    refineWithNnInteractive,
    refreshNnInteractiveStatus,
    zh,
  ]);

  useEffect(() => {
    if (!nnInteractiveMode || mediaMode !== 'video') return;
    const live = Number((videoRef.current?.currentTime ?? videoTime).toFixed(3)).toFixed(3);
    const sessionKey = nnInteractiveSessionRef.current.key;
    if (!sessionKey) return;
    const parts = sessionKey.split(':');
    if (!parts.includes(live)) {
      invalidateNnInteractiveSession({ abort: true });
      void refineWithNnInteractive(nnInteractiveTarget, undefined, [], [], true);
    }
  }, [
    invalidateNnInteractiveSession,
    mediaMode,
    nnInteractiveMode,
    nnInteractiveTarget,
    refineWithNnInteractive,
    videoTime,
  ]);

  const buildLumenOverride = useCallback((): LumenOverride | null => {
    const currentLumenBox = lumenBoxRef.current;
    const currentLumenPolygon = lumenPolygonRef.current;
    const resolvedLumenBox = currentLumenBox || (currentLumenPolygon.length >= 3 ? bboxFromPolygon(currentLumenPolygon) : null);
    if (!patient || !resolvedLumenBox) return null;
    const video = videoRef.current;
    const img = imgRef.current;
    const width =
      mediaMode === 'video' && video?.videoWidth
        ? video.videoWidth
        : (img?.naturalWidth || lumenOverride?.imageWidth || 0);
    const height =
      mediaMode === 'video' && video?.videoHeight
        ? video.videoHeight
        : (img?.naturalHeight || lumenOverride?.imageHeight || 0);
    if (!width || !height) return null;
    return {
      patientId: patient.patient_id,
      frameId: patient.id,
      imageWidth: width,
      imageHeight: height,
      lumen_bbox: normalizeLumenBBox(resolvedLumenBox),
      lumen_polygon: currentLumenPolygon.length >= 3
        ? currentLumenPolygon.map((p) => [Math.round(p[0] * 10) / 10, Math.round(p[1] * 10) / 10])
        : undefined,
      lumen_confidence: lumenConfidence ?? undefined,
      lumen_mask_type: currentLumenPolygon.length >= 3
        ? (lumenResultMeta?.source === 'nninteractive' ? 'nninteractive_polygon' : 'sam31_polygon')
        : 'bbox_proxy',
      source: lumenResultMeta?.source || (currentLumenPolygon.length >= 3 ? 'yolo_then_sam31' : 'yolo'),
      detector_backend_id: lumenResultMeta?.detector_backend_id,
      sam_backend_id: lumenResultMeta?.sam_backend_id,
      sam_score: lumenResultMeta?.sam_score,
      video_time_sec: mediaMode === 'video' ? Number(videoTime.toFixed(3)) : undefined,
      video_url: mediaMode === 'video' ? videoUrl || undefined : undefined,
      updated_at: new Date().toISOString(),
    };
  }, [
    lumenConfidence,
    lumenOverride?.imageHeight,
    lumenOverride?.imageWidth,
    lumenResultMeta,
    mediaMode,
    patient,
    videoTime,
    videoUrl,
  ]);

  const detectLumen = useCallback(async (): Promise<LumenBBox | null> => {
    if (!patient || lumenBusy) return null;
    recordDoctorOp('tool_switch', { layer: 'lumen', operation: 'detect_lumen', tool: 'detect_lumen' });
    const traceId = `lumen_detect_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
    const traceStartedAt = performance.now();
    setLumenBusy(true);
    setLumenResultMeta(null);
    setMessage(zh ? '胃腔 YOLO 检测中…' : 'Detecting gastric lumen…');
    try {
      const frame = await videoOrImageToSamFrame(
        videoRef.current,
        imgRef.current,
        mediaMode === 'video',
        1024,
      );
      const scale = frame.scale || 1;
      const response = await fetch('/api/agent/lumen-detection', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          frame_png_b64: frame.b64,
          image_width: frame.width,
          image_height: frame.height,
        }),
      });
      const data = await readJsonPayload<{
        ok?: boolean;
        available?: boolean;
        lumen_detected?: boolean;
        lumen_bbox?: LumenBBox;
        lumen_confidence?: number;
        backend_id?: string;
        error?: string;
      }>(response, 'Lumen detection endpoint');
      if (!response.ok || !data.ok) {
        throw new Error(data.error || 'Lumen detection failed');
      }
      if (!data.lumen_detected || !data.lumen_bbox) {
        maskAuditRef.current('model_trace', {
          trace_id: traceId,
          operation: 'lumen_detection',
          model: 'lumen_detector',
          source: 'lumen_detection_endpoint',
          outcome: 'no_detection',
          frame_time_sec: Number((videoRef.current?.currentTime ?? videoTime).toFixed(3)),
          output: { backend_id: data.backend_id },
          duration_ms: Math.round(performance.now() - traceStartedAt),
        });
        setLumenBox(null);
        setLumenPolygon([]);
        setLumenConfidence(null);
        setLumenResultMeta({ error: data.error || 'no lumen detected', detector_backend_id: data.backend_id });
        setMessage(zh ? '未检测到胃腔，可手动框选后分割' : 'No lumen detected; draw a box then segment');
        return null;
      }
      // Keep the detector box as-is. Auto-expand made the lumen ROI jump toward the lesion.
      const box = normalizeLumenBBox({
        x1: data.lumen_bbox.x1 / scale,
        y1: data.lumen_bbox.y1 / scale,
        x2: data.lumen_bbox.x2 / scale,
        y2: data.lumen_bbox.y2 / scale,
      });
      lumenBoxRef.current = box;
      lumenPolygonRef.current = [];
      setLumenBox(box);
      setLumenPolygon([]);
      setLumenConfidence(typeof data.lumen_confidence === 'number' ? data.lumen_confidence : null);
      setNnInteractiveMode(false);
      setLumenResultMeta({
        detector_backend_id: data.backend_id,
        source: 'yolo',
      });
      maskAuditRef.current('model_trace', {
        trace_id: traceId,
        operation: 'lumen_detection',
        model: 'lumen_detector',
        source: 'lumen_detection_endpoint',
        outcome: 'success',
        frame_time_sec: Number((videoRef.current?.currentTime ?? videoTime).toFixed(3)),
        output: {
          backend_id: data.backend_id,
          confidence: data.lumen_confidence,
          bbox_present: true,
          expanded_for_wall_and_mass: false,
        },
        duration_ms: Math.round(performance.now() - traceStartedAt),
      });
      freezeCurrentFrame();
      // Stay in box-edit so the doctor can keep adjusting after detection.
      enterLumenBoxEdit(
        zh
          ? `已检出胃腔框（conf ${(data.lumen_confidence ?? 0).toFixed(2)}）。请手动拖调；勿依赖自动外扩。`
          : `Lumen box detected (conf ${(data.lumen_confidence ?? 0).toFixed(2)}). Drag to adjust; no auto-expand.`,
      );
      return box;
    } catch (error) {
      const messageText = error instanceof Error ? error.message : 'Lumen detection failed';
      maskAuditRef.current('model_trace', {
        trace_id: traceId,
        operation: 'lumen_detection',
        model: 'lumen_detector',
        source: 'lumen_detection_endpoint',
        outcome: 'error',
        frame_time_sec: Number((videoRef.current?.currentTime ?? videoTime).toFixed(3)),
        error: messageText.slice(0, 240),
        duration_ms: Math.round(performance.now() - traceStartedAt),
      });
      setLumenResultMeta({ error: messageText });
      setMessage(messageText);
      return null;
    } finally {
      setLumenBusy(false);
    }
  }, [enterLumenBoxEdit, freezeCurrentFrame, lumenBusy, mediaMode, patient, recordDoctorOp, videoTime, zh]);

  const segmentLumenWithSam31 = useCallback(async (
    extraClicks: Array<{ x: number; y: number; label: 'positive' | 'negative' }> = [],
  ): Promise<boolean> => {
    const currentLumenBox = lumenBoxRef.current;
    if (!patient || !currentLumenBox || lumenSamBusy) return false;
    recordDoctorOp('tool_switch', { layer: 'lumen', operation: 'segment_lumen', tool: 'segment_lumen' });
    const traceId = `lumen_segment_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
    const traceStartedAt = performance.now();
    freezeCurrentFrame();
    const lesionSnapshot = clonePoly(pointsRef.current);
    setLumenSamBusy(true);
    setMessage(zh ? '胃腔分割中…病灶轮廓保持不动' : 'Segmenting lumen… lesion contour stays put');
    try {
      const frame = await videoOrImageToSamFrame(
        videoRef.current,
        imgRef.current,
        mediaMode === 'video',
        1024,
      );
      const scale = frame.scale || 1;
      const box = normalizeLumenBBox(currentLumenBox);
      // Lumen uses base SAM3.1 (no gastric lesion LoRA) and box-only prompts.
      // Lesion negative clicks biased the contour away from true lumen.
      let response: Response;
      try {
        response = await fetch('/api/agent/sam-interactive', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            case_id: patient.patient_id,
            frame_png_b64: frame.b64,
            image_width: frame.width,
            image_height: frame.height,
            model: 'sam31',
            text_prompt: 'gastric lumen cavity',
            threshold: 0.2,
            use_lora: false,
            include_overlay: false,
            box: {
              x1: box.x1 * scale,
              y1: box.y1 * scale,
              x2: box.x2 * scale,
              y2: box.y2 * scale,
            },
            clicks: extraClicks.map((click) => ({
              x: click.x * scale,
              y: click.y * scale,
              label: click.label,
            })),
          }),
        });
      } catch (networkError) {
        const detail = networkError instanceof Error ? networkError.message : 'network error';
        throw new Error(
          zh
            ? `胃腔分割请求失败（${detail}）。请确认 SAM 服务可用后重试`
            : `Lumen segment request failed (${detail}). Check SAM service and retry`,
        );
      }
      let data: {
        ok?: boolean;
        error?: string;
        result?: {
          ok?: boolean;
          mask_polygon?: number[][];
          backend_id?: string;
          fallback_backend?: string;
          prompt_meta?: { sam_score?: number };
          error?: string;
        };
      };
      try {
        data = await response.json();
      } catch {
        throw new Error(
          zh
            ? `胃腔分割接口异常（HTTP ${response.status}）`
            : `Lumen segment API error (HTTP ${response.status})`,
        );
      }
      const result = data.result;
      if (!response.ok || !data.ok || !result?.mask_polygon || result.mask_polygon.length < 3) {
        throw new Error(data.error || result?.error || 'SAM3.1 returned no lumen polygon');
      }
      const maxCoord = Math.max(...result.mask_polygon.flatMap((point) => point));
      const polyFull = maxCoord <= 1.5
        ? result.mask_polygon.map((point) => [point[0] * frame.fullWidth, point[1] * frame.fullHeight])
        : result.mask_polygon.map((point) => [point[0] / scale, point[1] / scale]);
      let poly = prepareEditableContour(polyFull, LUMEN_CONTOUR_MAX_POINTS);
      // Guard against a mask that drifts far outside the doctor-confirmed lumen box.
      const outBox = bboxFromPolygon(poly);
      if (outBox) {
        const boxW = Math.max(24, box.x2 - box.x1);
        const boxH = Math.max(24, box.y2 - box.y1);
        const drift = outBox.x2 < box.x1 - boxW * 0.5
          || outBox.x1 > box.x2 + boxW * 0.5
          || outBox.y2 < box.y1 - boxH * 0.5
          || outBox.y1 > box.y2 + boxH * 0.5
          || (outBox.x2 - outBox.x1) > boxW * 4
          || (outBox.y2 - outBox.y1) > boxH * 4;
        if (drift) {
          const cx = (box.x1 + box.x2) / 2;
          const cy = (box.y1 + box.y2) / 2;
          const hw = boxW * 1.6;
          const hh = boxH * 1.6;
          poly = poly.map(([px, py]) => [
            Math.min(cx + hw, Math.max(cx - hw, px)),
            Math.min(cy + hh, Math.max(cy - hh, py)),
          ]);
        }
      }
      const usedSam2Fallback = result.fallback_backend === 'sam2_interactive';
      maskAuditRef.current('model_trace', {
        trace_id: traceId,
        operation: 'lumen_segmentation',
        model: usedSam2Fallback ? 'sam2_interactive_fallback' : 'sam31',
        backend_id: result.backend_id,
        source: 'lumen_segmentation_endpoint',
        outcome: 'success',
        frame_time_sec: Number((videoRef.current?.currentTime ?? videoTime).toFixed(3)),
        input: {
          box_prompt: true,
          use_lora: false,
          negative_lesion_guard: false,
        },
        output: {
          polygon_points: poly.length,
          score: result.prompt_meta?.sam_score,
          fallback_backend: result.fallback_backend,
        },
        duration_ms: Math.round(performance.now() - traceStartedAt),
      });
      setLumenPolygon(poly);
      lumenPolygonRef.current = poly;
      if (lesionSnapshot.length >= 3) {
        pointsRef.current = lesionSnapshot;
        setPoints(lesionSnapshot);
      }
      if (mediaMode === 'video' && lesionSnapshot.length >= 3) {
        recordVideoFrameOverride(lesionSnapshot, 'accepted');
      }
      // Leave lumen box-edit so the canvas shows the lumen contour.
      // Do not exit lesion refine or rewrite the lesion polygon.
      setLumenEditMode(false);
      if (nnInteractiveTarget === 'lumen') {
        setNnInteractiveMode(false);
        setSimplePromptMode('box');
      }
      setLumenResultMeta((prev) => {
        const source = usedSam2Fallback
          ? 'sam2_fallback'
          : (prev?.source === 'manual' || prev?.source === 'yolo_then_manual'
            ? 'yolo_then_sam31'
            : (prev?.source === 'yolo' ? 'yolo_then_sam31' : 'sam31'));
        return {
          ...prev,
          sam_backend_id: result.backend_id || 'sam3.1_multiplex_static',
          sam_score: result.prompt_meta?.sam_score,
          source,
          error: undefined,
        };
      });
      onImagingAssist?.({
        layerResult,
        lesionPolygon: pointsRef.current,
        wallPolygon: wallPointsRef.current,
        frameSize: { width: frame.fullWidth, height: frame.fullHeight },
        lumenBBox: box,
        lumenPolygon: poly,
      });
      freezeCurrentFrame();
      // Do not auto-start video tracking here. Joint lesion+lumen tracking starts
      // only when the doctor clicks「视频跟踪」after both contours are ready.
      const lesionReady = pointsRef.current.length >= 3;
      setMessage(
        zh
          ? (lesionReady
            ? `已生成胃腔轮廓（${poly.length} 点），病灶位置未改。确认后可点「视频跟踪」。`
            : `已生成胃腔轮廓（${poly.length} 点）。请先完成病灶分割，再点「视频跟踪」。`)
          : (lesionReady
            ? `Lumen contour ready (${poly.length} points); lesion unchanged. Tap Track video when both look right.`
            : `Lumen contour ready (${poly.length} points). Finish the lesion contour, then tap Track video.`),
      );
      return true;
    } catch (error) {
      const messageText = error instanceof Error ? error.message : (zh ? '胃腔分割失败' : 'Lumen segmentation failed');
      maskAuditRef.current('model_trace', {
        trace_id: traceId,
        operation: 'lumen_segmentation',
        model: 'sam31',
        source: 'lumen_segmentation_endpoint',
        outcome: 'error',
        frame_time_sec: Number((videoRef.current?.currentTime ?? videoTime).toFixed(3)),
        input: { box_prompt: true },
        error: messageText.slice(0, 240),
        duration_ms: Math.round(performance.now() - traceStartedAt),
      });
      setLumenResultMeta((prev) => ({ ...prev, error: messageText }));
      setMessage(messageText);
      return false;
    } finally {
      setLumenSamBusy(false);
    }
  }, [freezeCurrentFrame, layerResult, lumenSamBusy, mediaMode, nnInteractiveTarget, onImagingAssist, patient, recordDoctorOp, recordVideoFrameOverride, videoTime, zh]);

  const startSam31Refine = useCallback(async (target: 'lesion' | 'lumen') => {
    const lesionPoly = getCurrentTrackedPolygon();
    const hasLesion = lesionPoly.length >= 3;
    const hasLumen = lumenPolygonRef.current.length >= 3 || Boolean(lumenBoxRef.current);
    if (target === 'lesion' && !hasLesion) {
      setMessage(zh ? '请先框选或自动找到病灶，再精修' : 'Create a lesion contour before refining');
      return;
    }
    if (target === 'lumen' && !hasLumen) {
      setMessage(zh ? '请先检测或分割胃腔，再精修' : 'Detect or segment the lumen before refining');
      return;
    }
    setNnInteractiveMode(false);
    setSimpleEditMode(false);
    setLumenEditMode(false);
    setSam31RefineTarget(target);
    setSimplePromptMode('point');
    setMode('sam');
    setTrackOnPlay(false);
    if (target === 'lesion') {
      const box = bboxFromPolygon(lesionPoly) || null;
      const centroid = polygonCentroid(lesionPoly);
      setMessage(zh ? 'SAM 3.1 精修病灶…' : 'SAM 3.1 refining lesion…');
      const next = await runLesionModelRef.current(
        centroid,
        box,
        samClicksRef.current,
        'sam31',
      );
      if (next && next.length >= 3) {
        setMessage(zh ? '病灶已用 SAM 3.1 精修；可再点正/负点，或改用编辑轮廓' : 'Lesion refined with SAM 3.1; add pos/neg clicks or edit the contour');
      }
      return;
    }
    setMessage(zh ? 'SAM 3.1 精修胃腔…' : 'SAM 3.1 refining lumen…');
    const ok = await segmentLumenWithSam31();
    if (ok) {
      setMessage(zh ? '胃腔已用 SAM 3.1 精修；可再点正/负点继续修' : 'Lumen refined with SAM 3.1; add pos/neg clicks to continue');
    }
  }, [getCurrentTrackedPolygon, segmentLumenWithSam31, zh]);

  const handleSaveLumen = useCallback(async (silent = false): Promise<boolean> => {
    const next = buildLumenOverride();
    if (!next) {
      if (!silent) setMessage(zh ? '请先检测或框选胃腔' : 'Detect or draw a lumen box first');
      return false;
    }
    if (!silent) {
      recordDoctorOp('lumen_edit', {
        layer: 'lumen',
        operation: 'save_lumen',
        tool: 'save_lumen',
        point_count: lumenPolygonRef.current.length,
      });
    }
    setLumenSaving(true);
    try {
      const res = await fetch('/api/patients/lumen-overrides', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ override: next }),
      });
      const data = await res.json() as { override?: LumenOverride; error?: string };
      if (!res.ok) throw new Error(data.error || 'Save lumen failed');
      const saved = data.override || next;
      onLumenOverrideChange?.(saved);
      // Do not exit lumen box edit on save — doctors need continuous adjustment.
      // Only an explicit "完成调整" toggle leaves edit mode.
      if (pointsRef.current.length >= 3) {
        void persistOverrideRef.current(
          silent ? 'lumen_auto_save' : 'lumen_manual_save',
          { silent: true },
        );
      }
      maskAuditRef.current('mask_saved', {
        action: silent ? 'lumen_auto_save' : 'lumen_manual_save',
        success: true,
        lumen_points: saved.lumen_polygon?.length || 0,
        lumen_box_present: Boolean(saved.lumen_bbox),
        lumen_source: saved.source,
        detector_backend_id: saved.detector_backend_id,
        sam_backend_id: saved.sam_backend_id,
      });
      if (!silent) setMessage(zh ? '胃腔结果已保存，分析将优先使用此框' : 'Lumen override saved for Agent geometry');
      return true;
    } catch (error) {
      maskAuditRef.current('mask_saved', {
        action: silent ? 'lumen_auto_save' : 'lumen_manual_save',
        success: false,
        error: error instanceof Error ? error.message.slice(0, 240) : 'Save lumen failed',
      });
      setMessage(error instanceof Error ? error.message : 'Save lumen failed');
      return false;
    } finally {
      setLumenSaving(false);
    }
  }, [buildLumenOverride, onLumenOverrideChange, recordDoctorOp, zh]);

  const recordDoctorWorkflowStep = useCallback((
    stepId: string,
    action: string,
    status: 'started' | 'completed' | 'error' | 'skipped',
    details: { input?: Record<string, unknown>; output?: Record<string, unknown>; error?: string } = {},
  ) => {
    const traceId = `doctor_workflow_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
    maskAuditRef.current('model_trace', {
      trace_id: traceId,
      operation: `doctor_workflow:${stepId}`,
      model: 'doctor_workflow_agent',
      source: 'doctor_workflow',
      outcome: status,
      frame_time_sec: Number((videoRef.current?.currentTime ?? videoTime).toFixed(3)),
      ...details,
    });
    if (canvasWorkflowLabelRef.current) setWorkflowStepLabel(action);
  }, [videoTime]);

  const runDoctorWorkflow = useCallback(async () => {
    if (!simpleVideoMode || mediaMode !== 'video' || workflowBusy) return;
    canvasWorkflowLabelRef.current = true;
    setWorkflowBusy(true);
    recordDoctorWorkflowStep('workflow_start', '开始医生式全流程', 'started');
    try {
      let detectedLumenBox = lumenBoxRef.current;
      if (!detectedLumenBox) {
        recordDoctorWorkflowStep('lumen_detection', '自动检测胃腔框', 'started');
        detectedLumenBox = await detectLumen();
        if (!detectedLumenBox) throw new Error('自动检测胃腔失败，请手动框选胃腔');
        recordDoctorWorkflowStep('lumen_detection', '自动检测胃腔框', 'completed', {
          output: { bbox: detectedLumenBox, source: 'lumen_detector' },
        });
      } else {
        recordDoctorWorkflowStep('lumen_reuse', '复用已有胃腔位置', 'skipped', {
          output: { bbox: detectedLumenBox, reason: 'existing_lumen_prompt' },
        });
      }

      let lesion = pointsRef.current;
      if (lesion.length < 3) {
        recordDoctorWorkflowStep('lesion_detection', '自动检测病灶候选', 'started', {
          input: {
            model: publicLesionSegModel(segmentationModel),
            prompt: publicLesionSegModel(segmentationModel) === 'dinov3'
              ? 'full_image_dino'
              : 'lesion_box_then_lora_mask',
          },
        });
        lesion = await findLesionCandidate() || [];
        if (lesion.length < 3) throw new Error('自动检测病灶失败，请手动框选病灶');
        recordDoctorWorkflowStep('lesion_detection', '自动检测病灶候选', 'completed', {
          output: { polygon_points: lesion.length, source: publicLesionSegModel(segmentationModel) },
        });
      } else {
        recordDoctorWorkflowStep('lesion_reuse', '复用已有病灶位置', 'skipped', {
          output: { polygon_points: lesion.length, reason: 'existing_lesion_prompt' },
        });
      }

      const seedBox = bboxFromPolygon(lesion);
      const seedCenter = polygonCentroid(lesion);
      if (!seedBox || !seedCenter) throw new Error('病灶候选无法生成中心提示');
      recordDoctorWorkflowStep('center_prompt', '在病灶中心添加正点并重新检测', 'started', {
        input: { center: seedCenter, box: seedBox, label: 'positive' },
      });
      const refined = await runLesionModelRef.current(
            seedCenter,
            seedBox,
            [{ x: seedCenter[0], y: seedCenter[1], label: 'positive' }],
            publicLesionSegModel(segmentationModel),
          );
      if (refined && refined.length >= 3) {
        pointsRef.current = refined;
        setPoints(refined);
        lesion = refined;
      }
      recordDoctorWorkflowStep('center_prompt', '在病灶中心添加正点并重新检测', refined?.length ? 'completed' : 'error', {
        output: { polygon_points: refined?.length || 0 },
        error: refined?.length ? undefined : 'center_refinement_returned_no_mask',
      });
      if (!refined?.length) throw new Error('中心正点精修未返回有效病灶轮廓');

      recordDoctorWorkflowStep('lumen_refinement', '参考病灶位置重新生成胃腔轮廓', 'started');
      const lumenSegmented = await segmentLumenWithSam31();
      if (!lumenSegmented) throw new Error('胃腔轮廓精修未返回有效结果');
      const lumenSaved = await handleSaveLumen(true);
      if (!lumenSaved) throw new Error('胃腔轮廓自动保存失败');
      recordDoctorWorkflowStep('lumen_refinement', '参考病灶位置重新生成胃腔轮廓', 'completed', {
        output: {
          lumen_points: lumenPolygonRef.current.length,
          lesion_guard: true,
        },
      });

      // Do not auto-start tracking or multi-frame Agent after lumen segmentation.
      // Doctor confirms both contours, then clicks「视频跟踪」to track lesion+lumen together.
      recordDoctorWorkflowStep('video_tracking', '等待医生确认后手动开跟踪', 'skipped', {
        output: {
          reason: 'await_manual_joint_track',
          lesion_points: lesion.length,
          lumen_points: lumenPolygonRef.current.length,
        },
      });
      recordDoctorWorkflowStep('workflow_complete', '病灶与胃腔分割完成，等待手动跟踪', 'completed', {
        output: { lesion_points: lesion.length, lumen_points: lumenPolygonRef.current.length },
      });
      scheduleCompleteMaskAutosaveRef.current('auto_save');
      setMessage(
        zh
          ? '病灶与胃腔分割已完成。确认轮廓后点「视频跟踪」，将同时跟踪病灶与胃腔。'
          : 'Lesion and lumen contours are ready. Confirm, then tap Track video to track both together.',
      );
    } catch (error) {
      const messageText = error instanceof Error ? error.message : '医生式全流程失败';
      recordDoctorWorkflowStep('workflow_complete', '医生式全流程失败', 'error', { error: messageText });
      setMessage(messageText);
    } finally {
      canvasWorkflowLabelRef.current = false;
      setWorkflowBusy(false);
      setWorkflowStepLabel(null);
    }
  }, [
    detectLumen,
    findLesionCandidate,
    handleSaveLumen,
    mediaMode,
    recordDoctorWorkflowStep,
    runSamAtPoint,
    segmentLumenWithSam31,
    segmentationModel,
    simpleVideoMode,
    workflowBusy,
    zh,
  ]);

  /** Contour-anchored Assist: lesion contour is required; lumen is optional. */
  const runContourAnchoredAssist = useCallback(async () => {
    if (!onUnifiedAgentRun || !simpleVideoMode || mediaMode !== 'video' || unifiedAgentBusy || workflowBusy) return;
    setAssistOverlayOpen(true);
    setTaskProgress({
      label: zh ? '辅助分析' : 'Assisted analysis',
      step: 1,
      totalSteps: ASSIST_ANALYSIS_STEPS.length,
      detail: zh ? ASSIST_ANALYSIS_STEPS[0].zh : ASSIST_ANALYSIS_STEPS[0].en,
    });
    const boundKeyframe = await ensureActiveDoctorKeyframeForAnalysis({ seek: false });
    if (!boundKeyframe) {
      setAssistOverlayOpen(false);
      setTaskProgress(null);
      return;
    }
    if (pointsRef.current.length < 3) {
      setAssistOverlayOpen(false);
      setTaskProgress(null);
      setMessage(zh ? '请先框选病灶' : 'Draw a lesion box first');
      return;
    }

    const prepared: string[] = [];

    contourPrepActionsRef.current = prepared;
    setTaskProgress({
      label: zh ? '辅助分析' : 'Assisted analysis',
      step: 2,
      totalSteps: ASSIST_ANALYSIS_STEPS.length,
      detail: zh ? ASSIST_ANALYSIS_STEPS[1].zh : ASSIST_ANALYSIS_STEPS[1].en,
    });
    await runUnifiedAgent();
  }, [
    ensureActiveDoctorKeyframeForAnalysis,
    handleSaveLumen,
    mediaMode,
    onUnifiedAgentRun,
    runUnifiedAgent,
    segmentLumenWithSam31,
    simpleVideoMode,
    unifiedAgentBusy,
    workflowBusy,
    zh,
  ]);

  useEffect(() => {
    const onRunAssist = () => {
      void runContourAnchoredAssist();
    };
    window.addEventListener('gastric:run-assist', onRunAssist);
    return () => window.removeEventListener('gastric:run-assist', onRunAssist);
  }, [runContourAnchoredAssist]);

  const autoDetectLesion = useCallback(async () => {
    if (!simpleVideoMode || mediaMode !== 'video' || lesionAutoBusy) return;
    canvasWorkflowLabelRef.current = true;
    setLesionAutoBusy(true);
    recordDoctorWorkflowStep('lesion_detection', '自动检测病灶候选', 'started', {
      input: {
        model: publicLesionSegModel(segmentationModel),
        prompt: publicLesionSegModel(segmentationModel) === 'dinov3'
          ? 'full_image_dino'
          : 'lesion_box_then_lora_mask',
      },
    });
    try {
      const polygon = await findLesionCandidate();
      if (!polygon || polygon.length < 3) {
        throw new Error('自动检测病灶未返回有效候选轮廓');
      }
      recordDoctorWorkflowStep('lesion_detection', '自动检测病灶候选', 'completed', {
        output: { polygon_points: polygon.length, model: publicLesionSegModel(segmentationModel) },
      });
      setMessage(zh ? '已找到病灶候选；可用「编辑轮廓」微调后点顶中辅助分析' : 'Lesion candidate found; refine with Edit, then use top Assist');
    } catch (error) {
      const messageText = error instanceof Error ? error.message : '自动检测病灶失败';
      recordDoctorWorkflowStep('lesion_detection', '自动检测病灶候选', 'error', { error: messageText });
      setMessage(messageText);
    } finally {
      canvasWorkflowLabelRef.current = false;
      setLesionAutoBusy(false);
      setWorkflowStepLabel(null);
    }
  }, [findLesionCandidate, lesionAutoBusy, mediaMode, recordDoctorWorkflowStep, segmentationModel, simpleVideoMode, zh]);

  useEffect(() => {
    persistLumenOverrideRef.current = handleSaveLumen;
  }, [handleSaveLumen]);

  const handleClearLumen = useCallback(async () => {
    if (!patient) return;
    setLumenSaving(true);
    try {
      await fetch(
        `/api/patients/lumen-overrides?patientId=${encodeURIComponent(patient.patient_id)}&frameId=${encodeURIComponent(patient.id)}`,
        { method: 'DELETE' },
      );
      setLumenBox(null);
      setLumenPolygon([]);
      setLumenConfidence(null);
      setLumenEditMode(false);
      setLumenResultMeta(null);
      setViewFocusBox(null);
      setViewFocusMode(null);
      onLumenOverrideChange?.(null);
      maskAuditRef.current('mask_event', {
        action: 'lumen_cleared',
        success: true,
        displayed_on_canvas: false,
      });
      setMessage(zh ? '已清除胃腔覆盖' : 'Lumen override cleared');
    } catch (error) {
      maskAuditRef.current('error', {
        operation: 'lumen_clear',
        error: error instanceof Error ? error.message.slice(0, 240) : 'Clear lumen failed',
      });
      setMessage(error instanceof Error ? error.message : 'Clear lumen failed');
    } finally {
      setLumenSaving(false);
    }
  }, [onLumenOverrideChange, patient, zh]);

  const hitLumenHandle = useCallback((imgPt: number[], box: LumenBBox, thr: number): LumenBoxHandle | null => {
    // Larger grab area so continuous box adjustment stays easy on clinical displays.
    const cornerThr = Math.max(thr * 3.6, 22);
    const corners: Array<[LumenBoxHandle, number, number]> = [
      ['nw', box.x1, box.y1],
      ['ne', box.x2, box.y1],
      ['sw', box.x1, box.y2],
      ['se', box.x2, box.y2],
    ];
    let best: LumenBoxHandle | null = null;
    let bestD = cornerThr * cornerThr;
    for (const [handle, x, y] of corners) {
      const d = dist2([x, y], imgPt);
      if (d <= bestD) {
        bestD = d;
        best = handle;
      }
    }
    if (best) return best;
    const pad = Math.max(thr * 0.5, 4);
    if (
      imgPt[0] >= box.x1 - pad
      && imgPt[0] <= box.x2 + pad
      && imgPt[1] >= box.y1 - pad
      && imgPt[1] <= box.y2 + pad
    ) {
      return 'move';
    }
    return null;
  }, []);

  const runSamClick = useCallback(async (
    imgPt: number[],
    label: 'positive' | 'negative' = 'positive',
    box?: { x1: number; y1: number; x2: number; y2: number } | null,
  ) => {
    freezeCurrentFrame();
    let next = samClicksRef.current;
    const alreadyPrompted = next.some((point) => (
      Math.abs(point.x - imgPt[0]) < 1
      && Math.abs(point.y - imgPt[1]) < 1
      && point.label === label
    ));
    if (!alreadyPrompted) {
      next = [...samClicksRef.current, { x: imgPt[0], y: imgPt[1], label }];
      samClicksRef.current = next;
      setSamClicks(next);
    }
    if (simpleVideoMode && mediaMode === 'video') {
      const publicModel = publicLesionSegModel(segmentationModel);
      if (publicModel === 'dinov3') {
        return runLesionModelRef.current(imgPt, box || null, next, 'dinov3');
      }
      return runSamAtPoint(imgPt, {
        silent: true,
        keepEditing: true,
        stayInSam: true,
        source: 'sam',
        clicks: next.length ? next : undefined,
        box: box || undefined,
        model: 'sam31',
      });
    }
    return runSamAtPoint(imgPt, {
      keepEditing: true,
      stayInSam: true,
      source: 'sam',
      clicks: next.length ? next : undefined,
      box: box || undefined,
    });
  }, [freezeCurrentFrame, mediaMode, runSamAtPoint, segmentationModel, simpleVideoMode]);

  const activateActiveSamPrompt = useCallback((
    promptMode: ActiveSamPromptMode,
    target: 'lesion' | 'lumen' = 'lesion',
  ) => {
    const hasMask = target === 'lesion'
      ? getCurrentTrackedPolygon().length >= 3
      : lumenPolygonRef.current.length >= 3 || Boolean(lumenBoxRef.current);
    if (!hasMask) {
      setMessage(
        target === 'lesion'
          ? (zh ? '请先生成病灶轮廓，再启动 nnInteractive 交互' : 'Create a lesion mask before starting nnInteractive')
          : (zh ? '请先生成胃腔轮廓，再启动 nnInteractive 交互' : 'Create a lumen mask before starting nnInteractive'),
      );
      return;
    }
    if (promptMode !== 'point' && nnInteractiveAvailable !== true) {
      setSimplePromptMode('point');
      setNnInteractiveMode(false);
      setSam31RefineTarget(target);
      setMessage(
        zh
          ? '涂鸦和套索需要 nnInteractive；已改用 SAM 3.1 正/负点'
          : 'Scribble and lasso need nnInteractive; switched to SAM 3.1 points',
      );
      void refreshNnInteractiveStatus();
      return;
    }
    setMode('sam');
    setSimplePromptMode(promptMode);
    armLesionBox(false);
    setSimpleEditMode(false);
    setLumenEditMode(false);
    setNnInteractiveTarget(target);
    setTrackOnPlay(false);
    if (nnInteractiveAvailable !== true) {
      setNnInteractiveMode(false);
      setSam31RefineTarget(target);
      setMessage(
        target === 'lesion'
          ? (zh
            ? 'nnInteractive 未连接，已改用 SAM 3.1 正/负点；正点保留，负点排除'
            : 'nnInteractive is unavailable; using SAM 3.1 points. Positive keeps, negative excludes')
          : (zh
            ? 'nnInteractive 未连接，已改用 SAM 3.1 精修胃腔'
            : 'nnInteractive is unavailable; using SAM 3.1 to refine the lumen'),
      );
      void refreshNnInteractiveStatus();
      return;
    }
    setSam31RefineTarget(null);
    setNnInteractiveMode(true);
    setMessage(
      target === 'lesion'
        ? (zh
          ? `nnInteractive 病灶${promptModeText(promptMode, true)}已开启，${promptMode === 'point' ? '点击添加提示' : '拖动提交提示'}`
          : `nnInteractive lesion ${promptModeText(promptMode, false)} is ready; ${promptMode === 'point' ? 'click to add prompts' : 'drag to submit a prompt'}`)
        : (zh
          ? `nnInteractive 胃腔${promptModeText(promptMode, true)}已开启，${promptMode === 'point' ? '点击添加提示' : '拖动提交提示'}`
          : `nnInteractive lumen ${promptModeText(promptMode, false)} is ready; ${promptMode === 'point' ? 'click to add prompts' : 'drag to submit a prompt'}`),
    );
  }, [getCurrentTrackedPolygon, nnInteractiveAvailable, refreshNnInteractiveStatus, zh]);

  const applyActiveSamStroke = useCallback(async (stroke: ActiveSamStroke) => {
    const prepared = prepareSubmitPromptStroke(
      stroke.points,
      stroke.kind === 'lasso' ? 'lasso' : 'scribble',
      {
        maxPoints: stroke.kind === 'lasso' ? 64 : 48,
        minPoints: 2,
        minLengthPx: 4,
        minAreaPx2: 64,
      },
    );
    if (!prepared.ok) {
      setMessage(
        prepared.reason === 'lasso_area_too_small'
          ? (zh ? '套索面积过小，请扩大闭合区域后重试' : 'Lasso area is too small; enlarge the closed region and retry')
          : prepared.reason === 'too_short'
            ? (zh ? '笔画过短，请继续拖动画出有效提示' : 'Stroke is too short; keep dragging to form a usable prompt')
            : (zh ? '涂鸦或套索至少需要两个点' : 'A scribble or lasso needs at least two points'),
      );
      return;
    }
    const submitStroke: ActiveSamStroke = {
      ...stroke,
      points: prepared.points,
    };
    const target = stroke.target || (nnInteractiveMode ? nnInteractiveTarget : 'lesion');
    if (!nnInteractiveMode || nnInteractiveAvailable !== true) {
      setMessage(
        zh
          ? '涂鸦和套索需要边界辅助服务，未转换为 SAM 默认点击'
          : 'Scribble and lasso require boundary assistance and will not fall back to SAM clicks',
      );
      return;
    }

    setPromptStrokes((previous) => [...previous, submitStroke]);
    promptStrokesRef.current = [...promptStrokesRef.current, submitStroke];
    await refineWithNnInteractive(target, undefined, [submitStroke]);
  }, [
    nnInteractiveAvailable,
    nnInteractiveMode,
    nnInteractiveTarget,
    refineWithNnInteractive,
    zh,
  ]);

  const beginActiveSamStroke = useCallback((
    imgPt: number[],
    event: React.PointerEvent<HTMLCanvasElement>,
  ): boolean => {
    if (simpleVideoMode && !nnInteractiveMode) return false;
    if (simplePromptMode !== 'scribble' && simplePromptMode !== 'lasso') return false;
    if (nnInteractiveAvailable !== true) {
      event.preventDefault();
      event.stopPropagation();
      setMessage(
        zh
          ? '涂鸦和套索暂不可用，请先启动边界辅助服务'
          : 'Scribble and lasso are unavailable until boundary assistance is running',
      );
      return true;
    }
    if (samBusy || nnInteractiveBusy || segmentationBusy) return true;
    const label = explicitPromptLabel(activeSamPromptLabel, event.shiftKey);
    const stroke: ActiveSamStroke = {
      points: [imgPt],
      label,
      kind: simplePromptMode,
      width: simplePromptMode === 'lasso' ? 3 : 10,
      target: nnInteractiveMode ? nnInteractiveTarget : 'lesion',
    };
    activePromptStrokeRef.current = stroke;
    setActivePromptStroke(stroke);
    event.preventDefault();
    event.stopPropagation();
    capturePointerSafely(event.currentTarget, event.pointerId);
    freezeCurrentFrame();
    return true;
  }, [
    activeSamPromptLabel,
    freezeCurrentFrame,
    nnInteractiveBusy,
    nnInteractiveMode,
    nnInteractiveAvailable,
    nnInteractiveTarget,
    samBusy,
    segmentationBusy,
    simplePromptMode,
    simpleVideoMode,
    zh,
  ]);

  const onPointerDown = (e: React.PointerEvent<HTMLCanvasElement>) => {
    const wantPan = (e.shiftKey || e.button === 1)
      && viewZoomRef.current > 1.02
      && !wallPaintModeRef.current
      && !wallPickModeRef.current
      && !lumenSculptMode;
    if (wantPan) {
      e.preventDefault();
      capturePointerSafely(e.currentTarget, e.pointerId);
      const fallback = canvasToImage(e, { clamp: true });
      const center = viewCenterRef.current || (fallback ? { x: fallback[0], y: fallback[1] } : { x: 0, y: 0 });
      viewPanDragRef.current = { x: e.clientX, y: e.clientY, cx: center.x, cy: center.y };
      return;
    }
    const wantLesionBox = lesionBoxArmedRef.current || lesionBoxArmed;
    const imgPt = canvasToImage(e, {
      clamp: wantLesionBox || lumenEditMode || wallPickModeRef.current || analysisFocusModeRef.current,
    });
    if (!imgPt) {
      if (wantLesionBox) {
        setMessage(zh ? '请在图像上拖出矩形框选病灶' : 'Drag a rectangle on the image');
      }
      return;
    }

    if (analysisFocusModeRef.current) {
      e.preventDefault();
      freezeCurrentFrame();
      const next = addAnalysisFocusPoint(analysisFocusPointsRef.current, imgPt);
      analysisFocusPointsRef.current = next;
      setAnalysisFocusPoints(next);
      persistOpenKeyframeContoursRef.current({ refined: true });
      recordDoctorOpRef.current('analysis_focus', {
        video_time_sec: videoRef.current?.currentTime ?? null,
        image_x: imgPt[0],
        image_y: imgPt[1],
        layer: 'wall',
        operation: 'analysis_focus',
        point_count: next.length,
      });
      setMessage(zh
        ? (next.length
          ? `已标 ${next.length} 个分析焦点。再点可改或再加，最多 3 个。这不是突破点。`
          : '已去掉分析焦点。')
        : (next.length
          ? `${next.length} analysis focus point(s). Tap again to add or remove, max 3. Not a breach mark.`
          : 'Cleared analysis focus.'));
      redrawRef.current?.();
      return;
    }

    if (wallPickModeRef.current) {
      e.preventDefault();
      freezeCurrentFrame();
      const next = [...wallPickFlanksRef.current, imgPt].slice(0, 2);
      wallPickFlanksRef.current = next;
      setWallPickFlanks(next);
      recordDoctorOpRef.current('wall_edit', {
        video_time_sec: videoRef.current?.currentTime ?? null,
        image_x: imgPt[0],
        image_y: imgPt[1],
        layer: 'wall',
        operation: 'wall_flank_pick',
        point_count: next.length,
        frozen: true,
      });
      if (next.length >= 2) {
        wallPickModeRef.current = false;
        setWallPickMode(false);
        applyWallExtension({ doctorFlanks: next });
      } else {
        setMessage(zh ? '已点一侧可见壁。请再点对侧。' : 'First visible flank marked. Click the opposite side.');
      }
      redrawRef.current?.();
      return;
    }

    if (wallPaintModeRef.current) {
      e.preventDefault();
      freezeCurrentFrame();
      capturePointerSafely(e.currentTarget, e.pointerId);
      wallPaintStrokeRef.current = [imgPt];
      setWallPaintStroke([imgPt]);
      redrawRef.current?.();
      return;
    }

    // Armed box-lesion wins over handles, whole-mask drag, nnInteractive, and in-flight SAM.
    if (wantLesionBox && !lumenEditMode && !lumenSculptMode) {
      e.preventDefault();
      lastPolyClickRef.current = null;
      contourInteractionRef.current = true;
      generatedLesionRef.current = [];
      videoFrameOverridesRef.current = [];
      setVideoFrameOverrides([]);
      setTrackingPrepared(false);
      setSimpleEditMode(false);
      clearSamPrompts();
      setSimplePromptBox(null);
      freezeCurrentFrame();
      capturePointerSafely(e.currentTarget, e.pointerId);
      samBoxDragRef.current = { x0: imgPt[0], y0: imgPt[1], x1: imgPt[0], y1: imgPt[1] };
      setSamBoxPreview({ x1: imgPt[0], y1: imgPt[1], x2: imgPt[0], y2: imgPt[1] });
      return;
    }

    if (lumenSculptMode) {
      e.preventDefault();
      capturePointerSafely(e.currentTarget, e.pointerId);
      freezeCurrentFrame();
      pushEditUndo();
      const layer = sculptLayerRef.current;
      const base = layer === 'lumen'
        ? (lumenPolygonRef.current.length >= 3
          ? clonePoly(lumenPolygonRef.current)
          : clonePoly(ensureLumenPolygonForRefine()))
        : clonePoly(pointsRef.current);
      lumenPaintBaseRef.current = base;
      lumenPaintStrokeRef.current = [imgPt];
      paintCursorRef.current = imgPt;
      redraw();
      return;
    }

    if (lumenEditMode) {
      if (samBusy || segmentationBusy || lumenBusy || lumenSamBusy) return;
      const activeBox = lumenBoxRef.current || lumenBox;
      const startFresh = lumenBoxFreshDrawRef.current || !activeBox;
      if (!startFresh && activeBox) {
        const handle = hitLumenHandle(imgPt, activeBox, hitThreshold());
        if (handle) {
          e.preventDefault();
          capturePointerSafely(e.currentTarget, e.pointerId);
          freezeCurrentFrame();
          lumenBoxDragRef.current = {
            handle,
            start: normalizeLumenBBox(activeBox),
            origin: imgPt,
          };
          return;
        }
      }
      // Fresh draw, or click outside the current box: start a new lumen box.
      lumenBoxFreshDrawRef.current = false;
      e.preventDefault();
      capturePointerSafely(e.currentTarget, e.pointerId);
      freezeCurrentFrame();
      lumenBoxDragRef.current = {
        handle: 'se',
        start: { x1: imgPt[0], y1: imgPt[1], x2: imgPt[0], y2: imgPt[1] },
        origin: imgPt,
      };
      const draft = { x1: imgPt[0], y1: imgPt[1], x2: imgPt[0], y2: imgPt[1] };
      lumenBoxRef.current = draft;
      setLumenBox(draft);
      setLumenPolygon([]);
      lumenPolygonRef.current = [];
      setLumenResultMeta((prev) => ({ ...prev, source: 'manual', error: undefined }));
      return;
    }

    // Traditional polygon tool: click vertices; close by near-start or double-click.
    if (mode === 'polygon' && !lumenEditMode) {
      e.preventDefault();
      const thr = hitThreshold();
      const draft = polygonDraft;
      if (draft.length >= 3) {
        const d0 = dist2(draft[0], imgPt);
        if (d0 <= thr * thr * 4 || (lastPolyClickRef.current && Date.now() - lastPolyClickRef.current.t < 350)) {
          const closed = prepareEditableContour(
            draft,
            refineTarget === 'lumen' ? LUMEN_CONTOUR_MAX_POINTS : LESION_CONTOUR_MAX_POINTS,
          );
          pushEditUndo();
          if (refineTarget === 'lumen') {
            lumenPolygonRef.current = closed;
            setLumenPolygon(closed);
            const box = bboxFromPolygon(closed);
            if (box) {
              lumenBoxRef.current = box;
              setLumenBox(box);
            }
          } else {
            pointsRef.current = closed;
            generatedLesionRef.current = closed;
            setPoints(closed);
            setSimpleEditLayer('lesion');
          }
          setPolygonDraft([]);
          setMode('hard');
          setSimpleEditMode(true);
          markActiveDoctorKeyframeRefined();
          recordDoctorOp('polygon_edit', {
            layer: refineTarget,
            operation: 'polygon_edit',
            tool: 'polygon',
            point_count: closed.length,
          });
          setMessage(zh ? '多边形已闭合，可继续拖点精修' : 'Polygon closed; drag points to refine');
          redrawRef.current();
          return;
        }
      }
      lastPolyClickRef.current = { t: Date.now(), pt: imgPt };
      setPolygonDraft((prev) => [...prev, imgPt]);
      return;
    }

    // Soft-drag any point on the active refine contour (lesion or lumen).
    if ((mode === 'brush' || mode === 'hard') && !lumenEditMode && !lumenSculptMode) {
      const source = refineTarget === 'lumen'
        ? (lumenPolygonRef.current.length >= 3 ? lumenPolygonRef.current : ensureLumenPolygonForRefine())
        : getCurrentTrackedPolygon();
      if (source.length >= 3) {
        const handleCount = adaptiveHandleCount(
          source,
          Math.min(VISIBLE_HANDLE_COUNT, refineTarget === 'lumen' ? LUMEN_CTRL_COUNT : LESION_CTRL_COUNT),
        );
        const picked = pickVisibleHandle(source, imgPt, hitThreshold(), handleCount, hitThreshold() * 1.4);
        if (picked) {
          e.preventDefault();
          capturePointerSafely(e.currentTarget, e.pointerId);
          freezeCurrentFrame();
          pushEditUndo();
          if (refineTarget === 'lumen') {
            lumenPolygonRef.current = picked.points;
          } else {
            pointsRef.current = picked.points;
            setActiveLayer('lesion');
          }
          dragSoftRef.current = true;
          dragIndexRef.current = picked.index;
          dragLayerRef.current = refineTarget;
          setDragIndex(picked.index);
          setDragLayer(refineTarget);
          setSimpleEditMode(true);
          return;
        }
      }
    }

    if (
      !lumenEditMode
      && !simpleEditMode
      && (simplePromptMode === 'scribble' || simplePromptMode === 'lasso')
      && beginActiveSamStroke(imgPt, e)
    ) {
      return;
    }

    if (!lumenEditMode && !simpleEditMode && nnInteractiveMode && !simpleVideoMode) {
      if (nnInteractiveBusy) return;
      e.preventDefault();
      void refineWithNnInteractive(nnInteractiveTarget, {
        x: imgPt[0],
        y: imgPt[1],
        label: explicitPromptLabel(activeSamPromptLabel, e.shiftKey),
      });
      return;
    }

    if (!lumenEditMode && !simpleEditMode && mode === 'sam' && !simpleVideoMode && simplePromptMode === 'point') {
      if (samBusy || segmentationBusy) return;
      e.preventDefault();
      void runSamClick(
        imgPt,
        explicitPromptLabel(activeSamPromptLabel, e.shiftKey),
        simplePromptBox,
      );
      return;
    }

    if (simpleVideoMode && mediaMode === 'video') {
      if (samBusy || segmentationBusy || lumenSamBusy || nnInteractiveBusy) {
        setMessage(zh ? '正在分割中，请稍候再画' : 'Segmentation in progress; wait before drawing');
        return;
      }
      e.preventDefault();
      const canEditExisting = !lesionBoxArmed && !lumenEditMode;
      if (simpleEditMode || (canEditExisting && getCurrentTrackedPolygon().length >= 3)) {
        const bands = wallLayerBandsRef.current;
        if (bands.length && !lumenEditMode && refineTarget !== 'lumen') {
          const bandThr = hitThreshold() * (viewZoom >= 1.35 ? 2.4 : 1.4);
          let found: { bandIndex: number; pick: { index: number; points: number[][] } } | null = null;
          let bestD = Infinity;
          for (let bandIndex = 0; bandIndex < bands.length; bandIndex += 1) {
            const band = bands[bandIndex];
            if (band.length < 2) continue;
            const hit = (e.altKey || e.ctrlKey)
              ? pickOrInsertOnContour(band, imgPt, bandThr)
              : pickSoftAnchor(band, imgPt, bandThr);
            if (!hit) continue;
            const d = dist2(band[hit.index] || hit.points[hit.index], imgPt);
            if (d < bestD) {
              bestD = d;
              found = { bandIndex, pick: hit };
            }
          }
          if (found) {
            const hitBand = found;
            capturePointerSafely(e.currentTarget, e.pointerId);
            freezeCurrentFrame();
            pushEditUndo();
            const nextBands = bands.map((band, index) => (
              index === hitBand.bandIndex ? clonePoly(hitBand.pick.points) : band
            ));
            wallLayerBandsRef.current = nextBands;
            setWallLayerBands(nextBands);
            dragSoftRef.current = true;
            dragIndexRef.current = hitBand.pick.index;
            dragLayerRef.current = 'band';
            dragBandIndexRef.current = hitBand.bandIndex;
            setDragIndex(hitBand.pick.index);
            setDragLayer('band');
            setSimpleEditMode(true);
            return;
          }
        }
        const source = refineTarget === 'lumen'
          ? (lumenPolygonRef.current.length >= 3 ? lumenPolygonRef.current : ensureLumenPolygonForRefine())
          : (simpleEditLayer === 'wall' && wallPointsRef.current.length >= 3
            ? wallPointsRef.current
            : getCurrentTrackedPolygon());
        const layer: DragLayer = refineTarget === 'lumen'
          ? 'lumen'
          : (simpleEditLayer === 'wall' && wallPointsRef.current.length >= 3 ? 'wall' : 'lesion');
        const handleCount = adaptiveHandleCount(
          source,
          Math.min(
            VISIBLE_HANDLE_COUNT,
            layer === 'lumen' ? LUMEN_CTRL_COUNT : layer === 'wall' ? WALL_CTRL_COUNT : LESION_CTRL_COUNT,
          ),
        );
        const picked = source.length >= 3
          ? ((e.altKey || e.ctrlKey)
            ? pickOrInsertOnContour(source, imgPt, hitThreshold())
            : pickVisibleHandle(source, imgPt, hitThreshold(), handleCount, hitThreshold() * 1.4))
          : null;
        if (picked) {
          capturePointerSafely(e.currentTarget, e.pointerId);
          freezeCurrentFrame();
          pushEditUndo();
          if (layer === 'lumen') {
            lumenPolygonRef.current = picked.points;
          } else if (layer === 'wall') {
            wallPointsRef.current = picked.points;
          } else {
            pointsRef.current = picked.points;
          }
          dragSoftRef.current = true;
          dragIndexRef.current = picked.index;
          dragLayerRef.current = layer;
          setDragIndex(picked.index);
          setDragLayer(layer);
          setSimpleEditMode(true);
          return;
        }
        if (source.length >= 3 && hitWholeShape(imgPt, source, hitThreshold())) {
          capturePointerSafely(e.currentTarget, e.pointerId);
          freezeCurrentFrame();
          pushEditUndo();
          polyMoveRef.current = { layer, start: clonePoly(source), origin: imgPt };
          setSimpleEditMode(true);
          return;
        }
        if (!lesionBoxArmed) {
          setMessage(
            zh
              ? '拖病灶本体可整体移动；要重新画框，请先点亮「框选病灶」'
              : 'Drag the lesion body to move it. Arm Box lesion only when you want a new box',
          );
          return;
        }
      }

      if (nnInteractiveMode) {
        if (simplePromptMode === 'scribble' || simplePromptMode === 'lasso') {
          return;
        }
        void refineWithNnInteractive(nnInteractiveTarget, {
          x: imgPt[0],
          y: imgPt[1],
          label: explicitPromptLabel(activeSamPromptLabel, e.shiftKey),
        });
        return;
      }

      if (sam31RefineTarget) {
        const label = explicitPromptLabel(activeSamPromptLabel, e.shiftKey);
        if (sam31RefineTarget === 'lumen') {
          void segmentLumenWithSam31([{ x: imgPt[0], y: imgPt[1], label }]);
          return;
        }
        const lesionPoly = getCurrentTrackedPolygon();
        const box = bboxFromPolygon(lesionPoly) || simplePromptBox;
        void runSamClick(imgPt, label, box);
        return;
      }

      // Only start a new lesion box when the button is armed.
      if (!lesionBoxArmed) {
        setMessage(
          zh
            ? (getCurrentTrackedPolygon().length >= 3
              ? '已有病灶遮罩。拖本体可移动；要重画请先点亮「框选病灶」'
              : '请先点亮右侧「框选病灶」，再拖出矩形')
            : (getCurrentTrackedPolygon().length >= 3
              ? 'A lesion mask exists. Drag the body to move it, or arm Box lesion to redraw'
              : 'Arm Box lesion on the right, then drag a rectangle'),
        );
        return;
      }
      {
        lastPolyClickRef.current = null;
        contourInteractionRef.current = true;
        generatedLesionRef.current = [];
        videoFrameOverridesRef.current = [];
        setVideoFrameOverrides([]);
        setTrackingPrepared(false);
        setSimpleEditMode(false);
        clearSamPrompts();
        setSimplePromptBox(null);
        capturePointerSafely(e.currentTarget, e.pointerId);
        samBoxDragRef.current = { x0: imgPt[0], y0: imgPt[1], x1: imgPt[0], y1: imgPt[1] };
        setSamBoxPreview({ x1: imgPt[0], y1: imgPt[1], x2: imgPt[0], y2: imgPt[1] });
        return;
      }
    }

    // Alt/Option+click：设置浸润通道取样点（会议纪要：接触弧内点选）
    const editableLesionPoints = mediaMode === 'video' ? getCurrentTrackedPolygon() : points;
    if (mediaMode === 'video' && editableLesionPoints !== pointsRef.current) {
      pointsRef.current = clonePoly(editableLesionPoints);
      setPoints(pointsRef.current);
    }

    if (e.altKey && editableLesionPoints.length >= 3) {
      setLayerPick({ x: imgPt[0], y: imgPt[1] });
      captureFrameDataUrl();
      recordDoctorOpRef.current('layer_pick', {
        video_time_sec: videoRef.current?.currentTime ?? null,
        image_x: imgPt[0],
        image_y: imgPt[1],
        layer: 'sample',
        frozen: true,
      });
      setMessage(zh ? `已设取样点 (${Math.round(imgPt[0])},${Math.round(imgPt[1])})` : `Pick set (${Math.round(imgPt[0])},${Math.round(imgPt[1])})`);
      return;
    }

    const thr = hitThreshold() * 1.6;
    const lesionCtrls = editableLesionPoints.length >= 3 ? controlIndices(editableLesionPoints.length, LESION_CTRL_COUNT) : [];
    const wallCtrls = wallPoints.length >= 3 ? controlIndices(wallPoints.length, WALL_CTRL_COUNT) : [];

    const nearestCtrl = (
      poly: number[][],
      idxs: number[],
      thresholdPx: number,
    ): number => {
      let best = -1;
      let bestD = thresholdPx * thresholdPx;
      for (const i of idxs) {
        const p = poly[i];
        if (!p) continue;
        const d = dist2(p, imgPt);
        if (d <= bestD) {
          bestD = d;
          best = i;
        }
      }
      return best;
    };

    // Prefer control handles on BOTH contours (direction_demo dual handles)
    const nearLes = nearestCtrl(editableLesionPoints, lesionCtrls, thr);
    const nearWall = nearestCtrl(wallPoints, wallCtrls, thr);
    let pickLayer: DragLayer | null = null;
    let pickIdx = -1;
    if (nearLes >= 0 && nearWall >= 0) {
      const dL = dist2(editableLesionPoints[nearLes], imgPt);
      const dW = dist2(wallPoints[nearWall], imgPt);
      if (dW <= dL) {
        pickLayer = 'wall';
        pickIdx = nearWall;
      } else {
        pickLayer = 'lesion';
        pickIdx = nearLes;
      }
    } else if (nearWall >= 0) {
      pickLayer = 'wall';
      pickIdx = nearWall;
    } else if (nearLes >= 0) {
      pickLayer = 'lesion';
      pickIdx = nearLes;
    }

    if (pickLayer && pickIdx >= 0 && (mode === 'soft' || mode === 'hard' || mode === 'brush' || mode === 'sam' || mode === 'add')) {
      e.preventDefault();
      capturePointerSafely(e.currentTarget, e.pointerId);
      freezeCurrentFrame();
      pushEditUndo();
      if (pickLayer === 'wall') {
        wallExtensionMaskRef.current = [];
        setWallExtensionNote('');
      }
      setActiveLayer(pickLayer);
      const useSoft = mode !== 'hard';
      if (mode === 'sam' || mode === 'add') setMode('soft');
      dragSoftRef.current = useSoft;
      dragIndexRef.current = pickIdx;
      dragLayerRef.current = pickLayer;
      setDragIndex(pickIdx);
      setDragLayer(pickLayer);
      return;
    }

    const layerPts = activeLayer === 'lesion' ? editableLesionPoints : activePoints;

    // Hard / add: edge insert on active layer
    if ((mode === 'hard' || mode === 'add') && layerPts.length >= 3) {
      const edge = nearestEdgeInsert(layerPts, imgPt, thr);
      if (edge >= 0) {
        e.preventDefault();
        capturePointerSafely(e.currentTarget, e.pointerId);
        freezeCurrentFrame();
        pushEditUndo();
        const next = [...layerPts];
        next.splice(edge + 1, 0, imgPt);
        if (activeLayer === 'wall') {
          wallPointsRef.current = next;
          setWallPoints(next);
          recordDoctorOpRef.current('wall_edit', {
            video_time_sec: videoRef.current?.currentTime ?? null,
            image_x: imgPt[0],
            image_y: imgPt[1],
            layer: 'wall',
            point_count: next.length,
            frozen: true,
          });
        } else {
          pointsRef.current = next;
          setPoints(next);
          recordDoctorOpRef.current('lesion_edit', {
            video_time_sec: videoRef.current?.currentTime ?? null,
            image_x: imgPt[0],
            image_y: imgPt[1],
            layer: 'lesion',
            point_count: next.length,
            frozen: true,
          });
        }
        const newIdx = edge + 1;
        setMode('hard');
        dragSoftRef.current = false;
        dragIndexRef.current = newIdx;
        dragLayerRef.current = activeLayer;
        setDragIndex(newIdx);
        setDragLayer(activeLayer);
        return;
      }
    }

    if (mode === 'sam' && simplePromptMode === 'point') {
      void runSamClick(imgPt, explicitPromptLabel(activeSamPromptLabel, e.shiftKey));
      return;
    }
    if (mode === 'sam') {
      if (simpleVideoMode && !requireOpenKeyframeForBox()) return;
      e.preventDefault();
      capturePointerSafely(e.currentTarget, e.pointerId);
      freezeCurrentFrame();
      // Start potential box drag; commit on pointerup (click or box).
      samBoxDragRef.current = { x0: imgPt[0], y0: imgPt[1], x1: imgPt[0], y1: imgPt[1] };
      setSamBoxPreview({ x1: imgPt[0], y1: imgPt[1], x2: imgPt[0], y2: imgPt[1] });
      (e.currentTarget as HTMLCanvasElement).dataset.samNeg = e.shiftKey ? '1' : '0';
      return;
    }
    if (mode === 'add') {
      freezeCurrentFrame();
      pushEditUndo();
      const next = [...layerPts, imgPt];
      if (activeLayer === 'wall') {
        wallPointsRef.current = next;
        setWallPoints(next);
        recordDoctorOpRef.current('wall_edit', {
          video_time_sec: videoRef.current?.currentTime ?? null,
          image_x: imgPt[0],
          image_y: imgPt[1],
          layer: 'wall',
          point_count: next.length,
          frozen: true,
        });
      } else {
        pointsRef.current = next;
        setPoints(next);
        recordDoctorOpRef.current('lesion_edit', {
          video_time_sec: videoRef.current?.currentTime ?? null,
          image_x: imgPt[0],
          image_y: imgPt[1],
          layer: 'lesion',
          point_count: next.length,
          frozen: true,
        });
      }
      void persistOverrideRef.current('doctor_edit', { silent: true });
      return;
    }
    if (mode === 'delete') {
      freezeCurrentFrame();
      // Delete nearest control handle on active layer (or any vertex in hard mode)
      const idxs = activeLayer === 'wall' ? wallCtrls : lesionCtrls;
      const idx = nearestCtrl(layerPts, idxs.length ? idxs : layerPts.map((_, i) => i), thr);
      if (idx >= 0 && layerPts.length > 3) {
        pushEditUndo();
        const next = layerPts.filter((_, i) => i !== idx);
        if (activeLayer === 'wall') {
          wallPointsRef.current = next;
          setWallPoints(next);
        } else {
          pointsRef.current = next;
          setPoints(next);
        }
        void persistOverrideRef.current('doctor_edit', { silent: true });
      }
      return;
    }

    // soft mode fallback: grab nearest dense vertex with soft deform
    if (mode === 'soft' && layerPts.length >= 3) {
      const fallback = nearestVertex(layerPts, imgPt, thr * 3);
      if (fallback >= 0) {
        e.preventDefault();
        capturePointerSafely(e.currentTarget, e.pointerId);
        freezeCurrentFrame();
        pushEditUndo();
        dragSoftRef.current = true;
        dragIndexRef.current = fallback;
        dragLayerRef.current = activeLayer;
        setDragIndex(fallback);
        setDragLayer(activeLayer);
      }
    }
  };

  const onPointerMove = (e: React.PointerEvent<HTMLCanvasElement>) => {
    if (viewPanDragRef.current) {
      const canvas = canvasRef.current;
      if (!canvas) return;
      const video = videoRef.current;
      const img = imgRef.current;
      const useVideo = mediaMode === 'video' && video && video.videoWidth > 0;
      const iw = useVideo ? video!.videoWidth : (img?.naturalWidth || 1);
      const ih = useVideo ? video!.videoHeight : (img?.naturalHeight || 1);
      const { scale } = computeDisplayTransform(
        iw,
        ih,
        canvas.width,
        canvas.height,
        viewFocusBox,
        viewZoomRef.current,
        viewCenterRef.current,
      );
      const rect = canvas.getBoundingClientRect();
      const css = rect.width / Math.max(1, canvas.width);
      const drag = viewPanDragRef.current;
      const next = {
        x: drag.cx - (e.clientX - drag.x) / Math.max(1e-6, scale * css),
        y: drag.cy - (e.clientY - drag.y) / Math.max(1e-6, scale * css),
      };
      viewCenterRef.current = next;
      setViewCenter(next);
      return;
    }
    if (magnifierOn && dragIndexRef.current == null && !samBoxDragRef.current && !lumenBoxDragRef.current && !activePromptStrokeRef.current) {
      const canvas = canvasRef.current;
      const imgPt = canvasToImage(e);
      if (canvas && imgPt) {
        const rect = canvas.getBoundingClientRect();
        const scaleX = canvas.width / Math.max(1, rect.width);
        const scaleY = canvas.height / Math.max(1, rect.height);
        magnifierPosRef.current = {
          cx: (e.clientX - rect.left) * scaleX,
          cy: (e.clientY - rect.top) * scaleY,
          ix: imgPt[0],
          iy: imgPt[1],
        };
        redraw();
      }
    }
    if (lumenSculptMode && !lumenPaintStrokeRef.current) {
      const hoverPt = canvasToImage(e, { clamp: true });
      if (hoverPt) {
        paintCursorRef.current = hoverPt;
        if (paintRafRef.current == null) {
          paintRafRef.current = window.requestAnimationFrame(() => {
            paintRafRef.current = null;
            redrawRef.current();
          });
        }
      }
    }
    const wallStroke = wallPaintStrokeRef.current;
    if (wallStroke) {
      const imgPt = canvasToImage(e, { clamp: true });
      if (!imgPt) return;
      e.preventDefault();
      const last = wallStroke[wallStroke.length - 1];
      if (!last || Math.hypot(imgPt[0] - last[0], imgPt[1] - last[1]) >= 2.2) {
        wallStroke.push(imgPt);
        setWallPaintStroke([...wallStroke]);
      }
      redrawRef.current?.();
      return;
    }
    const paintStroke = lumenPaintStrokeRef.current;
    if (paintStroke && lumenSculptMode) {
      const imgPt = canvasToImage(e, { clamp: true });
      if (!imgPt) return;
      e.preventDefault();
      pendingDragPtRef.current = imgPt;
      if (paintRafRef.current != null) return;
      paintRafRef.current = window.requestAnimationFrame(() => {
        paintRafRef.current = null;
        const stroke = lumenPaintStrokeRef.current;
        const pending = pendingDragPtRef.current;
        if (!stroke || !pending) return;
        const last = stroke[stroke.length - 1];
        if (last && Math.hypot(pending[0] - last[0], pending[1] - last[1]) < 2.2) {
          paintCursorRef.current = pending;
          redrawRef.current();
          return;
        }
        stroke.push(pending);
        paintCursorRef.current = pending;
        redrawRef.current();
      });
      return;
    }
    const activeStroke = activePromptStrokeRef.current;
    if (activeStroke) {
      const imgPt = canvasToImage(e);
      if (!imgPt) return;
      e.preventDefault();
      pendingPromptPointRef.current = imgPt;
      if (promptStrokeRafRef.current != null) return;
      promptStrokeRafRef.current = window.requestAnimationFrame(() => {
        promptStrokeRafRef.current = null;
        const stroke = activePromptStrokeRef.current;
        const pending = pendingPromptPointRef.current;
        if (!stroke || !pending) return;
        const nextPoints = appendPromptPoint(stroke.points, pending, 2);
        if (nextPoints.length === stroke.points.length) return;
        const nextStroke = { ...stroke, points: nextPoints };
        activePromptStrokeRef.current = nextStroke;
        setActivePromptStroke(nextStroke);
        redraw();
      });
      return;
    }
    const polyMove = polyMoveRef.current;
    if (polyMove) {
      const imgPt = canvasToImage(e);
      if (!imgPt) return;
      e.preventDefault();
      const next = translatePolygon(
        polyMove.start,
        imgPt[0] - polyMove.origin[0],
        imgPt[1] - polyMove.origin[1],
      );
      if (polyMove.layer === 'lumen') {
        lumenPolygonRef.current = next;
        setLumenPolygon(next);
      } else if (polyMove.layer === 'wall') {
        wallPointsRef.current = next;
        setWallPoints(next);
      } else {
        pointsRef.current = next;
        setPoints(next);
      }
      redrawRef.current();
      return;
    }
    const lumenDrag = lumenBoxDragRef.current;
    if (lumenDrag) {
      const imgPt = canvasToImage(e);
      if (!imgPt) return;
      e.preventDefault();
      const { handle, start, origin } = lumenDrag;
      const dx = imgPt[0] - origin[0];
      const dy = imgPt[1] - origin[1];
      let next: LumenBBox = { ...start };
      if (handle === 'move') {
        next = {
          x1: start.x1 + dx,
          y1: start.y1 + dy,
          x2: start.x2 + dx,
          y2: start.y2 + dy,
        };
      } else {
        next = { ...start };
        if (handle.includes('n')) next.y1 = start.y1 + dy;
        if (handle.includes('s')) next.y2 = start.y2 + dy;
        if (handle.includes('w')) next.x1 = start.x1 + dx;
        if (handle.includes('e')) next.x2 = start.x2 + dx;
      }
      const normalized = normalizeLumenBBox(next);
      lumenBoxRef.current = normalized;
      redraw();
      return;
    }
    const boxDrag = samBoxDragRef.current;
    if (boxDrag) {
      const imgPt = canvasToImage(e, { clamp: true });
      if (!imgPt) return;
      e.preventDefault();
      boxDrag.x1 = imgPt[0];
      boxDrag.y1 = imgPt[1];
      setSamBoxPreview({ x1: boxDrag.x0, y1: boxDrag.y0, x2: boxDrag.x1, y2: boxDrag.y1 });
      redraw();
      return;
    }
    const idx = dragIndexRef.current;
    const layer = dragLayerRef.current;
    if (idx === null || !layer) return;
    e.preventDefault();
    const imgPt = canvasToImage(e, { clamp: true });
    if (!imgPt) return;
    pendingDragPtRef.current = imgPt;
    if (dragRafRef.current != null) return;
    dragRafRef.current = window.requestAnimationFrame(() => {
      dragRafRef.current = null;
      const pt = pendingDragPtRef.current;
      const dragIdx = dragIndexRef.current;
      const dragLayer = dragLayerRef.current;
      if (!pt || dragIdx === null || !dragLayer) return;
      if (dragLayer === 'band') {
        const bandIndex = dragBandIndexRef.current;
        const bands = wallLayerBandsRef.current;
        if (bandIndex == null || !bands[bandIndex]?.[dragIdx]) return;
        const nextBand = clonePoly(bands[bandIndex]);
        if (dragSoftRef.current) {
          softDeform(nextBand, dragIdx, pt[0], pt[1], WALL_SOFT_SIGMA);
        }
        nextBand[dragIdx] = [pt[0], pt[1]];
        const nextBands = bands.map((band, index) => (index === bandIndex ? nextBand : band));
        wallLayerBandsRef.current = nextBands;
        draggingRef.current = true;
        redrawRef.current();
        return;
      }
      const src = dragLayer === 'wall'
        ? wallPointsRef.current
        : dragLayer === 'lumen'
          ? lumenPolygonRef.current
          : pointsRef.current;
      if (!src[dragIdx]) return;
      const next = clonePoly(src);
      if (dragSoftRef.current) {
        softDeform(
          next,
          dragIdx,
          pt[0],
          pt[1],
          dragLayer === 'wall' ? WALL_SOFT_SIGMA : dragLayer === 'lumen' ? LUMEN_SOFT_SIGMA : LESION_SOFT_SIGMA,
        );
      }
      next[dragIdx] = [pt[0], pt[1]];
      if (dragLayer === 'wall') wallPointsRef.current = next;
      else if (dragLayer === 'lumen') lumenPolygonRef.current = next;
      else pointsRef.current = next;
      draggingRef.current = true;
      redrawRef.current();
    });
  };

  const onPointerUp = (e: React.PointerEvent<HTMLCanvasElement>) => {
    if (viewPanDragRef.current) {
      viewPanDragRef.current = null;
      return;
    }
    if (polyMoveRef.current) {
      const move = polyMoveRef.current;
      polyMoveRef.current = null;
      if (move.layer === 'lumen') {
        setLumenPolygon(clonePoly(lumenPolygonRef.current));
        const box = bboxFromPolygon(lumenPolygonRef.current);
        if (box) {
          lumenBoxRef.current = box;
          setLumenBox(box);
        }
      } else if (move.layer === 'wall') {
        setWallPoints(clonePoly(wallPointsRef.current));
      } else {
        setPoints(clonePoly(pointsRef.current));
      }
      markActiveDoctorKeyframeRefined();
      void persistOverrideRef.current('doctor_edit', { silent: true });
      return;
    }
    if (wallPaintStrokeRef.current) {
      const stroke = wallPaintStrokeRef.current;
      wallPaintStrokeRef.current = null;
      try {
        if (e.currentTarget.hasPointerCapture(e.pointerId)) {
          e.currentTarget.releasePointerCapture(e.pointerId);
        }
      } catch {
        /* ignore */
      }
      commitWallPaintStroke(stroke);
      return;
    }
    if (lumenPaintStrokeRef.current) {
      if (paintRafRef.current != null) {
        window.cancelAnimationFrame(paintRafRef.current);
        paintRafRef.current = null;
      }
      const stroke = lumenPaintStrokeRef.current;
      const pending = pendingDragPtRef.current;
      if (pending) {
        const lastPt = stroke[stroke.length - 1];
        if (!lastPt || Math.hypot(pending[0] - lastPt[0], pending[1] - lastPt[1]) >= 1) {
          stroke.push(pending);
        }
      }
      const last = stroke[stroke.length - 1];
      const layer = sculptLayerRef.current;
      const op: PaintOp = lumenSculptMode?.endsWith('add') ? 'add' : 'subtract';
      commitLayerPaint(stroke, op, layer, lumenPaintBaseRef.current || undefined);
      recordDoctorOp(layer === 'lumen' ? 'lumen_paint' : 'lesion_edit', {
        layer,
        operation: 'mask_paint',
        tool: lumenSculptMode,
        op,
        radius: paintRadiusRef.current,
        point_count: layer === 'lumen' ? lumenPolygonRef.current.length : pointsRef.current.length,
        image_x: last?.[0],
        image_y: last?.[1],
      });
      lumenPaintStrokeRef.current = null;
      lumenPaintBaseRef.current = null;
      try {
        if (e.currentTarget.hasPointerCapture(e.pointerId)) {
          e.currentTarget.releasePointerCapture(e.pointerId);
        }
      } catch {
        /* ignore */
      }
      return;
    }
    const activeStroke = activePromptStrokeRef.current;
    if (activeStroke) {
      if (promptStrokeRafRef.current != null) {
        cancelAnimationFrame(promptStrokeRafRef.current);
        promptStrokeRafRef.current = null;
      }
      const finalPoint = canvasToImage(e) || pendingPromptPointRef.current;
      pendingPromptPointRef.current = null;
      const finalizedStroke: ActiveSamStroke = {
        ...activeStroke,
        points: appendFinalPromptPoint(activeStroke.points, finalPoint, 0.5),
      };
      activePromptStrokeRef.current = null;
      setActivePromptStroke(null);
      try {
        if (e.currentTarget.hasPointerCapture(e.pointerId)) {
          e.currentTarget.releasePointerCapture(e.pointerId);
        }
      } catch {
        /* ignore */
      }
      void applyActiveSamStroke(finalizedStroke);
      return;
    }
    if (lumenBoxDragRef.current) {
      lumenBoxDragRef.current = null;
      try {
        if (e.currentTarget.hasPointerCapture(e.pointerId)) {
          e.currentTarget.releasePointerCapture(e.pointerId);
        }
      } catch {
        /* ignore */
      }
      const current = lumenBoxRef.current;
      if (current) {
        const normalized = normalizeLumenBBox(current);
        setLumenBox(normalized);
        setLumenPolygon([]);
        setLumenResultMeta((prev) => ({
          ...prev,
          source: prev?.source === 'yolo' || prev?.source === 'yolo_then_sam31' ? 'yolo_then_manual' : 'manual',
          sam_backend_id: undefined,
          sam_score: undefined,
          error: undefined,
        }));
        const boxW = Math.abs(normalized.x2 - normalized.x1);
        const boxH = Math.abs(normalized.y2 - normalized.y1);
        if (boxW > 12 && boxH > 12) {
          setLumenEditMode(false);
          setMessage(zh ? '胃腔框已画出，正在自动分割…' : 'Lumen box set; auto-segmenting…');
          void segmentLumenWithSam31().then((ok) => {
            if (ok) {
              setLumenEditMode(false);
              setMessage(zh ? '胃腔已自动分割。要重画请再点「框选胃腔」' : 'Lumen auto-segmented. Arm Box lumen to redraw');
            } else {
              setLumenEditMode(true);
              lumenBoxFreshDrawRef.current = true;
              setMessage(zh ? '胃腔自动分割未成功，框选仍点亮，可再拖一框' : 'Lumen auto-segment failed; Box lumen stays armed');
            }
          });
        } else {
          setMessage(zh ? '请拖出更大的胃腔框' : 'Drag a larger lumen box');
          setLumenEditMode(true);
        }
        if (mediaMode === 'video' && pointsRef.current.length >= 3) {
          recordVideoFrameOverride(pointsRef.current, 'accepted');
          void persistOverrideRef.current('doctor_edit', { silent: true });
        }
        void persistLumenOverrideRef.current(true);
        recordDoctorOp('lumen_edit', {
          layer: 'lumen',
          operation: 'lumen_box_drag',
          tool: 'lumen_box',
        });
      }
      return;
    }
    const boxDrag = samBoxDragRef.current;
    if (boxDrag) {
      samBoxDragRef.current = null;
      setSamBoxPreview(null);
      try {
        if (e.currentTarget.hasPointerCapture(e.pointerId)) {
          e.currentTarget.releasePointerCapture(e.pointerId);
        }
      } catch {
        /* ignore */
      }
      const dx = Math.abs(boxDrag.x1 - boxDrag.x0);
      const dy = Math.abs(boxDrag.y1 - boxDrag.y0);
      const neg = e.currentTarget.dataset.samNeg === '1' || e.shiftKey;
      delete e.currentTarget.dataset.samNeg;
      if (dx > 12 || dy > 12) {
        const box = {
          x1: Math.min(boxDrag.x0, boxDrag.x1),
          y1: Math.min(boxDrag.y0, boxDrag.y1),
          x2: Math.max(boxDrag.x0, boxDrag.x1),
          y2: Math.max(boxDrag.y0, boxDrag.y1),
        };
        const cx = (box.x1 + box.x2) / 2;
        const cy = (box.y1 + box.y2) / 2;
        // Box prompt resets click history (cleaner region seed).
        samClicksRef.current = [{ x: cx, y: cy, label: 'positive' }];
        setSamClicks(samClicksRef.current);
        setSimplePromptBox(box);
        setSimplePromptMode('box');
        armLesionBox(false);
        recordDoctorOp('box_draw_end', {
          layer: 'lesion',
          operation: 'box_draw_end',
          tool: 'box_lesion',
          image_x: cx,
          image_y: cy,
        });
        if (simpleVideoMode) {
          applyDoctorLesionBox(box);
          setBoxAutoSegBusy(true);
          void runSamClick([cx, cy], 'positive', box).then((poly) => {
            setBoxAutoSegBusy(false);
            resumeSimpleTracking(poly);
            stopInteractivePrompt();
            setMode('soft');
            setSimplePromptMode('box');
            armLesionBox(false);
            setSimpleEditMode(true);
            setSimpleEditLayer('lesion');
            setActiveLayer('lesion');
            setLumenEditMode(false);
            persistOpenKeyframeContours({ refined: true });
            const ok = Boolean(poly && poly.length >= 3);
            recordDoctorOp('sam_refine', {
              layer: 'lesion',
              operation: 'sam_refine',
              tool: 'box_lesion',
              status: ok ? 'ok' : 'error',
              point_count: (poly && poly.length >= 3) ? poly.length : pointsRef.current.length,
            });
            setMessage(
              ok
                ? (zh ? '已出遮罩，可拖病灶精修' : 'Mask ready; drag to refine')
                : (zh ? '已用框作为轮廓，可拖点精修' : 'Kept the box as the contour; drag to refine'),
            );
          }).catch(() => {
            setBoxAutoSegBusy(false);
            armLesionBox(false);
            setMode('soft');
            setSimpleEditMode(true);
            setSimpleEditLayer('lesion');
            persistOpenKeyframeContours({ refined: true });
            recordDoctorOp('sam_refine', {
              layer: 'lesion',
              operation: 'sam_refine',
              tool: 'box_lesion',
              status: 'error',
            });
            setMessage(zh ? '已用框作为轮廓，可拖点精修' : 'Kept the box as the contour; drag to refine');
          });
        } else {
          void runSamClick([cx, cy], 'positive', box).then((poly) => {
            resumeSimpleTracking(poly);
            if (poly && poly.length >= 3) {
              stopInteractivePrompt();
              setMode('soft');
              setSimplePromptMode('box');
              armLesionBox(false);
              setSimpleEditMode(true);
              setSimpleEditLayer('lesion');
              setActiveLayer('lesion');
              setLumenEditMode(false);
              setMessage(
                zh
                  ? '框选完成：已出遮罩。拖病灶本体可整体移动；要重画请再点「框选病灶」'
                  : 'Box done: mask ready. Drag the lesion body to move it; arm Box lesion only to redraw',
              );
            }
          });
        }
      } else if (simpleVideoMode) {
        setMessage(zh ? '请拖出矩形框选病灶（单击不会加正负点）' : 'Drag a rectangle to box the lesion (clicks do not add points)');
      } else {
        void runSamClick(
          [boxDrag.x0, boxDrag.y0],
          neg ? 'negative' : 'positive',
        )
          .then((poly) => resumeSimpleTracking(poly));
      }
      return;
    }
    if (dragIndexRef.current !== null) {
      if (dragRafRef.current != null) {
        cancelAnimationFrame(dragRafRef.current);
        dragRafRef.current = null;
      }
      const lastPt = pendingDragPtRef.current;
      const editedLayer = dragLayerRef.current;
      const dragIdx = dragIndexRef.current;
      if (lastPt && editedLayer && dragIdx !== null) {
        if (editedLayer === 'band') {
          const bandIndex = dragBandIndexRef.current;
          const bands = wallLayerBandsRef.current;
          if (bandIndex != null && bands[bandIndex]?.[dragIdx]) {
            const nextBand = clonePoly(bands[bandIndex]);
            if (dragSoftRef.current) {
              softDeform(nextBand, dragIdx, lastPt[0], lastPt[1], WALL_SOFT_SIGMA);
            }
            nextBand[dragIdx] = [lastPt[0], lastPt[1]];
            const nextBands = bands.map((band, index) => (index === bandIndex ? nextBand : band));
            wallLayerBandsRef.current = nextBands;
            setWallLayerBands(nextBands);
            const wall = wallPointsRef.current;
            const readout = wallLayerReadoutRef.current;
            const frame = captureFrameGray();
            if (wall.length >= 3 && readout && frame) {
              const ids = doctorClinicalIds(wallLayerTargetRef.current);
              const next = attachLayerInterrupts(
                readout,
                frame.gray,
                frame.width,
                frame.height,
                nextBands.map((curve, index) => ({
                  layer: ids[index] || 5,
                  curve,
                })),
                wallLayerTargetRef.current,
              );
              setWallLayerReadout(next);
              wallLayerReadoutRef.current = next;
            }
          }
        } else {
          const src = editedLayer === 'wall'
            ? wallPointsRef.current
            : editedLayer === 'lumen'
              ? lumenPolygonRef.current
              : pointsRef.current;
          if (src[dragIdx]) {
            const next = clonePoly(src);
            if (dragSoftRef.current) {
              softDeform(
                next,
                dragIdx,
                lastPt[0],
                lastPt[1],
                editedLayer === 'wall' ? WALL_SOFT_SIGMA : editedLayer === 'lumen' ? LUMEN_SOFT_SIGMA : LESION_SOFT_SIGMA,
              );
            }
            next[dragIdx] = [lastPt[0], lastPt[1]];
            if (editedLayer === 'wall') wallPointsRef.current = next;
            else if (editedLayer === 'lumen') lumenPolygonRef.current = next;
            else pointsRef.current = next;
          }
        }
      }
      pendingDragPtRef.current = null;
      draggingRef.current = false;
      recordDoctorOp('contour_drag', {
        layer: editedLayer === 'band' ? 'wall' : editedLayer,
        operation: editedLayer === 'band' ? 'wall_band_drag' : 'contour_drag',
        tool: dragSoftRef.current ? 'brush' : 'hard',
        point_count: editedLayer === 'band'
          ? (wallLayerBandsRef.current[dragBandIndexRef.current || 0]?.length || 0)
          : editedLayer === 'wall'
            ? wallPointsRef.current.length
            : editedLayer === 'lumen'
              ? lumenPolygonRef.current.length
              : pointsRef.current.length,
        image_x: lastPt?.[0],
        image_y: lastPt?.[1],
      });
      setPoints(clonePoly(pointsRef.current));
      setWallPoints(clonePoly(wallPointsRef.current));
      setLumenPolygon(clonePoly(lumenPolygonRef.current));
      if (editedLayer === 'lumen' && lumenPolygonRef.current.length >= 3) {
        const box = bboxFromPolygon(lumenPolygonRef.current);
        if (box) {
          lumenBoxRef.current = box;
          setLumenBox(box);
        }
        void persistLumenOverrideRef.current(true);
      }
      if (editedLayer === 'band') {
        persistOpenKeyframeContours({ refined: true });
        setMessage(zh ? '已按您拖过的假想分层重核中断（不定 cT）' : 'Re-checked interrupt on the sculpted layer (not a definite cT)');
      }
      if (mediaMode === 'video' && editedLayer === 'lesion') {
        setTrackingPrepared(false);
        recordVideoFrameOverride(pointsRef.current, 'accepted');
      }
      markActiveDoctorKeyframeRefined();
      if (editedLayer !== 'band') {
        setMessage(
          zh
            ? (editedLayer === 'wall' ? '胃壁区域已更新' : editedLayer === 'lumen' ? '胃腔轮廓已更新' : '当前帧病灶区域已更新')
            : (editedLayer === 'wall' ? 'Wall region updated' : editedLayer === 'lumen' ? 'Lumen contour updated' : 'Current-frame lesion region updated'),
        );
      }
      void persistOverrideRef.current('doctor_edit', { silent: true });
      try {
        if (e.currentTarget.hasPointerCapture(e.pointerId)) {
          e.currentTarget.releasePointerCapture(e.pointerId);
        }
      } catch {
        /* ignore */
      }
    }
    dragIndexRef.current = null;
    dragLayerRef.current = null;
    dragBandIndexRef.current = null;
    setDragIndex(null);
    setDragLayer(null);
  };

  const onPointerCancel = (e: React.PointerEvent<HTMLCanvasElement>) => {
    if (activePromptStrokeRef.current) {
      if (promptStrokeRafRef.current != null) {
        cancelAnimationFrame(promptStrokeRafRef.current);
        promptStrokeRafRef.current = null;
      }
      pendingPromptPointRef.current = null;
      activePromptStrokeRef.current = null;
      setActivePromptStroke(null);
      try {
        if (e.currentTarget.hasPointerCapture(e.pointerId)) {
          e.currentTarget.releasePointerCapture(e.pointerId);
        }
      } catch {
        /* ignore */
      }
      e.preventDefault();
      redraw();
      return;
    }
    onPointerUp(e);
  };

  const propagateMaskAcrossVideo = useCallback(async () => {
    if (mediaMode !== 'video' || !videoRef.current || points.length < 3) {
      setMessage(zh ? '请先在视频帧上得到可编辑区域' : 'Need an editable region on a video frame');
      return;
    }
    const video = videoRef.current;
    const start = video.currentTime || 0;
    const duration = video.duration || 0;
    // Full-video tracking must cover frames before and after the seed, not only later frames.
    if (!duration || duration <= 0.1) {
      setMessage(zh ? '当前视频时长不可用' : 'Video duration unavailable');
      return;
    }
    freezeCurrentFrame();
    setPropagateBusy(true);
    setTrackOnPlay(false);
    const traceId = `video_propagate_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
    const traceStartedAt = performance.now();
    const step = Math.max(0.2, Math.min(0.5, duration / 40));
    const maxSteps = 12;
    const imageWidth = video.videoWidth;
    const imageHeight = video.videoHeight;
    let currentPoly = points.map((p) => [p[0], p[1]]);
    const seedLumenPoly = lumenPolygonRef.current.length >= 3 ? clonePoly(lumenPolygonRef.current) : undefined;
    const seedLumenBox = lumenBoxRef.current || (seedLumenPoly ? bboxFromPolygon(seedLumenPoly) : undefined);
    let propagatedFrames: VideoMaskFrameOverride[] = [{
      timestamp_sec: Number(start.toFixed(3)),
      imageWidth,
      imageHeight,
      mask_polygon: currentPoly.map((p) => [Math.round(p[0] * 10) / 10, Math.round(p[1] * 10) / 10]),
      roi_bbox: bboxFromPolygon(currentPoly),
      lumen_polygon: seedLumenPoly,
      lumen_bbox: seedLumenBox || undefined,
      source: 'video_propagate',
      propagation_status: 'seed',
    }];
    setVideoFrameOverrides(propagatedFrames);
    let okSteps = 0;
    try {
      try {
        const centroid = polygonCentroid(currentPoly);
        const nativeResponse = await fetch('/api/agent/video/propagate', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            case_id: patient?.patient_id || patient?.id || '',
            model: segmentationModel,
            video_url: videoUrl,
            frame_time: start,
            image_width: imageWidth,
            image_height: imageHeight,
            clicks: samClicksRef.current.length
              ? samClicksRef.current
              : centroid
                ? [{ x: centroid[0], y: centroid[1], label: 'positive' }]
                : [],
            box: bboxFromPolygon(currentPoly),
            direction: 'both',
            max_frames: Math.max(120, Math.ceil(duration * 120)),
          }),
        });
        const nativePayload = await nativeResponse.json() as {
          ok?: boolean;
          error?: string;
          result?: {
            status?: string;
            needs_reanchor?: boolean;
            accepted_frames?: number;
            num_frames?: number;
            propagation_mode?: string;
            native_multiplex_memory?: boolean;
            frames?: Array<{
              frame_index?: number;
              frame_time: number;
              direction?: string;
              mask_polygon?: number[][];
              accepted?: boolean;
              quality_score?: number;
            }>;
          };
        };
        if (!nativeResponse.ok || !nativePayload.ok || !nativePayload.result) {
          throw new Error(nativePayload.error || 'native video propagation failed');
        }
        const nativeFrames = mapPropagateFramesToOverrides(
          nativePayload.result.frames || [],
          imageWidth,
          imageHeight,
          'video_track',
        );
        if (!nativeFrames.length) throw new Error('native video propagation returned no masks');

        const lumenSeedPoly = lumenPolygonRef.current.length >= 3 ? clonePoly(lumenPolygonRef.current) : [];
        const lumenSeedBox = lumenBoxRef.current || (lumenSeedPoly.length >= 3 ? bboxFromPolygon(lumenSeedPoly) : null);
        const lumenCentroid = lumenSeedPoly.length >= 3
          ? polygonCentroid(lumenSeedPoly)
          : (lumenSeedBox
            ? [(lumenSeedBox.x1 + lumenSeedBox.x2) / 2, (lumenSeedBox.y1 + lumenSeedBox.y2) / 2]
            : null);
        let lumenFrames: VideoMaskFrameOverride[] = [];
        let lumenTracked = false;
        if (lumenSeedBox && lumenCentroid) {
          setPropagateProgress(zh ? '胃腔跟踪中…' : 'Tracking lumen…');
          try {
            const lumenResult = await requestVideoPropagate({
              case_id: patient?.patient_id || patient?.id || '',
              model: segmentationModel,
              video_url: videoUrl,
              frame_time: start,
              image_width: imageWidth,
              image_height: imageHeight,
              clicks: [{ x: lumenCentroid[0], y: lumenCentroid[1], label: 'positive' }],
              box: lumenSeedBox,
              direction: 'both',
              max_frames: Math.max(120, Math.ceil(duration * 120)),
              text_prompt: 'gastric lumen cavity',
              use_lora: false,
            });
            lumenFrames = mapPropagateFramesToOverrides(
              lumenResult.frames || [],
              imageWidth,
              imageHeight,
              'video_track',
            );
            lumenTracked = lumenFrames.length > 0;
          } catch (lumenError) {
            console.warn('lumen video track failed', lumenError);
          }
        }

        const mergedFrames = mergeLumenIntoLesionFrames(nativeFrames, lumenFrames, {
          polygon: lumenSeedPoly,
          box: lumenSeedBox,
        }, start);
        videoFrameOverridesRef.current = mergedFrames;
        setVideoFrameOverrides(mergedFrames);
        const nearest = mergedFrames.reduce((best, frame) => (
          Math.abs(frame.timestamp_sec - start) < Math.abs(best.timestamp_sec - start) ? frame : best
        ), mergedFrames[0]);
        if (nearest?.mask_polygon?.length) {
          pointsRef.current = nearest.mask_polygon;
          setPoints(nearest.mask_polygon);
        }
        if (nearest?.lumen_polygon?.length) {
          lumenPolygonRef.current = nearest.lumen_polygon;
          setLumenPolygon(nearest.lumen_polygon);
          const nextBox = nearest.lumen_bbox || bboxFromPolygon(nearest.lumen_polygon);
          if (nextBox) {
            lumenBoxRef.current = nextBox;
            setLumenBox(nextBox);
          }
        }
        setFrameFrozen(true);
        frameFrozenRef.current = true;
        const usedSam31MemoryPrompt = nativePayload.result.propagation_mode === 'sam3.1_motion_memory_box'
          || nativePayload.result.propagation_mode === 'sam3.1_framewise_fixed_box'
          || nativePayload.result.propagation_mode === 'sam3.1_native_multiplex_memory'
          || nativePayload.result.native_multiplex_memory === true;
        await applyAreaKeyframesRef.current(mergedFrames);
        const persisted = await persistOverrideRef.current('video_tracking_complete');
        maskAuditRef.current('model_trace', {
          trace_id: traceId,
          operation: 'video_propagation',
          model: segmentationModel,
          source: 'video_propagate',
          outcome: 'success',
          frame_time_sec: start,
          input: {
            direction: 'both',
            requested_max_frames: nativePayload.result.num_frames,
            video_duration_sec: duration,
          },
          output: {
            lesion_frame_count: nativeFrames.length,
            lumen_frame_count: lumenFrames.length,
            merged_frame_count: mergedFrames.length,
            accepted_frames: nativePayload.result.accepted_frames,
            lumen_tracked: lumenTracked,
            needs_reanchor: nativePayload.result.needs_reanchor,
            persisted,
          },
          duration_ms: Math.round(performance.now() - traceStartedAt),
        });
        setMessage(
          zh
            ? `${usedSam31MemoryPrompt ? '视频跟踪完成' : '跟踪扩散完成'}：病灶 ${nativePayload.result.accepted_frames || nativeFrames.length}/${nativePayload.result.num_frames || nativeFrames.length} 帧${lumenTracked ? `，胃腔 ${lumenFrames.length} 帧` : (lumenSeedBox ? '（胃腔跟踪失败）' : '（未提供胃腔）')}；${persisted ? '完整结果已保存' : '保存失败，请点击保存轮廓'}${nativePayload.result.needs_reanchor ? '，已请求重锚定' : ''}`
            : `${usedSam31MemoryPrompt ? 'Video tracking complete' : 'Tracking propagation complete'}: lesion ${nativePayload.result.accepted_frames || nativeFrames.length}/${nativePayload.result.num_frames || nativeFrames.length} frames${lumenTracked ? `, lumen ${lumenFrames.length}` : ''}; ${persisted ? 'complete result saved' : 'save failed, click Save complete masks'}`,
        );
        return;
      } catch (nativeError) {
        maskAuditRef.current('model_trace', {
          trace_id: traceId,
          operation: 'video_propagation',
          model: segmentationModel,
          source: 'video_propagate',
          outcome: 'fallback_to_sampled_tracking',
          frame_time_sec: start,
          error: nativeError instanceof Error ? nativeError.message.slice(0, 240) : 'Native propagation failed',
        });
        setMessage(
          zh
            ? `原生视频传播不可用，回退逐帧跟踪：${nativeError instanceof Error ? nativeError.message : 'unknown error'}`
            : 'Native propagation unavailable; falling back to sampled tracking',
        );
      }

      // Fallback sampled tracking: cover both directions from the seed, not only later frames.
      const backwardSteps = Math.max(0, Math.floor(maxSteps * (start / Math.max(duration, 0.01))));
      const forwardSteps = maxSteps - backwardSteps;
      const sampleTimes = [
        ...Array.from({ length: backwardSteps }, (_, index) => Math.max(0.01, start - step * (backwardSteps - index))).reverse(),
        ...Array.from({ length: forwardSteps }, (_, index) => Math.min(duration - 0.01, start + step * (index + 1))),
      ].filter((t) => t > 0 && t < duration && Math.abs(t - start) > 0.05);

      for (let i = 0; i < sampleTimes.length; i += 1) {
        const t = sampleTimes[i];
        setPropagateProgress(`${i + 1}/${sampleTimes.length}, t=${t.toFixed(2)}s`);
        video.currentTime = t;
        await new Promise<void>((resolve) => {
          const done = () => {
            video.removeEventListener('seeked', done);
            resolve();
          };
          video.addEventListener('seeked', done);
        });
        await sleep(40);
        const bbox = bboxFromPolygon(currentPoly);
        const centroid = polygonCentroid(currentPoly);
        if (!bbox || !centroid) break;
        const prev = currentPoly;
        const nextPoly = await runSamAtPoint(centroid, {
          silent: true,
          source: 'video_propagate',
          box: bbox,
          keepEditing: false,
        });
        if (!nextPoly || nextPoly.length < 3) {
          setPoints(prev);
          break;
        }
        currentPoly = nextPoly;
        setPoints(nextPoly);
        propagatedFrames = ([
          ...propagatedFrames,
          {
            timestamp_sec: Number(t.toFixed(3)),
            imageWidth,
            imageHeight,
            mask_polygon: nextPoly.map((p) => [Math.round(p[0] * 10) / 10, Math.round(p[1] * 10) / 10]),
            roi_bbox: bboxFromPolygon(nextPoly),
            lumen_polygon: seedLumenPoly,
            lumen_bbox: seedLumenBox || undefined,
            source: 'video_propagate' as const,
            propagation_status: 'accepted' as const,
          },
        ] as VideoMaskFrameOverride[]).sort((a, b) => a.timestamp_sec - b.timestamp_sec);
        setVideoFrameOverrides(propagatedFrames);
        okSteps += 1;
        setVideoTime(t);
        redraw();
      }
      setFrameFrozen(true);
      frameFrozenRef.current = true;
      setMode('soft');
      videoFrameOverridesRef.current = propagatedFrames;
      await applyAreaKeyframesRef.current(propagatedFrames);
      const persisted = await persistOverrideRef.current('video_tracking_complete');
      maskAuditRef.current('model_trace', {
        trace_id: traceId,
        operation: 'video_propagation',
        model: segmentationModel,
        source: 'video_propagate_fallback',
        outcome: 'success',
        frame_time_sec: start,
        input: {
          direction: 'both',
          max_steps: maxSteps,
          video_duration_sec: duration,
        },
        output: {
          lesion_frame_count: propagatedFrames.length,
          successful_steps: okSteps,
          lumen_seed_present: Boolean(seedLumenBox),
          persisted,
        },
        duration_ms: Math.round(performance.now() - traceStartedAt),
      });
    setMessage(
      zh
        ? `已跟踪扩散 ${okSteps} 帧（覆盖种子帧前后）；${persisted ? '完整结果已保存' : '保存失败，请点击保存轮廓'}`
        : `Propagated ${okSteps} frames (before and after the seed); ${persisted ? 'complete result saved' : 'save failed, click Save complete masks'}`,
    );
    } catch (error) {
      maskAuditRef.current('model_trace', {
        trace_id: traceId,
        operation: 'video_propagation',
        model: segmentationModel,
        source: 'video_propagate',
        outcome: 'error',
        frame_time_sec: start,
        error: error instanceof Error ? error.message.slice(0, 240) : 'Video propagation failed',
        duration_ms: Math.round(performance.now() - traceStartedAt),
      });
      setMessage(error instanceof Error ? error.message : (zh ? '视频跟踪失败' : 'Video propagation failed'));
    } finally {
      setPropagateBusy(false);
      setPropagateProgress(null);
    }
  }, [mediaMode, patient?.id, patient?.patient_id, points, segmentationModel, videoUrl, zh, freezeCurrentFrame, runSamAtPoint, redraw]);

  const buildOverride = useCallback((): MaskBoundaryOverride | null => {
    const currentPoints = mediaMode === 'video' && videoFrameOverridesRef.current.length
      ? getCurrentTrackedPolygon()
      : pointsRef.current;
    const currentWallPoints = wallPointsRef.current;
    const currentVideoFrames = mediaMode === 'video' && videoFrameOverridesRef.current.length
      ? videoFrameOverridesRef.current
      : [];
    if (!patient || currentPoints.length < 3) return null;
    const video = videoRef.current;
    const img = imgRef.current;
    const width =
      mediaMode === 'video' && video?.videoWidth
        ? video.videoWidth
        : (img?.naturalWidth || 0);
    const height =
      mediaMode === 'video' && video?.videoHeight
        ? video.videoHeight
        : (img?.naturalHeight || 0);
    if (!width || !height) return null;
    return {
      patientId: patient.patient_id,
      frameId: patient.id,
      imageWidth: width,
      imageHeight: height,
      mask_polygon: currentPoints.map((p) => [Math.round(p[0]), Math.round(p[1])]),
      wall_polygon:
        currentWallPoints.length >= 3
          ? currentWallPoints.map((p) => [Math.round(p[0]), Math.round(p[1])])
          : undefined,
      roi_bbox: bboxFromPolygon(currentPoints),
      roi_mode: roiMode,
      source: nnInteractiveMode && nnInteractiveTarget === 'lesion'
        ? 'nninteractive'
        : (mode === 'sam' ? 'sam' : 'manual'),
      video_time_sec: mediaMode === 'video'
        ? Number((video?.currentTime ?? videoTime).toFixed(3))
        : undefined,
      video_url: mediaMode === 'video' ? videoUrl || undefined : undefined,
      video_frames: currentVideoFrames.length
        ? currentVideoFrames.map((frame) => {
          const maskPolygon = frame.mask_polygon.map((point) => [Math.round(point[0]), Math.round(point[1])]);
          const lumenPolygon = frame.lumen_polygon?.map((point) => [Math.round(point[0]), Math.round(point[1])]);
          return {
            ...frame,
            mask_polygon: maskPolygon,
            roi_bbox: frame.roi_bbox || bboxFromPolygon(maskPolygon),
            lumen_polygon: lumenPolygon,
            lumen_bbox: frame.lumen_bbox
              || (lumenPolygon && bboxFromPolygon(lumenPolygon)),
          };
        })
        : undefined,
      note: currentVideoFrames.length
        ? 'Video tracking stores complete lesion and lumen contours at sampled timestamps; doctor edits replace the current timestamp.'
        : undefined,
      prompt_type: mode === 'sam' ? simplePromptMode : mode,
      prompt_payload: {
        mode: mode === 'sam' ? simplePromptMode : mode,
        box: simplePromptBox,
        clicks: samClicks.map((click) => ({
          x: Math.round(click.x * 10) / 10,
          y: Math.round(click.y * 10) / 10,
          label: click.label,
        })),
        scribbles: promptStrokes.map((stroke) => ({
          points: stroke.points.map((point) => ({
            x: Math.round(point[0] * 10) / 10,
            y: Math.round(point[1] * 10) / 10,
          })),
          label: stroke.label,
          width: stroke.width,
          kind: stroke.kind,
        })),
      },
      model_version: nnInteractiveMode ? 'nnInteractive_v1.0' : segmentationModel,
      sam_score: samReport?.sam_score,
      updated_at: new Date().toISOString(),
    };
  }, [getCurrentTrackedPolygon, mediaMode, mode, nnInteractiveMode, nnInteractiveTarget, patient, promptStrokes, roiMode, samClicks, samReport?.sam_score, segmentationModel, simplePromptBox, simplePromptMode, videoTime, videoUrl]);

  const persistOverride = useCallback(async (
    action = 'manual_save',
    options: PersistOverrideOptions = {},
  ): Promise<boolean> => {
    const next = buildOverride();
    if (!next) {
      if (!options.silent) setMessage(zh ? '至少需要 3 个顶点' : 'Need at least 3 vertices');
      return false;
    }
    const lumenSnapshot = buildLumenOverride() || lumenOverride || undefined;
    const save = async (): Promise<boolean> => {
      savingRef.current = true;
      setSaving(true);
      if (!options.silent) setMessage(null);
      try {
        const res = await fetch('/api/patients/mask-overrides', {
          method: 'POST',
          headers: authHeaders({ 'Content-Type': 'application/json' }),
          body: JSON.stringify({
            override: next,
            lumen_override: lumenSnapshot,
            action,
            reader_id: accountReaderId || undefined,
          }),
        });
        const data = await res.json() as {
          override?: MaskBoundaryOverride;
          lumen_override?: LumenOverride;
          history_entry?: MaskHistoryEntry;
          error?: string;
        };
        if (!res.ok) throw new Error(data.error || 'Save failed');
        const saved = data.override || next;
        onOverrideChange(saved);
        videoFrameOverridesRef.current = saved.video_frames || [];
        setVideoFrameOverrides(videoFrameOverridesRef.current);
        maskAuditRef.current('mask_saved', {
          action,
          success: true,
          history_entry_id: data.history_entry?.id,
          ...summarizeMaskForAudit(saved),
        });
        recordDoctorOp('mask_save', {
          operation: action || 'mask_save',
          op: 'mask_save',
          status: 'ok',
          history_entry_id: data.history_entry?.id || null,
        });
        if (accountReaderId && patient?.id) {
          void fetch('/api/reader/case-state', {
            method: 'PUT',
            headers: authHeaders({ 'Content-Type': 'application/json' }),
            body: JSON.stringify({
              account_id: accountReaderId,
              case_id: patient.id,
              patient_id: patient.patient_id,
              study_mode: patient.study_mode || undefined,
              progress: 'in_progress',
              increment_mask_save: true,
              activity_append: {
                id: `mask_${Date.now().toString(36)}`,
                at: new Date().toISOString(),
                type: 'mask_saved',
                label_zh: action === 'video_tracking_complete' ? '视频跟踪分割已保存' : '病灶/胃腔分割已保存',
                label_en: action === 'video_tracking_complete' ? 'Tracking segmentation saved' : 'Lesion/lumen mask saved',
                detail: { action, history_entry_id: data.history_entry?.id || null },
              },
            }),
          }).catch(() => {});
        }
        if (data.history_entry) {
          setMaskHistory((current) => [
            data.history_entry!,
            ...current.filter((item) => item.id !== data.history_entry!.id),
          ].slice(0, 40));
        }
        lastCompleteMaskSigRef.current = [
          next.mask_polygon?.length || 0,
          next.mask_polygon?.[0]?.[0] || 0,
          next.mask_polygon?.[0]?.[1] || 0,
          lumenSnapshot?.lumen_polygon?.length || 0,
          (saved.video_frames || []).length,
        ].join(':');
        if (simpleVideoMode) setCompleteMaskAutosaved(true);
        if (!options.silent) {
          setMessage(
            action === 'video_tracking_complete'
              ? (zh ? '视频跟踪结果已完整保存，可在历史记录中恢复' : 'Complete video tracking result saved; it can be restored from history')
              : (zh ? '边界已保存，分析将使用此覆盖' : 'Boundary saved — analyze will use this override'),
          );
        }
        return true;
      } catch (err) {
        maskAuditRef.current('mask_saved', {
          action,
          success: false,
          error: err instanceof Error ? err.message.slice(0, 240) : 'Save failed',
        });
        if (!options.silent) {
          setMessage(err instanceof Error ? err.message : 'Save failed');
        }
        return false;
      } finally {
        savingRef.current = false;
        setSaving(false);
      }
    };
    const queued = persistChainRef.current.catch(() => false).then(save);
    persistChainRef.current = queued.catch(() => false);
    return queued;
  }, [accountReaderId, authHeaders, buildLumenOverride, buildOverride, lumenOverride, onOverrideChange, simpleVideoMode, zh]);

  useEffect(() => {
    persistOverrideRef.current = persistOverride;
  }, [persistOverride]);

  const scheduleCompleteMaskAutosave = useCallback((action = 'auto_save') => {
    if (!simpleVideoMode || pointsRef.current.length < 3) return;
    if (completeMaskAutosaveTimerRef.current != null) {
      window.clearTimeout(completeMaskAutosaveTimerRef.current);
    }
    completeMaskAutosaveTimerRef.current = window.setTimeout(() => {
      completeMaskAutosaveTimerRef.current = null;
      if (pointsRef.current.length < 3 || trackBusyRef.current || samBusyRef.current) return;
      const lesion = pointsRef.current;
      const mid = lesion[Math.floor(lesion.length / 2)] || lesion[0];
      const sig = [
        lesion.length,
        lesion[0]?.[0] || 0,
        lesion[0]?.[1] || 0,
        mid?.[0] || 0,
        mid?.[1] || 0,
        lumenPolygonRef.current.length,
        videoFrameOverridesRef.current.length,
      ].join(':');
      if (sig === lastCompleteMaskSigRef.current) return;
      void persistOverrideRef.current(action, { silent: true });
    }, 400);
  }, [simpleVideoMode]);
  scheduleCompleteMaskAutosaveRef.current = scheduleCompleteMaskAutosave;

  useEffect(() => () => {
    if (completeMaskAutosaveTimerRef.current != null) {
      window.clearTimeout(completeMaskAutosaveTimerRef.current);
    }
  }, []);

  const loadMaskHistory = useCallback(async () => {
    if (!patient) return;
    setHistoryBusy(true);
    try {
      const params = new URLSearchParams({
        patientId: patient.patient_id,
        frameId: patient.id,
        history: '1',
      });
      if (accountReaderId) params.set('readerId', accountReaderId);
      const res = await fetch(`/api/patients/mask-overrides?${params.toString()}`, {
        cache: 'no-store',
        headers: authHeaders(),
      });
      const data = await res.json() as { history?: MaskHistoryEntry[]; error?: string };
      if (!res.ok) throw new Error(data.error || 'History loading failed');
      const nextHistory = Array.isArray(data.history) ? data.history : [];
      setMaskHistory(nextHistory);
      setHistoryPreviewId((current) => (
        current && nextHistory.some((entry) => entry.id === current) ? current : null
      ));
      maskAuditRef.current('mask_event', {
        action: 'history_loaded',
        history_count: nextHistory.length,
        displayed_on_canvas: false,
      });
    } catch (error) {
      maskAuditRef.current('error', {
        operation: 'history_loaded',
        error: error instanceof Error ? error.message.slice(0, 240) : 'History loading failed',
      });
      setMessage(error instanceof Error ? error.message : (zh ? '历史记录加载失败' : 'History loading failed'));
    } finally {
      setHistoryBusy(false);
    }
  }, [accountReaderId, authHeaders, patient, zh]);

  const deleteMaskHistoryEntry = useCallback(async (entry: MaskHistoryEntry) => {
    if (!patient || !entry?.id || historyBusy) return;
    if (!window.confirm(zh ? '删除该历史版本？仅对本账号隐藏。' : 'Delete this history version? It will be hidden for your account.')) {
      return;
    }
    setHistoryBusy(true);
    try {
      const params = new URLSearchParams({
        patientId: patient.patient_id,
        frameId: patient.id,
        historyId: entry.id,
      });
      if (accountReaderId) params.set('readerId', accountReaderId);
      const res = await fetch(`/api/patients/mask-overrides?${params.toString()}`, {
        method: 'DELETE',
        headers: authHeaders(),
      });
      const data = await res.json() as { ok?: boolean; error?: string };
      if (!res.ok || !data.ok) throw new Error(data.error || 'Delete failed');
      if (historyPreviewId === entry.id) setHistoryPreviewId(null);
      maskAuditRef.current('mask_event', {
        action: 'history_deleted',
        history_entry_id: entry.id,
      });
      await loadMaskHistory();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : (zh ? '删除失败' : 'Delete failed'));
    } finally {
      setHistoryBusy(false);
    }
  }, [accountReaderId, authHeaders, historyBusy, historyPreviewId, loadMaskHistory, patient, zh]);

  const restoreMaskHistory = useCallback(async (entry: MaskHistoryEntry) => {
    if (!patient || !entry?.override || historyBusy || savingRef.current) return;
    setHistoryBusy(true);
    maskAuditRef.current('mask_event', {
      action: 'history_restore_requested',
      history_entry_id: entry.id,
      ...summarizeMaskForAudit(entry.override),
    });
    try {
      await persistChainRef.current.catch(() => false);
      const res = await fetch('/api/patients/mask-overrides', {
        method: 'POST',
        headers: authHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({
          override: entry.override,
          lumen_override: entry.lumen_override,
          action: 'restore_history',
          reader_id: accountReaderId || undefined,
        }),
      });
      const data = await res.json() as {
        override?: MaskBoundaryOverride;
        lumen_override?: LumenOverride;
        error?: string;
      };
      if (!res.ok) throw new Error(data.error || 'History restore failed');
      const restored = data.override || entry.override;
      let restoredLumen = data.lumen_override || entry.lumen_override;
      if (restoredLumen) {
        const lumenRes = await fetch('/api/patients/lumen-overrides', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ override: restoredLumen }),
        });
        const lumenData = await lumenRes.json() as { override?: LumenOverride; error?: string };
        if (!lumenRes.ok) throw new Error(lumenData.error || 'History lumen restore failed');
        restoredLumen = lumenData.override || restoredLumen;
      }
      pointsRef.current = clonePoly(restored.mask_polygon);
      wallPointsRef.current = clonePoly(restored.wall_polygon || []);
      videoFrameOverridesRef.current = restored.video_frames || [];
      setPoints(pointsRef.current);
      setWallPoints(wallPointsRef.current);
      setVideoFrameOverrides(videoFrameOverridesRef.current);
      onOverrideChange(restored);
      // Restored contours must refresh report evidence images (mask overlay,
      // ROI crop, boundary curvature) even without further user edits.
      window.setTimeout(() => {
        void emitReportEvidenceImages();
      }, 400);
      if (restoredLumen) {
        lumenBoxRef.current = restoredLumen.lumen_bbox;
        lumenPolygonRef.current = restoredLumen.lumen_polygon || [];
        setLumenBox(restoredLumen.lumen_bbox);
        setLumenPolygon(restoredLumen.lumen_polygon || []);
        setLumenConfidence(restoredLumen.lumen_confidence ?? null);
        setLumenResultMeta({
          detector_backend_id: restoredLumen.detector_backend_id,
          sam_backend_id: restoredLumen.sam_backend_id,
          sam_score: restoredLumen.sam_score,
          source: restoredLumen.source,
        });
        onLumenOverrideChange?.(restoredLumen);
      }
      setHistoryOpen(true);
      setHistoryPreviewId(entry.id);
      setMessage(zh ? '已恢复完整遮罩版本，历史面板保持打开' : 'Complete mask version restored; history stays open');
      maskAuditRef.current('mask_event', {
        action: 'history_restored',
        history_entry_id: entry.id,
        displayed_on_canvas: true,
        ...summarizeMaskForAudit(restored),
        lumen_points: restoredLumen?.lumen_polygon?.length || 0,
        lumen_box_present: Boolean(restoredLumen?.lumen_bbox),
      });
      await loadMaskHistory();
    } catch (error) {
      maskAuditRef.current('error', {
        operation: 'history_restore',
        history_entry_id: entry.id,
        error: error instanceof Error ? error.message.slice(0, 240) : 'History restore failed',
      });
      setMessage(error instanceof Error ? error.message : (zh ? '历史版本恢复失败' : 'History restore failed'));
    } finally {
      setHistoryBusy(false);
    }
  }, [accountReaderId, authHeaders, emitReportEvidenceImages, historyBusy, loadMaskHistory, onLumenOverrideChange, onOverrideChange, patient, zh]);

  const toggleHistoryPanel = useCallback(() => {
    const nextOpen = !historyOpen;
    setHistoryOpen(nextOpen);
    maskAuditRef.current('mask_event', {
      action: nextOpen ? 'history_opened' : 'history_closed',
      history_loaded: nextOpen,
      displayed_on_canvas: false,
    });
    if (nextOpen) {
      setHistoryPreviewId(null);
      void loadMaskHistory();
    } else {
      setHistoryPreviewId(null);
    }
  }, [historyOpen, loadMaskHistory]);

  const toggleHistoryPreview = useCallback((entry: MaskHistoryEntry) => {
    const previewing = historyPreviewId === entry.id;
    setHistoryPreviewId(previewing ? null : entry.id);
    maskAuditRef.current('mask_event', {
      action: previewing ? 'history_preview_closed' : 'history_preview_opened',
      history_entry_id: entry.id,
      displayed_on_canvas: !previewing,
      ...summarizeMaskForAudit(entry.override),
    });
  }, [historyPreviewId]);

  const handleSave = async () => {
    recordDoctorOp('lesion_edit', {
      layer: 'lesion',
      operation: 'save_edit',
      tool: 'save_edit',
      point_count: pointsRef.current.length,
    });
    const ok = await persistOverride('manual_save');
    if (ok) {
      // Doctor action record: compact edit save with full-video frame count.
      recordDoctorWorkflowStep(
        'save_edit',
        mediaMode === 'video' ? '保存编辑（含全部视频帧轮廓）' : '保存编辑',
        'completed',
        {
          output: {
            video_frames: videoFrameOverridesRef.current.length,
            lesion_points: pointsRef.current.length,
            lumen_points: lumenPolygonRef.current.length,
          },
        },
      );
      setMessage(
        zh
          ? (mediaMode === 'video' && videoFrameOverridesRef.current.length
            ? `已保存编辑：${videoFrameOverridesRef.current.length} 帧轮廓 + 操作记录`
            : '已保存编辑并记录操作')
          : (mediaMode === 'video' && videoFrameOverridesRef.current.length
            ? `Edit saved: ${videoFrameOverridesRef.current.length} frame masks + action log`
            : 'Edit saved with action log'),
      );
    }
  };

  const handleClear = async () => {
    if (!patient) return;
    recordDoctorOp('lesion_edit', { layer: 'lesion', operation: 'clear_edit', tool: 'reset' });
    setSaving(true);
    try {
      await fetch(
        `/api/patients/mask-overrides?patientId=${encodeURIComponent(patient.patient_id)}&frameId=${encodeURIComponent(patient.id)}`,
        { method: 'DELETE' },
      );
      generatedLesionRef.current = [];
      setPoints([]);
      pointsRef.current = [];
      setWallPoints([]);
      wallPointsRef.current = [];
      setViewFocusBox(null);
      setViewFocusMode(null);
      videoFrameOverridesRef.current = [];
      setVideoFrameOverrides([]);
      clearSamPrompts();
      setNnInteractiveMode(false);
      nnInteractiveSessionRef.current = { key: '', id: '', initialized: false };
      setSimplePromptBox(null);
      setLayerResult(null);
      onImagingAssist?.(null);
      onOverrideChange(null);
      maskAuditRef.current('mask_event', {
        action: 'mask_cleared',
        success: true,
        displayed_on_canvas: false,
      });
      setMessage(zh ? '已清除覆盖，将使用模型分割' : 'Override cleared; model seg will be used');
    } catch (err) {
      maskAuditRef.current('error', {
        operation: 'mask_clear',
        error: err instanceof Error ? err.message.slice(0, 240) : 'Clear failed',
      });
      setMessage(err instanceof Error ? err.message : 'Clear failed');
    } finally {
      setSaving(false);
    }
  };

  const openEditor = useCallback((opts?: { videoSam?: boolean; sam?: boolean; keyframes?: boolean }) => {
    if (opts?.videoSam) setPendingOpenVideoSam(true);
    if (opts?.keyframes) setPendingKeyframeRequest(true);
    if (opts?.videoSam || opts?.keyframes) setMediaMode('video');
    if (opts?.sam && !opts?.videoSam && !opts?.keyframes) setMediaMode('image');
    const useSam = Boolean(opts?.videoSam || opts?.sam);
    setMode(useSam ? 'sam' : 'soft');
    clearSamPrompts();
    setNnInteractiveMode(false);
    nnInteractiveSessionRef.current = { key: '', id: '', initialized: false };
    setSamBoxPreview(null);
    setSimplePromptBox(null);
    // Keep dense contours — soft-deform uses sparse control handles (direction_demo)
    setOpen(true);
    maskAuditRef.current('mask_event', {
      action: 'editor_opened',
      mode: useSam ? 'sam' : 'soft',
      media_mode: opts?.videoSam || opts?.keyframes ? 'video' : opts?.sam ? 'image' : 'current',
      keyframe_request: Boolean(opts?.keyframes),
    });
    setMessage(
      useSam
        ? (zh
          ? '点击画面标记关注区域，系统返回当前帧结果'
          : 'Click the frame to get the current-frame result')
        : (zh
          ? '拖橙/绿控制点软变形边界（同人机互助 HTML）; 硬拖/加点/删点为辅助'
          : 'Drag orange/green handles to soft-deform (same as HTML demo)'),
    );
  }, [clearSamPrompts, zh]);

  // AssistHub / external open request (additive; floating buttons unchanged)
  useEffect(() => {
    const handler = (event: Event) => {
      const detail = (event as CustomEvent<{ videoSam?: boolean; sam?: boolean; keyframes?: boolean }>).detail;
      openEditor(detail || { sam: true });
    };
    window.addEventListener('gastric:open-boundary-edit', handler);
    return () => window.removeEventListener('gastric:open-boundary-edit', handler);
  }, [openEditor]);

  const simplifyActiveLayer = useCallback(() => {
    const src = activeLayer === 'wall' ? wallPoints : points;
    if (src.length < 8) return;
    pushEditUndo();
    const next = prepareEditableContour(
      src,
      activeLayer === 'wall' ? WALL_SIMPLIFY_TARGET : LESION_SIMPLIFY_TARGET,
    );
    if (activeLayer === 'wall') {
      wallPointsRef.current = next;
      setWallPoints(next);
    } else {
      pointsRef.current = next;
      setPoints(next);
    }
    setMode('soft');
    setMessage(
      zh
        ? `已弧长重采样为 ${next.length} 点, 控制手柄 ${controlIndices(next.length, activeLayer === 'wall' ? WALL_CTRL_COUNT : LESION_CTRL_COUNT).length} 个`
        : `Resampled to ${next.length} pts with sparse control handles`,
    );
  }, [activeLayer, points, wallPoints, zh, pushEditUndo]);

  if (!patient) return null;

  const modal = open ? (
        <div className={inline
          ? 'pointer-events-auto absolute inset-0 z-[120] flex min-h-0 min-w-0 items-stretch justify-stretch overflow-hidden bg-[#080b0f]'
          : 'pointer-events-auto fixed inset-0 z-[150000] flex items-center justify-center bg-black/85 p-3 backdrop-blur-sm'}>
          <div className={inline
            ? 'relative flex h-full w-full min-h-0 min-w-0 flex-col overflow-hidden bg-black'
            : 'flex h-[min(94vh,920px)] w-[min(1380px,98vw)] flex-col overflow-hidden rounded-2xl border border-cyan-400/25 bg-slate-950 shadow-2xl'}>
            <div className={`workbench-toolbar flex min-w-0 flex-wrap items-center justify-between gap-3 border-b border-white/10 bg-black px-3 ${simpleVideoMode ? 'py-1.5' : 'py-3'}`}>
              <div className="min-w-0 flex-1">
                <div className="flex min-w-0 items-center gap-2">
                  <div className="min-w-0 truncate text-sm font-bold text-slate-100">
                    {simpleVideoMode
                      ? (patientDisplayLabel(patient, language) || 'Case')
                      : (zh ? (mediaMode === 'video' ? '视频工具' : '静态图分割') : (mediaMode === 'video' ? 'Video tools' : 'Static image segmentation'))}
                  </div>
                  <CaseGoldReveal
                    patientId={patient.patient_id}
                    caseId={patient.id}
                    recordId={patient.id}
                    phase={patient.phase}
                    group={patient.group}
                    queueId={patient.queue_id}
                    available={patient.gold_available !== false}
                    knownLabel={patient.gold_five_class || null}
                    zh={zh}
                    compact
                    autoReveal
                  />
                </div>
                <div className="mt-0.5 truncate text-[10px] text-slate-500 max-md:hidden">
                  {simpleVideoMode
                    ? (zh
                      ? '先看视频，点亮「框选病灶」后拖框，当前帧即作为关键帧'
                      : 'Watch first, arm Box lesion, then drag; this frame becomes the keyframe')
                    : `${patientDisplayLabel(patient, language)}, ${zh
                      ? mediaMode === 'video'
                        ? '当前帧证据与 ROI 工具'
                        : '当前静态图，点击或框选病灶'
                      : mediaMode === 'video'
                        ? 'Current-frame evidence and ROI tools'
                        : 'Current image, click or box the lesion'}`}
                </div>
              </div>
              <div className={simpleVideoMode ? 'hidden' : 'flex min-w-0 flex-wrap items-center justify-end gap-2'}>
                  <button
                    type="button"
                    disabled={dinoBusy}
                    onClick={() => void extractDinoFeatures()}
                    className="rounded-lg border border-amber-300/50 bg-amber-400/10 px-2.5 py-1.5 text-[11px] font-semibold text-amber-100 disabled:opacity-40"
                    title={zh ? '提取当前帧区域特征' : 'Extract current-frame region features'}
                  >
                    {dinoBusy ? (zh ? '特征提取中' : 'Extracting') : dinoResult?.available ? (zh ? '区域特征 ✓' : 'Features ✓') : (zh ? '区域特征' : 'Region features')}
                  </button>
                  {!simpleVideoMode && (
                    <>
                      <button
                        type="button"
                        disabled={undoLen <= 0}
                        onClick={undoEdit}
                        className="rounded-lg border border-white/15 px-2.5 py-1.5 text-[11px] text-slate-200 disabled:opacity-40"
                      >
                        {zh ? `撤销 (${undoLen})` : `Undo (${undoLen})`}
                      </button>
                      <button
                        type="button"
                        disabled={!hasOriginal}
                        onClick={restoreOriginal}
                        className="rounded-lg border border-white/15 px-2.5 py-1.5 text-[11px] text-slate-200 disabled:opacity-40"
                      >
                        {zh ? '恢复原始' : 'Restore'}
                      </button>
                    </>
                  )}
                  {!inline && (
                    <button
                      type="button"
                      onClick={() => setOpen(false)}
                      className="rounded-lg border border-white/15 p-2 text-slate-300 hover:bg-white/5"
                      aria-label={zh ? '关闭分割编辑器' : 'Close segmentation editor'}
                    >
                      <X size={16} />
                    </button>
                  )}
              </div>
              {inline && (
                <button
                  type="button"
                  onClick={() => setOpen(false)}
                  className="flex items-center gap-1.5 rounded-lg border border-white/15 px-2.5 py-1.5 text-[11px] text-slate-300 hover:bg-white/5"
                  aria-label={zh ? '收起分割编辑器' : 'Close segmentation editor'}
                >
                  <X size={14} />
                  {zh ? '收起' : 'Close'}
                </button>
              )}
            </div>

            {(simpleVideoMode || mediaMode === 'video') && open ? (
              <DoctorKeyframeStrip
                zh={zh}
                keyframes={doctorKeyframes}
                activeId={activeDoctorKeyframeId}
                fps={videoFps}
                onSelect={(kf) => { void selectDoctorKeyframe(kf); }}
                onRemove={removeDoctorKeyframe}
                onMarkDeepest={markDoctorKeyframeDeepest}
              />
            ) : null}
            {analysisContourUnrefined ? (
              <div className="border-b border-amber-400/30 bg-amber-500/10 px-3 py-1.5 text-[10px] text-amber-100">
                {uncorrectedContourNote(zh)}
              </div>
            ) : null}

            {!simpleVideoMode && (
            <div className="workbench-toolbar flex flex-wrap items-center gap-2 border-b border-white/10 px-4 py-2">
              {([
                ['hard', zh ? '拖点' : 'Drag', Pencil],
                ['brush', zh ? '涂抹' : 'Brush', Brush],
                ['polygon', zh ? '多边形' : 'Polygon', Pentagon],
                ['soft', zh ? '软变形' : 'Soft', MousePointer2],
                ['add', zh ? '加点' : 'Add', Plus],
                ['delete', zh ? '删点' : 'Delete', Eraser],
                ['sam', zh ? '标记关注区域' : 'Mark region', Sparkles],
              ] as const).map(([id, label, Icon]) => (
                <button
                  key={id}
                  type="button"
                  disabled={id === 'sam' && samAvailable === false}
                  onClick={() => {
                    setMode(id);
                    setNnInteractiveMode(false);
                    nnInteractiveRequestRef.current += 1;
                    setNnInteractiveBusy(false);
                    nnInteractiveSessionRef.current = { key: '', id: '', initialized: false };
                    if (id === 'polygon') {
                      setPolygonDraft([]);
                      setMessage(zh ? '单击加点，双击或点回起点闭合多边形' : 'Click to add vertices; double-click or click near start to close');
                    } else if (id === 'brush') {
                      setMessage(zh ? '沿轮廓涂抹微调；按住拖动推拉边界' : 'Brush along the contour to nudge the boundary');
                    } else if (id === 'hard') {
                      setMessage(zh ? '拖动轮廓点，或在边上点击插入点' : 'Drag contour points, or click an edge to insert');
                    } else if (id === 'sam') {
                      setSimplePromptMode('point');
                      setActiveSamPromptLabel('positive');
                      setMessage(
                        zh
                          ? '点击画面标记关注区域'
                          : 'Click the frame to mark a region',
                      );
                    }
                  }}
                  className={`flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-[11px] ${
                    mode === id
                      ? 'border-cyan-400/50 bg-cyan-500/20 text-cyan-100'
                      : 'border-white/10 text-slate-300 hover:bg-white/5'
                  } disabled:opacity-40`}
                >
                  <Icon size={13} />
                  {label}
                </button>
              ))}
              <button
                type="button"
                disabled={getCurrentTrackedPolygon().length < 3 || nnInteractiveBusy}
                onClick={() => {
                  activateNnInteractive('lesion');
                }}
                className={`flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-[11px] disabled:opacity-40 ${
                  nnInteractiveMode
                    ? 'border-lime-300/70 bg-lime-500/30 text-lime-50'
                    : 'border-lime-400/40 bg-lime-500/15 text-lime-100 hover:bg-lime-500/25'
                }`}
                title={zh ? '用当前病灶边界启动辅助精修' : 'Refine the current lesion boundary'}
              >
                {nnInteractiveBusy ? <Loader2 size={13} className="animate-spin" /> : <Sparkles size={13} />}
                {nnInteractiveBusy ? (zh ? '边界精修中' : 'Refining') : (zh ? '边界精修' : 'Refine boundary')}
              </button>
              <div className="flex items-center gap-1 rounded-lg border border-emerald-400/25 bg-emerald-500/5 px-1 py-0.5">
                <span className="px-1 text-[10px] font-semibold text-emerald-200">nnInteractive</span>
                <button
                  type="button"
                  onClick={() => {
                    setActiveSamPromptLabel('positive');
                    activateActiveSamPrompt('point');
                  }}
                  className={`rounded px-1.5 py-1 text-[10px] ${activeSamPromptLabel === 'positive' ? 'bg-emerald-400/25 text-emerald-50' : 'text-slate-400 hover:bg-white/10'}`}
                >
                  {zh ? '正点' : '+ Point'}
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setActiveSamPromptLabel('negative');
                    activateActiveSamPrompt('point');
                  }}
                  className={`rounded px-1.5 py-1 text-[10px] ${activeSamPromptLabel === 'negative' ? 'bg-rose-400/25 text-rose-50' : 'text-slate-400 hover:bg-white/10'}`}
                >
                  {zh ? '负点' : '- Point'}
                </button>
                <button
                  type="button"
                  disabled={nnInteractiveAvailable !== true || nnInteractiveBusy}
                  onClick={() => activateActiveSamPrompt('scribble')}
                  className={`rounded px-1.5 py-1 text-[10px] ${simplePromptMode === 'scribble' ? 'bg-emerald-400/25 text-emerald-50' : 'text-slate-400 hover:bg-white/10'}`}
                >
                  {zh ? '涂鸦' : 'Scribble'}
                </button>
                <button
                  type="button"
                  disabled={nnInteractiveAvailable !== true || nnInteractiveBusy}
                  onClick={() => activateActiveSamPrompt('lasso')}
                  className={`rounded px-1.5 py-1 text-[10px] ${simplePromptMode === 'lasso' ? 'bg-cyan-400/25 text-cyan-50' : 'text-slate-400 hover:bg-white/10'}`}
                >
                  {zh ? '套索' : 'Lasso'}
                </button>
                {promptStrokes.length ? (
                  <span className="px-1 text-[9px] text-slate-500">{promptStrokes.length}</span>
                ) : null}
              </div>
              {mode === 'sam' && (
                <button
                  type="button"
                  onClick={() => {
                    clearSamPrompts();
                    setNnInteractiveMode(false);
                    setNnInteractiveTarget('lesion');
                    nnInteractiveSessionRef.current = { key: '', id: '', initialized: false };
                    setMessage(zh ? '已清除关注标记' : 'Region markers cleared');
                  }}
                  className="rounded-lg border border-rose-400/40 bg-rose-500/10 px-2.5 py-1.5 text-[11px] text-rose-100"
                >
                  {zh
                    ? `清除提示 (${samClicks.length + promptStrokes.length})`
                    : `Clear prompts (${samClicks.length + promptStrokes.length})`}
                </button>
              )}
              <button
                type="button"
                disabled={activePoints.length < 8}
                onClick={simplifyActiveLayer}
                className="rounded-lg border border-amber-400/40 bg-amber-500/10 px-2.5 py-1.5 text-[11px] text-amber-100 disabled:opacity-40"
                title={zh ? '弧长重采样稠密轮廓（不砍成稀少折线）' : 'Arc-length resample dense contour'}
              >
                {zh ? '重采样' : 'Resample'}
              </button>
              <div className="h-5 w-px bg-white/10" />
              <button
                type="button"
                onClick={() => {
                  setActiveLayer('wall');
                  recordDoctorOpRef.current('layer_switch', {
                    video_time_sec: videoRef.current?.currentTime ?? null,
                    layer: 'wall',
                  });
                }}
                className={`rounded-lg border px-2.5 py-1.5 text-[11px] ${
                  activeLayer === 'wall'
                    ? 'border-orange-400/50 bg-orange-500/20 text-orange-100'
                    : 'border-white/10 text-slate-300'
                }`}
              >
                {zh ? '胃壁' : 'Wall'} ({wallPoints.length})
              </button>
              <button
                type="button"
                disabled={points.length < 3}
                onClick={() => startWallExtensionTool()}
                className={`flex items-center gap-1 rounded-lg border px-2.5 py-1.5 text-[11px] ${
                  wallPickMode
                    ? 'border-amber-300 bg-amber-400/25 text-amber-50'
                    : 'border-amber-400/40 bg-amber-500/10 text-amber-100'
                } disabled:opacity-40`}
                title={zh ? '点两侧看得见的胃壁，沿突破方向接过去；虚线可拖改。再点一次则自动接。' : 'Click the two visible flanks, then join through the breach. Drag the dashes. Click again to auto-join.'}
              >
                <Spline size={13} />
                {zh ? (wallPickMode ? '自动接 / 点两侧' : '延长胃壁') : (wallPickMode ? 'Auto-join / click flanks' : 'Extend wall')}
              </button>
              <button
                type="button"
                onClick={() => startWallPaintTool()}
                className={`flex items-center gap-1 rounded-lg border px-2.5 py-1.5 text-[11px] ${
                  wallPaintMode
                    ? 'border-amber-300 bg-amber-400/25 text-amber-50'
                    : 'border-amber-400/40 bg-amber-500/10 text-amber-100'
                }`}
                title={paintLineHint(wallLayerTarget, zh)}
              >
                <Pencil size={13} />
                {paintToolLabel(wallPaintMode, zh)}
              </button>
              <button
                type="button"
                onClick={() => {
                  setActiveLayer('lesion');
                  recordDoctorOpRef.current('layer_switch', {
                    video_time_sec: videoRef.current?.currentTime ?? null,
                    layer: 'lesion',
                  });
                }}
                className={`rounded-lg border px-2.5 py-1.5 text-[11px] ${
                  activeLayer === 'lesion'
                    ? 'border-cyan-400/50 bg-cyan-500/20 text-cyan-100'
                    : 'border-white/10 text-slate-300'
                }`}
              >
                {zh ? '病灶' : 'Lesion'} ({points.length})
              </button>
              <button
                type="button"
                disabled={points.length < 3 && !layerResult}
                onClick={() => {
                  window.dispatchEvent(new CustomEvent('gastric:open-wall-layers', {
                    detail: { open: !wallAnalysisOpen },
                  }));
                }}
                className={`flex items-center gap-1 rounded-lg border px-2.5 py-1.5 text-[11px] ${
                  wallAnalysisOpen
                    ? 'border-emerald-400/50 bg-emerald-500/20 text-emerald-100'
                    : 'border-white/10 text-slate-300 hover:bg-white/5'
                } disabled:opacity-40`}
              >
                <Layers size={13} />
                    {wallAnalysisOpen ? (zh ? '收起壁层' : 'Close layers') : (zh ? '壁层' : 'Wall layers')}
              </button>
              <div className="h-5 w-px bg-white/10" />
              <button
                type="button"
                disabled={lumenBusy || !patient}
                onClick={() => {
                  prepareLumenDetection();
                  void detectLumen();
                }}
                className="flex items-center gap-1.5 rounded-lg border border-fuchsia-400/40 bg-fuchsia-500/10 px-2.5 py-1.5 text-[11px] text-fuchsia-100 disabled:opacity-40"
                title={zh ? 'YOLO 检测当前帧胃腔框' : 'YOLO lumen box on current frame'}
              >
                {lumenBusy ? <Loader2 size={13} className="animate-spin" /> : <ScanSearch size={13} />}
                {zh ? '检测胃腔' : 'Detect lumen'}
              </button>
              <button
                type="button"
                onClick={toggleLumenBoxEdit}
                className={`flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-[11px] ${
                  lumenEditMode
                    ? 'border-fuchsia-400/50 bg-fuchsia-500/20 text-fuchsia-100'
                    : 'border-white/10 text-slate-300'
                }`}
              >
                <Pencil size={13} />
                {lumenEditMode ? (zh ? '完成调整' : 'Done') : (zh ? '调胃腔框' : 'Edit lumen')}
              </button>
              <button
                type="button"
                disabled={!lumenBox || lumenSamBusy}
                onClick={() => void segmentLumenWithSam31()}
                className="flex items-center gap-1.5 rounded-lg border border-fuchsia-400/40 bg-fuchsia-500/10 px-2.5 py-1.5 text-[11px] text-fuchsia-100 disabled:opacity-40"
                title={zh ? '以当前胃腔框生成胃腔轮廓' : 'Segment lumen from current box'}
              >
                {lumenSamBusy ? <Loader2 size={13} className="animate-spin" /> : <Sparkles size={13} />}
                {zh ? '分割胃腔' : 'Segment lumen'}
              </button>
              <button
                type="button"
                disabled={lumenSaving || (!lumenBox && lumenPolygon.length < 3)}
                onClick={() => void handleSaveLumen()}
                className="flex items-center gap-1.5 rounded-lg border border-fuchsia-400/40 bg-fuchsia-500/15 px-2.5 py-1.5 text-[11px] text-fuchsia-100 disabled:opacity-40"
              >
                {lumenSaving ? <Loader2 size={13} className="animate-spin" /> : <Save size={13} />}
                {zh ? '保存胃腔' : 'Save lumen'}
              </button>
              <div className="h-5 w-px bg-white/10" />
              <button
                type="button"
                onClick={() => setMediaMode('image')}
                className={`rounded-lg border px-2.5 py-1.5 text-[11px] ${
                  mediaMode === 'image'
                    ? 'border-cyan-400/50 bg-cyan-500/20 text-cyan-100'
                    : 'border-white/10 text-slate-300'
                }`}
              >
                {zh ? '静图' : 'Image'}
              </button>
              <button
                type="button"
                onClick={() => {
                  if (videos.length) openPatientVideoSam();
                  else setMediaMode('video');
                }}
                className={`flex items-center gap-1 rounded-lg border px-2.5 py-1.5 text-[11px] ${
                  mediaMode === 'video'
                    ? 'border-violet-400/50 bg-violet-500/20 text-violet-100'
                    : 'border-white/10 text-slate-300'
                }`}
              >
                <Video size={13} />
                {zh ? `视频工具${videos.length ? ` (${videos.length})` : ''}` : `Video tools${videos.length ? ` (${videos.length})` : ''}`}
              </button>
              <div className="ml-auto flex items-center gap-2 text-[10px] text-slate-400">
                <span>{zh ? '模型' : 'Model'}</span>
                <select
                  value={segmentationModel}
                  onChange={(e) => {
                    const next = e.target.value as LesionSegmentationModel;
                    if (next === 'sam31' || next === 'dinov3') chooseLesionSegModel(next);
                    else setSegmentationModel(next);
                  }}
                  className="rounded border border-white/15 bg-black/40 px-2 py-1 text-[11px] text-slate-200"
                  aria-label={zh ? '静态分割模型' : 'Static segmentation model'}
                >
                  <option value="sabm_sam2_guided">{zh ? '引导式分割' : 'Guided segmentation'}</option>
                  <option value="sam31">SAM 3.1</option>
                  <option value="dinov3">DINO</option>
                  <option value="convnext">{zh ? '卷积分割' : 'Conv segmentation'}</option>
                </select>
                <span>ROI</span>
                <select
                  value={roiMode}
                  onChange={(e) => setRoiMode(e.target.value as typeof roiMode)}
                  className="rounded border border-white/15 bg-black/40 px-2 py-1 text-[11px] text-slate-200"
                >
                  <option value="predicted">{zh ? '编辑框' : 'Edited bbox'}</option>
                  <option value="doctor">{zh ? '磁盘医生 ROI' : 'Disk doctor ROI'}</option>
                  <option value="auto">Auto</option>
                </select>
              </div>
            </div>
            )}

            {mediaMode === 'video' && (
              <>
              {/* Simple video mode keeps the left and right rails as the single tool surface. */}
              <div className={simpleVideoMode ? 'hidden' : ''}>
              {simpleVideoMode ? (
                <>
                  {simpleToolsOpen && (
                    <div className="workbench-toolbar flex min-w-0 flex-wrap items-center gap-1.5 border-b border-white/10 bg-black/80 px-4 py-2">
                      <div className="flex min-w-0 flex-wrap items-center gap-1.5">
                        {onUnifiedAgentRun ? (
                          <button
                            type="button"
                            disabled={!videoUrl || workflowBusy || unifiedAgentBusy}
                            onClick={() => void runDoctorWorkflow()}
                            className="flex items-center gap-1.5 rounded-lg border border-amber-300/50 bg-amber-400/15 px-2.5 py-1.5 text-[11px] font-semibold text-amber-100 hover:bg-amber-400/25 disabled:opacity-40"
                            title={zh ? '按医生轨迹自动完成检测、精修和胃腔轮廓；跟踪需手动同时开' : 'Auto-run detection, refinement, and lumen contour; start joint tracking manually'}
                          >
                            {workflowBusy ? <Loader2 size={13} className="animate-spin" /> : <Workflow size={13} />}
                            {workflowBusy ? (workflowStepLabel || (zh ? '医生式流程中' : 'Doctor workflow')) : (zh ? '医生式全流程' : 'Doctor workflow')}
                          </button>
                        ) : null}
                        <span className="mr-1 hidden text-[10px] font-semibold uppercase tracking-wide text-cyan-300/80 sm:inline">
                          {zh ? '病灶' : 'Lesion'}
                        </span>
                        <button
                          type="button"
                          onClick={() => {
                            if (lesionBoxArmed) {
                              armLesionBox(false);
                              setMessage(zh ? '已取消框选病灶' : 'Box lesion cancelled');
                              return;
                            }
                            enterSimpleBoxPrompt();
                          }}
                          className={`flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-[11px] ${
                            lesionBoxArmed
                              ? 'border-cyan-200 bg-cyan-400/50 text-white ring-2 ring-cyan-100'
                              : 'border-white/15 bg-white/5 text-slate-300 hover:bg-white/10'
                          }`}
                        >
                          <ScanLine size={13} />
                          {zh ? '框选病灶' : 'Box lesion'}
                        </button>
                        <button
                          type="button"
                          disabled={!videoUrl || lesionAutoBusy || workflowBusy}
                          onClick={() => void autoDetectLesion()}
                          className="flex items-center gap-1.5 rounded-lg border border-cyan-300/40 bg-cyan-500/10 px-2.5 py-1.5 text-[11px] text-cyan-100 hover:bg-cyan-500/20 disabled:opacity-40"
                          title={zh ? '用全图候选模型先定位病灶，再用正负点确认' : 'Find a full-frame lesion candidate, then confirm it with positive and negative points'}
                        >
                          {lesionAutoBusy ? <Loader2 size={13} className="animate-spin" /> : <ScanSearch size={13} />}
                          {lesionAutoBusy ? (zh ? '寻找中' : 'Finding') : (zh ? '自动找病灶' : 'Auto-find lesion')}
                        </button>
                        <button
                          type="button"
                          disabled={getCurrentTrackedPolygon().length < 3 || nnInteractiveBusy}
                          onClick={() => {
                            activateNnInteractive('lesion');
                          }}
                          className={`flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-[11px] disabled:opacity-40 ${
                            nnInteractiveMode
                              ? 'border-lime-300/70 bg-lime-500/30 text-lime-50'
                              : 'border-lime-400/40 bg-lime-500/15 text-lime-100 hover:bg-lime-500/25'
                          }`}
                          title={zh ? '用当前病灶边界启动辅助精修' : 'Refine the current lesion boundary'}
                        >
                          {nnInteractiveBusy ? <Loader2 size={13} className="animate-spin" /> : <Sparkles size={13} />}
                          {nnInteractiveBusy ? (zh ? '边界精修中' : 'Refining') : (zh ? '边界精修' : 'Refine boundary')}
                        </button>
                        {nnInteractiveAvailable !== null ? (
                          <span
                            className={`rounded-md border px-2 py-1 text-[10px] ${
                              nnInteractiveAvailable
                                ? 'border-lime-300/30 bg-lime-500/10 text-lime-200'
                                : 'border-amber-300/25 bg-amber-500/10 text-amber-200'
                            }`}
                            title={nnInteractiveAvailable
                              ? (zh ? '边界辅助服务已连接' : 'Boundary assistance is ready')
                              : (zh ? '请先启动边界辅助服务' : 'Start the boundary assistance service first')}
                          >
                            {nnInteractiveAvailable
                              ? (zh ? '辅助已连接' : 'Assistance ready')
                              : (zh ? '辅助未连接' : 'Assistance offline')}
                          </span>
                        ) : null}
                        <div className="flex items-center gap-1 rounded-lg border border-emerald-400/25 bg-emerald-500/5 px-1 py-0.5">
                          <span className="px-1 text-[10px] font-semibold text-emerald-200">nnInteractive</span>
                          <button
                            type="button"
                            onClick={() => {
                              setActiveSamPromptLabel('positive');
                              activateActiveSamPrompt('point');
                            }}
                            className={`rounded px-1.5 py-1 text-[10px] ${simplePromptMode === 'point' && activeSamPromptLabel === 'positive' && nnInteractiveMode ? 'bg-emerald-400/25 text-emerald-50' : 'text-slate-400 hover:bg-white/10'}`}
                          >
                            {zh ? '正点' : '+ Point'}
                          </button>
                          <button
                            type="button"
                            onClick={() => {
                              setActiveSamPromptLabel('negative');
                              activateActiveSamPrompt('point');
                            }}
                            className={`rounded px-1.5 py-1 text-[10px] ${simplePromptMode === 'point' && activeSamPromptLabel === 'negative' && nnInteractiveMode ? 'bg-rose-400/25 text-rose-50' : 'text-slate-400 hover:bg-white/10'}`}
                          >
                            {zh ? '负点' : '- Point'}
                          </button>
                          <button
                            type="button"
                            disabled={nnInteractiveAvailable !== true || nnInteractiveBusy}
                            onClick={() => activateActiveSamPrompt('scribble')}
                            className={`rounded px-1.5 py-1 text-[10px] ${simplePromptMode === 'scribble' && nnInteractiveMode ? 'bg-emerald-400/25 text-emerald-50' : 'text-slate-400 hover:bg-white/10'}`}
                          >
                            {zh ? '涂鸦' : 'Scribble'}
                          </button>
                          <button
                            type="button"
                            disabled={nnInteractiveAvailable !== true || nnInteractiveBusy}
                            onClick={() => activateActiveSamPrompt('lasso')}
                            className={`rounded px-1.5 py-1 text-[10px] ${simplePromptMode === 'lasso' && nnInteractiveMode ? 'bg-cyan-400/25 text-cyan-50' : 'text-slate-400 hover:bg-white/10'}`}
                          >
                            {zh ? '套索' : 'Lasso'}
                          </button>
                        </div>
                        <div className="flex items-center gap-1 rounded-lg border border-emerald-400/30 bg-emerald-500/10 p-0.5">
                          <button
                            type="button"
                            onClick={() => setRefineTarget('lesion')}
                            className={`rounded px-1.5 py-1 text-[10px] ${refineTarget === 'lesion' ? 'bg-emerald-400/30 text-emerald-50' : 'text-slate-400 hover:bg-white/10'}`}
                          >
                            {zh ? '病灶' : 'Lesion'}
                          </button>
                          <button
                            type="button"
                            onClick={() => {
                              setRefineTarget('lumen');
                              ensureLumenPolygonForRefine();
                            }}
                            className={`rounded px-1.5 py-1 text-[10px] ${refineTarget === 'lumen' ? 'bg-fuchsia-400/30 text-fuchsia-50' : 'text-slate-400 hover:bg-white/10'}`}
                          >
                            {zh ? '胃腔' : 'Lumen'}
                          </button>
                        </div>
                        <button
                          type="button"
                          onClick={() => activateRefineTool('brush')}
                          className={`flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-[11px] ${
                            (mode === 'hard' || mode === 'brush' || simpleEditMode) && mode !== 'polygon' && !lumenSculptMode
                              ? 'border-emerald-300/70 bg-emerald-500/35 text-emerald-50'
                              : 'border-emerald-400/40 bg-emerald-500/15 text-emerald-100 hover:bg-emerald-500/25'
                          }`}
                          title={zh ? '拖线上任意处' : 'Drag any point on the line'}
                        >
                          <Pencil size={13} />
                          {zh ? '拖点' : 'Drag'}
                        </button>
                        <button
                          type="button"
                          onClick={() => activateRefineTool('brush')}
                          className={`flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-[11px] ${
                            mode === 'brush'
                              ? 'border-amber-300/70 bg-amber-500/35 text-amber-50'
                              : 'border-amber-400/40 bg-amber-500/15 text-amber-100 hover:bg-amber-500/25'
                          }`}
                        >
                          <Brush size={13} />
                          {zh ? '涂抹' : 'Brush'}
                        </button>
                        <button
                          type="button"
                          onClick={() => activateRefineTool('polygon')}
                          className={`flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-[11px] ${
                            mode === 'polygon'
                              ? 'border-sky-300/70 bg-sky-500/35 text-sky-50'
                              : 'border-sky-400/40 bg-sky-500/15 text-sky-100 hover:bg-sky-500/25'
                          }`}
                        >
                          <Pentagon size={13} />
                          {zh ? '多边形' : 'Polygon'}
                        </button>
                        <button
                          type="button"
                          disabled={saving}
                          onClick={() => void handleClear()}
                          className="flex items-center gap-1.5 rounded-lg border border-slate-400/35 bg-slate-500/15 px-2.5 py-1.5 text-[11px] text-slate-200 hover:bg-slate-500/25 disabled:opacity-40"
                        >
                          <RotateCcw size={13} />
                          {zh ? '重新画' : 'Redraw'}
                        </button>
                        <button
                          type="button"
                          disabled={points.length < 3 && !lumenBox && lumenPolygon.length < 3}
                          onClick={toggleZoomRoi}
                          className={`flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-[11px] disabled:opacity-40 ${
                            viewFocusBox
                              ? 'border-cyan-300/70 bg-cyan-500/35 text-cyan-50'
                              : 'border-indigo-400/40 bg-indigo-500/15 text-indigo-100 hover:bg-indigo-500/25'
                          }`}
                          title={zh ? '放大至病灶/胃腔 ROI' : 'Zoom to lesion/lumen ROI'}
                        >
                          <ZoomIn size={13} />
                          {viewFocusBox ? (zh ? '退出放大' : 'Exit zoom') : (zh ? '放大 ROI' : 'Zoom ROI')}
                        </button>
                        <button
                          type="button"
                          disabled={!overlapFocus}
                          onClick={toggleOverlapZoom}
                          className={`flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-[11px] disabled:opacity-40 ${
                            viewFocusMode === 'overlap'
                              ? 'border-amber-300/70 bg-amber-500/35 text-amber-50'
                              : 'border-amber-400/40 bg-amber-500/15 text-amber-100 hover:bg-amber-500/25'
                          }`}
                          title={zh ? '只放大病灶与胃腔轮廓的交叠/接触局部' : 'Zoom only to the lesion-lumen overlap or contact region'}
                        >
                          <ScanSearch size={13} />
                          {viewFocusMode === 'overlap' ? (zh ? '退出交叠放大' : 'Exit overlap') : (zh ? '放大交叠' : 'Zoom overlap')}
                        </button>
                      </div>

                      <div className="flex min-w-0 flex-wrap items-center justify-end gap-1.5">
                        <span className="mr-1 hidden text-[10px] font-semibold uppercase tracking-wide text-fuchsia-300/80 sm:inline">
                          {zh ? '胃腔 / 分析' : 'Lumen / analysis'}
                        </span>
                        <button
                          type="button"
                          disabled={lumenBusy || !patient}
                          onClick={() => {
                            prepareLumenDetection();
                            void detectLumen();
                          }}
                          className="flex items-center gap-1.5 rounded-lg border border-fuchsia-400/40 bg-fuchsia-500/10 px-2.5 py-1.5 text-[11px] text-fuchsia-100 disabled:opacity-40"
                        >
                          {lumenBusy ? <Loader2 size={13} className="animate-spin" /> : <ScanSearch size={13} />}
                          {zh ? '检测胃腔' : 'Detect lumen'}
                        </button>
                        <button
                          type="button"
                          onClick={() => activateLumenSculpt('brush-add')}
                          className={`flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-[11px] ${
                            lumenSculptMode === 'brush-add'
                              ? 'border-lime-300/70 bg-lime-500/30 text-lime-50'
                              : 'border-fuchsia-400/30 bg-fuchsia-500/10 text-fuchsia-100 hover:bg-fuchsia-500/20'
                          }`}
                        >
                          <Brush size={13} />
                          {zh ? '图增' : 'Add'}
                        </button>
                        <button
                          type="button"
                          onClick={() => activateLumenSculpt('brush-sub')}
                          className={`flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-[11px] ${
                            lumenSculptMode === 'brush-sub'
                              ? 'border-rose-300/70 bg-rose-500/30 text-rose-50'
                              : 'border-fuchsia-400/30 bg-fuchsia-500/10 text-fuchsia-100 hover:bg-fuchsia-500/20'
                          }`}
                        >
                          <Eraser size={13} />
                          {zh ? '图减' : 'Erase'}
                        </button>
                        {lumenSculptMode ? (
                          <label className="flex items-center gap-1.5 rounded-lg border border-fuchsia-400/30 bg-black/40 px-2 py-1 text-[10px] text-fuchsia-100">
                            <span>{zh ? `笔刷 ${paintRadius}` : `Brush ${paintRadius}`}</span>
                            <input
                              type="range"
                              min={6}
                              max={48}
                              value={paintRadius}
                              onChange={(e) => setPaintRadius(Number(e.target.value))}
                              className="w-20 accent-fuchsia-400"
                            />
                          </label>
                        ) : null}
                        <button
                          type="button"
                          onClick={toggleLumenBoxEdit}
                          className={`flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-[11px] ${
                            lumenEditMode
                              ? 'border-fuchsia-400/50 bg-fuchsia-500/20 text-fuchsia-100'
                              : 'border-fuchsia-400/30 bg-fuchsia-500/10 text-fuchsia-100 hover:bg-fuchsia-500/20'
                          }`}
                        >
                          <Pencil size={13} />
                          {lumenEditMode ? (zh ? '完成调整' : 'Done') : (zh ? '调胃腔框' : 'Edit lumen')}
                        </button>
                        <button
                          type="button"
                          disabled={!lumenBox || lumenSamBusy}
                          onClick={() => void segmentLumenWithSam31()}
                          className="flex items-center gap-1.5 rounded-lg border border-fuchsia-400/40 bg-fuchsia-500/10 px-2.5 py-1.5 text-[11px] text-fuchsia-100 disabled:opacity-40"
                        >
                          {lumenSamBusy ? <Loader2 size={13} className="animate-spin" /> : <Sparkles size={13} />}
                          {zh ? '分割胃腔' : 'Segment lumen'}
                        </button>
                        <button
                          type="button"
                          disabled={lumenSaving || (!lumenBox && lumenPolygon.length < 3)}
                          onClick={() => void handleSaveLumen()}
                          className="flex items-center gap-1.5 rounded-lg border border-fuchsia-400/40 bg-fuchsia-500/15 px-2.5 py-1.5 text-[11px] text-fuchsia-100 disabled:opacity-40"
                        >
                          {lumenSaving ? <Loader2 size={13} className="animate-spin" /> : <Save size={13} />}
                          {zh ? '保存胃腔' : 'Save lumen'}
                        </button>
                        <div className="mx-0.5 hidden h-5 w-px bg-white/10 sm:block" />
                        <button
                          type="button"
                          disabled={points.length < 3}
                          onClick={openExplainableAnalysis}
                          className={`flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-[11px] font-semibold disabled:opacity-40 ${
                            points.length >= 3
                              ? 'border-lime-400/50 bg-lime-500/25 text-lime-50 hover:bg-lime-500/35'
                              : 'border-white/10 bg-white/5 text-slate-500'
                          }`}
                          title={zh ? '可解释性边界分析（当前帧）' : 'Explainable boundary analysis (current frame)'}
                        >
                          <Brain size={13} />
                          {zh ? '边界分析' : 'Boundary'}
                        </button>
                        <button
                          type="button"
                          disabled={points.length < 3 && !layerResult}
                          onClick={() => {
                            window.dispatchEvent(new CustomEvent('gastric:open-wall-layers', {
                              detail: { open: !wallAnalysisOpen },
                            }));
                          }}
                          className={`flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-[11px] disabled:opacity-40 ${
                            wallAnalysisOpen
                              ? 'border-orange-300/70 bg-orange-500/35 text-orange-50'
                              : 'border-orange-400/40 bg-orange-500/15 text-orange-100 hover:bg-orange-500/25'
                          }`}
                          title={zh ? '壁层' : 'Wall layers'}
                        >
                          <Layers size={13} />
                          {zh ? '壁层' : 'Wall layers'}
                        </button>
                        <button
                          type="button"
                          disabled={dinoBusy}
                          onClick={() => void extractDinoFeatures()}
                          className="flex items-center gap-1.5 rounded-lg border border-orange-400/40 bg-orange-500/15 px-2.5 py-1.5 text-[11px] text-orange-100 hover:bg-orange-500/25 disabled:opacity-40"
                        >
                          <BrainCircuit size={13} />
                          {dinoBusy ? (zh ? '特征中' : 'Features…') : (zh ? '区域特征' : 'Region features')}
                        </button>
                        <button
                          type="button"
                          disabled={samBusy || points.length < 3}
                          onClick={() => {
                            const center = polygonCentroid(points);
                            const currentBox = bboxFromPolygon(points);
                            if (center && currentBox) {
                              freezeCurrentFrame();
                              void runSamAtPoint(center, {
                                source: 'sam',
                                box: currentBox,
                                keepEditing: true,
                                stayInSam: true,
                                llmReport: true,
                              });
                            }
                          }}
                          className="flex items-center gap-1.5 rounded-lg border border-teal-400/40 bg-teal-500/15 px-2.5 py-1.5 text-[11px] text-teal-100 hover:bg-teal-500/25 disabled:opacity-40"
                        >
                          <ScanLine size={13} />
                          {samBusy ? (zh ? '分析中' : 'Analyzing') : (zh ? '结构证据' : 'Structure')}
                        </button>
                        {onUnifiedAgentRun ? (
                          <button
                            type="button"
                            disabled={!videoUrl || unifiedAgentBusy}
                            onClick={() => void runContourAnchoredAssist()}
                            className="flex items-center gap-1.5 rounded-lg border border-sky-400/40 bg-sky-500/15 px-2.5 py-1.5 text-[11px] text-sky-100 hover:bg-sky-500/25 disabled:opacity-40"
                          >
                            <Sparkles size={13} />
                            {unifiedAgentBusy || assistOverlayOpen ? (zh ? '分析中' : 'Running') : (zh ? '辅助分析' : 'Assist')}
                          </button>
                        ) : null}
                        <button
                          type="button"
                          onClick={() => setSimpleToolsOpen(false)}
                          className="flex items-center gap-1.5 rounded-lg border border-white/10 px-2.5 py-1.5 text-[11px] text-slate-400 hover:bg-white/5"
                          title={zh ? '隐藏工具栏' : 'Hide tools'}
                        >
                          <PanelTop size={13} />
                          {zh ? '收起' : 'Hide'}
                        </button>
                      </div>
                    </div>
                  )}
                  {!simpleToolsOpen && (
                    <button
                      type="button"
                      onClick={() => setSimpleToolsOpen(true)}
                      className="flex items-center gap-1.5 border-b border-white/10 bg-black/80 px-3 py-1.5 text-[11px] text-slate-300"
                    >
                      <PanelTop size={13} />
                      {zh ? '工具栏' : 'Tools'}
                    </button>
                  )}
                </>
              ) : (
              <div className="flex flex-wrap items-center gap-2 border-b border-white/10 bg-black/80 px-4 py-2">
                <select
                  value={videoUrl}
                  onChange={(e) => {
                    setVideoUrl(e.target.value);
                    setIsPlaying(false);
                  }}
                  className="max-w-[280px] rounded border border-white/15 bg-black/40 px-2 py-1 text-[11px] text-slate-200"
                >
                  <option value="">{zh ? '选择视频…' : 'Select video…'}</option>
                  {videos.map((v) => (
                    <option key={v.url} value={v.url}>
                      {v.filename}
                    </option>
                  ))}
                </select>
                <button
                  type="button"
                  disabled={!videoUrl}
                  onClick={() => toggleVideoPlayback()}
                  className="flex items-center gap-1 rounded-lg border border-violet-400/40 px-2.5 py-1.5 text-[11px] text-violet-100 disabled:opacity-40"
                >
                  {isPlaying ? <Pause size={13} /> : <Play size={13} />}
                  {isPlaying ? (zh ? '暂停' : 'Pause') : (zh ? '播放' : 'Play')}
                </button>
                <button
                  type="button"
                  disabled={!videoUrl}
                  onClick={() => markDoctorKeyframe()}
                  className={`flex items-center gap-1 rounded-lg border px-2.5 py-1.5 text-[11px] font-semibold disabled:opacity-40 ${
                    isPlaying
                      ? 'border-amber-300/40 bg-amber-500/10 text-amber-100'
                      : 'border-amber-300/70 bg-amber-500/25 text-amber-50'
                  }`}
                  title={zh ? '暂停并标记当前帧为关键帧。空格先暂停，再按一次才标记' : 'Pause and mark this frame. Space pauses first; press again to mark'}
                >
                  {zh ? '标记此帧' : 'Mark this frame'}
                </button>
                <button
                  type="button"
                  disabled={
                    !videoUrl
                    || propagateToKeyframesBusy
                    || doctorKeyframes.length < 2
                    || !findDoctorKeyframeById(doctorKeyframes, activeDoctorKeyframeId)?.refined
                    || !(
                      points.length >= 3
                      || (findDoctorKeyframeById(doctorKeyframes, activeDoctorKeyframeId)?.lesionPolygon?.length || 0) >= 3
                    )
                  }
                  onClick={() => void runPropagateToOtherKeyframes()}
                  className="flex items-center gap-1 rounded-lg border border-sky-400/40 px-2.5 py-1.5 text-[11px] text-sky-100 disabled:opacity-40"
                  title={zh ? '按形变/光流把当前校正轮廓传到其余未精修关键帧' : 'Flow-propagate the refined contour to other unrefined keyframes'}
                >
                  {propagateToKeyframesBusy ? <Loader2 size={13} className="animate-spin" /> : <Share2 size={13} />}
                  {zh ? '传到其他关键帧' : 'To other keyframes'}
                </button>
                <CineScrubBar
                  className="min-w-[140px] flex-1"
                  duration={videoDuration}
                  progressPct={videoDuration > 0 ? (videoTime / videoDuration) * 100 : 0}
                  disabled={!videoUrl}
                  title={zh ? '拖进度条粗定位；滚轮逐帧' : 'Drag to seek; wheel steps one frame'}
                  ariaLabel={zh ? '视频进度' : 'Video progress'}
                  barRef={(node) => { videoProgressRefs.current[0] = node; }}
                  onScrubStart={beginVideoScrub}
                  onScrub={onVideoProgressChange}
                  onScrubEnd={endVideoScrub}
                />
                <span className="shrink-0 font-mono text-[10px] tabular-nums text-violet-200/90">
                  <span ref={(node) => { videoTimeLabelRefs.current[0] = node; }}>{formatCineTime(videoTime, videoFps)}</span>
                  {' / '}
                  {formatCineTime(videoDuration, videoFps)}
                </span>
                <CineSpeedSelect
                  value={videoPlaybackRate}
                  onChange={(rate) => {
                    setVideoPlaybackRate(rate);
                    recordDoctorOp('cine_speed', {
                      operation: 'cine_speed',
                      op: 'cine_speed',
                      value: rate,
                      video_time_sec: videoRef.current?.currentTime ?? null,
                    });
                  }}
                  zh={zh}
                  placement="down"
                />
                <label className="flex items-center gap-1.5 text-[10px] text-slate-500 opacity-70">
                  <input
                    type="checkbox"
                    checked={trackOnPlay}
                    disabled={frameFrozen}
                    onChange={(e) => {
                      setTrackOnPlay(e.target.checked);
                      if (e.target.checked) {
                        setFrameFrozen(false);
                        frameFrozenRef.current = false;
                      }
                    }}
                  />
                  {zh ? '播放时跟随（次要）' : 'Auto-track on play (secondary)'}
                </label>
                <button
                  type="button"
                  disabled={!videoUrl || samBusy || propagateBusy || points.length < 3}
                  onClick={() => {
                    freezeCurrentFrame();
                    const c = polygonCentroid(points);
                    const box = bboxFromPolygon(points);
                    if (c && box) void runSamAtPoint(c, { source: 'sam', box, keepEditing: true });
                    else setMessage(zh ? '请先点击视频画面获得当前帧结果' : 'Click the video frame first');
                  }}
                  className="rounded-lg border border-violet-400/40 px-2 py-1 text-[10px] text-violet-100 disabled:opacity-40"
                >
                  {zh ? '重新分析当前帧' : 'Re-analyze current frame'}
                </button>

                {frameFrozen && (
                  <button
                    type="button"
                    onClick={() => {
                      setFrameFrozen(false);
                      frameFrozenRef.current = false;
                      syncFrameFromVideo({ force: true });
                      redraw();
                      setMessage(zh ? '已解除帧冻结，可继续播放' : 'Frame unfrozen');
                    }}
                    className="rounded-lg border border-amber-400/40 px-2 py-1 text-[10px] text-amber-100"
                  >
                    {zh ? '解除冻结' : 'Unfreeze'}
                  </button>
                )}
                {!videos.length && (
                  <span className="text-[10px] text-amber-300/90">
                    {zh
                      ? '未命中 crop_ui/阅片库视频：可换病例或用样例目录'
                      : 'No crop_ui/reader video match — try another case or sample catalog'}
                  </span>
                )}
                {!!videos.length && mediaMode === 'video' && !videoUrl && (
                  <button
                    type="button"
                    onClick={openPatientVideoSam}
                    className="rounded-lg border border-violet-400/50 bg-violet-500/30 px-2 py-1 text-[10px] text-violet-50"
                  >
                    {zh ? '打开对应视频' : 'Open matched video'}
                  </button>
                )}
                {!videos.length && (
                  <button
                    type="button"
                    onClick={async () => {
                      const res = await fetch('/api/patients/videos?list=1&limit=30');
                      const data = await res.json();
                      const list = (data.videos || []).map((v: VideoInfo & { patient_key?: string }) => ({
                        url: v.url,
                        filename: v.filename,
                        treatment: v.treatment || 'direct_surgery',
                        water_filled: Boolean(v.water_filled),
                      }));
                      setVideos(list);
                      if (list[0]) setVideoUrl(list[0].url);
                    }}
                    className="rounded border border-white/15 px-2 py-1 text-[10px] text-slate-300"
                  >
                    {zh ? '载入样例视频' : 'Load sample videos'}
                  </button>
                )}
              </div>
              )}
              </div>
              </>
            )}


            <div className="relative min-h-0 flex-1 overflow-hidden bg-black">
              <div ref={containerRef} tabIndex={-1} className="relative h-full w-full bg-black outline-none">
                {simpleVideoMode && mediaMode === 'video' && (
                  <div className="pointer-events-none absolute inset-x-2 top-3 z-[180] overflow-x-auto">
                    <div className="pointer-events-none mx-auto flex min-w-full w-max flex-col items-center justify-center gap-1.5 pb-1">
                      <FloatingToolGroup accent="amber">
                        <FloatingToolButton
                          icon={<Pencil size={14} />}
                          label={paintToolLabel(wallPaintMode, zh)}
                          title={paintLineHint(wallLayerTarget, zh)}
                          active={wallPaintMode}
                          disabled={boxAutoSegBusy}
                          onClick={() => startWallPaintTool()}
                          tone="amber"
                        />
                        <FloatingToolButton
                          icon={<Crosshair size={14} />}
                          label={zh ? (analysisFocusMode ? '正在标焦点' : '分析焦点') : (analysisFocusMode ? 'Marking focus' : 'Focus')}
                          title={analysisFocusHint(zh)}
                          active={analysisFocusMode}
                          disabled={boxAutoSegBusy}
                          onClick={() => startAnalysisFocusTool()}
                          tone="amber"
                        />
                        <label className="flex items-center gap-1 px-1.5 text-[10px] text-amber-100/85">
                          <span>{zh ? `笔刷 ${wallBrushRadius}` : `Brush ${wallBrushRadius}`}</span>
                          <input
                            type="range"
                            min={3}
                            max={22}
                            value={wallBrushRadius}
                            onChange={(event) => setWallBrushRadius(Number(event.target.value))}
                            className="h-1 w-16 accent-amber-300"
                          />
                        </label>
                        <span className="flex items-center gap-0.5 px-1" title={zh ? '选择要分析的界面。不是判断病灶已经到了哪一层。第一版主看浆膜。' : 'Pick the interface to analyze. This is not a claim about how deep the lesion has reached. First version is serosa.'}>
                          {WALL_ANATOMY_TARGETS.map((target) => (
                            <button
                              key={target.id}
                              type="button"
                              onClick={() => applyWallLayerTarget(target.id)}
                              className={`rounded px-1.5 py-0.5 text-[10px] font-semibold ${
                                wallLayerTarget === target.id
                                  ? 'bg-amber-300 text-slate-900'
                                  : 'bg-black/30 text-amber-100/80 hover:bg-black/50'
                              }`}
                              title={zh ? target.askZh : target.askEn}
                            >
                              {zh ? target.shortZh : target.shortEn}
                            </button>
                          ))}
                        </span>
                        <FloatingToolButton
                          icon={<MousePointer2 size={14} />}
                          label={wallPickMode ? (zh ? '点两侧' : 'Pick flanks') : (zh ? '点两侧接' : 'Mark flanks')}
                          title={zh ? '点两侧看得见的胃壁，再自动接过去。再点一次则自动接。' : 'Click the two visible flanks, then join. Click again to auto-join.'}
                          active={wallPickMode}
                          disabled={boxAutoSegBusy || points.length < 3}
                          onClick={() => startWallExtensionTool()}
                          tone="amber"
                        />
                        <FloatingToolButton
                          icon={<ScanSearch size={14} />}
                          label={zh ? '最深窄带回声' : 'Deepest echo'}
                          title={zh ? '只在浸润最深窄带做亮/中/暗区域聚类，用于分层，不是全图超分' : 'Cluster bright/mid/dark echo on the deepest narrow band for layering, not full-image super-resolution'}
                          active={Boolean(wallEchoClarify?.available && viewFocusMode === 'roi')}
                          disabled={boxAutoSegBusy || (points.length < 3 && wallPoints.length < 3)}
                          onClick={() => {
                            const next = wallEchoClarify?.available ? wallEchoClarify : refreshWallEchoClarify();
                            if (!next?.available) {
                              setMessage(zh ? '请先框选病灶并画邻近胃壁，再盯浸润最深窄带' : 'Box the lesion and paint the adjacent wall first');
                              return;
                            }
                            if (viewFocusMode === 'roi' && viewFocusBox) {
                              setViewFocusBox(null);
                              setViewFocusMode(null);
                              setMessage(zh ? '已回到整帧' : 'Back to the full frame');
                              return;
                            }
                            setMagnifierOn(false);
                            magnifierPosRef.current = null;
                            viewZoomRef.current = 1;
                            viewCenterRef.current = null;
                            setViewZoom(1);
                            setViewCenter(null);
                            setViewFocusBox(next.box);
                            setViewFocusMode('roi');
                            setMessage(zh
                              ? `已放大浸润最深窄带（${next.patternZh || '回声聚类'}）。不是全图超分。`
                              : `Zoomed to the deepest narrow band (${next.patternEn || 'echo cluster'}). Not full-image super-resolution.`);
                          }}
                          tone="amber"
                        />
                        <FloatingToolButton
                          icon={dinoBusy ? <Loader2 size={14} className="animate-spin" /> : <BrainCircuit size={14} />}
                          label={dinoDockOpen
                            ? (zh ? '收起DINO' : 'Hide DINO')
                            : dinoBusy
                              ? (zh ? 'DINO层…' : 'DINO…')
                              : (zh ? 'ROI DINO层' : 'ROI DINO')}
                          title={zh
                            ? '打开对话框查看当前帧 ROI 的 DINOv3 L2 / L5 / L8 / L11。再点一次收起。'
                            : 'Open a dialog for DINOv3 L2 / L5 / L8 / L11 on the current ROI. Click again to collapse.'}
                          active={dinoDockOpen}
                          disabled={boxAutoSegBusy || points.length < 3}
                          onClick={() => toggleRoiDinoLayers()}
                          tone="amber"
                        />
                        <FloatingToolButton
                          icon={<Layers size={14} />}
                          label={wallAnalysisOpen ? (zh ? '收起壁层' : 'Close layers') : (zh ? '壁层' : 'Layers')}
                          title={zh ? '打开或收起胃壁分层面板' : 'Open or close the wall-layer panel'}
                          active={wallAnalysisOpen}
                          disabled={points.length < 3 && !layerResult && wallPoints.length < 3}
                          onClick={() => {
                            window.dispatchEvent(new CustomEvent('gastric:open-wall-layers', {
                              detail: { open: !wallAnalysisOpen },
                            }));
                          }}
                          tone="amber"
                        />
                        <FloatingToolButton
                          icon={<Save size={14} />}
                          label={zh ? '保存胃壁' : 'Save wall'}
                          title={zh ? '把当前帧的胃壁辅助线存到本关键帧。不会传到其他帧。' : 'Save wall guides on this keyframe only. They are not copied to other frames.'}
                          disabled={boxAutoSegBusy || (wallPoints.length < 3 && !wallLayerBands.length && !analysisFocusPoints.length)}
                          onClick={() => saveWallDraftOnFrame()}
                          tone="amber"
                        />
                        <FloatingToolButton
                          icon={<Trash2 size={14} />}
                          label={zh ? '清除胃壁' : 'Clear wall'}
                          title={zh ? '只清除当前帧的胃壁辅助线，不影响其他关键帧' : 'Clear wall guides on this frame only'}
                          disabled={boxAutoSegBusy || (wallPoints.length < 3 && !wallLayerBands.length && !analysisFocusPoints.length)}
                          onClick={() => clearWallDraftOnFrame()}
                          tone="amber"
                        />
                      </FloatingToolGroup>
                      {onUnifiedAgentRun ? (
                        <FloatingToolGroup accent="sky">
                          <FloatingToolButton
                            icon={unifiedAgentBusy ? <Loader2 size={15} className="animate-spin" /> : <Sparkles size={15} />}
                            label={unifiedAgentBusy || assistOverlayOpen ? (zh ? '分析中' : 'Running') : (zh ? '辅助分析' : 'Assist')}
                            title={
                              points.length < 3
                                ? (zh ? '请先框选病灶，再分析' : 'Draw a lesion box first, then analyze')
                                : (zh ? '用当前框选做辅助分析' : 'Run assist on the current lesion box')
                            }
                            disabled={!videoUrl || unifiedAgentBusy || points.length < 3}
                            onClick={() => void runContourAnchoredAssist()}
                            tone="sky"
                            emphasize
                          />
                        </FloatingToolGroup>
                      ) : null}
                    </div>
                  </div>
                )}
                {simpleVideoMode && simpleToolsOpen ? (
                  <div className="workbench-tool-rail-dock pointer-events-none absolute top-2 bottom-2 right-2 z-[220] flex items-start sm:top-3 sm:right-3">
                    <div className="workbench-tool-rail pointer-events-auto max-h-full rounded-lg border border-white/10 bg-black/70 p-1 shadow-2xl shadow-black/40 backdrop-blur-md">
                      <ToolRailSectionTitle>{zh ? '病灶' : 'Lesion'}</ToolRailSectionTitle>
                      <div className="mx-1 mb-0.5 rounded-md border border-white/10 bg-black/40 p-0.5">
                        <div className="grid grid-cols-2 gap-0.5">
                          {([
                            { id: 'sam31' as const, zh: 'SAM 3.1', en: 'SAM 3.1' },
                            { id: 'dinov3' as const, zh: 'DINO', en: 'DINO' },
                          ]).map((item) => {
                            const active = publicLesionSegModel(segmentationModel) === item.id;
                            return (
                              <button
                                key={item.id}
                                type="button"
                                disabled={boxAutoSegBusy}
                                title={
                                  item.id === 'dinov3'
                                    ? (zh ? '框选病灶时用 DINO 画 mask，随后辅助分析相同' : 'Box lesion with DINO; Assist is the same after the mask')
                                    : (zh ? '框选病灶时用 SAM 3.1 画 mask，随后辅助分析相同' : 'Box lesion with SAM 3.1; Assist is the same after the mask')
                                }
                                onClick={() => chooseLesionSegModel(item.id)}
                                className={`rounded px-1 py-1 text-[10px] font-semibold disabled:opacity-40 ${
                                  active
                                    ? 'bg-cyan-400/40 text-white'
                                    : 'text-slate-400 hover:bg-white/10 hover:text-slate-200'
                                }`}
                              >
                                {zh ? item.zh : item.en}
                              </button>
                            );
                          })}
                        </div>
                        <ToolRailButton
                          icon={boxAutoSegBusy ? <Loader2 size={15} className="animate-spin" /> : <ScanLine size={15} />}
                          label={zh ? '框选病灶' : 'Box lesion'}
                          hint={
                            zh
                              ? `当前 ${publicLesionSegModel(segmentationModel) === 'dinov3' ? 'DINO' : 'SAM 3.1'}。点亮后拖框。已有病灶时再拖会替换。多个灶用「再框一灶」`
                              : `Now ${publicLesionSegModel(segmentationModel) === 'dinov3' ? 'DINO' : 'SAM 3.1'}. Arm, then drag. A new box replaces the current lesion. Use Add lesion for a second mass`
                          }
                          active={lesionBoxArmed && !keepExtraLesion}
                          onClick={() => {
                            if (lesionBoxArmed && !keepExtraLesion) {
                              armLesionBox(false);
                              setKeepExtraLesion(false);
                              keepExtraLesionRef.current = false;
                              setMessage(zh ? '已取消框选病灶' : 'Box lesion cancelled');
                              return;
                            }
                            keepExtraLesionRef.current = false;
                            setKeepExtraLesion(false);
                            enterSimpleBoxPrompt();
                          }}
                          side="right"
                          tone={lesionBoxArmed && !keepExtraLesion ? 'cyan' : 'slate'}
                          prominent={lesionBoxArmed && !keepExtraLesion}
                        />
                      </div>
                      {points.length >= 3 ? (
                        <ToolRailButton
                          icon={<ScanLine size={15} />}
                          label={zh ? '再框一灶' : 'Add lesion'}
                          hint={zh ? '再拖一个框，上一处病灶留下（青色）' : 'Draw another box; the previous lesion stays (teal)'}
                          active={lesionBoxArmed && keepExtraLesion}
                          onClick={() => {
                            keepExtraLesionRef.current = true;
                            setKeepExtraLesion(true);
                            enterSimpleBoxPrompt();
                          }}
                          side="right"
                          tone={lesionBoxArmed && keepExtraLesion ? 'cyan' : 'slate'}
                          prominent={lesionBoxArmed && keepExtraLesion}
                        />
                      ) : null}
                      {extraLesionPolygons.length ? (
                        <ToolRailButton
                          icon={<ScanLine size={15} />}
                          label={zh ? '去掉上一灶' : 'Drop last extra'}
                          hint={zh ? '去掉最近留下的额外病灶，不改当前主灶' : 'Remove the last extra lesion; keep the current primary'}
                          onClick={() => dropLastExtraLesion()}
                          side="right"
                          tone="slate"
                        />
                      ) : null}
                      <ToolRailDivider />
                      <ToolRailButton
                        icon={<ScanLine size={15} />}
                        label={lumenEditMode ? (zh ? '正在框胃腔' : 'Boxing lumen') : (zh ? '框选胃腔' : 'Box lumen')}
                        hint={zh ? '点亮后光标变为拖框标记；松手后自动分割胃腔。再点一次取消' : 'Arm to get the box cursor; release auto-segments the lumen. Click again to cancel'}
                        active={lumenEditMode}
                        disabled={boxAutoSegBusy}
                        onClick={() => toggleLumenBoxEdit()}
                        side="right"
                        tone="fuchsia"
                        prominent={lumenEditMode}
                      />
                      <ToolRailButton
                        icon={<Spline size={15} />}
                        label={zh ? (wallPaintMode ? '正在画预期线' : '预期线') : (wallPaintMode ? 'Drawing trajectory' : 'Trajectory')}
                        hint={paintLineHint(wallLayerTarget, zh)}
                        active={wallPaintMode || wallPickMode || (simpleEditMode && simpleEditLayer === 'wall')}
                        disabled={boxAutoSegBusy}
                        onClick={() => startWallPaintTool()}
                        side="right"
                        tone="amber"
                        prominent={wallPaintMode || wallPickMode}
                      />
                      <ToolRailButton
                        icon={<MoreHorizontal size={15} />}
                        label={zh ? '更多工具' : 'More tools'}
                        hint={zh ? '拖点精修、正负点、涂改、检测胃腔、多边形与清空' : 'Contour edit, points, paint, find lumen, polygon, and clear'}
                        active={railMoreOpen}
                        onClick={() => setRailMoreOpen((value) => !value)}
                        side="right"
                        tone="slate"
                      />
                      {railMoreOpen ? (
                        <>
                          {points.length >= 3 && !boxAutoSegBusy && !lumenEditMode ? (
                            <>
                              <ToolRailDivider />
                              <ToolRailSectionTitle>{zh ? '病灶精修' : 'Lesion refine'}</ToolRailSectionTitle>
                              <ToolRailButton
                                icon={<Pencil size={15} />}
                                label={zh ? '拖点精修' : 'Edit contour'}
                                hint={zh ? '遮罩已出：拖控制点微调病灶轮廓' : 'Mask ready: drag handles to refine the lesion'}
                                active={simpleEditMode && simpleEditLayer === 'lesion' && !lumenSculptMode}
                                disabled={boxAutoSegBusy}
                                onClick={() => {
                                  enterSimpleContourEdit('lesion');
                                  recordDoctorOp('tool_switch', { layer: 'lesion', operation: 'tool_switch', tool: 'contour_edit' });
                                }}
                                side="right"
                                tone="cyan"
                                prominent={simpleEditMode && simpleEditLayer === 'lesion'}
                              />
                              <ToolRailButton
                                icon={<CirclePlus size={15} />}
                                label={zh ? '正点' : '+ Point'}
                                hint={zh ? '点击补充漏分割区域' : 'Click to add missed lesion area'}
                                active={simplePromptMode === 'point' && activeSamPromptLabel === 'positive' && !lumenSculptMode}
                                onClick={() => {
                                  setActiveSamPromptLabel('positive');
                                  activateActiveSamPrompt('point');
                                  recordDoctorOp('tool_switch', { layer: 'lesion', operation: 'tool_switch', tool: 'point_positive' });
                                }}
                                side="right"
                                tone="emerald"
                              />
                              <ToolRailButton
                                icon={<CircleMinus size={15} />}
                                label={zh ? '负点' : '- Point'}
                                hint={zh ? '点击排除伪影或壁' : 'Click to exclude artifact or wall'}
                                active={simplePromptMode === 'point' && activeSamPromptLabel === 'negative' && !lumenSculptMode}
                                onClick={() => {
                                  setActiveSamPromptLabel('negative');
                                  activateActiveSamPrompt('point');
                                  recordDoctorOp('tool_switch', { layer: 'lesion', operation: 'tool_switch', tool: 'point_negative' });
                                }}
                                side="right"
                                tone="rose"
                              />
                              <ToolRailButton
                                icon={<Brush size={15} />}
                                label={zh ? '病灶增' : 'Lesion +'}
                                hint={zh ? '涂抹以扩大病灶区域' : 'Paint to expand the lesion'}
                                active={lumenSculptMode === 'brush-add' && sculptLayer === 'lesion'}
                                onClick={() => activateSculpt('brush-add', 'lesion')}
                                side="right"
                                tone="lime"
                              />
                              <ToolRailButton
                                icon={<Eraser size={15} />}
                                label={zh ? '病灶减' : 'Lesion -'}
                                hint={zh ? '涂抹以缩小病灶区域' : 'Paint to shrink the lesion'}
                                active={lumenSculptMode === 'brush-sub' && sculptLayer === 'lesion'}
                                onClick={() => activateSculpt('brush-sub', 'lesion')}
                                side="right"
                                tone="rose"
                              />
                              <ToolRailButton
                                icon={<Sparkles size={15} />}
                                label={zh ? '边界精修' : 'Refine'}
                                hint={zh ? '用当前病灶边界启动辅助精修' : 'Refine the current lesion boundary'}
                                disabled={nnInteractiveBusy}
                                active={nnInteractiveMode}
                                onClick={() => {
                                  activateNnInteractive('lesion');
                                  recordDoctorOp('nninteractive', { layer: 'lesion', operation: 'nninteractive', tool: 'refine' });
                                }}
                                side="right"
                                tone="lime"
                              />
                              {(lumenSculptMode && sculptLayer === 'lesion') ? (
                                <div className="px-1 py-1">
                                  <div className="text-center text-[9px] text-slate-200">
                                    {zh ? `笔刷 ${paintRadius}` : `Brush ${paintRadius}`}
                                  </div>
                                  <input
                                    type="range"
                                    min={6}
                                    max={48}
                                    value={paintRadius}
                                    onChange={(event) => setPaintRadius(Number(event.target.value))}
                                    className="w-full accent-sky-400"
                                  />
                                </div>
                              ) : null}
                            </>
                          ) : null}
                          <ToolRailDivider />
                          <ToolRailSectionTitle>{zh ? '胃腔（可选）' : 'Lumen (optional)'}</ToolRailSectionTitle>
                          <ToolRailButton
                            icon={lumenBusy ? <Loader2 size={15} className="animate-spin" /> : <ScanSearch size={15} />}
                            label={zh ? '检测胃腔' : 'Find lumen'}
                            hint={zh ? '自动检测胃腔候选' : 'Auto-detect lumen candidate'}
                            disabled={boxAutoSegBusy || lumenBusy}
                            onClick={() => void detectLumen()}
                            side="right"
                            tone="fuchsia"
                          />
                          <ToolRailButton
                            icon={<Brush size={15} />}
                            label={zh ? '胃腔增' : 'Lumen +'}
                            hint={zh ? '涂抹以扩大胃腔区域' : 'Paint to expand the lumen'}
                            active={lumenSculptMode === 'brush-add' && sculptLayer === 'lumen'}
                            disabled={!lumenBox && lumenPolygon.length < 3}
                            onClick={() => activateSculpt('brush-add', 'lumen')}
                            side="right"
                            tone="lime"
                          />
                          <ToolRailButton
                            icon={<Eraser size={15} />}
                            label={zh ? '胃腔减' : 'Lumen -'}
                            hint={zh ? '涂抹以缩小胃腔区域' : 'Paint to shrink the lumen'}
                            active={lumenSculptMode === 'brush-sub' && sculptLayer === 'lumen'}
                            disabled={!lumenBox && lumenPolygon.length < 3}
                            onClick={() => activateSculpt('brush-sub', 'lumen')}
                            side="right"
                            tone="rose"
                          />
                          {(lumenSculptMode && sculptLayer === 'lumen') ? (
                            <div className="px-1 py-1">
                              <div className="text-center text-[9px] text-slate-200">
                                {zh ? `笔刷 ${paintRadius}` : `Brush ${paintRadius}`}
                              </div>
                              <input
                                type="range"
                                min={6}
                                max={48}
                                value={paintRadius}
                                onChange={(event) => setPaintRadius(Number(event.target.value))}
                                className="w-full accent-sky-400"
                              />
                            </div>
                          ) : null}
                          <ToolRailDivider />
                          <ToolRailButton
                            icon={<Pentagon size={15} />}
                            label={zh ? '多边形' : 'Polygon'}
                            hint={zh ? '手工多边形编辑病灶' : 'Manual polygon edit for lesion'}
                            active={mode === 'polygon'}
                            disabled={boxAutoSegBusy}
                            onClick={() => {
                              setMode('polygon');
                              setSimpleEditMode(false);
                              setLumenEditMode(false);
                              setLumenSculptMode(null);
                              recordDoctorOp('tool_switch', { layer: 'lesion', operation: 'tool_switch', tool: 'polygon' });
                              setMessage(zh ? '多边形模式：点击加点，双击或按钮闭合' : 'Polygon mode: click to add vertices');
                            }}
                            side="right"
                            tone="amber"
                          />
                          <ToolRailButton
                            icon={<RotateCcw size={15} />}
                            label={zh ? '清空重画' : 'Clear all'}
                            hint={zh ? '清除当前框后重新框选' : 'Clear the current box and draw again'}
                            disabled={saving || boxAutoSegBusy}
                            onClick={() => void handleClear()}
                            side="right"
                            tone="slate"
                          />
                          <ToolRailButton
                            icon={<Undo2 size={15} />}
                            label={zh ? '撤销操作' : 'Undo last'}
                            hint={zh ? '撤销上一步编辑' : 'Undo the last edit'}
                            disabled={undoLen < 1}
                            onClick={undoEdit}
                            side="right"
                            tone="slate"
                          />
                          <ToolRailDivider />
                          <ToolRailButton
                            icon={<ZoomIn size={15} />}
                            label={magnifierOn ? (zh ? '关闭放大' : 'Lens off') : (zh ? '局部放大' : 'Local zoom')}
                            hint={zh ? '开启或关闭局部放大镜' : 'Toggle the local magnifier'}
                            active={magnifierOn}
                            onClick={toggleMagnifier}
                            side="right"
                            tone="sky"
                          />
                          <ToolRailButton
                            icon={<ZoomIn size={15} />}
                            label={(viewFocusBox || viewZoom > 1.02) ? (zh ? '退出放大' : 'Exit zoom') : (zh ? '区域放大' : 'Region zoom')}
                            hint={zh ? '放大病灶或胃腔区域；滚轮也可缩放当前帧' : 'Zoom to the lesion or lumen; the wheel also zooms this frame'}
                            disabled={points.length < 3 && !lumenBox && lumenPolygon.length < 3 && viewZoom <= 1.02}
                            active={Boolean(viewFocusBox) || viewZoom > 1.02}
                            onClick={toggleZoomRoi}
                            side="right"
                            tone="sky"
                          />
                          <ToolRailButton
                            icon={<PanelTop size={15} />}
                            label={zh ? '隐藏工具' : 'Hide tools'}
                            hint={zh ? '隐藏工具栏' : 'Hide the tool rail'}
                            onClick={() => setSimpleToolsOpen(false)}
                            side="right"
                            tone="slate"
                          />
                        </>
                      ) : null}
                    </div>
                  </div>
                ) : null}
                {simpleVideoMode && !simpleToolsOpen ? (
                  <div className="pointer-events-none absolute bottom-2 right-2 z-[220] md:top-2 md:bottom-auto md:right-2">
                    <div className="pointer-events-auto rounded-lg border border-white/10 bg-black/70 p-1 backdrop-blur-md">
                      <ToolRailButton
                        icon={<PanelTop size={16} />}
                        label={zh ? '显示工具' : 'Show tools'}
                        hint={zh ? '打开右侧工具栏' : 'Open the right tool rail'}
                        onClick={() => setSimpleToolsOpen(true)}
                        side="right"
                        tone="slate"
                      />
                    </div>
                  </div>
                ) : null}
                {mediaMode === 'video' && (
                  <video
                    ref={videoRef}
                    className={simpleVideoMode && viewZoom <= 1.02 && !viewFocusBox ? 'absolute inset-0 z-0 h-full w-full bg-black object-contain' : 'hidden'}
                    muted
                    playsInline
                    autoPlay
                    preload="auto"
                    crossOrigin="anonymous"
                  />
                )}
                {viewZoom > 1.02 ? (
                  <div className="pointer-events-none absolute left-3 bottom-3 z-[30] flex items-center gap-2 rounded-md border border-white/15 bg-black/70 px-2 py-1 text-[10px] text-slate-200">
                    <span className="font-mono text-amber-100">{`x${viewZoom.toFixed(1)}`}</span>
                    <span className="text-slate-400">{zh ? '滚轮缩放, Shift 拖移, 双击复位' : 'Wheel zoom, Shift drag, double-click reset'}</span>
                  </div>
                ) : null}
                <canvas
                  ref={canvasRef}
                  className="relative z-10 h-full w-full touch-none"
                  style={{
                    cursor: magnifierOn
                      ? 'none'
                      : (wallPickMode || wallPaintMode)
                        ? 'crosshair'
                        : lumenSculptMode
                        ? 'crosshair'
                        : lumenEditMode
                          ? BOX_DRAW_CURSOR_LUMEN
                          : lesionBoxArmed
                            ? BOX_DRAW_CURSOR_LESION
                            : dragIndex !== null
                              ? 'grabbing'
                              : (simpleEditMode || points.length >= 3)
                                ? 'move'
                                : 'default',
                  }}
                  onPointerDown={onPointerDown}
                  onPointerMove={onPointerMove}
                  onPointerUp={onPointerUp}
                  onPointerCancel={onPointerCancel}
                  onWheel={(e) => {
                    if (wallPaintMode) {
                      e.preventDefault();
                      const step = e.deltaY > 0 ? -1 : 1;
                      setWallBrushRadius((value) => Math.max(3, Math.min(22, value + step)));
                      return;
                    }
                    if (lumenSculptMode) {
                      e.preventDefault();
                      const step = e.deltaY > 0 ? -2 : 2;
                      setPaintRadius((r) => Math.max(6, Math.min(48, r + step)));
                      return;
                    }
                    e.preventDefault();
                  }}
                  onDoubleClick={(e) => {
                    if (viewZoom > 1.02) {
                      resetViewZoom();
                      return;
                    }
                    if (simpleVideoMode) return;
                    const imgPt = canvasToImage(e);
                    if (!imgPt) return;
                    const edgeThr = hitThreshold() * 3;
                    const lesionHit = polygonHit(imgPt, pointsRef.current, edgeThr);
                    const wallHit = polygonHit(imgPt, wallPointsRef.current, edgeThr);
                    if (!lesionHit && !wallHit) return;
                    const preferWall = wallHit && (
                      !lesionHit
                      || minDist2ToPolygon(imgPt, wallPointsRef.current) <= minDist2ToPolygon(imgPt, pointsRef.current)
                    );
                    const layer: ContourLayer = preferWall ? 'wall' : 'lesion';
                    freezeCurrentFrame();
                    stopInteractivePrompt();
                    setSimplePromptMode('box');
                    setLumenEditMode(false);
                    setActiveLayer(layer);
                    setMode('soft');
                    setMessage(
                      zh
                        ? (layer === 'wall' ? '已进入胃壁编辑：拖动手柄微调' : '已进入病灶编辑：拖动手柄微调')
                        : (layer === 'wall' ? 'Wall edit mode: drag handles' : 'Lesion edit mode: drag handles'),
                    );
                  }}
                />
                {(samBusy || lumenSamBusy || segmentationBusy || propagateBusy || precomputeBusy || workflowBusy || lesionAutoBusy || (mediaMode === 'image' && !imgLoaded)) && !assistOverlayOpen && !unifiedAgentBusy && (
                  <div className="pointer-events-none absolute inset-0 z-[170] flex flex-col items-center justify-center bg-black/45 px-4">
                    <Loader2 className="animate-spin text-cyan-300" size={34} />
                    {(taskProgress || precomputeProgress || unifiedAgentBusy || workflowBusy || lesionAutoBusy || lumenSamBusy || propagateBusy || samBusy || segmentationBusy) ? (
                      <div className="mt-4 w-[min(40rem,100%)] rounded-2xl border border-white/20 bg-slate-950/95 px-6 py-5 text-center shadow-2xl backdrop-blur">
                        <div className="text-sm font-semibold text-slate-100">
                          {taskProgress?.label
                            || (precomputeBusy
                              ? (zh ? '整段视频跟踪' : 'Full-video tracking')
                              : unifiedAgentBusy
                                ? (zh ? '辅助意见分析' : 'Assisted analysis')
                                : workflowBusy
                                  ? (workflowStepLabel || (zh ? '流程中' : 'Running'))
                                  : lesionAutoBusy
                                    ? (zh ? '正在找病灶' : 'Finding lesion')
                                    : lumenSamBusy
                                      ? (zh ? '胃腔分割中' : 'Segmenting lumen')
                                      : propagateBusy
                                        ? (zh ? '视频跟踪中' : 'Tracking video')
                                        : (zh ? '分割中' : 'Segmenting'))}
                        </div>
                        <div className="mt-2 text-xs leading-5 text-slate-300">
                          {taskProgress?.detail
                            || precomputeProgress
                            || (workflowBusy ? workflowStepLabel : null)
                            || (lumenSamBusy
                              ? (zh ? '病灶轮廓保持不动' : 'Lesion contour stays put')
                              : (zh ? '请稍候，不要重复点击' : 'Please wait; do not click repeatedly'))}
                        </div>
                        <div className="mt-3 h-2 overflow-hidden rounded-full bg-white/10">
                          <div
                            className={`h-full rounded-full bg-sky-400/80 ${
                              taskProgress ? 'transition-[width] duration-500 ease-out' : 'task-progress-indeterminate'
                            }`}
                            style={taskProgress ? {
                              width: `${Math.max(
                                12,
                                Math.min(
                                  96,
                                  Math.round((taskProgress.step / Math.max(1, taskProgress.totalSteps)) * 100),
                                ),
                              )}%`,
                            } : undefined}
                          />
                        </div>
                        <div className="mt-2 flex items-center justify-center gap-4 font-mono text-[11px] text-slate-400">
                          {taskProgress ? (
                            <span>{zh ? `步骤 ${taskProgress.step}/${taskProgress.totalSteps}` : `Step ${taskProgress.step}/${taskProgress.totalSteps}`}</span>
                          ) : null}
                          <span>{zh ? `已用时 ${taskElapsedSec}s` : `Elapsed ${taskElapsedSec}s`}</span>
                        </div>
                      </div>
                    ) : null}
                  </div>
                )}
                {taskProgress && !assistOverlayOpen && !(samBusy || propagateBusy || precomputeBusy || unifiedAgentBusy || workflowBusy) ? (
                  <div className="pointer-events-none absolute inset-x-0 bottom-3 z-[175] flex justify-center px-4">
                    <div className="w-[min(44rem,100%)] rounded-xl border border-white/20 bg-slate-950/95 px-4 py-3 shadow-xl backdrop-blur">
                      <div className="flex items-center justify-between gap-2 text-xs text-slate-200">
                        <span className="font-semibold">{taskProgress.label}</span>
                        <span className="font-mono text-slate-400">
                          {taskProgress.step}/{taskProgress.totalSteps}, {taskElapsedSec}s
                        </span>
                      </div>
                      <div className="mt-1 text-[11px] leading-4 text-slate-400">{taskProgress.detail}</div>
                      <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-white/10">
                        <div
                          className="h-full rounded-full bg-sky-400/80 transition-[width] duration-500 ease-out"
                          style={{ width: `${Math.round((taskProgress.step / Math.max(1, taskProgress.totalSteps)) * 100)}%` }}
                        />
                      </div>
                    </div>
                  </div>
                ) : null}
                {(lumenEditMode || (!simpleVideoMode && (nnInteractiveMode || (mode === 'sam' && simplePromptMode !== 'box')))) && (
                  <div className={`pointer-events-none absolute top-3 left-3 z-20 rounded-lg border bg-slate-950/95 px-2.5 py-2 text-[10px] text-slate-200 shadow-lg ${
                    lumenEditMode
                      ? 'border-fuchsia-300/40'
                      : lesionBoxArmed
                        ? 'border-cyan-300/40'
                        : 'border-emerald-300/30'
                  }`}>
                    <div className={`font-semibold ${lumenEditMode ? 'text-fuchsia-100' : 'text-emerald-100'}`}>
                      {lumenEditMode
                        ? (zh ? '正在框选胃腔' : 'Boxing lumen')
                        : nnInteractiveMode
                          ? `${nnInteractiveTarget === 'lumen' ? (zh ? '胃腔' : 'Lumen') : (zh ? '病灶' : 'Lesion')} ${promptModeText(simplePromptMode, zh)}`
                          : `${zh ? '本地点提示' : 'Local prompt'} ${promptModeText(simplePromptMode, zh)}`}
                    </div>
                    {lumenEditMode ? (
                      <div className="mt-1 text-fuchsia-200">
                        {zh ? '拖出矩形，松手后自动分割胃腔' : 'Drag a rectangle; release auto-segments the lumen'}
                      </div>
                    ) : (
                      <>
                        <div className="mt-1 flex items-center gap-2">
                          <span className="inline-flex items-center gap-0.5 text-emerald-300"><CirclePlus size={11} />{zh ? '正点' : 'Positive'}</span>
                          <span className="inline-flex items-center gap-0.5 text-rose-300"><CircleMinus size={11} />{zh ? '负点' : 'Negative'}</span>
                          <span className="text-slate-400">
                            {nnInteractiveMode ? nnInteractiveClicks.length : samClicks.length} {zh ? '点' : 'points'}
                            {promptStrokes.length ? `, ${promptStrokes.length} ${zh ? '笔' : 'strokes'}` : ''}
                          </span>
                        </div>
                        {nnInteractiveBusy ? (
                          <div className="mt-1 text-amber-200">{zh ? '边界更新中…' : 'Updating boundary…'}</div>
                        ) : null}
                      </>
                    )}
                  </div>
                )}
              </div>
              {wallDockEl ? createPortal(
                <WallFeatureAnalysisCard
                  zh={zh}
                  lesionPolygon={points}
                  wallPolygon={wallPoints}
                  frameSize={frameSize}
                  frameDataUrl={frameDataUrl}
                  pick={layerPick}
                  lumenPrefer={lumenPrefer}
                  paused={dragIndex !== null || samBusy || propagateBusy || lumenBusy || lumenSamBusy}
                  onResult={setLayerResult}
                />,
                wallDockEl,
              ) : null}
            </div>
            {simpleVideoMode && (
              <div className="workbench-cine-bar shrink-0 border-t border-white/10 bg-black px-3 py-2">
                <div className="flex items-center gap-2">
                  <span className="w-[7.6rem] shrink-0 text-right font-mono text-[10px] tabular-nums text-slate-300">
                    <span ref={(node) => { videoTimeLabelRefs.current[1] = node; }}>{formatCineTime(videoTime, videoFps)}</span>
                  </span>
                  <CineScrubBar
                    className="min-w-0 flex-1"
                    duration={videoDuration}
                    progressPct={videoDuration > 0 ? (videoTime / videoDuration) * 100 : 0}
                    disabled={!videoUrl}
                    title={zh ? '拖进度条粗定位；滚轮逐帧' : 'Drag to seek; wheel steps one frame'}
                    ariaLabel={zh ? '视频进度' : 'Video progress'}
                    barRef={(node) => { videoProgressRefs.current[1] = node; }}
                    onScrubStart={beginVideoScrub}
                    onScrub={onVideoProgressChange}
                    onScrubEnd={endVideoScrub}
                  />
                  <span className="w-[7.6rem] shrink-0 font-mono text-[10px] tabular-nums text-slate-300">
                    {formatCineTime(videoDuration, videoFps)}
                  </span>
                </div>
                <div className="mt-1.5 flex items-center justify-between gap-2 max-md:justify-center">
                  <span className="min-w-0 truncate text-[10px] text-slate-500 max-md:hidden">
                    {zh
                      ? (doctorKeyframes.length < 2
                        ? 'T 分期最好再标 1–2 个关键帧。进度条粗定位，滚轮或左右键逐帧。空格先暂停，再按一次才标记'
                        : '进度条粗定位，滚轮或左右键逐帧。空格先暂停；已暂停时再按空格才标关键帧')
                      : (doctorKeyframes.length < 2
                        ? 'T-staging works better with 2–3 keyframes. Drag to seek, wheel or arrows for one frame. Space pauses; press again to mark'
                        : 'Drag to seek; wheel or arrows step one frame. Space pauses first. Press Space again while paused to mark')}
                  </span>
                  <div className="flex shrink-0 items-center gap-1">
                    {simpleVideoMode && keyCandidates.length > 0 ? (
                      <div className="mr-1 flex max-w-[42%] items-center gap-1 overflow-x-auto max-md:hidden">
                        <span className="shrink-0 text-[9px] text-slate-500" title={zh ? '算法建议帧，仅供参考；请医生 scrub 自选关键帧' : 'Algorithm hints only; scrub to pick your own key frames'}>
                          {zh ? '建议帧' : 'Hints'}
                        </span>
                        {keyCandidates.slice(0, 5).map((candidate) => (
                          <button
                            key={`${candidate.timestamp_sec}-${candidate.frame_index ?? 'x'}`}
                            type="button"
                            onClick={() => {
                              const video = videoRef.current;
                              if (!video) return;
                              video.pause();
                              video.currentTime = candidate.timestamp_sec;
                              setVideoTime(candidate.timestamp_sec);
                              syncFrameFromVideo({ force: true });
                              redrawRef.current();
                              setMessage(
                                zh
                                  ? `已跳到算法建议帧 t=${candidate.timestamp_sec.toFixed(2)}s；仍可自行 scrub 选帧`
                                  : `Jumped to suggested frame t=${candidate.timestamp_sec.toFixed(2)}s; you may still scrub freely`,
                              );
                            }}
                            className="shrink-0 rounded border border-amber-300/30 bg-amber-500/10 px-1.5 py-0.5 font-mono text-[9px] text-amber-100 hover:bg-amber-500/25"
                          >
                            {candidate.timestamp_sec.toFixed(1)}s
                          </button>
                        ))}
                      </div>
                    ) : (
                      <span className="mr-1 hidden text-[9px] text-slate-500 sm:inline">
                        {zh ? '关键帧以医生自选为主' : 'Doctor-selected frames preferred'}
                      </span>
                    )}
                    <button
                      type="button"
                      disabled={!videoUrl}
                      onClick={() => stepCineFrames(-1)}
                      className="rounded-md p-1.5 text-slate-400 hover:bg-white/10 hover:text-white disabled:opacity-30 max-md:min-h-11 max-md:min-w-11"
                      title={zh ? '后退一帧' : 'Previous frame'}
                    >
                      <SkipBack size={13} />
                    </button>
                    <button
                      type="button"
                      disabled={!videoUrl}
                      onClick={() => toggleVideoPlayback()}
                      className="flex h-7 min-w-12 items-center justify-center gap-1 rounded-md border border-white/20 bg-white/10 px-2 text-[10px] text-white hover:bg-white/15 disabled:opacity-30 max-md:h-11 max-md:min-w-16 max-md:text-xs"
                    >
                      {isPlaying ? <Pause size={12} /> : <Play size={12} />}
                      {isPlaying ? (zh ? '暂停' : 'Pause') : (zh ? '播放' : 'Play')}
                    </button>
                    <button
                      type="button"
                      disabled={!videoUrl}
                      onClick={() => stepCineFrames(1)}
                      className="rounded-md p-1.5 text-slate-400 hover:bg-white/10 hover:text-white disabled:opacity-30 max-md:min-h-11 max-md:min-w-11"
                      title={zh ? '前进一帧' : 'Next frame'}
                    >
                      <SkipForward size={13} />
                    </button>
                    <button
                      type="button"
                      disabled={!videoUrl}
                      onClick={() => markDoctorKeyframe()}
                      className="flex h-7 items-center justify-center gap-1 rounded-md border border-amber-300/50 bg-amber-500/20 px-2.5 text-[10px] font-semibold text-amber-50 hover:bg-amber-500/30 disabled:opacity-30 max-md:h-11 max-md:px-3 max-md:text-xs"
                      title={zh
                        ? '暂停并标记当前帧为关键帧。空格先暂停，再按一次才标记'
                        : 'Pause and mark this frame. Space pauses first; press again to mark'}
                    >
                      <Flag size={12} />
                      {zh ? '标记此帧' : 'Mark frame'}
                    </button>
                    <CineSpeedSelect
                      value={videoPlaybackRate}
                      onChange={(rate) => {
                        setVideoPlaybackRate(rate);
                        recordDoctorOp('cine_speed', {
                          operation: 'cine_speed',
                          op: 'cine_speed',
                          value: rate,
                          video_time_sec: videoRef.current?.currentTime ?? null,
                        });
                      }}
                      zh={zh}
                      placement="up"
                    />
                  </div>
                </div>
              </div>
            )}
            <div className={`workbench-toolbar flex flex-wrap items-center gap-2 border-t border-white/10 px-4 ${simpleVideoMode ? 'py-1' : 'py-3'}`}>
              {!simpleVideoMode && (
                <button
                  type="button"
                  disabled={saving || points.length < 3}
                  onClick={() => void handleSave()}
                  className="flex items-center gap-1.5 rounded-lg border border-emerald-400/40 bg-emerald-500/15 px-3 py-1.5 text-[11px] font-semibold text-emerald-100 disabled:opacity-40"
                >
                  {saving ? <Loader2 size={13} className="animate-spin" /> : <Save size={13} />}
                  {zh ? '保存覆盖' : 'Save override'}
                </button>
              )}
              {!simpleVideoMode && (
                <button
                  type="button"
                  disabled={samBusy || points.length < 3}
                  onClick={() => {
                    const c = polygonCentroid(points);
                    const box = bboxFromPolygon(points);
                    if (c && box) {
                      freezeCurrentFrame();
                      void runSamAtPoint(c, { source: 'sam', box, keepEditing: true, stayInSam: true, llmReport: true });
                    }
                  }}
                  className="flex items-center gap-1.5 rounded-lg border border-white/15 bg-white/[0.06] px-3 py-1.5 text-[11px] font-semibold text-slate-200 hover:bg-white/10 disabled:opacity-40"
                >
                  {samBusy ? <Loader2 size={13} className="animate-spin" /> : <Sparkles size={13} />}
                  {zh ? '生成系统证据' : 'Generate system evidence'}
                </button>
              )}
              {simpleVideoMode && points.length >= 3 && (
                <span className="inline-flex items-center gap-1.5 rounded-lg border border-white/10 bg-white/[0.04] px-3 py-1.5 text-[11px] text-slate-300">
                  {saving ? <Loader2 size={13} className="animate-spin" /> : <Check size={13} className="text-emerald-300" />}
                  {saving
                    ? (zh ? '完整遮罩自动保存中' : 'Autosaving complete masks')
                    : completeMaskAutosaved
                      ? (zh ? '完整遮罩已自动保存' : 'Complete masks autosaved')
                      : (zh ? '完整遮罩将自动保存' : 'Complete masks will autosave')}
                </span>
              )}
              <button
                type="button"
                onClick={toggleHistoryPanel}
                className={`flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-[11px] font-semibold ${
                  historyOpen
                    ? 'border-sky-300/60 bg-sky-500/20 text-sky-100'
                    : 'border-white/15 bg-white/[0.04] text-slate-300 hover:bg-white/10'
                }`}
                title={zh ? '默认关闭，按需查看并恢复完整遮罩版本' : 'Closed by default; open to inspect and restore complete mask versions'}
              >
                <History size={13} />
                {zh ? '历史记录' : 'History'}{historyOpen && maskHistory.length ? ` (${maskHistory.length})` : ''}
              </button>
              {!simpleVideoMode && (
                <>
                  <button
                    type="button"
                    disabled={saving}
                    onClick={() => void handleClear()}
                    className="flex items-center gap-1.5 rounded-lg border border-white/15 px-3 py-1.5 text-[11px] text-slate-300 hover:bg-white/5"
                  >
                    <Trash2 size={13} />
                    {zh ? '清除' : 'Clear'}
                  </button>
                  <button
                    type="button"
                    disabled={lumenSaving || (!lumenBox && !lumenOverride)}
                    onClick={() => void handleClearLumen()}
                    className="flex items-center gap-1.5 rounded-lg border border-white/15 px-3 py-1.5 text-[11px] text-slate-300 hover:bg-white/5 disabled:opacity-40"
                  >
                    <Trash2 size={13} />
                    {zh ? '清除胃腔' : 'Clear lumen'}
                  </button>
                </>
              )}
              {!inline && (
                <button
                  type="button"
                  onClick={() => setOpen(false)}
                  className="flex items-center gap-1.5 rounded-lg border border-cyan-400/30 bg-cyan-500/10 px-3 py-1.5 text-[11px] text-cyan-100"
                >
                  <Check size={13} />
                  {zh ? '完成并关闭' : 'Done'}
                </button>
              )}
              {!simpleVideoMode ? (
              <div className="ml-auto flex flex-col items-end gap-0.5 text-[10px] text-slate-400">
                <div className="flex items-center gap-2">
                  <ZoomIn size={12} />
                  <span>
                    {zh ? '当前层' : 'Layer'} {activeLayer === 'wall' ? wallPoints.length : points.length}pt
                    {wallPoints.length >= 3 ? `, ${zh ? '壁' : 'wall'}${wallPoints.length}` : ''}
                  </span>
                  {samAvailable === false && (
                    <span className="text-amber-300/90">
                      {zh ? '系统分析服务不可用' : 'Analysis service unavailable'}
                    </span>
                  )}
                </div>
              </div>
              ) : null}
            </div>
            {historyOpen && (
              <div className="shrink-0 border-t border-sky-300/20 bg-sky-950/20 px-4 py-2.5">
                <div className="mb-2 flex items-center justify-between gap-2">
                  <div className="flex items-center gap-1.5 text-[11px] font-semibold text-sky-100">
                    <History size={13} />
                    {zh ? '完整遮罩历史（各账号）' : 'Complete mask history (all accounts)'}
                  </div>
                  <button
                    type="button"
                    onClick={() => void loadMaskHistory()}
                    disabled={historyBusy}
                    className="rounded border border-white/15 px-2 py-1 text-[10px] text-slate-300 hover:bg-white/10 disabled:opacity-40"
                  >
                    {historyBusy ? (zh ? '读取中' : 'Loading') : (zh ? '刷新' : 'Refresh')}
                  </button>
                </div>
                {historyBusy && !maskHistory.length ? (
                  <div className="py-2 text-[10px] text-slate-400">{zh ? '正在读取历史版本…' : 'Loading saved versions…'}</div>
                ) : maskHistory.length ? (
                  <div className="workbench-scrollless max-h-44 space-y-1.5 overflow-y-auto pr-1">
                    {maskHistory.map((entry) => {
                      const frames = entry.override.video_frames || [];
                      const lastFrame = frames[frames.length - 1];
                      const latestLumenFrame = [...frames].reverse().find(
                        (frame) => frame.lumen_polygon?.length || frame.lumen_bbox,
                      );
                      const historyLumen = entry.lumen_override;
                      const previewing = historyPreviewId === entry.id;
                      return (
                        <div key={entry.id} className="rounded-lg border border-white/10 bg-black/30 px-2.5 py-2">
                          <div className="flex items-start justify-between gap-2">
                            <HistoryMaskThumbnail
                              entry={entry}
                              frameDataUrl={frameDataUrl}
                              mediaMode={mediaMode}
                              videoTime={videoTime}
                              zh={zh}
                            />
                            <div className="min-w-0 flex-1">
                              <div className="truncate text-[10px] text-slate-200">
                                {new Date(entry.saved_at).toLocaleString()}
                              </div>
                              <div className="mt-0.5 text-[9px] text-slate-500">
                                {entry.owner_account_id || entry.override.reviewer_id || (zh ? '未记账号' : 'unattributed')}
                                {entry.action ? ` / ${entry.action}` : ''}
                                {frames.length
                                  ? `, ${frames.length} ${zh ? '帧' : 'frames'}`
                                  : ''}
                              </div>
                            </div>
                            <div className="flex shrink-0 items-center gap-1">
                              <button
                                type="button"
                                disabled={historyBusy}
                                onClick={() => toggleHistoryPreview(entry)}
                                className="rounded border border-white/15 px-2 py-1 text-[10px] text-slate-300 hover:bg-white/10 disabled:opacity-40"
                              >
                                {previewing ? (zh ? '关闭预览' : 'Hide preview') : (zh ? '查看版本' : 'View version')}
                              </button>
                              <button
                                type="button"
                                disabled={saving || historyBusy}
                                onClick={() => void restoreMaskHistory(entry)}
                                className="rounded border border-sky-300/30 bg-sky-400/10 px-2 py-1 text-[10px] text-sky-100 hover:bg-sky-400/20 disabled:opacity-40"
                              >
                                {zh ? '恢复' : 'Restore'}
                              </button>
                              <button
                                type="button"
                                disabled={
                                  historyBusy
                                  || !accountReaderId
                                  || Boolean(entry.owner_account_id && entry.owner_account_id !== accountReaderId)
                                }
                                onClick={() => void deleteMaskHistoryEntry(entry)}
                                className="rounded border border-red-400/30 bg-red-500/10 px-2 py-1 text-[10px] text-red-200 hover:bg-red-500/20 disabled:opacity-40"
                                title={
                                  entry.owner_account_id && entry.owner_account_id !== accountReaderId
                                    ? (zh ? '只能删除自己的版本' : 'You can delete only your own version')
                                    : (accountReaderId ? (zh ? '删除自己的该版本' : 'Delete your version') : (zh ? '请先登录账号' : 'Sign in first'))
                                }
                              >
                                {zh ? '删除' : 'Delete'}
                              </button>
                            </div>
                          </div>
                          {previewing && (
                            <div className="mt-2 space-y-1 border-t border-white/10 pt-2 text-[9px] leading-relaxed text-slate-400">
                              <div className="flex flex-wrap gap-x-3 gap-y-0.5">
                                <span>{zh ? `病灶分割 ${entry.override.mask_polygon?.length || 0} 点` : `Lesion mask ${entry.override.mask_polygon?.length || 0} points`}</span>
                                <span>{zh ? `病灶框 ${formatHistoryBox(entry.override.roi_bbox)}` : `Lesion box ${formatHistoryBox(entry.override.roi_bbox)}`}</span>
                                <span>{zh ? `胃壁 ${entry.override.wall_polygon?.length || 0} 点` : `Wall ${entry.override.wall_polygon?.length || 0} points`}</span>
                              </div>
                              <div className="flex flex-wrap gap-x-3 gap-y-0.5">
                                <span>{zh ? `胃腔分割 ${latestLumenFrame?.lumen_polygon?.length || historyLumen?.lumen_polygon?.length || 0} 点` : `Lumen mask ${latestLumenFrame?.lumen_polygon?.length || historyLumen?.lumen_polygon?.length || 0} points`}</span>
                                <span>{zh ? `胃腔框 ${formatHistoryBox(latestLumenFrame?.lumen_bbox || historyLumen?.lumen_bbox)}` : `Lumen box ${formatHistoryBox(latestLumenFrame?.lumen_bbox || historyLumen?.lumen_bbox)}`}</span>
                              </div>
                              {lastFrame && (
                                <div className="rounded border border-white/10 bg-white/[0.03] px-2 py-1">
                                  <div className="text-slate-300">
                                    {zh ? '末帧' : 'Last frame'}: {lastFrame.frame_index ?? '—'} / {lastFrame.timestamp_sec.toFixed(3)}s
                                  </div>
                                  <div className="mt-0.5 flex flex-wrap gap-x-3 gap-y-0.5">
                                    <span>{zh ? `病灶分割 ${lastFrame.mask_polygon?.length || 0} 点` : `Lesion mask ${lastFrame.mask_polygon?.length || 0} points`}</span>
                                    <span>{zh ? `病灶框 ${formatHistoryBox(lastFrame.roi_bbox)}` : `Lesion box ${formatHistoryBox(lastFrame.roi_bbox)}`}</span>
                                    <span>{zh ? `胃腔分割 ${lastFrame.lumen_polygon?.length || 0} 点` : `Lumen mask ${lastFrame.lumen_polygon?.length || 0} points`}</span>
                                    <span>{zh ? `胃腔框 ${formatHistoryBox(lastFrame.lumen_bbox)}` : `Lumen box ${formatHistoryBox(lastFrame.lumen_bbox)}`}</span>
                                  </div>
                                </div>
                              )}
                              <div className="text-slate-500">
                                {zh ? '查看只显示历史预览，不会替换当前可编辑轮廓；确认后点击“恢复”。' : 'View shows a non-destructive history preview without replacing the editable contour; click Restore to apply it.'}
                              </div>
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                ) : (
                  <div className="py-2 text-[10px] text-slate-500">
                    {zh ? '此例各账号都还没有已保存的完整遮罩' : 'No saved complete masks from any account for this case'}
                  </div>
                )}
              </div>
            )}
            {!simpleVideoMode && samReport && (
              <div className="border-t border-white/10 bg-black px-4 py-3 text-[11px] text-slate-200">
                <div className="font-semibold text-slate-100">{zh ? '系统证据（辅助意见）' : 'System evidence (assistive)'}</div>
                <div className="mt-1 flex flex-wrap gap-3 text-[10px] text-slate-400">
                  <span>{zh ? '推荐' : 'Recommendation'}: {samReport.recommended_stage || '—'}</span>
                  <span>{zh ? '置信度' : 'Confidence'}: {samReport.calibrated_confidence != null ? `${Math.round(samReport.calibrated_confidence * 100)}%` : '—'}</span>
                  <span>{zh ? '证据' : 'Evidence'}: {samReport.evidence?.length || 0}</span>
                  <span>{zh ? '相似病例' : 'Similar cases'}: {samReport.similar_cases?.length || 0}</span>
                </div>
                {samReport.summary ? <div className="mt-2 leading-relaxed text-slate-300">{sanitizeSystemCopy(samReport.summary)}</div> : null}
                <div className="mt-2 text-[10px] text-amber-200/80">{zh ? '仅供医生复核，不覆盖最终判断；证据不足时请继续查看连续帧。' : 'For clinician review only; does not overwrite final judgment.'}</div>
              </div>
            )}
            {analysisContourUnrefined ? (
              <div className="border-t border-amber-400/25 bg-amber-500/10 px-4 py-2 text-[11px] text-amber-100">
                {uncorrectedContourNote(zh)}
              </div>
            ) : null}
            {wallPaintMode ? (
              <div className="border-t border-amber-400/20 bg-amber-500/10 px-4 py-2 text-[11px] leading-relaxed text-amber-50">
                <span className="font-semibold">{zh ? anatomyTargetMeta(wallLayerTarget).lineZh : anatomyTargetMeta(wallLayerTarget).lineEn}</span>
                <div className="mt-1.5 flex flex-wrap items-center gap-1">
                  {WALL_VISIBILITY_OPTIONS.map((option) => (
                    <button
                      key={option.id}
                      type="button"
                      onClick={() => applyPromptMetaLive(option.id, serosaAnchorMode)}
                      className={`rounded px-1.5 py-0.5 text-[10px] font-semibold ${
                        wallVisibility === option.id
                          ? 'bg-amber-200 text-slate-900'
                          : 'border border-amber-200/30 bg-black/20 text-amber-50'
                      }`}
                    >
                      {zh ? option.zh : option.en}
                    </button>
                  ))}
                  {SEROSA_ANCHOR_OPTIONS.map((option) => (
                    <button
                      key={option.id}
                      type="button"
                      onClick={() => applyPromptMetaLive(wallVisibility, option.id)}
                      className={`rounded px-1.5 py-0.5 text-[10px] font-semibold ${
                        serosaAnchorMode === option.id
                          ? 'bg-sky-200 text-slate-900'
                          : 'border border-sky-200/30 bg-black/20 text-sky-50'
                      }`}
                    >
                      {zh ? option.zh : option.en}
                    </button>
                  ))}
                </div>
              </div>
            ) : null}
            {wallPickMode ? (
              <div className="border-t border-amber-400/20 bg-amber-500/10 px-4 py-2 text-[11px] leading-relaxed text-amber-50">
                <span className="font-semibold">{zh ? '胃壁延长（点选）' : 'Wall extension (pick)'}</span>
                <span className="ml-1 text-amber-100/80">
                  {zh
                    ? (wallPickFlanks.length >= 1
                      ? '已点一侧。请再点对侧看得见的胃壁。'
                      : '请点两侧看得见的胃壁。未点两侧时不会从肿块正中自动接。')
                    : (wallPickFlanks.length >= 1
                      ? 'First flank marked. Click the opposite visible wall.'
                      : 'Click the two visible wall flanks. The wall is not invented in the mass center.')}
                </span>
                <button
                  type="button"
                  className="ml-2 rounded border border-amber-200/40 px-1.5 py-0.5 text-[10px] text-amber-50 hover:bg-amber-400/20"
                  onClick={() => {
                    wallPickModeRef.current = false;
                    setWallPickMode(false);
                    applyWallExtension();
                  }}
                >
                  {zh ? '自动接' : 'Auto-join'}
                </button>
                <button
                  type="button"
                  className="ml-1 rounded border border-white/20 px-1.5 py-0.5 text-[10px] text-amber-50/80 hover:bg-white/10"
                  onClick={() => {
                    wallPickModeRef.current = false;
                    wallPickFlanksRef.current = [];
                    setWallPickMode(false);
                    setWallPickFlanks([]);
                    setMessage('');
                    redrawRef.current?.();
                  }}
                >
                  {zh ? '取消' : 'Cancel'}
                </button>
              </div>
            ) : null}
            {wallLayerReadout && !hideWallOnOtherFrames && (wallLayerReadout.layersBreached > 0 || (wallLayerReadout.paintedLayers || 0) > 0) ? (
              <div className="border-t border-sky-400/20 bg-sky-500/10 px-4 py-2 text-[11px] leading-relaxed text-sky-50">
                <span className="font-semibold">{zh ? '预期线草稿' : 'Trajectory draft'}</span>
                <span className="ml-1">
                  {zh
                    ? `${wallLayerReadout.targetLayers ? `${anatomyTargetMeta(wallLayerReadout.targetLayers).lineZh}。` : ''}${
                      wallLayerReadout.interrupts?.length
                        ? `${wallLayerReadout.interrupts.map((item) => `${item.nameZh}${verdictLabel(item.verdict, true)}`).join('，')}。`
                        : ''
                    }${wallLayerReadout.mucosaBreached ? '黏膜层已受累。' : ''}${wallLayerReadout.layersBreached > 0 && !wallLayerReadout.interrupts?.length ? `最深到${wallLayerReadout.deepestZh}${wallLayerReadout.extraserosal ? '，并越过外缘' : ''}。` : ''}`
                    : `${wallLayerReadout.targetLayers ? `${anatomyTargetMeta(wallLayerReadout.targetLayers).lineEn}. ` : ''}${
                      wallLayerReadout.interrupts?.length
                        ? `${wallLayerReadout.interrupts.map((item) => `${item.nameEn} ${verdictLabel(item.verdict, false)}`).join(', ')}. `
                        : ''
                    }${wallLayerReadout.mucosaBreached ? 'Mucosa involved. ' : ''}${wallLayerReadout.layersBreached > 0 && !wallLayerReadout.interrupts?.length ? `Deepest ${wallLayerReadout.deepestEn}${wallLayerReadout.extraserosal ? ', past the outer edge' : ''}.` : ''}`}
                </span>
                {wallLayerReadout.ticks?.length ? (
                  <span className="ml-1 inline-flex flex-wrap gap-1">
                    {wallLayerReadout.ticks.map((tick) => (
                      <span
                        key={tick.layer}
                        className={`rounded px-1.5 py-0.5 text-[10px] ${
                          tick.status === 'absent' || tick.status === 'imaginary'
                            ? 'bg-rose-400/20 text-rose-100'
                            : tick.status === 'thinned'
                              ? 'bg-amber-400/20 text-amber-100'
                              : tick.status === 'unseen'
                                ? 'bg-white/10 text-slate-300'
                                : 'bg-emerald-400/15 text-emerald-100'
                        }`}
                      >
                        {zh ? `${tick.nameZh} ${tick.labelZh}` : `${tick.nameEn} ${tick.labelEn}`}
                      </span>
                    ))}
                  </span>
                ) : null}
                <span className="ml-1 text-sky-100/80">{zh ? wallLayerReadout.noteZh : wallLayerReadout.noteEn}</span>
              </div>
            ) : null}
            {!hideWallOnOtherFrames && wallEchoClarify?.available ? (
              <div className="border-t border-pink-400/25 bg-pink-500/10 px-4 py-2 text-[11px] leading-relaxed text-pink-50">
                <span className="font-semibold">{zh ? '最深窄带回声（草稿）' : 'Deepest-band echo (draft)'}</span>
                <span className="ml-1">{zh ? wallEchoClarify.noteZh : wallEchoClarify.noteEn}</span>
                <span className="ml-2 inline-flex items-center gap-2 align-middle">
                  {echoPreview.raw ? (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img
                      src={echoPreview.raw}
                      alt=""
                      className="h-8 w-16 rounded border border-white/20 object-cover"
                      title={zh ? '原图窄带' : 'Raw narrow band'}
                    />
                  ) : null}
                  {echoPreview.clustered ? (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img
                      src={echoPreview.clustered}
                      alt=""
                      className="h-8 w-16 rounded border border-pink-200/40 object-cover"
                      title={zh ? '亮/中/暗区域聚类' : 'Bright / mid / dark regions'}
                    />
                  ) : null}
                  <span className="rounded bg-black/30 px-1.5 py-0.5 font-mono text-[10px] text-pink-100">
                    {zh ? wallEchoClarify.patternZh : wallEchoClarify.patternEn}
                  </span>
                </span>
              </div>
            ) : null}
            {!hideWallOnOtherFrames && wallExtensionNote ? (
              <div className="border-t border-amber-400/20 bg-amber-500/10 px-4 py-2 text-[11px] leading-relaxed text-amber-50">
                <span className="font-semibold">{zh ? '胃壁延长（草稿）' : 'Wall extension (draft)'}</span>
                {wallExtensionStats?.overshootPx != null && wallExtensionStats.overshootPx > 1
                  ? (zh
                    ? `  超出约 ${wallExtensionStats.overshootPx} px。`
                    : `  Overshoot about ${wallExtensionStats.overshootPx} px.`)
                  : wallExtensionStats?.remainPx != null
                    ? (zh
                      ? `  尚未明显超出，剩余约 ${wallExtensionStats.remainPx} px。`
                      : `  Not clearly past the line; about ${wallExtensionStats.remainPx} px remains.`)
                    : ''}
                <span className="ml-1 text-amber-100/80">{wallExtensionNote}</span>
              </div>
            ) : null}
            {message ? (
              <div className="border-t border-white/5 px-3 py-1 text-[10px] leading-snug text-slate-400">{message}</div>
            ) : null}
            <ViewingTraceDock
              zh={zh}
              sessionId={viewingTraceSessionId}
              eventCount={viewingTraceEventCount}
              actions={viewingTraceActions}
              onRefresh={refreshViewingTraceActions}
              onReview={submitViewingTraceReview}
            />
          </div>
        </div>
  ) : null;

  return (
    <>
      {!inline && (<div className="pointer-events-auto absolute bottom-[5.75rem] left-3 z-[110] flex flex-col gap-2">
        <button
          type="button"
          onClick={() => openEditor({ sam: true })}
          className={`flex items-center gap-2 rounded-xl border px-3 py-2 text-[11px] font-semibold shadow-lg backdrop-blur transition hover:-translate-y-0.5 ${
            override
              ? 'border-cyan-400/50 bg-cyan-500/20 text-cyan-100'
              : 'border-white/15 bg-black/70 text-gray-200 hover:border-cyan-400/40'
          }`}
          title={zh ? '打开边界工具' : 'Open boundary tools'}
        >
          <Pencil size={14} />
          <span>{zh ? '边界工具' : 'Boundary tools'}</span>
          {override && (
            <span className="rounded-full bg-cyan-400/20 px-1.5 py-0.5 text-[9px] text-cyan-200">
              {override.mask_polygon.length}pt
            </span>
          )}
        </button>
        <button
          type="button"
          onClick={() => openEditor({ videoSam: true })}
          className="flex items-center gap-2 rounded-xl border border-white/15 bg-black/75 px-3 py-2 text-[11px] font-semibold text-slate-200 shadow-lg backdrop-blur transition hover:-translate-y-0.5 hover:border-white/30"
          title={zh ? '直接打开本例对应视频工具' : 'Open matched patient video tools'}
        >
          <Video size={14} />
          <span>{zh ? '视频工具' : 'Video tools'}</span>
        </button>
      </div>)}
      <ExplainableAnalysis
        patient={patient}
        isOpen={showExplainable}
        onClose={() => setShowExplainable(false)}
        onAnalysisComplete={onExplainableComplete}
        buildFramePayload={buildExplainableFramePayload}
      />
      {typeof document !== 'undefined' && !inline ? createPortal(modal, document.body) : modal}
      <AssistAnalysisModal
        open={assistOverlayOpen || Boolean(unifiedAgentBusy && taskProgress)}
        zh={zh}
        step={taskProgress?.step || 1}
        totalSteps={taskProgress?.totalSteps || ASSIST_ANALYSIS_STEPS.length}
        detail={taskProgress?.detail || null}
        elapsedSec={taskElapsedSec}
      />
      <DinoRoiLayerDialog
        open={dinoDockOpen}
        busy={dinoBusy}
        zh={zh}
        result={dinoResult}
        activeLayer={activeDinoLayer}
        onSelectLayer={setActiveDinoLayer}
        onClose={() => setDinoDockOpen(false)}
      />
    </>
  );
}
