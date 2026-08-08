'use client';

import React, { useEffect, useMemo, useState } from 'react';
import {
  AlertTriangle,
  CheckCircle2,
  FileDown,
  FileText,
  Image as ImageIcon,
  Printer,
  RotateCcw,
  Save,
  ShieldCheck,
} from 'lucide-react';
import type { AgentAnalysisResponse, Patient } from '@/types';
import {
  applyGcUsDoctorOverride,
  buildGcUsFindingSentence,
  buildGcUsTemplateImpression,
  buildGcUsTemplateReport,
  GC_US_REPORT_SOURCE_DOC,
  GC_US_TEMPLATE_FIELD_DEFINITIONS,
  GC_US_TEMPLATE_SELECT_OPTIONS,
  GC_US_WALL_LAYER_SPECS,
  syncSignsFromTemplateFields,
  validateGcUsReportForFinalize,
  type GcUsDoctorAction,
  type GcUsField,
  type GcUsReportImage,
  type GcUsReportState,
  type GcUsReportValidationResult,
  type GcUsTemplateFieldId,
} from '@/lib/gc-us-report-template';
import { exportTemplateReportToPDF } from '@/lib/template-report-export';

type Props = {
  patient: Patient;
  state: GcUsReportState;
  analysis?: AgentAnalysisResponse | null;
  extraImages?: GcUsReportImage[];
  zh?: boolean;
  onChange: (state: GcUsReportState) => void;
};

type SaveAction = 'save_draft' | 'review' | 'finalize';

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown>
    : null;
}

function auditId(prefix: string, fieldId = 'report'): string {
  const nonce = typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function'
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  return `${prefix}:${fieldId}:${nonce}`;
}

function fieldValue(state: GcUsReportState, id: GcUsTemplateFieldId): string {
  const value = state.template_fields[id]?.value;
  return value == null ? '' : String(value);
}

function hasFilledValue(value: unknown): boolean {
  return value != null && String(value).trim() !== '';
}

function filledText(value: unknown): string {
  return hasFilledValue(value) ? String(value).trim() : '';
}

function stageToken(value: unknown, prefix: 'uT' | 'N' | 'M'): string {
  const text = filledText(value);
  if (!text) return '';
  if (prefix === 'uT') return text.replace(/^u?T?/i, '');
  if (prefix === 'N') return text.replace(/^N/i, '');
  return text.replace(/^M/i, '');
}

function siteMatchesOption(selected: string, option: string): boolean {
  if (!selected) return false;
  if (selected === option) return true;
  if (option === '胃体' && selected.startsWith('胃体')) return true;
  if (option === '胃窦' && selected.startsWith('胃窦')) return true;
  return false;
}

function wallAspectSelected(selected: string, aspect: '大弯' | '小弯' | '前壁' | '后壁'): boolean {
  return selected.includes(`（${aspect}）`) || selected.endsWith(aspect);
}

function defaultImages(
  patient: Patient,
  analysis?: AgentAnalysisResponse | null,
  extraImages: GcUsReportImage[] = [],
): GcUsReportImage[] {
  const artifacts = asRecord(analysis?.prediction_artifacts);
  const candidates: Array<GcUsReportImage | null> = [
    ...extraImages,
    patient.image_url
      ? { id: 'original', label: '原始超声图像', url: patient.image_url, kind: 'original', selected: true }
      : null,
    patient.overlay_url
      ? { id: 'overlay', label: '病灶分割叠加图', url: patient.overlay_url, kind: 'overlay', selected: true }
      : null,
    patient.roi_url
      ? { id: 'roi', label: '病灶 ROI', url: patient.roi_url, kind: 'roi', selected: true }
      : null,
    typeof artifacts?.real_wall_analysis_panel_url === 'string'
      ? {
          id: 'wall-analysis',
          label: '胃壁层次辅助图',
          url: artifacts.real_wall_analysis_panel_url,
          kind: 'wall',
          selected: true,
        }
      : null,
    typeof artifacts?.gc_us_sign_panel_url === 'string'
      ? {
          id: 'gc-us-signs',
          label: '核心征象辅助图',
          url: artifacts.gc_us_sign_panel_url,
          kind: 'evidence',
          selected: true,
        }
      : null,
  ];
  const seen = new Set<string>();
  return candidates.filter((item): item is GcUsReportImage => {
    if (!item || seen.has(item.id)) return false;
    seen.add(item.id);
    return true;
  });
}

function persistLocalState(state: GcUsReportState) {
  if (typeof window === 'undefined' || !state.case_id) return;
  try {
    const storageKey = `next-gc-us-report:${state.case_id}`;
    window.localStorage.setItem(storageKey, JSON.stringify(state));
    window.localStorage.setItem(`${storageKey}:updated_at`, String(Date.now()));
    window.dispatchEvent(new CustomEvent('gastric:template-report-updated', { detail: state }));
  } catch {
    // Browser storage is optional.
  }
}

