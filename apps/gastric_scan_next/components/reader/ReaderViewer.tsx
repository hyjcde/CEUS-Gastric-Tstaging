'use client';

import React, { useCallback, useEffect, useRef } from 'react';
import type { InteractionMode, SamBox, SamClick } from '@/lib/reader/types';

export type ViewerTransform = {
  vw: number;
  vh: number;
  scale: number;
  offsetX: number;
  offsetY: number;
};

type Props = {
  videoSrc: string;
  interactionMode: InteractionMode;
  clicks: SamClick[];
  box: SamBox | null;
  maskPolygon: number[][] | null;
  showMask: boolean;
  maskOpacity: number;
  maskOverlayPng?: string | null;
  onVideoReady: (video: HTMLVideoElement) => void;
  onTimeUpdate: (time: number, duration: number) => void;
  onAddClick: (click: SamClick) => void;
  onSetBox: (box: SamBox | null) => void;
  onPointerUpAfterBox?: () => void;
  badge?: string | null;
  hint?: string;
};

function getTransform(video: HTMLVideoElement, container: HTMLElement): ViewerTransform {
  const rect = container.getBoundingClientRect();
  const vw = video.videoWidth || 1;
  const vh = video.videoHeight || 1;
  const scale = Math.min(rect.width / vw, rect.height / vh);
  const renderW = vw * scale;
  const renderH = vh * scale;
  return {
    vw,
    vh,
    scale,
    offsetX: (rect.width - renderW) / 2,
    offsetY: (rect.height - renderH) / 2,
  };
}

function clientToImage(clientX: number, clientY: number, video: HTMLVideoElement, container: HTMLElement) {
  const rect = container.getBoundingClientRect();
  const t = getTransform(video, container);
  const localX = clientX - rect.left;
  const localY = clientY - rect.top;
  const x = (localX - t.offsetX) / t.scale;
  const y = (localY - t.offsetY) / t.scale;
  return {
    x,
    y,
    inVideo: x >= 0 && y >= 0 && x <= t.vw && y <= t.vh,
    image_width: t.vw,
    image_height: t.vh,
  };
}

function imageToCanvas(ix: number, iy: number, t: ViewerTransform) {
  return { x: t.offsetX + ix * t.scale, y: t.offsetY + iy * t.scale };
}

