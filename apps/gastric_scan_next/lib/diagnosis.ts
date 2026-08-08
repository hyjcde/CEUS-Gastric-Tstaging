import { CONCEPT_CONFIGS } from './medical-config';
import { ConceptState, Patient } from '@/types';

export interface DiagnosisResult {
  tStage: string;
  nStage: string;
  probabilities: {
    t4: number;
    t3: number;
    t2: number; // T1/T2
    n3: number;
    n2: number;
    n1: number;
    n0: number;
  };
  confidence: {
    t: number;
    n: number;
    overall: number;
  };
  scores: {
    t: number;
    n: number;
  };
  flags: {
    isT4: boolean;
    hasMetastasis: boolean;
    highRisk: boolean;
  };
  // 与病理金标准的对比（仅在有病理数据时存在）
  validation?: {
    groundTruth: { t: string; n: string; m: string; stage: string } | null;
    tMatch: boolean;
    nMatch: boolean;
    discrepancy: 'none' | 'minor' | 'major';
    discrepancyExplanation: string;
  };
  // 详细推理过程
  reasoning: {
    tStageFactors: Array<{ factor: string; contribution: string; impact: 'positive' | 'negative' | 'neutral' }>;
    nStageFactors: Array<{ factor: string; contribution: string; impact: 'positive' | 'negative' | 'neutral' }>;
    limitations: string[];
    clinicalSuggestions: string[];
  };
  // 新增：术前决策建议（核心临床价值）
  preoperativeAdvice: {
    overallAssessment: string;  // 综合评估
    urgency: 'routine' | 'priority' | 'urgent';  // 紧迫程度
    recommendedWorkup: string[];  // 建议完善检查
    treatmentConsiderations: string[];  // 治疗考量
    mdtRequired: boolean;  // 是否需要MDT
    uncertaintyNotes: string[];  // 不确定性说明
  };
}

