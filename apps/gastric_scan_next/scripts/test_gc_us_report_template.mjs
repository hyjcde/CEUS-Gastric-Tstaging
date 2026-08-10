#!/usr/bin/env node
import assert from 'node:assert/strict';
import {
  GC_US_REPORT_SCHEMA_VERSION,
  createGcUsField,
  createGcUsReportState,
  buildGcUsReport,
} from '../lib/gc-us-report-template.ts';

const provenance = {
  evidence_id: 'evidence:test:layer',
  source_type: 'doctor_input',
  source_refs: ['case:TEST', 'field:layer_structure', 'frame:frame-1'],
  frame_id_or_time: 'frame-1',
  model_version: null,
  rule_version: GC_US_REPORT_SCHEMA_VERSION,
  actor_id: null,
  created_at: new Date().toISOString(),
};

const state = createGcUsReportState({
  case_id: 'TEST',
  frame_id: 'frame-1',
  signs: {
    layer_structure: createGcUsField('固有肌层（T2）', {
      status: 'doctor_edited',
      source: 'doctor',
      provenance: [provenance],
      evidence_ref: [provenance.evidence_id],
    }),
  },
  doctor_actions: [{
    action_id: 'action:test:layer',
    action_type: 'field_edit',
    field_id: 'layer_structure',
    suggestion_id: null,
    before_value: '当前帧层次显示有限',
    after_value: '固有肌层（T2）',
    reason: 'Doctor confirmation',
    evidence_ids: [provenance.evidence_id],
    source_refs: provenance.source_refs,
    frame_id_or_time: 'frame-1',
    actor_id: null,
    software_version: 'test',
    model_version: null,
    rule_version: GC_US_REPORT_SCHEMA_VERSION,
    created_at: new Date().toISOString(),
  }],
});

assert.equal(state.signs.layer_structure.provenance?.[0].evidence_id, provenance.evidence_id);
assert.equal(state.doctor_actions.length, 1);
assert.equal(state.doctor_actions[0].after_value, '固有肌层（T2）');

const report = buildGcUsReport(state, 'uncertain');
assert.equal(report.structured.doctor_actions.length, 1);
const reportEn = buildGcUsReport(state, 'uncertain', 'en');
assert.match(reportEn.prose, /\[Ultrasound findings\]/);
assert.match(reportEn.prose, /ultrasound-assessed cTx/i);
assert.equal(reportEn.prose.includes('超声所见'), false);
console.log('gc_us_report_template provenance regression: 3/3 passed');
