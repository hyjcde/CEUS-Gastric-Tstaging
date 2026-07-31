'use client';

import React, { useMemo, useState } from 'react';
import { AlertTriangle, CheckCircle2, Clapperboard, Loader2, ShieldCheck, UploadCloud, XCircle } from 'lucide-react';
import { AgentAnalysisResponse } from '@/types';

interface VideoAnalysisUploadProps {
  onAnalysisComplete?: (result: AgentAnalysisResponse) => void;
}

type VideoAnalysisResult = AgentAnalysisResponse & {
  upload?: {
    filename?: string;
    extracted_frame_count?: number;
    candidate_frame_count?: number;
    original_video_frame_count?: number;
    duration_sec?: number;
    frame_indices?: number[];
    frames?: Array<{
      frame_index: number;
      timestamp_sec: number;
      quality_score: number;
    }>;
  };
  video_intelligence?: {
    temporal_consistency?: 'stable' | 'borderline' | 'unstable' | string;
    classifier_margin?: number;
    aggregation?: string;
    rag_weight?: number;
    rag_reason?: string;
    review_priority?: 'standard' | 'medium' | 'high' | string;
    similar_case_majority?: string;
  };
  system_integrity?: {
    status?: 'verified' | 'degraded' | 'failed' | string;
    not_mock?: boolean;
    required_components?: string[];
    failed_required_components?: string[];
    degraded_components?: string[];
    proxy_visual_notes?: string[];
    components?: Array<{
      component?: string;
      called?: boolean;
      status?: string;
      forward_pass?: boolean;
      api_kind?: string;
      checkpoint?: string;
      error?: string;
      skip_reason?: string;
    }>;
  };
};