export function calculateDiagnosis(state: ConceptState, patient?: Patient | null): DiagnosisResult {
  // ---------------------------------------------------------
  // Enhanced Logic for Probabilities (Based on updated CBM)
  // ---------------------------------------------------------
  
  // T-Stage Logic with detailed factor tracking
  const tStageFactors: DiagnosisResult['reasoning']['tStageFactors'] = [];
  
  const proliferationScore = state.c1 * 0.4 + state.c3 * 0.3;
  if (state.c1 > 50) {
    tStageFactors.push({ 
      factor: `Ki-67 高表达 (${state.c1}%)`, 
      contribution: '提示高增殖活性，倾向进展期', 
      impact: 'negative' 
    });
  } else if (state.c1 > 30) {
    tStageFactors.push({ 
      factor: `Ki-67 中等 (${state.c1}%)`, 
      contribution: '增殖活性中等', 
      impact: 'neutral' 
    });
  } else {
    tStageFactors.push({ 
      factor: `Ki-67 低表达 (${state.c1}%)`, 
      contribution: '增殖活性低，倾向早期', 
      impact: 'positive' 
    });
  }

  const invasionScore = (state.vascularInvasion ? 30 : 0) + (state.neuralInvasion ? 20 : 0);
  if (state.vascularInvasion) {
    tStageFactors.push({ 
      factor: '脉管侵犯 (LVI+)', 
      contribution: '显著增加局部进展风险 (+30分)', 
      impact: 'negative' 
    });
  }
  if (state.neuralInvasion) {
    tStageFactors.push({ 
      factor: '神经侵犯 (PNI+)', 
      contribution: '增加局部复发风险 (+20分)', 
      impact: 'negative' 
    });
  }

  const diffVal = state.differentiation || 2;
  const differentiationPenalty = (diffVal - 1) * 8; 
  const diffLabels = ['高分化', '中分化', '中-低分化', '低分化', '未知'];
  if (diffVal >= 3) {
    tStageFactors.push({ 
      factor: `分化程度: ${diffLabels[diffVal - 1] || '低分化'}`, 
      contribution: '低分化与更深浸润相关', 
      impact: 'negative' 
    });
  }

  const tScore = Math.min(100, proliferationScore * 0.5 + invasionScore + differentiationPenalty);
  
  const probT4 = Math.max(0, Math.min(100, tScore));
  const probT3 = Math.max(0, Math.min(100, (100 - probT4) * 0.7));
  const probT2 = 100 - probT4 - probT3;

  const isT4 = probT4 > 60;
  const tStage = isT4 ? "T4a" : (probT3 > 45 ? "T3" : "T1/T2");
  const tConf = Math.floor(Math.max(probT4, probT3, probT2));

  // N-Stage Logic with detailed factor tracking
  const nStageFactors: DiagnosisResult['reasoning']['nStageFactors'] = [];
  
  const immuneScore = state.c4 * 0.5 + state.c2 * 0.3;
  if (state.c4 > 30) {
    nStageFactors.push({ 
      factor: `FoxP3 高 (${state.c4}%)`, 
      contribution: 'Treg 浸润增加，免疫抑制微环境', 
      impact: 'negative' 
    });
  }
  if (state.c2 > 10) {
    nStageFactors.push({ 
      factor: `CPS 阳性 (${state.c2})`, 
      contribution: 'PD-L1 表达，可能对免疫治疗敏感', 
      impact: 'neutral' 
    });
  }

  const microEnvScore = (state.c6 > state.c7) ? 20 : 0; 
  if (state.c6 > state.c7) {
    nStageFactors.push({ 
      factor: 'CD4/CD8 比值倒置', 
      contribution: 'CD4 > CD8，可能提示免疫失调', 
      impact: 'negative' 
    });
  }

  const laurenVal = state.lauren ?? 1;
  const laurenRisk = (laurenVal === 0) ? 30 : (laurenVal === 4 ? 15 : 0);
  const laurenLabels = ['弥漫型', '肠型', '混合型', '未知'];
  if (laurenVal === 0) {
    nStageFactors.push({ 
      factor: `Lauren 分型: 弥漫型`, 
      contribution: '弥漫型与更高淋巴结转移率相关', 
      impact: 'negative' 
    });
  } else if (laurenVal === 1) {
    nStageFactors.push({ 
      factor: `Lauren 分型: 肠型`, 
      contribution: '肠型预后相对较好', 
      impact: 'positive' 
    });
  }

  const nScore = Math.min(100, immuneScore + microEnvScore + laurenRisk);
  
  const probN3 = Math.max(0, Math.min(100, nScore * 0.8));
  const probN2 = Math.max(0, Math.min(100, (nScore - 30) * 0.6));
  const probN1 = Math.max(0, Math.min(100, (nScore - 20) * 0.5));
  const probN0 = Math.max(0, 100 - probN3 - probN2 - probN1);
  
  const nStage = probN3 > 50 ? "N3" : (probN2 > 40 ? "N2" : (probN1 > 30 ? "N1" : "N0"));
  const nConf = Math.floor(Math.max(probN0, probN1, probN2, probN3));
  
  const hasMetastasis = nStage !== "N0";
  const highRisk = isT4 || state.c4 > 60 || state.c3 > 60 || state.vascularInvasion === 1;
  const stageConfidence = Math.floor((tConf + nConf) / 2);

  // 模型局限性说明
  const limitations: string[] = [
    '本模型基于免疫组化特征推断，未整合影像学深度信息',
    '超声图像分辨率可能影响边界判断准确性',
    '模型训练数据以中国人群为主，跨人群泛化性待验证'
  ];

  // 临床建议
  const clinicalSuggestions: string[] = [];
  if (highRisk) {
    clinicalSuggestions.push('建议多学科会诊 (MDT) 讨论治疗方案');
    clinicalSuggestions.push('考虑新辅助化疗评估');
  }
  if (state.vascularInvasion || state.neuralInvasion) {
    clinicalSuggestions.push('术后需密切随访，警惕局部复发');
  }
  if (state.c2 > 5) {
    clinicalSuggestions.push('CPS 阳性，可考虑免疫检查点抑制剂');
  }
  if (clinicalSuggestions.length === 0) {
    clinicalSuggestions.push('倾向早期病变，建议规范手术切除');
    clinicalSuggestions.push('术后定期随访监测');
  }

  // 术前决策建议（核心临床价值）
  const preoperativeAdvice = generatePreoperativeAdvice(
    tStage, nStage, tScore, nScore, highRisk, 
    state, tStageFactors, nStageFactors
  );

  // 当前前端默认使用脱敏术前数据，不做术后病理校验。
  const validation: DiagnosisResult['validation'] = undefined;

  return {
    tStage,
    nStage,
    probabilities: {
      t4: probT4,
      t3: probT3,
      t2: probT2,
      n3: probN3,
      n2: probN2,
      n1: probN1,
      n0: probN0
    },
    confidence: {
      t: tConf,
      n: nConf,
      overall: stageConfidence
    },
    scores: {
      t: tScore,
      n: nScore
    },
    flags: {
      isT4,
      hasMetastasis,
      highRisk
    },
    validation,
    reasoning: {
      tStageFactors,
      nStageFactors,
      limitations,
      clinicalSuggestions
    },
    preoperativeAdvice
  };
}

