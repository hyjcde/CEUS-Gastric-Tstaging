'use client';

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useSearchParams } from 'next/navigation';
import toast from 'react-hot-toast';
import {
  ArrowLeft, ExternalLink, Loader2, RefreshCw, ScanSearch,
} from 'lucide-react';
import { ReaderCaseSidebar, type CaseSummary } from '@/components/reader/ReaderCaseSidebar';
import { ReaderToolbar } from '@/components/reader/ReaderToolbar';
import { ReaderViewer } from '@/components/reader/ReaderViewer';
import { ReaderReportPanel } from '@/components/reader/ReaderReportPanel';
import { ReaderTimeline } from '@/components/reader/ReaderTimeline';
import { ReaderEvidencePanel } from '@/components/reader/ReaderEvidencePanel';
import { readerMediaUrl } from '@/lib/reader/media-url';
import {
  captureVideoFrameB64,
  fetchNnInteractiveStatus,
  fetchSamStatus,
  llmReportConfigured,
  runNnInteractiveRefine,
  runSamAnalyze,
  runSamVideoPropagation,
  strokeToNnInteractivePayload,
  type SamVideoPropagationResult,
} from '@/lib/reader/sam-client';
import type {
  InteractionMode,
  NnInteractiveStatus,
  ReaderCase,
  ReaderCohort,
  SamBackendStatus,
  SamBox,
  SamClick,
  ReaderPromptStroke,
  ReaderDoctorAction,
  SamReport,
} from '@/lib/reader/types';
import type { AgentAnalysisResponse } from '@/types';
import type { LayerAnalyzeResult } from '@/lib/human-assist/load-contact-geom';
import type { GcUsReportState } from '@/lib/gc-us-report-template';
import { buildReadingAgentUrl, getReadingAgentPageUrl } from '@/lib/reading-agent-url';
import { navigateTo } from '@/lib/navigation';

const TRACK_INTERVAL_MS = 1000;
const VIDEO_SPEEDS = [0.25, 0.5, 1] as const;
const DEFAULT_VIDEO_SPEED = 0.25;
const VIDEO_SPEED_STORAGE_KEY = 'gastric-next-reader-video-speed';
type AuditEventType =
  | 'session_start'
  | 'session_end'
  | 'ai_suggestion'
  | 'report_generated'
  | 'doctor_action'
  | 'frame_viewed'
  | 'error';

function newAuditId(prefix: string) {
  const random = typeof crypto !== 'undefined' && 'randomUUID' in crypto
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  return `${prefix}-${random}`;
}

function seekVideoForEvidence(video: HTMLVideoElement, time: number): Promise<void> {
  return new Promise((resolve) => {
    const done = () => {
      video.removeEventListener('seeked', done);
      resolve();
    };
    video.addEventListener('seeked', done, { once: true });
    video.currentTime = time;
    window.setTimeout(done, 1200);
  });
}

async function copyReaderText(text: string): Promise<boolean> {
  if (typeof navigator !== 'undefined' && navigator.clipboard?.writeText) {
    try {
      await navigator.clipboard.writeText(text);
      return true;
    } catch {
      // Fall through to the legacy clipboard path when permission is unavailable.
    }
  }

  if (typeof document === 'undefined' || !document.body) return false;
  const textarea = document.createElement('textarea');
  textarea.value = text;
  textarea.setAttribute('readonly', '');
  textarea.style.position = 'fixed';
  textarea.style.opacity = '0';
  document.body.appendChild(textarea);
  textarea.select();
  try {
    return document.execCommand('copy');
  } catch {
    return false;
  } finally {
    textarea.remove();
  }
}

async function writeReaderAuditEvent(event: {
  event_type: AuditEventType;
  session_id: string;
  case_id: string;
  reader_id?: string;
  round?: string;
  patient_id?: string;
  payload?: Record<string, unknown>;
}) {
  try {
    await fetch('/api/reader-audit/events', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        ...event,
        client_recorded_at: new Date().toISOString(),
      }),
      keepalive: event.event_type === 'session_end',
    });
  } catch {
    // Audit recording must not interrupt clinical reading.
  }
}

