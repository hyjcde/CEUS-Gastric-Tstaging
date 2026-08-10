'use client';

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
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
  gcUsLabel,
  gcUsOptionLabel,
  gcUsWallLayerLabel,
  growthPatternFromGrossType,
  localizeGcUsFreeText,
  resolveGcUsReportLocale,
  syncSignsFromTemplateFields,
  syncWallLayerSummaryFromTicks,
  validateGcUsReportForFinalize,
  type GcUsDoctorAction,
  type GcUsField,
  type GcUsExportMethod,
  type GcUsReportImage,
  type GcUsReportLocale,
  type GcUsReportState,
  type GcUsReportValidationResult,
  type GcUsTemplateFieldId,
} from '@/lib/gc-us-report-template';
import { exportTemplateReportToPDF } from '@/lib/template-report-export';
import {
  isRenderableReportImageUrl,
  preferReliableReportImages,
  sanitizeReportImages,
} from '@/lib/report-image-url';

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
  const lower = text.toLowerCase();
  // Legacy unassessed / pending values map to the default definite option (uT1 / N0 / M0).
  if (/^(u?tx|未评估|未提供|待定|undetermined)/.test(lower)) {
    return prefix === 'uT' ? '1' : '0';
  }
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
  // DINO: skip the composite 2x4 panel; use a few single-map images (green wall evidence
  // + red/blue affinity/PCA). Single maps are emitted as artifacts by the backend.
  const dinoSingles: Array<GcUsReportImage | null> = [
    typeof artifacts?.dino_wall_evidence_map_url === 'string'
      ? { id: 'dino-wall-evidence', label: 'DINO 壁层证据图', url: artifacts.dino_wall_evidence_map_url, kind: 'analysis', caption: '壁层证据热图（绿）', selected: true }
      : null,
    typeof artifacts?.dino_lesion_affinity_map_url === 'string'
      ? { id: 'dino-lesion-affinity', label: 'DINO 病灶亲和图', url: artifacts.dino_lesion_affinity_map_url, kind: 'analysis', caption: '病灶亲和热图（红蓝）', selected: true }
      : null,
    typeof artifacts?.dino_pca_map_url === 'string'
      ? { id: 'dino-pca', label: 'DINO PCA 图', url: artifacts.dino_pca_map_url, kind: 'analysis', caption: 'DINO 主成分热图（红蓝）', selected: false }
      : null,
  ];
  const candidates: Array<GcUsReportImage | null> = [
    ...extraImages,
    patient.image_url
      ? { id: 'original', label: '原始超声图像', url: patient.image_url, kind: 'original', selected: true }
      : null,
    // Real wall evidence is the lumen-relative signed-distance overlay from WallEvidenceTool.
    // The old composed fallback panel was not a true wall-layer figure; require the live tool.
    artifacts?.real_wall_analysis_panel_source === 'live_lumen_signed_distance'
      && typeof artifacts?.real_wall_analysis_panel_url === 'string'
      ? {
          id: 'wall-analysis',
          label: '胃壁层次辅助图（实时腔距）',
          url: artifacts.real_wall_analysis_panel_url,
          kind: 'wall',
          caption: '基于胃腔有符号距离的壁层证据叠加图',
          selected: true,
        }
      : (typeof artifacts?.wall_penetration_heatmap_url === 'string'
        ? {
            id: 'wall-analysis',
            label: '胃壁壁层证据热图',
            url: artifacts.wall_penetration_heatmap_url,
            kind: 'wall',
            caption: '壁层穿透风险热图（代理，需复核）',
            selected: true,
          }
        : null),
    typeof artifacts?.gc_us_sign_panel_url === 'string'
      ? {
          id: 'gc-us-signs',
          label: '核心征象辅助图',
          url: artifacts.gc_us_sign_panel_url,
          kind: 'evidence',
          selected: true,
        }
      : null,
    ...dinoSingles,
  ];
  return sanitizeReportImages(
    candidates.filter((item): item is GcUsReportImage => Boolean(item && item.id && isRenderableReportImageUrl(item.url))),
  );
}

