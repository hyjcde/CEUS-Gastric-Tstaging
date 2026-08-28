"use client";

import { useSettings } from '@/contexts/SettingsContext';
import { calculateDiagnosis, generateNarrativeReport, generateSummaryPoints, getFeatureDescriptions } from '@/lib/diagnosis';
import { AgentAnalysisResponse, ConceptState, Patient } from '@/types';
import { Activity, AlignLeft, BarChart2, FileText, Maximize2, Tag, Terminal, X, Download, FileDown, ChevronDown } from 'lucide-react';
import React, { useEffect, useMemo, useState } from 'react';
import { createPortal } from 'react-dom';
import { exportReportToPDF, exportSinglePatientToCSV } from '@/lib/export-utils';
import toast from 'react-hot-toast';
import type { GcUsReportState } from '@/lib/gc-us-report-template';
import type { GcUsReportImage } from '@/lib/gc-us-report-template';
import type { SamReport } from '@/lib/reader/types';
import type { DinoFeatureResult, DinoLayerResult } from '@/components/InteractiveSegPanel';
import { DoctorReportStudio } from '@/components/DoctorReportStudio';
import { patientDisplayLabel } from '@/lib/patient-display';
import { ClinicalHistoryCard } from '@/components/ClinicalHistoryCard';
import { SimilarCaseReferencePanel } from '@/components/reader/SimilarCaseReferencePanel';
import { isEvaluationBrowserSession } from '@/lib/reader/evaluation-session';

interface DiagnosisPanelProps {
  state: ConceptState;
  patient: Patient | null;
  agentAnalysis?: AgentAnalysisResponse | null;
  systemReport?: SamReport | null;
  dinoFeature?: DinoFeatureResult | null;
  gcUsReport?: GcUsReportState | null;
  extraImages?: GcUsReportImage[];
  onGcUsReportChange?: (state: GcUsReportState) => void;
  onExpandedChange?: (expanded: boolean) => void;
  /** GC-US imaging paragraph from SAM + wall features */
  imagingNarrative?: string | null;
  similarCasesEnabled?: boolean;
  studyMode?: string;
  queryPreviewUrl?: string;
  queryMaskPolygon?: number[][] | null;
  queryImageWidth?: number;
  queryImageHeight?: number;
};

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown>
    : null;
}