export function ReaderWorkbench() {
  const searchParams = useSearchParams();

  const [cohort, setCohort] = useState<ReaderCohort>(
    (searchParams.get('cohort') as ReaderCohort) || 'all',
  );
  const [caseSummaries, setCaseSummaries] = useState<CaseSummary[]>([]);
  const [selectedCase, setSelectedCase] = useState<ReaderCase | null>(null);
  const [frameIndex, setFrameIndex] = useState(0);
  const [casesLoading, setCasesLoading] = useState(true);

  const [samStatus, setSamStatus] = useState<SamBackendStatus | null>(null);
  const [nnInteractiveStatus, setNnInteractiveStatus] = useState<NnInteractiveStatus | null>(null);
  const [nnInteractiveBusy, setNnInteractiveBusy] = useState(false);
  const [interactionMode, setInteractionMode] = useState<InteractionMode>('box');
  const [clicks, setClicks] = useState<SamClick[]>([]);
  const [promptStrokes, setPromptStrokes] = useState<ReaderPromptStroke[]>([]);
  const [box, setBox] = useState<SamBox | null>(null);
  const [maskPolygon, setMaskPolygon] = useState<number[][] | null>(null);
  const [maskOverlayPng, setMaskOverlayPng] = useState<string | null>(null);
  const [report, setReport] = useState<SamReport | null>(null);
  const [unifiedAgentResult, setUnifiedAgentResult] = useState<AgentAnalysisResponse | null>(null);
  const [unifiedAgentBusy, setUnifiedAgentBusy] = useState(false);
  const [unifiedAgentError, setUnifiedAgentError] = useState<string | null>(null);
  const [gcUsReport, setGcUsReport] = useState<GcUsReportState | null>(null);
  const [samScore, setSamScore] = useState<number | null>(null);
  const [showMask, setShowMask] = useState(true);
  const [maskOpacity, setMaskOpacity] = useState(0.3);
  const [samBusy, setSamBusy] = useState(false);
  const [reportBusy, setReportBusy] = useState(false);
  const [isPlaying, setIsPlaying] = useState(false);
  const [playbackRate, setPlaybackRate] = useState<number>(() => {
    if (typeof window === 'undefined') return DEFAULT_VIDEO_SPEED;
    const saved = Number(window.localStorage.getItem(VIDEO_SPEED_STORAGE_KEY));
    return VIDEO_SPEEDS.some((speed) => speed === saved) ? saved : DEFAULT_VIDEO_SPEED;
  });
  const [trackOnPlay, setTrackOnPlay] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [frameSize, setFrameSize] = useState<{ width: number; height: number } | null>(null);
  const [frameDataUrl, setFrameDataUrl] = useState<string | null>(null);
  const [layerResult, setLayerResult] = useState<LayerAnalyzeResult | null>(null);
  const [badge, setBadge] = useState<string | null>(null);
  const [bundleVersion, setBundleVersion] = useState<string | undefined>();
  const [videoTrack, setVideoTrack] = useState<SamVideoPropagationResult | null>(null);
  const [videoTrackBusy, setVideoTrackBusy] = useState(false);
  const [videoTrackStatus, setVideoTrackStatus] = useState<string | null>(null);

  const videoRef = useRef<HTMLVideoElement | null>(null);
  const trackBusyRef = useRef(false);
  const lastTrackRef = useRef(0);
  const videoTrackRequestRef = useRef(0);
  const lastVideoTrackFrameRef = useRef<number | null>(null);
  const llmDebounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const trackingClientIdRef = useRef(`reader_${Math.random().toString(36).slice(2)}`);
  const nnInteractiveSessionRef = useRef({ key: '', id: '', initialized: false });
  const runSamRef = useRef<(opts?: {
    llmReport?: boolean;
    silent?: boolean;
    clicks?: SamClick[];
    box?: SamBox | null;
    resetTracking?: boolean;
  }) => Promise<void>>(async () => {});
  const auditSessionRef = useRef<string | null>(null);
  const auditCaseRef = useRef<string | null>(null);
  const auditSuggestionRef = useRef<string | null>(null);
  const gcUsAuditSignatureRef = useRef<string | null>(null);
  const auditStartedAtRef = useRef<number | null>(null);
  const lastAuditFrameRef = useRef(0);
  const initialCaseSelectionRef = useRef(false);
  const caseLoadRequestRef = useRef(0);
  const caseSelectionRequestRef = useRef(0);
  const loadedCohortRef = useRef<ReaderCohort | null>(null);
  const ignoreDeepCaseRef = useRef(false);
  const externalVideo = searchParams.get('video') || '';
  const externalImage = searchParams.get('image') || '';
  const deepCaseId = searchParams.get('case') || '';
  const patientIdParam = searchParams.get('patient_id') || '';
  const readerIdParam = searchParams.get('reader_id') || 'unknown_reader';
  const roundParam = searchParams.get('round') || 'round2';
  const callbackUrl = searchParams.get('callback') || '';
  const effectiveDeepCaseId = ignoreDeepCaseRef.current ? '' : deepCaseId;
  const effectivePatientIdParam = ignoreDeepCaseRef.current ? '' : patientIdParam;
  const activeCaseId = selectedCase?.case_id || effectiveDeepCaseId || effectivePatientIdParam || 'external';
  const hasExternalMedia = Boolean(externalVideo || externalImage);

  const llmReady = llmReportConfigured(samStatus);
  const hasPrompt = Boolean(box) || clicks.length > 0;

  const updatePlaybackRate = (value: number) => {
    const next = VIDEO_SPEEDS.find((speed) => speed === value) || DEFAULT_VIDEO_SPEED;
    setPlaybackRate(next);
    try {
      window.localStorage.setItem(VIDEO_SPEED_STORAGE_KEY, String(next));
    } catch {
      // Browser storage is optional.
    }
  };

  const recordAudit = useCallback(
    (
      eventType: AuditEventType,
      payload: Record<string, unknown> = {},
      overrides: { sessionId?: string; caseId?: string; patientId?: string } = {},
    ) => {
      const sessionId = overrides.sessionId || auditSessionRef.current;
      const caseId = overrides.caseId || auditCaseRef.current || activeCaseId;
      if (!sessionId || !caseId) return;
      void writeReaderAuditEvent({
        event_type: eventType,
        session_id: sessionId,
        case_id: caseId,
        reader_id: readerIdParam,
        round: roundParam,
        patient_id: overrides.patientId || selectedCase?.patient_id || patientIdParam || caseId,
        payload,
      });
    },
    [activeCaseId, patientIdParam, readerIdParam, roundParam, selectedCase?.patient_id],
  );

  const handleGcUsEvidenceState = useCallback((state: GcUsReportState) => {
    setGcUsReport(state);
    if (!state.report.doctor_edited) return;
    const signature = JSON.stringify({
      signs: state.signs,
      reference_stage: state.reference_stage,
    });
    if (gcUsAuditSignatureRef.current === signature) return;
    gcUsAuditSignatureRef.current = signature;
    recordAudit('doctor_action', {
      action_id: newAuditId('report-signs'),
      action_type: 'modify',
      template_id: state.template_id,
      schema_version: state.schema_version,
      signs: state.signs,
      reference_stage: state.reference_stage,
      conflicts: state.conflicts,
    });
  }, [recordAudit]);

  const currentFrame = selectedCase?.frames?.[frameIndex] || selectedCase?.frames?.[0];
  const videoSrc = useMemo(() => {
    if (externalVideo) return externalVideo;
    if (currentFrame?.video_rel) return readerMediaUrl(currentFrame.video_rel, bundleVersion);
    return '';
  }, [bundleVersion, currentFrame?.video_rel, externalVideo]);
  const trackingSessionId = useMemo(() => {
    if (!videoSrc) return '';
    const raw = `${trackingClientIdRef.current}__${activeCaseId}__${videoSrc}`;
    return raw.replace(/[^A-Za-z0-9_-]+/g, '_').slice(0, 160);
  }, [activeCaseId, videoSrc]);

  const nearestVideoTrackFrame = useMemo(() => {
    const frames = videoTrack?.frames || [];
    if (!frames.length) return null;
    return frames.reduce((nearest, frame) => (
      Math.abs(frame.frame_time - currentTime) < Math.abs(nearest.frame_time - currentTime)
        ? frame
        : nearest
    ), frames[0]);
  }, [currentTime, videoTrack]);

  const promptSummary = useMemo(() => {
    const pos = clicks.filter((c) => c.label !== 'negative').length;
    const neg = clicks.filter((c) => c.label === 'negative').length;
    const parts: string[] = [];
    if (box) parts.push('1 框');
    if (pos || neg) parts.push(`${pos} 正 / ${neg} 负`);
    const scribbleCount = promptStrokes.filter((stroke) => stroke.kind === 'scribble').length;
    const lassoCount = promptStrokes.filter((stroke) => stroke.kind === 'lasso').length;
    if (scribbleCount) parts.push(`${scribbleCount} 涂鸦`);
    if (lassoCount) parts.push(`${lassoCount} 套索`);
    if (maskPolygon?.length) {
      parts.push(samScore != null && samScore > 0
        ? `Mask 已生成 · ${Math.round(samScore * 100)}%`
        : 'Mask 已生成 · 分数不可用');
    } else if (samScore != null) {
      parts.push(`分割 ${Math.round(samScore * 100)}%`);
    }
    return parts.join(' · ');
  }, [box, clicks, maskPolygon, promptStrokes, samScore]);

  const loadCases = useCallback(async (c: ReaderCohort) => {
    const requestId = ++caseLoadRequestRef.current;
    loadedCohortRef.current = null;
    setCasesLoading(true);
    try {
      const res = await fetch(`/api/reader/cases?cohort=${encodeURIComponent(c)}`, { cache: 'no-store', signal: AbortSignal.timeout(15_000) });
      const data = await res.json();
      if (!data.ok) throw new Error(data.error || 'cases load failed');
      if (requestId !== caseLoadRequestRef.current) return;
      setCaseSummaries(data.cases || []);
      setBundleVersion(data.created_at);
    } catch (err) {
      if (requestId !== caseLoadRequestRef.current) return;
      toast.error(err instanceof Error ? err.message : '病例库加载失败');
    } finally {
      if (requestId === caseLoadRequestRef.current) {
        loadedCohortRef.current = c;
        setCasesLoading(false);
      }
    }
  }, []);

  const loadCaseDetail = useCallback(async (caseId: string) => {
    const requestId = ++caseSelectionRequestRef.current;
    if (auditSessionRef.current && auditCaseRef.current && auditCaseRef.current !== caseId) {
      recordAudit(
        'session_end',
        {
          elapsed_ms: auditStartedAtRef.current ? Date.now() - auditStartedAtRef.current : null,
          reason: 'case_changed',
        },
        { sessionId: auditSessionRef.current, caseId: auditCaseRef.current },
      );
    }
    try {
      const res = await fetch(`/api/reader/cases?case_id=${encodeURIComponent(caseId)}`, { cache: 'no-store', signal: AbortSignal.timeout(15_000) });
      const data = await res.json();
      if (!data.ok || !data.case) throw new Error('case not found');
      if (requestId !== caseSelectionRequestRef.current) return;
      const nextParams = new URLSearchParams(searchParams.toString());
      nextParams.set('case', caseId);
      nextParams.set('cohort', cohort);
      ['patient_id', 'video', 'image', 'frame_id', 'title'].forEach((key) => nextParams.delete(key));
      navigateTo(`/reader?${nextParams.toString()}`, { replace: true });
      ignoreDeepCaseRef.current = false;
      const sessionId = newAuditId('reader');
      auditSessionRef.current = sessionId;
      auditCaseRef.current = caseId;
      auditSuggestionRef.current = null;
      auditStartedAtRef.current = Date.now();
      lastAuditFrameRef.current = 0;
      setSelectedCase(data.case as ReaderCase);
      setFrameIndex(0);
      resetInteraction();
      recordAudit(
        'session_start',
        {
          cohort,
          round: roundParam,
          reader_id: readerIdParam,
          study_mode: data.case.study_mode,
          frame_count: data.case.frames?.length || 0,
          software_version: 'gastric_scan_next_reader',
        },
        { sessionId, caseId, patientId: data.case.patient_id },
      );
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '病例加载失败');
    }
  }, [cohort, readerIdParam, recordAudit, roundParam, searchParams]);

  const resetInteraction = () => {
    setClicks([]);
    setPromptStrokes([]);
    setInteractionMode('box');
    setBox(null);
    setMaskPolygon(null);
    setMaskOverlayPng(null);
    setReport(null);
    setUnifiedAgentResult(null);
    setUnifiedAgentError(null);
    setGcUsReport(null);
    gcUsAuditSignatureRef.current = null;
    setSamScore(null);
    setLayerResult(null);
    setBadge(null);
    setFrameDataUrl(null);
    setFrameSize(null);
    setVideoTrack(null);
    setVideoTrackStatus(null);
    videoTrackRequestRef.current += 1;
    lastVideoTrackFrameRef.current = null;
    setCurrentTime(0);
    setDuration(0);
    setIsPlaying(false);
    nnInteractiveSessionRef.current = { key: '', id: '', initialized: false };
  };

  useEffect(() => {
    loadCases(cohort);
  }, [cohort, loadCases]);

  useEffect(() => {
    fetchSamStatus().then(setSamStatus).catch(() => setSamStatus({ available: false }));
    fetchNnInteractiveStatus()
      .then(setNnInteractiveStatus)
      .catch((error) => setNnInteractiveStatus({
        available: false,
        error: error instanceof Error ? error.message : 'nnInteractive status unavailable',
      }));
  }, []);

  useEffect(() => () => {
    const sessionId = auditSessionRef.current;
    const caseId = auditCaseRef.current;
    if (!sessionId || !caseId) return;
    void writeReaderAuditEvent({
      event_type: 'session_end',
      session_id: sessionId,
      case_id: caseId,
      patient_id: selectedCase?.patient_id || patientIdParam || caseId,
      reader_id: readerIdParam,
      round: roundParam,
      payload: {
        elapsed_ms: auditStartedAtRef.current ? Date.now() - auditStartedAtRef.current : null,
        reason: 'unmount',
      },
    });
  }, [patientIdParam, readerIdParam, roundParam]);

  useEffect(() => {
    if (
      initialCaseSelectionRef.current
      || !caseSummaries.length
      || loadedCohortRef.current !== cohort
    ) return;
    const hasExternalDeepLink = Boolean(effectiveDeepCaseId || effectivePatientIdParam || externalVideo || externalImage);
    const deepCaseInCohort = effectiveDeepCaseId
      ? caseSummaries.some((item) => item.case_id === effectiveDeepCaseId)
      : false;
    const mappedPatientCase = effectivePatientIdParam
      ? caseSummaries.find((item) => item.patient_id === effectivePatientIdParam)?.case_id
      : undefined;
    const target = (deepCaseInCohort ? effectiveDeepCaseId : undefined)
      || mappedPatientCase
      || (hasExternalDeepLink ? undefined : caseSummaries[0]?.case_id);
    if (target) {
      initialCaseSelectionRef.current = true;
      void loadCaseDetail(target);
    } else if (hasExternalMedia) {
      // Keep an external media deep-link and create a session without inventing BM-001.
      const sessionId = newAuditId('reader');
      auditSessionRef.current = sessionId;
      auditCaseRef.current = activeCaseId;
      auditSuggestionRef.current = null;
      auditStartedAtRef.current = Date.now();
      lastAuditFrameRef.current = 0;
      initialCaseSelectionRef.current = true;
      recordAudit('session_start', {
        cohort,
        round: roundParam,
        reader_id: readerIdParam,
        study_mode: 'external_media',
        frame_count: 0,
        software_version: 'gastric_scan_next_reader',
      }, { sessionId, caseId: activeCaseId, patientId: effectivePatientIdParam || activeCaseId });
    } else if (hasExternalDeepLink) {
      // Never silently load BM-001 when an unmapped patient link is supplied.
      initialCaseSelectionRef.current = true;
      toast.error('深链未映射到阅片病例；未自动加载其他病例');
    }
  }, [
    activeCaseId,
    caseSummaries,
    cohort,
    effectiveDeepCaseId,
    effectivePatientIdParam,
    externalImage,
    externalVideo,
    hasExternalMedia,
    loadCaseDetail,
    readerIdParam,
    recordAudit,
    roundParam,
  ]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return;
      if (e.code === 'Space') {
        e.preventDefault();
        togglePlay();
      }
      if (e.key === '1') setInteractionMode('box');
      if (e.key === '2') setInteractionMode('inspect');
      if (e.key === '3') setInteractionMode('positive');
      if (e.key === '4') setInteractionMode('negative');
      if (e.key === '5') setInteractionMode('scribble');
      if (e.key === '6') setInteractionMode('lasso');
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  });

  const onVideoReady = useCallback((video: HTMLVideoElement) => {
    videoRef.current = video;
    lastVideoTrackFrameRef.current = null;
    try {
      video.defaultPlaybackRate = playbackRate;
    } catch {
      // Some remote browsers reject defaultPlaybackRate before media metadata is ready.
    }
    try {
      video.playbackRate = playbackRate;
    } catch {
      // Keep the reader usable even when the browser rejects the initial rate.
    }
    setFrameSize({ width: video.videoWidth, height: video.videoHeight });
    setDuration(video.duration || 0);
    try {
      const c = document.createElement('canvas');
      c.width = video.videoWidth;
      c.height = video.videoHeight;
      c.getContext('2d')?.drawImage(video, 0, 0);
      setFrameDataUrl(c.toDataURL('image/jpeg', 0.85));
    } catch {
      setFrameDataUrl(null);
    }
  }, [playbackRate]);

  const buildPayload = useCallback(
    (
      llmReport: boolean,
      clickOverride?: SamClick[],
      boxOverride?: SamBox | null,
      trackingReset = false,
    ) => {
      const video = videoRef.current;
      if (!video?.videoWidth) throw new Error('Video frame not ready');
      const useUpload = Boolean(externalVideo || externalImage || !currentFrame?.video_rel);
      const effectiveClicks = clickOverride ?? clicks;
      const effectiveBox = boxOverride !== undefined ? boxOverride : box;
      const payload = {
        case_id: activeCaseId,
        video_rel: useUpload ? '' : currentFrame?.video_rel,
        video_url: videoSrc || undefined,
        frame_time: video.currentTime || currentTime || 0,
        image_width: video.videoWidth,
        image_height: video.videoHeight,
        tracking_session_id: trackingSessionId || undefined,
        tracking_enabled: Boolean(videoSrc && trackingSessionId),
        tracking_reset: trackingReset,
        clicks: effectiveClicks.map((c) => ({ x: c.x, y: c.y, label: c.label })),
        box: effectiveBox || undefined,
        llm_report: llmReport,
        gc_us_report: gcUsReport || undefined,
      } as Parameters<typeof runSamAnalyze>[0];
      if (useUpload) {
        payload.frame_png_b64 = captureVideoFrameB64(video);
      }
      return payload;
    },
    [
      activeCaseId,
      box,
      clicks,
      currentFrame?.video_rel,
      currentTime,
      externalImage,
      externalVideo,
      gcUsReport,
      trackingSessionId,
      videoSrc,
    ],
  );

  const applySamResult = useCallback((result: Awaited<ReturnType<typeof runSamAnalyze>>, withReport: boolean) => {
    setMaskPolygon(result.mask_polygon || null);
    setMaskOverlayPng(result.mask_overlay_png || null);
    setSamScore(result.sam_score ?? null);
    nnInteractiveSessionRef.current = { key: '', id: '', initialized: false };
    const suggestionId = newAuditId('suggestion');
    auditSuggestionRef.current = suggestionId;
    if (withReport && result.report) {
      setReport({
        ...result.report,
        sam_score: result.sam_score,
        elapsed_ms: result.elapsed_ms,
      });
      const structured = result.report.structured;
      if (structured && typeof structured === 'object' && 'signs' in structured) {
        setGcUsReport(structured as unknown as GcUsReportState);
      }
    } else if (result.report) {
      setReport((prev) => ({
        ...(prev || {}),
        ...result.report,
        sam_score: result.sam_score,
        elapsed_ms: result.elapsed_ms,
      }));
      const structured = result.report.structured;
      if (structured && typeof structured === 'object' && 'signs' in structured) {
        setGcUsReport(structured as unknown as GcUsReportState);
      }
    }
    recordAudit(withReport ? 'report_generated' : 'ai_suggestion', {
      suggestion_id: suggestionId,
      frame_id: currentFrame?.media_token || currentFrame?.video_rel || null,
      frame_time: currentTime,
      input_source: currentFrame?.video_rel ? 'workstation_media' : 'uploaded_frame',
      sam_score: result.sam_score ?? null,
      elapsed_ms: result.elapsed_ms ?? null,
      prompt_meta: result.prompt_meta || null,
      recommended_stage: result.report?.recommended_stage || null,
      stage_distribution: result.report?.stage_distribution || null,
      calibrated_confidence: result.report?.calibrated_confidence ?? null,
      evidence: result.report?.evidence || [],
      toolchain: result.report?.toolchain || [],
      model: result.report?.llm_report?.model || null,
    });
    setBadge(result.mask_polygon?.length
      ? `Mask 已生成${result.sam_score && result.sam_score > 0 ? ` · ${Math.round(result.sam_score * 100)}%` : ' · 分数不可用'}`
      : '未生成 Mask');
  }, [currentFrame?.media_token, currentFrame?.video_rel, currentTime, recordAudit]);

  const runSam = useCallback(
    async (opts: {
      llmReport?: boolean;
      silent?: boolean;
      clicks?: SamClick[];
      box?: SamBox | null;
      resetTracking?: boolean;
    } = {}) => {
      const effectiveClicks = opts.clicks ?? clicks;
      const effectiveBox = opts.box !== undefined ? opts.box : box;
      const hasLocalPrompt = Boolean(effectiveBox) || effectiveClicks.length > 0;
      if (!hasLocalPrompt && !opts.llmReport) {
        if (!opts.silent) toast.error('请先框选区域或添加标注点');
        return;
      }
      setSamBusy(true);
      if (opts.llmReport) setReportBusy(true);
      try {
        const payload = buildPayload(
          Boolean(opts.llmReport),
          effectiveClicks,
          effectiveBox,
          Boolean(opts.resetTracking),
        );
        const wrapped = await runSamAnalyze(payload);
        applySamResult(wrapped, Boolean(opts.llmReport));
        if (!opts.silent) toast.success(`分割完成 · ${Math.round((wrapped.sam_score || 0) * 100)}%`);
        if (opts.llmReport) toast.success('文字报告已生成');
        else if (llmReady && hasLocalPrompt) {
          if (llmDebounceRef.current) clearTimeout(llmDebounceRef.current);
          llmDebounceRef.current = setTimeout(() => {
            runSamRef.current({ llmReport: true, silent: true, clicks: effectiveClicks, box: effectiveBox });
          }, 1500);
        }
        postCallbackIfNeeded(wrapped);
      } catch (err) {
        const msg = err instanceof Error ? err.message : 'SAM 失败';
        if (opts.llmReport) {
          setReport((prev) => ({
            ...(prev || {}),
            llm_report: { error: msg },
          }));
        }
        if (!opts.silent) toast.error(msg);
      } finally {
        setSamBusy(false);
        if (opts.llmReport) setReportBusy(false);
      }
    },
    [applySamResult, box, buildPayload, clicks, llmReady],
  );

  const runFullVideoTrack = useCallback(async () => {
    const video = videoRef.current;
    const videoRel = currentFrame?.video_rel;
    if (!video || !videoRel) {
      toast.error('当前病例没有可跟踪的视频');
      return;
    }
    if (!hasPrompt) {
      toast.error('请先框选或添加标注点');
      return;
    }
    const requestId = ++videoTrackRequestRef.current;
    const resumeAfterTrack = !video.paused;
    if (resumeAfterTrack) {
      video.pause();
      setIsPlaying(false);
    }
    setVideoTrackBusy(true);
    setVideoTrackStatus('SAM2.1 视频 memory 传播中…');
    try {
      const result = await runSamVideoPropagation({
        case_id: activeCaseId,
        video_rel: videoRel,
        frame_time: video.currentTime || currentTime,
        image_width: video.videoWidth,
        image_height: video.videoHeight,
        clicks,
        box,
        direction: 'both',
      });
      if (requestId !== videoTrackRequestRef.current) return;
      setVideoTrack(result);
      lastVideoTrackFrameRef.current = null;
      setVideoTrackStatus(result.needs_reanchor
        ? `传播中断，已接受 ${result.accepted_frames}/${result.num_frames} 帧；请重锚定`
        : `全视频 ${result.accepted_frames}/${result.num_frames} 帧已完成`);
      const nearest = result.frames.reduce((current, frame) => (
        Math.abs(frame.frame_time - (video.currentTime || currentTime)) < Math.abs(current.frame_time - (video.currentTime || currentTime))
          ? frame
          : current
      ), result.frames[0]);
      if (nearest?.mask_polygon?.length) setMaskPolygon(nearest.mask_polygon);
      recordAudit('ai_suggestion', {
        source: 'sam2.1_video_memory',
        status: result.status,
        accepted_frames: result.accepted_frames,
        total_frames: result.num_frames,
        elapsed_ms: result.elapsed_ms,
        direction_reports: result.direction_reports,
      });
      if (result.needs_reanchor) toast.error('跟踪扩散已在质量门处停止，请重新框选或点击重锚定');
      else toast.success(`跟踪扩散完成, ${result.accepted_frames}/${result.num_frames} 帧`);
    } catch (error) {
      if (requestId !== videoTrackRequestRef.current) return;
      setVideoTrackStatus('跟踪扩散失败');
      toast.error(error instanceof Error ? error.message : '跟踪扩散失败');
    } finally {
      if (requestId === videoTrackRequestRef.current) {
        setVideoTrackBusy(false);
        if (resumeAfterTrack) {
          void video.play().then(() => setIsPlaying(true)).catch(() => setIsPlaying(false));
        }
      }
    }
  }, [activeCaseId, box, clicks, currentFrame?.video_rel, currentTime, hasPrompt, recordAudit]);

  const runUnifiedAgent = useCallback(async () => {
    const video = videoRef.current;
    if (!selectedCase || !video?.videoWidth || !video.videoHeight) {
      toast.error('当前视频帧尚未准备好');
      return;
    }
    setUnifiedAgentBusy(true);
    setUnifiedAgentError(null);
    try {
      const originalTime = video.currentTime || currentTime;
      const durationSec = video.duration || duration;
      const frameSpan = durationSec > 0 ? Math.max(0.5, Math.min(2, durationSec / 8)) : 0;
      const positions = Array.from(new Set(
        [originalTime - frameSpan, originalTime, originalTime + frameSpan]
          .filter((time) => time >= 0 && (!durationSec || time < durationSec))
          .map((time) => Number(time.toFixed(3))),
      ));
      const wasPlaying = !video.paused;
      if (wasPlaying) video.pause();
      const evidenceFrames: Array<{
        frame_png_b64: string;
        frame_id: string;
        frame_index: number;
        timestamp_sec: number;
        quality_score: number;
      }> = [];
      for (const [index, position] of positions.entries()) {
        if (Math.abs(video.currentTime - position) > 0.01) {
          await seekVideoForEvidence(video, position);
        }
        evidenceFrames.push({
          frame_png_b64: captureVideoFrameB64(video),
          frame_id: `${currentFrame?.media_token || currentFrame?.video_rel || activeCaseId}:${position}`,
          frame_index: index,
          timestamp_sec: position,
          quality_score: 1,
        });
      }
      if (Math.abs(video.currentTime - originalTime) > 0.01) {
        await seekVideoForEvidence(video, originalTime);
      }
      setCurrentTime(originalTime);
      if (wasPlaying) void video.play().catch(() => {});
      const response = await fetch('/api/reader/agent/analyze', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          case_id: selectedCase.case_id,
          patient_id: selectedCase.patient_id || selectedCase.case_id,
          reader_id: readerIdParam,
          round: roundParam,
          study_mode: selectedCase.study_mode,
          frame_id: currentFrame?.media_token || currentFrame?.video_rel || null,
          frame_time: currentTime,
          frame_png_b64: evidenceFrames.find((frame) => Math.abs(frame.timestamp_sec - originalTime) < 0.01)?.frame_png_b64
            || evidenceFrames[0]?.frame_png_b64,
          frames: evidenceFrames,
          gc_us_report: gcUsReport || undefined,
          mask_override: maskPolygon?.length
            ? {
                patientId: selectedCase.patient_id || selectedCase.case_id,
                frameId: currentFrame?.media_token || currentFrame?.video_rel,
                imageWidth: video.videoWidth,
                imageHeight: video.videoHeight,
                mask_polygon: maskPolygon,
                roi_bbox: box || undefined,
                source: 'sam',
                video_time_sec: currentTime,
              }
            : undefined,
        }),
      });
      const data = await response.json() as {
        ok?: boolean;
        error?: string;
        result?: AgentAnalysisResponse;
      };
      if (!response.ok || !data.ok || !data.result) {
        throw new Error(data.error || `Unified Agent HTTP ${response.status}`);
      }
      setUnifiedAgentResult(data.result);
      recordAudit('ai_suggestion', {
        source: 'unified_agent_bridge',
        bridge_schema_version: 'reader_unified_agent_bridge_v1',
        frame_id: currentFrame?.media_token || currentFrame?.video_rel || null,
        frame_time: currentTime,
        recommended_stage: data.result.report?.recommended_t_stage || null,
        belief_state_schema_version: data.result.belief_state?.schema_version || null,
        next_action: data.result.belief_state?.next_actions?.[0]?.action_type || null,
      });
      toast.success('辅助诊断意见已更新');
    } catch (error) {
      const message = error instanceof Error ? error.message : '统一 Agent 分析失败';
      setUnifiedAgentError(message);
      toast.error(message);
    } finally {
      setUnifiedAgentBusy(false);
    }
  }, [
    activeCaseId,
    box,
    currentFrame?.media_token,
    currentFrame?.video_rel,
    currentTime,
    duration,
    gcUsReport,
    maskPolygon,
    readerIdParam,
    recordAudit,
    roundParam,
    selectedCase,
  ]);

  const runNextAgentAction = useCallback((actionType?: string) => {
    if (actionType === 'inspect_next_frame') {
      const video = videoRef.current;
      if (video && duration > 0) {
        const step = Math.max(0.5, Math.min(2, duration / 12));
        video.pause();
        const nextTime = Math.min(Math.max(0, duration - 0.02), video.currentTime + step);
        video.currentTime = nextTime;
        setCurrentTime(nextTime);
        window.setTimeout(() => void runUnifiedAgent(), 120);
        return;
      }
    }
    void runUnifiedAgent();
  }, [duration, runUnifiedAgent]);

  useEffect(() => {
    runSamRef.current = runSam;
  }, [runSam]);

  useEffect(() => {
    const frame = nearestVideoTrackFrame;
    if (!frame || videoTrackBusy || samBusy || lastVideoTrackFrameRef.current === frame.frame_index) return;
    lastVideoTrackFrameRef.current = frame.frame_index;
    if (frame.mask_polygon?.length) setMaskPolygon(frame.mask_polygon);
    setBadge(`视频传播 · ${Math.round(frame.quality_score * 100)}% · ${frame.frame_index + 1}/${videoTrack?.num_frames || 0}`);
  }, [nearestVideoTrackFrame, samBusy, videoTrack?.num_frames, videoTrackBusy]);

  const postCallbackIfNeeded = useCallback(async (result: Awaited<ReturnType<typeof runSamAnalyze>>) => {
    const url = callbackUrl || (typeof window !== 'undefined' ? `${window.location.origin}/api/reader-agent/result` : '');
    if (!url || !result.mask_polygon?.length) return;
    try {
      await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          case_id: activeCaseId,
          frame_id: searchParams.get('frame_id') || undefined,
          patient_id: selectedCase?.patient_id || patientIdParam || undefined,
          mask_polygon: result.mask_polygon,
          layer_label: layerResult?.layer?.label,
          t_hint: layerResult?.layer?.tHint,
          in_contact: layerResult?.inContact,
          ok: true,
        }),
      });
    } catch {
      /* optional write-back */
    }
  }, [
    activeCaseId,
    callbackUrl,
    layerResult?.inContact,
    layerResult?.layer?.label,
    layerResult?.layer?.tHint,
    patientIdParam,
    searchParams,
    selectedCase?.patient_id,
  ]);

  const runNnInteractive = useCallback(async (
    point?: SamClick,
    stroke?: ReaderPromptStroke,
  ) => {
    if (nnInteractiveStatus?.available !== true) {
      toast.error('nnInteractive 未连接，未切换到 SAM3.1');
      return;
    }
    const video = videoRef.current;
    if (!video?.videoWidth || !video.videoHeight) {
      toast.error('当前视频帧尚未就绪');
      return;
    }
    const initialPolygon = maskPolygon && maskPolygon.length >= 3
      ? maskPolygon
      : box
        ? [
          [box.x1, box.y1],
          [box.x2, box.y1],
          [box.x2, box.y2],
          [box.x1, box.y2],
        ]
        : null;
    if (!initialPolygon) {
      toast.error('请先框选病灶并生成初始轮廓');
      return;
    }
    if (!point && !stroke) return;

    const frameKey = [
      activeCaseId,
      currentFrame?.media_token || currentFrame?.video_rel || videoSrc,
      (video.currentTime || currentTime).toFixed(3),
    ].join(':');
    const session = nnInteractiveSessionRef.current;
    if (session.key !== frameKey || !session.id) {
      session.key = frameKey;
      session.id = `reader_nn_${activeCaseId}_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
      session.initialized = false;
    }
    setNnInteractiveBusy(true);
    try {
      const strokePayload = stroke ? strokeToNnInteractivePayload(stroke) : null;
      const result = await runNnInteractiveRefine({
        session_id: session.id,
        case_id: activeCaseId,
        frame_time: video.currentTime || currentTime || 0,
        frame_png_b64: captureVideoFrameB64(video),
        image_width: video.videoWidth,
        image_height: video.videoHeight,
        reset_session: !session.initialized,
        initial_mask_polygon: !session.initialized ? initialPolygon : [],
        points: point ? [point] : [],
        scribbles: strokePayload && stroke?.kind === 'scribble' ? [strokePayload] : [],
        lassos: strokePayload && stroke?.kind === 'lasso' ? [strokePayload] : [],
      });
      session.initialized = true;
      setMaskPolygon(result.mask_polygon || null);
      setMaskOverlayPng(null);
      setSamScore(null);
      setBadge(`nnInteractive 已生成 Mask${result.elapsed_ms ? `, ${Math.round(result.elapsed_ms)} ms` : ''}`);
      recordAudit('ai_suggestion', {
        backend_id: result.backend_id || 'nninteractive_remote_v1',
        model: result.model || 'nnInteractive_v1.0',
        prompt_meta: result.prompt_meta || null,
        elapsed_ms: result.elapsed_ms || null,
        frame_id: currentFrame?.media_token || currentFrame?.video_rel || null,
        frame_time: currentTime,
      });
      if (result.mask_polygon?.length) {
        await postCallbackIfNeeded({
          mask_polygon: result.mask_polygon,
          sam_score: undefined,
          elapsed_ms: result.elapsed_ms,
        });
      }
    } catch (error) {
      session.initialized = false;
      toast.error(error instanceof Error ? error.message : 'nnInteractive 推理失败');
    } finally {
      setNnInteractiveBusy(false);
    }
  }, [
    activeCaseId,
    box,
    currentFrame?.media_token,
    currentFrame?.video_rel,
    currentTime,
    maskPolygon,
    nnInteractiveStatus?.available,
    postCallbackIfNeeded,
    recordAudit,
    videoSrc,
  ]);

  const onAddClick = (click: SamClick) => {
    setVideoTrack(null);
    setVideoTrackStatus(null);
    lastVideoTrackFrameRef.current = null;
    if (interactionMode === 'positive' || interactionMode === 'negative') {
      if (nnInteractiveStatus?.available !== true) {
        toast.error('nnInteractive 未连接，正点和负点不会改走 SAM3.1');
        return;
      }
      setClicks((prev) => [...prev, click]);
      queueMicrotask(() => {
        void runNnInteractive(click);
      });
      return;
    }
    setClicks((prev) => {
      const next = [...prev, click];
      // Schedule outside the updater — never toast/setState synchronously while React is rendering.
      queueMicrotask(() => {
        void runSamRef.current({
          silent: true,
          clicks: next,
          box,
          resetTracking: true,
        });
      });
      return next;
    });
  };

  const onAddStroke = (stroke: ReaderPromptStroke) => {
    setVideoTrack(null);
    setVideoTrackStatus(null);
    lastVideoTrackFrameRef.current = null;
    if (nnInteractiveStatus?.available !== true) {
      toast.error('nnInteractive 未连接，自由涂鸦和套索不会改走 SAM3.1');
      return;
    }
    if (!maskPolygon?.length && !box) {
      toast.error('请先框选病灶并生成初始轮廓');
      return;
    }
    setPromptStrokes((prev) => [...prev, stroke]);
    queueMicrotask(() => {
      void runNnInteractive(undefined, stroke);
    });
  };

  const onPointerUpAfterBox = () => {
    setVideoTrack(null);
    setVideoTrackStatus(null);
    lastVideoTrackFrameRef.current = null;
    nnInteractiveSessionRef.current = { key: '', id: '', initialized: false };
    if (box && Math.abs(box.x2 - box.x1) > 8 && Math.abs(box.y2 - box.y1) > 8) {
      queueMicrotask(() => {
        void runSamRef.current({
          silent: true,
          clicks,
          box,
          resetTracking: true,
        });
      });
    }
  };

  const togglePlay = () => {
    const video = videoRef.current;
    if (!video) return;
    if (video.paused) {
      video.play();
      setIsPlaying(true);
    } else {
      video.pause();
      setIsPlaying(false);
    }
  };

  useEffect(() => {
    const video = videoRef.current;
    if (!video || !trackOnPlay || !isPlaying || !hasPrompt || videoTrackBusy || videoTrack?.frames.length) return;
    const timer = window.setInterval(() => {
      const now = performance.now();
      if (trackBusyRef.current || now - lastTrackRef.current < TRACK_INTERVAL_MS) return;
      lastTrackRef.current = now;
      trackBusyRef.current = true;
      runSam({ silent: true }).finally(() => {
        trackBusyRef.current = false;
      });
    }, TRACK_INTERVAL_MS);
    return () => window.clearInterval(timer);
  }, [hasPrompt, isPlaying, runSam, trackOnPlay, videoTrack?.frames.length, videoTrackBusy]);

  const onSeek = (time: number) => {
    const video = videoRef.current;
    if (!video) return;
    video.currentTime = time;
    setCurrentTime(time);
  };

  const onVideoTimeUpdate = useCallback((time: number, videoDuration: number) => {
    setCurrentTime(time);
    setDuration(videoDuration);
    if (Math.abs(time - lastAuditFrameRef.current) >= 0.5) {
      lastAuditFrameRef.current = time;
      recordAudit('frame_viewed', {
        frame_id: currentFrame?.media_token || currentFrame?.video_rel || null,
        frame_time: time,
        duration: videoDuration,
      });
    }
  }, [currentFrame?.media_token, currentFrame?.video_rel, recordAudit]);

  const onDoctorAction = useCallback((action: ReaderDoctorAction) => {
    const recommendedStage = unifiedAgentResult?.report.recommended_t_stage || report?.recommended_stage || (
      report?.stage_distribution
        ? Object.entries(report.stage_distribution).sort((a, b) => b[1] - a[1])[0]?.[0]
        : undefined
    );
    recordAudit('doctor_action', {
      action_id: newAuditId('action'),
      reader_id: readerIdParam,
      suggestion_id: auditSuggestionRef.current,
      action_type: action.action_type,
      before_value: recommendedStage || null,
      after_value: action.final_t_stage || null,
      reason: action.reason || null,
      frame_id: currentFrame?.media_token || currentFrame?.video_rel || null,
      frame_time: currentTime,
      elapsed_ms: auditStartedAtRef.current ? Date.now() - auditStartedAtRef.current : null,
      ai_confidence: report?.calibrated_confidence
        ?? (unifiedAgentResult?.report.confidence === 'high'
          ? 0.85
          : unifiedAgentResult?.report.confidence === 'low' ? 0.35 : 0.6),
    });
    toast.success(
      action.action_type === 'accept'
        ? '已记录采纳'
        : action.action_type === 'modify'
          ? '已记录修改'
          : action.action_type === 'reject'
            ? '已记录拒绝'
            : '已记录证据不足',
    );
  }, [currentFrame?.media_token, currentFrame?.video_rel, currentTime, readerIdParam, recordAudit, report, unifiedAgentResult]);

  const caseTitle = selectedCase
    ? `${selectedCase.case_id}${selectedCase.patient_id ? ` · ${selectedCase.patient_id}` : ''}`
    : effectiveDeepCaseId || effectivePatientIdParam || '—';
  const frameTitle = currentFrame?.axis_label || (externalVideo ? '外部视频' : '—');

  const samBadge = samStatus?.available
    ? `${samStatus.status?.model || 'SAM'}${samStatus.status?.cuda ? ' · GPU' : ' · CPU'}${llmReady ? ' · 报告' : ''}`
    : '分割离线';

  return (
    <div className="flex h-full flex-col bg-[#08090a] text-gray-100">
      <header className="flex shrink-0 items-center justify-between border-b border-white/10 px-4 py-2.5">
        <div className="flex items-center gap-3">
          <button type="button" onClick={() => navigateTo('/')} className="reader-btn">
            <ArrowLeft size={14} /> 工作台
          </button>
          <div>
            <div className="flex items-center gap-2">
              <ScanSearch size={16} className="text-emerald-400" />
              <h1 className="text-sm font-bold">胃充盈超声智能诊断系统</h1>
              <span className="rounded bg-emerald-500/15 px-2 py-0.5 text-[10px] text-emerald-300">临床智能工作台</span>
            </div>
            <div className="text-[10px] text-gray-500">
              福建协和医院超声 · 交互式视频 T 分期 · 人机协作阅片 · SAM 分割 + 分层 + 文字报告
              {callbackUrl || searchParams.get('frame_id')
                ? ' · 结果会回写主工作台右上角'
                : ' · 从工作台选例进入可自动回写'}
            </div>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <span className="rounded border border-white/10 bg-black/40 px-2 py-1 text-[10px] text-gray-400">{samBadge}</span>
          <span className="text-[10px] text-gray-500">
            {selectedCase ? `${caseSummaries.findIndex((c) => c.case_id === selectedCase.case_id) + 1}/${caseSummaries.length}` : '—'}
          </span>
          <button
            type="button"
            className="reader-btn"
            onClick={() => {
              const htmlUrl = buildReadingAgentUrl({
                id: searchParams.get('frame_id') || undefined,
                patient_id: selectedCase?.patient_id || patientIdParam || undefined,
                id_short: selectedCase?.display_id || searchParams.get('title') || selectedCase?.case_id || undefined,
                image_url: externalImage || undefined,
                video_urls: externalVideo ? [{ url: externalVideo }] : undefined,
              });
              window.open(htmlUrl || getReadingAgentPageUrl(), '_blank', 'noopener,noreferrer');
            }}
            title="打开经典 HTML 版（回退；带 callback 可回写工作台）"
          >
            <ExternalLink size={12} /> HTML 版
          </button>
          <button
            type="button"
            className="reader-btn"
            onClick={() => {
              fetchSamStatus().then(setSamStatus);
              fetchNnInteractiveStatus().then(setNnInteractiveStatus);
            }}
          >
            <RefreshCw size={12} />
          </button>
        </div>
      </header>

      <div className="flex min-h-0 flex-1">
        <ReaderCaseSidebar
          cohort={cohort}
          onCohortChange={(c) => {
            if (c === cohort) return;
            if (auditSessionRef.current && auditCaseRef.current) {
              recordAudit('session_end', {
                elapsed_ms: auditStartedAtRef.current ? Date.now() - auditStartedAtRef.current : null,
                reason: 'cohort_changed',
              });
            }
            auditSessionRef.current = null;
            auditCaseRef.current = null;
            caseLoadRequestRef.current += 1;
            caseSelectionRequestRef.current += 1;
            loadedCohortRef.current = null;
            ignoreDeepCaseRef.current = true;
            initialCaseSelectionRef.current = false;
            setCaseSummaries([]);
            setCohort(c);
            setSelectedCase(null);
            resetInteraction();
            const nextParams = new URLSearchParams(searchParams.toString());
            nextParams.set('cohort', c);
            ['case', 'patient_id', 'video', 'image', 'frame_id', 'title'].forEach((key) => nextParams.delete(key));
            navigateTo(`/reader?${nextParams.toString()}`, { replace: true });
          }}
          cases={caseSummaries}
          selectedCaseId={selectedCase?.case_id || null}
          onSelectCase={loadCaseDetail}
          loading={casesLoading}
        />

        <main className="flex min-w-0 flex-1 flex-col">
          <ReaderToolbar
            caseTitle={caseTitle}
            frameTitle={frameTitle}
            interactionMode={interactionMode}
            onInteractionModeChange={setInteractionMode}
            isPlaying={isPlaying}
            onTogglePlay={togglePlay}
            playbackRate={playbackRate}
            onPlaybackRateChange={updatePlaybackRate}
            trackOnPlay={trackOnPlay}
            onToggleTrack={() => setTrackOnPlay((v) => !v)}
            videoTrackBusy={videoTrackBusy}
            videoTrackStatus={videoTrackStatus}
            onPropagateVideo={runFullVideoTrack}
            showMask={showMask}
            onToggleShowMask={() => setShowMask((v) => !v)}
            maskOpacity={maskOpacity}
            onMaskOpacityChange={setMaskOpacity}
            hasMask={Boolean(maskPolygon?.length)}
            promptSummary={promptSummary}
            samBusy={samBusy}
            reportBusy={reportBusy}
            llmReady={llmReady}
            hasPrompt={hasPrompt}
            nnInteractiveAvailable={nnInteractiveStatus?.available ?? null}
            nnInteractiveBusy={nnInteractiveBusy}
            onGenerateReport={() => runSam({ llmReport: true })}
            onClearPrompt={resetInteraction}
            onUndoPoint={() => setClicks((prev) => prev.slice(0, -1))}
            onAnalyzeKeyframe={() => runSam({ llmReport: false })}
          />

          {videoSrc ? (
            <ReaderViewer
              key={selectedCase?.case_id || externalVideo || externalImage || 'external-reader'}
              videoSrc={videoSrc}
              playbackRate={playbackRate}
              interactionMode={interactionMode}
              clicks={clicks}
              promptStrokes={promptStrokes}
              box={box}
              maskPolygon={maskPolygon}
              showMask={showMask}
              maskOpacity={maskOpacity}
              maskOverlayPng={maskOverlayPng}
              onVideoReady={onVideoReady}
              onTimeUpdate={onVideoTimeUpdate}
              onAddClick={onAddClick}
              onAddStroke={onAddStroke}
              onSetBox={setBox}
              onPointerUpAfterBox={onPointerUpAfterBox}
              badge={badge}
              hint="先框选病灶，再用 nnInteractive 正点、负点、自由涂鸦或套索修正"
            />
          ) : (
            <div className="flex flex-1 flex-col items-center justify-center gap-3 px-6 text-center text-sm text-gray-500">
              {casesLoading ? (
                <Loader2 className="animate-spin" />
              ) : (
                <>
                  <div>请从左侧选病例，或从主工作台 Header「阅片Agent」/ 辅助中心带深链进入。</div>
                  <div className="max-w-md text-[11px] leading-relaxed text-gray-600">
                    分割完成后结果会 POST 回主工作台右上角「辅助回写」卡。也可点右上角「HTML 版」打开经典页（同样可回写）。
                  </div>
                  <button
                    type="button"
                    className="reader-btn"
                    onClick={() => navigateTo('/')}
                  >
                    返回工作台选例
                  </button>
                </>
              )}
            </div>
          )}

          <ReaderTimeline currentTime={currentTime} duration={duration} onSeek={onSeek} />
          <div className="max-h-[280px] shrink-0 overflow-hidden border-t border-white/10">
            <ReaderEvidencePanel
              result={unifiedAgentResult}
              loading={unifiedAgentBusy}
              onRun={() => void runUnifiedAgent()}
              onNextAction={(actionType) => runNextAgentAction(actionType)}
            />
            {unifiedAgentError ? (
              <div className="border-t border-rose-400/20 bg-rose-400/5 px-3 py-2 text-[10px] text-rose-200">
                {unifiedAgentError}
              </div>
            ) : null}
          </div>
        </main>

        <ReaderReportPanel
          key={selectedCase?.case_id || externalVideo || externalImage || 'external-report'}
          report={report}
          gcUsReport={gcUsReport}
          loading={reportBusy}
          samScore={samScore}
          maskPolygon={maskPolygon}
          frameSize={frameSize}
          frameDataUrl={frameDataUrl}
          caseId={activeCaseId}
          frameId={currentFrame?.media_token || currentFrame?.video_rel || null}
          frameTime={currentTime}
          clinical={selectedCase?.clinical}
          layerResult={layerResult}
          onLayerResult={setLayerResult}
          onEvidenceStateChange={handleGcUsEvidenceState}
          onDoctorAction={onDoctorAction}
          unifiedResult={unifiedAgentResult}
          onCopy={async () => {
            const text = unifiedAgentResult?.report.dynamic_report_draft?.full_text
              || gcUsReport?.report.prose
              || report?.template_prose
              || report?.llm_report?.narrative
              || report?.summary
              || '';
            if (!text) {
              toast.error('暂无可复制报告');
              return;
            }
            if (await copyReaderText(text)) {
              toast.success('已复制报告');
            } else {
              toast.error('浏览器暂未授权剪贴板，请先点击页面后重试');
            }
          }}
        />
      </div>
    </div>
  );
}