function resolveReportImages(
  stateImages: GcUsReportImage[],
  patient: Patient,
  analysis: AgentAnalysisResponse | null | undefined,
  extraImages: GcUsReportImage[],
): GcUsReportImage[] {
  const candidates = [
    ...extraImages,
    ...stateImages.filter((image) => !(
      image.id === 'overlay'
      || image.id === 'roi'
      || image.id === 'wall-analysis'
      || image.id === 'gc-us-signs'
    )),
    ...defaultImages(patient, analysis, []),
  ];
  const seen = new Map<string, GcUsReportImage>();
  for (const image of sanitizeReportImages(candidates)) {
    seen.set(image.id, image);
  }
  return preferReliableReportImages([...seen.values()]);
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

type AutoSaveStatus = 'idle' | 'waiting' | 'saving' | 'saved' | 'error';

function reportAutosaveSignature(
  state: GcUsReportState,
  images: GcUsReportImage[],
): string {
  return JSON.stringify({
    case_id: state.case_id,
    frame_id: state.frame_id,
    frame_time: state.frame_time,
    signs: state.signs,
    template_fields: state.template_fields,
    report_images: images.map((image) => ({
      id: image.id,
      url: image.url,
      label: image.label,
      kind: image.kind,
      caption: image.caption,
      selected: image.selected !== false,
    })),
    report: {
      prose: state.report.prose,
      source: state.report.source,
      doctor_edited: state.report.doctor_edited,
      signed_by: state.report.signed_by,
      export_method: state.report.export_method,
    },
  });
}

function updateField(
  state: GcUsReportState,
  id: GcUsTemplateFieldId,
  rawValue: string,
  locale: GcUsReportLocale = 'zh',
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
    reason: locale === 'en' ? 'Physician edited GC-US report template field.' : '医生修改胃充盈超声报告模板字段。',
    evidence_ids: previous.evidence_ref || [],
    source_refs: [`case:${state.case_id || 'unknown'}`, `template_field:${id}`],
    frame_id_or_time: state.frame_id || state.frame_time || null,
    actor_id: state.report.signed_by,
    software_version: 'next-gastric-template-report-v1',
    model_version: null,
    rule_version: state.schema_version,
    created_at: new Date().toISOString(),
  };
  let nextTemplateFields = {
    ...state.template_fields,
    [id]: nextField,
  };
  // Layer / perigastric ticks own wall_layer_summary so five-layer UI and summary stay aligned.
  if (
    id === 'layer_1_mucosa'
    || id === 'layer_2_submucosa'
    || id === 'layer_3_muscularis'
    || id === 'layer_4_subserosa'
    || id === 'layer_5_serosa'
    || id === 'perigastric_involvement'
  ) {
    nextTemplateFields = syncWallLayerSummaryFromTicks(nextTemplateFields);
  }
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
  }, locale);
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
  const images = resolveReportImages(state.report_images, patient, analysis, extraImages);
  const fields = state.template_fields;
  const selectedImages = images.filter((item) => item.selected !== false);
  const clinical = patient.clinical;
  const locale = resolveGcUsReportLocale(zh);
  const finding = buildGcUsFindingSentence(state, locale);
  const storedImpression = filledText(fields.impression.value);
  const impression = (locale === 'en' && /[\u4e00-\u9fff]/.test(storedImpression))
    ? buildGcUsTemplateImpression(state, locale)
    : (storedImpression || buildGcUsTemplateImpression(state, locale));
  const recommendation = localizeGcUsFreeText(
    filledText(fields.recommendation.value),
    locale,
    '建议结合胃镜活检及其他影像学资料，必要时进行多切面复核。',
    'Correlate with endoscopic biopsy and other imaging; multi-plane review when needed.',
  );
  const site = filledText(fields.lesion_site.value) || filledText(clinical?.location) || '胃体';
  const diameter = filledText(fields.maximum_diameter_cm.value);
  const thickness = filledText(fields.maximum_thickness_cm.value);
  const grossType = filledText(fields.gross_type.value);
  const growthPattern = filledText(state.signs.growth_pattern.value)
    || growthPatternFromGrossType(grossType)
    || (zh ? '待复核' : 'Locally infiltrative (pending review)');
  const ascites = filledText(fields.ascites.value);
  const perigastric = filledText(fields.perigastric_involvement.value);
  const lymphNodes = filledText(fields.lymph_nodes.value);
  const distantMeta = filledText(fields.distant_metastasis.value);
  const uT = stageToken(fields.ct_stage.value, 'uT');
  const n = stageToken(fields.cn_stage.value, 'N');
  const m = stageToken(fields.cm_stage.value, 'M');
  const uTOptions = GC_US_TEMPLATE_SELECT_OPTIONS.ct_stage || [];
  const nOptions = GC_US_TEMPLATE_SELECT_OPTIONS.cn_stage || [];
  const mOptions = GC_US_TEMPLATE_SELECT_OPTIONS.cm_stage || [];
  const layerOptions = ['存在', '模糊/变薄', '消失'] as const;
  const layer5Options = ['存在', '模糊/变薄', '消失', '角征'] as const;
  const wallAspects = ['大弯', '小弯', '前壁', '后壁'] as const;
  const sep = zh ? '、' : ', ';

  return (
    <article
      id={previewId}
      className="template-report-preview mx-auto w-full max-w-[794px] bg-white text-black shadow-2xl"
      style={{
        fontFamily: '"Times New Roman", "SimSun", "宋体", serif',
        padding: '2.54cm 3.17cm',
        fontSize: '13pt',
        lineHeight: 1.55,
      }}
    >
      <header className="text-center">
        <div className="font-bold" style={{ fontSize: '16pt', lineHeight: 1.3 }}>
          {zh ? '胃癌超声报告' : 'Gastric Cancer Ultrasound Report'}
        </div>
        <div className="mt-2 text-[10.5pt] text-neutral-700">
          {patient.id_short || patient.id}
          {patient.patient_id ? ` / ${patient.patient_id}` : ''}
          {' / '}
          {statusLabel(state.report.status, zh)}
          {state.report.signed_by ? ` / ${zh ? '签发：' : 'Signed by: '}${state.report.signed_by}` : ''}
        </div>
      </header>

      <WordHeading>{zh ? '超声描述：' : 'Ultrasound description:'}</WordHeading>

      <WordParagraph>
        {zh ? '病灶位于［' : 'Lesion site ['}
        <ChoiceToken selected={siteMatchesOption(site, '贲门')}>{gcUsOptionLabel('贲门', zh)}</ChoiceToken>
        {sep}
        <ChoiceToken selected={siteMatchesOption(site, '胃底')}>{gcUsOptionLabel('胃底', zh)}</ChoiceToken>
        {sep}
        <ChoiceToken selected={site === '胃体' || site.startsWith('胃体（')}>{gcUsOptionLabel('胃体', zh)}</ChoiceToken>
        {' ('}
        {wallAspects.map((aspect, index) => (
          <React.Fragment key={aspect}>
            {index > 0 ? sep : null}
            <ChoiceToken selected={site.startsWith('胃体') && wallAspectSelected(site, aspect)}>
              {gcUsOptionLabel(aspect, zh)}
            </ChoiceToken>
          </React.Fragment>
        ))}
        {')'}{sep}
        <ChoiceToken selected={siteMatchesOption(site, '胃角')}>{gcUsOptionLabel('胃角', zh)}</ChoiceToken>
        {sep}
        <ChoiceToken selected={site === '胃窦' || site.startsWith('胃窦（')}>{gcUsOptionLabel('胃窦', zh)}</ChoiceToken>
        {' ('}
        {wallAspects.map((aspect, index) => (
          <React.Fragment key={`antrum-${aspect}`}>
            {index > 0 ? sep : null}
            <ChoiceToken selected={site.startsWith('胃窦') && wallAspectSelected(site, aspect)}>
              {gcUsOptionLabel(aspect, zh)}
            </ChoiceToken>
          </React.Fragment>
        ))}
        {')'}{sep}
        <ChoiceToken selected={siteMatchesOption(site, '幽门')}>{gcUsOptionLabel('幽门', zh)}</ChoiceToken>
        {zh ? '］；' : '];'}
      </WordParagraph>

      <WordParagraph>
        {zh ? '最大径 ' : 'Max diameter '}
        <UnderlineBlank value={diameter} width="4.5em" /> cm
        {zh ? '，最厚径 ' : ', max thickness '}
        <UnderlineBlank value={thickness} width="4.5em" /> cm;
      </WordParagraph>

      <WordParagraph>
        {zh ? '大体分型（' : 'Gross type ('}
        {(GC_US_TEMPLATE_SELECT_OPTIONS.gross_type || []).map((option, index) => (
          <React.Fragment key={option}>
            {index > 0 ? sep : null}
            <ChoiceToken selected={grossType === option}>{gcUsOptionLabel(option, zh)}</ChoiceToken>
          </React.Fragment>
        ))}
        )
      </WordParagraph>
      <WordParagraph>
        {zh ? '生长方式 ' : 'Growth pattern '}
        <UnderlineBlank
          value={growthPattern === '未评估' || growthPattern === 'not assessed'
            ? (zh ? '待复核' : 'Locally infiltrative (pending review)')
            : gcUsOptionLabel(growthPattern, zh)}
          width="10em"
        />;
      </WordParagraph>

      <WordParagraph>
        {zh ? '胃壁层次结构（由内往外）［' : 'Wall layers (inner to outer) ['}
        {GC_US_WALL_LAYER_SPECS.map((spec, layerIndex) => {
          const options = spec.id === 'layer_5_serosa' ? layer5Options : layerOptions;
          const selected = filledText(fields[spec.id].value);
          return (
            <React.Fragment key={spec.id}>
              {layerIndex > 0 ? sep : null}
              {gcUsWallLayerLabel(spec, zh)} (
              {options.map((option, index) => (
                <React.Fragment key={`${spec.id}-${option}`}>
                  {index > 0 ? sep : null}
                  <ChoiceToken selected={selected === option}>{gcUsOptionLabel(option, zh)}</ChoiceToken>
                </React.Fragment>
              ))}
              )
            </React.Fragment>
          );
        })}
        {zh ? '］；' : '];'}
      </WordParagraph>

      {filledText(fields.wall_layer_summary.value) ? (
        <WordParagraph>
          {zh ? '层次总评：' : 'Layer summary: '}
          <UnderlineBlank value={gcUsOptionLabel(filledText(fields.wall_layer_summary.value), zh)} width="12em" />.
        </WordParagraph>
      ) : null}

      <WordParagraph>
        {zh ? '侵及胃周组织 ' : 'Perigastric involvement '}
        <UnderlineBlank
          value={localizeGcUsFreeText(
            perigastric,
            locale,
            '____',
            'No definite perigastric invasion identified',
          )}
          width="10em"
        />;
      </WordParagraph>
      <WordParagraph>
        {zh ? '淋巴结（' : 'Lymph nodes ('}
        <UnderlineBlank
          value={localizeGcUsFreeText(
            lymphNodes,
            locale,
            '待补充',
            'To be completed with additional imaging',
          )}
          width="10em"
        />
        );
      </WordParagraph>
      <WordParagraph>
        {zh ? '远处转移（' : 'Distant metastasis ('}
        <UnderlineBlank
          value={localizeGcUsFreeText(
            distantMeta,
            locale,
            '待补充',
            'To be completed by staging examinations',
          )}
          width="10em"
        />
        );
      </WordParagraph>
      <WordParagraph>
        {zh ? '腹腔游离液性区（' : 'Ascites / free fluid ('}
        {(GC_US_TEMPLATE_SELECT_OPTIONS.ascites || []).map((option, index) => (
          <React.Fragment key={option}>
            {index > 0 ? sep : null}
            <ChoiceToken selected={ascites === option}>{gcUsOptionLabel(option, zh)}</ChoiceToken>
          </React.Fragment>
        ))}
        ).
      </WordParagraph>

      <WordHeading>{zh ? '超声提示：' : 'Ultrasound impression:'}</WordHeading>
      <WordParagraph>
        <UnderlineBlank value={gcUsOptionLabel(site || '', zh)} width="6em" />
        {zh ? '（部位）胃壁 ' : ' (site) gastric wall '}
        <UnderlineBlank value={impression} width="18em" />
      </WordParagraph>
      <WordParagraph>
        {zh ? '考虑胃癌（uT［' : 'Consider gastric cancer (uT ['}
        {uTOptions.map((option, index) => (
          <React.Fragment key={`ut-${option}`}>
            {index > 0 ? sep : null}
            <ChoiceToken selected={uT === stageToken(option, 'uT')}>{gcUsOptionLabel(option, zh)}</ChoiceToken>
          </React.Fragment>
        ))}
        {zh ? '］' : ']'}
        {zh ? ' N［' : ' N ['}
        {nOptions.map((option, index) => (
          <React.Fragment key={`cn-${option}`}>
            {index > 0 ? sep : null}
            <ChoiceToken selected={n === stageToken(option, 'N')}>{gcUsOptionLabel(option, zh)}</ChoiceToken>
          </React.Fragment>
        ))}
        {zh ? '］' : ']'}
        {zh ? ' M［' : ' M ['}
        {mOptions.map((option, index) => (
          <React.Fragment key={`cm-${option}`}>
            {index > 0 ? sep : null}
            <ChoiceToken selected={m === stageToken(option, 'M')}>{gcUsOptionLabel(option, zh)}</ChoiceToken>
          </React.Fragment>
        ))}
        {zh ? '］' : ']'}
        )
      </WordParagraph>

      <WordHeading>{zh ? '注：' : 'Notes:'}</WordHeading>
      <WordParagraph>
        {zh
          ? '形态、生长方式并入大体分型；边界并入层次结构，细化并勾选累及最深层次。'
          : 'Morphology and growth are folded into gross type; boundary is folded into wall layers. Select the deepest involved layer.'}
      </WordParagraph>
      <WordParagraph>
        {zh
          ? '突破胃壁分析的关键区为病灶与胃腔壁的接触带；重叠填色仅作定位辅助，不能单独作为突破依据。'
          : 'Breakthrough analysis focuses on the lesion-lumen contact band; overlap wash is localization only and not standalone evidence of breakthrough.'}
      </WordParagraph>
      <WordParagraph>
        {zh
          ? '五层解剖（由内往外）：第一层黏膜浅层，第二层黏膜肌层，第三层黏膜下层，第四层固有肌层，第五层浆膜。'
          : 'Five-layer anatomy (inner to outer): mucosa, muscularis mucosae, submucosa, muscularis propria, serosa.'}
      </WordParagraph>

      {(() => {
        const pack = analysis?.report?.report_pack;
        const contour = analysis?.report?.contour_diagnosis;
        const boundary = pack?.charts?.boundary_geometry || [];
        const wall = pack?.charts?.wall_geometry || [];
        const signsRoot = (analysis?.tool_evidence?.gc_us_signs || {}) as Record<string, unknown>;
        const signsMap = ((signsRoot.signs as Record<string, unknown> | undefined) || signsRoot) as Record<string, unknown>;
        const findSign = (id: string) => {
          const field = signsMap[id] as { value?: unknown } | undefined;
          if (field && field.value != null && String(field.value).trim()) return String(field.value);
          const items = Array.isArray(signsRoot.items) ? signsRoot.items as Array<Record<string, unknown>> : [];
          const item = items.find((entry) => String(entry.id || entry.name) === id);
          const value = item?.value ?? item?.status ?? item?.label;
          return value != null && String(value).trim() ? String(value) : '';
        };
        // Pull every available sign from the live template state (imaging assist included),
        // then Agent gc_us_signs as fallback — the report must always show an assessment.
        const stateSign = (id: string) => filledText((state.signs as unknown as Record<string, { value?: unknown }>)[id]?.value);
        const boundaryText = stateSign('boundary') || findSign('boundary');
        const layerText = stateSign('layer_structure') || findSign('layer_structure');
        const serosaText = stateSign('serosa_change') || findSign('serosa_change');
        const growthText = stateSign('growth_pattern') || findSign('growth_pattern');
        const gatedStage = analysis?.report?.assist_display_stage || contour?.display_stage || 'cT1';
        const tendency = analysis?.report?.recommended_t_stage || '';
        const showTendency = tendency && !/^c?tx$/i.test(String(tendency)) && tendency !== gatedStage;
        const pixelNote = (state.signs as unknown as Record<string, { note?: string }>).boundary?.note || '';
        const wallFromSigns = layerText || serosaText
          ? (zh
            ? `壁层层次：${layerText || '显示欠清'}；浆膜：${serosaText || '连续性欠清'}`
            : `Wall layers: ${gcUsOptionLabel(layerText || '显示欠清', false)}; Serosa: ${gcUsOptionLabel(serosaText || '连续性欠清', false)}`)
          : '';
        return (
          <>
            <WordHeading>{zh ? 'AI辅助征象与壁层评估（供复核）：' : 'AI-assisted signs and wall assessment (for review):'}</WordHeading>
            <WordParagraph>
              {zh ? '分期评估' : 'Stage assessment'}：{gatedStage}
              {showTendency
                ? (zh ? `；分类器/融合倾向 ${tendency}（供参考，非最终分期）` : `; classifier/fusion tendency ${tendency} (reference only, not final)`)
                : ''}
              {zh
                ? '。当前为轮廓/几何代理证据，正式分期需医生结合多切面复核后确认。'
                : '. Current evidence is contour/geometry proxy only; the formal stage needs physician multi-plane review.'}
            </WordParagraph>
            <WordParagraph>
              {zh ? '壁层评估' : 'Wall assessment'}：{wallFromSigns || (zh ? '当前帧壁层为几何/回声代理，层次显示欠清，建议结合多切面核对。' : 'Wall layers are geometry/echo proxy on this frame; please confirm on multiple planes.')}
            </WordParagraph>
            <WordParagraph>
              {zh ? '形态/边界' : 'Morphology/boundary'}：{[
                growthText ? `${zh ? '生长方式' : 'Growth'} ${gcUsOptionLabel(growthText, zh)}` : '',
                boundaryText ? `${zh ? '边界' : 'Boundary'} ${gcUsOptionLabel(boundaryText, zh)}` : '',
              ].filter(Boolean).join(zh ? '；' : '; ') || (zh ? '见上方大体分型与层次勾选。' : 'See gross type and layer ticks above.')}
              {pixelNote ? (zh ? `（${pixelNote}）` : ` (${pixelNote})`) : ''}
            </WordParagraph>
          </>
        );
      })()}

      <WordHeading>{zh ? '核心影像征象体系：' : 'Core imaging-sign framework:'}</WordHeading>
      <WordParagraph>
        {zh ? finding.replace(/未评估/g, '待复核') : finding}
      </WordParagraph>
      <WordParagraph>
        {zh
          ? '综合超声影像征象及AI辅助分析，考虑：'
          : 'Integrating ultrasound imaging signs and AI-assisted analysis, consider: '}
        {zh ? `胃癌可能，超声评估cT${uT || '1'}期。` : `possible gastric cancer, ultrasound assessment cT${uT || '1'}.`}
      </WordParagraph>

      {recommendation ? (
        <>
          <WordHeading>{zh ? '检查建议：' : 'Recommendations:'}</WordHeading>
          <WordParagraph>{recommendation}</WordParagraph>
        </>
      ) : null}

      <ReportPreviewImageSection images={selectedImages} zh={zh} />

      <footer className="mt-6 border-t border-black/20 pt-2 text-[10pt] leading-5 text-neutral-600">
        <div>
          {zh
            ? `说明：本报告按《${GC_US_REPORT_SOURCE_DOC}》版式生成，关键图像均应来自当前病例分割/关键帧/分析结果，影像辅助结果需由医生复核后签发。`
            : `Note: Generated from the ${GC_US_REPORT_SOURCE_DOC} layout. Key images must come from the current-case segmentation/key-frame/analysis outputs. Imaging assists require physician review before sign-off.`}
        </div>
        <div className="mt-1 flex justify-between gap-3">
          <span>{zh ? '报告编号：' : 'Report ID: '}{state.report.report_id || (zh ? '草稿未编号' : 'Draft untitled')}</span>
          <span>{zh ? '版本：' : 'Version: '}v{state.report.revision || 0}</span>
        </div>
      </footer>
    </article>
  );
}

