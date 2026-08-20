'use client';

import React, { useEffect, useMemo, useRef, useState } from 'react';
import { FileText } from 'lucide-react';
import { useSettings } from '@/contexts/SettingsContext';
import {
  BM_US_ASCITES_OPTIONS,
  BM_US_CDFI_OPTIONS,
  BM_US_LESION_SITES,
  BM_US_PERISTALSIS_OPTIONS,
  BM_US_REPORT_SOURCE_DOC,
  BM_US_RETENTION_OPTIONS,
  BM_US_SURFACE_OPTIONS,
  BM_US_WALL_LAYER_OPTIONS,
  bmUsOptionLabel,
  createBmUsReportState,
  type BmUsReportFields,
  type BmUsReportState,
} from '@/lib/bm-us-report-template';

type NatureLabel = 'benign' | 'malignant';

type Props = {
  caseId?: string | null;
  clinical?: Record<string, unknown>;
  compact?: boolean;
  assistNature?: NatureLabel | null;
  onStateChange?: (state: BmUsReportState) => void;
};

const EMPTY_CLINICAL: Record<string, unknown> = {};

function Chip<T extends string>({
  value,
  current,
  label,
  onSelect,
}: {
  value: T;
  current: string;
  label: string;
  onSelect: (value: T) => void;
}) {
  const active = current === value;
  return (
    <button
      type="button"
      onClick={() => onSelect(value)}
      className={`rounded border px-2 py-1 text-[11px] ${
        active
          ? 'border-amber-300/70 bg-amber-500/20 text-amber-50'
          : 'border-white/10 text-slate-400 hover:bg-white/5'
      }`}
    >
      {label}
    </button>
  );
}

function NumberField({
  value,
  onChange,
  suffix,
}: {
  value: number | null;
  onChange: (value: number | null) => void;
  suffix: string;
}) {
  return (
    <label className="inline-flex items-center gap-1 rounded border border-white/10 bg-black/20 px-1.5 py-1">
      <input
        type="number"
        step="0.1"
        min="0"
        value={value ?? ''}
        onChange={(event) => {
          const next = event.target.value;
          onChange(next === '' ? null : Number(next));
        }}
        className="w-16 bg-transparent text-[11px] text-gray-100 outline-none"
      />
      <span className="text-[10px] text-slate-500">{suffix}</span>
    </label>
  );
}

function TextField({
  value,
  onChange,
  placeholder,
  wide,
}: {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  wide?: boolean;
}) {
  return (
    <input
      type="text"
      value={value}
      placeholder={placeholder}
      onChange={(event) => onChange(event.target.value)}
      className={`rounded border border-white/10 bg-black/20 px-2 py-1 text-[11px] text-gray-100 outline-none placeholder:text-slate-600 ${wide ? 'w-full' : 'w-28'}`}
    />
  );
}

