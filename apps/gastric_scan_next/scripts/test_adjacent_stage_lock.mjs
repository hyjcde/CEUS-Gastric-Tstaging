#!/usr/bin/env node
import assert from 'node:assert/strict';
import {
  compareKeyframeContinuity,
  fuseWallDraftIntoStaging,
  lockAdjacentStage,
  pairMeta,
  parseAdjacentPair,
  parseWallLayerTarget,
  buildWallDraftProse,
} from '../lib/reader/adjacent-stage-lock.ts';
import { buildAssistJudgmentProse, mergeJudgmentDoctorSigns } from '../lib/reader/assist-judgment-prose.ts';
import { periLesionRoi } from '../lib/mask-override.ts';

assert.equal(parseAdjacentPair('t3_t4'), 't3_t4');
assert.equal(parseAdjacentPair('T3/T4'), null);
assert.equal(parseWallLayerTarget(2), 2);
assert.equal(parseWallLayerTarget(5), null);
assert.equal(pairMeta('t3_t4').layers, 1);
assert.equal(pairMeta('t2_t3').layers, 2);
assert.equal(pairMeta('t1_t2').layers, 3);

const inside = lockAdjacentStage({ T1: 0.05, T2: 0.1, T3: 0.35, T4: 0.5 }, 't3_t4');
assert.equal(inside.lockedChoice, 'T4');
assert.equal(inside.outsideLock, false);
assert.ok(inside.lockedShare > 0.5);
assert.match(inside.noteZh, /T3 \/ T4/);

const outside = lockAdjacentStage({ T1: 0.02, T2: 0.08, T3: 0.1, T4: 0.8 }, 't1_t2');
assert.equal(outside.frozenTop1, 'T4');
assert.equal(outside.outsideLock, true);
assert.equal(outside.lockedChoice, 'T2');
assert.match(outside.noteZh, /超出/);

const mixed = compareKeyframeContinuity([
  { interrupts: [{ layer: 5, interrupted: true }] },
  { interrupts: [{ layer: 5, interrupted: false }] },
  { ticks: [{ layer: 5, status: 'present' }] },
]);
assert.equal(mixed.mixed, true);
assert.equal(mixed.interrupted, 1);
assert.equal(mixed.continuous, 2);
assert.match(mixed.noteZh, /伪像/);

const prose = buildWallDraftProse({
  targetLayers: 1,
  visibility: 'clear',
  spanCount: 1,
  interrupts: [{ layer: 5, nameZh: '浆膜', interrupted: true, verdict: 'interrupted' }],
  keyframeCount: 1,
}, true);
assert.match(prose, /还缺对侧/);
assert.match(prose, /浆膜预期走行线/);
assert.match(prose, /中断/);
assert.match(prose, /1 个关键帧/);
assert.doesNotMatch(prose, /按 1 层画/);

const unseen = buildWallDraftProse({
  targetLayers: 1,
  visibility: 'unseen',
  anchorMode: 'unanalyzable',
  interrupts: [{ layer: 5, nameZh: '浆膜', interrupted: true, verdict: 'cannot_judge' }],
}, true);
assert.match(unseen, /看不清不等于中断/);
assert.match(unseen, /无法判断/);

const lockedProse = buildAssistJudgmentProse({
  studyMode: 't_staging',
  aiValue: 'T3',
  zh: true,
  wallDraft: {
    targetLayers: 1,
    interrupts: [{ nameZh: '浆膜', interrupted: true }],
  },
  adjacentLock: {
    pairZh: 'T3 / T4',
    pairEn: 'T3 / T4',
    lockedChoice: 'T3',
    outsideLock: true,
    frozenTop1: 'T4',
  },
});
assert.match(lockedProse, /浆膜中断/);
assert.match(lockedProse, /收回到锁定范围内的 T3/);
assert.match(lockedProse, /cT3/);

const signs = mergeJudgmentDoctorSigns({
  signs: {
    morphology: '溃疡浸润型',
    serosa_change: '浆膜连续性中断',
    layer_structure: '浆膜连续性中断（T4a）',
  },
  wallDraft: {
    targetLayers: 1,
    interrupts: [{ nameZh: '浆膜', interrupted: false }],
  },
  headline: 'T3',
  frozenTop1: 'T4',
  zh: true,
});
assert.match(signs.layer_structure, /浆膜连续/);
assert.match(signs.layer_structure, /不定 cT/);
assert.match(signs.serosa_change, /浆膜连续/);
assert.equal(signs.morphology, '溃疡浸润型');

const dropT4Seed = mergeJudgmentDoctorSigns({
  signs: { serosa_change: '浆膜连续性中断' },
  headline: 'T2',
  frozenTop1: 'T4a',
  zh: true,
});
assert.equal(dropT4Seed.serosa_change, undefined);