// 生成术前决策建议
function generatePreoperativeAdvice(
  tStage: string,
  nStage: string,
  tScore: number,
  nScore: number,
  highRisk: boolean,
  state: ConceptState,
  tFactors: DiagnosisResult['reasoning']['tStageFactors'],
  nFactors: DiagnosisResult['reasoning']['nStageFactors']
): DiagnosisResult['preoperativeAdvice'] {
  
  const isAdvanced = tStage.includes('3') || tStage.includes('4') || nStage !== 'N0';
  const isEarly = tStage === 'T1/T2' && nStage === 'N0';
  
  // 综合评估
  let overallAssessment = '';
  if (isEarly) {
    overallAssessment = `倾向早期胃癌 (c${tStage}${nStage})，预后较好。建议评估内镜下切除或腹腔镜手术可行性。`;
  } else if (highRisk || tStage.includes('4')) {
    overallAssessment = `进展期胃癌可能性大 (c${tStage}${nStage})，存在多项高危因素。强烈建议多学科讨论，评估新辅助治疗获益。`;
  } else {
    overallAssessment = `局部进展期胃癌 (c${tStage}${nStage})，需综合评估手术时机和方案。`;
  }
  
  // 紧迫程度
  let urgency: 'routine' | 'priority' | 'urgent' = 'routine';
  if (tStage.includes('4') || state.vascularInvasion) {
    urgency = 'urgent';
  } else if (isAdvanced || highRisk) {
    urgency = 'priority';
  }
  
  // 建议完善检查
  const recommendedWorkup: string[] = [];
  if (isAdvanced) {
    recommendedWorkup.push('腹部增强 CT 评估浸润深度及远处转移');
    recommendedWorkup.push('内镜超声 (EUS) 精确评估 T 分期');
  }
  if (nStage !== 'N0' || nScore > 30) {
    recommendedWorkup.push('PET-CT 排除远处转移');
  }
  if (state.c2 > 5) {
    recommendedWorkup.push('完善 HER2 检测，评估靶向治疗可能');
  }
  if (recommendedWorkup.length === 0) {
    recommendedWorkup.push('常规术前检查（血常规、生化、肿瘤标志物）');
    recommendedWorkup.push('胃镜复查确认病变范围');
  }
  
  // 治疗考量
  const treatmentConsiderations: string[] = [];
  if (isEarly) {
    treatmentConsiderations.push('符合 ESD 指征可考虑内镜下切除');
    treatmentConsiderations.push('腹腔镜远端/近端胃切除术');
  } else if (highRisk) {
    treatmentConsiderations.push('新辅助化疗 (SOX/XELOX/FLOT) 后再评估手术');
    treatmentConsiderations.push('术后辅助化疗必要性高');
  } else {
    treatmentConsiderations.push('根治性胃切除 + D2 淋巴结清扫');
    treatmentConsiderations.push('术后根据病理结果决定辅助治疗');
  }
  if (state.c2 > 10) {
    treatmentConsiderations.push('CPS ≥ 10，可考虑免疫联合化疗');
  }
  
  // 是否需要MDT
  const mdtRequired = highRisk || tStage.includes('4') || nStage === 'N3';
  
  // 不确定性说明
  const uncertaintyNotes: string[] = [
    '术前分期准确率约 70-85%，最终以术后病理为准',
    '超声对微小淋巴结转移检出率有限，可能存在低估'
  ];
  
  // 根据置信度添加不确定性说明
  const avgConfidence = (tScore + nScore) / 2;
  if (avgConfidence < 50) {
    uncertaintyNotes.push('当前预测置信度偏低，建议结合其他影像学检查综合判断');
  }
  
  // 根据高危因素数量
  const highRiskFactorCount = tFactors.filter(f => f.impact === 'negative').length + 
                              nFactors.filter(f => f.impact === 'negative').length;
  if (highRiskFactorCount >= 3) {
    uncertaintyNotes.push(`存在 ${highRiskFactorCount} 项高危因素，实际分期可能偏晚`);
  }
  
  return {
    overallAssessment,
    urgency,
    recommendedWorkup,
    treatmentConsiderations,
    mdtRequired,
    uncertaintyNotes
  };
}