function ReportPreviewImageSection({
  images,
  zh = true,
}: {
  images: GcUsReportImage[];
  zh?: boolean;
}) {
  const [failedIds, setFailedIds] = React.useState<Set<string>>(() => new Set());
  const visible = images.filter((image) => image.selected !== false && !failedIds.has(image.id));
  if (!images.length) {
    return (
      <>
        <WordHeading>{zh ? '关键图像：' : 'Key images:'}</WordHeading>
        <WordParagraph>
          {zh
            ? '当前无可显示图像。请先确认病灶与胃腔轮廓，或等待分割证据图生成后再预览。'
            : 'No displayable images yet. Confirm lesion and lumen contours, or wait for segmentation evidence images.'}
        </WordParagraph>
      </>
    );
  }
  if (!visible.length) {
    return (
      <>
        <WordHeading>{zh ? '关键图像：' : 'Key images:'}</WordHeading>
        <WordParagraph>
          {zh
            ? '已选图像暂不可加载。请改选当前帧分割叠加图，或重新运行辅助意见生成壁层证据图。'
            : 'Selected images failed to load. Prefer current-frame segmentation overlays, or re-run Assist for wall evidence panels.'}
        </WordParagraph>
      </>
    );
  }
  return (
    <>
      <WordHeading>{zh ? '关键图像：' : 'Key images:'}</WordHeading>
      <div className="mt-2 grid grid-cols-2 gap-3">
        {visible.map((image) => (
          <figure key={image.id} className="break-inside-avoid border border-black/20 p-1.5">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={image.url}
              alt={image.label}
              // Do not force anonymous CORS — that breaks same-origin cookie/auth and non-CORS remotes.
              className="h-[170px] w-full object-contain bg-white"
              onError={() => {
                setFailedIds((previous) => {
                  if (previous.has(image.id)) return previous;
                  const next = new Set(previous);
                  next.add(image.id);
                  return next;
                });
              }}
            />
            <figcaption className="mt-1 text-center text-[11pt] leading-5 text-neutral-700">
              {image.caption || image.label}
            </figcaption>
          </figure>
        ))}
      </div>
      {failedIds.size ? (
        <p className="mt-2 text-[10pt] leading-5 text-neutral-500">
          {zh
            ? `已自动隐藏 ${failedIds.size} 张无法加载的图像，避免报告出现裂图。`
            : `Hid ${failedIds.size} unloadable image(s) so the preview never shows broken figures.`}
        </p>
      ) : null}
    </>
  );
}

