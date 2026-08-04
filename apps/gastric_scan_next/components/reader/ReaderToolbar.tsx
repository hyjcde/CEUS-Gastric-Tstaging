'use client';

import React from 'react';
import {
  Eraser, FileText, Loader2, Pause, Play, RotateCcw, Route, Sparkles, Undo2,
} from 'lucide-react';
import type { InteractionMode } from '@/lib/reader/types';

type Props = {
  caseTitle: string;
  frameTitle: string;
  interactionMode: InteractionMode;
  onInteractionModeChange: (mode: InteractionMode) => void;
  isPlaying: boolean;
  onTogglePlay: () => void;
  trackOnPlay: boolean;
  onToggleTrack: () => void;
  videoTrackBusy: boolean;
  videoTrackStatus?: string | null;
  onPropagateVideo: () => void;
  showMask: boolean;
  onToggleShowMask: () => void;
  maskOpacity: number;
  onMaskOpacityChange: (v: number) => void;
  hasMask: boolean;
  promptSummary: string;
  samBusy: boolean;
  reportBusy: boolean;
  llmReady: boolean;
  hasPrompt: boolean;
  onGenerateReport: () => void;
  onClearPrompt: () => void;
  onUndoPoint: () => void;
  onAnalyzeKeyframe: () => void;
};

const MODES: { id: InteractionMode; label: string; hint: string }[] = [
  { id: 'positive', label: '正向点', hint: '1' },
  { id: 'negative', label: '负向点', hint: '2' },
  { id: 'box', label: '框选', hint: '3' },
  { id: 'inspect', label: '检视', hint: '4' },
];

export function ReaderToolbar({
  caseTitle,
  frameTitle,
  interactionMode,
  onInteractionModeChange,
  isPlaying,
  onTogglePlay,
  trackOnPlay,
  onToggleTrack,
  videoTrackBusy,
  videoTrackStatus,
  onPropagateVideo,
  showMask,
  onToggleShowMask,
  maskOpacity,
  onMaskOpacityChange,
  hasMask,
  promptSummary,
  samBusy,
  reportBusy,
  llmReady,
  hasPrompt,
  onGenerateReport,
  onClearPrompt,
  onUndoPoint,
  onAnalyzeKeyframe,
}: Props) {
  return (
    <div className="space-y-2 border-b border-white/10 bg-[#0e1012] px-3 py-2">
      <div className="flex flex-wrap items-center gap-2">
        <div className="min-w-0 flex-1">
          <div className="truncate text-xs font-semibold text-gray-100">{caseTitle}</div>
          <div className="truncate text-[10px] text-gray-500">{frameTitle}</div>
        </div>
        <span className="rounded border border-white/10 bg-black/40 px-2 py-0.5 text-[10px] text-gray-400">
          {promptSummary || '未标注'}
        </span>
      </div>

      <div className="flex flex-wrap items-center gap-1.5">
        <button type="button" onClick={onTogglePlay} className="reader-btn">
          {isPlaying ? <Pause size={12} /> : <Play size={12} />}
          {isPlaying ? '暂停' : '播放'}
        </button>
        <button
          type="button"
          onClick={onToggleTrack}
          className={`reader-btn ${trackOnPlay ? 'reader-btn-primary' : ''}`}
        >
          自动单帧跟踪 · {trackOnPlay ? '开' : '关'}
        </button>
        <button
          type="button"
          onClick={onPropagateVideo}
          className="reader-btn"
          disabled={videoTrackBusy || !hasPrompt}
          title={!hasPrompt ? '请先框选或点击病灶' : '使用 SAM2.1 视频 memory 对整个视频传播'}
        >
          {videoTrackBusy ? <Loader2 size={12} className="animate-spin" /> : <Route size={12} />}
          {videoTrackBusy ? '全视频传播中' : '全视频传播'}
        </button>
        {videoTrackStatus ? <span className="text-[10px] text-gray-500">{videoTrackStatus}</span> : null}
        <button type="button" onClick={onAnalyzeKeyframe} className="reader-btn" disabled={samBusy}>
          {samBusy ? <Loader2 size={12} className="animate-spin" /> : <Sparkles size={12} />}
          关键帧分析
        </button>
        <button
          type="button"
          onClick={onGenerateReport}
          className="reader-btn reader-btn-primary"
          disabled={reportBusy || !llmReady || !hasPrompt}
          title={!llmReady ? '未配置 DeepSeek / MiniMax' : !hasPrompt ? '请先框选或点击病灶' : ''}
        >
          {reportBusy ? <Loader2 size={12} className="animate-spin" /> : <FileText size={12} />}
          生成文字报告
        </button>
        <button type="button" onClick={onClearPrompt} className="reader-btn">
          <Eraser size={12} /> 清除
        </button>
        <button type="button" onClick={onUndoPoint} className="reader-btn">
          <Undo2 size={12} /> 撤销
        </button>
      </div>

      <div className="flex flex-wrap items-center gap-1.5">
        <span className="text-[10px] text-gray-500">交互</span>
        {MODES.map((m) => (
          <button
            key={m.id}
            type="button"
            onClick={() => onInteractionModeChange(m.id)}
            className={`rounded px-2 py-0.5 text-[10px] font-medium transition-colors ${
              interactionMode === m.id
                ? 'bg-cyan-600/80 text-white'
                : 'bg-white/5 text-gray-400 hover:bg-white/10'
            }`}
            title={`快捷键 ${m.hint}`}
          >
            {m.label}
          </button>
        ))}
      </div>

      {hasMask ? (
        <div className="flex flex-wrap items-center gap-3 text-[10px] text-gray-400">
          <label className="inline-flex items-center gap-1.5">
            <input type="checkbox" checked={showMask} onChange={onToggleShowMask} />
            显示分割轮廓
          </label>
          <label className="inline-flex items-center gap-1.5">
            填充
            <input
              type="range"
              min={8}
              max={55}
              value={Math.round(maskOpacity * 100)}
              onChange={(e) => onMaskOpacityChange(Number(e.target.value) / 100)}
            />
          </label>
          <button type="button" onClick={onClearPrompt} className="inline-flex items-center gap-1 text-gray-500 hover:text-gray-300">
            <RotateCcw size={10} /> 重置 mask
          </button>
        </div>
      ) : null}
    </div>
  );
}
