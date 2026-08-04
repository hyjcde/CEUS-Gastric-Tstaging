'use client';

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import toast from 'react-hot-toast';
import {
  ArrowLeft, ExternalLink, Loader2, RefreshCw, ScanSearch,
} from 'lucide-react';
import { ReaderCaseSidebar, type CaseSummary } from '@/components/reader/ReaderCaseSidebar';
import { ReaderToolbar } from '@/components/reader/ReaderToolbar';
import { ReaderViewer } from '@/components/reader/ReaderViewer';
import { ReaderReportPanel } from '@/components/reader/ReaderReportPanel';
import { ReaderTimeline } from '@/components/reader/ReaderTimeline';
import { readerMediaUrl } from '@/lib/reader/media-url';
import {
  captureVideoFrameB64,
  fetchSamStatus,
  llmReportConfigured,
  runSamAnalyze,
  runSamVideoPropagation,
  type SamVideoPropagationResult,
} from '@/lib/reader/sam-client';
import type {
  InteractionMode,
  ReaderCase,
  ReaderCohort,
  SamBackendStatus,
  SamBox,
  SamClick,
  ReaderDoctorAction,
  SamReport,
} from '@/lib/reader/types';
import type { LayerAnalyzeResult } from '@/lib/human-assist/load-contact-geom';
import { buildReadingAgentUrl, getReadingAgentPageUrl } from '@/lib/reading-agent-url';

