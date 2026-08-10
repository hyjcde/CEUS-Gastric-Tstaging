import { deepToTraditionalHK } from '@/lib/zh-convert';

export type Language = 'en' | 'zh' | 'zh-HK';

export function isChineseLocale(language: Language): boolean {
  return language === 'zh' || language === 'zh-HK';
}

export function languageLabel(language: Language): string {
  if (language === 'en') return 'EN';
  if (language === 'zh-HK') return '繁中';
  return '简中';
}

/** Cycle: 简体 → 香港繁體 → EN → 简体 */
export function nextLanguage(language: Language): Language {
  if (language === 'zh') return 'zh-HK';
  if (language === 'zh-HK') return 'en';
  return 'zh';
}

const en = {
  title: 'Gastric Filling Ultrasound Intelligent Diagnosis',
  subtitle: 'Clinical Intelligence Workstation',
  hospital: 'FUJIAN XIEHE ULTRASOUND',
  dept: 'Dept.US',
  protocol: 'GC_Protocol',
  live: 'LIVE_SESSION',
  status: {
    model: 'Model: Research Prototype',
    gpu: 'GPU ACCEL',
  },
  userMenu: {
    name: 'Dr. Lin',
    role: 'Chief Physician',
    profile: 'Profile',
    reports: 'My Reports',
    settings: 'System Settings',
    signout: 'Sign Out',
  },
  nav: {
    annotator: 'Annotation',
    annotatorTitle: 'Open direction annotation tool',
    videoAnnotator: 'Video Platform',
    videoAnnotatorTitle: 'Open MedDINO video/static annotation platform',
    readingAgent: 'Reader Agent',
    readingAgentTitle: 'Open SAM + wall-layer interactive reader agent',
    humanAssist: 'Human Assist',
    humanAssistTitle: 'Open contact-geometry human-assist demo for current case',
  },
  cohort: {
    title: 'Study Cohort',
    search: 'Filter by PID / MRN...',
    loading: 'Loading Cohort...',
    total: 'TOTAL',
  },
  viewer: {
    noData: 'No Imaging Data Loaded',
    source: 'Source',
    cropUi: 'CROP UI',
    originalView: 'ORIGINAL',
    seg: 'Seg',
    xai: 'XAI',
    contrast: 'Contrast',
    ruler: 'Ruler',
    bmode: 'B-MODE',
    mask: 'AI SEGMENTATION',
    heatmap: 'GRAD-CAM ATTENTION MAP',
    detect: 'Detection',
    detection_box: 'Detection ROI',
    detection_missing: 'ROI not available',
  },
  reasoning: {
    title: 'Pathology Features (CBM)',
    interactive: 'Interactive',
    sliders: {
      c1: 'Serosa Continuity',
      c2: 'Wall Stiffness',
      c3: 'Doppler Flow',
      c4: 'Lymph Node Axis',
      labels: {
        c1: ['Intact', 'Disrupted'],
        c2: ['Soft (Normal)', 'Hard (Fibrosis)'],
        c3: ['Hypovascular', 'Hypervascular'],
        c4: ['S/L < 0.5', 'S/L > 0.5'],
      },
    },
  },
  diagnosis: {
    title: 'Diagnosis',
    predicted: 'Predicted Stage',
    confidence: 'Model Confidence',
    risk_high: 'HIGH RISK',
    risk_low: 'LOW RISK',
    serosa_invaded: 'Serosa Invaded',
    localized: 'Subserosa/Muscularis',
    invasion_detected: 'SEROSA INVASION DETECTED',
    localized_disease: 'LOCALIZED DISEASE',
    report_header: 'Automated Report',
    waiting: 'Waiting for input...',
    clinical: 'Clinical Data',
    no_clinical: 'No Clinical Data Available',
    demographics: 'Demographics',
    tumor_size: 'Tumor Size',
    biomarkers: 'Biomarkers',
    case_summary: 'Case Summary',
    segmentation_assets: 'Segmentation Assets',
    agent_readiness: 'Agent Draft',
    pathology: 'Pathology',
    ground_truth: 'Ground Truth (Post-Op)',
    ai_vs_gt: 'AI vs Ground Truth',
    ai_prediction: 'AI Prediction',
    post_op_pathology: 'Post-Op Pathology',
    prediction_matched: 'Prediction Matched',
    available_data: 'Available Data',
    imaging_only: 'Imaging analysis and AI prediction only',
  },
} as const;

