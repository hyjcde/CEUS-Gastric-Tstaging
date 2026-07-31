import fs from 'fs';
import path from 'path';
import { PROJECT_ROOT } from '@/lib/config';

const LLM_ENV_KEYS = [
  'AGENT_API_KEY',
  'AGENT_LLM_BASE_URL',
  'AGENT_LLM_MODEL',
  'POE_API_KEY',
  'POE_BASE_URL',
  'POE_MODEL',
  'VLM_API_KEY',
  'VLM_API_BASE_URL',
  'VLM_MODEL',
  'OPENAI_API_KEY',
  'DEEPSEEK_API_KEY',
  'DEEPSEEK_BASE_URL',
  'DEEPSEEK_MODEL',
  'DEEPSEEK_API_KEY_FILE',
  'MINIMAX_API_KEY',
  'MINIMAX_BASE_URL',
  'MINIMAX_MODEL',
  'AGENT_MEMORY_ENABLED',
  'AGENT_MEMORY_STORE',
  'AGENT_MEMORY_FUSION_MODE',
] as const;

function parseEnvFile(filePath: string): Record<string, string> {
  if (!fs.existsSync(filePath)) return {};
  const out: Record<string, string> = {};
  for (const raw of fs.readFileSync(filePath, 'utf-8').split(/\r?\n/)) {
    const line = raw.trim();
    if (!line || line.startsWith('#')) continue;
    const eq = line.indexOf('=');
    if (eq <= 0) continue;
    const key = line.slice(0, eq).trim();
    let value = line.slice(eq + 1).trim();
    if (
      (value.startsWith('"') && value.endsWith('"'))
      || (value.startsWith("'") && value.endsWith("'"))
    ) {
      value = value.slice(1, -1);
    }
    if (key) out[key] = value;
  }
  return out;
}

let cachedFileEnv: Record<string, string> | null = null;

/** Load repo-root .env + Next .env.local (server-only). */
export function loadAgentFileEnv(): Record<string, string> {
  if (cachedFileEnv) return cachedFileEnv;
  const rootEnv = parseEnvFile(path.join(PROJECT_ROOT, '.env'));
  const localEnv = parseEnvFile(path.join(PROJECT_ROOT, 'apps/gastric_scan_next/.env.local'));
  const exampleHints = parseEnvFile(path.join(PROJECT_ROOT, 'apps/gastric_scan_next/.env.example'));
  cachedFileEnv = { ...exampleHints, ...rootEnv, ...localEnv };
  return cachedFileEnv;
}

function readDeepseekKeyFile(fileEnv: Record<string, string>): string {
  const explicit = fileEnv.DEEPSEEK_API_KEY_FILE || process.env.DEEPSEEK_API_KEY_FILE;
  const candidates = [
    explicit,
    path.join(PROJECT_ROOT, 'docs/clinical_validation/reader_study_v150/server/deepseek_api_key.txt'),
  ].filter(Boolean) as string[];
  for (const p of candidates) {
    if (fs.existsSync(p)) {
      const key = fs.readFileSync(p, 'utf-8').trim();
      if (key) return key;
    }
  }
  return '';
}

/**
 * Environment inherited by Python agent subprocesses.
 * Merges process.env ← file envs ← DeepSeek keyfile fallback.
 */
export function buildPythonAgentEnv(
  extra: Record<string, string | undefined> = {},
): NodeJS.ProcessEnv {
  const fileEnv = loadAgentFileEnv();
  const merged: Record<string, string> = {};

  for (const key of LLM_ENV_KEYS) {
    const fromProcess = process.env[key];
    const fromFile = fileEnv[key];
    if (fromProcess && fromProcess.trim()) merged[key] = fromProcess.trim();
    else if (fromFile && fromFile.trim() && !fromFile.includes('REPLACE')) merged[key] = fromFile.trim();
  }

  if (!merged.DEEPSEEK_API_KEY) {
    const fromFile = readDeepseekKeyFile(fileEnv);
    if (fromFile) merged.DEEPSEEK_API_KEY = fromFile;
  }

  // If only DeepSeek is available, point AgentLLMClient at native DeepSeek API.
  const hasPoeStyle = Boolean(merged.AGENT_API_KEY || merged.POE_API_KEY || merged.VLM_API_KEY || merged.OPENAI_API_KEY);
  if (!hasPoeStyle && merged.DEEPSEEK_API_KEY) {
    if (!merged.AGENT_API_KEY) merged.AGENT_API_KEY = merged.DEEPSEEK_API_KEY;
    if (!merged.AGENT_LLM_BASE_URL) {
      merged.AGENT_LLM_BASE_URL = merged.DEEPSEEK_BASE_URL || 'https://api.deepseek.com';
    }
    if (!merged.AGENT_LLM_MODEL) {
      merged.AGENT_LLM_MODEL = merged.DEEPSEEK_MODEL || 'deepseek-chat';
    }
  }

  const env: NodeJS.ProcessEnv = {
    ...process.env,
    ...merged,
    GASTRIC_ROOT: PROJECT_ROOT,
    PYTHONPATH: `${PROJECT_ROOT}/pipeline${process.env.PYTHONPATH ? `:${process.env.PYTHONPATH}` : ''}`,
  };

  for (const [k, v] of Object.entries(extra)) {
    if (v !== undefined) env[k] = v;
  }
  return env;
}

export function probeAgentLlmEnv() {
  const env = buildPythonAgentEnv();
  const keySources = [
    'AGENT_API_KEY',
    'POE_API_KEY',
    'VLM_API_KEY',
    'OPENAI_API_KEY',
    'DEEPSEEK_API_KEY',
  ].filter((k) => Boolean(env[k]));

  const base = env.AGENT_LLM_BASE_URL || env.VLM_API_BASE_URL || null;
  const model = env.AGENT_LLM_MODEL || env.VLM_MODEL || null;
  const preferred =
    env.DEEPSEEK_API_KEY && (base || '').includes('deepseek')
      ? 'deepseek'
      : keySources.includes('POE_API_KEY') || keySources.includes('AGENT_API_KEY')
        ? 'poe_or_agent'
        : keySources[0] || null;

  return {
    ok: keySources.length > 0,
    configured: keySources.length > 0,
    key_sources: keySources,
    base_url: base,
    model,
    preferred,
    // never return secrets
  };
}
