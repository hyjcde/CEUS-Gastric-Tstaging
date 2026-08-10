'use client';

import React, { useEffect, useRef } from 'react';
import { useSettings } from '@/contexts/SettingsContext';

type Props = {
  currentTime: number;
  duration: number;
  onSeek: (time: number) => void;
  keyframes?: number[];
};

export function ReaderTimeline({ currentTime, duration, onSeek, keyframes = [] }: Props) {
  const { language } = useSettings();
  const zh = language !== 'en';

  const sliderRef = useRef<HTMLInputElement>(null);
  const currentLabelRef = useRef<HTMLSpanElement>(null);
  const scrubbingRef = useRef(false);
  const seekRafRef = useRef<number | null>(null);
  const pendingSeekRef = useRef<number | null>(null);

  useEffect(() => {
    if (scrubbingRef.current) return;
    if (sliderRef.current) sliderRef.current.value = String(currentTime);
    if (currentLabelRef.current) currentLabelRef.current.textContent = formatTime(currentTime);
  }, [currentTime]);

  useEffect(() => {
    if (sliderRef.current) sliderRef.current.max = String(duration || 1);
  }, [duration]);

  const flushSeek = () => {
    seekRafRef.current = null;
    const next = pendingSeekRef.current;
    pendingSeekRef.current = null;
    if (next == null) return;
    onSeek(next);
  };

  const scheduleSeek = (time: number) => {
    pendingSeekRef.current = time;
    if (seekRafRef.current != null) return;
    seekRafRef.current = requestAnimationFrame(flushSeek);
  };

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
              title={zh ? `关键帧 ${t.toFixed(1)}s` : `Keyframe ${t.toFixed(1)}s`}
              onClick={() => onSeek(t)}
            />
          );
        })}
      </div>
      <input
        ref={sliderRef}
        type="range"
        min={0}
        max={duration || 1}
        step={0.05}
        defaultValue={currentTime}
        onPointerDown={() => {
          scrubbingRef.current = true;
        }}
        onPointerUp={() => {
          scrubbingRef.current = false;
          if (seekRafRef.current != null) {
            cancelAnimationFrame(seekRafRef.current);
            seekRafRef.current = null;
          }
          const value = Number(sliderRef.current?.value || currentTime);
          onSeek(value);
        }}
        onPointerCancel={() => {
          scrubbingRef.current = false;
        }}
        onChange={(e) => {
          const next = Number(e.target.value);
          if (currentLabelRef.current) currentLabelRef.current.textContent = formatTime(next);
          if (!scrubbingRef.current) {
            onSeek(next);
            return;
          }
          scheduleSeek(next);
        }}
        className="video-progress w-full"
      />
      <div className="mt-0.5 flex justify-between text-[10px] text-gray-500">
        <span ref={currentLabelRef}>{formatTime(currentTime)}</span>
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