export function BmEvidencePanel({
  caseId,
  clinical = EMPTY_CLINICAL,
  compact = false,
  assistNature = null,
  onStateChange,
}: Props) {
  const { language } = useSettings();
  const zh = language !== 'en';
  const storageKey = caseId ? `next-bm-report:${caseId}` : null;
  const [state, setState] = useState<BmUsReportState>(() => createBmUsReportState({
    case_id: caseId,
    clinical,
    fields: assistNature ? { nature: assistNature } : undefined,
  }));

  useEffect(() => {
    const seeded = createBmUsReportState({
      case_id: caseId,
      clinical,
      fields: assistNature ? { nature: assistNature } : undefined,
    });
    if (!storageKey || typeof window === 'undefined') {
      setState(seeded);
      return;
    }
    try {
      const raw = window.localStorage.getItem(storageKey);
      if (!raw) {
        setState(seeded);
        return;
      }
      const parsed = JSON.parse(raw) as BmUsReportState;
      setState({
        ...seeded,
        fields: {
          ...seeded.fields,
          ...parsed.fields,
          nature: parsed.fields?.nature || assistNature || '',
        },
      });
    } catch {
      setState(seeded);
    }
  }, [assistNature, caseId, storageKey]);

  const lastEmittedRef = useRef('');
  useEffect(() => {
    let serialized = '';
    try {
      serialized = JSON.stringify(state.fields);
    } catch {
      serialized = '';
    }
    if (serialized && serialized === lastEmittedRef.current) return;
    lastEmittedRef.current = serialized;
    onStateChange?.(state);
    if (!storageKey || typeof window === 'undefined') return;
    try {
      window.localStorage.setItem(storageKey, JSON.stringify(state));
    } catch {
      // Browser storage is optional.
    }
  }, [onStateChange, state, storageKey]);

  const patch = (next: Partial<BmUsReportFields>) => {
    setState((prev) => ({
      ...prev,
      fields: { ...prev.fields, ...next },
    }));
  };

  const fields = state.fields;
  const siteLabel = useMemo(
    () => (value: string) => bmUsOptionLabel(value, zh),
    [zh],
  );

  return (
    <section className={`rounded-xl border border-amber-400/20 bg-amber-400/[0.04] text-sm text-gray-200 ${compact ? 'p-2.5' : 'p-3.5'}`}>
      <div className="mb-2.5 flex items-center gap-1.5 text-base font-semibold text-amber-50">
        <FileText size={16} />
        {zh ? '良恶性鉴别报告' : 'Benign / malignant report'}
      </div>
      <div className="mb-2 text-[11px] leading-relaxed text-slate-400">
        {zh
          ? `按《${BM_US_REPORT_SOURCE_DOC}》填写。生成报告时用此模板，不再套用 T 分期壁层报告。`
          : `Complete the ${BM_US_REPORT_SOURCE_DOC} fields. Generate uses this template, not the T-staging wall-layer report.`}
      </div>

      <div className="mb-2">
        <div className="mb-1 text-xs font-semibold text-slate-300">{zh ? '病灶部位' : 'Lesion site'}</div>
        <div className="flex flex-wrap gap-1">
          {BM_US_LESION_SITES.map((site) => (
            <Chip
              key={site}
              value={site}
              current={fields.lesion_site}
              label={siteLabel(site)}
              onSelect={(value) => patch({ lesion_site: value, impression_site: value })}
            />
          ))}
        </div>
      </div>

      <div className="mb-2 grid grid-cols-2 gap-2">
        <div>
          <div className="mb-1 text-xs font-semibold text-slate-300">{zh ? '最大径' : 'Max diameter'}</div>
          <NumberField value={fields.maximum_diameter_cm} onChange={(value) => patch({ maximum_diameter_cm: value })} suffix="cm" />
        </div>
        <div>
          <div className="mb-1 text-xs font-semibold text-slate-300">{zh ? '最厚径' : 'Max thickness'}</div>
          <NumberField value={fields.maximum_thickness_cm} onChange={(value) => patch({ maximum_thickness_cm: value })} suffix="cm" />
        </div>
      </div>

      <div className="mb-2">
        <div className="mb-1 text-xs font-semibold text-slate-300">{zh ? '溃疡' : 'Ulcer'}</div>
        <div className="mb-1.5 flex flex-wrap gap-1">
          <Chip value="no" current={fields.ulcer_present === false ? 'no' : fields.ulcer_present === true ? 'yes' : ''} label={zh ? '无' : 'None'} onSelect={() => patch({ ulcer_present: false })} />
          <Chip value="yes" current={fields.ulcer_present === false ? 'no' : fields.ulcer_present === true ? 'yes' : ''} label={zh ? '有' : 'Present'} onSelect={() => patch({ ulcer_present: true })} />
        </div>
        {fields.ulcer_present ? (
          <div className="flex flex-wrap gap-1.5">
            <NumberField value={fields.ulcer_base_width_cm} onChange={(value) => patch({ ulcer_base_width_cm: value })} suffix={zh ? '底宽 cm' : 'base cm'} />
            <NumberField value={fields.ulcer_mouth_width_cm} onChange={(value) => patch({ ulcer_mouth_width_cm: value })} suffix={zh ? '口宽 cm' : 'mouth cm'} />
            <NumberField value={fields.ulcer_depth_cm} onChange={(value) => patch({ ulcer_depth_cm: value })} suffix={zh ? '深 cm' : 'depth cm'} />
          </div>
        ) : null}
      </div>

      <div className="mb-2">
        <div className="mb-1 text-xs font-semibold text-slate-300">{zh ? '胃壁层次结构' : 'Wall-layer structure'}</div>
        <div className="flex flex-wrap gap-1">
          {BM_US_WALL_LAYER_OPTIONS.map((option) => (
            <Chip
              key={option}
              value={option}
              current={fields.wall_layers}
              label={siteLabel(option)}
              onSelect={(value) => patch({ wall_layers: value, impression_wall: value === '其他' ? fields.wall_layers_other : value })}
            />
          ))}
        </div>
        {fields.wall_layers === '其他' ? (
          <div className="mt-1.5">
            <TextField value={fields.wall_layers_other} onChange={(value) => patch({ wall_layers_other: value, impression_wall: value })} placeholder={zh ? '其他描述' : 'Other'} wide />
          </div>
        ) : null}
      </div>

      <div className="mb-2">
        <div className="mb-1 text-xs font-semibold text-slate-300">{zh ? '病灶表面' : 'Lesion surface'}</div>
        <div className="flex flex-wrap gap-1">
          {BM_US_SURFACE_OPTIONS.map((option) => (
            <Chip key={option} value={option} current={fields.surface} label={siteLabel(option)} onSelect={(value) => patch({ surface: value })} />
          ))}
        </div>
        {fields.surface === '其他' ? (
          <div className="mt-1.5">
            <TextField value={fields.surface_other} onChange={(value) => patch({ surface_other: value })} placeholder={zh ? '其他描述' : 'Other'} wide />
          </div>
        ) : null}
      </div>

      <div className="mb-2">
        <div className="mb-1 text-xs font-semibold text-slate-300">{zh ? '胃蠕动' : 'Peristalsis'}</div>
        <div className="flex flex-wrap gap-1">
          {BM_US_PERISTALSIS_OPTIONS.map((option) => (
            <Chip key={option} value={option} current={fields.peristalsis} label={siteLabel(option)} onSelect={(value) => patch({ peristalsis: value })} />
          ))}
        </div>
      </div>

      <div className="mb-2">
        <div className="mb-1 text-xs font-semibold text-slate-300">{zh ? '胃腔狭窄' : 'Luminal stenosis'}</div>
        <div className="mb-1.5 flex flex-wrap gap-1">
          <Chip value="no" current={fields.stenosis_present === false ? 'no' : fields.stenosis_present === true ? 'yes' : ''} label={zh ? '无' : 'None'} onSelect={() => patch({ stenosis_present: false })} />
          <Chip value="yes" current={fields.stenosis_present === false ? 'no' : fields.stenosis_present === true ? 'yes' : ''} label={zh ? '有' : 'Present'} onSelect={() => patch({ stenosis_present: true })} />
        </div>
        {fields.stenosis_present ? (
          <div className="flex flex-wrap gap-1.5">
            <TextField value={fields.stenosis_site} onChange={(value) => patch({ stenosis_site: value })} placeholder={zh ? '部位' : 'Site'} />
            <NumberField value={fields.stenosis_min_diameter_cm} onChange={(value) => patch({ stenosis_min_diameter_cm: value })} suffix={zh ? '最窄 cm' : 'min cm'} />
          </div>
        ) : null}
      </div>

      <div className="mb-2">
        <div className="mb-1 text-xs font-semibold text-slate-300">{zh ? '胃潴留' : 'Gastric retention'}</div>
        <div className="flex flex-wrap gap-1">
          {BM_US_RETENTION_OPTIONS.map((option) => (
            <Chip key={option} value={option} current={fields.retention} label={siteLabel(option)} onSelect={(value) => patch({ retention: value })} />
          ))}
        </div>
      </div>

      <div className="mb-2">
        <div className="mb-1 text-xs font-semibold text-slate-300">CDFI</div>
        <div className="flex flex-wrap gap-1">
          {BM_US_CDFI_OPTIONS.map((option) => (
            <Chip key={option} value={option} current={fields.cdfi} label={siteLabel(option)} onSelect={(value) => patch({ cdfi: value })} />
          ))}
        </div>
      </div>

      <div className="mb-2">
        <div className="mb-1 text-xs font-semibold text-slate-300">{zh ? '淋巴结' : 'Lymph nodes'}</div>
        <div className="mb-1.5 flex flex-wrap gap-1">
          <Chip value="no" current={fields.lymph_nodes_present === false ? 'no' : fields.lymph_nodes_present === true ? 'yes' : ''} label={zh ? '无' : 'None'} onSelect={() => patch({ lymph_nodes_present: false })} />
          <Chip value="yes" current={fields.lymph_nodes_present === false ? 'no' : fields.lymph_nodes_present === true ? 'yes' : ''} label={zh ? '有' : 'Present'} onSelect={() => patch({ lymph_nodes_present: true })} />
        </div>
        {fields.lymph_nodes_present ? (
          <div className="grid grid-cols-2 gap-1.5">
            <TextField value={fields.lymph_node_site} onChange={(value) => patch({ lymph_node_site: value })} placeholder={zh ? '位置' : 'Site'} wide />
            <TextField value={fields.lymph_node_count} onChange={(value) => patch({ lymph_node_count: value })} placeholder={zh ? '数量' : 'Count'} wide />
            <NumberField value={fields.lymph_node_long_cm} onChange={(value) => patch({ lymph_node_long_cm: value })} suffix={zh ? '长径 cm' : 'long cm'} />
            <NumberField value={fields.lymph_node_short_cm} onChange={(value) => patch({ lymph_node_short_cm: value })} suffix={zh ? '短径 cm' : 'short cm'} />
            <TextField value={fields.lymph_node_hilum} onChange={(value) => patch({ lymph_node_hilum: value })} placeholder={zh ? '淋巴门' : 'Hilum'} wide />
            <TextField value={fields.lymph_node_flow} onChange={(value) => patch({ lymph_node_flow: value })} placeholder={zh ? '血流信号' : 'Flow'} wide />
          </div>
        ) : null}
      </div>

      <div className="mb-2">
        <div className="mb-1 text-xs font-semibold text-slate-300">{zh ? '腹水' : 'Ascites'}</div>
        <div className="flex flex-wrap gap-1">
          {BM_US_ASCITES_OPTIONS.map((option) => (
            <Chip key={option} value={option} current={fields.ascites} label={siteLabel(option)} onSelect={(value) => patch({ ascites: value })} />
          ))}
        </div>
      </div>

      <div className="mb-2">
        <div className="mb-1 text-xs font-semibold text-slate-300">{zh ? '医生良恶性判断' : 'Physician nature judgment'}</div>
        <div className="grid grid-cols-2 gap-1.5">
          {(['benign', 'malignant'] as const).map((value) => (
            <button
              key={value}
              type="button"
              onClick={() => patch({
                nature: fields.nature === value ? '' : value,
                impression_consider: value === 'benign' ? (zh ? '良性病变' : 'benign lesion') : (zh ? '恶性病变' : 'malignant lesion'),
              })}
              className={`rounded border px-2 py-2 text-sm ${
                fields.nature === value
                  ? 'border-orange-400/60 bg-orange-500/15 text-orange-100'
                  : 'border-white/10 text-gray-400 hover:bg-white/5'
              }`}
            >
              {value === 'benign' ? (zh ? '良性' : 'Benign') : (zh ? '恶性' : 'Malignant')}
            </button>
          ))}
        </div>
      </div>

      <div>
        <div className="mb-1 text-xs font-semibold text-slate-300">{zh ? '超声提示' : 'Ultrasound impression'}</div>
        <div className="space-y-1.5">
          <TextField value={fields.impression_site} onChange={(value) => patch({ impression_site: value })} placeholder={zh ? '部位' : 'Site'} wide />
          <TextField value={fields.impression_wall} onChange={(value) => patch({ impression_wall: value })} placeholder={zh ? '胃壁表现' : 'Wall finding'} wide />
          <TextField value={fields.impression_consider} onChange={(value) => patch({ impression_consider: value })} placeholder={zh ? '考虑……' : 'Consider…'} wide />
        </div>
      </div>
    </section>
  );
}
