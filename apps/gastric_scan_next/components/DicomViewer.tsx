"use client";

import { Patient } from '@/types';
import {
  Activity,
  AlertCircle,
  ChevronLeft,
  ChevronRight,
  Loader2,
  Minus,
  Plus,
  RotateCcw,
  SlidersHorizontal,
} from 'lucide-react';
import React, { useCallback, useEffect, useRef, useState } from 'react';

interface DicomFrame {
  filename: string;
  index: number;
  isDicom: boolean;
  url: string;
}

interface DicomViewerProps {
  patient: Patient;
  language?: string;
}

interface WindowLevel {
  window: number;
  level: number;
}

function applyWindowLevel(
  pixelData: Uint8Array | Uint16Array | Int16Array,
  width: number,
  height: number,
  wl: WindowLevel,
  canvas: HTMLCanvasElement,
  bitsAllocated: number,
  isSigned: boolean
) {
  canvas.width = width;
  canvas.height = height;
  const ctx = canvas.getContext('2d');
  if (!ctx) return;

  const imgData = ctx.createImageData(width, height);
  const data = imgData.data;
  const wMin = wl.level - wl.window / 2;
  const wMax = wl.level + wl.window / 2;
  const range = wMax - wMin || 1;

  for (let i = 0; i < width * height; i++) {
    const val = pixelData[i] ?? 0;
    // Clamp to window
    const mapped = Math.min(255, Math.max(0, Math.round(((val - wMin) / range) * 255)));
    data[i * 4]     = mapped;
    data[i * 4 + 1] = mapped;
    data[i * 4 + 2] = mapped;
    data[i * 4 + 3] = 255;
  }
  ctx.putImageData(imgData, 0, 0);
}