export function ReaderViewer({
  videoSrc,
  interactionMode,
  clicks,
  box,
  maskPolygon,
  showMask,
  maskOpacity,
  maskOverlayPng,
  onVideoReady,
  onTimeUpdate,
  onAddClick,
  onSetBox,
  onPointerUpAfterBox,
  badge,
  hint,
}: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const videoRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const overlayImgRef = useRef<HTMLImageElement | null>(null);
  const dragRef = useRef<{ startX: number; startY: number; active: boolean } | null>(null);

  const redraw = useCallback(() => {
    const video = videoRef.current;
    const canvas = canvasRef.current;
    const container = containerRef.current;
    if (!video || !canvas || !container) return;
    const rect = container.getBoundingClientRect();
    canvas.width = rect.width;
    canvas.height = rect.height;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    const t = getTransform(video, container);

    if (showMask && maskOverlayPng && overlayImgRef.current?.complete) {
      ctx.globalAlpha = maskOpacity;
      ctx.drawImage(
        overlayImgRef.current,
        t.offsetX,
        t.offsetY,
        t.vw * t.scale,
        t.vh * t.scale,
      );
      ctx.globalAlpha = 1;
    } else if (showMask && maskPolygon && maskPolygon.length >= 3) {
      ctx.beginPath();
      maskPolygon.forEach(([x, y], i) => {
        const p = imageToCanvas(x, y, t);
        if (i === 0) ctx.moveTo(p.x, p.y);
        else ctx.lineTo(p.x, p.y);
      });
      ctx.closePath();
      ctx.fillStyle = `rgba(34, 211, 238, ${maskOpacity})`;
      ctx.fill();
      ctx.strokeStyle = 'rgba(34, 211, 238, 0.95)';
      ctx.lineWidth = 2;
      ctx.stroke();
    }

    if (box) {
      const p1 = imageToCanvas(box.x1, box.y1, t);
      const p2 = imageToCanvas(box.x2, box.y2, t);
      ctx.strokeStyle = 'rgba(52, 211, 153, 0.95)';
      ctx.lineWidth = 2;
      ctx.setLineDash([6, 4]);
      ctx.strokeRect(
        Math.min(p1.x, p2.x),
        Math.min(p1.y, p2.y),
        Math.abs(p2.x - p1.x),
        Math.abs(p2.y - p1.y),
      );
      ctx.setLineDash([]);
    }

    clicks.forEach((c) => {
      const p = imageToCanvas(c.x, c.y, t);
      const neg = c.label === 'negative';
      ctx.beginPath();
      ctx.arc(p.x, p.y, 6, 0, Math.PI * 2);
      ctx.fillStyle = neg ? 'rgba(248, 113, 113, 0.95)' : 'rgba(52, 211, 153, 0.95)';
      ctx.fill();
      ctx.strokeStyle = '#fff';
      ctx.lineWidth = 1.5;
      ctx.stroke();
    });
  }, [box, clicks, maskOpacity, maskOverlayPng, maskPolygon, showMask]);

  useEffect(() => {
    if (!maskOverlayPng) {
      overlayImgRef.current = null;
      redraw();
      return;
    }
    const img = new Image();
    img.onload = () => {
      overlayImgRef.current = img;
      redraw();
    };
    img.src = maskOverlayPng.startsWith('data:') ? maskOverlayPng : `data:image/png;base64,${maskOverlayPng}`;
  }, [maskOverlayPng, redraw]);

  useEffect(() => {
    redraw();
    const onResize = () => redraw();
    window.addEventListener('resize', onResize);
    return () => window.removeEventListener('resize', onResize);
  }, [redraw]);

  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;
    const onLoaded = () => {
      onVideoReady(video);
      redraw();
    };
    const onTime = () => onTimeUpdate(video.currentTime, video.duration || 0);
    video.addEventListener('loadedmetadata', onLoaded);
    video.addEventListener('timeupdate', onTime);
    return () => {
      video.removeEventListener('loadedmetadata', onLoaded);
      video.removeEventListener('timeupdate', onTime);
    };
  }, [onTimeUpdate, onVideoReady, redraw, videoSrc]);

  const handlePointerDown = (e: React.PointerEvent) => {
    const video = videoRef.current;
    const container = containerRef.current;
    if (!video || !container || interactionMode === 'inspect') return;
    if (interactionMode === 'box') {
      const pt = clientToImage(e.clientX, e.clientY, video, container);
      if (!pt.inVideo) return;
      dragRef.current = { startX: pt.x, startY: pt.y, active: true };
      (e.target as HTMLElement).setPointerCapture(e.pointerId);
      return;
    }
    const pt = clientToImage(e.clientX, e.clientY, video, container);
    if (!pt.inVideo) return;
    onAddClick({
      x: pt.x,
      y: pt.y,
      label: interactionMode === 'negative' ? 'negative' : 'positive',
    });
  };

  const handlePointerMove = (e: React.PointerEvent) => {
    const video = videoRef.current;
    const container = containerRef.current;
    const drag = dragRef.current;
    if (!video || !container || !drag?.active || interactionMode !== 'box') return;
    const pt = clientToImage(e.clientX, e.clientY, video, container);
    onSetBox({
      x1: Math.min(drag.startX, pt.x),
      y1: Math.min(drag.startY, pt.y),
      x2: Math.max(drag.startX, pt.x),
      y2: Math.max(drag.startY, pt.y),
    });
    redraw();
  };

  const handlePointerUp = () => {
    if (dragRef.current?.active && interactionMode === 'box') {
      dragRef.current.active = false;
      onPointerUpAfterBox?.();
    }
    dragRef.current = null;
  };

  return (
    <div ref={containerRef} className="relative flex min-h-0 flex-1 items-center justify-center bg-black">
      <video
        ref={videoRef}
        key={videoSrc}
        src={videoSrc}
        className="max-h-full max-w-full object-contain"
        loop
        muted
        playsInline
        preload="metadata"
      />
      <div
        className={`absolute inset-0 ${interactionMode === 'box' ? 'cursor-crosshair' : 'cursor-pointer'}`}
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={handlePointerUp}
        onPointerLeave={handlePointerUp}
      >
        <canvas ref={canvasRef} className="absolute inset-0 h-full w-full" />
      </div>
      {hint ? (
        <div className="pointer-events-none absolute bottom-3 left-1/2 max-w-[90%] -translate-x-1/2 rounded-lg border border-white/10 bg-black/70 px-3 py-1.5 text-center text-[10px] text-gray-300 backdrop-blur">
          {hint}
        </div>
      ) : null}
      {badge ? (
        <div className="pointer-events-none absolute right-3 top-3 rounded-lg border border-emerald-500/30 bg-black/75 px-2.5 py-1 text-[10px] text-emerald-200 backdrop-blur">
          {badge}
        </div>
      ) : null}
    </div>
  );
}

export function getVideoElementFromViewer(container: HTMLElement | null): HTMLVideoElement | null {
  return container?.querySelector('video') ?? null;
}