function WordHeading({ children }: { children: React.ReactNode }) {
  return (
    <h2 className="mt-4 font-bold" style={{ fontSize: '15pt', lineHeight: 1.5 }}>
      {children}
    </h2>
  );
}

function WordParagraph({ children }: { children: React.ReactNode }) {
  return (
    <p className="mt-1 text-justify" style={{ fontSize: '13pt', lineHeight: 1.55 }}>
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
  const locale = resolveGcUsReportLocale(zh);
  const [busy, setBusy] = useState<SaveAction | null>(null);
  const [exportBusy, setExportBusy] = useState(false);
  const [message, setMessage] = useState('');
  const [signoffConfirmed, setSignoffConfirmed] = useState(false);
  const [revisionOf, setRevisionOf] = useState<number | null>(null);
  const [autoSaveStatus, setAutoSaveStatus] = useState<AutoSaveStatus>('idle');
  const [autoSavedAt, setAutoSavedAt] = useState<string | null>(null);
  const autoSaveTimerRef = useRef<number | null>(null);
  const autoSaveInFlightRef = useRef(false);
  const autoSavedSignatureRef = useRef<string | null>(null);
  const previewId = `template-report-preview-${(state.case_id || patient.id).replace(/[^a-zA-Z0-9_-]/g, '-')}`;
  const isFinalized = state.report.status === 'finalized';
  const images = useMemo(
    () => resolveReportImages(state.report_images, patient, analysis, extraImages),
    [analysis, extraImages, patient, state.report_images],
  );
  const validation = useMemo<GcUsReportValidationResult>(
    () => validateGcUsReportForFinalize({ ...state, report_images: images }),
    [images, state],
  );
  // Boss template focus: wall layers first, then basic site/size, then spread/stage/text.
  const groups = useMemo(
    () => (['wall', 'basic', 'spread', 'stage', 'text'] as const).map((group) => ({
      group,
      fields: GC_US_TEMPLATE_FIELD_DEFINITIONS.filter((item) => item.group === group),
    })),
    [],
  );

  useEffect(() => {
    setSignoffConfirmed(false);
    setRevisionOf(null);
    setMessage('');
    autoSavedSignatureRef.current = null;
    setAutoSaveStatus('idle');
    setAutoSavedAt(null);
  }, [state.case_id]);

  const emit = useCallback((next: GcUsReportState) => {
    persistLocalState(next);
    onChange(next);
  }, [onChange]);

  const autoSaveState = useMemo(
    () => buildGcUsTemplateReport({
      ...state,
      report_images: images,
      report: {
        ...state.report,
        status: 'draft',
        signed_at: null,
      },
    }, locale),
    [images, locale, state],
  );
  const autoSaveSignature = useMemo(
    () => reportAutosaveSignature(autoSaveState, images),
    [autoSaveState, images],
  );

  useEffect(() => {
    if (!state.case_id || isFinalized || autoSaveInFlightRef.current) return undefined;
    if (autoSavedSignatureRef.current === autoSaveSignature) return undefined;
    if (autoSaveTimerRef.current !== null) {
      window.clearTimeout(autoSaveTimerRef.current);
    }
    setAutoSaveStatus('waiting');
    autoSaveTimerRef.current = window.setTimeout(async () => {
      if (autoSaveInFlightRef.current) return;
      autoSaveInFlightRef.current = true;
      setAutoSaveStatus('saving');
      try {
        const response = await fetch('/api/reports/template', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            action: 'save_draft',
            case_id: patient.patient_id || patient.id,
            patient_id: patient.patient_id,
            patient_label: patient.id_short || patient.id,
            report: autoSaveState,
          }),
        });
        const payload = await response.json().catch(() => null) as {
          ok?: boolean;
          error?: string;
          report_id?: string;
          revision?: number;
          status?: GcUsReportState['report']['status'];
        } | null;
        if (!response.ok || !payload?.ok) {
          throw new Error(payload?.error || '自动保存失败');
        }
        const saved = {
          ...autoSaveState,
          report: {
            ...autoSaveState.report,
            report_id: payload.report_id || autoSaveState.report.report_id,
            revision: payload.revision ?? autoSaveState.report.revision,
            status: payload.status || 'draft',
          },
        };
        autoSavedSignatureRef.current = autoSaveSignature;
        emit(saved);
        setAutoSavedAt(new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }));
        setAutoSaveStatus('saved');
      } catch (error) {
        setAutoSaveStatus('error');
        setMessage(error instanceof Error ? error.message : '自动保存失败');
      } finally {
        autoSaveInFlightRef.current = false;
        autoSaveTimerRef.current = null;
      }
    }, 1400);
    return () => {
      if (autoSaveTimerRef.current !== null) {
        window.clearTimeout(autoSaveTimerRef.current);
        autoSaveTimerRef.current = null;
      }
    };
  }, [
    autoSaveSignature,
    autoSaveState,
    emit,
    isFinalized,
    patient.id,
    patient.id_short,
    patient.patient_id,
    state.case_id,
  ]);

  const handleFieldChange = (id: GcUsTemplateFieldId, value: string) => {
    if (isFinalized) return;
    const next = updateField(state, id, value, locale);
    if (next !== state) emit(next);
  };

  const handleImageToggle = (imageId: string) => {
    if (isFinalized) return;
    const selectedCount = images.filter((image) => image.selected !== false).length;
    const current = images.find((image) => image.id === imageId);
    if (current?.selected !== false && selectedCount <= 1) {
      setMessage(zh ? '参考报告图像至少保留一张。' : 'Keep at least one reference report image.');
      return;
    }
    const nextImages = images.map((image) => (
      image.id === imageId ? { ...image, selected: image.selected === false } : image
    ));
    emit({ ...state, report_images: nextImages });
  };

  const handleExportMethodChange = (method: GcUsExportMethod) => {
    if (isFinalized || state.report.export_method === method) return;
    emit({
      ...state,
      report: {
        ...state.report,
        export_method: method,
      },
    });
    setMessage(
      method === 'pdf'
        ? (zh ? '已选择 PDF 文件导出。' : 'PDF file export selected.')
        : (zh ? '已选择打印预览。' : 'Print preview selected.'),
    );
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
    }, locale));
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
    }, locale));
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
      }, locale);
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
      autoSavedSignatureRef.current = reportAutosaveSignature(next, images);
      setAutoSavedAt(new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }));
      setAutoSaveStatus('saved');
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
    }, locale);
    emit(next);
  };

  const handleExport = async () => {
    if (exportBusy) return;
    if (state.report.export_method !== 'pdf') {
      setMessage(zh ? '请先选择“PDF 文件”作为导出方式。' : 'Select PDF file as the export method first.');
      return;
    }
    setExportBusy(true);
    setMessage('');
    try {
      await exportTemplateReportToPDF(
        previewId,
        zh
          ? `胃充盈超声报告_${patient.id_short || patient.id}_v${state.report.revision || 0}.pdf`
          : `gastric_us_report_${patient.id_short || patient.id}_v${state.report.revision || 0}.pdf`,
      );
      setMessage(zh ? 'PDF 已导出到浏览器默认下载目录。' : 'PDF exported to the browser default download directory.');
    } catch (error) {
      setMessage(error instanceof Error ? error.message : (zh ? 'PDF 导出失败' : 'PDF export failed'));
    } finally {
      setExportBusy(false);
    }
  };

  const handlePrint = () => {
    if (state.report.export_method !== 'print') {
      setMessage(zh ? '请先选择“打印预览”作为导出方式。' : 'Select print preview as the export method first.');
      return;
    }
    window.print();
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
        <div className="flex flex-wrap items-center justify-end gap-2">
          <div
            className="flex items-center gap-1.5 rounded-full border border-white/15 px-2.5 py-1 text-[10px] text-slate-200 backdrop-blur-sm"
            style={{ backgroundColor: 'rgba(26, 34, 45, 0.92)' }}
          >
            {state.report.status === 'finalized' ? <CheckCircle2 size={12} className="text-emerald-300" /> : <ShieldCheck size={12} className="text-amber-300" />}
            {statusLabel(state.report.status, zh)}
            <span className="text-slate-400">v{state.report.revision || 0}</span>
          </div>
          {!isFinalized ? (
            <div
              className={`flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[10px] ${
                autoSaveStatus === 'error'
                  ? 'border-rose-300/40 bg-rose-500/10 text-rose-100'
                  : autoSaveStatus === 'saving' || autoSaveStatus === 'waiting'
                    ? 'border-cyan-300/35 bg-cyan-500/10 text-cyan-100'
                    : 'border-emerald-300/30 bg-emerald-500/10 text-emerald-100'
              }`}
              title={autoSavedAt ? `最近自动保存: ${autoSavedAt}` : '报告编辑会自动保存为草稿'}
            >
              <Save size={12} className={autoSaveStatus === 'saving' ? 'animate-pulse' : undefined} />
              {autoSaveStatus === 'waiting'
                ? '待自动保存'
                : autoSaveStatus === 'saving'
                  ? '自动保存中'
                  : autoSaveStatus === 'error'
                    ? '自动保存失败'
                    : autoSavedAt
                      ? `已自动保存 ${autoSavedAt}`
                      : '自动保存已开启'}
            </div>
          ) : null}
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
            <section
              key={group}
              className={`rounded-xl border p-3 ${group === 'wall' ? 'border-emerald-300/35 ring-1 ring-emerald-300/20' : 'border-white/12'}`}
              style={{ backgroundColor: group === 'wall' ? 'rgba(16, 42, 34, 0.92)' : 'rgba(34, 42, 53, 0.88)', WebkitBackdropFilter: 'blur(10px)', backdropFilter: 'blur(10px)' }}
            >
              <div className={`mb-2 text-[11px] font-semibold ${group === 'wall' ? 'text-emerald-100' : 'text-slate-200'}`}>
                {{
                  basic: zh ? '超声描述, 基本信息' : 'US description, basic info',
                  wall: zh ? '主看点: 胃壁五层层次及胃周组织' : 'Primary: wall five-layer and perigastric',
                  spread: zh ? '超声描述, 转移及伴随征象' : 'US description, spread and associated signs',
                  stage: zh ? '超声提示, 分期记录' : 'US impression, staging',
                  text: zh ? '超声提示, 印象和建议' : 'US impression and recommendations',
                }[group]}
              </div>
              {group === 'wall' ? (
                <div className="mb-2 rounded border border-emerald-300/20 bg-black/20 px-2 py-1.5 text-[9px] leading-relaxed text-emerald-50/80">
                  {zh
                    ? '老板模板重心在壁层层次。形态并入大体分型；边界并入层次结构。请先勾选最深累及层，再核对其余字段。'
                    : 'Boss template focuses on wall layers. Morphology merges into gross type; boundary merges into layer structure. Confirm deepest involved layer first.'}
                </div>
              ) : null}
              <div className="space-y-2">
                {fields.map((definition) => {
                  const value = fieldValue(state, definition.id);
                  const options = GC_US_TEMPLATE_SELECT_OPTIONS[definition.id] || [];
                  return (
                    <label key={definition.id} className="block text-[10px] text-slate-400">
                      <span>{gcUsLabel(definition, zh)}</span>
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
                            placeholder={zh ? '未评估' : 'Not assessed'}
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
                          <option value="">{zh ? '请选择' : 'Select'}</option>
                          {options.map((option) => (
                            <option key={option} value={option}>{gcUsOptionLabel(option, zh)}</option>
                          ))}
                          {value && !options.includes(value) ? (
                            <option value={value}>{gcUsOptionLabel(value, zh)}</option>
                          ) : null}
                        </select>
                      )}
                      <span className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[9px] text-slate-600">
                        <span>
                          {state.template_fields[definition.id].status === 'doctor_edited'
                            ? (zh ? '医生已修改' : 'Physician edited')
                            : (zh
                              ? `来源: ${state.template_fields[definition.id].source}`
                              : `Source: ${state.template_fields[definition.id].source}`)}
                        </span>
                        {state.template_fields[definition.id].confidence != null ? (
                          <span>
                            {zh ? '置信度: ' : 'Confidence: '}
                            {Math.round((state.template_fields[definition.id].confidence || 0) * 100)}%
                          </span>
                        ) : null}
                        {state.template_fields[definition.id].evidence_ref?.length ? (
                          <button
                            type="button"
                            onClick={() => {
                              const anchor = state.frame_id || state.frame_time || state.case_id;
                              if (anchor) {
                                window.dispatchEvent(new CustomEvent('gc-us:evidence-anchor', {
                                  detail: {
                                    fieldId: definition.id,
                                    frameId: state.frame_id,
                                    frameTime: state.frame_time,
                                    caseId: state.case_id,
                                    evidenceRef: state.template_fields[definition.id].evidence_ref,
                                  },
                                }));
                              }
                            }}
                            className="max-w-full truncate rounded border border-white/10 px-1.5 py-0.5 text-left text-cyan-200/80 hover:border-cyan-300/40 hover:text-cyan-100"
                            title={zh
                              ? `依据: ${state.template_fields[definition.id].evidence_ref.join(', ')}（点击定位原帧）`
                              : `Evidence: ${state.template_fields[definition.id].evidence_ref.join(', ')} (click to jump to source frame)`}
                          >
                            {zh ? '依据: ' : 'Evidence: '}
                            {state.template_fields[definition.id].evidence_ref.join(', ')}
                          </button>
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
              {zh ? '参考报告图像（可多选，至少一项）' : 'Reference report images (multi-select, at least one)'}
            </div>
            <div className="mb-2 text-[9px] leading-relaxed text-slate-500">
              {zh
                ? '优先勾选当前帧分割叠加图与胃壁层次图。预览会自动隐藏加载失败的图，避免报告裂图。'
                : 'Prefer current-frame segmentation overlays and wall-layer panels. Preview hides failed loads so the report never shows broken figures.'}
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
                  <span className="min-w-0 flex-1 truncate">{image.label}</span>
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img
                    src={image.url}
                    alt=""
                    className="h-8 w-10 shrink-0 rounded border border-white/10 object-cover bg-black"
                    onError={(event) => {
                      (event.currentTarget as HTMLImageElement).style.opacity = '0.25';
                      (event.currentTarget as HTMLImageElement).title = zh ? '无法加载' : 'Failed to load';
                    }}
                  />
                </label>
              ))}
              {!images.length ? (
                <div className="text-[10px] text-slate-500">
                  {zh ? '暂无可用图像：请先勾画病灶/胃腔并生成证据图' : 'No images yet: draw lesion/lumen and generate evidence images first'}
                </div>
              ) : null}
            </div>
          </section>

          <section className="rounded-xl border border-white/12 p-3" style={{ backgroundColor: 'rgba(34, 42, 53, 0.88)', WebkitBackdropFilter: 'blur(10px)', backdropFilter: 'blur(10px)' }}>
            <div className="mb-2 text-[11px] font-semibold text-slate-200">
              {zh ? '导出方式（必选）' : 'Export method (required)'}
            </div>
            <div className="flex flex-wrap gap-2">
              {([
                ['pdf', zh ? 'PDF 文件' : 'PDF file'],
                ['print', zh ? '打印预览' : 'Print preview'],
              ] as Array<[GcUsExportMethod, string]>).map(([method, label]) => (
                <label
                  key={method}
                  className={`inline-flex items-center gap-2 rounded-lg border px-3 py-2 text-[10px] ${
                    state.report.export_method === method
                      ? 'border-amber-300/50 bg-amber-300/15 text-amber-100'
                      : 'border-white/10 text-slate-400'
                  }`}
                >
                  <input
                    type="radio"
                    name={`report-export-method-${previewId}`}
                    checked={state.report.export_method === method}
                    onChange={() => handleExportMethodChange(method)}
                    disabled={isFinalized}
                  />
                  {label}
                </label>
              ))}
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
              disabled={exportBusy || state.report.export_method !== 'pdf'}
              className="inline-flex items-center gap-1.5 rounded-lg border border-amber-300/30 bg-amber-300/10 px-3 py-2 text-[11px] text-amber-100 hover:bg-amber-300/20 disabled:opacity-50"
            >
              <FileDown size={13} />
              {exportBusy ? '导出中' : '导出 PDF'}
            </button>
            <button
              type="button"
              onClick={handlePrint}
              disabled={state.report.export_method !== 'print'}
              className="inline-flex items-center gap-1.5 rounded-lg border border-white/15 px-3 py-2 text-[11px] text-slate-300 hover:bg-white/5 disabled:opacity-50"
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
