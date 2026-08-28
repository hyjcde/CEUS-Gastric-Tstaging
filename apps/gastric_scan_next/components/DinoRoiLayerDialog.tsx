'use client';

import React, { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import { BrainCircuit, Loader2, X } from 'lucide-react';
import type { DinoFeatureResult, DinoLayerResult } from '@/components/InteractiveSegPanel';

type Props = {
  open: boolean;
  busy?: boolean;
  zh?: boolean;
  result?: DinoFeatureResult | null;
  activeLayer?: number;
  onSelectLayer?: (layer: number) => void;
  onClose: () => void;
};

export function DinoRoiLayerDialog({
  open,
  busy = false,
  zh = true,
  result = null,
  activeLayer,
  onSelectLayer,
  onClose,
}: Props) {
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);

  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose, open]);

  if (!mounted || !open) return null;

  const layers = (result?.available && result.layers?.length ? result.layers : result?.available ? [result] : [])
    .filter((layer): layer is DinoLayerResult => Number.isFinite(Number(layer?.layer_index)));
  const selected = layers.find((layer) => layer.layer_index === activeLayer) || layers[layers.length - 1] || null;
  const error = result && !result.available ? result.error : null;

  return createPortal(
    <div className="fixed inset-0 z-[460] flex items-center justify-center p-4" role="dialog" aria-modal="true" aria-label={zh ? 'ROI DINO 层特征' : 'ROI DINO layers'}>
      <button
        type="button"
        className="absolute inset-0 bg-[#08090a]/45 backdrop-blur-sm"
        aria-label={zh ? '收起对话框' : 'Close dialog'}
        onClick={onClose}
      />
      <div className="relative w-[min(36rem,100%)] overflow-hidden rounded-2xl border border-violet-300/25 bg-[#14151a] shadow-[0_24px_64px_rgba(0,0,0,0.5)]">
        <div className="flex items-start justify-between gap-3 border-b border-white/10 px-4 py-3">
          <div>
            <div className="flex items-center gap-2 text-[13px] font-semibold text-violet-50">
              <BrainCircuit size={15} />
              {zh ? 'ROI 附近 DINO 层特征' : 'ROI DINO layers'}
            </div>
            <div className="mt-0.5 text-[10px] text-slate-400">
              {zh ? '当前帧病灶/胃壁附近。草稿，不定 cT。Esc 或点收起。' : 'Current-frame lesion/wall neighborhood. Draft only. Esc or Close to collapse.'}
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="inline-flex items-center gap-1 rounded-lg border border-white/15 px-2 py-1 text-[11px] text-slate-200 hover:bg-white/10"
          >
            <X size={13} />
            {zh ? '收起' : 'Close'}
          </button>
        </div>
        <div className="px-4 py-3">
          {busy && !layers.length ? (
            <div className="flex items-center gap-2 py-8 text-[12px] text-violet-100">
              <Loader2 size={16} className="animate-spin" />
              {zh ? '正在提取 ROI 层特征，请稍候…' : 'Extracting ROI layer features…'}
            </div>
          ) : null}
          {error ? (
            <div className="rounded-lg border border-rose-400/30 bg-rose-500/10 px-3 py-2 text-[12px] text-rose-100">
              {error}
            </div>
          ) : null}
          {layers.length ? (
            <>
              <div className="flex flex-wrap items-center gap-1.5">
                {layers.map((layer) => {
                  const index = Number(layer.layer_index);
                  const selectedLayer = selected?.layer_index === index;
                  return (
                    <button
                      key={`dino-dialog-l${index}`}
                      type="button"
                      onClick={() => onSelectLayer?.(index)}
                      className={`rounded px-2 py-1 text-[11px] font-semibold ${
                        selectedLayer
                          ? 'bg-violet-200 text-slate-900'
                          : 'bg-white/10 text-violet-100 hover:bg-white/15'
                      }`}
                    >
                      {`L${index}`}
                    </button>
                  );
                })}
                {busy ? <Loader2 size={13} className="ml-1 animate-spin text-violet-200" /> : null}
                {selected?.scalars?.cos_wall_lesion != null ? (
                  <span className="ml-auto rounded bg-black/40 px-1.5 py-0.5 font-mono text-[10px] text-violet-100">
                    {zh ? '壁/灶' : 'wall/lesion'} {Number(selected.scalars.cos_wall_lesion).toFixed(2)}
                  </span>
                ) : null}
              </div>
              <div className="mt-3 grid grid-cols-2 gap-2">
                {layers.map((layer) => {
                  const index = Number(layer.layer_index);
                  const feature = layer.roi_feature_overlay_png || layer.feature_overlay_png;
                  const wall = layer.roi_wall_evidence_overlay_png || layer.wall_evidence_overlay_png;
                  return (
                    <button
                      key={`dino-dialog-preview-${index}`}
                      type="button"
                      onClick={() => onSelectLayer?.(index)}
                      className={`rounded-lg border p-1.5 text-left ${
                        selected?.layer_index === index
                          ? 'border-violet-200/80 bg-black/40'
                          : 'border-white/10 bg-black/20'
                      }`}
                    >
                      <div className="mb-1 font-mono text-[10px] text-violet-100">{`L${index}`}</div>
                      <span className="flex gap-1">
                        {feature ? (
                          // eslint-disable-next-line @next/next/no-img-element
                          <img src={feature} alt="" className="h-20 w-1/2 rounded object-cover" />
                        ) : null}
                        {wall ? (
                          // eslint-disable-next-line @next/next/no-img-element
                          <img src={wall} alt="" className="h-20 w-1/2 rounded object-cover" />
                        ) : null}
                      </span>
                      <div className="mt-1 text-[9px] text-slate-400">
                        {zh ? '左：像不像灶　右：更像壁还是灶' : 'Left: lesion-like. Right: wall vs lesion.'}
                      </div>
                    </button>
                  );
                })}
              </div>
            </>
          ) : null}
        </div>
      </div>
    </div>,
    document.body,
  );
}
