"use client";

import React, {
  useState, useEffect, useRef, useCallback, useMemo,
} from "react";
import type {
  DirectionBatchItem, GridCellAnnotation, BreachPolygon,
  VisibleLayers, BreachConfidence, DirectionAnnotationPayload,
} from "@/lib/direction-annotation/directionAnnotationTypes";
import {
  encodeDatasetPath,
  parseLesionMaskFromLabelMe,
  resolveMaskBbox,
} from "@/lib/direction-annotation/labelme-utils";

const GRID_ROWS = 3;
const GRID_COLS = 3;
const ROI_PAD = 60;
const PAGE_SIZE = 200;
const PATCH_SIZE = 130;

const VISIBLE_LAYERS_OPTIONS: { value: VisibleLayers; label: string }[] = [
  { value: 0, label: "0 (全穿透)" },
  { value: 1, label: "1 层" },
  { value: 2, label: "2 层" },
  { value: "3+", label: "3+ 层" },
  { value: "uncertain", label: "不确定" },
];

const CONFIDENCE_OPTIONS: { value: BreachConfidence; label: string }[] = [
  { value: "high", label: "高" },
  { value: "medium", label: "中" },
  { value: "low", label: "低" },
];

type TabId = "overlay" | "grid" | "draw";
type StageFilter = "all" | "T1" | "T2" | "T3" | "T4a" | "T4b";

function defaultCell(row: number, col: number): GridCellAnnotation {
  return { row, col, has_breach: false, visible_layers: "uncertain", breach_confidence: "medium" };
}
function initGrid(): GridCellAnnotation[] {
  const cells: GridCellAnnotation[] = [];
  for (let r = 0; r < GRID_ROWS; r++)
    for (let c = 0; c < GRID_COLS; c++) cells.push(defaultCell(r, c));
  return cells;
}
function computeROI(bbox: [number, number, number, number], imgW: number, imgH: number) {
  const [bx0, by0, bx1, by1] = bbox;
  return {
    rx0: Math.max(0, bx0 - ROI_PAD), ry0: Math.max(0, by0 - ROI_PAD),
    rx1: Math.min(imgW, bx1 + ROI_PAD), ry1: Math.min(imgH, by1 + ROI_PAD),
    rw: Math.min(imgW, bx1 + ROI_PAD) - Math.max(0, bx0 - ROI_PAD),
    rh: Math.min(imgH, by1 + ROI_PAD) - Math.max(0, by0 - ROI_PAD),
  };
}

const stageColor: Record<string, string> = {
  T1: "text-sky-400", T2: "text-amber-400", T3: "text-red-400",
  "T4a": "text-rose-500", "T4b": "text-fuchsia-500",
};
const stageBg: Record<string, string> = {
  T1: "bg-sky-600", T2: "bg-amber-600", T3: "bg-red-600",
  "T4a": "bg-rose-600", "T4b": "bg-fuchsia-600",
};

