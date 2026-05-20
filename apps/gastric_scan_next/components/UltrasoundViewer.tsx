"use client";

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Patient } from '@/types';
import { Columns, Eye, Layers, Maximize2, RefreshCw, Ruler, Scan, Settings2, Undo2, XCircle, CircleDashed, ZoomIn, Minimize2, Brain, Grid2X2, ChevronLeft, ChevronRight, Video, FileStack } from 'lucide-react';
import { ExplainableAnalysis } from './ExplainableAnalysis';
import { DicomViewer } from './DicomViewer';
import { VideoPlayer } from './VideoPlayer';
import { useSettings } from '@/contexts/SettingsContext';
import { 
  AnnotationBbox, 
  calculateDetectionOverlayStyle, 
  calculateDistanceCm, 
  extractAnnotationBbox, 
  ImageMetrics 
} from '@/lib/image-utils';
import { generatePeritumoralRingFromAnnotation } from '@/lib/morphology';
import { OptimizedImage } from './OptimizedImage';
import toast from 'react-hot-toast';

interface UltrasoundViewerProps {
  patient: Patient | null;
  siblingImages?: Patient[];
  onSelectSibling?: (patient: Patient) => void;
}

type ViewMode = 'original' | 'overlay' | 'roi' | 'heatmap' | 'split' | 'multi' | 'video' | 'dicom';