const thinSigns = mergeJudgmentDoctorSigns({
  signs: {},
  wallDraft: {
    targetLayers: 3,
    interrupts: [{ nameZh: '固有肌层', interrupted: false }],
    ticks: [
      { nameZh: '黏膜浅层', status: 'thinned' },
      { nameZh: '固有肌层', status: 'thinned' },
    ],
    echoPatternZh: '亮暗相间',
  },
  headline: 'T2',
  frozenTop1: 'T3',
  zh: true,
});
assert.match(thinSigns.layer_structure, /黏膜浅层变薄/);
assert.match(thinSigns.layer_structure, /固有肌层变薄/);
assert.match(thinSigns.layer_structure, /亮暗相间/);
assert.match(thinSigns.layer_structure, /不定 cT/);

const fused = fuseWallDraftIntoStaging({
  targetLayers: 2,
  adjacentPair: 't2_t3',
  fates: [
    { id: 'mucosa', nameZh: '黏膜', verdict: 'continuous', labelZh: '黏膜连续' },
    { id: 'muscularis', nameZh: '固有肌层', verdict: 'fused', labelZh: '固有肌与灶融合' },
    { id: 'serosa', nameZh: '浆膜', verdict: 'displaced', labelZh: '浆膜受压绕行' },
  ],
  cluster: { available: true, pattern: 'bright-dark-bright' },
  remainPx: 12,
}, 't2_t3', 'T3');
assert.equal(fused.lean, 'T3');
assert.equal(fused.agree, 'agree');
assert.match(fused.noteZh, /支持 T3/);
assert.match(fused.noteZh, /不定 cT/);
assert.match(fused.noteZh, /亮-暗-亮/);

const clusterSigns = mergeJudgmentDoctorSigns({
  signs: {},
  wallDraft: {
    targetLayers: 2,
    adjacentPair: 't2_t3',
    fates: [
      { id: 'muscularis', nameZh: '固有肌层', verdict: 'fused', labelZh: '固有肌与灶融合' },
      { id: 'serosa', nameZh: '浆膜', verdict: 'displaced', labelZh: '浆膜受压绕行' },
    ],
    cluster: { available: true, pattern: 'bright-dark-bright' },
    remainPx: 12,
  },
  headline: 'T3',
  frozenTop1: 'T3',
  zh: true,
});
assert.match(clusterSigns.layer_structure, /固有肌层与灶融合|固有肌与灶融合/);
assert.match(clusterSigns.layer_structure, /亮-暗-亮/);
assert.match(clusterSigns.layer_structure, /不定 cT/);

const fusedProse = buildAssistJudgmentProse({
  studyMode: 't_staging',
  aiValue: 'T3',
  zh: true,
  wallDraft: {
    targetLayers: 2,
    adjacentPair: 't2_t3',
    fates: [
      { id: 'serosa', nameZh: '浆膜', verdict: 'displaced', labelZh: '浆膜受压绕行' },
    ],
    cluster: { available: true, pattern: 'bright-dark-bright' },
  },
  adjacentLock: {
    pair: 't2_t3',
    pairZh: 'T2 / T3',
    pairEn: 'T2 / T3',
    lockedChoice: 'T3',
    outsideLock: false,
    frozenTop1: 'T3',
  },
});
assert.match(fusedProse, /胃壁层次聚类/);
assert.match(fusedProse, /T2 \/ T3/);
assert.match(fusedProse, /支持 T3/);

const roi = periLesionRoi({
  lesion: [[10, 10], [30, 10], [30, 30], [10, 30]],
  extras: [[[80, 10], [100, 10], [100, 30], [80, 30]]],
  wall: [[5, 20], [110, 20], [110, 28], [5, 28]],
  width: 200,
  height: 80,
  margin: 8,
});
assert.ok(roi);
assert.ok(roi.x1 <= 2);
assert.ok(roi.x2 >= 108);

const waitingProse = buildWallDraftProse({
  proposedDeepestCount: 1,
  focusCount: 0,
}, true);
assert.match(waitingProse, /待医生选择后才开始分析/);

const startedProse = buildWallDraftProse({
  focusCount: 1,
  echoNoteZh: '最深区回声：亮-暗-中。不定 cT。',
}, true);
assert.match(startedProse, /已确认最深浸润区，开始分析/);
assert.match(startedProse, /最深区回声/);
assert.doesNotMatch(startedProse, /确定 cT/);

const singleSigns = mergeJudgmentDoctorSigns({
  signs: {},
  wallDraft: {
    targetLayers: 1,
    echoPatternZh: '亮-暗-中',
  },
  headline: 'T3',
  frozenTop1: 'T3',
  zh: true,
});
assert.match(singleSigns.layer_structure, /亮-暗-中/);
assert.match(singleSigns.layer_structure, /不定 cT/);

console.log('adjacent-stage-lock ok', {
  share: Number(inside.lockedShare.toFixed(3)),
  outside: outside.lockedChoice,
});
