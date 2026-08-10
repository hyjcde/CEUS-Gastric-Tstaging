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
  deriveGcUsSigns,
  deriveGcUsTemplateFields,
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

const clinicalPriority = deriveGcUsSigns({
  clinical: {
    tumorSize: { length: 2.3, thickness: 0.9 },
  },
  layer: { label: '达固有肌层（L4）', tHint: 'T2', inContact: true },
  lesion: {
    lengthMm: 99,
    thicknessMm: 88,
  },
  pixel: { irregularity: 3.7 },
});
assert.equal(clinicalPriority.size.length.value, 23);
assert.equal(clinicalPriority.size.thickness.value, 9);
assert.equal(clinicalPriority.size.thickness.unit, 'mm');
assert.equal(clinicalPriority.boundary.value, '边界不规则');
assert.equal(clinicalPriority.morphology.value, '溃疡浸润型');
assert.equal(clinicalPriority.growth_pattern.value, '明显浸润性');

const clinicalTemplateFields = deriveGcUsTemplateFields({
  clinical: { tumorSize: { length: 2.3, thickness: 0.9 }, location: '胃窦' },
  signs: clinicalPriority,
});
assert.equal(clinicalTemplateFields.maximum_diameter_cm.value, 2.3);
assert.equal(clinicalTemplateFields.maximum_thickness_cm.value, 0.9);
assert.equal(clinicalTemplateFields.layer_4_subserosa.value, '模糊/变薄');
assert.equal(clinicalTemplateFields.layer_5_serosa.value, '存在');

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

const proseEn = buildGcUsTemplateReportText(state, 'en');
assert.match(proseEn, /Gastric Cancer Ultrasound Report/);
assert.match(proseEn, /Ultrasound description:/);
assert.match(proseEn, /Layer 1 \(superficial mucosa\)/);
assert.match(proseEn, /Layer 4 \(muscularis propria\)/);
assert.match(proseEn, /uT4b/);
assert.match(proseEn, /Antrum \(posterior wall\)/);
assert.match(proseEn, /Consider gastric cancer/);
assert.match(proseEn, /Five-layer anatomy/);
assert.equal(proseEn.includes('第一层'), false);
assert.equal(proseEn.includes('超声描述'), false);

console.log('gc_us_template_alignment: passed');
