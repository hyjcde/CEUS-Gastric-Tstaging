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
} from '@/lib/reader/sam-client';
import type {
  InteractionMode,
  ReaderCase,
  ReaderCohort,
  SamBackendStatus,
  SamBox,
  SamClick,
  SamReport,
} from '@/lib/reader/types';
import type { LayerAnalyzeResult } from '@/lib/human-assist/load-contact-geom';
import { buildReadingAgentUrl, getReadingAgentPageUrl } from '@/lib/reading-agent-url';

const TRACK_INTERVAL_MS = 500;

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
  const [trackOnPlay, setTrackOnPlay] = useState(true);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [frameSize, setFrameSize] = useState<{ width: number; height: number } | null>(null);
  const [frameDataUrl, setFrameDataUrl] = useState<string | null>(null);
  const [layerResult, setLayerResult] = useState<LayerAnalyzeResult | null>(null);
  const [badge, setBadge] = useState<string | null>(null);
  const [bundleVersion, setBundleVersion] = useState<string | undefined>();

  const videoRef = useRef<HTMLVideoElement | null>(null);
  const trackBusyRef = useRef(false);
  const lastTrackRef = useRef(0);
  const llmDebounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const runSamRef = useRef<(opts?: { llmReport?: boolean; silent?: boolean; clicks?: SamClick[]; box?: SamBox | null }) => Promise<void>>(async () => {});
  const externalVideo = searchParams.get('video') || '';
  const externalImage = searchParams.get('image') || '';
  const deepCaseId = searchParams.get('case') || '';
  const callbackUrl = searchParams.get('callback') || '';

  const llmReady = llmReportConfigured(samStatus);
  const hasPrompt = Boolean(box) || clicks.length > 0;

  const currentFrame = selectedCase?.frames?.[frameIndex] || selectedCase?.frames?.[0];
  const videoSrc = useMemo(() => {
    if (externalVideo) return externalVideo;
    if (currentFrame?.video_rel) return readerMediaUrl(currentFrame.video_rel, bundleVersion);
    return '';
  }, [bundleVersion, currentFrame?.video_rel, externalVideo]);

  const promptSummary = useMemo(() => {
    const pos = clicks.filter((c) => c.label !== 'negative').length;
    const neg = clicks.filter((c) => c.label === 'negative').length;
    const parts: string[] = [];
    if (box) parts.push('1 框');
    if (pos || neg) parts.push(`${pos} 正 / ${neg} 负`);
    if (samScore != null) parts.push(`分割 ${Math.round(samScore * 100)}%`);
    return parts.join(' · ');
  }, [box, clicks, samScore]);

  const loadCases = useCallback(async (c: ReaderCohort) => {
    setCasesLoading(true);
    try {
      const res = await fetch(`/api/reader/cases?cohort=${encodeURIComponent(c)}`);
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
    try {
      const res = await fetch(`/api/reader/cases?case_id=${encodeURIComponent(caseId)}`);
      const data = await res.json();
      if (!data.ok || !data.case) throw new Error('case not found');
      setSelectedCase(data.case as ReaderCase);
      setFrameIndex(0);
      resetInteraction();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '病例加载失败');
    }
  }, []);

  const resetInteraction = () => {
    setClicks([]);
    setBox(null);
    setMaskPolygon(null);
    setMaskOverlayPng(null);
    setReport(null);
    setSamScore(null);
    setLayerResult(null);
    setBadge(null);
  };

  useEffect(() => {
    loadCases(cohort);
  }, [cohort, loadCases]);

  useEffect(() => {
    fetchSamStatus().then(setSamStatus).catch(() => setSamStatus({ available: false }));
  }, []);

  useEffect(() => {
    const target = deepCaseId || caseSummaries[0]?.case_id;
    if (target && !selectedCase) {
      loadCaseDetail(target);
    }
  }, [caseSummaries, deepCaseId, loadCaseDetail, selectedCase]);

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
    (llmReport: boolean, clickOverride?: SamClick[], boxOverride?: SamBox | null) => {
      const video = videoRef.current;
      if (!video?.videoWidth) throw new Error('Video frame not ready');
      const useUpload = Boolean(externalVideo || externalImage || !currentFrame?.video_rel);
      const effectiveClicks = clickOverride ?? clicks;
      const effectiveBox = boxOverride !== undefined ? boxOverride : box;
      const payload = {
        case_id: selectedCase?.case_id || deepCaseId || 'external',
        video_rel: useUpload ? '' : currentFrame?.video_rel,
        frame_time: useUpload ? 0 : video.currentTime || 0,
        image_width: video.videoWidth,
        image_height: video.videoHeight,
        clicks: effectiveClicks.map((c) => ({ x: c.x, y: c.y, label: c.label })),
        box: effectiveBox || undefined,
        llm_report: llmReport,
      } as Parameters<typeof runSamAnalyze>[0];
      if (useUpload) {
        payload.frame_png_b64 = captureVideoFrameB64(video);
      }
      return payload;
    },
    [box, clicks, currentFrame?.video_rel, deepCaseId, externalImage, externalVideo, selectedCase?.case_id],
  );

  const applySamResult = useCallback((result: Awaited<ReturnType<typeof runSamAnalyze>>, withReport: boolean) => {
    setMaskPolygon(result.mask_polygon || null);
    setMaskOverlayPng(result.mask_overlay_png || null);
    setSamScore(result.sam_score ?? null);
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
    setBadge(`分割 ${Math.round((result.sam_score || 0) * 100)}%`);
  }, []);

  const runSam = useCallback(
    async (opts: { llmReport?: boolean; silent?: boolean; clicks?: SamClick[]; box?: SamBox | null } = {}) => {
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
        const payload = buildPayload(Boolean(opts.llmReport), effectiveClicks, effectiveBox);
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

  useEffect(() => {
    runSamRef.current = runSam;
  }, [runSam]);

  const postCallbackIfNeeded = async (result: Awaited<ReturnType<typeof runSamAnalyze>>) => {
    const url = callbackUrl || (typeof window !== 'undefined' ? `${window.location.origin}/api/reader-agent/result` : '');
    if (!url || !result.mask_polygon?.length) return;
    try {
      await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          case_id: selectedCase?.case_id,
          frame_id: searchParams.get('frame_id') || undefined,
          patient_id: searchParams.get('patient_id') || undefined,
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
    setClicks((prev) => {
      const next = [...prev, click];
      // Schedule outside the updater — never toast/setState synchronously while React is rendering.
      queueMicrotask(() => {
        void runSamRef.current({ silent: true, clicks: next, box });
      });
      return next;
    });
  };

  const onPointerUpAfterBox = () => {
    if (box && Math.abs(box.x2 - box.x1) > 8 && Math.abs(box.y2 - box.y1) > 8) {
      queueMicrotask(() => {
        void runSamRef.current({ silent: true, clicks, box });
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
    if (!video || !trackOnPlay || !isPlaying || !hasPrompt) return;
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
  }, [hasPrompt, isPlaying, runSam, trackOnPlay]);

  const onSeek = (time: number) => {
    const video = videoRef.current;
    if (!video) return;
    video.currentTime = time;
    setCurrentTime(time);
  };

  const caseTitle = selectedCase?.case_id || deepCaseId || '—';
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
                patient_id: searchParams.get('patient_id') || undefined,
                id_short: searchParams.get('title') || selectedCase?.case_id || undefined,
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
              videoSrc={videoSrc}
              interactionMode={interactionMode}
              clicks={clicks}
              box={box}
              maskPolygon={maskPolygon}
              showMask={showMask}
              maskOpacity={maskOpacity}
              maskOverlayPng={maskOverlayPng}
              onVideoReady={onVideoReady}
              onTimeUpdate={(t, d) => {
                setCurrentTime(t);
                setDuration(d);
              }}
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
          report={report}
          loading={reportBusy}
          samScore={samScore}
          maskPolygon={maskPolygon}
          frameSize={frameSize}
          frameDataUrl={frameDataUrl}
          onLayerResult={setLayerResult}
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
