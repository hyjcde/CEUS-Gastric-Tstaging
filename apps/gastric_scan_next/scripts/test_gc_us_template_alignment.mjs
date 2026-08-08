#!/usr/bin/env node
import assert from 'node:assert/strict';
import {
  GC_US_TEMPLATE_SELECT_OPTIONS,
  GC_US_WALL_LAYER_SPECS,
  buildGcUsTemplateReportText,
  createEmptyGcUsSigns,
  createEmptyGcUsTemplateFields,
  createGcUsField,
  createGcUsReportState,
  deepestInvolvedWallLayer,
  normalizeGcUsStage,
  syncSignsFromTemplateFields,
} from '../lib/gc-us-report-template.ts';

assert.deepEqual(
  GC_US_WALL_LAYER_SPECS.map((item) => item.anatomyZh),
  ['黏膜浅层', '黏膜肌层', '黏膜下层', '固有肌层', '浆膜'],
);

assert.ok(GC_US_TEMPLATE_SELECT_OPTIONS.ct_stage.includes('uT4a'));
assert.ok(GC_US_TEMPLATE_SELECT_OPTIONS.ct_stage.includes('uT4b'));
assert.equal(normalizeGcUsStage('uT4a').band, 'T4a');
assert.equal(normalizeGcUsStage('T4b').band, 'T4b');
assert.equal(normalizeGcUsStage('uT4').band, 'T4');
assert.equal(normalizeGcUsStage('T4+').band, 'uncertain');

const fields = createEmptyGcUsTemplateFields();
fields.layer_1_mucosa = createGcUsField('消失');
fields.layer_2_submucosa = createGcUsField('消失');
fields.layer_3_muscularis = createGcUsField('模糊/变薄');
fields.layer_4_subserosa = createGcUsField('存在');
fields.layer_5_serosa = createGcUsField('存在');
fields.gross_type = createGcUsField('浸润溃疡型');
fields.perigastric_involvement = createGcUsField('未见明确侵犯');

const deepestL3 = deepestInvolvedWallLayer(fields);
assert.equal(deepestL3.suggestedBand, 'T1');
assert.equal(deepestL3.anatomyZh, '黏膜下层');

fields.layer_4_subserosa = createGcUsField('消失');
const deepestL4 = deepestInvolvedWallLayer(fields);
assert.equal(deepestL4.suggestedBand, 'T2');
assert.equal(deepestL4.anatomyZh, '固有肌层');

fields.layer_5_serosa = createGcUsField('消失');
const deepestL5 = deepestInvolvedWallLayer(fields);
assert.equal(deepestL5.suggestedBand, 'T4a');

fields.perigastric_involvement = createGcUsField('邻近器官侵犯（胰腺）');
const deepestT4b = deepestInvolvedWallLayer(fields);
assert.equal(deepestT4b.suggestedBand, 'T4b');

const synced = syncSignsFromTemplateFields(createEmptyGcUsSigns(), fields);
assert.equal(synced.morphology.value, '溃疡浸润型');
assert.equal(synced.growth_pattern.value, '明显浸润性');
assert.match(String(synced.layer_structure.value || ''), /T4b/);
assert.match(String(synced.boundary.note || ''), /层次/);

const state = createGcUsReportState({
  case_id: 'ALIGN-TEST',
  template_fields: {
    ...fields,
    lesion_site: createGcUsField('胃窦（后壁）'),
    maximum_diameter_cm: createGcUsField(4.2, { unit: 'cm' }),
    maximum_thickness_cm: createGcUsField(1.1, { unit: 'cm' }),
    ct_stage: createGcUsField('uT4b'),
    cn_stage: createGcUsField('N0'),
    cm_stage: createGcUsField('M0'),
  },
  signs: synced,
});
const prose = buildGcUsTemplateReportText(state);
assert.match(prose, /第一层（黏膜浅层）/);
assert.match(prose, /第四层（固有肌层）/);
assert.match(prose, /uT4b/);
assert.match(prose, /形态、生长方式并入大体分型/);

console.log('gc_us_template_alignment: passed');