export function getFeatureDescriptions(state: ConceptState, language: 'zh' | 'en') {
  const replaceVal = (text: string, val: number) => text.replace('{val}', val.toString());
  const getDesc = (key: 'c1' | 'c2' | 'c3' | 'c4') => {
    const config = CONCEPT_CONFIGS[key];
    const val = state[key];
    const descs = config.descriptions[language];
    
    if (val >= config.thresholds.danger) return replaceVal(descs.high, val);
    if (val >= config.thresholds.warning) return replaceVal(descs.mid, val);
    return replaceVal(descs.low, val);
  };

  return {
    ki67: getDesc('c1'),
    cps: getDesc('c2'),
    pd1: getDesc('c3'),
    foxp3: getDesc('c4'),
  };
}

export function generateNarrativeReport(
  state: ConceptState, 
  diagnosis: DiagnosisResult, 
  patient: Patient | null, 
  language: 'zh' | 'en'
): string[] {
  const { tStage, nStage, confidence, flags, validation, reasoning } = diagnosis;
  const lines: string[] = [];
  const timeStr = new Date().toISOString().split('T')[1].substring(0, 8);
  const dateStr = new Date().toLocaleDateString(language !== 'en' ? 'zh-CN' : 'en-US');
  const clin = patient?.clinical;

  const descriptions = getFeatureDescriptions(state, language);

  if (language !== 'en') {
    // ==================== 报告头 ====================
    lines.push(`╔══════════════════════════════════════════════════════════════╗`);
    lines.push(`║           胃癌 T/N 分期 AI 辅助诊断报告                       ║`);
    lines.push(`╚══════════════════════════════════════════════════════════════╝`);
    lines.push(``);
    
    // ==================== 患者信息 ====================
    lines.push(`【患者信息】`);
    lines.push(`  病例号: ${patient?.id_short ?? '未知'}`);
    if (clin) {
      lines.push(`  性  别: ${clin.sex === 'Male' ? '男' : '女'}    年龄: ${clin.age}岁`);
      lines.push(`  部  位: ${clin.location || '未记录'}`);
      if (clin.tumorSize?.length || clin.tumorSize?.thickness) {
        lines.push(`  肿瘤大小: ${clin.tumorSize.length ?? '?'} × ${clin.tumorSize.thickness ?? '?'} cm`);
      }
    }
    lines.push(`  报告时间: ${dateStr} ${timeStr}`);
    lines.push(``);

    // ==================== AI 预测结果 ====================
    lines.push(`【AI 预测结果】`);
    lines.push(`  ┌─────────────────────────────────────────────────────────┐`);
    lines.push(`  │  预测分期: ${tStage}${nStage}                                          │`);
    lines.push(`  │  置信度: T分期 ${confidence.t}% | N分期 ${confidence.n}% | 综合 ${confidence.overall}%  │`);
    lines.push(`  │  风险等级: ${flags.highRisk ? '⚠️ 高危' : '✓ 低危'}                                    │`);
    lines.push(`  └─────────────────────────────────────────────────────────┘`);
    lines.push(``);

    // ==================== 与病理金标准对比 ====================
    if (validation) {
      lines.push(`【病理金标准对比】`);
      lines.push(`  术后病理: p${validation.groundTruth?.t}${validation.groundTruth?.n}${validation.groundTruth?.m} (Stage ${validation.groundTruth?.stage})`);
      lines.push(`  AI 预测: ${tStage}${nStage}`);
      
      if (validation.discrepancy === 'none') {
        lines.push(`  ✓ 预测与病理一致`);
      } else if (validation.discrepancy === 'minor') {
        lines.push(`  △ 轻微差异 (临床可接受)`);
        lines.push(`    ${validation.discrepancyExplanation}`);
    } else {
        lines.push(`  ⚠️ 显著差异 - 需关注`);
        lines.push(`    ${validation.discrepancyExplanation}`);
      }
      lines.push(``);
    }

    // ==================== 推理依据 ====================
    lines.push(`【T 分期推理依据】`);
    reasoning.tStageFactors.forEach(f => {
      const icon = f.impact === 'negative' ? '↑' : f.impact === 'positive' ? '↓' : '→';
      lines.push(`  ${icon} ${f.factor}`);
      lines.push(`    └─ ${f.contribution}`);
    });
    lines.push(``);

    lines.push(`【N 分期推理依据】`);
    reasoning.nStageFactors.forEach(f => {
      const icon = f.impact === 'negative' ? '↑' : f.impact === 'positive' ? '↓' : '→';
      lines.push(`  ${icon} ${f.factor}`);
      lines.push(`    └─ ${f.contribution}`);
    });
    lines.push(``);

    // ==================== 免疫组化特征 ====================
    lines.push(`【免疫组化特征分析】`);
    lines.push(`  • Ki-67: ${descriptions.ki67}`);
    lines.push(`  • CPS:   ${descriptions.cps}`);
    lines.push(`  • PD-1:  ${descriptions.pd1}`);
    lines.push(`  • FoxP3: ${descriptions.foxp3}`);
    if (state.vascularInvasion) lines.push(`  • 脉管侵犯: 阳性 (LVI+) ⚠️`);
    if (state.neuralInvasion) lines.push(`  • 神经侵犯: 阳性 (PNI+) ⚠️`);
    lines.push(``);

    // ==================== 临床建议 ====================
    lines.push(`【临床建议】`);
    reasoning.clinicalSuggestions.forEach((s, i) => {
      lines.push(`  ${i + 1}. ${s}`);
    });
    lines.push(``);

    // ==================== 模型局限性 ====================
    lines.push(`【模型局限性说明】`);
    reasoning.limitations.forEach(l => {
      lines.push(`  • ${l}`);
    });
    lines.push(``);

    // ==================== 免责声明 ====================
    lines.push(`────────────────────────────────────────────────────────────────`);
    lines.push(`⚕️ 本报告由 AI 辅助生成，仅供临床参考，不能替代医生诊断。`);
    lines.push(`   最终诊断请结合病理、影像及临床综合判断。`);
    lines.push(`────────────────────────────────────────────────────────────────`);

  } else {
    // English version
    lines.push(`╔══════════════════════════════════════════════════════════════╗`);
    lines.push(`║      Gastric Cancer T/N Staging AI Diagnostic Report         ║`);
    lines.push(`╚══════════════════════════════════════════════════════════════╝`);
    lines.push(``);
    
    lines.push(`[PATIENT INFORMATION]`);
    lines.push(`  Case ID: ${patient?.id_short ?? 'N/A'}`);
    if (clin) {
      lines.push(`  Sex: ${clin.sex}    Age: ${clin.age}y`);
      lines.push(`  Location: ${clin.location || 'Not recorded'}`);
    }
    lines.push(`  Report Time: ${dateStr} ${timeStr}`);
    lines.push(``);

    lines.push(`[AI PREDICTION]`);
    lines.push(`  Predicted Stage: ${tStage}${nStage}`);
    lines.push(`  Confidence: T ${confidence.t}% | N ${confidence.n}% | Overall ${confidence.overall}%`);
    lines.push(`  Risk Level: ${flags.highRisk ? '⚠️ HIGH RISK' : '✓ LOW RISK'}`);
    lines.push(``);

    if (validation) {
      lines.push(`[PATHOLOGY COMPARISON]`);
      lines.push(`  Ground Truth: p${validation.groundTruth?.t}${validation.groundTruth?.n}${validation.groundTruth?.m}`);
      lines.push(`  AI Prediction: ${tStage}${nStage}`);
      lines.push(`  ${validation.discrepancy === 'none' ? '✓ Match' : validation.discrepancy === 'minor' ? '△ Minor discrepancy' : '⚠️ Major discrepancy'}`);
      if (validation.discrepancyExplanation) {
        lines.push(`  Note: ${validation.discrepancyExplanation}`);
      }
        lines.push(``);
    }

    lines.push(`[REASONING FACTORS]`);
    lines.push(`T-Stage:`);
    reasoning.tStageFactors.forEach(f => {
      lines.push(`  • ${f.factor}: ${f.contribution}`);
    });
    lines.push(`N-Stage:`);
    reasoning.nStageFactors.forEach(f => {
      lines.push(`  • ${f.factor}: ${f.contribution}`);
    });
    lines.push(``);

    lines.push(`[CLINICAL RECOMMENDATIONS]`);
    reasoning.clinicalSuggestions.forEach((s, i) => {
      lines.push(`  ${i + 1}. ${s}`);
    });
    lines.push(``);

    lines.push(`────────────────────────────────────────────────────────────────`);
    lines.push(`⚕️ AI-assisted report for reference only. Final diagnosis`);
    lines.push(`   requires clinical, pathological, and imaging correlation.`);
    lines.push(`────────────────────────────────────────────────────────────────`);
  }

  return lines;
}