const zh = {
  title: '胃充盈超声智能诊断系统',
  subtitle: '临床智能工作台',
  hospital: '福建协和医院超声科',
  dept: '超声科',
  protocol: '胃癌分期协议',
  live: '实时会诊',
  status: {
    model: '模型: 研究型模型',
    gpu: 'GPU 加速中',
  },
  userMenu: {
    name: '林医生',
    role: '主任医师',
    profile: '个人资料',
    reports: '我的报告',
    settings: '系统设置',
    signout: '退出登录',
  },
  nav: {
    annotator: '方向标注',
    annotatorTitle: '打开突破方向标注工具',
    videoAnnotator: '视频标注',
    videoAnnotatorTitle: '打开 MedDINO 视频/静态图标注平台',
    readingAgent: '阅片Agent',
    readingAgentTitle: '打开 SAM + 胃壁分层交互阅片 Agent',
    humanAssist: '人机互助',
    humanAssistTitle: '打开接触几何人机互助演示（当前病例深链）',
  },
  cohort: {
    title: '研究队列',
    search: '搜索 PID / 病历号...',
    loading: '加载队列中...',
    total: '总计',
  },
  viewer: {
    noData: '未加载影像数据',
    source: '主视图',
    cropUi: 'CROP UI',
    originalView: '原图',
    seg: '分割',
    xai: '热力图',
    contrast: '对比',
    ruler: '标尺',
    bmode: '二维超声 (B-Mode)',
    mask: 'AI 分割掩膜',
    heatmap: 'Grad-CAM 注意力图',
    detect: '检测',
    detection_box: '检测 ROI',
    detection_missing: 'ROI 数据缺失',
  },
  reasoning: {
    title: '病理特征推理 (CBM)',
    interactive: '交互模式',
    sliders: {
      c1: '浆膜层连续性',
      c2: '胃壁硬度 (弹性)',
      c3: '多普勒血流',
      c4: '淋巴结长短径比',
      labels: {
        c1: ['连续完整', '明显中断'],
        c2: ['软 (正常)', '硬 (纤维化)'],
        c3: ['乏血供', '富血供'],
        c4: ['S/L < 0.5', 'S/L > 0.5'],
      },
    },
  },
  diagnosis: {
    title: '智能诊断',
    predicted: '预测分期',
    confidence: '置信度',
    risk_high: '高风险',
    risk_low: '低风险',
    serosa_invaded: '浆膜受侵',
    localized: '局限于肌层/浆膜下',
    invasion_detected: '检测到浆膜侵犯',
    localized_disease: '局限性病变',
    report_header: 'AI 自动生成报告',
    waiting: '等待输入...',
    clinical: '临床数据',
    no_clinical: '无临床数据',
    demographics: '基本信息',
    tumor_size: '肿瘤大小',
    biomarkers: '肿瘤标志物',
    case_summary: '病例摘要',
    segmentation_assets: '分割资产',
    agent_readiness: 'Agent 草稿',
    pathology: '病理信息',
    ground_truth: '术后病理 (金标准)',
    ai_vs_gt: 'AI预测 vs 金标准',
    ai_prediction: 'AI预测',
    post_op_pathology: '术后病理',
    prediction_matched: '预测匹配',
    available_data: '可用数据',
    imaging_only: '仅影像分析和AI预测',
  },
} as const;

