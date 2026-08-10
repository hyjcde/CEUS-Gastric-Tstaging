#!/usr/bin/env node

import { spawn } from 'node:child_process';
import { mkdtemp, readFile, rm } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import process from 'node:process';

const port = Number(process.env.REPORT_TEST_PORT || 3197);
const externalBaseUrl = process.env.REPORT_TEST_BASE_URL?.replace(/\/$/, '');
const baseUrl = externalBaseUrl || `http://127.0.0.1:${port}`;
const runtimeDir = await mkdtemp(path.join(os.tmpdir(), 'gastric-report-test-'));
const nextDistDir = '.next-report-test';
const caseId = `workflow-smoke-${Date.now()}`;

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

function field(value, source = 'doctor') {
  return {
    value,
    status: value == null ? 'unevaluated' : 'doctor_edited',
    source: value == null ? 'not_available' : source,
    confidence: null,
    raw_value: value,
    doctor_override: value,
    evidence_ref: value == null ? [] : [`smoke:${caseId}`],
    unit: null,
    note: '',
    provenance: [],
  };
}

function reportState(status = 'draft') {
  const value = {
    schema_version: 'gc_us_report_signs_v1',
    template_id: 'gc_us_t_report_template_v1',
    source_doc: '胃充盈超声报告模板.docx',
    case_id: caseId,
    frame_id: `${caseId}-frame`,
    frame_time: 12.5,
    clinical: {},
    signs: {},
    template_fields: {
      lesion_site: field('胃窦（后壁）'),
      maximum_diameter_cm: { ...field(4.2), unit: 'cm' },
      maximum_thickness_cm: { ...field(1.1), unit: 'cm' },
      gross_type: field('浸润溃疡型'),
      wall_layer_summary: field('固有肌层受累'),
      layer_1_mucosa: field('消失'),
      layer_2_submucosa: field('消失'),
      layer_3_muscularis: field('模糊/变薄'),
      layer_4_subserosa: field('存在'),
      layer_5_serosa: field('存在'),
      perigastric_involvement: field('未见明确侵犯'),
      lymph_nodes: field('未见明确肿大'),
      distant_metastasis: field('未见'),
      ascites: field('无'),
      ct_stage: field('uT2'),
      cn_stage: field('N0'),
      cm_stage: field('M0'),
      impression: field('胃窦后壁占位，超声倾向 uT2N0M0。'),
      recommendation: field('建议结合胃镜活检。', 'template_reference'),
    },
    report_images: [{
      id: 'workflow-reference',
      label: 'Workflow reference image',
      url: 'data:image/png;base64,iVBORw0KGgo=',
      kind: 'original',
      selected: true,
    }],
    reference_stage: {
      band: 'T2',
      requested_band: 'T2',
      raw: 'T2',
      source: 'doctor',
      conflicts: [],
    },
    report: {
      prose: '胃癌超声报告\n胃窦后壁占位，超声倾向 uT2N0M0。',
      source: 'doctor',
      doctor_edited: true,
      status,
      report_id: null,
      revision: 0,
      signed_by: 'workflow-smoke-doctor',
      signed_at: null,
      export_method: 'pdf',
    },
    conflicts: [],
    doctor_actions: [],
  };
  return value;
}

async function waitForServer(child) {
  const deadline = Date.now() + 90_000;
  while (Date.now() < deadline) {
    if (child.exitCode != null) throw new Error(`Next server exited with ${child.exitCode}`);
    try {
      const response = await fetch(`${baseUrl}/api/reports/template`);
      if (response.ok) return;
    } catch {
      // The development server is still compiling or starting.
    }
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
  throw new Error('Timed out waiting for the Next server');
}

async function post(action, report, revisionOf = null) {
  const response = await fetch(`${baseUrl}/api/reports/template`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      action,
      case_id: caseId,
      patient_id: caseId,
      patient_label: 'Workflow smoke case',
      revision_of: revisionOf,
      report,
    }),
  });
  const payload = await response.json();
  return { response, payload };
}

const server = externalBaseUrl
  ? null
  : spawn(process.execPath, [path.resolve('node_modules/next/dist/bin/next'), 'dev', '--webpack', '--hostname', '127.0.0.1', '--port', String(port)], {
      cwd: process.cwd(),
      env: {
        ...process.env,
        NODE_ENV: 'development',
        GASTRIC_RUNTIME_DATA_DIR: runtimeDir,
        NEXT_DIST_DIR: nextDistDir,
      },
      stdio: 'inherit',
    });