export function generateSummaryPoints(
  state: ConceptState,
  diagnosis: DiagnosisResult,
  patient: Patient | null,
  language: 'zh' | 'en'
): string[] {
  const { tStage, nStage, flags } = diagnosis;
  
  const inferencePoint = language !== 'en'
    ? `模型结合 Ki-67/CPS/FoxP3/Lauren分型 推断 ${tStage}${nStage}，侵犯与微环境指标支持该结论。`
    : `Model fuses Ki-67/CPS/FoxP3/Lauren dynamics to infer ${tStage}${nStage}, supported by invasion/TME markers.`;

  const clinicalCorrelation = patient?.clinical
    ? language !== 'en'
      ? `分化${patient.clinical.differentiation || '待补充'}，Lauren ${patient.clinical.lauren || '待补充'}，CEA ${patient.clinical.biomarkers.cea ?? 'N/A'}${patient.clinical.biomarkers.cea_positive ? ' +' : ''}。`
      : `Differentiation ${patient.clinical.differentiation || 'pending'}, Lauren ${patient.clinical.lauren || 'pending'}; biomarkers CEA ${patient.clinical.biomarkers.cea ?? 'N/A'}${patient.clinical.biomarkers.cea_positive ? ' +' : ''}.`
    : language !== 'en'
      ? '临床摘要待补录。'
      : 'Clinical summary pending.';

  const actionPoint = flags.highRisk
    ? language !== 'en'
      ? '高危预警：建议多学科(MDT)讨论，特别是关于新辅助治疗的介入时机。'
      : 'High Risk Alert: Recommend MDT discussion regarding timing of neoadjuvant therapy.'
    : language !== 'en'
      ? '低危提示：建议定期复查监测 Ki-67 及免疫指标变化。'
      : 'Low Risk: Monitor Ki-67 and immune markers regularly.';

  return [inferencePoint, clinicalCorrelation, actionPoint];
}