const zhHK = {
  title: '胃充盈超聲智能診斷系統',
  subtitle: '臨床智能工作台',
  hospital: '福建協和醫院超聲科',
  dept: '超聲科',
  protocol: '胃癌分期協議',
  live: '即時會診',
  status: {
    model: '模型: 研究型模型',
    gpu: 'GPU 加速中',
  },
  userMenu: {
    name: '林醫生',
    role: '主任醫生',
    profile: '個人資料',
    reports: '我的報告',
    settings: '系統設定',
    signout: '登出',
  },
  nav: {
    annotator: '方向標註',
    annotatorTitle: '打開突破方向標註工具',
    videoAnnotator: '影片標註',
    videoAnnotatorTitle: '打開 MedDINO 影片/靜態圖標註平台',
    readingAgent: '閱片 Agent',
    readingAgentTitle: '打開 SAM + 胃壁分層互動閱片 Agent',
    humanAssist: '人機互助',
    humanAssistTitle: '打開接觸幾何人機互助演示（目前病例深層連結）',
  },
  cohort: {
    title: '研究隊列',
    search: '搜尋 PID / 病歷號...',
    loading: '載入隊列中...',
    total: '總計',
  },
  viewer: {
    noData: '未載入影像資料',
    source: '主畫面',
    cropUi: 'CROP UI',
    originalView: '原圖',
    seg: '分割',
    xai: '熱力圖',
    contrast: '對比',
    ruler: '標尺',
    bmode: '二維超聲 (B-Mode)',
    mask: 'AI 分割掩膜',
    heatmap: 'Grad-CAM 注意力圖',
    detect: '檢測',
    detection_box: '檢測 ROI',
    detection_missing: 'ROI 資料缺失',
  },
  reasoning: {
    title: '病理特徵推理 (CBM)',
    interactive: '互動模式',
    sliders: {
      c1: '漿膜層連續性',
      c2: '胃壁硬度 (彈性)',
      c3: '多普勒血流',
      c4: '淋巴結長短徑比',
      labels: {
        c1: ['連續完整', '明顯中斷'],
        c2: ['軟 (正常)', '硬 (纖維化)'],
        c3: ['乏血供', '富血供'],
        c4: ['S/L < 0.5', 'S/L > 0.5'],
      },
    },
  },
  diagnosis: {
    title: '智能診斷',
    predicted: '預測分期',
    confidence: '置信度',
    risk_high: '高風險',
    risk_low: '低風險',
    serosa_invaded: '漿膜受侵',
    localized: '局限於肌層/漿膜下',
    invasion_detected: '檢測到漿膜侵犯',
    localized_disease: '局限性病變',
    report_header: 'AI 自動生成報告',
    waiting: '等待輸入...',
    clinical: '臨床資料',
    no_clinical: '無臨床資料',
    demographics: '基本資料',
    tumor_size: '腫瘤大小',
    biomarkers: '腫瘤標誌物',
    case_summary: '病例摘要',
    segmentation_assets: '分割資產',
    agent_readiness: 'Agent 草稿',
    pathology: '病理資料',
    ground_truth: '術後病理 (金標準)',
    ai_vs_gt: 'AI預測 vs 金標準',
    ai_prediction: 'AI預測',
    post_op_pathology: '術後病理',
    prediction_matched: '預測匹配',
    available_data: '可用資料',
    imaging_only: '僅影像分析和AI預測',
  },
} as const;

export const dictionary: Record<Language, typeof en> = {
  en,
  zh: zh as unknown as typeof en,
  // Keep hand-tuned zhHK as override layer; default zh-HK is auto-converted from Simplified.
  'zh-HK': zhHK as unknown as typeof en,
};

/** Resolve UI dictionary. zh-HK prefers OpenCC(s2hk) of Simplified, then merges explicit zhHK overrides. */
export function resolveDictionary(language: Language): typeof en {
  if (language !== 'zh-HK') {
    return dictionary[language];
  }
  const auto = deepToTraditionalHK(zh as unknown as typeof en);
  return deepMergeDict(auto, zhHK as unknown as typeof en);
}

function deepMergeDict<T>(base: T, override: T): T {
  if (typeof base === 'string' && typeof override === 'string') {
    return (override || base) as T;
  }
  if (Array.isArray(base) || Array.isArray(override) || typeof base !== 'object' || typeof override !== 'object' || !base || !override) {
    return (override ?? base) as T;
  }
  const out: Record<string, unknown> = { ...(base as Record<string, unknown>) };
  for (const [key, value] of Object.entries(override as Record<string, unknown>)) {
    out[key] = deepMergeDict((base as Record<string, unknown>)[key], value);
  }
  return out as T;
}