export const DiagnosisPanel: React.FC<DiagnosisPanelProps> = React.memo(({
  state,
  patient,
  agentAnalysis = null,
  systemReport = null,
  dinoFeature = null,
  gcUsReport = null,
  extraImages = [],
  onGcUsReportChange,
  onExpandedChange,
  imagingNarrative = null,
  similarCasesEnabled = false,
  studyMode,
  queryPreviewUrl,
  queryMaskPolygon,
  queryImageWidth,
  queryImageHeight,
}) => {
  const { t, language } = useSettings();
  const evaluationSession = isEvaluationBrowserSession();
  const [reportText, setReportText] = useState('');
  const [isExpanded, setIsExpanded] = useState(false);
  const [activeTab, setActiveTab] = useState<'diagnosis' | 'clinical'>('diagnosis');
  const [portalReady, setPortalReady] = useState(false);
  const [activeDinoLayer, setActiveDinoLayer] = useState<number | null>(null);

  useEffect(() => {
    setPortalReady(true);
  }, []);

  useEffect(() => {
    const handler = () => {
      setIsExpanded(true);
      onExpandedChange?.(true);
      window.dispatchEvent(new CustomEvent('gastric:focus-agent'));
    };
    window.addEventListener('gastric:open-full-report', handler);
    return () => window.removeEventListener('gastric:open-full-report', handler);
  }, [onExpandedChange]);

  useEffect(() => {
    if (!isExpanded) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setIsExpanded(false);
        onExpandedChange?.(false);
      }
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [isExpanded, onExpandedChange]);

  const toggleExpanded = () => {
    const newExpanded = !isExpanded;
    setIsExpanded(newExpanded);
    onExpandedChange?.(newExpanded);
    if (newExpanded) {
      window.dispatchEvent(new CustomEvent('gastric:focus-agent'));
    }
  };

  const diagnosis = useMemo(() => calculateDiagnosis(state, patient), [state, patient]);
  const { tStage, nStage, probabilities, confidence, scores, flags, reasoning, preoperativeAdvice } = diagnosis;

  const displayPreoperativeAdvice = useMemo(() => {
    if (!agentAnalysis) return preoperativeAdvice;

    const decision = asRecord(agentAnalysis.tool_evidence.clinical_decision);
    const recommendation = typeof decision?.recommendation === 'string'
      ? decision.recommendation
      : '';
    const missingModalities = Array.isArray(decision?.missing_modalities)
      ? decision.missing_modalities.filter((item): item is string => typeof item === 'string')
      : [];
    const requiresMdt = decision?.requires_mdt === true;
    const agentStage = agentAnalysis.report.recommended_t_stage;
    if (!recommendation && !agentStage) return preoperativeAdvice;

    const modalityWorkup = missingModalities.map((modality) => {
      if (language === 'en') {
        if (modality === 'ct_report') return 'Obtain contrast-enhanced CT for local invasion and distant disease assessment.';
        if (modality === 'endoscopy_report') return 'Complete endoscopy/EUS review for primary lesion extent and T staging.';
        return `Complete missing modality: ${modality}.`;
      }
      if (modality === 'ct_report') return '补充增强 CT，评估局部侵犯范围及远处转移。';
      if (modality === 'endoscopy_report') return '补充胃镜/EUS，确认原发灶范围和 T 分期。';
      return `补充缺失检查：${modality}。`;
    });
    const reviewNote = language === 'en'
      ? 'Agent output is decision support only; confirm with imaging, endoscopy, pathology, and physician review.'
      : 'Agent 输出仅供辅助决策，须结合影像、胃镜、病理及医生复核。';

    return {
      ...preoperativeAdvice,
      overallAssessment: recommendation || (
        language === 'en'
          ? `Agent provisional stage: ${agentStage}.`
          : `Agent 暂定分期：${agentStage}。`
      ),
      urgency: requiresMdt ? 'urgent' : preoperativeAdvice.urgency,
      recommendedWorkup: modalityWorkup.length ? modalityWorkup : preoperativeAdvice.recommendedWorkup,
      treatmentConsiderations: [reviewNote],
      mdtRequired: requiresMdt || preoperativeAdvice.mdtRequired,
      uncertaintyNotes: Array.from(new Set([...preoperativeAdvice.uncertaintyNotes, reviewNote])),
    };
  }, [agentAnalysis, language, preoperativeAdvice]);
  
  const diagnosisLanguage = language === 'en' ? 'en' : 'zh';
  const descriptions = useMemo(() => getFeatureDescriptions(state, diagnosisLanguage), [state, diagnosisLanguage]);

  const dinoLayers = useMemo<DinoLayerResult[]>(() => {
    if (!dinoFeature?.available) return [];
    const layers = dinoFeature.layers?.length ? dinoFeature.layers : [dinoFeature];
    return layers.filter((layer): layer is DinoLayerResult => (
      Boolean(layer) && Number.isFinite(Number(layer.layer_index))
    ));
  }, [dinoFeature]);

  useEffect(() => {
    if (!dinoLayers.length) {
      setActiveDinoLayer(null);
      return;
    }
    if (!dinoLayers.some((layer) => layer.layer_index === activeDinoLayer)) {
      setActiveDinoLayer(dinoLayers[dinoLayers.length - 1].layer_index ?? null);
    }
  }, [activeDinoLayer, dinoLayers]);

  const selectedDinoLayer = useMemo(
    () => dinoLayers.find((layer) => layer.layer_index === activeDinoLayer) || dinoLayers[dinoLayers.length - 1] || null,
    [activeDinoLayer, dinoLayers],
  );

  const formatDinoValue = (value: unknown, digits = 3) => (
    typeof value === 'number' && Number.isFinite(value) ? value.toFixed(digits) : '—'
  );
  const formatDinoPercent = (value: unknown) => (
    typeof value === 'number' && Number.isFinite(value) ? `${Math.round(value * 100)}%` : '—'
  );

  const conceptFeatures = useMemo(() => {
    if (patient?.clinical?.concept_features) {
      return patient.clinical.concept_features;
    }
    return null;
  }, [patient?.clinical]);

  const formatConceptValue = (value?: string) => value ?? (language !== 'en' ? '未记录' : 'N/A');
  const actualFeatureRows = useMemo(() => {
    if (!conceptFeatures) return [];
    return [
      { label: language !== 'en' ? 'Ki-67（实际）' : 'Ki-67 (actual)', value: formatConceptValue(conceptFeatures.ki67) },
      { label: language !== 'en' ? 'CPS（实际）' : 'CPS (actual)', value: formatConceptValue(conceptFeatures.cps) },
      { label: language !== 'en' ? 'PD-1（实际）' : 'PD-1 (actual)', value: formatConceptValue(conceptFeatures.pd1) },
      { label: language !== 'en' ? 'FoxP3（实际）' : 'FoxP3 (actual)', value: formatConceptValue(conceptFeatures.foxp3) },
      { label: language !== 'en' ? 'CD3（实际）' : 'CD3 (actual)', value: formatConceptValue(conceptFeatures.cd3) },
      { label: language !== 'en' ? 'CD4（实际）' : 'CD4 (actual)', value: formatConceptValue(conceptFeatures.cd4) },
      { label: language !== 'en' ? 'CD8（实际）' : 'CD8 (actual)', value: formatConceptValue(conceptFeatures.cd8) },
      { label: language !== 'en' ? '脉管/血管' : 'Vascular/lymphatic', value: formatConceptValue(conceptFeatures.vascular) },
      { label: language !== 'en' ? '神经侵犯' : 'Neural invasion', value: formatConceptValue(conceptFeatures.neural) },
      { label: language !== 'en' ? '分化程度' : 'Differentiation', value: formatConceptValue(conceptFeatures.differentiation) },
      { label: language !== 'en' ? 'Lauren 分型' : 'Lauren class', value: formatConceptValue(conceptFeatures.lauren) }
    ];
  }, [conceptFeatures, language]);

  const structuredReportSections = useMemo(() => {
    const imagingFindings = [
      descriptions.ki67,
      descriptions.cps,
      descriptions.pd1,
      descriptions.foxp3,
      state.vascularInvasion ? (language !== 'en' ? '伴脉管侵犯。' : 'Vascular invasion present.') : '',
      state.neuralInvasion ? (language !== 'en' ? '伴神经侵犯。' : 'Neural invasion present.') : ''
    ].filter(Boolean).join(' ');

    const tumorSizeData = patient?.clinical?.tumorSize;
    const lesionSizeValue =
      tumorSizeData?.length && tumorSizeData?.thickness
        ? `${tumorSizeData.length} × ${tumorSizeData.thickness} cm${
            tumorSizeData.length && tumorSizeData.thickness
              ? ` (${(tumorSizeData.length * tumorSizeData.thickness).toFixed(1)} cm²)`
              : ''
          }`
        : language !== 'en'
          ? '待补充'
          : 'Pending measurement';

    const lymphStatusText = flags.hasMetastasis
      ? language !== 'en'
        ? `提示区域淋巴结转移（${nStage}），参考 FoxP3/Lauren/CPS 综合风险。`
        : `Regional nodal spread suspected (${nStage}), supported by FoxP3/Lauren/CPS risk.`
      : language !== 'en'
        ? '未见明确淋巴结转移高危信号（N0）。'
        : 'No definitive high-risk nodal signals (N0).';

    const stageText = language !== 'en'
      ? `工作台评估的是 cT（浸润深度），不等于完整 TNM；N 为淋巴结，M 为远处转移。当前辅助推断 ${tStage}${nStage}（置信度 ${confidence.overall}%）。无经确认壁层/浆膜/邻近器官证据时分期标记为 provisional。`
      : `This workbench estimates cT (invasion depth), not full TNM; N is nodal and M is distant metastasis. Current assistive inference is ${tStage}${nStage} (${confidence.overall}% confidence). Without confirmed wall/serosa/adjacent-organ evidence the stage is provisional.`;

    const recommendationText = flags.highRisk
      ? language !== 'en'
        ? '建议结合分割证据、分类结果和临床信息做多学科复核。'
        : 'Recommend multidisciplinary review with segmentation evidence, classifier output, and clinical context.'
      : language !== 'en'
        ? '当前更适合作为辅助结论，建议继续结合医生阅片与后续检查。'
        : 'Current output is suitable as assistive evidence and should be reviewed together with the physician assessment.';

    return [
      ...(imagingNarrative
        ? [{
            key: 'us_findings',
            label: language !== 'en' ? '超声所见（影像描述）' : 'Ultrasound findings',
            value: imagingNarrative,
          }]
        : []),
      {
        key: 'findings',
        label: language !== 'en' ? '病理特征' : 'Pathological Features',
        value: imagingFindings
      },
      {
        key: 'size',
        label: language !== 'en' ? '病灶尺寸' : 'Lesion size',
        value: lesionSizeValue
      },
      {
        key: 'nodes',
        label: language !== 'en' ? '淋巴结评估' : 'Lymph node assessment',
        value: lymphStatusText
      },
      {
        key: 'stage',
        label: language !== 'en' ? '分期推断' : 'Stage inference',
        value: stageText
      },
      {
        key: 'recommendation',
        label: language !== 'en' ? '建议后续' : 'Recommended action',
        value: recommendationText
      }
    ];
  }, [
    imagingNarrative,
    descriptions,
    language,
    patient?.clinical?.tumorSize,
    tStage,
    nStage,
    confidence.overall,
    flags.hasMetastasis,
    flags.highRisk,
    state.vascularInvasion,
    state.neuralInvasion
  ]);

  const smartSummaryPoints = useMemo(() => 
    generateSummaryPoints(state, diagnosis, patient, diagnosisLanguage),
    [state, diagnosis, patient, diagnosisLanguage]
  );

  const caseSummaryRows = useMemo(() => {
    if (!patient) return [];
    return [
      { label: language !== 'en' ? '病例标识' : 'Case token', value: patient.agent_report.case_token },
      { label: language !== 'en' ? '数据来源' : 'Data source', value: patient.source_label || patient.agent_report.data_source },
      { label: language !== 'en' ? '帧数' : 'Frames', value: String(patient.frame_count) },
      { label: language !== 'en' ? '模式' : 'View mode', value: patient.roi_url ? 'Image + ROI' : 'Image only' },
    ];
  }, [language, patient]);

  const segmentationRows = useMemo(() => {
    if (!patient) return [];
    return [
      { label: 'Annotation', value: patient.segmentation.has_annotation ? 'Yes' : 'No' },
      { label: 'Overlay', value: patient.segmentation.has_overlay ? 'Yes' : 'No' },
      { label: 'ROI', value: patient.segmentation.has_roi ? 'Yes' : 'No' },
      { label: language !== 'en' ? '标注总数' : 'Annotation count', value: String(patient.segmentation.annotation_count) },
    ];
  }, [language, patient]);

  const agentRows = useMemo(() => {
    if (!patient) return [];
    return [
      { label: language !== 'en' ? '图像质量' : 'Image quality', value: patient.agent_report.image_quality.summary },
      { label: language !== 'en' ? '分割状态' : 'Segmentation', value: patient.agent_report.segmentation.summary },
      { label: language !== 'en' ? '分类状态' : 'Classification', value: patient.agent_report.classification.summary },
      { label: language !== 'en' ? '相似病例' : 'Similar cases', value: patient.agent_report.similar_case_support.summary },
      {
        label: language !== 'en' ? '人工复核' : 'Manual review',
        value: patient.agent_report.manual_review_recommended
          ? (language !== 'en' ? '建议复核' : 'Recommended')
          : (language !== 'en' ? '可直接浏览' : 'Optional'),
      },
    ];
  }, [language, patient]);

  const patientReportRows = useMemo(() => {
    if (!patient) return [];
    const rows = [
      {
        label: language !== 'en' ? '超声报告' : 'Ultrasound report',
        value: patient.report?.ultrasound_report,
      },
      {
        label: language !== 'en' ? '超声所见' : 'Ultrasound findings',
        value: patient.report?.ultrasound_findings,
      },
      {
        label: language !== 'en' ? '超声提示' : 'Ultrasound impression',
        value: patient.report?.ultrasound_impression,
      },
      {
        label: language !== 'en' ? '内镜报告' : 'Endoscopy report',
        value: patient.report?.endoscopy_report,
      },
      {
        label: language !== 'en' ? '病理报告' : 'Pathology report',
        value: patient.report?.pathology_report || patient.clinical?.pathology_text,
      },
      {
        label: language !== 'en' ? '出院诊断' : 'Discharge diagnosis',
        value: patient.clinical?.discharge_diagnosis,
      },
      {
        label: language !== 'en' ? 'CT 报告' : 'CT report',
        value: patient.report?.ct_report,
      },
    ];
    return rows.filter((row) => row.value);
  }, [language, patient]);

  useEffect(() => {
    if (!patient) {
      setReportText(t.diagnosis.waiting);
      return;
    }

    const lines = generateNarrativeReport(state, diagnosis, patient, diagnosisLanguage);
    const fullText = lines.join("\n");
    let i = 0;
    setReportText('');
    const timer = setInterval(() => {
        if (i < fullText.length) {
            setReportText(prev => prev + fullText.charAt(i));
            i++;
        } else {
            clearInterval(timer);
        }
    }, 2);

    return () => clearInterval(timer);
  }, [patient?.id, state, language, diagnosis, t.diagnosis.waiting]);

  const agentClassificationProbs = useMemo(() => {
    const probs = agentAnalysis?.tool_evidence.classification?.probabilities;
    if (!probs || typeof probs !== 'object' || Array.isArray(probs)) return null;
    const entries = Object.entries(probs as Record<string, unknown>).map(([stage, value]) => ({
      stage,
      prob: Math.round((Number(value) <= 1 ? Number(value) * 100 : Number(value)) || 0),
    }));
    return entries.length > 0 ? entries : null;
  }, [agentAnalysis]);
  const formatAgentConfidence = (value?: string) => {
    if (!value) return `${confidence.overall}%`;
    if (language !== 'en') {
      return { high: '高', medium: '中等', low: '低' }[value] ?? value;
    }
    return value;
  };
  const doctorEditedGcUsReport = Boolean(
    gcUsReport
    && (gcUsReport.report.doctor_edited || gcUsReport.reference_stage.source === 'doctor'),
  );
  const agentDraft = doctorEditedGcUsReport ? null : agentAnalysis?.report.dynamic_report_draft;
  const agentFallbackReportText = useMemo(() => {
    if (!agentAnalysis || doctorEditedGcUsReport) return null;
    const decision = asRecord(agentAnalysis.tool_evidence.clinical_decision);
    const recommendation = typeof decision?.recommendation === 'string' ? decision.recommendation : '';
    const lines = [
      language !== 'en' ? '【Agent 辅助分析】' : 'Agent assisted analysis',
      `${language !== 'en' ? '推荐分期' : 'Provisional stage'}: ${agentAnalysis.report.recommended_t_stage}`,
      `${language !== 'en' ? '置信度' : 'Confidence'}: ${agentAnalysis.report.confidence}`,
      agentAnalysis.report.reasoning
        ? `${language !== 'en' ? '综合依据' : 'Reasoning'}: ${agentAnalysis.report.reasoning}`
        : '',
      recommendation
        ? `${language !== 'en' ? '临床建议' : 'Clinical recommendation'}: ${recommendation}`
        : '',
      agentAnalysis.report.conflicting_evidence?.length
        ? `${language !== 'en' ? '冲突证据' : 'Conflicting evidence'}: ${agentAnalysis.report.conflicting_evidence.join('；')}`
        : '',
      agentAnalysis.report.uncertainty_flags?.length
        ? `${language !== 'en' ? '不确定性' : 'Uncertainty'}: ${agentAnalysis.report.uncertainty_flags.join('；')}`
        : '',
      language !== 'en'
        ? '备注：该结果为辅助证据，不替代医生、胃镜、CT 或病理结论。'
        : 'Note: this is decision support and does not replace physician, endoscopy, CT, or pathology conclusions.',
    ];
    return lines.filter(Boolean).join('\n');
  }, [agentAnalysis, doctorEditedGcUsReport, language]);
  const expandedReportText = doctorEditedGcUsReport
    ? gcUsReport?.report.prose || reportText
    : agentDraft?.full_text || agentFallbackReportText || gcUsReport?.report.prose || reportText;
  const expandedStage = doctorEditedGcUsReport
    && gcUsReport?.reference_stage.band
    && gcUsReport.reference_stage.band !== 'uncertain'
    ? `c${gcUsReport.reference_stage.band}${nStage}`
    : agentAnalysis?.report.recommended_t_stage
    ? `${agentAnalysis.report.recommended_t_stage}${nStage}`
    : gcUsReport?.reference_stage.band && gcUsReport.reference_stage.band !== 'uncertain'
    ? `c${gcUsReport.reference_stage.band}${nStage}`
    : `${tStage}${nStage}`;
  const expandedConfidence = formatAgentConfidence(agentAnalysis?.report.confidence);

  const renderBar = (label: string, prob: number, color: string) => (
    <div key={label} className="flex items-center gap-2 text-[10px] font-mono mb-1.5">
        <span className="w-8 text-gray-500 text-right">{label}</span>
        <div className="flex-1 h-1.5 bg-[#222] rounded-full overflow-hidden">
            <div className={`h-full ${color} transition-all duration-500`} style={{ width: `${prob}%` }}></div>
        </div>
        <span className="w-6 text-gray-400 text-right">{Math.floor(prob)}%</span>
    </div>
  );

  // Risk Gauge Render Function
  const renderRiskGauge = (score: number) => {
      const rotation = (score / 100) * 180 - 90;
      const color = score > 80 ? 'text-red-500' : score > 50 ? 'text-amber-500' : 'text-emerald-500';
      
      return (
          <div className="flex flex-col items-center mt-2">
              <div className="relative w-40 h-20 overflow-hidden">
                  <div className="absolute top-0 left-1/2 -translate-x-1/2 w-36 h-36 rounded-full border-neutral-800 box-border" style={{ borderWidth: '15px', clipPath: 'polygon(0 0, 100% 0, 100% 50%, 0 50%)' }}></div>
                  <svg viewBox="0 0 100 50" className="absolute top-0 left-1/2 -translate-x-1/2 w-36 h-18 overflow-visible">
                      <path d="M 10 50 A 40 40 0 0 1 90 50" fill="none" stroke="#333" strokeWidth="8" strokeLinecap="round" />
                      <path 
                        d="M 10 50 A 40 40 0 0 1 90 50" 
                        fill="none" 
                        stroke={score > 80 ? '#ef4444' : score > 50 ? '#f59e0b' : '#10b981'} 
                        strokeWidth="8" 
                        strokeLinecap="round"
                        strokeDasharray="126"
                        strokeDashoffset={126 - (126 * score / 100)}
                        className="transition-all duration-1000 ease-out"
                      />
                  </svg>
                  <div className={`absolute bottom-0 left-1/2 -translate-x-1/2 text-2xl font-black tracking-tighter ${color} drop-shadow-lg`}>
                      {score}
                  </div>
              </div>
              <div className="text-[9px] font-bold text-gray-500 uppercase tracking-widest mt-1">Malignancy Risk</div>
          </div>
      )
  }

  return (
    <div className="flex flex-col h-full w-full bg-bg-dark relative">
      {/* Fullscreen Modal — portal 到 body，避免被右侧 420px 栏裁剪 */}
      {isExpanded && portalReady && createPortal(
        <div
          className="fixed inset-0 z-[200000] flex flex-col bg-black/95 backdrop-blur-md"
          style={{ top: '64px' }}
          role="dialog"
          aria-modal="true"
          aria-label={language !== 'en' ? '详细报告' : 'Detailed report'}
        >
          {/* 固定右上角关闭 — 始终可见 */}
          <button
            type="button"
            onClick={toggleExpanded}
            className="fixed top-[72px] right-4 z-[200001] flex h-11 w-11 items-center justify-center rounded-full border border-white/20 bg-neutral-900/95 text-gray-100 shadow-2xl transition hover:border-red-400/60 hover:bg-red-500/20 hover:text-white"
            title={language !== 'en' ? '关闭报告 (Esc)' : 'Close report (Esc)'}
            aria-label={language !== 'en' ? '关闭报告' : 'Close report'}
          >
            <X size={22} />
          </button>

          <div className="flex h-full w-full flex-col overflow-hidden bg-bg-dark">
                {/* Header */}
                <div className="h-20 shrink-0 border-b border-neutral-800 flex items-center justify-between px-8 pr-20 bg-linear-to-r from-neutral-900 via-neutral-800 to-neutral-900 shadow-lg">
                    <div className="flex items-center gap-4">
                        <div className="p-2 bg-emerald-500/20 rounded-lg border border-emerald-500/30">
                            <FileText size={20} className="text-emerald-400" /> 
                        </div>
                        <div>
                            <div className="text-sm font-bold text-gray-200 uppercase tracking-widest">
                                {language !== 'en' ? '辅助诊断完整报告' : 'Assisted diagnosis full report'}
                            </div>
                            <div className="text-xs text-gray-500 mt-0.5">
                                {patientDisplayLabel(patient, language)} • {new Date().toLocaleString(language !== 'en' ? 'zh-CN' : 'en-US')}
                            </div>
                        </div>
                    </div>
                    <div className="flex items-center gap-2">
                        <button
                            onClick={async () => {
                                if (!patient) {
                                    toast.error(language !== 'en' ? '请先选择患者' : 'Please select a patient first');
                                    return;
                                }
                                try {
                                    toast.loading(language !== 'en' ? '正在导出 PDF...' : 'Exporting PDF...', { id: 'export-pdf' });
                                    await exportReportToPDF(
                                        'diagnosis-report-content',
                                        `report_${patient.id_short}_${Date.now()}.pdf`
                                    );
                                    toast.success(language !== 'en' ? 'PDF 导出成功' : 'PDF exported successfully', { id: 'export-pdf' });
                                } catch (error) {
                                    console.error('Export failed:', error);
                                    toast.error(language !== 'en' ? 'PDF 导出失败' : 'Failed to export PDF', { id: 'export-pdf' });
                                }
                            }}
                            className="p-2.5 hover:bg-blue-500/20 rounded-lg transition-colors text-blue-400 hover:text-blue-300 border border-blue-500/30 hover:border-blue-500/50"
                            title={language !== 'en' ? '导出 PDF' : 'Export PDF'}
                        >
                            <FileDown size={18} />
                        </button>
                        <button
                            onClick={() => {
                                if (!patient) {
                                    toast.error(language !== 'en' ? '请先选择患者' : 'Please select a patient first');
                                    return;
                                }
                                try {
                                    exportSinglePatientToCSV(patient, state, diagnosis, `patient_${patient.id_short}_${Date.now()}.csv`);
                                    toast.success(language !== 'en' ? 'CSV 导出成功' : 'CSV exported successfully');
                                } catch (error) {
                                    console.error('Export failed:', error);
                                    toast.error(language !== 'en' ? 'CSV 导出失败' : 'Failed to export CSV');
                                }
                            }}
                            className="p-2.5 hover:bg-emerald-500/20 rounded-lg transition-colors text-emerald-400 hover:text-emerald-300 border border-emerald-500/30 hover:border-emerald-500/50"
                            title={language !== 'en' ? '导出 CSV' : 'Export CSV'}
                        >
                            <Download size={18} />
                        </button>
                        <button 
                            onClick={toggleExpanded}
                            className="p-2.5 hover:bg-red-500/20 rounded-lg transition-colors text-gray-200 hover:text-white border border-white/20 hover:border-red-400/50 bg-white/5"
                            title={language !== 'en' ? '关闭 (Esc)' : 'Close (Esc)'}
                            aria-label={language !== 'en' ? '关闭报告' : 'Close report'}
                        >
                            <X size={20} />
                        </button>
                    </div>
                </div>
                
                <div className="flex-1 overflow-y-auto custom-scrollbar">
                    <div id="diagnosis-report-content" className="p-5 space-y-4">
                        <DoctorReportStudio
                          patient={patient}
                          analysis={agentAnalysis}
                          gcUsReport={gcUsReport}
                          systemReport={systemReport}
                          extraImages={extraImages}
                          onGcUsReportChange={onGcUsReportChange}
                        />
                        <details className="rounded-xl border border-white/10 bg-black/20">
                          <summary className="cursor-pointer px-4 py-3 text-[11px] font-semibold text-slate-400 hover:text-slate-200">
                            {language !== 'en' ? '兼容旧版紧凑报告视图' : 'Legacy compact report view'}
                          </summary>
                          <div className="space-y-4 border-t border-white/10 p-4">
                        <div className={`rounded-xl border ${flags.isT4 || flags.hasMetastasis ? 'border-red-500/40 bg-red-950/20' : 'border-emerald-500/40 bg-emerald-950/20'} px-4 py-3 flex items-center justify-between gap-4`}>
                            <div className="min-w-0">
                                <div className="text-[10px] text-gray-500 uppercase tracking-wider">{language !== 'en' ? '可编辑诊断意见草稿' : 'Editable diagnosis draft'}</div>
                                <div className="text-base text-gray-100 font-mono truncate mt-1">{patientDisplayLabel(patient, language)}</div>
                                <div className="text-[11px] text-gray-500 mt-0.5">
                                    {patientDisplayLabel(patient, language)} • {new Date().toLocaleString(language !== 'en' ? 'zh-CN' : 'en-US')}
                                </div>
                            </div>
                            <div className="flex items-center gap-5 shrink-0">
                                <div className="text-right">
                                    <div className="text-[10px] text-gray-500 uppercase tracking-wider">{language !== 'en' ? '综合分期' : 'Stage'}</div>
                                    <div className={`text-4xl font-black tracking-tighter ${flags.isT4 || flags.hasMetastasis ? 'text-red-400' : 'text-emerald-400'}`}>{expandedStage}</div>
                                </div>
                                <div className="text-right">
                                    <div className="text-[10px] text-gray-500 uppercase tracking-wider">{language !== 'en' ? '置信度' : 'Confidence'}</div>
                                    <div className="text-2xl font-black text-gray-100">{expandedConfidence}</div>
                                </div>
                                <div className="hidden lg:block">
                                    {renderRiskGauge(Math.floor((scores.t + scores.n)/2))}
                                </div>
                            </div>
                        </div>

                        <div className="grid grid-cols-12 gap-4">
                            <div className="col-span-12 xl:col-span-7 space-y-4">
                                <div className="bg-linear-to-br from-black/85 to-neutral-900/70 p-4 rounded-xl border border-emerald-500/20 shadow-xl">
                                    <div className="flex items-center justify-between gap-3 mb-3">
                                        <div className="flex items-center gap-2">
                                            <Terminal size={16} className="text-emerald-400" />
                                            <div className="text-sm font-bold text-gray-200">
                                                {agentDraft
                                                    ? (language !== 'en' ? 'AI 动态报告正文' : 'AI Dynamic Report Draft')
                                                    : (language !== 'en' ? '本地报告草稿' : 'Local Draft Report')}
                                            </div>
                                        </div>
                                        <div className="text-[10px] text-gray-500">
                                            {agentDraft
                                                ? (language !== 'en' ? '来自 Agent 多工具证据链' : 'From Agent evidence workflow')
                                                : (language !== 'en' ? '运行 Agent 后自动升级为动态报告' : 'Run Agent to upgrade this draft')}
                                        </div>
                                    </div>
                                    {!agentDraft && (
                                        <div className="mb-3 rounded-lg border border-amber-500/20 bg-amber-500/10 px-3 py-2 text-xs text-amber-200">
                                            {language !== 'en'
                                                ? '当前展示的是 CBM 本地兜底报告。点击影像区顶部「启动当前病例 Agent」，会自动生成包含分割、壁层证据、报告线索、相似病例和复核建议的动态报告稿。'
                                                : 'This is the local CBM fallback draft. Start the case agent from the image viewer to generate a dynamic report with tool evidence, report cues, similar cases, and review advice.'}
                                        </div>
                                    )}
                                    <div className="bg-black/40 p-4 rounded-lg border border-neutral-700/50 max-h-[58vh] overflow-y-auto custom-scrollbar">
                                        <pre className="font-mono text-[13px] leading-6 text-gray-200 whitespace-pre-wrap typing-cursor">{expandedReportText}</pre>
                                    </div>
                                </div>

                                {agentDraft ? (
                                    <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                                        {agentDraft.sections.map((section) => (
                                            <div key={section.heading} className="rounded-lg border border-emerald-500/20 bg-emerald-500/5 p-3 text-xs text-gray-300 leading-relaxed">
                                                <div className="text-[11px] text-emerald-300 mb-1 font-semibold">{section.heading}</div>
                                                <div className="line-clamp-4">{section.lines.join(' ')}</div>
                                            </div>
                                        ))}
                                    </div>
                                ) : (
                                    <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                                        {smartSummaryPoints.map((point, idx) => (
                                            <div key={idx} className="rounded-lg border border-white/10 bg-white/5 p-3 text-xs text-gray-300 leading-relaxed">
                                                <div className="text-[10px] text-emerald-300 mb-1">{language !== 'en' ? `要点 ${idx + 1}` : `Point ${idx + 1}`}</div>
                                                {point}
                                            </div>
                                        ))}
                                    </div>
                                )}
                            </div>

                            <div className="col-span-12 xl:col-span-5 space-y-4">
                                <div className="grid grid-cols-2 gap-3">
                                    {caseSummaryRows.map((row) => (
                                        <div key={row.label} className="rounded-lg bg-neutral-900/70 border border-white/10 p-3">
                                            <div className="text-[10px] text-gray-500 mb-1">{row.label}</div>
                                            <div className="text-xs text-gray-200 font-mono break-all">{row.value}</div>
                                        </div>
                                    ))}
                                </div>

                                <div className="bg-linear-to-br from-neutral-900/80 to-neutral-800/40 p-4 rounded-xl border border-neutral-700/50">
                                    <div className="text-xs text-gray-400 uppercase tracking-wider mb-3">{language !== 'en' ? '分期概率' : 'Stage Probability'}</div>
                                    <div className="grid grid-cols-2 gap-4">
                                        <div>
                                            <div className="text-[10px] text-gray-500 mb-2">T-{language !== 'en' ? '分期' : 'Stage'}</div>
                                            {renderBar('T4', probabilities.t4, 'bg-red-500')}
                                            {renderBar('T3', probabilities.t3, 'bg-amber-500')}
                                            {renderBar('T1-2', probabilities.t2, 'bg-emerald-500')}
                                        </div>
                                        <div>
                                            <div className="text-[10px] text-gray-500 mb-2">N-{language !== 'en' ? '分期' : 'Stage'}</div>
                                            {renderBar('N0', probabilities.n0, 'bg-emerald-500')}
                                            {renderBar('N1', probabilities.n1, 'bg-yellow-500')}
                                            {renderBar('N2', probabilities.n2, 'bg-orange-500')}
                                            {renderBar('N3', probabilities.n3, 'bg-red-500')}
                                        </div>
                                    </div>
                                </div>

                                <div className="bg-linear-to-br from-neutral-900/90 to-neutral-800/50 p-4 rounded-xl border border-neutral-700/50">
                                    <div className="flex items-center gap-2 mb-3">
                                        <BarChart2 size={15} className="text-blue-400" />
                                        <div className="text-xs font-bold text-gray-300 uppercase tracking-wider">{language !== 'en' ? '结构化证据' : 'Structured Evidence'}</div>
                                    </div>
                                    <div className="space-y-2">
                                        {structuredReportSections.map((section) => (
                                            <div key={section.key} className="rounded bg-white/5 border border-white/5 p-2">
                                                <div className="text-[10px] text-gray-500 mb-1">{section.label}</div>
                                                <div className="text-[11px] text-gray-300 leading-relaxed">{section.value}</div>
                                            </div>
                                        ))}
                                    </div>
                                </div>

                                <div className="grid grid-cols-2 gap-2">
                                    {[
                                        { label: 'Ki-67', value: state.c1, color: '#ef4444' },
                                        { label: 'CPS', value: state.c2, color: '#f59e0b' },
                                        { label: 'PD-1', value: state.c3, color: '#3b82f6' },
                                        { label: 'FoxP3', value: state.c4, color: '#a855f7' }
                                    ].map((feature) => (
                                        <div key={feature.label} className="p-2.5 bg-white/5 rounded-lg border border-white/10">
                                            <div className="flex items-center justify-between text-xs mb-2">
                                                <span className="text-gray-400">{feature.label}</span>
                                                <span className="text-gray-200 font-bold font-mono">{Math.floor(feature.value)}%</span>
                                            </div>
                                            <div className="h-1.5 bg-neutral-800 rounded-full overflow-hidden">
                                                <div className="h-full rounded-full" style={{ width: `${feature.value}%`, backgroundColor: feature.color }} />
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            </div>
                        </div>
                        </div>
                        </details>
                    </div>
                </div>
          </div>
        </div>,
        document.body,
      )}

      {/* Minimized Panel */}
      <div className="h-9 shrink-0 border-b border-neutral-800 flex items-center justify-between px-3 bg-bg-dark">
        <div className="flex gap-2">
            <button 
                onClick={() => setActiveTab('diagnosis')}
                className={`flex items-center gap-2 text-[11px] font-bold uppercase tracking-widest transition-all px-3 py-1.5 rounded-md ${
                    activeTab === 'diagnosis' 
                        ? 'text-emerald-400 bg-emerald-500/20 border border-emerald-500/40 shadow-[0_0_10px_rgba(16,185,129,0.2)]' 
                        : 'text-gray-500 hover:text-gray-300 hover:bg-white/5'
                }`}
            >
                <FileText size={12} /> 
          {t.diagnosis.title}
            </button>
            <button 
                onClick={() => setActiveTab('clinical')}
                className={`flex items-center gap-2 text-[11px] font-bold uppercase tracking-widest transition-all px-3 py-1.5 rounded-md relative ${
                    activeTab === 'clinical' 
                        ? 'text-blue-400 bg-blue-500/20 border border-blue-500/40 shadow-[0_0_10px_rgba(59,130,246,0.2)]' 
                        : 'text-gray-500 hover:text-gray-300 hover:bg-white/5'
                } ${!patient?.clinical ? 'opacity-60' : ''}`}
                title={!patient?.clinical ? t.diagnosis.no_clinical : t.diagnosis.clinical}
            >
                <Activity size={12} /> 
                {t.diagnosis.clinical.toUpperCase()}
                {patient?.clinical && (
                    <span className="absolute -top-1 -right-1 w-2 h-2 bg-blue-500 rounded-full animate-pulse"></span>
                )}
            </button>
        </div>
        <div className="flex items-center gap-1">
            <button
                onClick={() => {
                    if (!patient) {
                        toast.error(language !== 'en' ? '请先选择患者' : 'Please select a patient first');
                        return;
                    }
                    try {
                        exportSinglePatientToCSV(patient, state, diagnosis, `patient_${patient.id_short}_${Date.now()}.csv`);
                        toast.success(language !== 'en' ? 'CSV 导出成功' : 'CSV exported successfully');
                    } catch (error) {
                        console.error('Export failed:', error);
                        toast.error(language !== 'en' ? 'CSV 导出失败' : 'Failed to export CSV');
                    }
                }}
                className="p-1 hover:bg-emerald-500/20 rounded transition-colors text-gray-500 hover:text-emerald-400"
                title={language !== 'en' ? '导出 CSV' : 'Export CSV'}
            >
                <Download size={12} />
            </button>
            <button 
                onClick={toggleExpanded}
                className="p-1 hover:bg-white/10 rounded transition-colors text-gray-500 hover:text-emerald-400"
                title="Expand Report"
            >
                <Maximize2 size={12} />
            </button>
        </div>
      </div>

      <div className="flex-1 flex flex-col min-h-0">
        {activeTab === 'diagnosis' ? (
            <>
                {similarCasesEnabled && patient ? (
                  <div className="shrink-0 max-h-[42vh] overflow-y-auto border-b border-white/10 p-2">
                    <SimilarCaseReferencePanel
                      caseId={patient.id}
                      patientId={patient.patient_id || patient.id}
                      studyMode={studyMode || patient.study_mode}
                      enabled
                      zh={language !== 'en'}
                      compact
                      allowOpenWorkbench={!evaluationSession}
                      queryPreviewUrl={queryPreviewUrl}
                      queryMaskPolygon={queryMaskPolygon}
                      queryImageWidth={queryImageWidth}
                      queryImageHeight={queryImageHeight}
                    />
                  </div>
                ) : null}

                {/* Probabilities Section - Compact 2 Columns */}
                <div className="shrink-0 p-3 border-b border-neutral-800 bg-neutral-900/30 grid grid-cols-2 gap-4">
                {/* Column 1: T-Stage */}
                <div>
                    <div className="flex items-center gap-2 mb-2">
                        <BarChart2 size={10} className="text-blue-400" />
                        <span className="text-[9px] font-bold text-gray-500 uppercase tracking-wider">T-Stage</span>
                    </div>
                    {renderBar('T4', probabilities.t4, 'bg-red-500')}
                    {renderBar('T3', probabilities.t3, 'bg-amber-500')}
                    {renderBar('T1-2', probabilities.t2, 'bg-emerald-500')}
                </div>
                
                {/* Column 2: N-Stage */}
                <div>
                    <div className="flex items-center gap-2 mb-2">
                        <BarChart2 size={10} className="text-purple-400" />
                        <span className="text-[9px] font-bold text-gray-500 uppercase tracking-wider">N-Stage</span>
                    </div>
                    {renderBar('N0', probabilities.n0, 'bg-emerald-500')}
                    {renderBar('N1', probabilities.n1, 'bg-yellow-500')}
                    {renderBar('N2', probabilities.n2, 'bg-orange-500')}
                    {renderBar('N3', probabilities.n3, 'bg-red-500')}
                </div>
                </div>

                {/* Prediction Header */}
                <div className="shrink-0 p-4 border-b border-neutral-800 bg-neutral-900/50 flex flex-col items-center justify-center relative overflow-hidden">
                  <div className={`absolute top-0 left-0 w-full h-1 ${flags.isT4 || flags.hasMetastasis ? 'bg-red-500' : 'bg-emerald-500'} shadow-[0_0_15px_currentColor]`}></div>
                        
                        <div className="flex items-center justify-between w-full px-2">
                            {/* Left: Text Prediction */}
                            <div className="flex flex-col items-center">
                                <div className="text-[11px] font-mono uppercase text-gray-400 mb-1">
                                  {agentAnalysis
                                    ? (language !== 'en' ? '辅助分期建议' : 'Assisted stage')
                                    : t.diagnosis.predicted}
                                </div>
                                <div className={`text-4xl font-black tracking-tighter mb-1 ${flags.isT4 || flags.hasMetastasis ? 'text-red-500' : 'text-emerald-400'}`}>
                                    {agentAnalysis?.report.recommended_t_stage
                                      ? `${agentAnalysis.report.recommended_t_stage}${nStage}`
                                      : `${tStage}${nStage}`}
                                </div>
                                <div className="max-w-[220px] text-center text-[9px] leading-relaxed text-slate-500">
                                  {language !== 'en'
                                    ? 'cT 阶梯：T1 黏膜/黏膜下层；T2 固有肌层；T3 浆膜下；T4a 浆膜；T4b 邻近器官。T4+ 仅为亚型未定聚合标签。'
                                    : 'cT ladder: T1 mucosa/SM; T2 MP; T3 subserosa; T4a serosa; T4b adjacent organs. T4+ is aggregate when subtype is unresolved.'}
                                </div>
                                <div className="text-[10px] font-mono text-gray-400">
                                  {language !== 'en' ? '置信度' : 'Confidence'}: {agentAnalysis ? formatAgentConfidence(agentAnalysis.report.confidence) : `${confidence.overall}%`}
                                </div>
                            </div>

                            {/* Right: Gauge */}
                            {renderRiskGauge(Math.floor((scores.t + scores.n)/2))}
                        </div>
                </div>

                {displayPreoperativeAdvice && (
                  <div className="shrink-0 border-b border-neutral-800 bg-neutral-900/30">
                    <details className="group" open>
                      <summary className="px-3 py-2.5 cursor-pointer flex items-center justify-between text-sm font-bold text-gray-300 uppercase tracking-wider hover:bg-white/5">
                        <span className="flex items-center gap-2">
                          <FileText size={15} className="text-blue-400" />
                          {language !== 'en' ? '术前决策建议' : 'Preop advice'}
                        </span>
                        <ChevronDown size={15} className="group-open:rotate-180 transition-transform" />
                      </summary>
                      <div className="px-3 pb-3 space-y-2">
                        <div className="text-sm p-2.5 bg-blue-500/10 border border-blue-500/20 rounded text-blue-200 leading-relaxed">
                          {displayPreoperativeAdvice.overallAssessment}
                        </div>
                        <div className="text-[12px] text-gray-400 space-y-1">
                          {displayPreoperativeAdvice.recommendedWorkup.map((item, i) => (
                            <div key={i}>• {item}</div>
                          ))}
                        </div>
                      </div>
                    </details>
                  </div>
                )}

                {systemReport && (
                  <div className="shrink-0 border-b border-cyan-500/20 bg-cyan-500/5 px-3 py-2.5">
                    <div className="mb-1.5 flex items-center justify-between gap-2">
                      <span className="text-[11px] font-bold uppercase tracking-wider text-cyan-200">
                        {language !== 'en' ? '当前帧辅助意见' : 'Current-frame assist'}
                      </span>
                    </div>
                    <div className="flex flex-wrap gap-2 text-[12px] text-slate-300">
                      {systemReport.recommended_stage ? (
                        <span>{language !== 'en' ? '建议' : 'Suggest'} {systemReport.recommended_stage}</span>
                      ) : null}
                      {systemReport.calibrated_confidence != null ? (
                        <span>{language !== 'en' ? '置信度' : 'Confidence'} {Math.round(systemReport.calibrated_confidence * 100)}%</span>
                      ) : null}
                      <span>{systemReport.evidence?.length || 0} {language !== 'en' ? '条证据' : 'evidence items'}</span>
                    </div>
                    {systemReport.summary ? (
                      <div className="mt-1.5 line-clamp-3 text-[12px] leading-relaxed text-slate-400">
                        {systemReport.summary}
                      </div>
                    ) : null}
                  </div>
                )}

                {selectedDinoLayer && dinoLayers.length > 0 && (
                  <section className="shrink-0 border-b border-amber-400/20 bg-amber-400/[0.04] px-3 py-3">
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <div className="text-[11px] font-bold uppercase tracking-wider text-amber-100">
                          {language !== 'en' ? '区域特征, DINOv3 多层分析' : 'Region features, DINOv3 multi-layer analysis'}
                        </div>
                        <div className="mt-1 text-[10px] text-slate-500">
                          {dinoFeature?.model || 'DINOv3'}
                          {dinoFeature?.frame_time != null ? `, ${language !== 'en' ? '当前帧' : 'frame'} ${Number(dinoFeature.frame_time).toFixed(2)}s` : ''}
                          {selectedDinoLayer.token_grid ? `, ${selectedDinoLayer.token_grid.join(' x ')} tokens` : ''}
                        </div>
                      </div>
                      <span className="rounded border border-amber-300/25 bg-amber-300/10 px-1.5 py-0.5 text-[9px] text-amber-100">
                        {dinoLayers.length} {language !== 'en' ? '层' : 'layers'}
                      </span>
                    </div>

                    <div className="mt-2 grid grid-cols-2 gap-2">
                      {dinoLayers.map((layer) => {
                        const layerIndex = Number(layer.layer_index);
                        const isSelected = layerIndex === selectedDinoLayer.layer_index;
                        const scalars = layer.scalars || {};
                        return (
                          <button
                            key={`dino-layer-${layerIndex}`}
                            type="button"
                            aria-pressed={isSelected}
                            onClick={() => setActiveDinoLayer(layerIndex)}
                            className={`rounded-lg border p-2 text-left transition ${
                              isSelected
                                ? 'border-amber-300/70 bg-amber-300/10'
                                : 'border-white/10 bg-black/20 hover:border-amber-300/35 hover:bg-white/[0.04]'
                            }`}
                          >
                            <div className="flex items-center justify-between gap-2">
                              <span className="text-[10px] font-semibold text-slate-100">
                                Layer {layerIndex + 1}
                              </span>
                              <span className="font-mono text-[9px] text-slate-500">
                                {layer.feature_dim || 0}D
                              </span>
                            </div>
                            <div className="mt-1 grid grid-cols-2 gap-1 text-[9px] text-slate-400">
                              <span>
                                {language !== 'en' ? '壁/病灶' : 'Wall/lesion'} {formatDinoValue(scalars.cos_wall_lesion)}
                              </span>
                              <span>
                                {language !== 'en' ? '边界/病灶' : 'Boundary/lesion'} {formatDinoValue(scalars.cos_boundary_lesion)}
                              </span>
                            </div>
                            {layer.roi_feature_overlay_png || layer.feature_overlay_png || layer.roi_wall_evidence_overlay_png || layer.wall_evidence_overlay_png ? (
                              <div className="mt-1.5 grid grid-cols-2 gap-1 overflow-hidden rounded">
                                {(layer.roi_feature_overlay_png || layer.feature_overlay_png) ? (
                                  // eslint-disable-next-line @next/next/no-img-element
                                  <img
                                    src={layer.roi_feature_overlay_png || layer.feature_overlay_png}
                                    alt={`${language !== 'en' ? '病灶亲和图' : 'Lesion affinity map'} layer ${layerIndex + 1}`}
                                    loading="lazy"
                                    className="h-14 w-full object-cover"
                                  />
                                ) : <div className="h-14 rounded bg-black/30" />}
                                {(layer.roi_wall_evidence_overlay_png || layer.wall_evidence_overlay_png) ? (
                                  // eslint-disable-next-line @next/next/no-img-element
                                  <img
                                    src={layer.roi_wall_evidence_overlay_png || layer.wall_evidence_overlay_png}
                                    alt={`${language !== 'en' ? '胃壁证据图' : 'Wall evidence map'} layer ${layerIndex + 1}`}
                                    loading="lazy"
                                    className="h-14 w-full object-cover"
                                  />
                                ) : <div className="h-14 rounded bg-black/30" />}
                              </div>
                            ) : null}
                          </button>
                        );
                      })}
                    </div>

                    <div className="mt-2 rounded-lg border border-white/10 bg-black/25 p-2">
                      <div className="flex items-center justify-between gap-2">
                        <div className="text-[10px] font-semibold text-amber-100">
                          {language !== 'en' ? `Layer ${Number(selectedDinoLayer.layer_index) + 1} 详细读数` : `Layer ${Number(selectedDinoLayer.layer_index) + 1} detail`}
                        </div>
                        <div className="font-mono text-[9px] text-slate-500">
                          μ {formatDinoValue(selectedDinoLayer.vector_stats?.mean)}
                          {' '}σ {formatDinoValue(selectedDinoLayer.vector_stats?.std)}
                        </div>
                      </div>
                      <div className="mt-2 grid grid-cols-3 gap-1.5">
                        {[
                          ['壁/病灶', 'cos_wall_lesion', 'Wall/lesion'],
                          ['边界/病灶', 'cos_boundary_lesion', 'Boundary/lesion'],
                          ['病灶 token', 'lesion_token_fraction', 'Lesion tokens'],
                          ['胃壁 token', 'wall_token_fraction', 'Wall tokens'],
                          ['边界 token', 'boundary_token_fraction', 'Boundary tokens'],
                        ].map(([zhLabel, key, enLabel]) => (
                          <div key={key} className="rounded border border-white/10 bg-white/[0.03] px-1.5 py-1">
                            <div className="text-[8px] text-slate-500">{language !== 'en' ? zhLabel : enLabel}</div>
                            <div className="mt-0.5 font-mono text-[10px] text-slate-200">
                              {key.includes('fraction')
                                ? formatDinoPercent(selectedDinoLayer.scalars?.[key])
                                : formatDinoValue(selectedDinoLayer.scalars?.[key])}
                            </div>
                          </div>
                        ))}
                      </div>
                      <div className="mt-2 grid grid-cols-2 gap-2">
                        {(selectedDinoLayer.roi_feature_overlay_png || selectedDinoLayer.feature_overlay_png) ? (
                          <figure>
                            <figcaption className="mb-1 text-[9px] text-slate-500">
                              {language !== 'en' ? '病灶亲和图（ROI）' : 'Lesion affinity (ROI)'}
                            </figcaption>
                            {/* eslint-disable-next-line @next/next/no-img-element */}
                            <img
                              src={selectedDinoLayer.roi_feature_overlay_png || selectedDinoLayer.feature_overlay_png}
                              alt={language !== 'en' ? '当前层病灶亲和叠加图' : 'Selected-layer lesion affinity overlay'}
                              className="h-28 w-full rounded border border-white/10 object-cover"
                            />
                          </figure>
                        ) : null}
                        {(selectedDinoLayer.roi_wall_evidence_overlay_png || selectedDinoLayer.wall_evidence_overlay_png) ? (
                          <figure>
                            <figcaption className="mb-1 text-[9px] text-slate-500">
                              {language !== 'en' ? '胃壁差异证据图（ROI）' : 'Wall evidence difference (ROI)'}
                            </figcaption>
                            {/* eslint-disable-next-line @next/next/no-img-element */}
                            <img
                              src={selectedDinoLayer.roi_wall_evidence_overlay_png || selectedDinoLayer.wall_evidence_overlay_png}
                              alt={language !== 'en' ? '当前层胃壁证据叠加图' : 'Selected-layer wall evidence overlay'}
                              className="h-28 w-full rounded border border-white/10 object-cover"
                            />
                          </figure>
                        ) : null}
                      </div>
                    </div>
                    <div className="mt-1.5 text-[9px] leading-relaxed text-slate-500">
                      {language !== 'en'
                        ? '这些是当前帧区域表征和相似度辅助，不是独立的病理或分期结论。'
                        : 'These are current-frame region representations and similarity cues, not independent pathology or staging conclusions.'}
                    </div>
                  </section>
                )}

                <div className="shrink-0 border-b border-white/10 px-3 py-2.5">
                  <button
                    type="button"
                    onClick={toggleExpanded}
                    className="flex w-full items-center justify-center gap-2 rounded-lg border border-emerald-400/40 bg-emerald-500/15 px-3 py-2.5 text-sm font-semibold text-emerald-100 hover:bg-emerald-500/25"
                  >
                    <Maximize2 size={16} />
                    {language !== 'en' ? '确认完整报告' : 'Confirm full report'}
                  </button>
                  <div className="mt-1.5 text-center text-[11px] text-slate-500">
                    {language !== 'en'
                      ? '完整报告中可查看详细意见并启动辅助分析'
                      : 'Full report includes detailed opinion and assisted analysis'}
                  </div>
                </div>

                {/* Editable draft preview */}
                <div className="flex-1 bg-black p-3.5 text-[13px] leading-relaxed text-gray-300 overflow-y-auto min-h-0 relative group custom-scrollbar" onClick={toggleExpanded}>
                <div className="absolute top-2 right-2 opacity-30 group-hover:opacity-70 transition-opacity cursor-pointer">
                    <Maximize2 size={14} />
                </div>
                {agentDraft && (
                  <div className="mb-2 rounded border border-emerald-500/20 bg-emerald-500/5 px-2.5 py-1.5 text-[12px] text-emerald-200">
                    {language !== 'en' ? '辅助诊断意见已就绪，点击展开完整报告' : 'Assisted opinion ready — open full report'}
                  </div>
                )}
                <pre className="whitespace-pre-wrap cursor-pointer font-sans">{agentDraft?.full_text?.slice(0, 600) || reportText}{agentDraft && agentDraft.full_text.length > 600 ? '…' : ''}</pre>
                </div>
            </>
        ) : patient ? (
            <div className="flex-1 overflow-y-auto animate-in fade-in duration-300 custom-scrollbar">
                 <ClinicalHistoryCard
                   patient={patient}
                   hideGold={evaluationSession}
                   hideReports={evaluationSession}
                 />
                 <div className="space-y-4 p-4">

                 {!evaluationSession ? (
                 <div className="bg-linear-to-br from-neutral-900/50 to-neutral-800/30 p-3 rounded-lg border border-white/5">
                    <div className="text-[10px] text-gray-500 uppercase tracking-wider mb-2 flex items-center gap-1"><AlignLeft size={10}/> {t.diagnosis.case_summary}</div>
                    <div className="space-y-1.5 text-xs text-gray-300">
                        {caseSummaryRows.map((row) => (
                          <div className="flex gap-2 items-center" key={row.label}>
                            <span className="text-gray-500 w-24 text-right">{row.label}</span>
                            <span className="flex-1 font-mono break-all">{row.value}</span>
                          </div>
                        ))}
                    </div>
                 </div>
                 ) : null}

                 {!evaluationSession && patientReportRows.length > 0 && (
                    <div className="bg-linear-to-br from-cyan-900/20 to-slate-800/20 p-3 rounded-lg border border-cyan-500/30">
                      <div className="text-[10px] text-gray-400 uppercase tracking-wider mb-2 flex items-center gap-1">
                        <FileText size={10} className="text-cyan-400"/>
                        {language !== 'en' ? '报告文本证据' : 'Report Text Evidence'}
                      </div>
                      <div className="space-y-2 text-xs text-gray-200">
                        {patientReportRows.map((row) => (
                          <div className="space-y-1" key={row.label}>
                            <div className="text-gray-500">{row.label}</div>
                            <div className="font-mono whitespace-pre-wrap break-words rounded bg-black/20 p-2 leading-relaxed">
                              {row.value}
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                 )}
                 
                 {/* Segmentation Assets */}
                 <div className="bg-linear-to-br from-blue-900/20 to-blue-800/10 p-3 rounded-lg border border-blue-500/30">
                    <div className="text-[10px] text-gray-400 uppercase tracking-wider mb-2 flex items-center gap-1"><Tag size={10} className="text-blue-400"/> {t.diagnosis.segmentation_assets}</div>
                    <div className="space-y-2 text-xs text-gray-200">
                        {segmentationRows.map((row) => (
                          <div className="flex items-center justify-between gap-3" key={row.label}>
                            <span className="text-gray-400">{row.label}</span>
                            <span className="font-mono">{row.value}</span>
                          </div>
                        ))}
                    </div>
                 </div>

                 {/* Agent Draft */}
                 <div className="bg-linear-to-br from-purple-900/20 to-purple-800/10 p-3 rounded-lg border border-purple-500/30">
                    <div className="text-[10px] text-gray-400 uppercase tracking-wider mb-2 flex items-center gap-1"><FileText size={10} className="text-purple-400"/> {t.diagnosis.agent_readiness}</div>
                    <div className="space-y-2 text-xs text-gray-200">
                        {agentRows.map((row) => (
                          <div className="flex items-start justify-between gap-3" key={row.label}>
                            <span className="text-gray-400 shrink-0">{row.label}</span>
                            <span className="font-mono text-right">{row.value}</span>
                          </div>
                        ))}
                    </div>
                 </div>
                 </div>

            </div>
        ) : (
                <div className="flex-1 flex flex-col items-center justify-center p-8 text-center">
                    <div className="text-sm font-bold text-gray-400 mb-2 uppercase tracking-wider">{t.diagnosis.no_clinical}</div>
                </div>
        )}
      </div>
    </div>
  );
});

DiagnosisPanel.displayName = 'DiagnosisPanel';