export const DicomViewer: React.FC<DicomViewerProps> = ({ patient, language = 'zh' }) => {
  const [frames, setFrames] = useState<DicomFrame[]>([]);
  const [currentFrame, setCurrentFrame] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [wl, setWl] = useState<WindowLevel>({ window: 400, level: 200 });
  const [showControls, setShowControls] = useState(false);
  const [frameLoading, setFrameLoading] = useState(false);
  const [metadata, setMetadata] = useState<Record<string, string>>({});
  const [isJpegFrame, setIsJpegFrame] = useState(false);

  const canvasRef = useRef<HTMLCanvasElement>(null);
  const imgRef = useRef<HTMLImageElement>(null);

  // Extract cohort and treatment from patient data
  const cohort = patient.group?.includes('2024') ? '2024'
    : patient.group?.includes('2019') ? '2019'
    : '2024';
  const treatment = patient.group?.toLowerCase().includes('nac') || patient.phase?.toLowerCase().includes('nac')
    ? 'nac' : 'surgery';

  // Load available frames for this patient
  useEffect(() => {
    if (!patient.patient_id) return;
    setLoading(true);
    setError(null);
    setFrames([]);
    setCurrentFrame(0);

    fetch(`/api/dicom?patient_id=${patient.patient_id}&cohort=${cohort}&treatment=${treatment}`)
      .then(r => r.json())
      .then(data => {
        if (data.frames && data.frames.length > 0) {
          setFrames(data.frames);
        } else {
          setError(language === 'zh' ? '该患者无可用DICOM文件' : 'No DICOM files available for this patient');
        }
      })
      .catch(() => setError(language === 'zh' ? '加载DICOM列表失败' : 'Failed to load DICOM list'))
      .finally(() => setLoading(false));
  }, [patient.patient_id, cohort, treatment, language]);

  // Render current frame
  const renderFrame = useCallback(async (frame: DicomFrame) => {
    if (!frame) return;
    setFrameLoading(true);
    setMetadata({});

    try {
      // Plain JPEG files - display directly
      if (!frame.isDicom) {
        setIsJpegFrame(true);
        if (imgRef.current) {
          imgRef.current.src = frame.url;
        }
        setFrameLoading(false);
        return;
      }

      // DICOM file - parse with dicom-parser
      const response = await fetch(frame.url);
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const arrayBuffer = await response.arrayBuffer();
      const byteArray = new Uint8Array(arrayBuffer);

      // Dynamic import to avoid SSR issues
      const dicomParser = (await import('dicom-parser')).default;
      const dataSet = dicomParser.parseDicom(byteArray, { untilTag: undefined });

      // Extract metadata
      const extractedMeta: Record<string, string> = {};
      const transferSyntax = dataSet.string('x00020010') || '';
      const rows = dataSet.uint16('x00280010') || 0;
      const cols = dataSet.uint16('x00280011') || 0;
      const bitsAllocated = dataSet.uint16('x00280100') || 8;
      const pixelRepresentation = dataSet.uint16('x00280103') || 0;
      const samplesPerPixel = dataSet.uint16('x00280002') || 1;
      const photometricInterpretation = dataSet.string('x00280004') || '';
      const windowCenter = dataSet.floatString('x00281050');
      const windowWidth = dataSet.floatString('x00281051');
      const modality = dataSet.string('x00080060') || '';
      const instanceNumber = dataSet.string('x00200013') || '';

      if (rows) extractedMeta['Size'] = `${cols}×${rows}`;
      if (modality) extractedMeta['Modality'] = modality;
      if (bitsAllocated) extractedMeta['Bits'] = `${bitsAllocated}`;
      if (photometricInterpretation) extractedMeta['Photometric'] = photometricInterpretation;
      if (instanceNumber) extractedMeta['Instance'] = instanceNumber;
      setMetadata(extractedMeta);

      // Update W/L from DICOM tags if not manually set
      if (windowCenter !== undefined && windowWidth !== undefined) {
        setWl({ window: windowWidth, level: windowCenter });
      } else if (bitsAllocated === 8) {
        setWl({ window: 256, level: 128 });
      }

      const pixelDataElement = dataSet.elements['x7fe00010'];
      if (!pixelDataElement) throw new Error('No pixel data found');

      // Detect JPEG compression (most ultrasound DICOMs use JPEG Baseline)
      const isJpeg =
        transferSyntax === '1.2.840.10008.1.2.4.50' || // JPEG Baseline
        transferSyntax === '1.2.840.10008.1.2.4.51' || // JPEG Extended
        transferSyntax === '1.2.840.10008.1.2.4.57' || // JPEG Lossless
        transferSyntax === '1.2.840.10008.1.2.4.70' || // JPEG Lossless SV1
        pixelDataElement.encapsulatedPixelData === true;

      if (isJpeg || pixelDataElement.encapsulatedPixelData) {
        // Encapsulated (JPEG): extract first fragment and display as image
        setIsJpegFrame(true);
        const fragmentStart = (pixelDataElement.fragments && pixelDataElement.fragments[0])
          ? pixelDataElement.fragments[0].position
          : pixelDataElement.dataOffset;
        const fragmentLength = (pixelDataElement.fragments && pixelDataElement.fragments[0])
          ? pixelDataElement.fragments[0].length
          : pixelDataElement.length;

        const fragment = byteArray.slice(fragmentStart, fragmentStart + fragmentLength);
        const blob = new Blob([fragment], { type: 'image/jpeg' });
        const url = URL.createObjectURL(blob);

        if (imgRef.current) {
          imgRef.current.onload = () => URL.revokeObjectURL(url);
          imgRef.current.src = url;
        }
      } else {
        // Uncompressed pixel data → render to canvas
        setIsJpegFrame(false);
        const canvas = canvasRef.current;
        if (!canvas || !rows || !cols) throw new Error('Invalid image dimensions');

        const pixelDataOffset = pixelDataElement.dataOffset;
        const pixelDataLength = pixelDataElement.length;
        const rawBytes = byteArray.slice(pixelDataOffset, pixelDataOffset + pixelDataLength);

        let pixelArray: Uint8Array | Uint16Array | Int16Array;
        if (bitsAllocated === 16) {
          const buffer = rawBytes.buffer.slice(rawBytes.byteOffset, rawBytes.byteOffset + rawBytes.byteLength);
          pixelArray = pixelRepresentation === 1
            ? new Int16Array(buffer)
            : new Uint16Array(buffer);
        } else {
          pixelArray = rawBytes;
        }

        // For RGB, handle separately
        if (samplesPerPixel === 3 || photometricInterpretation === 'RGB') {
          canvas.width = cols;
          canvas.height = rows;
          const ctx = canvas.getContext('2d');
          if (ctx) {
            const imgData = ctx.createImageData(cols, rows);
            for (let i = 0; i < cols * rows; i++) {
              imgData.data[i * 4]     = rawBytes[i * 3] ?? 0;
              imgData.data[i * 4 + 1] = rawBytes[i * 3 + 1] ?? 0;
              imgData.data[i * 4 + 2] = rawBytes[i * 3 + 2] ?? 0;
              imgData.data[i * 4 + 3] = 255;
            }
            ctx.putImageData(imgData, 0, 0);
          }
        } else {
          applyWindowLevel(pixelArray, cols, rows, wl, canvas, bitsAllocated, pixelRepresentation === 1);
        }
      }
    } catch (err) {
      console.error('[DicomViewer] Render error:', err);
      setError(language === 'zh' ? `渲染失败: ${(err as Error).message}` : `Render failed: ${(err as Error).message}`);
    } finally {
      setFrameLoading(false);
    }
  }, [wl, language]);

  useEffect(() => {
    const frame = frames[currentFrame];
    if (frame) renderFrame(frame);
  }, [frames, currentFrame, renderFrame]);

  // Re-apply W/L when slider changes (only for canvas-rendered frames)
  const handleWLChange = useCallback(() => {
    if (isJpegFrame) return; // JPEG frames don't need re-rendering
    const frame = frames[currentFrame];
    if (frame?.isDicom) renderFrame(frame);
  }, [isJpegFrame, frames, currentFrame, renderFrame]);

  if (loading) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center gap-3 text-gray-500">
        <Loader2 size={32} className="animate-spin text-blue-500" />
        <span className="text-[11px] font-mono uppercase tracking-widest">
          {language === 'zh' ? '加载DICOM...' : 'Loading DICOM...'}
        </span>
      </div>
    );
  }

  if (error && frames.length === 0) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center gap-3 text-gray-500">
        <AlertCircle size={32} className="text-amber-500" />
        <span className="text-[11px] font-mono text-center px-8">{error}</span>
        <span className="text-[9px] text-gray-600 font-mono">Patient ID: {patient.patient_id}</span>
      </div>
    );
  }

  const frame = frames[currentFrame];

  return (
    <div className="flex flex-col h-full w-full bg-black relative select-none">

      {/* Top Info Bar */}
        <div className="absolute top-0 left-0 right-0 z-20 flex items-center justify-between px-4 py-2 bg-linear-to-b from-black/90 to-transparent pointer-events-none">
        <div className="flex items-center gap-3">
          <div className="w-1.5 h-1.5 rounded-full bg-violet-500 shadow-[0_0_8px_#8b5cf6]" />
          <span className="text-[10px] font-mono font-black text-gray-300 uppercase tracking-widest">
            DICOM RAW
          </span>
          <span className="text-[9px] font-mono text-violet-400/70">
            {frame?.filename}
          </span>
        </div>
        <div className="flex items-center gap-4 text-[9px] font-mono text-gray-500">
          {Object.entries(metadata).map(([k, v]) => (
            <span key={k}><span className="text-gray-600">{k}:</span> {v}</span>
          ))}
          {!isJpegFrame && (
            <span className="text-violet-400/70">W:{Math.round(wl.window)} L:{Math.round(wl.level)}</span>
          )}
        </div>
      </div>

      {/* Main Image Area */}
      <div className="flex-1 flex items-center justify-center overflow-hidden relative">
        {frameLoading && (
          <div className="absolute inset-0 z-30 flex items-center justify-center bg-black/60">
            <Loader2 size={24} className="animate-spin text-violet-400" />
          </div>
        )}

        {/* JPEG display (most ultrasound DICOMs) */}
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          ref={imgRef}
          alt="DICOM frame"
          className={`max-h-full max-w-full object-contain transition-opacity duration-300 ${isJpegFrame ? 'block' : 'hidden'}`}
          onError={() => setError(language === 'zh' ? '图像解码失败' : 'Image decode failed')}
        />

        {/* Canvas display (uncompressed DICOMs) */}
        <canvas
          ref={canvasRef}
          className={`max-h-full max-w-full object-contain ${!isJpegFrame ? 'block' : 'hidden'}`}
          style={{ imageRendering: 'pixelated' }}
        />
      </div>

      {/* Bottom Controls */}
      <div className="absolute bottom-0 left-0 right-0 z-20 flex flex-col gap-2 px-4 py-3 bg-linear-to-t from-black/95 to-transparent">

        {/* W/L Controls (only for uncompressed) */}
        {showControls && !isJpegFrame && (
          <div className="flex items-center gap-4 mb-1 bg-black/60 backdrop-blur border border-white/10 rounded-xl px-4 py-2 animate-in slide-in-from-bottom-2">
            <span className="text-[9px] font-mono text-gray-500 uppercase w-12">Window</span>
            <input
              type="range" min="1" max="4096"
              value={wl.window}
              onChange={e => { setWl(prev => ({ ...prev, window: Number(e.target.value) })); handleWLChange(); }}
              className="flex-1 accent-violet-500"
            />
            <span className="text-[9px] font-mono text-violet-400 w-12 text-right">{Math.round(wl.window)}</span>

            <div className="w-px h-4 bg-white/10" />

            <span className="text-[9px] font-mono text-gray-500 uppercase w-8">Level</span>
            <input
              type="range" min="-1024" max="3072"
              value={wl.level}
              onChange={e => { setWl(prev => ({ ...prev, level: Number(e.target.value) })); handleWLChange(); }}
              className="flex-1 accent-violet-500"
            />
            <span className="text-[9px] font-mono text-violet-400 w-12 text-right">{Math.round(wl.level)}</span>

            <button
              onClick={() => setWl({ window: 400, level: 200 })}
              className="p-1 text-gray-500 hover:text-white transition-colors"
              title="Reset W/L"
            >
              <RotateCcw size={12} />
            </button>
          </div>
        )}

        {/* Frame Navigation */}
        <div className="flex items-center justify-between gap-3">
          {/* Left: Tools */}
          <div className="flex items-center gap-2">
            {!isJpegFrame && (
              <button
                onClick={() => setShowControls(p => !p)}
                className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-[9px] font-mono transition-all border ${
                  showControls
                    ? 'bg-violet-500/20 border-violet-500/40 text-violet-400'
                    : 'bg-white/5 border-white/10 text-gray-500 hover:text-gray-300'
                }`}
              >
                <SlidersHorizontal size={11} />
                W/L
              </button>
            )}
            <div className="flex items-center gap-1 bg-white/5 border border-white/10 rounded-lg px-2 py-1">
              <Activity size={11} className="text-violet-400" />
              <span className="text-[9px] font-mono text-gray-400">
                {frames.filter(f => f.isDicom).length} DCM · {frames.filter(f => !f.isDicom).length} JPG
              </span>
            </div>
          </div>

          {/* Center: Frame navigation */}
          <div className="flex items-center gap-2">
            <button
              onClick={() => setCurrentFrame(p => Math.max(0, p - 1))}
              disabled={currentFrame === 0}
              className="p-1.5 rounded-lg bg-white/5 border border-white/10 text-gray-400 hover:text-white hover:bg-white/10 disabled:opacity-30 disabled:cursor-not-allowed transition-all"
            >
              <ChevronLeft size={14} />
            </button>

            {/* Frame dots (max 12 visible) */}
            <div className="flex items-center gap-1 overflow-hidden max-w-[200px]">
              {frames.slice(
                Math.max(0, currentFrame - 5),
                Math.min(frames.length, currentFrame + 7)
              ).map((f, i) => {
                const absIdx = Math.max(0, currentFrame - 5) + i;
                return (
                  <button
                    key={f.filename}
                    onClick={() => setCurrentFrame(absIdx)}
                    title={f.filename}
                    className={`rounded-full shrink-0 transition-all ${
                      absIdx === currentFrame
                        ? 'w-4 h-2 bg-violet-500'
                        : f.isDicom
                        ? 'w-1.5 h-1.5 bg-gray-600 hover:bg-gray-400'
                        : 'w-1.5 h-1.5 bg-amber-700 hover:bg-amber-500'
                    }`}
                  />
                );
              })}
            </div>

            <button
              onClick={() => setCurrentFrame(p => Math.min(frames.length - 1, p + 1))}
              disabled={currentFrame === frames.length - 1}
              className="p-1.5 rounded-lg bg-white/5 border border-white/10 text-gray-400 hover:text-white hover:bg-white/10 disabled:opacity-30 disabled:cursor-not-allowed transition-all"
            >
              <ChevronRight size={14} />
            </button>

            <span className="text-[9px] font-mono text-gray-500 min-w-[48px] text-center">
              {currentFrame + 1} / {frames.length}
            </span>
          </div>

          {/* Right: Zoom buttons placeholder */}
          <div className="flex items-center gap-1">
            <button
              onClick={() => {
                if (!isJpegFrame) {
                  setWl(prev => ({ ...prev, window: Math.max(1, prev.window - 50) }));
                  handleWLChange();
                }
              }}
              disabled={isJpegFrame}
              className="p-1.5 rounded-lg bg-white/5 border border-white/10 text-gray-500 hover:text-white hover:bg-white/10 disabled:opacity-20 disabled:cursor-not-allowed transition-all"
              title={language === 'zh' ? '减小窗宽' : 'Narrow Window'}
            >
              <Minus size={12} />
            </button>
            <button
              onClick={() => {
                if (!isJpegFrame) {
                  setWl(prev => ({ ...prev, window: Math.min(4096, prev.window + 50) }));
                  handleWLChange();
                }
              }}
              disabled={isJpegFrame}
              className="p-1.5 rounded-lg bg-white/5 border border-white/10 text-gray-500 hover:text-white hover:bg-white/10 disabled:opacity-20 disabled:cursor-not-allowed transition-all"
              title={language === 'zh' ? '增大窗宽' : 'Widen Window'}
            >
              <Plus size={12} />
            </button>
          </div>
        </div>

      </div>
    </div>
  );
};
