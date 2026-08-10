import fs from 'node:fs/promises';
import { legacyAppDataFile, runtimeDataFile } from '@/lib/runtime-data';
import { resolveResearchReader, type ReaderAuthResult } from '@/lib/reader/study-auth';
import { readerRound2CaseMembership } from '@/lib/reader/round2-order';
import {
  READER_ROUND2_AGENT_VERSION,
  READER_ROUND2_FREEZE_ID,
  READER_ROUND2_MANIFEST_VERSION,
  READER_ROUND2_MODEL_VERSION,
  READER_ROUND2_PROMPT_VERSION,
  READER_ROUND2_RULE_VERSION,
  READER_ROUND2_SOFTWARE_VERSION,
  type ReaderStudyVersionFields,
} from '@/lib/reader/study-contract';

export const RESEARCH_VERSIONS: ReaderStudyVersionFields = {
  freeze_id: READER_ROUND2_FREEZE_ID,
  software_version: READER_ROUND2_SOFTWARE_VERSION,
  agent_version: READER_ROUND2_AGENT_VERSION,
  model_version: READER_ROUND2_MODEL_VERSION,
  rule_version: READER_ROUND2_RULE_VERSION,
  prompt_version: READER_ROUND2_PROMPT_VERSION,
  manifest_version: READER_ROUND2_MANIFEST_VERSION,
};

const DATA_FILE = runtimeDataFile('reader_audit_events.jsonl');
const LEGACY_DATA_FILE = legacyAppDataFile('reader_audit_events.jsonl');

function text(value: unknown, fallback = '') {
  return String(value ?? fallback).trim();
}

async function readEventLines(): Promise<string[]> {
  const files = [LEGACY_DATA_FILE, DATA_FILE].filter(
    (file, index, all) => all.indexOf(file) === index,
  );
  const chunks = await Promise.all(
    files.map(async (file) => {
      try {
        return await fs.readFile(file, 'utf8');
      } catch {
        return '';
      }
    }),
  );
  return chunks.join('\n').split('\n').filter(Boolean);
}

export function validateResearchVersions(
  supplied: Partial<Record<keyof ReaderStudyVersionFields, unknown>>,
): { ok: true; versions: ReaderStudyVersionFields } | { ok: false; message: string } {
  const mismatches: string[] = [];
  (Object.keys(RESEARCH_VERSIONS) as Array<keyof ReaderStudyVersionFields>).forEach((key) => {
    const value = text(supplied[key]);
    if (value && value !== RESEARCH_VERSIONS[key]) {
      mismatches.push(`${key}=${value}`);
    }
  });
  if (mismatches.length) {
    return {
      ok: false,
      message: `research version fields must match freeze constants (${mismatches.join(', ')})`,
    };
  }
  return { ok: true, versions: { ...RESEARCH_VERSIONS } };
}

export async function hasResearchInitialJudgment(params: {
  readerId: string;
  caseId: string;
  sessionId?: string;
}): Promise<boolean> {
  const readerId = text(params.readerId);
  const caseId = text(params.caseId);
  const sessionId = text(params.sessionId);
  if (!readerId || !caseId) return false;
  const lines = await readEventLines();
  for (let index = lines.length - 1; index >= 0; index -= 1) {
    try {
      const event = JSON.parse(lines[index]) as Record<string, unknown>;
      if (event.event_type !== 'initial_judgment') continue;
      if (text(event.case_id) !== caseId) continue;
      if (sessionId && text(event.session_id) !== sessionId) continue;
      const eventReader = text(event.authenticated_reader_id || event.reader_id);
      if (eventReader === readerId) return true;
    } catch {
      /* skip malformed historical lines */
    }
  }
  return false;
}

export type ResearchAccessOk = {
  ok: true;
  readerId: string;
  authMode: 'signed_proxy' | 'unsigned_development';
  versions: ReaderStudyVersionFields;
  presentationIndex: number;
};

export type ResearchAccessErr = {
  ok: false;
  status: number;
  code: string;
  message: string;
};

export async function assertResearchCaseAccess(params: {
  headers: Headers;
  requestedReaderId?: unknown;
  caseId: string;
  round?: unknown;
  versions?: Partial<Record<keyof ReaderStudyVersionFields, unknown>>;
  requireInitialJudgment?: boolean;
  sessionId?: string;
}): Promise<ResearchAccessOk | ResearchAccessErr> {
  if (text(params.round) && text(params.round) !== 'round2') {
    return {
      ok: false,
      status: 422,
      code: 'research_round_invalid',
      message: 'research requests must use round2',
    };
  }
  const auth: ReaderAuthResult = resolveResearchReader(params.headers, params.requestedReaderId);
  if (!auth.ok) {
    return {
      ok: false,
      status: auth.code === 'invalid_identity' ? 403 : 401,
      code: `research_auth_${auth.code}`,
      message: auth.message,
    };
  }
  const membership = readerRound2CaseMembership(auth.readerId, params.caseId);
  if (!membership.ok) {
    return {
      ok: false,
      status: 422,
      code: 'research_case_not_in_freeze',
      message: membership.reason,
    };
  }
  const versions = validateResearchVersions(params.versions || {});
  if (!versions.ok) {
    return {
      ok: false,
      status: 422,
      code: 'research_version_mismatch',
      message: versions.message,
    };
  }
  if (params.requireInitialJudgment) {
    const initialOk = await hasResearchInitialJudgment({
      readerId: auth.readerId,
      caseId: params.caseId,
      sessionId: params.sessionId,
    });
    if (!initialOk) {
      return {
        ok: false,
        status: 422,
        code: 'research_initial_judgment_required',
        message: params.sessionId
          ? 'research final actions require a prior initial_judgment for the same session and case'
          : 'research AI analysis requires a prior initial_judgment for this case',
      };
    }
  }
  return {
    ok: true,
    readerId: auth.readerId,
    authMode: auth.authMode,
    versions: versions.versions,
    presentationIndex: membership.presentationIndex,
  };
}