function updateField(
  state: GcUsReportState,
  id: GcUsTemplateFieldId,
  rawValue: string,
): GcUsReportState {
  const previous = state.template_fields[id] as GcUsField<unknown>;
  const isNumber = id === 'maximum_diameter_cm' || id === 'maximum_thickness_cm';
  const value = isNumber
    ? (rawValue.trim() === '' ? null : Number(rawValue))
    : (rawValue.trim() === '' ? null : rawValue);
  if (isNumber && value !== null && !Number.isFinite(value)) return state;

  const nextField = {
    ...applyGcUsDoctorOverride(previous, value),
    ...(isNumber ? { unit: 'cm' as const } : {}),
  } as GcUsField<unknown>;
  const action: GcUsDoctorAction = {
    action_id: auditId('template-field-edit', id),
    action_type: 'template_field_edit',
    field_id: id,
    suggestion_id: previous.evidence_ref?.[0] || null,
    before_value: previous.value,
    after_value: value,
    reason: '医生修改胃充盈超声报告模板字段。',
    evidence_ids: previous.evidence_ref || [],
    source_refs: [`case:${state.case_id || 'unknown'}`, `template_field:${id}`],
    frame_id_or_time: state.frame_id || state.frame_time || null,
    actor_id: state.report.signed_by,
    software_version: 'next-gastric-template-report-v1',
    model_version: null,
    rule_version: state.schema_version,
    created_at: new Date().toISOString(),
  };
  const nextTemplateFields = {
    ...state.template_fields,
    [id]: nextField,
  };
  return buildGcUsTemplateReport({
    ...state,
    signs: syncSignsFromTemplateFields(state.signs, nextTemplateFields),
    template_fields: nextTemplateFields,
    report: {
      ...state.report,
      source: 'doctor',
      doctor_edited: true,
      status: state.report.status === 'finalized' || state.report.status === 'reviewed'
        ? 'draft'
        : state.report.status,
      signed_at: state.report.status === 'finalized' || state.report.status === 'reviewed'
        ? null
        : state.report.signed_at,
    },
    doctor_actions: [...state.doctor_actions, action],
  });
}

function updateSignedBy(state: GcUsReportState, signedBy: string): GcUsReportState {
  const changed = (state.report.signed_by || '') !== signedBy;
  if (!changed) return state;
  const action: GcUsDoctorAction = {
    action_id: auditId('template-field-edit', 'signed_by'),
    action_type: 'template_field_edit',
    field_id: 'signed_by',
    suggestion_id: null,
    before_value: state.report.signed_by,
    after_value: signedBy || null,
    reason: '医生修改签发信息。',
    evidence_ids: [],
    source_refs: [`case:${state.case_id || 'unknown'}`, 'report_field:signed_by'],
    frame_id_or_time: state.frame_id || state.frame_time || null,
    actor_id: signedBy || state.report.signed_by,
    software_version: 'next-gastric-template-report-v1',
    model_version: null,
    rule_version: state.schema_version,
    created_at: new Date().toISOString(),
  };
  return {
    ...state,
    report: {
      ...state.report,
      signed_by: signedBy || null,
      source: signedBy ? 'doctor' : state.report.source,
      doctor_edited: signedBy ? true : state.report.doctor_edited,
      status: state.report.status === 'finalized' || state.report.status === 'reviewed'
        ? 'draft'
        : state.report.status,
      signed_at: state.report.status === 'finalized' || state.report.status === 'reviewed'
        ? null
        : state.report.signed_at,
    },
    doctor_actions: [...state.doctor_actions, action],
  };
}

function statusLabel(status: GcUsReportState['report']['status'], zh: boolean): string {
  if (zh) {
    return {
      draft: '草稿',
      reviewed: '已复核',
      finalized: '已签发',
    }[status];
  }
  return {
    draft: 'Draft',
    reviewed: 'Reviewed',
    finalized: 'Finalized',
  }[status];
}

