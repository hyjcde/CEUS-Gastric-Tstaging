'use client';

import React from 'react';

type Props = {
  currentTime: number;
  duration: number;
  onSeek: (time: number) => void;
  keyframes?: number[];
};

export function ReaderTimeline({ currentTime, duration, onSeek, keyframes = [] }: Props) {
  const pct = duration > 0 ? (currentTime / duration) * 100 : 0;
  return (
    <div className="border-t border-white/10 bg-[#0e1012] px-3 py-2">
      <div className="relative mb-1 h-6">
        {keyframes.map((t, i) => {
          const left = duration > 0 ? (t / duration) * 100 : 0;
          return (
            <button
              key={`${t}-${i}`}
              type="button"
              className="absolute top-1 h-4 w-0.5 -translate-x-1/2 rounded bg-amber-400/80 hover:bg-amber-300"
              style={{ left: `${left}%` }}
              title={`关键帧 ${t.toFixed(1)}s`}
              onClick={() => onSeek(t)}
            />
          );
        })}
      </div>
      <input
        type="range"
        min={0}
        max={duration || 1}
        step={0.05}
        value={currentTime}
        onChange={(e) => onSeek(Number(e.target.value))}
        className="w-full accent-emerald-500"
      />
      <div className="mt-0.5 flex justify-between text-[10px] text-gray-500">
        <span>{formatTime(currentTime)}</span>
        <span>{formatTime(duration)}</span>
      </div>
    </div>
  );
}

function formatTime(sec: number): string {
  if (!Number.isFinite(sec)) return '00:00';
  const m = Math.floor(sec / 60);
  const s = Math.floor(sec % 60);
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
}