export default function AnnotatePage() {
  const [items, setItems] = useState<DirectionBatchItem[]>([]);
  const [patientGroups, setPatientGroups] = useState<Record<string, number[]>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [currentIdx, setCurrentIdx] = useState(0);
  const [filter, setFilter] = useState<StageFilter>("all");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [pagination, setPagination] = useState({ page: 1, totalPages: 1, totalFiltered: 0, totalAll: 0 });
  const [stageCounts, setStageCounts] = useState<Record<string, number>>({});
  const [annotatedCount, setAnnotatedCount] = useState(0);

  const [activeTab, setActiveTab] = useState<TabId>("overlay");
  const [gridCells, setGridCells] = useState<GridCellAnnotation[]>(initGrid);
  const [breachPolygons, setBreachPolygons] = useState<BreachPolygon[]>([]);
  const [drawingPoints, setDrawingPoints] = useState<[number, number][]>([]);
  const [note, setNote] = useState("");
  const [saving, setSaving] = useState(false);
  const [saveMsg, setSaveMsg] = useState<string | null>(null);

  const [maskPolygon, setMaskPolygon] = useState<number[][] | null>(null);
  const [maskBbox, setMaskBbox] = useState<[number, number, number, number] | null>(null);
  const [imgLoaded, setImgLoaded] = useState(false);
  const imgRef = useRef<HTMLImageElement | null>(null);

  const canvasRef = useRef<HTMLCanvasElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [hoveredCell, setHoveredCell] = useState<number | null>(null);

  const [zoomLevel, setZoomLevel] = useState(1);
  const [panOffset, setPanOffset] = useState<[number, number]>([0, 0]);
  const isPanning = useRef(false);
  const lastPanPos = useRef<[number, number]>([0, 0]);

  const [showHelp, setShowHelp] = useState(false);

  const currentItem = items[currentIdx] ?? null;
  const effectiveMaskBbox = maskBbox || resolveMaskBbox(currentItem);
  const hasMask = Boolean(effectiveMaskBbox);

  const siblingIndices: number[] = useMemo(() => {
    if (!currentItem) return [];
    return patientGroups[currentItem.patient_id] ?? [];
  }, [currentItem, patientGroups]);

  const fetchBatch = useCallback(async (p: number, f: StageFilter, s: string) => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams({ page: String(p), pageSize: String(PAGE_SIZE), filter: f, search: s });
      const res = await fetch(`/api/direction-annotation/batch?${params}`);
      const data = await res.json();
      if (data.success) {
        setItems(data.items);
        setPatientGroups(data.patient_groups || {});
        setPagination(data.pagination);
        setStageCounts(data.stage_counts || {});
        setAnnotatedCount(data.annotated_count || 0);
        setCurrentIdx(0);
      } else {
        setError(data.error || "加载失败");
      }
    } catch (e) { setError(String(e)); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { fetchBatch(page, filter, search); }, [page, filter, fetchBatch]);

  const searchTimeout = useRef<NodeJS.Timeout>(undefined);
  const handleSearchChange = (val: string) => {
    setSearch(val);
    clearTimeout(searchTimeout.current);
    searchTimeout.current = setTimeout(() => { setPage(1); fetchBatch(1, filter, val); }, 400);
  };

  useEffect(() => {
    if (!currentItem) return;
    setImgLoaded(false);
    setMaskPolygon(null);
    setMaskBbox(null);
    setZoomLevel(1);
    setPanOffset([0, 0]);

    const img = new Image();
    img.crossOrigin = "anonymous";
    img.src = `/api/direction-annotation/image/${encodeDatasetPath(currentItem.image_path)}`;
    img.onload = () => { imgRef.current = img; setImgLoaded(true); };
    img.onerror = () => { imgRef.current = null; setImgLoaded(true); };

    if (currentItem.annotation_path) {
      fetch(`/api/direction-annotation/annotation/${encodeDatasetPath(currentItem.annotation_path)}`)
        .then((r) => { if (r.ok) return r.json(); throw new Error("not found"); })
        .then((data) => {
          const parsed = parseLesionMaskFromLabelMe(data);
          if (parsed) {
            setMaskPolygon(parsed.points);
            setMaskBbox(parsed.bbox);
          }
        })
        .catch(() => {});
    }

    setGridCells(initGrid());
    setBreachPolygons([]);
    setDrawingPoints([]);
    setNote("");
    setSaveMsg(null);
  }, [currentItem?.image_path]);

  const getCanvasTransform = useCallback(() => {
    const canvas = canvasRef.current;
    const img = imgRef.current;
    if (!canvas || !img || !currentItem) return null;

    if (activeTab === "overlay") {
      const baseScale = Math.min(canvas.width / img.width, canvas.height / img.height);
      const scale = baseScale * zoomLevel;
      const dx = (canvas.width - img.width * scale) / 2 + panOffset[0];
      const dy = (canvas.height - img.height * scale) / 2 + panOffset[1];
      return { srcX: 0, srcY: 0, srcW: img.width, srcH: img.height, dx, dy, scale };
    }

    if (!hasMask) {
      const scale = Math.min(canvas.width / img.width, canvas.height / img.height);
      const dx = (canvas.width - img.width * scale) / 2;
      const dy = (canvas.height - img.height * scale) / 2;
      return { srcX: 0, srcY: 0, srcW: img.width, srcH: img.height, dx, dy, scale };
    }

    const roi = computeROI(effectiveMaskBbox!, img.width, img.height);
    const scale = Math.min(canvas.width / roi.rw, canvas.height / roi.rh);
    const dx = (canvas.width - roi.rw * scale) / 2;
    const dy = (canvas.height - roi.rh * scale) / 2;
    return { srcX: roi.rx0, srcY: roi.ry0, srcW: roi.rw, srcH: roi.rh, dx, dy, scale };
  }, [currentItem, imgLoaded, activeTab, hasMask, effectiveMaskBbox, zoomLevel, panOffset]);

  const drawCanvas = useCallback(() => {
    const canvas = canvasRef.current;
    const img = imgRef.current;
    if (!canvas || !img || !currentItem) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    const t = getCanvasTransform();
    if (!t) return;

    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.fillStyle = "#0a0a0a";
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.drawImage(img, t.srcX, t.srcY, t.srcW, t.srcH, t.dx, t.dy, t.srcW * t.scale, t.srcH * t.scale);

    const toCanvas = (x: number, y: number): [number, number] => [
      t.dx + (x - t.srcX) * t.scale, t.dy + (y - t.srcY) * t.scale,
    ];

    if (maskPolygon && maskPolygon.length > 2) {
      ctx.beginPath();
      const [sx, sy] = toCanvas(maskPolygon[0][0], maskPolygon[0][1]);
      ctx.moveTo(sx, sy);
      for (let i = 1; i < maskPolygon.length; i++) {
        const [px, py] = toCanvas(maskPolygon[i][0], maskPolygon[i][1]);
        ctx.lineTo(px, py);
      }
      ctx.closePath();
      if (activeTab === "overlay") { ctx.fillStyle = "rgba(34,197,94,0.18)"; ctx.fill(); }
      ctx.strokeStyle = "#22c55e"; ctx.lineWidth = 2.5; ctx.stroke();
    }

    if (activeTab === "grid" && hasMask) {
      const [bx0, by0, bx1, by1] = effectiveMaskBbox!;
      const cellW = ((bx1 - bx0) * t.scale) / GRID_COLS;
      const cellH = ((by1 - by0) * t.scale) / GRID_ROWS;
      const [gx0, gy0] = toCanvas(bx0, by0);

      for (let r = 0; r < GRID_ROWS; r++) {
        for (let c = 0; c < GRID_COLS; c++) {
          const idx = r * GRID_COLS + c;
          const cx = gx0 + c * cellW;
          const cy = gy0 + r * cellH;
          const cell = gridCells[idx];

          ctx.fillStyle = idx === hoveredCell
            ? "rgba(100,180,255,0.25)"
            : cell.has_breach ? "rgba(239,68,68,0.35)" : "rgba(100,100,100,0.08)";
          ctx.fillRect(cx, cy, cellW, cellH);
          ctx.setLineDash([4, 3]);
          ctx.strokeStyle = "rgba(255,255,255,0.35)"; ctx.lineWidth = 1;
          ctx.strokeRect(cx, cy, cellW, cellH);
          ctx.setLineDash([]);

          ctx.fillStyle = cell.has_breach ? "#fbbf24" : "rgba(255,255,255,0.45)";
          ctx.font = "bold 16px system-ui"; ctx.textAlign = "center"; ctx.textBaseline = "middle";
          ctx.fillText(`${idx + 1}`, cx + cellW / 2, cy + cellH / 2);

          if (cell.has_breach) {
            ctx.fillStyle = "rgba(239,68,68,0.12)";
            ctx.fillRect(cx + 1, cy + 1, cellW - 2, cellH - 2);
          }
        }
      }
    }

    if (activeTab === "draw" || activeTab === "grid") {
      for (const bp of breachPolygons) {
        if (bp.points.length < 2) continue;
        ctx.beginPath();
        const [sx, sy] = toCanvas(bp.points[0][0], bp.points[0][1]);
        ctx.moveTo(sx, sy);
        for (let i = 1; i < bp.points.length; i++) {
          const [px, py] = toCanvas(bp.points[i][0], bp.points[i][1]);
          ctx.lineTo(px, py);
        }
        ctx.closePath();
        ctx.fillStyle = "rgba(251,146,60,0.3)"; ctx.fill();
        ctx.strokeStyle = "#fb923c"; ctx.lineWidth = 2; ctx.stroke();
      }
    }

    if (activeTab === "draw" && drawingPoints.length > 0) {
      ctx.beginPath();
      const [sx, sy] = toCanvas(drawingPoints[0][0], drawingPoints[0][1]);
      ctx.moveTo(sx, sy);
      for (let i = 1; i < drawingPoints.length; i++) {
        const [px, py] = toCanvas(drawingPoints[i][0], drawingPoints[i][1]);
        ctx.lineTo(px, py);
      }
      ctx.strokeStyle = "#f97316"; ctx.lineWidth = 2;
      ctx.setLineDash([6, 3]); ctx.stroke(); ctx.setLineDash([]);
      for (const pt of drawingPoints) {
        const [px, py] = toCanvas(pt[0], pt[1]);
        ctx.beginPath(); ctx.arc(px, py, 4, 0, 2 * Math.PI);
        ctx.fillStyle = "#f97316"; ctx.fill();
        ctx.strokeStyle = "#fff"; ctx.lineWidth = 1; ctx.stroke();
      }
    }

    if (!hasMask && activeTab !== "overlay") {
      ctx.fillStyle = "rgba(0,0,0,0.65)";
      ctx.fillRect(0, 0, canvas.width, 40);
      ctx.fillStyle = "#fbbf24"; ctx.font = "bold 14px system-ui";
      ctx.textAlign = "center"; ctx.textBaseline = "middle";
      ctx.fillText("此图片无 Mask 标注，仅显示原图", canvas.width / 2, 20);
    }

    if (activeTab === "overlay" && hasMask) {
      const [bx0, by0, bx1, by1] = effectiveMaskBbox!;
      const [cx0, cy0] = toCanvas(bx0, by0);
      const [cx1, cy1] = toCanvas(bx1, by1);
      ctx.setLineDash([6, 4]);
      ctx.strokeStyle = "rgba(59,130,246,0.45)"; ctx.lineWidth = 1.5;
      ctx.strokeRect(cx0, cy0, cx1 - cx0, cy1 - cy0);
      ctx.setLineDash([]);
    }
  }, [currentItem, maskPolygon, gridCells, hoveredCell, imgLoaded, activeTab, breachPolygons, drawingPoints, hasMask, zoomLevel, panOffset]);

  useEffect(() => { drawCanvas(); }, [drawCanvas]);

  useEffect(() => {
    const resize = () => {
      if (canvasRef.current && containerRef.current) {
        const rect = containerRef.current.getBoundingClientRect();
        canvasRef.current.width = rect.width;
        canvasRef.current.height = rect.height;
        drawCanvas();
      }
    };
    resize();
    window.addEventListener("resize", resize);
    return () => window.removeEventListener("resize", resize);
  }, [drawCanvas]);

  const canvasToImage = useCallback((e: React.MouseEvent<HTMLCanvasElement>): [number, number] | null => {
    const canvas = canvasRef.current;
    if (!canvas) return null;
    const t = getCanvasTransform();
    if (!t) return null;
    const rect = canvas.getBoundingClientRect();
    const mx = e.clientX - rect.left;
    const my = e.clientY - rect.top;
    return [t.srcX + (mx - t.dx) / t.scale, t.srcY + (my - t.dy) / t.scale];
  }, [getCanvasTransform]);

  const getGridCell = useCallback((e: React.MouseEvent<HTMLCanvasElement>): number | null => {
    if (!currentItem || !hasMask) return null;
    const pt = canvasToImage(e);
    if (!pt) return null;
    const [ix, iy] = pt;
    const [bx0, by0, bx1, by1] = effectiveMaskBbox!;
    if (ix < bx0 || ix > bx1 || iy < by0 || iy > by1) return null;
    const col = Math.min(GRID_COLS - 1, Math.floor(((ix - bx0) / (bx1 - bx0)) * GRID_COLS));
    const row = Math.min(GRID_ROWS - 1, Math.floor(((iy - by0) / (by1 - by0)) * GRID_ROWS));
    return row * GRID_COLS + col;
  }, [currentItem, hasMask, canvasToImage]);

  const handleCanvasMouseDown = useCallback((e: React.MouseEvent<HTMLCanvasElement>) => {
    if (activeTab === "overlay" && e.button === 0) {
      isPanning.current = true;
      lastPanPos.current = [e.clientX, e.clientY];
    }
  }, [activeTab]);

  const handleCanvasMouseMove = useCallback((e: React.MouseEvent<HTMLCanvasElement>) => {
    if (isPanning.current && activeTab === "overlay") {
      const dx = e.clientX - lastPanPos.current[0];
      const dy = e.clientY - lastPanPos.current[1];
      lastPanPos.current = [e.clientX, e.clientY];
      setPanOffset(prev => [prev[0] + dx, prev[1] + dy]);
      return;
    }
    if (activeTab === "grid") setHoveredCell(getGridCell(e));
  }, [activeTab, getGridCell]);

  const handleCanvasMouseUp = useCallback(() => { isPanning.current = false; }, []);

  const handleCanvasClick = useCallback((e: React.MouseEvent<HTMLCanvasElement>) => {
    if (activeTab === "grid") {
      const idx = getGridCell(e);
      if (idx === null) return;
      setGridCells(prev => { const n = [...prev]; n[idx] = { ...n[idx], has_breach: !n[idx].has_breach }; return n; });
    } else if (activeTab === "draw") {
      const pt = canvasToImage(e);
      if (pt) setDrawingPoints(prev => [...prev, pt]);
    }
  }, [activeTab, getGridCell, canvasToImage]);

  const handleCanvasDoubleClick = useCallback(() => {
    if (activeTab === "draw" && drawingPoints.length >= 3) {
      setBreachPolygons(prev => [...prev, { points: drawingPoints, label: `breach_${prev.length + 1}` }]);
      setDrawingPoints([]);
    }
  }, [activeTab, drawingPoints]);

  const handleWheel = useCallback((e: React.WheelEvent<HTMLCanvasElement>) => {
    if (activeTab === "overlay") {
      e.preventDefault();
      setZoomLevel(prev => Math.max(0.2, Math.min(10, prev * (e.deltaY > 0 ? 0.9 : 1.1))));
    }
  }, [activeTab]);

  const handleSave = useCallback(async () => {
    if (!currentItem || saving) return;
    setSaving(true);
    setSaveMsg(null);
    const payload: DirectionAnnotationPayload = {
      image_path: currentItem.image_path,
      patient_id: currentItem.patient_id,
      T_stage: currentItem.T_stage,
      grid_mode: "3x3",
      grid_cells: gridCells.filter(c => c.has_breach),
      breach_polygons: breachPolygons,
      mask_centroid: currentItem.mask_centroid || [0, 0],
      mask_bbox: effectiveMaskBbox || [0, 0, 0, 0],
      note,
      timestamp: new Date().toISOString(),
    };
    try {
      const res = await fetch("/api/direction-annotation/save", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await res.json();
      if (data.success) {
        setSaveMsg("已保存 ✓");
        setItems(prev => {
          const n = [...prev];
          const it = n.find(i => i.image_path === currentItem.image_path);
          if (it) it.is_annotated = true;
          return n;
        });
        setAnnotatedCount(prev => prev + 1);
        setTimeout(() => { if (currentIdx < items.length - 1) setCurrentIdx(p => p + 1); }, 500);
      } else { setSaveMsg(`失败: ${data.error}`); }
    } catch (err) { setSaveMsg(`错误: ${String(err)}`); }
    finally { setSaving(false); }
  }, [currentItem, saving, gridCells, breachPolygons, note, currentIdx, items.length]);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLTextAreaElement || e.target instanceof HTMLInputElement) return;

      if (e.key >= "1" && e.key <= "9" && !e.ctrlKey && !e.metaKey && activeTab === "grid" && hasMask) {
        const idx = parseInt(e.key) - 1;
        if (idx < GRID_ROWS * GRID_COLS) {
          setGridCells(prev => { const n = [...prev]; n[idx] = { ...n[idx], has_breach: !n[idx].has_breach }; return n; });
        }
        e.preventDefault();
      }
      if (e.key === "ArrowRight" || e.key === "ArrowDown") { setCurrentIdx(p => Math.min(p + 1, items.length - 1)); e.preventDefault(); }
      if (e.key === "ArrowLeft" || e.key === "ArrowUp") { setCurrentIdx(p => Math.max(p - 1, 0)); e.preventDefault(); }
      if (e.ctrlKey && e.key === "z") {
        e.preventDefault();
        if (drawingPoints.length > 0) setDrawingPoints(p => p.slice(0, -1));
        else if (breachPolygons.length > 0) setBreachPolygons(p => p.slice(0, -1));
      }
      if ((e.ctrlKey && e.key === "s") || e.key === "Enter") { e.preventDefault(); handleSave(); }
      if (e.key === "q") setActiveTab("overlay");
      if (e.key === "w") setActiveTab("grid");
      if (e.key === "e") setActiveTab("draw");
      if (e.key === "r" && activeTab === "overlay") { setZoomLevel(1); setPanOffset([0, 0]); }
      if (e.key === "?" || (e.key === "h" && !e.ctrlKey)) setShowHelp(v => !v);
      if (e.key === "Escape") setShowHelp(false);
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [items.length, activeTab, drawingPoints, breachPolygons, hasMask, handleSave]);

  const patchCanvasRefs = useRef<(HTMLCanvasElement | null)[]>(Array(9).fill(null));
  const drawPatchPreviews = useCallback(() => {
    const img = imgRef.current;
    if (!img || !currentItem || !imgLoaded || !hasMask) return;
    const [bx0, by0, bx1, by1] = effectiveMaskBbox!;
    const cellW = (bx1 - bx0) / GRID_COLS;
    const cellH = (by1 - by0) / GRID_ROWS;
    for (let r = 0; r < GRID_ROWS; r++) {
      for (let c = 0; c < GRID_COLS; c++) {
        const idx = r * GRID_COLS + c;
        const pc = patchCanvasRefs.current[idx];
        if (!pc) continue;
        const pctx = pc.getContext("2d");
        if (!pctx) continue;
        pc.width = PATCH_SIZE;
        pc.height = PATCH_SIZE;
        pctx.drawImage(img, bx0 + c * cellW, by0 + r * cellH, cellW, cellH, 0, 0, PATCH_SIZE, PATCH_SIZE);
      }
    }
  }, [currentItem, imgLoaded, hasMask]);
  useEffect(() => { drawPatchPreviews(); }, [drawPatchPreviews]);

  const showGallery = siblingIndices.length > 1;
  const breachCount = gridCells.filter(c => c.has_breach).length;

  const progressPct = pagination.totalFiltered > 0
    ? Math.round((annotatedCount / pagination.totalFiltered) * 100) : 0;

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center h-screen gap-4">
        <div className="text-red-400 text-lg">错误: {error}</div>
        <a href="/annotate/setup" className="text-blue-400 underline mt-4">返回设置页面</a>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-screen overflow-hidden select-none" style={{ background: "#010409" }}>
      {/* ─── Top bar ─── */}
      <header className="flex items-center justify-between px-3 py-1.5 border-b border-gray-800 bg-[#0d1117] shrink-0">
        <div className="flex items-center gap-3">
          <a href="/" className="text-gray-500 hover:text-white text-xs transition-colors" title="返回工作站">←</a>
          <a href="/annotate/setup" className="text-gray-500 hover:text-white text-xs transition-colors" title="数据设置">⚙</a>
          <h1 className="text-sm font-semibold tracking-tight">突破方向标注</h1>
          {currentItem && (
            <span className={`text-xs font-bold px-1.5 py-0.5 rounded ${stageBg[currentItem.T_stage] || "bg-gray-600"}`}>
              {currentItem.T_stage}
            </span>
          )}
          <span className="text-[10px] text-gray-500 font-mono">
            {pagination.totalFiltered > 0 && `${(page - 1) * PAGE_SIZE + currentIdx + 1} / ${pagination.totalFiltered}`}
          </span>

          {/* Progress indicator */}
          <div className="flex items-center gap-1.5">
            <div className="w-16 h-1.5 bg-gray-800 rounded-full overflow-hidden">
              <div className="h-full bg-green-500 transition-all duration-300 rounded-full" style={{ width: `${progressPct}%` }} />
            </div>
            <span className="text-[10px] text-green-500 font-mono">{annotatedCount}/{pagination.totalFiltered}</span>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {/* Tabs */}
          <div className="flex gap-0.5 text-[11px]">
            {([["overlay", "完整图 Q"], ["grid", "3×3 网格 W"], ["draw", "绘制 E"]] as [TabId, string][]).map(([id, label]) => (
              <button key={id} onClick={() => setActiveTab(id)}
                className={`px-3 py-1.5 rounded-md font-medium transition-colors ${activeTab === id ? "bg-blue-600 text-white shadow-sm shadow-blue-500/20" : "bg-gray-800 text-gray-400 hover:bg-gray-700 hover:text-gray-300"}`}>
                {label}
              </button>
            ))}
          </div>
          <div className="w-px h-4 bg-gray-700" />
          {/* T-stage filter */}
          <div className="flex gap-0.5 text-[11px]">
            {(["all", "T1", "T2", "T3", "T4a", "T4b"] as StageFilter[]).map(f => (
              <button key={f} onClick={() => { setFilter(f); setPage(1); setCurrentIdx(0); }}
                className={`px-1.5 py-1 rounded transition-colors ${filter === f ? (f === "all" ? "bg-emerald-700 text-white" : `${stageBg[f] || "bg-gray-600"} text-white`) : "bg-gray-800 text-gray-500 hover:bg-gray-700"}`}>
                {f === "all" ? "全部" : f}{f !== "all" && stageCounts[f] ? ` (${stageCounts[f]})` : ""}
              </button>
            ))}
          </div>
          <div className="w-px h-4 bg-gray-700" />
          <input type="text" placeholder="搜索 ID..." value={search} onChange={e => handleSearchChange(e.target.value)}
            className="w-28 bg-gray-800 border border-gray-700 rounded px-2 py-1 text-[11px] text-white placeholder-gray-600 focus:outline-none focus:border-blue-500" />
          <button onClick={() => setShowHelp(v => !v)} className="text-gray-500 hover:text-white text-xs transition-colors" title="帮助 (H)">?</button>
        </div>
      </header>

      {/* ─── Main area ─── */}
      <div className="flex flex-1 min-h-0">
        {/* Left gallery */}
        {showGallery && (
          <div className="w-[100px] border-r border-gray-800 bg-[#0d1117] overflow-y-auto shrink-0 p-1 space-y-1">
            <div className="text-[8px] text-gray-500 font-semibold uppercase tracking-wider mb-0.5 px-0.5">同一病人</div>
            {siblingIndices.map(idx => {
              const it = items[idx]; if (!it) return null;
              const isCurrent = idx === currentIdx;
              return (
                <button key={idx} onClick={() => setCurrentIdx(idx)}
                  className={`w-full rounded overflow-hidden border-2 transition-colors ${isCurrent ? "border-blue-500" : it.is_annotated ? "border-green-800" : "border-transparent hover:border-gray-600"}`}>
                  <img src={`/api/direction-annotation/image/${encodeDatasetPath(it.image_path)}`} alt="" className="w-full h-auto" loading="lazy" />
                  <div className={`text-[7px] px-0.5 py-0.5 truncate ${isCurrent ? "bg-blue-900/50 text-blue-200" : "bg-gray-900 text-gray-500"}`}>
                    {it.image_path.split("/").pop()?.replace(/\.[^.]+$/, "")}
                  </div>
                </button>
              );
            })}
          </div>
        )}

        {/* Center canvas */}
        <div ref={containerRef} className="relative flex-1 min-w-0">
          <canvas ref={canvasRef}
            className={`absolute inset-0 ${activeTab === "draw" ? "cursor-crosshair" : activeTab === "grid" ? "cursor-pointer" : "cursor-grab active:cursor-grabbing"}`}
            onMouseDown={handleCanvasMouseDown} onMouseMove={handleCanvasMouseMove}
            onMouseUp={handleCanvasMouseUp} onMouseLeave={() => { setHoveredCell(null); isPanning.current = false; }}
            onClick={handleCanvasClick} onDoubleClick={handleCanvasDoubleClick} onWheel={handleWheel}
          />
          {loading && <div className="absolute inset-0 flex items-center justify-center bg-black/60"><div className="text-gray-300 animate-pulse text-sm">加载中...</div></div>}
          {!imgLoaded && currentItem && !loading && <div className="absolute inset-0 flex items-center justify-center"><div className="text-gray-500 animate-pulse">加载图像...</div></div>}
          {items.length === 0 && !loading && <div className="absolute inset-0 flex items-center justify-center text-gray-500">无匹配图像</div>}

          {/* Status bar */}
          <div className="absolute bottom-2 left-2 right-2 flex items-center justify-between pointer-events-none">
            <div className="text-[10px] text-gray-400 bg-black/70 backdrop-blur-sm px-2.5 py-1 rounded-md pointer-events-auto">
              {activeTab === "overlay" && <><span>滚轮缩放 | 拖拽平移 | R 重置</span><span className="ml-2 text-blue-400 font-mono">{Math.round(zoomLevel * 100)}%</span></>}
              {activeTab === "draw" && <span>单击添加顶点 | 双击闭合多边形 | Ctrl+Z 撤销</span>}
              {activeTab === "grid" && <span>点击格子或按 1-9 切换突破 | 右侧 Patch 也可点击</span>}
            </div>
            {currentItem && (
              <div className="text-[10px] bg-black/70 backdrop-blur-sm px-2.5 py-1 rounded-md text-gray-300 font-mono max-w-[350px] truncate">
                {currentItem.patient_id} · {currentItem.image_path.split("/").pop()}
              </div>
            )}
          </div>
        </div>

        {/* Right panel */}
        <div className="w-[340px] border-l border-gray-800 bg-[#0d1117] flex flex-col overflow-hidden shrink-0">
          <div className="flex-1 overflow-y-auto">
            {/* Patient info card */}
            {currentItem && (
              <div className="p-3 border-b border-gray-800">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-[10px] font-semibold text-gray-500 uppercase tracking-wider">患者信息</span>
                  {currentItem.is_annotated && (
                    <span className="text-[10px] text-green-400 bg-green-900/30 px-2 py-0.5 rounded-full font-medium">已标注 ✓</span>
                  )}
                </div>
                <div className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-xs">
                  <span className="text-gray-500">患者</span>
                  <span className="font-mono font-medium">{currentItem.patient_id}</span>
                  <span className="text-gray-500">T 分期</span>
                  <span className={`font-bold ${stageColor[currentItem.T_stage] || "text-gray-400"}`}>{currentItem.T_stage}</span>
                  <span className="text-gray-500">来源</span>
                  <span className="text-gray-300">{currentItem.source}</span>
                  <span className="text-gray-500">Mask</span>
                  <span className={hasMask ? "text-green-400" : "text-yellow-500"}>{hasMask ? "有" : "无"}</span>
                </div>
              </div>
            )}

            {/* ═══ Grid tab: patches + controls ═══ */}
            {activeTab === "grid" && hasMask && (
              <>
                {/* Patch previews */}
                <div className="p-3 border-b border-gray-800">
                  <div className="flex items-center justify-between mb-2">
                    <h3 className="text-[10px] font-semibold text-gray-500 uppercase tracking-wider">3×3 Patch 预览</h3>
                    {breachCount > 0 && (
                      <span className="text-[10px] text-red-400 bg-red-900/20 px-2 py-0.5 rounded-full font-bold">{breachCount} 处突破</span>
                    )}
                  </div>
                  <div className="grid grid-cols-3 gap-1.5">
                    {Array.from({ length: GRID_ROWS * GRID_COLS }).map((_, idx) => (
                      <button key={idx} onClick={() => { setGridCells(prev => { const n = [...prev]; n[idx] = { ...n[idx], has_breach: !n[idx].has_breach }; return n; }); }}
                        className={`group relative rounded-lg overflow-hidden border-2 transition-all duration-150 ${gridCells[idx].has_breach
                          ? "border-red-500 shadow-lg shadow-red-900/40 ring-1 ring-red-500/30"
                          : "border-gray-700/50 hover:border-blue-500/50 hover:shadow-md"}`}>
                        <canvas ref={el => { patchCanvasRefs.current[idx] = el; }} width={PATCH_SIZE} height={PATCH_SIZE} className="w-full h-auto" />
                        <div className={`absolute inset-0 transition-colors ${gridCells[idx].has_breach ? "bg-red-600/15" : "bg-transparent group-hover:bg-blue-500/5"}`} />
                        <div className={`absolute top-0.5 left-0.5 text-[10px] w-5 h-5 flex items-center justify-center rounded font-bold ${gridCells[idx].has_breach ? "bg-red-600 text-white" : "bg-black/50 text-gray-400 group-hover:bg-black/70"}`}>{idx + 1}</div>
                        {gridCells[idx].has_breach && (
                          <div className="absolute bottom-0 inset-x-0 text-center text-[9px] font-bold text-white bg-red-600/80 py-0.5 backdrop-blur-sm">突破</div>
                        )}
                      </button>
                    ))}
                  </div>
                  <p className="text-[9px] text-gray-600 mt-2 text-center">点击 Patch 切换突破状态</p>
                </div>

                {/* Per-cell detail controls (only for breached cells) */}
                {breachCount > 0 && (
                  <div className="p-3 border-b border-gray-800">
                    <h3 className="text-[10px] font-semibold text-gray-500 uppercase tracking-wider mb-2">突破区域详情</h3>
                    <div className="space-y-1.5">
                      {gridCells.filter(c => c.has_breach).map((cell) => {
                        const idx = cell.row * GRID_COLS + cell.col;
                        return (
                          <div key={idx} className="bg-red-950/20 border border-red-800/30 rounded-lg px-3 py-2">
                            <div className="flex items-center justify-between mb-1.5">
                              <div className="flex items-center gap-2">
                                <span className="inline-block w-5 h-5 rounded bg-red-600 text-center text-[10px] leading-5 font-bold text-white">{idx + 1}</span>
                                <span className="text-xs text-gray-400">R{cell.row + 1}C{cell.col + 1}</span>
                              </div>
                              <button onClick={() => { setGridCells(prev => { const n = [...prev]; n[idx] = { ...n[idx], has_breach: false }; return n; }); }}
                                className="text-[10px] text-gray-500 hover:text-red-400 transition-colors">✕ 取消</button>
                            </div>
                            <div className="flex gap-2">
                              <div className="flex-1">
                                <label className="text-[9px] text-gray-600 block mb-0.5">可见层数</label>
                                <select className="w-full bg-gray-800 border border-gray-700 rounded px-1.5 py-1 text-[11px] text-white"
                                  value={String(cell.visible_layers)}
                                  onChange={e => { const v = e.target.value; const p: VisibleLayers = v === "uncertain" ? "uncertain" : v === "3+" ? "3+" : (parseInt(v) as 0|1|2); setGridCells(prev => { const n = [...prev]; n[idx] = { ...n[idx], visible_layers: p }; return n; }); }}>
                                  {VISIBLE_LAYERS_OPTIONS.map(o => <option key={String(o.value)} value={String(o.value)}>{o.label}</option>)}
                                </select>
                              </div>
                              <div className="flex-1">
                                <label className="text-[9px] text-gray-600 block mb-0.5">信心度</label>
                                <select className="w-full bg-gray-800 border border-gray-700 rounded px-1.5 py-1 text-[11px] text-white"
                                  value={cell.breach_confidence}
                                  onChange={e => { setGridCells(prev => { const n = [...prev]; n[idx] = { ...n[idx], breach_confidence: e.target.value as BreachConfidence }; return n; }); }}>
                                  {CONFIDENCE_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
                                </select>
                              </div>
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                )}
              </>
            )}

            {/* No mask notice */}
            {(activeTab === "grid" || activeTab === "draw") && !hasMask && currentItem && (
              <div className="p-3">
                <div className="text-xs text-yellow-500 bg-yellow-900/20 border border-yellow-800/30 rounded-lg px-4 py-3">
                  此图片没有 Mask 标注，无法使用网格/绘制模式。请切换到完整图模式查看。
                </div>
              </div>
            )}

            {/* ═══ Draw tab controls ═══ */}
            {activeTab === "draw" && hasMask && (
              <div className="p-3 border-b border-gray-800">
                <h3 className="text-[10px] font-semibold text-gray-500 uppercase tracking-wider mb-2">自由绘制突破区域</h3>
                <div className="text-xs text-gray-400 space-y-1.5">
                  <div className="flex items-center justify-between">
                    <span>已完成多边形</span>
                    <span className="text-white font-semibold text-sm">{breachPolygons.length}</span>
                  </div>
                  {drawingPoints.length > 0 && (
                    <div className="flex items-center justify-between">
                      <span>正在绘制</span>
                      <span className="text-orange-400 font-mono">{drawingPoints.length} 个顶点</span>
                    </div>
                  )}
                </div>
                <div className="flex gap-2 mt-3 flex-wrap">
                  {drawingPoints.length >= 3 && (
                    <button onClick={() => { setBreachPolygons(prev => [...prev, { points: drawingPoints, label: `breach_${prev.length + 1}` }]); setDrawingPoints([]); }}
                      className="px-3 py-1.5 text-[11px] bg-orange-700 hover:bg-orange-600 rounded-md font-medium transition-colors">闭合多边形</button>
                  )}
                  {drawingPoints.length > 0 && (
                    <button onClick={() => setDrawingPoints(p => p.slice(0, -1))}
                      className="px-3 py-1.5 text-[11px] bg-gray-700 hover:bg-gray-600 rounded-md transition-colors">撤销点</button>
                  )}
                  {breachPolygons.length > 0 && (
                    <button onClick={() => setBreachPolygons(p => p.slice(0, -1))}
                      className="px-3 py-1.5 text-[11px] bg-gray-700 hover:bg-gray-600 rounded-md transition-colors">删除上一个</button>
                  )}
                  {(breachPolygons.length > 0 || drawingPoints.length > 0) && (
                    <button onClick={() => { setBreachPolygons([]); setDrawingPoints([]); }}
                      className="px-3 py-1.5 text-[11px] bg-red-800 hover:bg-red-700 rounded-md transition-colors">清除全部</button>
                  )}
                </div>
              </div>
            )}

            {/* Overlay tab info */}
            {activeTab === "overlay" && (
              <div className="p-3 border-b border-gray-800">
                <h3 className="text-[10px] font-semibold text-gray-500 uppercase tracking-wider mb-2">完整图模式</h3>
                <div className="text-xs text-gray-400 leading-relaxed">
                  <p>查看完整 EUS 图像，绿色区域为 lesion/tumor mask 标注。</p>
                  <p className="mt-1">滚轮缩放，拖拽平移，<span className="text-blue-400 font-mono">R</span> 重置视图。</p>
                  <p className="mt-1">按 <span className="text-blue-400 font-mono">W</span> 进入网格模式开始标注突破方向。</p>
                </div>
              </div>
            )}
          </div>

          {/* Bottom: note + save + navigation */}
          <div className="shrink-0 border-t border-gray-800">
            <div className="p-3">
              <textarea className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-xs text-white placeholder-gray-600 resize-none focus:outline-none focus:border-blue-500" rows={2} placeholder="备注（可选）..." value={note} onChange={e => setNote(e.target.value)} />
              <div className="flex items-center justify-between mt-2">
                <div className="flex gap-1.5">
                  <button onClick={() => setCurrentIdx(p => Math.max(p - 1, 0))} disabled={currentIdx === 0}
                    className="px-3 py-1.5 text-xs bg-gray-800 hover:bg-gray-700 disabled:opacity-30 rounded-md transition-colors font-medium">← 上一张</button>
                  <button onClick={() => setCurrentIdx(p => Math.min(p + 1, items.length - 1))} disabled={currentIdx >= items.length - 1}
                    className="px-3 py-1.5 text-xs bg-gray-800 hover:bg-gray-700 disabled:opacity-30 rounded-md transition-colors font-medium">下一张 →</button>
                </div>
                <div className="flex items-center gap-2">
                  {saveMsg && <span className={`text-[11px] font-medium ${saveMsg.includes("✓") ? "text-green-400" : "text-red-400"}`}>{saveMsg}</span>}
                  <button onClick={handleSave} disabled={saving}
                    className="px-5 py-1.5 text-xs bg-blue-600 hover:bg-blue-500 disabled:opacity-50 rounded-md font-semibold transition-colors shadow-sm shadow-blue-500/20">
                    {saving ? "保存中..." : "保存 ⏎"}
                  </button>
                </div>
              </div>
            </div>

            {/* Pagination */}
            {pagination.totalPages > 1 && (
              <div className="px-3 pb-2 flex items-center justify-between text-[11px]">
                <span className="text-gray-500">第 {page}/{pagination.totalPages} 页</span>
                <div className="flex gap-1">
                  <button onClick={() => setPage(p => Math.max(1, p - 1))} disabled={page <= 1}
                    className="px-2 py-0.5 bg-gray-800 hover:bg-gray-700 disabled:opacity-30 rounded text-gray-300 transition-colors">上页</button>
                  <button onClick={() => setPage(p => Math.min(pagination.totalPages, p + 1))} disabled={page >= pagination.totalPages}
                    className="px-2 py-0.5 bg-gray-800 hover:bg-gray-700 disabled:opacity-30 rounded text-gray-300 transition-colors">下页</button>
                </div>
              </div>
            )}

            {/* Quick nav dots */}
            <div className="px-3 pb-2">
              <div className="flex flex-wrap gap-[3px] max-h-[60px] overflow-y-auto">
                {items.map((it, idx) => (
                  <button key={idx} onClick={() => setCurrentIdx(idx)} title={`${it.patient_id} (${it.T_stage})`}
                    className={`w-[14px] h-[14px] text-[6px] rounded-sm transition-colors ${idx === currentIdx ? "bg-blue-600 text-white" : it.is_annotated ? "bg-green-900/60 text-green-300" : "bg-gray-800/80 text-gray-600 hover:bg-gray-700"}`}>
                  </button>
                ))}
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Help overlay */}
      {showHelp && (
        <div className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-center justify-center" onClick={() => setShowHelp(false)}>
          <div className="bg-[#0d1117] border border-gray-700 rounded-xl p-6 max-w-md w-full mx-4 shadow-2xl" onClick={e => e.stopPropagation()}>
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-base font-bold">快捷键</h2>
              <button onClick={() => setShowHelp(false)} className="text-gray-500 hover:text-white text-lg">✕</button>
            </div>
            <div className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 text-sm">
              <kbd className="font-mono text-blue-400 text-xs bg-blue-900/20 px-1.5 py-0.5 rounded">Q</kbd><span className="text-gray-300">完整图模式</span>
              <kbd className="font-mono text-blue-400 text-xs bg-blue-900/20 px-1.5 py-0.5 rounded">W</kbd><span className="text-gray-300">3×3 网格模式</span>
              <kbd className="font-mono text-blue-400 text-xs bg-blue-900/20 px-1.5 py-0.5 rounded">E</kbd><span className="text-gray-300">自由绘制模式</span>
              <kbd className="font-mono text-blue-400 text-xs bg-blue-900/20 px-1.5 py-0.5 rounded">1-9</kbd><span className="text-gray-300">切换网格区域突破 (W 模式)</span>
              <kbd className="font-mono text-blue-400 text-xs bg-blue-900/20 px-1.5 py-0.5 rounded">← →</kbd><span className="text-gray-300">上/下一张图像</span>
              <kbd className="font-mono text-blue-400 text-xs bg-blue-900/20 px-1.5 py-0.5 rounded">Enter</kbd><span className="text-gray-300">保存并跳到下一张</span>
              <kbd className="font-mono text-blue-400 text-xs bg-blue-900/20 px-1.5 py-0.5 rounded">Ctrl+S</kbd><span className="text-gray-300">保存当前标注</span>
              <kbd className="font-mono text-blue-400 text-xs bg-blue-900/20 px-1.5 py-0.5 rounded">Ctrl+Z</kbd><span className="text-gray-300">撤销绘制/删除多边形</span>
              <kbd className="font-mono text-blue-400 text-xs bg-blue-900/20 px-1.5 py-0.5 rounded">R</kbd><span className="text-gray-300">重置缩放 (Q 模式)</span>
              <kbd className="font-mono text-blue-400 text-xs bg-blue-900/20 px-1.5 py-0.5 rounded">H / ?</kbd><span className="text-gray-300">显示/隐藏帮助</span>
              <kbd className="font-mono text-blue-400 text-xs bg-blue-900/20 px-1.5 py-0.5 rounded">Esc</kbd><span className="text-gray-300">关闭帮助</span>
            </div>
            <div className="mt-4 pt-3 border-t border-gray-800 text-xs text-gray-500">
              <p><strong className="text-gray-400">网格模式:</strong> 点击 Canvas 上的格子或右侧 Patch 预览来标记突破区域</p>
              <p className="mt-1"><strong className="text-gray-400">绘制模式:</strong> 单击添加顶点，双击闭合多边形</p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