export function TemplateReportPreview({
  patient,
  state,
  analysis = null,
  extraImages = [],
  previewId,
  zh = true,
}: {
  patient: Patient;
  state: GcUsReportState;
  analysis?: AgentAnalysisResponse | null;
  extraImages?: GcUsReportImage[];
  previewId: string;
  zh?: boolean;
}) {
  const images = state.report_images.length
    ? state.report_images
    : defaultImages(patient, analysis, extraImages);
  const fields = state.template_fields;
  const selectedImages = images.filter((item) => item.selected !== false);
  const clinical = patient.clinical;
  const finding = buildGcUsFindingSentence(state);
  const impression = filledText(fields.impression.value) || buildGcUsTemplateImpression(state);
  const recommendation = filledText(fields.recommendation.value)
    || '建议结合胃镜活检及其他影像学资料，必要时进行多切面复核。';
  const site = filledText(fields.lesion_site.value) || filledText(clinical?.location);
  const diameter = filledText(fields.maximum_diameter_cm.value);
  const thickness = filledText(fields.maximum_thickness_cm.value);
  const grossType = filledText(fields.gross_type.value);
  const ascites = filledText(fields.ascites.value);
  const perigastric = filledText(fields.perigastric_involvement.value);
  const lymphNodes = filledText(fields.lymph_nodes.value);
  const distantMeta = filledText(fields.distant_metastasis.value);
  const uT = stageToken(fields.ct_stage.value, 'uT');
  const n = stageToken(fields.cn_stage.value, 'N');
  const m = stageToken(fields.cm_stage.value, 'M');
  const layerOptions = ['存在', '模糊/变薄', '消失'] as const;
  const layer5Options = ['存在', '模糊/变薄', '消失', '角征'] as const;
  const wallAspects = ['大弯', '小弯', '前壁', '后壁'] as const;

  return (
    <article
      id={previewId}
      className="template-report-preview mx-auto w-full max-w-[794px] bg-white text-black shadow-2xl"
      style={{
        fontFamily: '"Times New Roman", "SimSun", "宋体", serif',
        padding: '2.54cm 3.17cm',
        fontSize: '12pt',
        lineHeight: 1.5,
      }}
    >
      <header className="text-center">
        <div className="font-bold" style={{ fontSize: '16pt', lineHeight: 1.3 }}>
          胃癌超声报告
        </div>
        <div className="mt-2 text-[10.5pt] text-neutral-700">
          {patient.id_short || patient.id}
          {patient.patient_id ? ` / ${patient.patient_id}` : ''}
          {' / '}
          {statusLabel(state.report.status, zh)}
          {state.report.signed_by ? ` / 签发：${state.report.signed_by}` : ''}
        </div>
      </header>

      <WordHeading>超声描述：</WordHeading>

      <WordParagraph>
        病灶位于［
        <ChoiceToken selected={siteMatchesOption(site, '贲门')}>贲门</ChoiceToken>
        、
        <ChoiceToken selected={siteMatchesOption(site, '胃底')}>胃底</ChoiceToken>
        、
        <ChoiceToken selected={site === '胃体' || site.startsWith('胃体（')}>胃体</ChoiceToken>
        （
        {wallAspects.map((aspect, index) => (
          <React.Fragment key={aspect}>
            {index > 0 ? '、' : null}
            <ChoiceToken selected={site.startsWith('胃体') && wallAspectSelected(site, aspect)}>
              {aspect}
            </ChoiceToken>
          </React.Fragment>
        ))}
        ）、
        <ChoiceToken selected={siteMatchesOption(site, '胃角')}>胃角</ChoiceToken>
        、
        <ChoiceToken selected={site === '胃窦' || site.startsWith('胃窦（')}>胃窦</ChoiceToken>
        （
        {wallAspects.map((aspect, index) => (
          <React.Fragment key={`antrum-${aspect}`}>
            {index > 0 ? '、' : null}
            <ChoiceToken selected={site.startsWith('胃窦') && wallAspectSelected(site, aspect)}>
              {aspect}
            </ChoiceToken>
          </React.Fragment>
        ))}
        ）、
        <ChoiceToken selected={siteMatchesOption(site, '幽门')}>幽门</ChoiceToken>
        ］；
      </WordParagraph>

      <WordParagraph>
        最大径 <UnderlineBlank value={diameter} width="4.5em" /> cm，最厚径{' '}
        <UnderlineBlank value={thickness} width="4.5em" /> cm；
      </WordParagraph>

      <WordParagraph>
        大体分型（
        {(GC_US_TEMPLATE_SELECT_OPTIONS.gross_type || []).map((option, index) => (
          <React.Fragment key={option}>
            {index > 0 ? '、' : null}
            <ChoiceToken selected={grossType === option}>{option}</ChoiceToken>
          </React.Fragment>
        ))}
        ）
      </WordParagraph>

      <WordParagraph>
        胃壁层次结构（由内往外）［
        {GC_US_WALL_LAYER_SPECS.map((spec, layerIndex) => {
          const options = spec.id === 'layer_5_serosa' ? layer5Options : layerOptions;
          const selected = filledText(fields[spec.id].value);
          return (
            <React.Fragment key={spec.id}>
              {layerIndex > 0 ? '、' : null}
              {spec.labelZh}（
              {options.map((option, index) => (
                <React.Fragment key={`${spec.id}-${option}`}>
                  {index > 0 ? '、' : null}
                  <ChoiceToken selected={selected === option}>{option}</ChoiceToken>
                </React.Fragment>
              ))}
              ）
            </React.Fragment>
          );
        })}
        ］；
      </WordParagraph>

      {filledText(fields.wall_layer_summary.value) ? (
        <WordParagraph>
          层次总评：<UnderlineBlank value={filledText(fields.wall_layer_summary.value)} width="12em" />。
        </WordParagraph>
      ) : null}

      <WordParagraph>
        侵及胃周组织 <UnderlineBlank value={perigastric} width="10em" />；
      </WordParagraph>
      <WordParagraph>
        淋巴结（
        <UnderlineBlank value={lymphNodes || '待补充'} width="10em" />
        ）；
      </WordParagraph>
      <WordParagraph>
        远处转移（
        <UnderlineBlank value={distantMeta || '待补充'} width="10em" />
        ）；
      </WordParagraph>
      <WordParagraph>
        腹腔游离液性区（
        {(GC_US_TEMPLATE_SELECT_OPTIONS.ascites || []).map((option, index) => (
          <React.Fragment key={option}>
            {index > 0 ? '、' : null}
            <ChoiceToken selected={ascites === option}>{option}</ChoiceToken>
          </React.Fragment>
        ))}
        ）。
      </WordParagraph>

      <WordHeading>超声提示：</WordHeading>
      <WordParagraph>
        <UnderlineBlank value={site} width="6em" />
        （部位）胃壁{' '}
        <UnderlineBlank value={impression} width="18em" />
      </WordParagraph>
      <WordParagraph>
        考虑胃癌（uT
        <UnderlineBlank value={uT} width="2.2em" />
        {' '}N
        <UnderlineBlank value={n} width="2.2em" />
        {' '}M
        <UnderlineBlank value={m} width="2.2em" />
        ）
      </WordParagraph>

      <WordHeading>注：</WordHeading>
      <WordParagraph>
        形态、生长方式并入大体分型；边界并入层次结构，细化并勾选累及最深层次。
      </WordParagraph>
      <WordParagraph>
        五层解剖（由内往外）：第一层黏膜浅层，第二层黏膜肌层，第三层黏膜下层，第四层固有肌层，第五层浆膜。
      </WordParagraph>

      <WordHeading>核心影像征象体系：</WordHeading>
      <WordParagraph>
        {finding.replace(/未评估/g, '____')}
      </WordParagraph>
      <WordParagraph>
        综合超声影像征象及AI辅助分析，考虑：
        {uT ? `胃癌可能，超声评估cT${uT}期。` : '浸润深度尚需结合多切面复核。'}
      </WordParagraph>

      {recommendation ? (
        <>
          <WordHeading>检查建议：</WordHeading>
          <WordParagraph>{recommendation}</WordParagraph>
        </>
      ) : null}

      {selectedImages.length ? (
        <>
          <WordHeading>关键图像：</WordHeading>
          <div className="mt-2 grid grid-cols-2 gap-3">
            {selectedImages.map((image) => (
              <figure key={image.id} className="break-inside-avoid border border-black/20 p-1.5">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={image.url}
                  alt={image.label}
                  crossOrigin="anonymous"
                  className="h-[170px] w-full object-contain bg-white"
                />
                <figcaption className="mt-1 text-center text-[10pt] leading-5 text-neutral-700">
                  {image.caption || image.label}
                </figcaption>
              </figure>
            ))}
          </div>
        </>
      ) : null}

      <WordHeading>模板附图：</WordHeading>
      <figure className="mt-2 break-inside-avoid">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src="/report-template/wall-layers-reference.png"
          alt="T1-T4 核心影像征象对照表"
          className="w-full border border-black/10 object-contain"
        />
        <figcaption className="mt-1 text-center text-[10pt] text-neutral-700">
          模板附图 1：T1-T4 核心影像征象对照
        </figcaption>
      </figure>
      <figure className="mt-4 break-inside-avoid">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src="/report-template/staging-reference.png"
          alt="七个核心影像征象评分参考表"
          className="w-full border border-black/10 object-contain"
        />
        <figcaption className="mt-1 text-center text-[10pt] text-neutral-700">
          模板附图 2：七个核心影像征象与分期评分参考
        </figcaption>
      </figure>

      <footer className="mt-6 border-t border-black/20 pt-2 text-[9.5pt] leading-5 text-neutral-600">
        <div>说明：本报告按《{GC_US_REPORT_SOURCE_DOC}》版式生成，影像辅助结果需由医生复核后签发。</div>
        <div className="mt-1 flex justify-between gap-3">
          <span>报告编号：{state.report.report_id || '草稿未编号'}</span>
          <span>版本：v{state.report.revision || 0}</span>
        </div>
      </footer>
    </article>
  );
}