export const UltrasoundViewer: React.FC<UltrasoundViewerProps> = ({ patient, siblingImages = [], onSelectSibling }) => {
  const { t, language, dataset } = useSettings();
  const containerRef = useRef<HTMLDivElement>(null);
  const [mode, setMode] = useState<ViewMode>('original');
  
  // Image Adjustment State
  const [showControls, setShowControls] = useState(false);
  const [brightness, setBrightness] = useState(100);
  const [contrast, setContrast] = useState(100);
  
  // Zoom & Pan State
  const [scale, setScale] = useState(1);
  const [position, setPosition] = useState({ x: 0, y: 0 });
  const [isDragging, setIsDragging] = useState(false);
  const [startPos, setStartPos] = useState({ x: 0, y: 0 });

  // Measurement State
  const [isMeasuring, setIsMeasuring] = useState(false);
  const [measurements, setMeasurements] = useState<Array<{id: number, start: {x:number, y:number}, end: {x:number, y:number}}>>([]);
  const [activeMeasurement, setActiveMeasurement] = useState<{start: {x:number, y:number}, end: {x:number, y:number}} | null>(null);
  const [showDetectionBox, setShowDetectionBox] = useState(false);
  const [showRing, setShowRing] = useState(false);
  const [ringImageUrl, setRingImageUrl] = useState<string | null>(null);
  const [annotationBbox, setAnnotationBbox] = useState<AnnotationBbox | null>(null);
  const [imageMetrics, setImageMetrics] = useState<ImageMetrics | null>(null);
  const [zoomToROI, setZoomToROI] = useState(false);
  const [showExplainableAnalysis, setShowExplainableAnalysis] = useState(false);
  const imageWrapperRef = useRef<HTMLDivElement>(null);
  const imageRef = useRef<HTMLImageElement>(null);

  const resetAdjustments = () => {
      setBrightness(100);
      setContrast(100);
      setScale(1);
      setPosition({ x: 0, y: 0 });
      setMeasurements([]);
      setActiveMeasurement(null);
      setIsMeasuring(false);
      setShowRing(false);
      setZoomToROI(false);
  }
  
  // 计算 ROI 放大参数
  const roiZoomParams = useMemo(() => {
    if (!zoomToROI || !annotationBbox || !imageMetrics) return null;
    
    // ROI 在原始图像中的坐标
    const roiX = annotationBbox.x1;
    const roiY = annotationBbox.y1;
    const roiWidth = annotationBbox.x2 - annotationBbox.x1;
    const roiHeight = annotationBbox.y2 - annotationBbox.y1;
    
    // 添加 20% 的边距
    const padding = 0.2;
    const paddedWidth = roiWidth * (1 + padding * 2);
    const paddedHeight = roiHeight * (1 + padding * 2);
    const paddedX = roiX - roiWidth * padding;
    const paddedY = roiY - roiHeight * padding;
    
    // 计算需要的缩放比例（使 ROI 填充显示区域）
    const scaleX = imageMetrics.naturalWidth / paddedWidth;
    const scaleY = imageMetrics.naturalHeight / paddedHeight;
    const targetScale = Math.min(scaleX, scaleY, 4); // 最大 4x
    
    // 计算 ROI 中心点在原始图像中的位置
    const roiCenterX = paddedX + paddedWidth / 2;
    const roiCenterY = paddedY + paddedHeight / 2;
    
    // 计算偏移量（使 ROI 中心对齐到显示区域中心）
    const imageCenterX = imageMetrics.naturalWidth / 2;
    const imageCenterY = imageMetrics.naturalHeight / 2;
    
    // 显示尺寸下的偏移
    const offsetX = (imageCenterX - roiCenterX) * (imageMetrics.displayWidth / imageMetrics.naturalWidth);
    const offsetY = (imageCenterY - roiCenterY) * (imageMetrics.displayHeight / imageMetrics.naturalHeight);
    
    return {
      scale: targetScale,
      offsetX: offsetX * targetScale,
      offsetY: offsetY * targetScale
    };
  }, [zoomToROI, annotationBbox, imageMetrics]);
  
  // 切换 ROI 放大模式
  const toggleZoomToROI = useCallback(() => {
    if (!annotationBbox) return;
    
    if (zoomToROI) {
      // 退出 ROI 放大模式，恢复正常
      setZoomToROI(false);
      setScale(1);
      setPosition({ x: 0, y: 0 });
    } else {
      // 进入 ROI 放大模式
      setZoomToROI(true);
      if (roiZoomParams) {
        setScale(roiZoomParams.scale);
        setPosition({ x: roiZoomParams.offsetX, y: roiZoomParams.offsetY });
      }
    }
  }, [annotationBbox, zoomToROI, roiZoomParams]);
  
  // 当 roiZoomParams 变化且处于 ROI 模式时，更新缩放和位置
  useEffect(() => {
    if (zoomToROI && roiZoomParams) {
      setScale(roiZoomParams.scale);
      setPosition({ x: roiZoomParams.offsetX, y: roiZoomParams.offsetY });
    }
  }, [zoomToROI, roiZoomParams]);

  const updateImageMetrics = useCallback(() => {
    const img = imageRef.current;
    if (!img || !img.naturalWidth || !img.naturalHeight) {
      setImageMetrics(null);
      return;
    }
    setImageMetrics({
      displayWidth: img.offsetWidth,
      displayHeight: img.offsetHeight,
      naturalWidth: img.naturalWidth,
      naturalHeight: img.naturalHeight,
      offsetLeft: img.offsetLeft,
      offsetTop: img.offsetTop
    });
  }, []);

  useEffect(() => {
    updateImageMetrics();
  }, [patient, mode, updateImageMetrics]);

  useEffect(() => {
    window.addEventListener('resize', updateImageMetrics);
    return () => window.removeEventListener('resize', updateImageMetrics);
  }, [updateImageMetrics]);

  useEffect(() => {
    if (!annotationBbox) {
      setShowDetectionBox(false);
    }
  }, [annotationBbox]);

  useEffect(() => {
    resetAdjustments();
    setMode('original');
  }, [patient?.id, dataset]);

  useEffect(() => {
    if (!patient) {
      setAnnotationBbox(null);
      setRingImageUrl(null);
      return;
    }

    const controller = new AbortController();
    const loadAnnotations = async () => {
      try {
        const response = await fetch(patient.json_url, { signal: controller.signal });
        if (!response.ok) throw new Error('Annotation download failed');
        const payload = await response.json();
        const bbox = extractAnnotationBbox(payload.shapes);
        if (bbox) {
          setAnnotationBbox(bbox);
        } else {
          setAnnotationBbox(null);
        }
      } catch (error) {
        if (!(error instanceof DOMException && error.name === 'AbortError')) {
          console.error('Failed to load ROI annotation', error);
          toast.error('Failed to load annotation data');
        }
        setAnnotationBbox(null);
      }
    };

    loadAnnotations();

    return () => controller.abort();
  }, [patient]);
  
  // Effect to generate peritumoral ring
  useEffect(() => {
    if (showRing && patient && patient.json_url && imageMetrics) {
      console.log('[Ring] Generating ring from annotation:', patient.json_url);
      console.log('[Ring] Image dimensions:', imageMetrics.naturalWidth, 'x', imageMetrics.naturalHeight);
      
      generatePeritumoralRingFromAnnotation(
        patient.json_url,
        imageMetrics.naturalWidth,
        imageMetrics.naturalHeight,
        20, // radius in pixels (~5mm)
        [255, 165, 0, 200] // Orange color
      )
        .then(url => {
           console.log('[Ring] Generated successfully, data URL length:', url.length);
           setRingImageUrl(url);
        })
        .catch(err => {
           console.error("[Ring] Failed to generate peritumoral ring", err);
           toast.error(language === 'zh' ? "生成瘤周环失败: " + err.message : "Failed to generate peritumoral ring: " + err.message);
           setShowRing(false);
        });
    } else if (!showRing) {
      setRingImageUrl(null);
    }
  }, [showRing, patient, imageMetrics, language]);

  const undoMeasurement = () => {
      setMeasurements(prev => prev.slice(0, -1));
  };

  // Zoom Handler
  const toggleFullscreen = () => {
    if (!document.fullscreenElement) {
      containerRef.current?.requestFullscreen();
    } else {
      document.exitFullscreen();
    }
  };

  // Keyboard Shortcuts
  useEffect(() => {
    const handleKeyPress = (e: KeyboardEvent) => {
      // Only handle if not typing in input
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return;
      
      switch(e.key.toLowerCase()) {
        case '1':
          setMode('original');
          break;
        case '2':
          setMode('overlay');
          break;
        case '3':
          setMode('roi');
          break;
        case '4':
          setMode('split');
          break;
        case ' ':
          e.preventDefault();
          // Toggle between original and overlay
          setMode(mode === 'original' ? 'overlay' : 'original');
          break;
        case 'm':
          setIsMeasuring(!isMeasuring);
          break;
        case 'r':
          if (e.ctrlKey || e.metaKey) {
            e.preventDefault();
            resetAdjustments();
          }
          break;
        case 'f':
          if (e.ctrlKey || e.metaKey) {
            e.preventDefault();
            toggleFullscreen();
          }
          break;
      }
    };

    window.addEventListener('keydown', handleKeyPress);
    return () => window.removeEventListener('keydown', handleKeyPress);
  }, [mode, isMeasuring]);

  const handleWheel = (e: React.WheelEvent) => {
    if (mode === 'split') return; // Disable zoom in split mode for now
    e.preventDefault();
    const delta = -e.deltaY * 0.001;
    const newScale = Math.min(Math.max(1, scale + delta), 5); // Limit zoom 1x to 5x
    setScale(newScale);
  };

  // Mouse Handlers (Pan & Measure)
  const handleMouseDown = (e: React.MouseEvent) => {
      if (mode === 'split') return;
      
      // Measurement Logic (Click & Move & Click)
    // Transform coordinates to be relative to the image
    if (isMeasuring && imageMetrics) {
      // If we are already measuring (activeMeasurement exists), this click ends it
      if (activeMeasurement) {
        const dx = activeMeasurement.end.x - activeMeasurement.start.x;
        const dy = activeMeasurement.end.y - activeMeasurement.start.y;
        // Minimum length check
        if (Math.sqrt(dx*dx + dy*dy) > 5) {
             setMeasurements([...measurements, { id: Date.now(), ...activeMeasurement }]);
        }
        setActiveMeasurement(null);
      } else {
        // Start new measurement
        // Need to calculate coordinates relative to the image content, considering offset
        // Coordinate transformation:
        // Mouse (Screen) -> Container (Rect) -> Image Content (Offset) -> Scaled Image?
        // Actually, we want to draw on the image plane.
        // Since we are putting the SVG inside the transformed container, the coordinates 
        // should be relative to the transformed container's origin (0,0).
        // However, the image has an offset within that container (due to flex center).
        
        const rect = e.currentTarget.getBoundingClientRect();
        // Mouse position relative to the container (which is transformed)
        // e.currentTarget is the div with onMouseDown
        
        // Wait, if we move SVG inside, we need event listener on the container?
        // Let's keep event listener on the wrapper div.
        
        // Correct logic:
        // 1. Get mouse pos relative to the wrapper div.
        // 2. Subtract image offset (to make it relative to image top-left).
        // 3. Store these coordinates.
        
        // Note: e.clientX is screen space. rect.left is screen space of wrapper.
        const x = e.clientX - rect.left - (imageMetrics.offsetLeft || 0);
        const y = e.clientY - rect.top - (imageMetrics.offsetTop || 0);
        
        setActiveMeasurement({ start: {x, y}, end: {x, y} });
      }
      return;
    }

    // Pan Logic
      if (scale > 1) {
        setIsDragging(true);
        setStartPos({ x: e.clientX - position.x, y: e.clientY - position.y });
      }
  };

  const handleMouseMove = (e: React.MouseEvent) => {
      if (mode === 'split') return;

      // Measurement Logic
      if (isMeasuring && activeMeasurement && imageMetrics) {
        const rect = e.currentTarget.getBoundingClientRect();
        const x = e.clientX - rect.left - (imageMetrics.offsetLeft || 0);
        const y = e.clientY - rect.top - (imageMetrics.offsetTop || 0);
        setActiveMeasurement({ ...activeMeasurement, end: {x, y} });
        return;
      }

      // Pan Logic
      if (isDragging) {
        setPosition({
            x: e.clientX - startPos.x,
            y: e.clientY - startPos.y
        });
      }
  };

  const handleMouseUp = () => {
      // For Click-Move-Click, mouse up doesn't end measurement
      // It only matters for dragging/panning
      setIsDragging(false);
  };

  // Calculate Distance (Pixels -> approx CM)
  // Assumption: 40px ~= 1cm for display purposes
  const getDistance = (p1: {x:number, y:number}, p2: {x:number, y:number}) => {
    return calculateDistanceCm(p1, p2, 40);
  }

  const detectionOverlayStyle = useMemo(() => 
    calculateDetectionOverlayStyle(annotationBbox, imageMetrics), 
    [annotationBbox, imageMetrics]
  );

  const detectionSummary = useMemo(() => {
    if (!annotationBbox) return null;
    const widthPx = Math.max(0, annotationBbox.x2 - annotationBbox.x1);
    const heightPx = Math.max(0, annotationBbox.y2 - annotationBbox.y1);
    return {
      widthCm: (widthPx / 40).toFixed(1),
      heightCm: (heightPx / 40).toFixed(1)
    };
  }, [annotationBbox]);

  if (!patient) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center text-gray-600 bg-black medical-grid">
        <div className="p-6 rounded-full bg-[#111] border border-white/5 shadow-2xl">
           <Scan size={48} className="opacity-40 text-blue-500" />
        </div>
        <span className="text-[10px] font-mono uppercase tracking-[0.3em] opacity-40 mt-4">{t.viewer.noData}</span>
      </div>
    );
  }

  const getImageUrl = (m: ViewMode) => {
    if (!patient) return '';
    switch (m) {
      case 'overlay': return patient.overlay_url;
      case 'roi': return patient.roi_url || patient.image_url;
      case 'heatmap': return patient.overlay_url;
      default: return patient.image_url;
    }
  };

  const primaryViewLabel = dataset === 'cropped' ? t.viewer.cropUi : t.viewer.bmode;

  const getModeLabel = () => {
      if (mode === 'split') return 'SPLIT COMPARISON';
      if (mode === 'multi') return `MULTI-IMAGE (${siblingImages.length})`;
      if (mode === 'video') return `VIDEO (${patient?.video_urls?.length || 0})`;
      if (mode === 'dicom') return language === 'zh' ? 'DICOM 原始帧' : 'DICOM RAW';
      if (mode === 'original') return primaryViewLabel;
      if (mode === 'overlay') return t.viewer.mask;
      if (mode === 'roi') return language === 'zh' ? '病灶 ROI' : 'LESION ROI';
      return t.viewer.heatmap;
  }
  
  // 当前图片在兄弟图片中的索引
  const currentImageIndex = patient ? siblingImages.findIndex((p) => p.id === patient.id) : -1;
  
  // 导航到上一张/下一张
  const navigateImage = (direction: 'prev' | 'next') => {
    if (!onSelectSibling || siblingImages.length <= 1) return;
    const newIndex = direction === 'prev' 
      ? (currentImageIndex - 1 + siblingImages.length) % siblingImages.length
      : (currentImageIndex + 1) % siblingImages.length;
    onSelectSibling(siblingImages[newIndex]);
  };

  const getStatusColor = () => {
      if (mode === 'original') return dataset === 'cropped' ? 'bg-amber-500 text-amber-500' : 'bg-blue-500 text-blue-500';
      if (mode === 'overlay') return 'bg-amber-500 text-amber-500';
      if (mode === 'roi') return 'bg-emerald-500 text-emerald-500';
      if (mode === 'split') return 'bg-purple-500 text-purple-500';
      if (mode === 'video') return 'bg-rose-500 text-rose-500';
      if (mode === 'dicom') return 'bg-violet-500 text-violet-500';
      return 'bg-red-500 text-red-500';
  }

  // Apply filters dynamically
  const imgStyle = {
      filter: `brightness(${brightness}%) contrast(${contrast}%)`
  };

  return (
    <div ref={containerRef} className="flex flex-col h-full w-full bg-black relative group select-none overflow-hidden medical-grid">
      
      {/* Top Overlay */}
      <div className="absolute top-0 left-0 w-full z-20 p-5 flex justify-between items-start bg-linear-to-b from-black/90 via-black/40 to-transparent pointer-events-none">
        <div className="flex flex-col gap-1">
           <div className="flex items-center gap-2.5">
              <div className={`w-2 h-2 rounded-sm shadow-[0_0_8px_currentColor] transition-colors duration-500 ${getStatusColor()}`}></div>
              <span className="text-xs font-bold text-gray-100 tracking-widest drop-shadow-md font-mono uppercase">
                {getModeLabel()}
              </span>
           </div>
           <span className="text-[10px] font-mono text-gray-400 ml-4 tracking-wide opacity-80">
             PID: {patient.id}
           </span>
        </div>
        
        <div className="flex flex-col items-end gap-1 opacity-70">
           <div className="text-[10px] font-mono text-gray-300">MI: 0.9 TIS: 0.4</div>
           <div className="text-[10px] font-mono text-gray-300">Gn: {Math.floor(brightness * 0.6)}dB</div>
           <div className="text-[10px] font-mono text-gray-300">DR: {Math.floor(contrast * 0.8)}</div>
           {detectionSummary ? (
             <div className="text-[10px] font-mono text-emerald-300">
               {t.viewer.detection_box}: {detectionSummary.widthCm}cm × {detectionSummary.heightCm}cm
             </div>
           ) : (
             <div className="text-[10px] font-mono text-gray-500">{t.viewer.detection_missing}</div>
           )}
           {zoomToROI && (
             <div className="text-[10px] font-mono text-cyan-400 animate-pulse">
               {language === 'zh' ? '🔍 ROI 放大模式' : '🔍 ROI ZOOM MODE'}
             </div>
           )}
        </div>
      </div>

      {/* Adjustment Sliders (Floating Right) */}
      <div className={`absolute right-14 top-1/2 -translate-y-1/2 z-30 flex flex-col gap-4 transition-all duration-300 ${showControls ? 'opacity-100 translate-x-0' : 'opacity-0 translate-x-4 pointer-events-none'}`}>
         <div className="bg-black/90 backdrop-blur-md border border-white/10 p-4 rounded-xl flex flex-col gap-6 shadow-2xl">
            <div className="flex flex-col gap-2 items-center group/slider">
                <span className="text-[9px] font-bold text-gray-500 uppercase tracking-wider group-hover/slider:text-blue-400 transition-colors">Brightness</span>
                <div className="h-32 w-1.5 bg-white/10 rounded-full relative cursor-pointer hover:bg-white/20 transition-colors">
                    <input 
                        type="range" min="50" max="150" 
                        value={brightness} 
                        onChange={(e) => setBrightness(Number(e.target.value))}
                        className="absolute inset-0 w-full h-full opacity-0 cursor-pointer z-10"
                        style={{ writingMode: 'vertical-lr', direction: 'rtl' }}
                    />
                    <div className="absolute bottom-0 left-0 w-full bg-blue-500 rounded-full pointer-events-none" style={{ height: `${(brightness - 50)}%` }}></div>
                    <div className="absolute left-1/2 -translate-x-1/2 w-3 h-3 bg-white rounded-full shadow-lg pointer-events-none transition-all" style={{ bottom: `calc(${(brightness - 50)}% - 6px)` }}></div>
                </div>
            </div>
            <div className="flex flex-col gap-2 items-center group/slider">
                <span className="text-[9px] font-bold text-gray-500 uppercase tracking-wider group-hover/slider:text-blue-400 transition-colors">Contrast</span>
                <div className="h-32 w-1.5 bg-white/10 rounded-full relative cursor-pointer hover:bg-white/20 transition-colors">
                    <input 
                        type="range" min="50" max="150" 
                        value={contrast} 
                        onChange={(e) => setContrast(Number(e.target.value))}
                        className="absolute inset-0 w-full h-full opacity-0 cursor-pointer z-10"
                        style={{ writingMode: 'vertical-lr', direction: 'rtl' }}
                    />
                    <div className="absolute bottom-0 left-0 w-full bg-blue-500 rounded-full pointer-events-none" style={{ height: `${(contrast - 50)}%` }}></div>
                    <div className="absolute left-1/2 -translate-x-1/2 w-3 h-3 bg-white rounded-full shadow-lg pointer-events-none transition-all" style={{ bottom: `calc(${(contrast - 50)}% - 6px)` }}></div>
                </div>
            </div>
            <button onClick={resetAdjustments} className="p-2 text-gray-500 hover:text-white bg-white/5 hover:bg-white/10 rounded-full transition-all" title="Reset">
                <RefreshCw size={12} />
            </button>
         </div>
      </div>

      {/* Main Image Area */}
      <div className="flex-1 flex items-center justify-center overflow-hidden p-4 relative z-10 bg-black">
        
        {/* Multi-Image Navigation (when multiple images exist) */}
        {siblingImages.length > 1 && mode !== 'multi' && (
          <div className="absolute bottom-20 left-1/2 -translate-x-1/2 z-30 flex items-center gap-3 bg-black/80 backdrop-blur border border-white/10 rounded-full px-4 py-2">
            <button 
              onClick={() => navigateImage('prev')}
              className="p-1 text-gray-400 hover:text-white transition-colors"
            >
              <ChevronLeft size={16} />
            </button>
            <div className="flex items-center gap-1.5">
              {siblingImages.map((img, idx) => (
                <button
                  key={img.id}
                  onClick={() => onSelectSibling?.(img)}
                  className={`w-2 h-2 rounded-full transition-all ${
                    img.id === patient?.id 
                      ? 'bg-blue-500 scale-125' 
                      : 'bg-gray-600 hover:bg-gray-400'
                  }`}
                  title={img.id_short}
                />
              ))}
            </div>
            <button 
              onClick={() => navigateImage('next')}
              className="p-1 text-gray-400 hover:text-white transition-colors"
            >
              <ChevronRight size={16} />
            </button>
            <span className="text-[10px] text-gray-500 font-mono ml-1">
              {currentImageIndex + 1}/{siblingImages.length}
            </span>
          </div>
        )}
        
        {/* Image Container */}
        {mode === 'dicom' ? (
          /* DICOM Raw Viewer Mode */
          <div className="w-full h-full">
            <DicomViewer patient={patient} language={language} />
          </div>
        ) : mode === 'video' ? (
          /* Video Mode */
          <div className="w-full h-full">
            <VideoPlayer 
              videos={patient?.video_urls || []} 
              language={language}
            />
          </div>
        ) : mode === 'multi' && siblingImages.length > 1 ? (
          /* Multi-Image Mode: Grid View */
          <div className={`grid w-full h-full gap-2 p-2 ${
            siblingImages.length <= 2 ? 'grid-cols-2' :
            siblingImages.length <= 4 ? 'grid-cols-2' :
            siblingImages.length <= 6 ? 'grid-cols-3' :
            'grid-cols-4'
          }`}>
            {siblingImages.map((img, idx) => (
              <div 
                key={img.id}
                onClick={() => onSelectSibling?.(img)}
                className={`relative flex items-center justify-center bg-[#0a0a0a] rounded-lg overflow-hidden cursor-pointer transition-all hover:ring-2 hover:ring-blue-500/50 ${
                  img.id === patient?.id ? 'ring-2 ring-blue-500' : ''
                }`}
              >
                <OptimizedImage 
                  src={img.image_url} 
                  alt={img.id_short} 
                  className="max-h-full max-w-full object-contain"
                  priority={idx < 4}
                />
                {/* Overlay if available */}
                {img.overlay_transparent_url && (
                  <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
                    <OptimizedImage 
                      src={img.overlay_transparent_url} 
                      alt="Overlay" 
                      className="max-h-full max-w-full object-contain opacity-80"
                      silentError={true}
                    />
                  </div>
                )}
                {/* Label */}
                <div className="absolute bottom-1 left-1 right-1 flex items-center justify-between">
                  <span className={`text-[8px] font-bold px-1.5 py-0.5 rounded ${
                    img.id === patient?.id 
                      ? 'bg-blue-500 text-white' 
                      : 'bg-black/60 text-gray-300'
                  }`}>
                    {img.id_short}
                  </span>
                  {idx + 1 <= siblingImages.length && (
                    <span className="text-[8px] font-mono text-gray-500 bg-black/60 px-1 rounded">
                      {idx + 1}/{siblingImages.length}
                    </span>
                  )}
                </div>
              </div>
            ))}
          </div>
        ) : mode === 'split' ? (
          /* Split Mode: Side by Side */
          <div className="grid grid-cols-2 w-full h-full gap-1">
            {/* Left: Original Image */}
            <div className="relative flex items-center justify-center bg-black">
              <OptimizedImage 
                ref={imageRef}
                onLoad={updateImageMetrics}
                src={patient.image_url} 
                alt="Source" 
                style={imgStyle}
                className="max-h-full max-w-full object-contain shadow-2xl pointer-events-none"
                priority={!!patient}
              />
              <span className="absolute bottom-2 left-2 text-[9px] font-bold text-blue-400 bg-black/40 backdrop-blur-sm px-1.5 py-0.5 rounded border border-blue-500/20">
                SOURCE
              </span>
              <div className="absolute right-0 top-1/4 bottom-1/4 w-px bg-linear-to-b from-transparent via-white/10 to-transparent"></div>
            </div>

            {/* Right: Original + Overlay */}
            <div className="relative flex items-center justify-center bg-black">
              {patient.overlay_transparent_url || patient.overlay_url ? (
                <>
                  {/* Base Image */}
                  <OptimizedImage 
                    src={patient.image_url} 
                    alt="Base" 
                    style={imgStyle}
                    className="max-h-full max-w-full object-contain shadow-2xl pointer-events-none"
                    priority={!!patient}
                  />
                  {/* Overlay */}
                  <div className="absolute inset-0 w-full h-full flex items-center justify-center pointer-events-none z-10">
                    <OptimizedImage 
                      src={patient.overlay_transparent_url || patient.overlay_url} 
                      alt="AI Segmentation" 
                      className="max-h-full max-w-full object-contain"
                      style={{ opacity: 1 }}
                      silentError={true}
                    />
                  </div>
                  {/* Peritumoral Ring */}
                  {ringImageUrl && (
                    <div className="absolute inset-0 w-full h-full flex items-center justify-center pointer-events-none z-20">
                      <OptimizedImage 
                        src={ringImageUrl} 
                        alt="Peritumoral Ring" 
                        className="max-h-full max-w-full object-contain animate-in fade-in duration-500"
                        style={{ opacity: 1 }}
                        silentError={true}
                      />
                    </div>
                  )}
                  {/* Detection Box */}
                  {showDetectionBox && detectionOverlayStyle && (
                    <div
                      className="absolute border-2 border-emerald-300 rounded-md pointer-events-none shadow-2xl"
                      style={{
                        ...detectionOverlayStyle,
                        zIndex: 30
                      }}
                    >
                      <span className="absolute top-0 right-0 text-[8px] font-mono bg-black/70 text-emerald-100 px-1 rounded-bl">
                        {t.viewer.detection_box}
                      </span>
                    </div>
                  )}
                  <span className="absolute bottom-2 left-2 text-[9px] font-bold text-emerald-400 bg-black/40 backdrop-blur-sm px-1.5 py-0.5 rounded border border-emerald-500/20 z-20">
                    AI SEGMENTATION
                  </span>
                </>
              ) : (
                <div className="flex flex-col items-center justify-center text-gray-500">
                  <Scan size={32} className="opacity-40 mb-2" />
                  <span className="text-xs">{language === 'zh' ? '分割图像不可用' : 'Segmentation image unavailable'}</span>
                </div>
              )}
            </div>
          </div>
        ) : (
          /* Normal Mode: Single Image */
          <div 
            className="flex w-full h-full items-center justify-center transition-all duration-500 gap-4"
            onWheel={handleWheel}
            onMouseDown={handleMouseDown}
            onMouseMove={handleMouseMove}
            onMouseUp={handleMouseUp}
            onMouseLeave={handleMouseUp}
            style={{
              cursor: isDragging ? 'grabbing' : (isMeasuring ? 'crosshair' : (scale > 1 ? 'grab' : 'default'))
            }}
          >
            <div
              ref={imageWrapperRef}
              className="relative"
              style={{
                transform: `scale(${scale}) translate(${position.x / scale}px, ${position.y / scale}px)`,
                transition: isDragging ? 'none' : 'transform 0.2s' 
              }}
            >
              <div className="relative">
                {mode === 'overlay' ? (
                  <>
                    <OptimizedImage 
                      ref={imageRef}
                      onLoad={updateImageMetrics}
                      src={patient.image_url} 
                      alt="Base" 
                      style={imgStyle}
                      className="max-h-full max-w-full object-contain shadow-2xl pointer-events-none"
                      priority={!!patient}
                    />
                    <div className="absolute inset-0 w-full h-full flex items-center justify-center pointer-events-none z-10">
                        <OptimizedImage 
                        src={patient.overlay_transparent_url || patient.overlay_url} 
                        alt="Overlay" 
                        className="max-h-full max-w-full object-contain"
                        style={{ opacity: 1 }}
                        silentError={true}
                        />
                    </div>
                    {/* Peritumoral Ring */}
                    {ringImageUrl && (
                        <div className="absolute inset-0 w-full h-full flex items-center justify-center pointer-events-none z-20">
                            <OptimizedImage 
                            src={ringImageUrl} 
                            alt="Peritumoral Ring" 
                            className="max-h-full max-w-full object-contain animate-in fade-in duration-500"
                            style={{ opacity: 1 }}
                            silentError={true}
                            />
                        </div>
                    )}
                  </>
                ) : (
                  <OptimizedImage 
                    ref={imageRef}
                    onLoad={updateImageMetrics}
                    src={getImageUrl(mode)} 
                    alt="View" 
                    style={mode === 'original' ? imgStyle : {}}
                    className={`max-h-full max-w-full object-contain shadow-2xl pointer-events-none
                      ${mode === 'heatmap' ? 'contrast-125 brightness-110 hue-rotate-15 saturate-150' : ''}
                    `}
                    priority={!!patient}
                  />
                )}

                {/* Measurement Overlay - Moved INSIDE the scaled container */}
                {/* Note: We need to apply offset because the SVG is now relative to the image WRAPPER (div.relative) */}
                {/* But our coordinates are relative to the IMAGE itself. */}
                {/* So we position the SVG to match the image exactly? */}
                {/* No, simpler: SVG fills the wrapper, and we add offset to coordinates. */}
                {(measurements.length > 0 || activeMeasurement) && imageMetrics && (
                    <svg 
                        className="absolute inset-0 w-full h-full pointer-events-none z-20 overflow-visible"
                        style={{
                            left: imageMetrics.offsetLeft || 0,
                            top: imageMetrics.offsetTop || 0,
                            width: imageMetrics.displayWidth,
                            height: imageMetrics.displayHeight
                        }}
                    >
                        <defs>
                            <marker id="arrow" viewBox="0 0 10 10" refX="5" refY="5" markerWidth="4" markerHeight="4" orient="auto-start-reverse">
                            <path d="M 0 0 L 10 5 L 0 10 z" fill="#fbbf24" />
                            </marker>
                        </defs>
                        
                        {/* Completed Measurements */}
                        {measurements.map(m => (
                            <g key={m.id}>
                                <line 
                                    x1={m.start.x} 
                                    y1={m.start.y} 
                                    x2={m.end.x} 
                                    y2={m.end.y} 
                                    stroke="#fbbf24" 
                                    strokeWidth="2" // Scale stroke width inversely?
                                    strokeDasharray="4 4"
                                    markerStart="url(#arrow)"
                                    markerEnd="url(#arrow)"
                                    className="drop-shadow-[0_1px_2px_rgba(0,0,0,0.8)]"
                                    vectorEffect="non-scaling-stroke"
                                />
                                {/* Endpoints */}
                                <circle cx={m.start.x} cy={m.start.y} r="3" fill="#fbbf24" className="drop-shadow-md" />
                                <circle cx={m.end.x} cy={m.end.y} r="3" fill="#fbbf24" className="drop-shadow-md" />
                                
                                <text 
                                    x={(m.start.x + m.end.x) / 2} 
                                    y={(m.start.y + m.end.y) / 2 - 10} 
                                    fill="#fbbf24" 
                                    fontSize="14" 
                                    fontFamily="monospace" 
                                    fontWeight="bold"
                                    textAnchor="middle"
                                    className="drop-shadow-[0_1px_2px_rgba(0,0,0,0.8)]"
                                >
                                    {getDistance(m.start, m.end)} cm
                                </text>
                            </g>
                        ))}

                        {/* Active Measurement */}
                        {activeMeasurement && (
                            <g>
                                <line 
                                    x1={activeMeasurement.start.x} 
                                    y1={activeMeasurement.start.y} 
                                    x2={activeMeasurement.end.x} 
                                    y2={activeMeasurement.end.y} 
                                    stroke="#fbbf24" 
                                    strokeWidth="2" 
                                    strokeDasharray="4 4"
                                    markerStart="url(#arrow)"
                                    markerEnd="url(#arrow)"
                                    className="drop-shadow-[0_1px_2px_rgba(0,0,0,0.8)] opacity-80"
                                    vectorEffect="non-scaling-stroke"
                                />
                                <circle cx={activeMeasurement.start.x} cy={activeMeasurement.start.y} r="3" fill="#fbbf24" className="animate-pulse" />
                                <circle cx={activeMeasurement.end.x} cy={activeMeasurement.end.y} r="3" fill="#fbbf24" />

                                <text 
                                    x={(activeMeasurement.start.x + activeMeasurement.end.x) / 2} 
                                    y={(activeMeasurement.start.y + activeMeasurement.end.y) / 2 - 10} 
                                    fill="#fbbf24" 
                                    fontSize="14" 
                                    fontFamily="monospace" 
                                    fontWeight="bold"
                                    textAnchor="middle"
                                    className="drop-shadow-[0_1px_2px_rgba(0,0,0,0.8)]"
                                >
                                    {getDistance(activeMeasurement.start, activeMeasurement.end)} cm
                                </text>
                            </g>
                        )}
                    </svg>
                )}
              </div>
              {showDetectionBox && detectionOverlayStyle && (
                <div
                  className="absolute border-2 border-emerald-300 rounded-md pointer-events-none shadow-2xl"
                  style={{
                    ...detectionOverlayStyle,
                    zIndex: 30
                  }}
                >
                  <span className="absolute top-0 right-0 text-[8px] font-mono bg-black/70 text-emerald-100 px-1 rounded-bl">
                    {t.viewer.detection_box}
                  </span>
                </div>
              )}
            </div>
            {scale > 1 && (
              <div className="absolute top-4 right-4 bg-black/50 px-2 py-1 rounded text-[9px] font-mono text-blue-400 border border-blue-500/30">
                {scale.toFixed(1)}x
              </div>
            )}
          </div>
        )}

        {/* Measurement Overlay REMOVED FROM HERE */}

        {/* Measurement Controls (Contextual) */}
        {isMeasuring && (
                <div className="absolute top-4 right-14 flex gap-2 z-30">
                    <button 
                        onClick={undoMeasurement}
                        disabled={measurements.length === 0}
                        className="bg-black/80 backdrop-blur border border-white/10 text-white p-2 rounded-full shadow-lg hover:bg-white/10 disabled:opacity-30 disabled:cursor-not-allowed transition-all"
                        title="Undo Last Measurement"
                    >
                        <Undo2 size={14} />
                    </button>
                    <button 
                        onClick={() => setMeasurements([])}
                        disabled={measurements.length === 0}
                        className="bg-black/80 backdrop-blur border border-white/10 text-red-400 p-2 rounded-full shadow-lg hover:bg-red-500/20 disabled:opacity-30 disabled:cursor-not-allowed transition-all"
                        title="Clear All"
                    >
                        <XCircle size={14} />
                    </button>
                </div>
        )}

        {/* Ruler Scale */}
        <div className="absolute right-4 top-20 bottom-20 w-6 border-l border-white/20 flex flex-col justify-between py-2 pointer-events-none">
          {[...Array(10)].map((_, i) => (
             <div key={i} className="w-2 border-t border-white/40 relative">
                {i % 2 === 0 && <span className="absolute right-3 -top-1.5 text-[8px] font-mono text-white/40">{i}cm</span>}
             </div>
          ))}
        </div>

      </div>

      {/* Keyboard Shortcuts Hint */}
      <div className="absolute bottom-4 left-4 z-30 bg-black/60 backdrop-blur border border-white/10 rounded-lg p-2 text-[9px] text-gray-500 font-mono opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none">
        <div className="space-y-0.5">
          <div><kbd className="px-1 py-0.5 bg-white/10 rounded">1-4</kbd> Views</div>
          <div><kbd className="px-1 py-0.5 bg-white/10 rounded">Space</kbd> Toggle</div>
          <div><kbd className="px-1 py-0.5 bg-white/10 rounded">M</kbd> Measure</div>
        </div>
      </div>

      {/* Toolbar - Compact Design */}
      <div className="absolute top-3 left-1/2 -translate-x-1/2 z-30 transition-opacity duration-300 opacity-0 group-hover:opacity-100">
        <div className="flex items-center gap-1.5">
          
          {/* View Mode Group */}
          <div className="bg-black/70 backdrop-blur-md border border-white/10 rounded-lg px-1 py-0.5 flex items-center gap-0.5">
          <button
            onClick={() => setMode('original')}
              className={`p-1.5 rounded-md transition-all ${
                mode === 'original' ? 'bg-white/20 text-white' : 'text-gray-500 hover:text-white hover:bg-white/10'
            }`}
              title={primaryViewLabel}
          >
              <Eye size={14} />
          </button>
          <button
            onClick={() => setMode('overlay')}
              className={`p-1.5 rounded-md transition-all ${
                mode === 'overlay' ? 'bg-amber-500/30 text-amber-400' : 'text-gray-500 hover:text-white hover:bg-white/10'
            }`}
              title={t.viewer.seg}
          >
              <Layers size={14} />
          </button>
          <button
            onClick={() => setMode('roi')}
              disabled={!patient.roi_url}
              className={`p-1.5 rounded-md transition-all ${
                !patient.roi_url
                  ? 'opacity-30 cursor-not-allowed text-gray-600'
                  : mode === 'roi'
                    ? 'bg-emerald-500/30 text-emerald-400'
                    : 'text-gray-500 hover:text-white hover:bg-white/10'
            }`}
              title={language === 'zh' ? '病灶 ROI' : 'Lesion ROI'}
          >
              <Scan size={14} />
          </button>
            <button
              onClick={() => setMode('split')}
              className={`p-1.5 rounded-md transition-all ${
                mode === 'split' ? 'bg-purple-500/30 text-purple-400' : 'text-gray-500 hover:text-white hover:bg-white/10'
              }`}
              title={t.viewer.contrast}
            >
              <Columns size={14} />
            </button>
            {siblingImages.length > 1 && (
              <button
                onClick={() => setMode(mode === 'multi' ? 'original' : 'multi')}
                className={`p-1.5 rounded-md transition-all relative ${
                  mode === 'multi' ? 'bg-blue-500/30 text-blue-400' : 'text-gray-500 hover:text-white hover:bg-white/10'
                }`}
                title={language === 'zh' ? `${siblingImages.length} 张图片` : `${siblingImages.length} images`}
              >
                <Grid2X2 size={14} />
                <span className="absolute -top-1 -right-1 text-[8px] bg-blue-500 text-white rounded-full w-3.5 h-3.5 flex items-center justify-center font-bold">
                  {siblingImages.length}
                </span>
              </button>
            )}
            {patient?.video_urls && patient.video_urls.length > 0 && (
              <button
                onClick={() => setMode(mode === 'video' ? 'original' : 'video')}
                className={`p-1.5 rounded-md transition-all relative ${
                  mode === 'video' ? 'bg-rose-500/30 text-rose-400' : 'text-gray-500 hover:text-white hover:bg-white/10'
                }`}
                title={language === 'zh' ? `${patient.video_urls.length} 个视频` : `${patient.video_urls.length} videos`}
              >
                <Video size={14} />
                <span className="absolute -top-1 -right-1 text-[8px] bg-rose-500 text-white rounded-full w-3.5 h-3.5 flex items-center justify-center font-bold">
                  {patient.video_urls.length}
                </span>
              </button>
            )}
            <button
              onClick={() => setMode('dicom')}
              className={`p-2 rounded-xl transition-all relative group/btn ${
                mode === 'dicom'
                ? 'text-violet-400'
                : 'text-gray-500 hover:text-gray-300'
              }`}
              title={language === 'zh' ? 'DICOM 原始帧查看' : 'DICOM Raw Viewer'}
            >
              <div className={`absolute inset-0 bg-violet-500/10 rounded-xl blur-md transition-opacity duration-500 ${mode === 'dicom' ? 'opacity-100' : 'opacity-0'}`}></div>
              <FileStack size={16} className="relative z-10" />
            </button>
          </div>

          {/* Overlay & ROI Group */}
          <div className="bg-black/70 backdrop-blur-md border border-white/10 rounded-lg px-1 py-0.5 flex items-center gap-0.5">
          <button
            onClick={() => annotationBbox && setShowDetectionBox(prev => !prev)}
            disabled={!annotationBbox}
              className={`p-1.5 rounded-md transition-all ${
                !annotationBbox ? 'opacity-30 cursor-not-allowed text-gray-600' :
                showDetectionBox ? 'bg-emerald-500/30 text-emerald-400' : 'text-gray-500 hover:text-white hover:bg-white/10'
              }`}
              title={t.viewer.detect}
          >
              <Scan size={14} />
          </button>
          <button
              onClick={() => setShowRing(prev => !prev)}
              disabled={!patient.json_url}
              className={`p-1.5 rounded-md transition-all ${
                !patient.json_url ? 'opacity-30 cursor-not-allowed text-gray-600' :
                showRing ? 'bg-orange-500/30 text-orange-400' : 'text-gray-500 hover:text-white hover:bg-white/10'
            }`}
              title={language === 'zh' ? '瘤周环' : 'Peritumoral'}
          >
              <CircleDashed size={14} />
          </button>
          <button
              onClick={toggleZoomToROI}
              disabled={!annotationBbox}
              className={`p-1.5 rounded-md transition-all ${
                !annotationBbox ? 'opacity-30 cursor-not-allowed text-gray-600' :
                zoomToROI ? 'bg-cyan-500/30 text-cyan-400' : 'text-gray-500 hover:text-white hover:bg-white/10'
            }`}
              title="ROI Zoom"
            >
              {zoomToROI ? <Minimize2 size={14} /> : <ZoomIn size={14} />}
          </button>
          </div>

          {/* Tools Group */}
          <div className="bg-black/70 backdrop-blur-md border border-white/10 rounded-lg px-1 py-0.5 flex items-center gap-0.5">
            <button 
              onClick={() => setIsMeasuring(!isMeasuring)}
              className={`p-1.5 rounded-md transition-all ${
                isMeasuring ? 'bg-amber-500/30 text-amber-400' : 'text-gray-500 hover:text-white hover:bg-white/10'
              }`}
              title={language === 'zh' ? '测量' : 'Measure'}
            >
              <Ruler size={14} />
            </button>
          <button 
            onClick={() => setShowControls(!showControls)}
              className={`p-1.5 rounded-md transition-all ${
                showControls ? 'bg-blue-500/30 text-blue-400' : 'text-gray-500 hover:text-white hover:bg-white/10'
              }`}
              title={language === 'zh' ? '调节' : 'Adjust'}
          >
             <Settings2 size={14} />
          </button>
          </div>
          
          {/* Analysis Button - Highlighted */}
          <button 
            onClick={() => setShowExplainableAnalysis(true)}
            disabled={!patient.json_url}
            className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-all flex items-center gap-1.5 ${
              patient.json_url
                ? 'bg-emerald-500 text-white hover:bg-emerald-400 shadow-lg shadow-emerald-500/20'
                : 'bg-gray-800 text-gray-600 cursor-not-allowed'
            }`}
          >
            <Brain size={14} />
            <span>{language === 'zh' ? '分析' : 'AI'}</span>
          </button>

          {/* Fullscreen */}
          <button 
            onClick={toggleFullscreen}
            className="p-1.5 bg-black/70 backdrop-blur-md border border-white/10 rounded-lg text-gray-500 hover:text-white hover:bg-white/10 transition-all"
            title={language === 'zh' ? '全屏' : 'Fullscreen'}
          >
             <Maximize2 size={14} />
          </button>
        </div>
      </div>

      {/* Explainable Analysis Modal */}
      <ExplainableAnalysis
        patient={patient}
        isOpen={showExplainableAnalysis}
        onClose={() => setShowExplainableAnalysis(false)}
      />
    </div>
  );
};
