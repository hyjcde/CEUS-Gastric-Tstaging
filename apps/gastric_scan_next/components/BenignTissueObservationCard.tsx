"use client";

import React from 'react';
import { Eye, Layers3, ScanSearch } from 'lucide-react';
import type { Patient } from '@/types';

export function BenignTissueObservationCard({ patient }: { patient: Patient }) {
  const observations = [
    '胃腔充盈和图像质量',
    '胃壁层次连续性与局部增厚',
    '黏膜面、浆膜面和周围回声',
    '病灶边界及邻近组织关系',
  ];

  return (
    <section className="rounded-xl border border-emerald-400/25 bg-emerald-950/20 p-3 text-[11px] text-slate-200">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2 font-semibold text-emerald-100">
            <Layers3 size={14} />
            组织观察模式
          </div>
          <div className="mt-1 text-[10px] text-emerald-200/70">
            良性队列先观察组织，不输出胃癌 T 分期结论
          </div>
        </div>
        <Eye size={16} className="text-emerald-300" />
      </div>

      <div className="mt-3 grid grid-cols-2 gap-1.5">
        <div className="rounded border border-white/10 bg-black/20 px-2 py-1.5">
          <div className="text-[9px] text-slate-500">当前病例</div>
          <div className="mt-0.5 truncate font-mono text-[10px] text-slate-200">{patient.id_short || patient.id}</div>
        </div>
        <div className="rounded border border-white/10 bg-black/20 px-2 py-1.5">
          <div className="text-[9px] text-slate-500">数据中心</div>
          <div className="mt-0.5 truncate text-[10px] text-slate-200">{patient.center_label || '良性队列'}</div>
        </div>
      </div>

      <div className="mt-3 border-t border-emerald-400/15 pt-3">
        <div className="flex items-center gap-2 font-semibold text-cyan-100">
          <ScanSearch size={13} />
          系统观察顺序
        </div>
        <div className="mt-2 space-y-1.5">
          {observations.map((item, index) => (
            <div key={item} className="flex items-start gap-2 rounded border border-white/10 bg-black/20 px-2 py-1.5">
              <span className="font-mono text-[9px] text-cyan-300">{String(index + 1).padStart(2, '0')}</span>
              <span className="text-[10px] text-slate-300">{item}</span>
            </div>
          ))}
        </div>
      </div>

      <div className="mt-3 rounded border border-amber-400/20 bg-amber-500/5 px-2 py-1.5 text-[10px] leading-relaxed text-amber-100/80">
        当前影像可继续打开组织层观察和边界分析；系统辅助结果仅供医生复核。
      </div>
    </section>
  );
}