function WordHeading({ children }: { children: React.ReactNode }) {
  return (
    <h2 className="mt-4 font-bold" style={{ fontSize: '14pt', lineHeight: 1.5 }}>
      {children}
    </h2>
  );
}

function WordParagraph({ children }: { children: React.ReactNode }) {
  return (
    <p className="mt-1 text-justify" style={{ fontSize: '12pt', lineHeight: 1.5 }}>
      {children}
    </p>
  );
}

function ChoiceToken({
  selected,
  children,
}: {
  selected: boolean;
  children: React.ReactNode;
}) {
  if (selected) {
    return (
      <span
        className="mx-0.5 inline-flex items-baseline gap-0.5 rounded-sm px-1 font-bold text-black"
        style={{
          backgroundColor: '#ffe08a',
          border: '2px solid #111',
          textDecoration: 'underline',
          textDecorationThickness: '2px',
          textUnderlineOffset: '2px',
        }}
      >
        <span aria-hidden className="text-[10pt] leading-none">☑</span>
        {children}
      </span>
    );
  }
  return (
    <span style={{ color: '#6b7280' }}>
      {children}
    </span>
  );
}

function UnderlineBlank({
  value,
  width = '6em',
}: {
  value: string;
  width?: string;
}) {
  if (value) {
    return (
      <span
        className="mx-0.5 inline-block rounded-sm px-1.5 font-bold text-black"
        style={{
          minWidth: width,
          backgroundColor: '#ffe08a',
          border: '2px solid #111',
          textDecoration: 'underline',
          textDecorationThickness: '2px',
          textUnderlineOffset: '3px',
          textAlign: 'center',
        }}
      >
        {value}
      </span>
    );
  }
  return (
    <span
      className="mx-0.5 inline-block align-baseline"
      style={{
        minWidth: width,
        color: '#6b7280',
        borderBottom: '1.5px solid #666',
        lineHeight: 1.2,
        textAlign: 'center',
      }}
    >
      &nbsp;
    </span>
  );
}

