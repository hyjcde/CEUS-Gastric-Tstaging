import { ConceptState } from '@/types';

export interface ConceptMetadata {
  id: keyof ConceptState;
  label: { zh: string; en: string };
  minLabel?: string;
  maxLabel?: string;
  thresholds: { warning: number; danger: number }; // e.g., 40, 70
  descriptions: {
    zh: { low: string; mid: string; high: string };
    en: { low: string; mid: string; high: string };
  };
}

// Standardized thresholds for consistency across UI (colors) and Diagnosis (text)
// Default: <40 (Low/Green), 40-70 (Mid/Amber), >70 (High/Red)
export const DEFAULT_THRESHOLDS = { warning: 40, danger: 70 };

export const CONCEPT_CONFIGS: Record<string, ConceptMetadata> = {
  c1: {
    id: 'c1',
    label: { zh: 'Ki-67 指数', en: 'Ki-67 Index' },
    minLabel: 'Low',
    maxLabel: 'High',
    thresholds: { warning: 40, danger: 70 },
    descriptions: {
      zh: {
        low: 'Ki-67较低 ({val}%)，惰性生长。',
        mid: 'Ki-67中等 ({val}%)，需观察。',
        high: 'Ki-67明显升高 ({val}%)，增殖活跃。'
      },
      en: {
        low: 'Ki-67 low ({val}%), indolent.',
        mid: 'Ki-67 mod ({val}%), monitor.',
        high: 'Ki-67 high ({val}%), aggressive.'
      }
    }
  },
  c2: {
    id: 'c2',
    label: { zh: 'CPS 评分', en: 'CPS Score' },
    minLabel: '0',
    maxLabel: '100',
    thresholds: { warning: 40, danger: 70 },
    descriptions: {
      zh: {
        low: 'CPS评分低 ({val})。',
        mid: 'CPS评分中等 ({val})。',
        high: 'CPS评分高 ({val})，免疫原性强。'
      },
      en: {
        low: 'CPS low ({val}).',
        mid: 'CPS mid ({val}).',
        high: 'CPS high ({val}), immunogenic.'
      }
    }
  },
  c3: {
    id: 'c3',
    label: { zh: 'PD-1 表达', en: 'PD-1 Exp' },
    minLabel: '-',
    maxLabel: '+',
    thresholds: { warning: 40, danger: 70 },
    descriptions: {
      zh: {
        low: 'PD-1低表达 ({val}%)。',
        mid: 'PD-1中表达 ({val}%)。',
        high: 'PD-1高表达 ({val}%)，提示免疫耗竭。'
      },
      en: {
        low: 'PD-1 low ({val}%).',
        mid: 'PD-1 moderate ({val}%).',
        high: 'PD-1 high ({val}%), exhaustion possible.'
      }
    }
  },
  c4: {
    id: 'c4',
    label: { zh: 'FoxP3 浸润', en: 'FoxP3 Density' },
    minLabel: 'Sparse',
    maxLabel: 'Dense',
    thresholds: { warning: 40, danger: 70 },
    descriptions: {
      zh: {
        low: 'FoxP3稀疏 ({val}%)。',
        mid: 'FoxP3中等浸润 ({val}%)。',
        high: 'FoxP3浸润密集 ({val}%)，免疫抑制。'
      },
      en: {
        low: 'FoxP3 sparse ({val}%).',
        mid: 'FoxP3 moderate ({val}%).',
        high: 'FoxP3 dense ({val}%), immunosuppressive.'
      }
    }
  },
  // TME Markers (Currently used in calculation but less emphasized in narrative, adding for completeness)
  c5: {
    id: 'c5',
    label: { zh: 'CD3 T细胞', en: 'CD3 T-Cells' },
    minLabel: 'Low',
    maxLabel: 'High',
    thresholds: { warning: 40, danger: 70 },
    descriptions: {
      zh: { low: 'CD3浸润低', mid: 'CD3浸润中', high: 'CD3浸润高' },
      en: { low: 'CD3 Low', mid: 'CD3 Mod', high: 'CD3 High' }
    }
  },
  c6: {
    id: 'c6',
    label: { zh: 'CD4 辅助T', en: 'CD4 Helper' },
    minLabel: 'Low',
    maxLabel: 'High',
    thresholds: { warning: 40, danger: 70 },
    descriptions: {
      zh: { low: 'CD4浸润低', mid: 'CD4浸润中', high: 'CD4浸润高' },
      en: { low: 'CD4 Low', mid: 'CD4 Mod', high: 'CD4 High' }
    }
  },
  c7: {
    id: 'c7',
    label: { zh: 'CD8 杀伤T', en: 'CD8 Killer' },
    minLabel: 'Low',
    maxLabel: 'High',
    thresholds: { warning: 40, danger: 70 },
    descriptions: {
      zh: { low: 'CD8浸润低', mid: 'CD8浸润中', high: 'CD8浸润高' },
      en: { low: 'CD8 Low', mid: 'CD8 Mod', high: 'CD8 High' }
    }
  }
};

export const getConceptColor = (value: number, thresholds = DEFAULT_THRESHOLDS) => {
  if (value >= thresholds.danger) return 'text-red-500'; // High Risk
  if (value >= thresholds.warning) return 'text-amber-500'; // Moderate Risk
  return 'text-emerald-500'; // Low Risk / Normal
};

export const getConceptBarGradient = (value: number, thresholds = DEFAULT_THRESHOLDS) => {
  if (value >= thresholds.danger) return "from-red-600 to-red-400";
  if (value >= thresholds.warning) return "from-amber-500 to-yellow-400";
  return "from-emerald-600 to-emerald-400";
};