const TRACK_INTERVAL_MS = 1000;
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
  const router = useRouter();
  const searchParams = useSearchParams();

  const [cohort, setCohort] = useState<ReaderCohort>(
    (searchParams.get('cohort') as ReaderCohort) || 'all',
  );
  const [caseSummaries, setCaseSummaries] = useState<CaseSummary[]>([]);
  const [selectedCase, setSelectedCase] = useState<ReaderCase | null>(null);
  const [frameIndex, setFrameIndex] = useState(0);
  const [casesLoading, setCasesLoading] = useState(true);

  const [samStatus, setSamStatus] = useState<SamBackendStatus | null>(null);
  const [interactionMode, setInteractionMode] = useState<InteractionMode>('positive');
  const [clicks, setClicks] = useState<SamClick[]>([]);
  const [box, setBox] = useState<SamBox | null>(null);
  const [maskPolygon, setMaskPolygon] = useState<number[][] | null>(null);
  const [maskOverlayPng, setMaskOverlayPng] = useState<string | null>(null);
  const [report, setReport] = useState<SamReport | null>(null);
  const [samScore, setSamScore] = useState<number | null>(null);
  const [showMask, setShowMask] = useState(true);
  const [maskOpacity, setMaskOpacity] = useState(0.3);
  const [samBusy, setSamBusy] = useState(false);
  const [reportBusy, setReportBusy] = useState(false);
  const [isPlaying, setIsPlaying] = useState(false);
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
  const auditStartedAtRef = useRef<number | null>(null);
  const lastAuditFrameRef = useRef(0);
  const initialCaseSelectionRef = useRef(false);
  const externalVideo = searchParams.get('video') || '';
  const externalImage = searchParams.get('image') || '';
  const deepCaseId = searchParams.get('case') || '';
  const patientIdParam = searchParams.get('patient_id') || '';
  const readerIdParam = searchParams.get('reader_id') || 'unknown_reader';
  const roundParam = searchParams.get('round') || 'round2';
  const callbackUrl = searchParams.get('callback') || '';
  const activeCaseId = selectedCase?.case_id || deepCaseId || patientIdParam || 'external';
  const hasExternalMedia = Boolean(externalVideo || externalImage);

  const llmReady = llmReportConfigured(samStatus);
  const hasPrompt = Boolean(box) || clicks.length > 0;

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
    if (maskPolygon?.length) {
      parts.push(samScore != null && samScore > 0
        ? `Mask 已生成 · ${Math.round(samScore * 100)}%`
        : 'Mask 已生成 · 分数不可用');
    } else if (samScore != null) {
      parts.push(`分割 ${Math.round(samScore * 100)}%`);
    }
    return parts.join(' · ');
  }, [box, clicks, maskPolygon, samScore]);

  const loadCases = useCallback(async (c: ReaderCohort) => {
    setCasesLoading(true);
    try {
      const res = await fetch(`/api/reader/cases?cohort=${encodeURIComponent(c)}`, { cache: 'no-store', signal: AbortSignal.timeout(15_000) });
      const data = await res.json();
      if (!data.ok) throw new Error(data.error || 'cases load failed');
      setCaseSummaries(data.cases || []);
      setBundleVersion(data.created_at);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '病例库加载失败');
    } finally {
      setCasesLoading(false);
    }
  }, []);

  const loadCaseDetail = useCallback(async (caseId: string) => {
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
      const nextParams = new URLSearchParams(searchParams.toString());
      nextParams.set('case', caseId);
      ['patient_id', 'video', 'image', 'frame_id', 'title'].forEach((key) => nextParams.delete(key));
      router.replace(`/reader?${nextParams.toString()}`, { scroll: false });
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
  }, [cohort, readerIdParam, recordAudit, roundParam, router, searchParams]);

  const resetInteraction = () => {
    setClicks([]);
    setBox(null);
    setMaskPolygon(null);
    setMaskOverlayPng(null);
    setReport(null);
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
  };

  useEffect(() => {
    loadCases(cohort);
  }, [cohort, loadCases]);

  useEffect(() => {
    fetchSamStatus().then(setSamStatus).catch(() => setSamStatus({ available: false }));
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
    if (initialCaseSelectionRef.current || !caseSummaries.length) return;
    const hasExternalDeepLink = Boolean(deepCaseId || patientIdParam || externalVideo || externalImage);
    const mappedPatientCase = patientIdParam
      ? caseSummaries.find((item) => item.patient_id === patientIdParam)?.case_id
      : undefined;
    const target = deepCaseId || mappedPatientCase || (hasExternalDeepLink ? undefined : caseSummaries[0]?.case_id);
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
      }, { sessionId, caseId: activeCaseId, patientId: patientIdParam || activeCaseId });
    } else if (hasExternalDeepLink) {
      // Never silently load BM-001 when an unmapped patient link is supplied.
      initialCaseSelectionRef.current = true;
      toast.error('深链未映射到阅片病例；未自动加载其他病例');
    }
  }, [activeCaseId, caseSummaries, cohort, deepCaseId, externalImage, externalVideo, hasExternalMedia, loadCaseDetail, patientIdParam, readerIdParam, recordAudit, roundParam]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return;
      if (e.code === 'Space') {
        e.preventDefault();
        togglePlay();
      }
      if (e.key === '1') setInteractionMode('positive');
      if (e.key === '2') setInteractionMode('negative');
      if (e.key === '3') setInteractionMode('box');
      if (e.key === '4') setInteractionMode('inspect');
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  });

  const onVideoReady = useCallback((video: HTMLVideoElement) => {
    videoRef.current = video;
    lastVideoTrackFrameRef.current = null;
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
  }, []);

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
      trackingSessionId,
      videoSrc,
    ],
  );

  const applySamResult = useCallback((result: Awaited<ReturnType<typeof runSamAnalyze>>, withReport: boolean) => {
    setMaskPolygon(result.mask_polygon || null);
    setMaskOverlayPng(result.mask_overlay_png || null);
    setSamScore(result.sam_score ?? null);
    const suggestionId = newAuditId('suggestion');
    auditSuggestionRef.current = suggestionId;
    if (withReport && result.report) {
      setReport({
        ...result.report,
        sam_score: result.sam_score,
        elapsed_ms: result.elapsed_ms,
      });
    } else if (result.report) {
      setReport((prev) => ({
        ...(prev || {}),
        ...result.report,
        sam_score: result.sam_score,
        elapsed_ms: result.elapsed_ms,
      }));
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
      if (result.needs_reanchor) toast.error('全视频传播已在质量门处停止，请重新框选或点击重锚定');
      else toast.success(`全视频传播完成 · ${result.accepted_frames}/${result.num_frames} 帧`);
    } catch (error) {
      if (requestId !== videoTrackRequestRef.current) return;
      setVideoTrackStatus('全视频传播失败');
      toast.error(error instanceof Error ? error.message : '全视频传播失败');
    } finally {
      if (requestId === videoTrackRequestRef.current) {
        setVideoTrackBusy(false);
        if (resumeAfterTrack) {
          void video.play().then(() => setIsPlaying(true)).catch(() => setIsPlaying(false));
        }
      }
    }
  }, [activeCaseId, box, clicks, currentFrame?.video_rel, currentTime, hasPrompt, recordAudit]);

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

  const postCallbackIfNeeded = async (result: Awaited<ReturnType<typeof runSamAnalyze>>) => {
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
  };

  const onAddClick = (click: SamClick) => {
    setVideoTrack(null);
    setVideoTrackStatus(null);
    lastVideoTrackFrameRef.current = null;
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

  const onPointerUpAfterBox = () => {
    setVideoTrack(null);
    setVideoTrackStatus(null);
    lastVideoTrackFrameRef.current = null;
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
    const recommendedStage = report?.recommended_stage || (
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
      ai_confidence: report?.calibrated_confidence ?? null,
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
  }, [currentFrame?.media_token, currentFrame?.video_rel, currentTime, readerIdParam, recordAudit, report]);

  const caseTitle = selectedCase
    ? `${selectedCase.case_id}${selectedCase.patient_id ? ` · ${selectedCase.patient_id}` : ''}`
    : deepCaseId || patientIdParam || '—';
  const frameTitle = currentFrame?.axis_label || (externalVideo ? '外部视频' : '—');

  const samBadge = samStatus?.available
    ? `${samStatus.status?.model || 'SAM'}${samStatus.status?.cuda ? ' · GPU' : ' · CPU'}${llmReady ? ' · 报告' : ''}`
    : '分割离线';

  return (
    <div className="flex h-full flex-col bg-[#08090a] text-gray-100">
      <header className="flex shrink-0 items-center justify-between border-b border-white/10 px-4 py-2.5">
        <div className="flex items-center gap-3">
          <button type="button" onClick={() => router.push('/')} className="reader-btn">
            <ArrowLeft size={14} /> 工作台
          </button>
          <div>
            <div className="flex items-center gap-2">
              <ScanSearch size={16} className="text-emerald-400" />
              <h1 className="text-sm font-bold">交互式视频 T 分期</h1>
              <span className="rounded bg-emerald-500/15 px-2 py-0.5 text-[10px] text-emerald-300">Next 阅片 Agent</span>
            </div>
            <div className="text-[10px] text-gray-500">
              人机协作阅片 · SAM 分割 + 分层 + 文字报告
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
          <button type="button" className="reader-btn" onClick={() => fetchSamStatus().then(setSamStatus)}>
            <RefreshCw size={12} />
          </button>
        </div>
      </header>

      <div className="flex min-h-0 flex-1">
        <ReaderCaseSidebar
          cohort={cohort}
          onCohortChange={(c) => {
            if (auditSessionRef.current && auditCaseRef.current) {
              recordAudit('session_end', {
                elapsed_ms: auditStartedAtRef.current ? Date.now() - auditStartedAtRef.current : null,
                reason: 'cohort_changed',
              });
            }
            auditSessionRef.current = null;
            auditCaseRef.current = null;
            initialCaseSelectionRef.current = false;
            setCohort(c);
            setSelectedCase(null);
            resetInteraction();
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
            onGenerateReport={() => runSam({ llmReport: true })}
            onClearPrompt={resetInteraction}
            onUndoPoint={() => setClicks((prev) => prev.slice(0, -1))}
            onAnalyzeKeyframe={() => runSam({ llmReport: false })}
          />

          {videoSrc ? (
            <ReaderViewer
              key={selectedCase?.case_id || externalVideo || externalImage || 'external-reader'}
              videoSrc={videoSrc}
              interactionMode={interactionMode}
              clicks={clicks}
              box={box}
              maskPolygon={maskPolygon}
              showMask={showMask}
              maskOpacity={maskOpacity}
              maskOverlayPng={maskOverlayPng}
              onVideoReady={onVideoReady}
              onTimeUpdate={onVideoTimeUpdate}
              onAddClick={onAddClick}
              onSetBox={setBox}
              onPointerUpAfterBox={onPointerUpAfterBox}
              badge={badge}
              hint="点击或框选病灶 → 自动分割 → 右侧查看文字报告与胃壁分层"
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
                    onClick={() => router.push('/')}
                  >
                    返回工作台选例
                  </button>
                </>
              )}
            </div>
          )}

          <ReaderTimeline currentTime={currentTime} duration={duration} onSeek={onSeek} />
        </main>

        <ReaderReportPanel
          key={selectedCase?.case_id || externalVideo || externalImage || 'external-report'}
          report={report}
          loading={reportBusy}
          samScore={samScore}
          maskPolygon={maskPolygon}
          frameSize={frameSize}
          frameDataUrl={frameDataUrl}
          onLayerResult={setLayerResult}
          onDoctorAction={onDoctorAction}
          onCopy={() => {
            const text = report?.llm_report?.narrative || report?.summary || '';
            if (text) {
              navigator.clipboard.writeText(text);
              toast.success('已复制报告');
            }
          }}
        />
      </div>
    </div>
  );
}