export function TemplateReportEditor({
  patient,
  state,
  analysis = null,
  extraImages = [],
  zh = true,
  onChange,
}: Props) {
  const [busy, setBusy] = useState<SaveAction | null>(null);
  const [exportBusy, setExportBusy] = useState(false);
  const [message, setMessage] = useState('');
  const [signoffConfirmed, setSignoffConfirmed] = useState(false);
  const [revisionOf, setRevisionOf] = useState<number | null>(null);
  const previewId = `template-report-preview-${(state.case_id || patient.id).replace(/[^a-zA-Z0-9_-]/g, '-')}`;
  const isFinalized = state.report.status === 'finalized';
  const validation = useMemo<GcUsReportValidationResult>(
    () => validateGcUsReportForFinalize(state),
    [state],
  );
  const images = useMemo(
    () => state.report_images.length ? state.report_images : defaultImages(patient, analysis, extraImages),
    [analysis, extraImages, patient, state.report_images],
  );
  const groups = useMemo(
    () => (['basic', 'wall', 'spread', 'stage', 'text'] as const).map((group) => ({
      group,
      fields: GC_US_TEMPLATE_FIELD_DEFINITIONS.filter((item) => item.group === group),
    })),
    [],
  );

  useEffect(() => {
    setSignoffConfirmed(false);
    setRevisionOf(null);
    setMessage('');
  }, [state.case_id]);

  const emit = (next: GcUsReportState) => {
    persistLocalState(next);
    onChange(next);
  };

  const handleFieldChange = (id: GcUsTemplateFieldId, value: string) => {
    if (isFinalized) return;
    const next = updateField(state, id, value);
    if (next !== state) emit(next);
  };

  const handleImageToggle = (imageId: string) => {
    if (isFinalized) return;
    const nextImages = images.map((image) => (
      image.id === imageId ? { ...image, selected: image.selected === false } : image
    ));
    emit({ ...state, report_images: nextImages });
  };

  const restoreFieldSuggestion = (id: GcUsTemplateFieldId) => {
    if (isFinalized) return;
    const field = state.template_fields[id];
    if (field.status !== 'doctor_edited' && field.doctor_override == null) return;
    const restored = {
      ...field,
      value: field.raw_value,
      status: field.raw_value == null ? 'unevaluated' as const : 'suggested' as const,
      source: field.raw_value == null ? 'not_available' as const : 'clinical' as const,
      doctor_override: null,
    } as GcUsField<unknown>;
    const action: GcUsDoctorAction = {
      action_id: auditId('template-field-reset', id),
      action_type: 'reset',
      field_id: id,
      suggestion_id: field.evidence_ref?.[0] || null,
      before_value: field.value,
      after_value: restored.value,
      reason: '医生恢复系统建议值。',
      evidence_ids: field.evidence_ref || [],
      source_refs: [`case:${state.case_id || 'unknown'}`, `template_field:${id}`],
      frame_id_or_time: state.frame_id || state.frame_time || null,
      actor_id: state.report.signed_by,
      software_version: 'next-gastric-template-report-v1',
      model_version: null,
      rule_version: state.schema_version,
      created_at: new Date().toISOString(),
    };
    emit(buildGcUsTemplateReport({
      ...state,
      template_fields: {
        ...state.template_fields,
        [id]: restored,
      } as GcUsReportState['template_fields'],
      report: {
        ...state.report,
        status: 'draft',
        signed_at: null,
      },
      doctor_actions: [...state.doctor_actions, action],
    }));
  };

  const handleStartRevision = () => {
    if (!isFinalized) return;
    const action: GcUsDoctorAction = {
      action_id: auditId('revision-start'),
      action_type: 'revision_start',
      field_id: null,
      suggestion_id: null,
      before_value: state.report.revision,
      after_value: 'draft',
      reason: '医生开始修订已签发报告。',
      evidence_ids: [],
      source_refs: [`case:${state.case_id || 'unknown'}`, `revision:${state.report.revision}`],
      frame_id_or_time: state.frame_id || state.frame_time || null,
      actor_id: state.report.signed_by,
      software_version: 'next-gastric-template-report-v1',
      model_version: null,
      rule_version: state.schema_version,
      created_at: new Date().toISOString(),
    };
    setRevisionOf(state.report.revision);
    emit(buildGcUsTemplateReport({
      ...state,
      report: {
        ...state.report,
        status: 'draft',
        signed_at: null,
        source: 'doctor',
        doctor_edited: true,
      },
      doctor_actions: [...state.doctor_actions, action],
    }));
    setMessage(zh ? '已进入修订模式，原签发版本仍保留。' : 'Revision mode started. The signed version remains preserved.');
  };

  const handleSave = async (action: SaveAction) => {
    if (isFinalized) {
      setMessage(zh ? '已签发报告为只读，请先开始修订。' : 'The signed report is read-only. Start a revision first.');
      return;
    }
    if ((action === 'review' || action === 'finalize') && !signoffConfirmed) {
      setMessage(zh ? '请先勾选“我已完成医生复核”。' : 'Confirm that physician review is complete first.');
      return;
    }
    if (action === 'finalize') {
      const blocking = validation.issues.filter((issue) => issue.severity === 'error');
      if (blocking.length) {
        setMessage(`${zh ? '签发前仍有必填项或冲突未解决：' : 'Resolve required fields or conflicts before signing: '}${blocking.slice(0, 3).map((issue) => issue.message).join(' ')}`);
        return;
      }
    }
    if (action === 'review' && validation.issues.some((issue) => issue.severity === 'error')) {
      setMessage(zh ? '复核前请先补齐必填项并处理冲突。' : 'Complete required fields and resolve conflicts before review.');
      return;
    }
    setBusy(action);
    setMessage('');
    try {
      const current = buildGcUsTemplateReport({
        ...state,
        report_images: images,
        report: {
          ...state.report,
          status: action === 'finalize' ? 'finalized' : action === 'review' ? 'reviewed' : 'draft',
        },
      });
      const response = await fetch('/api/reports/template', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          action,
          case_id: patient.patient_id || patient.id,
          patient_id: patient.patient_id,
          patient_label: patient.id_short || patient.id,
          revision_of: revisionOf,
          report: current,
        }),
      });
      const payload = await response.json().catch(() => null) as {
        ok?: boolean;
        error?: string;
        report_id?: string;
        revision?: number;
        status?: GcUsReportState['report']['status'];
      } | null;
      if (!response.ok || !payload?.ok) throw new Error(payload?.error || '报告保存失败');
      const next: GcUsReportState = {
        ...current,
        report: {
          ...current.report,
          report_id: payload.report_id || current.report.report_id,
          revision: payload.revision ?? current.report.revision,
          status: payload.status || current.report.status,
          signed_at: action === 'finalize' ? new Date().toISOString() : current.report.signed_at,
        },
      };
      setRevisionOf(null);
      setSignoffConfirmed(false);
      emit(next);
      setMessage(action === 'finalize'
        ? (zh ? '报告已签发并保存，当前版本已锁定。' : 'Report finalized and locked.')
        : action === 'review'
          ? (zh ? '报告已标记为已复核。' : 'Report marked as reviewed.')
        : (zh ? '报告草稿已保存。' : 'Report draft saved.'));
    } catch (error) {
      setMessage(error instanceof Error ? error.message : (zh ? '报告保存失败' : 'Failed to save report'));
    } finally {
      setBusy(null);
    }
  };

  const handleReset = () => {
    if (isFinalized) return;
    const next = buildGcUsTemplateReport({
      ...state,
      template_fields: {
        ...state.template_fields,
        impression: {
          ...state.template_fields.impression,
          value: null,
          doctor_override: null,
          status: 'unevaluated',
          source: 'not_available',
        },
      },
      report: {
        ...state.report,
        source: 'template',
        doctor_edited: false,
        status: 'draft',
        signed_at: null,
      },
    });
    emit(next);
  };

  const handleExport = async () => {
    if (exportBusy) return;
    setExportBusy(true);
    setMessage('');
    try {
      await exportTemplateReportToPDF(previewId, `胃充盈超声报告_${patient.id_short || patient.id}_v${state.report.revision || 0}.pdf`);
      setMessage(zh ? 'PDF 已导出到浏览器默认下载目录。' : 'PDF exported to the browser default download directory.');
    } catch (error) {
      setMessage(error instanceof Error ? error.message : (zh ? 'PDF 导出失败' : 'PDF export failed'));
    } finally {
      setExportBusy(false);
    }
  };

  return (
    <div className="space-y-4 text-[12px] text-slate-200">
      <div
        className="flex flex-wrap items-start justify-between gap-3 rounded-xl border border-cyan-300/25 p-4 backdrop-blur-md"
        style={{ backgroundColor: 'rgba(36, 48, 64, 0.9)', WebkitBackdropFilter: 'blur(10px)', backdropFilter: 'blur(10px)' }}
      >
        <div>
          <div className="flex items-center gap-2 text-sm font-bold text-cyan-100">
            <FileText size={16} />
            {zh ? '胃充盈超声报告模板' : 'Gastric filling ultrasound report template'}
          </div>
          <div className="mt-1 text-[10px] leading-relaxed text-slate-400">
            {zh
              ? '按照指定 DOCX 的基本信息、胃壁五层、转移征象、分期和印象结构填写。系统建议保留来源，医生修改后才能签发。'
              : 'Fill the DOCX-aligned lesion, five-layer, spread, staging, and impression sections. Suggestions keep provenance until physician sign-off.'}
          </div>
        </div>
        <div
          className="flex items-center gap-1.5 rounded-full border border-white/15 px-2.5 py-1 text-[10px] text-slate-200 backdrop-blur-sm"
          style={{ backgroundColor: 'rgba(26, 34, 45, 0.92)' }}
        >
          {state.report.status === 'finalized' ? <CheckCircle2 size={12} className="text-emerald-300" /> : <ShieldCheck size={12} className="text-amber-300" />}
          {statusLabel(state.report.status, zh)}
          <span className="text-slate-400">v{state.report.revision || 0}</span>
        </div>
      </div>
      {isFinalized ? (
        <div
          className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-emerald-300/25 px-3 py-2 text-[10px] text-emerald-100 backdrop-blur-sm"
          style={{ backgroundColor: 'rgba(31, 42, 36, 0.92)' }}
        >
          <span>{zh ? '已签发版本只读，修订会生成新版本并保留当前历史。' : 'Signed versions are read-only. Revisions create a new version and preserve history.'}</span>
          <button
            type="button"
            onClick={handleStartRevision}
            className="rounded-md border border-emerald-300/30 px-2.5 py-1.5 font-semibold hover:bg-emerald-300/10"
          >
            {zh ? '以此版本开始修订' : 'Start revision'}
          </button>
        </div>
      ) : null}

      <div className="grid gap-4 lg:grid-cols-2">
        <div className="space-y-3">
          {groups.map(({ group, fields }) => (
            <section key={group} className="rounded-xl border border-white/12 p-3" style={{ backgroundColor: 'rgba(34, 42, 53, 0.88)', WebkitBackdropFilter: 'blur(10px)', backdropFilter: 'blur(10px)' }}>
              <div className="mb-2 text-[11px] font-semibold text-slate-200">
                {{
                  basic: '超声描述, 基本信息',
                  wall: '超声描述, 胃壁层次及胃周组织',
                  spread: '超声描述, 转移及伴随征象',
                  stage: '超声提示, 分期记录',
                  text: '超声提示, 印象和建议',
                }[group]}
              </div>
              <div className="space-y-2">
                {fields.map((definition) => {
                  const value = fieldValue(state, definition.id);
                  const options = GC_US_TEMPLATE_SELECT_OPTIONS[definition.id] || [];
                  return (
                    <label key={definition.id} className="block text-[10px] text-slate-400">
                      <span>{definition.label}</span>
                      {definition.kind === 'textarea' ? (
                        <textarea
                          value={value}
                          onChange={(event) => handleFieldChange(definition.id, event.target.value)}
                          disabled={isFinalized}
                          className="mt-1 min-h-16 w-full rounded-lg border border-white/10 px-2.5 py-2 text-[11px] leading-relaxed text-slate-100 outline-none focus:border-cyan-300/50" style={{ backgroundColor: 'rgba(26, 34, 45, 0.9)' }}
                          placeholder={zh ? '未填写' : 'Not filled'}
                        />
                      ) : definition.kind === 'number' ? (
                        <div className="mt-1 flex items-center gap-1.5">
                          <input
                            type="number"
                            step="0.1"
                            value={value}
                            onChange={(event) => handleFieldChange(definition.id, event.target.value)}
                            disabled={isFinalized}
                            className="min-w-0 flex-1 rounded-lg border border-white/10 px-2.5 py-2 font-mono text-[11px] text-slate-100 outline-none focus:border-cyan-300/50" style={{ backgroundColor: 'rgba(26, 34, 45, 0.9)' }}
                            placeholder="未评估"
                          />
                          <span className="rounded-lg border border-white/10 px-2 py-2 font-mono text-[10px] text-slate-500">cm</span>
                        </div>
                      ) : (
                        <select
                          value={value}
                          onChange={(event) => handleFieldChange(definition.id, event.target.value)}
                          disabled={isFinalized}
                          className="mt-1 w-full rounded-lg border border-white/10 px-2.5 py-2 text-[11px] text-slate-100 outline-none focus:border-cyan-300/50" style={{ backgroundColor: 'rgba(26, 34, 45, 0.9)' }}
                        >
                          <option value="">未评估</option>
                          {options.map((option) => <option key={option} value={option}>{option}</option>)}
                          {value && !options.includes(value) ? <option value={value}>{value}</option> : null}
                        </select>
                      )}
                      <span className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[9px] text-slate-600">
                        <span>
                          {state.template_fields[definition.id].status === 'doctor_edited'
                            ? '医生已修改'
                            : '来源: ' + state.template_fields[definition.id].source}
                        </span>
                        {state.template_fields[definition.id].confidence != null ? (
                          <span>置信度: {Math.round((state.template_fields[definition.id].confidence || 0) * 100)}%</span>
                        ) : null}
                        {state.template_fields[definition.id].evidence_ref?.length ? (
                          <span className="max-w-full truncate" title={state.template_fields[definition.id].evidence_ref.join(', ')}>
                            依据: {state.template_fields[definition.id].evidence_ref.join(', ')}
                          </span>
                        ) : null}
                        {state.template_fields[definition.id].status === 'doctor_edited' && !isFinalized ? (
                          <button
                            type="button"
                            onClick={() => restoreFieldSuggestion(definition.id)}
                            className="inline-flex items-center gap-0.5 text-cyan-300 hover:text-cyan-100"
                          >
                            <RotateCcw size={9} />
                            恢复建议
                          </button>
                        ) : null}
                      </span>
                    </label>
                  );
                })}
              </div>
            </section>
          ))}

          <section className="rounded-xl border border-white/12 p-3" style={{ backgroundColor: 'rgba(34, 42, 53, 0.88)', WebkitBackdropFilter: 'blur(10px)', backdropFilter: 'blur(10px)' }}>
            <label className="block text-[10px] text-slate-400">
              {zh ? '签发医生' : 'Signing physician'}
              <input
                value={state.report.signed_by || ''}
                onChange={(event) => emit(updateSignedBy(state, event.target.value))}
                disabled={isFinalized}
                className="mt-1 w-full rounded-lg border border-white/10 px-2.5 py-2 text-[11px] text-slate-100 outline-none focus:border-cyan-300/50" style={{ backgroundColor: 'rgba(26, 34, 45, 0.9)' }}
                placeholder={zh ? '填写医生姓名或工号' : 'Physician name or ID'}
              />
            </label>
          </section>

          <section className="rounded-xl border border-white/12 p-3" style={{ backgroundColor: 'rgba(34, 42, 53, 0.88)', WebkitBackdropFilter: 'blur(10px)', backdropFilter: 'blur(10px)' }}>
            <div className="mb-2 flex items-center gap-1.5 text-[11px] font-semibold text-slate-200">
              <ImageIcon size={13} />
              {zh ? '报告图像' : 'Report images'}
            </div>
            <div className="space-y-1.5">
              {images.map((image) => (
                <label key={image.id} className="flex items-center gap-2 rounded-lg border border-white/10 px-2 py-1.5 text-[10px] text-slate-300" style={{ backgroundColor: 'rgba(26, 34, 45, 0.9)' }}>
                  <input
                    type="checkbox"
                    checked={image.selected !== false}
                    onChange={() => handleImageToggle(image.id)}
                    disabled={isFinalized}
                  />
                  <span className="truncate">{image.label}</span>
                </label>
              ))}
              {!images.length ? <div className="text-[10px] text-slate-500">暂无可用图像</div> : null}
            </div>
          </section>

          {!isFinalized && validation.issues.length ? (
            <section className="rounded-lg border border-amber-300/25 px-3 py-2 text-[10px]" style={{ backgroundColor: 'rgba(42, 38, 24, 0.92)', WebkitBackdropFilter: 'blur(8px)', backdropFilter: 'blur(8px)' }}>
              <div className="mb-1 flex items-center gap-1.5 font-semibold text-amber-100">
                <AlertTriangle size={12} />
                {zh ? '签发前检查' : 'Pre-signoff checks'}
              </div>
              <div className="space-y-1 text-slate-300">
                {validation.issues.slice(0, 8).map((issue) => (
                  <div key={issue.code} className={issue.severity === 'error' ? 'text-rose-200' : 'text-amber-200'}>
                    {issue.severity === 'error' ? '必填' : '提示'}: {issue.message}
                  </div>
                ))}
                {validation.issues.length > 8 ? <div className="text-slate-500">还有 {validation.issues.length - 8} 项提示。</div> : null}
              </div>
            </section>
          ) : null}

          {!isFinalized ? (
            <label className="flex items-start gap-2 rounded-lg border border-white/12 px-3 py-2 text-[10px] text-slate-300" style={{ backgroundColor: 'rgba(26, 34, 45, 0.9)' }}>
              <input
                type="checkbox"
                checked={signoffConfirmed}
                onChange={(event) => setSignoffConfirmed(event.target.checked)}
                className="mt-0.5"
              />
              <span>{zh ? '我已逐项完成医生复核，确认报告字段、证据图像和冲突提示。' : 'I completed physician review of the fields, evidence images, and conflict warnings.'}</span>
            </label>
          ) : null}

          <div className="flex flex-wrap gap-2">
            {!isFinalized ? (
              <>
                <button
                  type="button"
                  onClick={() => void handleSave('save_draft')}
                  disabled={busy !== null}
                  className="inline-flex items-center gap-1.5 rounded-lg border border-cyan-300/30 bg-cyan-300/10 px-3 py-2 text-[11px] text-cyan-100 hover:bg-cyan-300/20 disabled:opacity-50"
                >
                  <Save size={13} />
                  {busy === 'save_draft' ? '保存中' : '保存草稿'}
                </button>
                <button
                  type="button"
                  onClick={() => void handleSave('review')}
                  disabled={busy !== null || !signoffConfirmed}
                  className="inline-flex items-center gap-1.5 rounded-lg border border-violet-300/30 bg-violet-300/10 px-3 py-2 text-[11px] text-violet-100 hover:bg-violet-300/20 disabled:opacity-50"
                >
                  <CheckCircle2 size={13} />
                  {busy === 'review' ? '复核中' : '标记已复核'}
                </button>
                <button
                  type="button"
                  onClick={() => void handleSave('finalize')}
                  disabled={busy !== null || !signoffConfirmed}
                  className="inline-flex items-center gap-1.5 rounded-lg border border-emerald-300/30 bg-emerald-300/10 px-3 py-2 text-[11px] text-emerald-100 hover:bg-emerald-300/20 disabled:opacity-50"
                >
                  <ShieldCheck size={13} />
                  {busy === 'finalize' ? '签发中' : '医生签发'}
                </button>
              </>
            ) : null}
            <button
              type="button"
              onClick={() => void handleExport()}
              disabled={exportBusy}
              className="inline-flex items-center gap-1.5 rounded-lg border border-amber-300/30 bg-amber-300/10 px-3 py-2 text-[11px] text-amber-100 hover:bg-amber-300/20 disabled:opacity-50"
            >
              <FileDown size={13} />
              {exportBusy ? '导出中' : '导出 PDF'}
            </button>
            <button
              type="button"
              onClick={() => window.print()}
              className="inline-flex items-center gap-1.5 rounded-lg border border-white/15 px-3 py-2 text-[11px] text-slate-300 hover:bg-white/5"
            >
              <Printer size={13} />
              打印
            </button>
            <button
              type="button"
              onClick={handleReset}
              disabled={isFinalized}
              className="rounded-lg border border-white/10 px-3 py-2 text-[11px] text-slate-500 hover:bg-white/5 hover:text-slate-300"
            >
              恢复建议
            </button>
          </div>
          {message ? <div className="rounded-lg border border-amber-300/20 bg-amber-300/5 px-3 py-2 text-[10px] text-amber-100">{message}</div> : null}
        </div>

        <div className="min-w-0 overflow-auto rounded-xl border border-white/12 p-3" style={{ backgroundColor: 'rgba(31, 39, 51, 0.88)', WebkitBackdropFilter: 'blur(10px)', backdropFilter: 'blur(10px)' }}>
          <TemplateReportPreview
            patient={patient}
            state={state}
            analysis={analysis}
            extraImages={extraImages}
            previewId={previewId}
            zh={zh}
          />
        </div>
      </div>
    </div>
  );
}