export function VideoAnalysisUpload({ onAnalysisComplete }: VideoAnalysisUploadProps) {
  const [file, setFile] = useState<File | null>(null);
  const [patientId, setPatientId] = useState('');
  const [notes, setNotes] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<VideoAnalysisResult | null>(null);

  const canSubmit = Boolean(file) && !loading;
  const stage = result?.report?.recommended_t_stage;
  const confidence = result?.report?.confidence;
  const evidence = useMemo(() => result?.report?.supporting_evidence?.slice(0, 3) ?? [], [result]);
  const intelligence = result?.video_intelligence;
  const integrity = result?.system_integrity;
  const consistencyTone = intelligence?.temporal_consistency === 'stable'
    ? 'text-emerald-100 border-emerald-300/30 bg-emerald-400/10'
    : intelligence?.temporal_consistency === 'borderline'
      ? 'text-amber-100 border-amber-300/30 bg-amber-400/10'
      : 'text-red-100 border-red-300/30 bg-red-400/10';
  const integrityTone = integrity?.status === 'verified'
    ? 'border-emerald-300/30 bg-emerald-400/10 text-emerald-100'
    : integrity?.status === 'degraded'
      ? 'border-amber-300/30 bg-amber-400/10 text-amber-100'
      : 'border-red-300/30 bg-red-400/10 text-red-100';
  const resultTone = integrity?.status === 'failed'
    ? 'border-red-400/25 bg-red-500/10'
    : integrity?.status === 'degraded'
      ? 'border-amber-400/25 bg-amber-500/10'
      : 'border-emerald-400/25 bg-emerald-500/10';
  const requiredComponents = integrity?.components?.filter((item) => (
    integrity.required_components?.includes(String(item.component))
  )) ?? [];

  const submit = async () => {
    if (!file) return;
    setLoading(true);
    setError(null);
    setResult(null);

    try {
      const formData = new FormData();
      formData.append('video', file);
      if (patientId.trim()) formData.append('patientId', patientId.trim());
      if (notes.trim()) formData.append('notes', notes.trim());

      const response = await fetch('/api/agent/video/analyze', {
        method: 'POST',
        body: formData,
      });
      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload?.error || 'Video analysis failed');
      }

      setResult(payload as VideoAnalysisResult);
      onAnalysisComplete?.(payload as AgentAnalysisResponse);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Video analysis failed');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="pointer-events-auto absolute left-5 top-5 z-30 w-[min(520px,calc(100%-2.5rem))] overflow-hidden rounded-2xl border border-cyan-400/20 bg-black/75 shadow-2xl shadow-cyan-950/30 backdrop-blur-xl">
      <div className="border-b border-white/10 bg-gradient-to-r from-cyan-500/15 via-blue-500/10 to-emerald-500/10 px-4 py-3">
        <div className="flex items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl border border-cyan-300/30 bg-cyan-400/10 text-cyan-200">
              <Clapperboard size={19} />
            </div>
            <div>
              <div className="text-sm font-bold text-white">视频综合分析入口</div>
              <div className="text-[11px] text-cyan-100/70">质量选帧 + 多帧聚合 + Agent / RAG / DINO 综合证据链</div>
            </div>
          </div>
          {loading && <Loader2 size={18} className="animate-spin text-cyan-200" />}
        </div>
      </div>

      <div className="space-y-3 p-4">
        <label className="flex cursor-pointer flex-col items-center justify-center rounded-xl border border-dashed border-cyan-300/30 bg-white/[0.03] px-4 py-5 text-center transition hover:border-cyan-300/60 hover:bg-cyan-400/5">
          <UploadCloud size={24} className="mb-2 text-cyan-200" />
          <span className="text-xs font-semibold text-slate-100">
            {file ? file.name : '选择或拖入 mp4 / mov / avi / webm 视频'}
          </span>
          <span className="mt-1 text-[10px] text-slate-500">系统会扫描候选帧，按清晰度/对比度/运动信息选取最多 5 帧</span>
          <input
            type="file"
            accept="video/mp4,video/quicktime,video/x-msvideo,video/webm,video/*"
            className="hidden"
            onChange={(event) => {
              setFile(event.target.files?.[0] ?? null);
              setError(null);
              setResult(null);
            }}
          />
        </label>

        <div className="grid gap-2 md:grid-cols-[0.8fr_1.2fr]">
          <input
            value={patientId}
            onChange={(event) => setPatientId(event.target.value)}
            placeholder="患者 ID（可选）"
            className="rounded-lg border border-white/10 bg-black/40 px-3 py-2 text-xs text-slate-100 outline-none placeholder:text-slate-600 focus:border-cyan-300/50"
          />
          <input
            value={notes}
            onChange={(event) => setNotes(event.target.value)}
            placeholder="报告/临床提示（可选，用于 RAG 综合）"
            className="rounded-lg border border-white/10 bg-black/40 px-3 py-2 text-xs text-slate-100 outline-none placeholder:text-slate-600 focus:border-cyan-300/50"
          />
        </div>

        <button
          type="button"
          disabled={!canSubmit}
          onClick={submit}
          className="flex w-full items-center justify-center gap-2 rounded-xl bg-cyan-400 px-4 py-2.5 text-xs font-bold text-slate-950 shadow-lg shadow-cyan-500/20 transition hover:bg-cyan-300 disabled:cursor-not-allowed disabled:bg-slate-700 disabled:text-slate-400 disabled:shadow-none"
        >
          {loading ? <Loader2 size={15} className="animate-spin" /> : <UploadCloud size={15} />}
          {loading ? '正在抽帧并调用综合 Agent...' : '上传视频并开始综合分析'}
        </button>

        {error && (
          <div className="flex gap-2 rounded-lg border border-red-400/30 bg-red-500/10 p-3 text-[11px] text-red-100">
            <AlertTriangle size={14} className="mt-0.5 shrink-0" />
            <span>{error}</span>
          </div>
        )}

        {result && (
          <div className={`rounded-xl border p-3 ${resultTone}`}>
            <div className="mb-2 flex items-center justify-between gap-3">
              <div className="flex items-center gap-2 text-xs font-bold text-slate-100">
                {integrity?.status === 'failed' ? <XCircle size={15} /> : <CheckCircle2 size={15} />}
                {integrity?.status === 'failed' ? '完整性未通过' : integrity?.status === 'degraded' ? '综合分析完成（有降级）' : '综合分析完成'}
              </div>
              <div className="rounded-full border border-white/20 px-2 py-0.5 text-[11px] font-bold text-slate-100">
                {stage || 'N/A'} · {confidence || 'unknown'}
              </div>
            </div>
            <div className="mb-2 text-[11px] text-slate-300">
              已从 {result.upload?.candidate_frame_count ?? 0} 个候选帧中选取 {result.upload?.extracted_frame_count ?? result.frame_evidence?.frame_count ?? 0} 帧；
              相似病例 {result.similar_cases?.length ?? 0} 例。
            </div>
            {integrity && (
              <div className={`mb-3 rounded-xl border p-3 ${integrityTone}`}>
                <div className="mb-2 flex items-center justify-between gap-2">
                  <div className="flex items-center gap-2 text-xs font-bold">
                    {integrity.not_mock ? <ShieldCheck size={15} /> : <XCircle size={15} />}
                    系统完整性：{integrity.status}
                  </div>
                  <span className="rounded-full border border-current/25 px-2 py-0.5 text-[10px]">
                    {integrity.not_mock ? '真实链路' : '核心缺失'}
                  </span>
                </div>
                {requiredComponents.length > 0 && (
                  <div className="grid grid-cols-2 gap-1.5">
                    {requiredComponents.map((item) => (
                      <div key={item.component} className="rounded-lg bg-black/20 px-2 py-1">
                        <div className="text-[10px] opacity-70">{item.component}</div>
                        <div className="text-[11px] font-semibold">
                          {item.called ? 'called' : 'missing'}{item.forward_pass ? ' · forward' : ''}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
                {(integrity.failed_required_components?.length ?? 0) > 0 && (
                  <div className="mt-2 text-[10px] leading-relaxed">
                    缺失核心组件：{integrity.failed_required_components?.join(', ')}
                  </div>
                )}
                {(integrity.proxy_visual_notes?.length ?? 0) > 0 && (
                  <div className="mt-2 text-[10px] leading-relaxed">
                    降级/代理证据：{integrity.proxy_visual_notes?.join('; ')}
                  </div>
                )}
              </div>
            )}
            {intelligence && (
              <div className="mb-3 grid grid-cols-2 gap-2">
                <div className={`rounded-lg border px-2 py-1.5 ${consistencyTone}`}>
                  <div className="text-[10px] opacity-70">时序一致性</div>
                  <div className="text-xs font-bold">{intelligence.temporal_consistency}</div>
                </div>
                <div className="rounded-lg border border-cyan-300/25 bg-cyan-400/10 px-2 py-1.5 text-cyan-100">
                  <div className="text-[10px] opacity-70">RAG 权重 / 多帧边界</div>
                  <div className="text-xs font-bold">
                    {Number(intelligence.rag_weight ?? 0).toFixed(2)} / Δ{Number(intelligence.classifier_margin ?? 0).toFixed(2)}
                  </div>
                </div>
              </div>
            )}
            <div className="space-y-1">
              {evidence.map((item) => (
                <div key={item} className="text-[11px] leading-relaxed text-slate-300">
                  • {item}
                </div>
              ))}
            </div>
            {result.upload?.frames && result.upload.frames.length > 0 && (
              <div className="mt-3 rounded-lg border border-white/10 bg-black/25 p-2">
                <div className="mb-1 text-[10px] font-bold text-slate-400">智能选帧</div>
                <div className="flex flex-wrap gap-1.5">
                  {result.upload.frames.map((frame) => (
                    <span key={frame.frame_index} className="rounded-full border border-white/10 bg-white/5 px-2 py-0.5 text-[10px] text-slate-300">
                      {frame.timestamp_sec.toFixed(1)}s · q{frame.quality_score.toFixed(2)}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
