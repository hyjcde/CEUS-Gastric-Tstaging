export const READER_ROUND2_FREEZE_ID = 'reader_round2_freeze_20260810';
export const READER_ROUND2_MANIFEST_VERSION = 'reader_round2_manifest_20260810';
export const READER_ROUND2_SOFTWARE_VERSION = 'gastric-agent-next-lan-20260801';
export const READER_ROUND2_AGENT_VERSION = 'reader_unified_agent_bridge_v1';
export const READER_ROUND2_MODEL_VERSION = 'tstage_acc_boost2_screened_20260603';
export const READER_ROUND2_RULE_VERSION = 'gc_us_report_signs_v1';
export const READER_ROUND2_PROMPT_VERSION = 'reader_agent_prompt_v1';
export const READER_ROUND2_ORDER_SEED = 20260810;

export type ReaderStudyEnvironment = 'qa' | 'staging' | 'research' | 'production';

export type ReaderStudyVersionFields = {
  freeze_id: string;
  software_version: string;
  agent_version: string;
  model_version: string;
  rule_version: string;
  prompt_version: string;
  manifest_version: string;
};

export const READER_ROUND2_VERSION_FIELDS: ReaderStudyVersionFields = {
  freeze_id: READER_ROUND2_FREEZE_ID,
  software_version: READER_ROUND2_SOFTWARE_VERSION,
  agent_version: READER_ROUND2_AGENT_VERSION,
  model_version: READER_ROUND2_MODEL_VERSION,
  rule_version: READER_ROUND2_RULE_VERSION,
  prompt_version: READER_ROUND2_PROMPT_VERSION,
  manifest_version: READER_ROUND2_MANIFEST_VERSION,
};

export function readerEnvironmentFromSearchParams(
  params: { get(name: string): string | null } | null | undefined,
): ReaderStudyEnvironment {
  const explicit = params?.get('environment') || params?.get('env');
  if (explicit === 'qa' || explicit === 'staging' || explicit === 'research' || explicit === 'production') {
    return explicit;
  }
  return params?.get('round') === 'qa' ? 'qa' : 'staging';
}

export function compactReaderSigns(report: unknown): Record<string, unknown> {
  if (!report || typeof report !== 'object') return {};
  const signs = (report as { signs?: unknown }).signs;
  if (!signs || typeof signs !== 'object' || Array.isArray(signs)) return {};
  const compactValue = (value: unknown): unknown => {
    if (!value || typeof value !== 'object' || Array.isArray(value)) return value;
    const field = value as Record<string, unknown>;
    if ('value' in field || 'status' in field || 'source' in field || 'evidence_ref' in field) {
      return {
        value: field.value ?? null,
        status: field.status ?? 'unevaluated',
        source: field.source ?? 'not_available',
        confidence: field.confidence ?? null,
        evidence_ref: Array.isArray(field.evidence_ref) ? field.evidence_ref : [],
      };
    }
    return Object.fromEntries(Object.entries(field).map(([key, nested]) => [key, compactValue(nested)]));
  };
  return Object.fromEntries(
    Object.entries(signs as Record<string, unknown>).map(([key, value]) => [key, compactValue(value)]),
  );
}

export function readerEvidenceIds(report: unknown): string[] {
  if (!report || typeof report !== 'object') return [];
  const evidence = (report as { evidence?: unknown }).evidence;
  if (!Array.isArray(evidence)) return [];
  return evidence
    .map((item, index) => {
      if (!item || typeof item !== 'object') return `evidence:${index}`;
      const value = item as Record<string, unknown>;
      return String(value.id || value.source || value.title || `evidence:${index}`);
    })
    .filter(Boolean);
}
