'use client';

import React from 'react';
import {
  Eraser, FileText, Loader2, Pause, Play, RotateCcw, Route, Sparkles, Undo2,
} from 'lucide-react';
import type { InteractionMode } from '@/lib/reader/types';
import { useSettings } from '@/contexts/SettingsContext';

type Props = {
  caseTitle: string;
  frameTitle: string;
  interactionMode: InteractionMode;
  onInteractionModeChange: (mode: InteractionMode) => void;
  isPlaying: boolean;
  onTogglePlay: () => void;
  playbackRate: number;
  onPlaybackRateChange: (value: number) => void;
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
  nnInteractiveAvailable: boolean | null;
  nnInteractiveBusy: boolean;
  onGenerateReport: () => void;
  onClearPrompt: () => void;
  onUndoPoint: () => void;
  onAnalyzeKeyframe: () => void;
};

export function ReaderToolbar({
  caseTitle,
  frameTitle,
  interactionMode,
  onInteractionModeChange,
  isPlaying,
  onTogglePlay,
  playbackRate,
  onPlaybackRateChange,
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
  nnInteractiveAvailable,
  nnInteractiveBusy,
  onGenerateReport,
  onClearPrompt,
  onUndoPoint,
  onAnalyzeKeyframe,
}: Props) {
  const { language } = useSettings();
  const zh = language !== 'en';
  const modes: { id: InteractionMode; label: string; hint: string }[] = [
    { id: 'box', label: zh ? '框选病灶' : 'Box lesion', hint: '1' },
    { id: 'inspect', label: zh ? '检视轮廓' : 'Inspect', hint: '2' },
    { id: 'positive', label: zh ? '正点' : 'Positive', hint: '3' },
    { id: 'negative', label: zh ? '负点' : 'Negative', hint: '4' },
    { id: 'scribble', label: zh ? '自由涂鸦' : 'Scribble', hint: '5' },
    { id: 'lasso', label: zh ? '套索' : 'Lasso', hint: '6' },
  ];

  return (
    <div className="space-y-2 border-b border-white/10 bg-[#0e1012] px-3 py-2">
      <div className="flex flex-wrap items-center gap-2">
        <div className="min-w-0 flex-1">
          <div className="truncate text-xs font-semibold text-gray-100">{caseTitle}</div>
          <div className="truncate text-[10px] text-gray-500">{frameTitle}</div>
        </div>
        <span className="rounded border border-white/10 bg-black/40 px-2 py-0.5 text-[10px] text-gray-400">
          {promptSummary || (zh ? '未标注' : 'No prompt')}
        </span>
        <span
          className={`rounded border px-2 py-0.5 text-[10px] ${
            nnInteractiveAvailable
              ? 'border-emerald-400/30 bg-emerald-500/10 text-emerald-200'
              : nnInteractiveAvailable === false
                ? 'border-amber-400/30 bg-amber-500/10 text-amber-200'
                : 'border-white/10 bg-black/40 text-gray-500'
          }`}
          title={nnInteractiveAvailable === false
            ? (zh ? '请启动官方 nnInteractive 服务' : 'Start the official nnInteractive service')
            : undefined}
        >
          {nnInteractiveBusy
            ? (zh ? 'nnInteractive 推理中' : 'nnInteractive running')
            : nnInteractiveAvailable
              ? (zh ? 'nnInteractive 已连接' : 'nnInteractive connected')
              : nnInteractiveAvailable === false
                ? (zh ? 'nnInteractive 未连接' : 'nnInteractive offline')
                : (zh ? 'nnInteractive 检查中' : 'nnInteractive checking')}
        </span>
      </div>

      <div className="flex flex-wrap items-center gap-1.5">
        <button type="button" onClick={onTogglePlay} className="reader-btn">
          {isPlaying ? <Pause size={12} /> : <Play size={12} />}
          {isPlaying ? (zh ? '暂停' : 'Pause') : (zh ? '播放' : 'Play')}
        </button>
        <label
          className="inline-flex items-center gap-1 rounded border border-white/10 bg-black/30 px-2 py-1 text-[10px] text-gray-400"
          title={zh ? '播放倍速（与阅片1一致）' : 'Playback speed'}
        >
          {zh ? '倍速' : 'Speed'}
          <select
            aria-label={zh ? '播放倍速' : 'Playback speed'}
            value={String(playbackRate)}
            onChange={(event) => onPlaybackRateChange(Number(event.target.value))}
            className="bg-transparent text-gray-200 outline-none"
          >
            <option value="0.25">0.25×</option>
            <option value="0.5">0.5×</option>
            <option value="1">1×</option>
          </select>
        </label>
        <button
          type="button"
          onClick={onToggleTrack}
          className={`reader-btn ${trackOnPlay ? 'reader-btn-primary' : ''}`}
        >
          {zh ? '自动单帧跟踪' : 'Auto frame track'} / {trackOnPlay ? (zh ? '开' : 'On') : (zh ? '关' : 'Off')}
        </button>
        <button
          type="button"
          onClick={onPropagateVideo}
          className="reader-btn"
          disabled={videoTrackBusy || !hasPrompt}
          title={!hasPrompt
            ? (zh ? '请先框选病灶' : 'Draw a lesion box first')
            : (zh ? '跟踪扩散到整个视频' : 'Propagate tracking across the video')}
        >
          {videoTrackBusy ? <Loader2 size={12} className="animate-spin" /> : <Route size={12} />}
          {videoTrackBusy
            ? (zh ? '跟踪扩散中' : 'Propagating')
            : (zh ? '跟踪扩散' : 'Propagate')}
        </button>
        {videoTrackStatus ? <span className="text-[10px] text-gray-500">{videoTrackStatus}</span> : null}
        <button type="button" onClick={onAnalyzeKeyframe} className="reader-btn" disabled={samBusy}>
          {samBusy ? <Loader2 size={12} className="animate-spin" /> : <Sparkles size={12} />}
          {zh ? '关键帧分析' : 'Analyze frame'}
        </button>
        <button
          type="button"
          onClick={onGenerateReport}
          className="reader-btn reader-btn-primary"
          disabled={reportBusy || !llmReady || !hasPrompt}
          title={!llmReady
            ? (zh ? '未配置 DeepSeek / MiniMax' : 'DeepSeek / MiniMax not configured')
            : !hasPrompt
              ? (zh ? '请先框选病灶' : 'Draw a lesion box first')
              : ''}
        >
          {reportBusy ? <Loader2 size={12} className="animate-spin" /> : <FileText size={12} />}
          {zh ? '生成文字报告' : 'Generate report'}
        </button>
        <button type="button" onClick={onClearPrompt} className="reader-btn">
          <Eraser size={12} /> {zh ? '清除' : 'Clear'}
        </button>
        <button type="button" onClick={onUndoPoint} className="reader-btn">
          <Undo2 size={12} /> {zh ? '撤销轮廓' : 'Undo contour'}
        </button>
      </div>

      <div className="flex flex-wrap items-center gap-1.5">
        <span className="text-[10px] text-gray-500">{zh ? '交互' : 'Interact'}</span>
        {modes.map((m) => (
          <button
            key={m.id}
            type="button"
            onClick={() => onInteractionModeChange(m.id)}
            className={`rounded px-2 py-0.5 text-[10px] font-medium transition-colors ${
              interactionMode === m.id
                ? 'bg-cyan-600/80 text-white'
                : 'bg-white/5 text-gray-400 hover:bg-white/10'
            }`}
            title={zh ? `快捷键 ${m.hint}` : `Shortcut ${m.hint}`}
          >
            {m.label}
          </button>
        ))}
      </div>

      {hasMask ? (
        <div className="flex flex-wrap items-center gap-3 text-[10px] text-gray-400">
          <label className="inline-flex items-center gap-1.5">
            <input type="checkbox" checked={showMask} onChange={onToggleShowMask} />
            {zh ? '显示分割轮廓' : 'Show mask'}
          </label>
          <label className="inline-flex items-center gap-1.5">
            {zh ? '填充' : 'Fill'}
            <input
              type="range"
              min={8}
              max={55}
              value={Math.round(maskOpacity * 100)}
              onChange={(e) => onMaskOpacityChange(Number(e.target.value) / 100)}
            />
          </label>
          <button type="button" onClick={onClearPrompt} className="inline-flex items-center gap-1 text-gray-500 hover:text-gray-300">
            <RotateCcw size={10} /> {zh ? '重置 mask' : 'Reset mask'}
          </button>
        </div>
      ) : null}
    </div>
  );
}
