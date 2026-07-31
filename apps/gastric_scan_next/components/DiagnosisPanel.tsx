"use client";

import { useSettings } from '@/contexts/SettingsContext';
import { calculateDiagnosis, generateNarrativeReport, generateSummaryPoints, getFeatureDescriptions } from '@/lib/diagnosis';
import { AgentAnalysisResponse, ConceptState, Patient } from '@/types';
import { Activity, AlignLeft, BarChart2, FileText, Maximize2, Ruler, Tag, Terminal, User, X, Download, FileDown, ChevronDown } from 'lucide-react';
import React, { useEffect, useMemo, useState } from 'react';
import { createPortal } from 'react-dom';
import { exportReportToPDF, exportSinglePatientToCSV } from '@/lib/export-utils';
import toast from 'react-hot-toast';

interface DiagnosisPanelProps {
  state: ConceptState;
  patient: Patient | null;
  agentAnalysis?: AgentAnalysisResponse | null;
  onExpandedChange?: (expanded: boolean) => void;
  /** GC-US imaging paragraph from SAM + wall features */
  imagingNarrative?: string | null;
};

export const DiagnosisPanel: React.FC<DiagnosisPanelProps> = React.memo(({ state, patient, agentAnalysis = null, onExpandedChange, imagingNarrative = null }) => {
  const { t, language } = useSettings();
  const [reportText, setReportText] = useState('');
  const [isExpanded, setIsExpanded] = useState(false);
  const [activeTab, setActiveTab] = useState<'diagnosis' | 'clinical'>('diagnosis');
  const [portalReady, setPortalReady] = useState(false);

  useEffect(() => {
    setPortalReady(true);
  }, []);

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
  };

  const diagnosis = useMemo(() => calculateDiagnosis(state, patient), [state, patient]);
  const { tStage, nStage, probabilities, confidence, scores, flags, reasoning, preoperativeAdvice } = diagnosis;
  
  const descriptions = useMemo(() => getFeatureDescriptions(state, language as 'zh' | 'en'), [state, language]);

  const conceptFeatures = useMemo(() => {
    if (patient?.clinical?.concept_features) {
      return patient.clinical.concept_features;
    }
    return null;
  }, [patient?.clinical]);

  const formatConceptValue = (value?: string) => value ?? (language === 'zh' ? '未记录' : 'N/A');
  const actualFeatureRows = useMemo(() => {
    if (!conceptFeatures) return [];
    return [
      { label: language === 'zh' ? 'Ki-67（实际）' : 'Ki-67 (actual)', value: formatConceptValue(conceptFeatures.ki67) },
      { label: language === 'zh' ? 'CPS（实际）' : 'CPS (actual)', value: formatConceptValue(conceptFeatures.cps) },
      { label: language === 'zh' ? 'PD-1（实际）' : 'PD-1 (actual)', value: formatConceptValue(conceptFeatures.pd1) },
      { label: language === 'zh' ? 'FoxP3（实际）' : 'FoxP3 (actual)', value: formatConceptValue(conceptFeatures.foxp3) },
      { label: language === 'zh' ? 'CD3（实际）' : 'CD3 (actual)', value: formatConceptValue(conceptFeatures.cd3) },
      { label: language === 'zh' ? 'CD4（实际）' : 'CD4 (actual)', value: formatConceptValue(conceptFeatures.cd4) },
      { label: language === 'zh' ? 'CD8（实际）' : 'CD8 (actual)', value: formatConceptValue(conceptFeatures.cd8) },
      { label: language === 'zh' ? '脉管/血管' : 'Vascular/lymphatic', value: formatConceptValue(conceptFeatures.vascular) },
      { label: language === 'zh' ? '神经侵犯' : 'Neural invasion', value: formatConceptValue(conceptFeatures.neural) },
      { label: language === 'zh' ? '分化程度' : 'Differentiation', value: formatConceptValue(conceptFeatures.differentiation) },
      { label: language === 'zh' ? 'Lauren 分型' : 'Lauren class', value: formatConceptValue(conceptFeatures.lauren) }
    ];
  }, [conceptFeatures, language]);

  const structuredReportSections = useMemo(() => {
    const imagingFindings = [
      descriptions.ki67,
      descriptions.cps,
      descriptions.pd1,
      descriptions.foxp3,
      state.vascularInvasion ? (language === 'zh' ? '伴脉管侵犯。' : 'Vascular invasion present.') : '',
      state.neuralInvasion ? (language === 'zh' ? '伴神经侵犯。' : 'Neural invasion present.') : ''
    ].filter(Boolean).join(' ');

    const tumorSizeData = patient?.clinical?.tumorSize;
    const lesionSizeValue =
      tumorSizeData?.length && tumorSizeData?.thickness
        ? `${tumorSizeData.length} × ${tumorSizeData.thickness} cm${
            tumorSizeData.length && tumorSizeData.thickness
              ? ` (${(tumorSizeData.length * tumorSizeData.thickness).toFixed(1)} cm²)`
              : ''
          }`
        : language === 'zh'
          ? '待补充'
          : 'Pending measurement';

    const lymphStatusText = flags.hasMetastasis
      ? language === 'zh'
        ? `提示区域淋巴结转移（${nStage}），参考 FoxP3/Lauren/CPS 综合风险。`
        : `Regional nodal spread suspected (${nStage}), supported by FoxP3/Lauren/CPS risk.`
      : language === 'zh'
        ? '未见明确淋巴结转移高危信号（N0）。'
        : 'No definitive high-risk nodal signals (N0).';

    const stageText = language === 'zh'
      ? `CBM模型推断 ${tStage}${nStage}（置信度 ${confidence.overall}%）。`
      : `CBM Model infers ${tStage}${nStage} with ${confidence.overall}% confidence.`;

    const recommendationText = flags.highRisk
      ? language === 'zh'
        ? '建议结合分割证据、分类结果和临床信息做多学科复核。'
        : 'Recommend multidisciplinary review with segmentation evidence, classifier output, and clinical context.'
      : language === 'zh'
        ? '当前更适合作为辅助结论，建议继续结合医生阅片与后续检查。'
        : 'Current output is suitable as assistive evidence and should be reviewed together with the physician assessment.';

    return [
      ...(imagingNarrative
        ? [{
            key: 'us_findings',
            label: language === 'zh' ? '超声所见（影像描述）' : 'Ultrasound findings',
            value: imagingNarrative,
          }]
        : []),
      {
        key: 'findings',
        label: language === 'zh' ? '病理特征' : 'Pathological Features',
        value: imagingFindings
      },
      {
        key: 'size',
        label: language === 'zh' ? '病灶尺寸' : 'Lesion size',
        value: lesionSizeValue
      },
      {
        key: 'nodes',
        label: language === 'zh' ? '淋巴结评估' : 'Lymph node assessment',
        value: lymphStatusText
      },
      {
        key: 'stage',
        label: language === 'zh' ? '分期推断' : 'Stage inference',
        value: stageText
      },
      {
        key: 'recommendation',
        label: language === 'zh' ? '建议后续' : 'Recommended action',
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
    generateSummaryPoints(state, diagnosis, patient, language as 'zh' | 'en'),
    [state, diagnosis, patient, language]
  );

  const caseSummaryRows = useMemo(() => {
    if (!patient) return [];
    return [
      { label: language === 'zh' ? '病例标识' : 'Case token', value: patient.agent_report.case_token },
      { label: language === 'zh' ? '数据来源' : 'Data source', value: patient.source_label || patient.agent_report.data_source },
      { label: language === 'zh' ? '帧数' : 'Frames', value: String(patient.frame_count) },
      { label: language === 'zh' ? '模式' : 'View mode', value: patient.roi_url ? 'Image + ROI' : 'Image only' },
    ];
  }, [language, patient]);

  const segmentationRows = useMemo(() => {
    if (!patient) return [];
    return [
      { label: 'Annotation', value: patient.segmentation.has_annotation ? 'Yes' : 'No' },
      { label: 'Overlay', value: patient.segmentation.has_overlay ? 'Yes' : 'No' },
      { label: 'ROI', value: patient.segmentation.has_roi ? 'Yes' : 'No' },
      { label: language === 'zh' ? '标注总数' : 'Annotation count', value: String(patient.segmentation.annotation_count) },
    ];
  }, [language, patient]);

  const agentRows = useMemo(() => {
    if (!patient) return [];
    return [
      { label: language === 'zh' ? '图像质量' : 'Image quality', value: patient.agent_report.image_quality.summary },
      { label: language === 'zh' ? '分割状态' : 'Segmentation', value: patient.agent_report.segmentation.summary },
      { label: language === 'zh' ? '分类状态' : 'Classification', value: patient.agent_report.classification.summary },
      { label: language === 'zh' ? '相似病例' : 'Similar cases', value: patient.agent_report.similar_case_support.summary },
      {
        label: language === 'zh' ? '人工复核' : 'Manual review',
        value: patient.agent_report.manual_review_recommended
          ? (language === 'zh' ? '建议复核' : 'Recommended')
          : (language === 'zh' ? '可直接浏览' : 'Optional'),
      },
    ];
  }, [language, patient]);

  const patientReportRows = useMemo(() => {
    if (!patient?.report) return [];
    const rows = [
      {
        label: language === 'zh' ? '超声报告' : 'Ultrasound report',
        value: patient.report.ultrasound_report,
      },
      {
        label: language === 'zh' ? '超声所见' : 'Ultrasound findings',
        value: patient.report.ultrasound_findings,
      },
      {
        label: language === 'zh' ? '超声提示' : 'Ultrasound impression',
        value: patient.report.ultrasound_impression,
      },
      {
        label: language === 'zh' ? '内镜报告' : 'Endoscopy report',
        value: patient.report.endoscopy_report,
      },
      {
        label: language === 'zh' ? '病理报告' : 'Pathology report',
        value: patient.report.pathology_report,
      },
    ];
    return rows.filter((row) => row.value);
  }, [language, patient?.report]);

  useEffect(() => {
    if (!patient) {
      setReportText(t.diagnosis.waiting);
      return;
    }

    const lines = generateNarrativeReport(state, diagnosis, patient, language as 'zh' | 'en');
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

  const agentDraft = agentAnalysis?.report.dynamic_report_draft;
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
    if (language === 'zh') {
      return { high: '高', medium: '中等', low: '低' }[value] ?? value;
    }
    return value;
  };
  const expandedReportText = agentDraft?.full_text || reportText;
  const expandedStage = agentAnalysis?.report.recommended_t_stage
    ? `${agentAnalysis.report.recommended_t_stage}${nStage}`
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
          aria-label={language === 'zh' ? '详细报告' : 'Detailed report'}
        >
          {/* 固定右上角关闭 — 始终可见 */}
          <button
            type="button"
            onClick={toggleExpanded}
            className="fixed top-[72px] right-4 z-[200001] flex h-11 w-11 items-center justify-center rounded-full border border-white/20 bg-neutral-900/95 text-gray-100 shadow-2xl transition hover:border-red-400/60 hover:bg-red-500/20 hover:text-white"
            title={language === 'zh' ? '关闭报告 (Esc)' : 'Close report (Esc)'}
            aria-label={language === 'zh' ? '关闭报告' : 'Close report'}
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
                                {t.diagnosis.report_header || "Detailed Medical Report"}
                            </div>
                            <div className="text-xs text-gray-500 mt-0.5">
                                {patient?.id_short || 'N/A'} • {new Date().toLocaleString(language === 'zh' ? 'zh-CN' : 'en-US')}
                            </div>
                        </div>
                    </div>
                    <div className="flex items-center gap-2">
                        <button
                            onClick={async () => {
                                if (!patient) {
                                    toast.error(language === 'zh' ? '请先选择患者' : 'Please select a patient first');
                                    return;
                                }
                                try {
                                    toast.loading(language === 'zh' ? '正在导出 PDF...' : 'Exporting PDF...', { id: 'export-pdf' });
                                    await exportReportToPDF(
                                        'diagnosis-report-content',
                                        `report_${patient.id_short}_${Date.now()}.pdf`
                                    );
                                    toast.success(language === 'zh' ? 'PDF 导出成功' : 'PDF exported successfully', { id: 'export-pdf' });
                                } catch (error) {
                                    console.error('Export failed:', error);
                                    toast.error(language === 'zh' ? 'PDF 导出失败' : 'Failed to export PDF', { id: 'export-pdf' });
                                }
                            }}
                            className="p-2.5 hover:bg-blue-500/20 rounded-lg transition-colors text-blue-400 hover:text-blue-300 border border-blue-500/30 hover:border-blue-500/50"
                            title={language === 'zh' ? '导出 PDF' : 'Export PDF'}
                        >
                            <FileDown size={18} />
                        </button>
                        <button
                            onClick={() => {
                                if (!patient) {
                                    toast.error(language === 'zh' ? '请先选择患者' : 'Please select a patient first');
                                    return;
                                }
                                try {
                                    exportSinglePatientToCSV(patient, state, diagnosis, `patient_${patient.id_short}_${Date.now()}.csv`);
                                    toast.success(language === 'zh' ? 'CSV 导出成功' : 'CSV exported successfully');
                                } catch (error) {
                                    console.error('Export failed:', error);
                                    toast.error(language === 'zh' ? 'CSV 导出失败' : 'Failed to export CSV');
                                }
                            }}
                            className="p-2.5 hover:bg-emerald-500/20 rounded-lg transition-colors text-emerald-400 hover:text-emerald-300 border border-emerald-500/30 hover:border-emerald-500/50"
                            title={language === 'zh' ? '导出 CSV' : 'Export CSV'}
                        >
                            <Download size={18} />
                        </button>
                        <button 
                            onClick={toggleExpanded}
                            className="p-2.5 hover:bg-red-500/20 rounded-lg transition-colors text-gray-200 hover:text-white border border-white/20 hover:border-red-400/50 bg-white/5"
                            title={language === 'zh' ? '关闭 (Esc)' : 'Close (Esc)'}
                            aria-label={language === 'zh' ? '关闭报告' : 'Close report'}
                        >
                            <X size={20} />
                        </button>
                    </div>
                </div>
                
                <div className="flex-1 overflow-y-auto custom-scrollbar">
                    <div id="diagnosis-report-content" className="p-5 space-y-4">
                        <div className={`rounded-xl border ${flags.isT4 || flags.hasMetastasis ? 'border-red-500/40 bg-red-950/20' : 'border-emerald-500/40 bg-emerald-950/20'} px-4 py-3 flex items-center justify-between gap-4`}>
                            <div className="min-w-0">
                                <div className="text-[10px] text-gray-500 uppercase tracking-wider">{language === 'zh' ? 'AI 自动生成报告草稿' : 'AI Generated Draft Report'}</div>
                                <div className="text-base text-gray-100 font-mono truncate mt-1">{patient?.id_short || 'N/A'}</div>
                                <div className="text-[11px] text-gray-500 mt-0.5">
                                    {patient?.id_short || 'N/A'} • {new Date().toLocaleString(language === 'zh' ? 'zh-CN' : 'en-US')}
                                </div>
                            </div>
                            <div className="flex items-center gap-5 shrink-0">
                                <div className="text-right">
                                    <div className="text-[10px] text-gray-500 uppercase tracking-wider">{language === 'zh' ? '综合分期' : 'Stage'}</div>
                                    <div className={`text-4xl font-black tracking-tighter ${flags.isT4 || flags.hasMetastasis ? 'text-red-400' : 'text-emerald-400'}`}>{expandedStage}</div>
                                </div>
                                <div className="text-right">
                                    <div className="text-[10px] text-gray-500 uppercase tracking-wider">{language === 'zh' ? '置信度' : 'Confidence'}</div>
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
                                                    ? (language === 'zh' ? 'AI 动态报告正文' : 'AI Dynamic Report Draft')
                                                    : (language === 'zh' ? '本地报告草稿' : 'Local Draft Report')}
                                            </div>
                                        </div>
                                        <div className="text-[10px] text-gray-500">
                                            {agentDraft
                                                ? (language === 'zh' ? '来自 Agent 多工具证据链' : 'From Agent evidence workflow')
                                                : (language === 'zh' ? '运行 Agent 后自动升级为动态报告' : 'Run Agent to upgrade this draft')}
                                        </div>
                                    </div>
                                    {!agentDraft && (
                                        <div className="mb-3 rounded-lg border border-amber-500/20 bg-amber-500/10 px-3 py-2 text-xs text-amber-200">
                                            {language === 'zh'
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
                                                <div className="text-[10px] text-emerald-300 mb-1">{language === 'zh' ? `要点 ${idx + 1}` : `Point ${idx + 1}`}</div>
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
                                    <div className="text-xs text-gray-400 uppercase tracking-wider mb-3">{language === 'zh' ? '分期概率' : 'Stage Probability'}</div>
                                    <div className="grid grid-cols-2 gap-4">
                                        <div>
                                            <div className="text-[10px] text-gray-500 mb-2">T-{language === 'zh' ? '分期' : 'Stage'}</div>
                                            {renderBar('T4', probabilities.t4, 'bg-red-500')}
                                            {renderBar('T3', probabilities.t3, 'bg-amber-500')}
                                            {renderBar('T1-2', probabilities.t2, 'bg-emerald-500')}
                                        </div>
                                        <div>
                                            <div className="text-[10px] text-gray-500 mb-2">N-{language === 'zh' ? '分期' : 'Stage'}</div>
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
                                        <div className="text-xs font-bold text-gray-300 uppercase tracking-wider">{language === 'zh' ? '结构化证据' : 'Structured Evidence'}</div>
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
                        toast.error(language === 'zh' ? '请先选择患者' : 'Please select a patient first');
                        return;
                    }
                    try {
                        exportSinglePatientToCSV(patient, state, diagnosis, `patient_${patient.id_short}_${Date.now()}.csv`);
                        toast.success(language === 'zh' ? 'CSV 导出成功' : 'CSV exported successfully');
                    } catch (error) {
                        console.error('Export failed:', error);
                        toast.error(language === 'zh' ? 'CSV 导出失败' : 'Failed to export CSV');
                    }
                }}
                className="p-1 hover:bg-emerald-500/20 rounded transition-colors text-gray-500 hover:text-emerald-400"
                title={language === 'zh' ? '导出 CSV' : 'Export CSV'}
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
                                <div className="text-[9px] font-mono uppercase text-gray-500 mb-1">
                                  {agentAnalysis ? (language === 'zh' ? 'Agent 推荐' : 'Agent stage') : t.diagnosis.predicted}
                                </div>
                                <div className={`text-3xl font-black tracking-tighter mb-1 ${flags.isT4 || flags.hasMetastasis ? 'text-red-500' : 'text-emerald-400'}`}>
                                    {agentAnalysis?.report.recommended_t_stage
                                      ? `${agentAnalysis.report.recommended_t_stage}${nStage}`
                                      : `${tStage}${nStage}`}
                                </div>
                                <div className="text-[8px] font-mono text-gray-500">
                                  CONF: {agentAnalysis ? formatAgentConfidence(agentAnalysis.report.confidence) : `${confidence.overall}%`}
                                </div>
                                {agentAnalysis && (
                                  <div className="mt-1 text-[8px] font-mono text-purple-400/80">
                                    CBM: {tStage}{nStage}
                                  </div>
                                )}
                            </div>

                            {/* Right: Gauge */}
                            {renderRiskGauge(Math.floor((scores.t + scores.n)/2))}
                        </div>
                </div>

                {preoperativeAdvice && (
                  <div className="shrink-0 border-b border-neutral-800 bg-neutral-900/30">
                    <details className="group" open>
                      <summary className="px-3 py-2.5 cursor-pointer flex items-center justify-between text-xs font-bold text-gray-400 uppercase tracking-wider hover:bg-white/5">
                        <span className="flex items-center gap-2">
                          <FileText size={14} className="text-blue-400" />
                          {language === 'zh' ? '术前决策建议' : 'Preop Advice'}
                        </span>
                        <ChevronDown size={14} className="group-open:rotate-180 transition-transform" />
                      </summary>
                      <div className="px-3 pb-3 space-y-2">
                        <div className="text-xs p-2.5 bg-blue-500/10 border border-blue-500/20 rounded text-blue-300 leading-relaxed">
                          {preoperativeAdvice.overallAssessment}
                        </div>
                        <div className="text-[10px] text-gray-400 space-y-1">
                          {preoperativeAdvice.recommendedWorkup.map((item, i) => (
                            <div key={i}>• {item}</div>
                          ))}
                        </div>
                      </div>
                    </details>
                  </div>
                )}

                {reasoning && (
                  <div className="shrink-0 border-b border-neutral-800 bg-neutral-900/30">
                    <details className="group">
                      <summary className="px-3 py-2.5 cursor-pointer flex items-center justify-between text-xs font-bold text-gray-400 uppercase tracking-wider hover:bg-white/5">
                        <span className="flex items-center gap-2">
                          <Activity size={14} />
                          {language === 'zh' ? '分期推理依据' : 'Staging Rationale'}
                        </span>
                        <ChevronDown size={14} className="group-open:rotate-180 transition-transform" />
                      </summary>
                      <div className="px-3 pb-3 space-y-2 text-[10px]">
                        {reasoning.tStageFactors.slice(0, 3).map((f, i) => (
                          <div key={`t-${i}`} className={f.impact === 'negative' ? 'text-red-400' : 'text-gray-400'}>{f.factor}</div>
                        ))}
                        {reasoning.nStageFactors.slice(0, 2).map((f, i) => (
                          <div key={`n-${i}`} className={f.impact === 'negative' ? 'text-red-400' : 'text-gray-400'}>{f.factor}</div>
                        ))}
                      </div>
                    </details>
                  </div>
                )}

                {agentAnalysis && (
                  <div className="shrink-0 px-3 py-2 border-b border-purple-500/20 bg-purple-500/5">
                    <div className="flex items-center justify-between gap-2 mb-1.5">
                      <span className="text-[9px] font-bold uppercase tracking-wider text-purple-300">
                        {language === 'zh' ? 'Agent 工具证据' : 'Agent tool evidence'}
                      </span>
                      {agentAnalysis.report.rag_gate && (
                        <span className="text-[8px] font-mono text-amber-300/80">
                          RAG {Math.round((agentAnalysis.report.rag_gate.rag_weight ?? 0) * 100)}%
                        </span>
                      )}
                    </div>
                    <div className="flex flex-wrap gap-1">
                      {Object.entries(agentAnalysis.report.tool_status || {}).slice(0, 6).map(([tool, status]) => (
                        <span key={tool} className="rounded border border-white/10 bg-black/30 px-1.5 py-0.5 text-[8px] font-mono text-gray-400">
                          {tool}: {status}
                        </span>
                      ))}
                    </div>
                    {agentClassificationProbs && (
                      <div className="mt-2 space-y-1">
                        {agentClassificationProbs.slice(0, 3).map(({ stage, prob }) => (
                          renderBar(stage, prob, stage.includes('4') ? 'bg-red-500' : stage.includes('3') ? 'bg-amber-500' : 'bg-emerald-500')
                        ))}
                      </div>
                    )}
                  </div>
                )}

                {/* Terminal */}
                <div className="flex-1 bg-black p-3 font-mono text-[10px] leading-relaxed text-gray-400 overflow-y-auto min-h-0 relative group custom-scrollbar" onClick={toggleExpanded}>
                <div className="absolute top-2 right-2 opacity-20 group-hover:opacity-50 transition-opacity cursor-pointer">
                    <Maximize2 size={12} />
                </div>
                {agentDraft && (
                  <div className="mb-2 rounded border border-emerald-500/20 bg-emerald-500/5 px-2 py-1 text-[9px] text-emerald-300">
                    {language === 'zh' ? 'Agent 动态报告已就绪，点击展开查看全文' : 'Agent dynamic report ready — expand for full text'}
                  </div>
                )}
                <pre className="whitespace-pre-wrap typing-cursor cursor-pointer">{agentDraft?.full_text?.slice(0, 600) || reportText}{agentDraft && agentDraft.full_text.length > 600 ? '…' : ''}</pre>
                </div>
            </>
        ) : patient ? (
            <div className="flex-1 overflow-y-auto p-4 space-y-4 animate-in fade-in duration-300 custom-scrollbar">
                 {/* Demographics */}
                 <div className="bg-linear-to-br from-neutral-900/50 to-neutral-800/30 p-3 rounded-lg border border-white/5 hover:border-blue-500/30 transition-colors">
                    <div className="text-[10px] text-gray-500 uppercase tracking-wider mb-1 flex items-center gap-1"><User size={10}/> {t.diagnosis.demographics}</div>
                    <div className="text-sm text-gray-200 font-mono">
                        {patient.clinical ? `${patient.clinical.sex}, ${patient.clinical.age ?? 'N/A'}y` : (language === 'zh' ? '当前病例未挂接临床摘要' : 'No safe clinical summary attached')}
                    </div>
                    {patient.clinical?.location && (
                        <div className="text-[10px] text-gray-500 mt-1">{patient.clinical.location}</div>
                    )}
                 </div>

                 {/* Tumor Size */}
                 <div className="bg-linear-to-br from-neutral-900/50 to-neutral-800/30 p-3 rounded-lg border border-white/5 hover:border-blue-500/30 transition-colors">
                    <div className="text-[10px] text-gray-500 uppercase tracking-wider mb-1 flex items-center gap-1"><Ruler size={10}/> {t.diagnosis.tumor_size}</div>
                    <div className="text-sm text-gray-200 font-mono">
                        {patient.clinical ? `${patient.clinical.tumorSize.length ?? 'N/A'} × ${patient.clinical.tumorSize.thickness ?? 'N/A'} cm` : 'N/A × N/A cm'}
                    </div>
                 </div>

                 {/* Biomarkers */}
                 <div className="bg-linear-to-br from-neutral-900/50 to-neutral-800/30 p-3 rounded-lg border border-white/5">
                    <div className="text-[10px] text-gray-500 uppercase tracking-wider mb-2 flex items-center gap-1"><Activity size={10}/> {t.diagnosis.biomarkers}</div>
                    <div className="space-y-2">
                        <div className="flex justify-between items-center text-xs p-2 rounded bg-neutral-800/30">
                            <span className="text-gray-400">CEA</span>
                            <div className="flex items-center gap-2">
                                <span className={`font-mono font-bold ${patient.clinical?.biomarkers.cea_positive ? 'text-red-400' : 'text-emerald-400'}`}>
                                    {patient.clinical?.biomarkers.cea ?? 'N/A'} ng/ml
                                </span>
                                {patient.clinical?.biomarkers.cea_positive && (
                                    <span className="text-[8px] bg-red-500/20 text-red-400 px-1.5 py-0.5 rounded border border-red-500/30">+</span>
                                )}
                            </div>
                        </div>
                        <div className="flex justify-between items-center text-xs p-2 rounded bg-neutral-800/30">
                            <span className="text-gray-400">CA19-9</span>
                            <div className="flex items-center gap-2">
                                <span className={`font-mono font-bold ${patient.clinical?.biomarkers.ca199_positive ? 'text-red-400' : 'text-emerald-400'}`}>
                                    {patient.clinical?.biomarkers.ca199 ?? 'N/A'} U/ml
                                </span>
                                {patient.clinical?.biomarkers.ca199_positive && (
                                    <span className="text-[8px] bg-red-500/20 text-red-400 px-1.5 py-0.5 rounded border border-red-500/30">+</span>
                                )}
                            </div>
                        </div>
                    </div>
                 </div>

                 {/* Case Summary */}
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

                 {patientReportRows.length > 0 && (
                    <div className="bg-linear-to-br from-cyan-900/20 to-slate-800/20 p-3 rounded-lg border border-cyan-500/30">
                      <div className="text-[10px] text-gray-400 uppercase tracking-wider mb-2 flex items-center gap-1">
                        <FileText size={10} className="text-cyan-400"/>
                        {language === 'zh' ? '报告文本证据' : 'Report Text Evidence'}
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