try {
  if (server) await waitForServer(server);

  const draft = await post('save_draft', reportState('draft'));
  assert(draft.response.ok && draft.payload.status === 'draft', `draft save failed: ${draft.response.status} ${JSON.stringify(draft.payload)}`);
  assert(draft.payload.revision === 1, 'first draft revision should be 1');

  const directFinalize = await post('finalize', reportState('finalized'));
  assert(directFinalize.response.status === 409, 'finalize must require reviewed state');

  const reviewed = await post('review', reportState('reviewed'));
  assert(reviewed.response.ok && reviewed.payload.status === 'reviewed', 'review transition failed');
  assert(reviewed.payload.revision === 2, 'review revision should be 2');

  const finalized = await post('finalize', reportState('finalized'));
  assert(finalized.response.ok && finalized.payload.status === 'finalized', 'finalization failed');
  assert(finalized.payload.revision === 3, 'final revision should be 3');

  const staleOverwrite = await post('save_draft', reportState('draft'));
  assert(staleOverwrite.response.status === 409, 'signed report was overwritten without revision intent');

  const revisionDraft = await post('save_draft', reportState('draft'), 3);
  assert(revisionDraft.response.ok && revisionDraft.payload.revision === 4, 'revision draft failed');
  const revisionReviewed = await post('review', reportState('reviewed'));
  assert(revisionReviewed.response.ok && revisionReviewed.payload.revision === 5, 'revision review failed');
  const revisionFinal = await post('finalize', reportState('finalized'));
  assert(revisionFinal.response.ok && revisionFinal.payload.revision === 6, 'revision finalization failed');

  const currentResponse = await fetch(`${baseUrl}/api/reports/template?case_id=${encodeURIComponent(caseId)}`);
  const current = await currentResponse.json();
  assert(currentResponse.ok && current.report?.report?.status === 'finalized', 'current report read failed');
  assert(current.revisions?.length === 6, 'history should contain six revisions');
  assert(current.revisions.some((item) => item.changed_fields?.includes('report.status')), 'history diff is missing');

  const historicalResponse = await fetch(
    `${baseUrl}/api/reports/template?report_id=${encodeURIComponent(revisionFinal.payload.report_id)}&revision=3`,
  );
  const historical = await historicalResponse.json();
  assert(historicalResponse.ok && historical.report?.report?.status === 'finalized', 'historical revision read failed');
  assert(historical.metadata?.revision === 3, 'historical revision metadata is incorrect');

  const indexRuntimeDir = externalBaseUrl
    ? process.env.GASTRIC_RUNTIME_DATA_DIR || path.join(os.tmpdir(), 'gastric-scan-next')
    : runtimeDir;
  const index = JSON.parse(await readFile(path.join(indexRuntimeDir, 'template_reports_index.json'), 'utf8'));
  assert(Array.isArray(index) && index[0]?.revision === 6, 'summary index was not updated atomically');
  console.log('Template report workflow smoke test passed');
} finally {
  if (server) {
    server.kill('SIGTERM');
    await new Promise((resolve) => setTimeout(resolve, 250));
  } else {
    const sharedRuntimeDir = process.env.GASTRIC_RUNTIME_DATA_DIR
      || path.join(os.tmpdir(), 'gastric-scan-next');
    const storeFile = path.join(sharedRuntimeDir, 'template_reports.json');
    const indexFile = path.join(sharedRuntimeDir, 'template_reports_index.json');
    try {
      const store = JSON.parse(await readFile(storeFile, 'utf8'));
      delete store[caseId];
      const { writeFile } = await import('node:fs/promises');
      await writeFile(storeFile, JSON.stringify(store, null, 2), 'utf8');
      const index = JSON.parse(await readFile(indexFile, 'utf8')).filter((item) => item.case_id !== caseId);
      await writeFile(indexFile, JSON.stringify(index, null, 2), 'utf8');
    } catch {
      // Cleanup is best effort for an externally managed development server.
    }
  }
  await rm(runtimeDir, { recursive: true, force: true });
}
