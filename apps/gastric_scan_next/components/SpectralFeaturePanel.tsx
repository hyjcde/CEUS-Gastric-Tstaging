'use client';

import React, { useMemo, useState } from 'react';
import { Activity, Info, Sparkles } from 'lucide-react';
import type { AgentAnalysisResponse } from '@/types';

type Props = {
  analysis: AgentAnalysisResponse | null;
  boundaryRoughness?: number | null;
  zh?: boolean;
};

type FeatureRow = {
  id: string;
  label: string;
  value: number | null;
  note: string;
};

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown>
    : null;
}

function asNumber(value: unknown): number | null {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function valueFrom(source: Record<string, unknown> | null, key: string): number | null {
  if (!source) return null;
  const direct = asNumber(source[key]);
  if (direct != null) return direct;
  const nested = asRecord(source[key]);
  return asNumber(nested?.value ?? nested?.raw ?? nested?.score);
}

function percent(value: number): number {
  const scaled = value <= 1 ? value * 100 : value;
  return Math.max(0, Math.min(100, scaled));
}

function valueLabel(value: number): string {
  return value <= 1 ? value.toFixed(2) : value.toFixed(1);
}

export function SpectralFeaturePanel({ analysis, boundaryRoughness = null, zh = true }: Props) {
  const [task, setTask] = useState<'bm' | 't'>('bm');

  const rows = useMemo<FeatureRow[]>(() => {
    const toolEvidence = asRecord(analysis?.tool_evidence);
    const morphology = asRecord(toolEvidence?.morphology);
    const signs = asRecord(toolEvidence?.gc_us_signs);
    const featurePack = asRecord(signs?.feature_pack);
    const featureFields = asRecord(featurePack?.fields);
    const artifacts = asRecord(analysis?.prediction_artifacts);
    const artifactPack = asRecord(artifacts?.gc_us_feature_pack);
    const sources = [morphology, featureFields, featurePack, artifactPack, artifacts];

    const pick = (keys: string[], fallback: number | null = null): number | null => {
      for (const source of sources) {
        for (const key of keys) {
          const value = valueFrom(source, key);
          if (value != null) return value;
        }
      }
      return fallback;
    };

    return [
      {
        id: 'hf_energy_ratio',
        label: zh ? '高频能量比, FFT' : 'High-frequency energy, FFT',
        value: pick(['hf_energy_ratio', 'morph_fd_high_energy', 'margin_bof_high_mean']),
        note: zh ? '旧版前端面板的高频边界特征，当前只显示实际返回值。' : 'High-frequency boundary feature from the legacy panel, showing returned values only.',
      },
      {
        id: 'fd_mid_energy',
        label: zh ? '中频 Fourier 能量' : 'Mid-band Fourier energy',
        value: pick(['morph_fd_mid_energy', 'margin_shape_fd_mid', 'margin_bof_mid_mean']),
        note: zh ? '中尺度分叶和边界起伏代理。' : 'Proxy for mid-scale lobulation and boundary undulation.',
      },
      {
        id: 'fd_low_energy',
        label: zh ? '低频能量' : 'Low-band energy',
        value: pick(['morph_fd_low_energy']),
        note: zh ? '整体轮廓形状和椭圆度的低频成分。' : 'Low-band contribution from global contour shape and ellipticity.',
      },
      {
        id: 'boundary_roughness',
        label: zh ? '边界频谱粗糙度' : 'Boundary spectral roughness',
        value: boundaryRoughness ?? pick(['boundary_roughness', 'morph_nrl_roughness']),
        note: zh ? '边界高频细节代理，不等同于病理浸润深度。' : 'High-frequency boundary proxy, not a pathology depth measurement.',
      },
      {
        id: 'spiculation',
        label: zh ? '毛刺或不规则度代理' : 'Spiculation or irregularity proxy',
        value: pick(['margin_spic_robust', 'morph_irregularity_index', 'roughness_index']),
        note: zh ? '结合频带能量、峰值和形态几何的辅助指标。' : 'Auxiliary metric combining band energy, peaks, and contour geometry.',
      },
    ].filter((row) => row.value != null);
  }, [analysis, boundaryRoughness, zh]);

  const analysisPoints = task === 'bm'
    ? (zh
      ? [
          '高频能量和边界粗糙度升高，可提示界面锐利或不规则。',
          '需要结合纹理异质性、轮廓形态和医生复核，不能单独判定恶性。',
          '旧版面板允许点击特征行查看解释，当前报告保留同样的特征解释结构。',
        ]
      : [
          'Higher band energy and boundary roughness may indicate a sharp or irregular interface.',
          'Combine texture heterogeneity, contour morphology, and physician review before judging malignancy.',
          'The current report preserves the legacy clickable feature explanation pattern.',
        ])
    : (zh
      ? [
          '频谱特征不能进入 stage-driving evidence，也不能解锁确定 cT。',
          'T 分期仍以经确认的壁层、浆膜或邻近器官证据为主；长径、厚度、FFT 仅作辅助。',
          '缺少当前病例频谱输出时，界面保持未评估，不使用旧病例数值填充。',
        ]
      : [
          'Spectral features must not enter stage-driving evidence and cannot unlock definite cT.',
          'T staging remains driven by confirmed wall, serosa, or adjacent-organ evidence; size and FFT are assistive only.',
          'When the current case has no spectral output, the panel stays unassessed rather than using legacy values.',
        ]);

  return (
    <section className="rounded-2xl border border-amber-300/20 bg-[linear-gradient(135deg,rgba(70,45,8,0.22),rgba(6,10,15,0.94))] p-5">
        <div className="mb-3 flex items-start justify-between gap-3">
          <div className="flex items-center gap-2 text-sm font-bold text-amber-50">
            <Sparkles size={15} className="text-amber-300" />
            <span>{zh ? '频谱和形态特征' : 'Spectral and morphology features'}</span>
          </div>
          <span className="rounded-full border border-rose-300/30 bg-rose-400/10 px-2 py-0.5 text-[10px] font-semibold text-rose-100">
            {zh ? '不能决定 T 分期' : 'Cannot decide T stage'}
          </span>
        </div>

      <div className="rounded-xl border border-white/10 bg-black/25 p-3">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-2 text-[11px] font-semibold text-white">
            <Activity size={13} className="text-amber-300" />
            {zh ? '分析要点' : 'Analysis points'}
          </div>
          <div className="inline-flex overflow-hidden rounded-md border border-white/10">
            {[
              { id: 'bm' as const, label: zh ? '良恶性判断' : 'Benign or malignant' },
              { id: 't' as const, label: zh ? '形态辅助说明' : 'Morphology assist note' },
            ].map((item) => (
              <button
                key={item.id}
                type="button"
                onClick={() => setTask(item.id)}
                className={`border-0 px-2.5 py-1 text-[10px] transition ${
                  task === item.id
                    ? 'bg-amber-300 text-slate-950'
                    : 'bg-transparent text-slate-400 hover:bg-white/10 hover:text-white'
                }`}
              >
                {item.label}
              </button>
            ))}
          </div>
        </div>

        {rows.length ? (
          <div className="space-y-3">
            {rows.map((row) => (
              <div key={row.id}>
                <div className="mb-1 flex items-center justify-between gap-3 text-[11px]">
                  <span className="text-slate-300">{row.label}</span>
                  <span className="font-mono text-amber-100">{valueLabel(row.value as number)}</span>
                </div>
                <div className="relative h-2 overflow-hidden rounded-full bg-white/10">
                  <div
                    className="h-full rounded-full bg-gradient-to-r from-amber-500/70 to-orange-300"
                    style={{ width: `${percent(row.value as number)}%` }}
                  />
                </div>
                <div className="mt-1 text-[9px] leading-relaxed text-slate-500">{row.note}</div>
              </div>
            ))}
          </div>
        ) : (
          <div className="rounded-lg border border-dashed border-white/10 px-3 py-5 text-center text-[11px] text-slate-500">
            {zh ? '当前病例尚未返回 Fourier 频带特征。' : 'No Fourier band features were returned for this case.'}
          </div>
        )}

        <div className="mt-3 rounded-lg border border-amber-300/15 bg-amber-300/5 p-3">
          <div className="mb-1 flex items-center gap-1.5 text-[10px] font-semibold text-amber-100">
            <Info size={12} />
            {zh ? '特征解释' : 'Feature interpretation'}
          </div>
          <div className="space-y-1 text-[10px] leading-relaxed text-slate-300">
            {analysisPoints.map((point) => (
              <div key={point} className="flex gap-2">
                <span className="text-amber-300">▸</span>
                <span>{point}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="mt-3 text-[10px] leading-relaxed text-amber-100/65">
        {zh
          ? '来源对应旧版 ai_demo.html 的特征行和分析要点布局。当前面板不复制 BM-045 的静态数值，只展示当前病例实际返回的频谱或形态特征。'
          : 'This follows the feature-row and analysis-point layout from the legacy ai_demo.html. Static BM-045 values are not copied; only features returned for the current case are shown.'}
      </div>
    </section>
  );
}
