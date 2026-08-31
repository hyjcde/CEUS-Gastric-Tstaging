#!/usr/bin/env node
import assert from 'node:assert/strict';
import {
  addAnalysisFocusPoint,
  confirmAnalysisFocusPoint,
  anatomyTargetMeta,
  appendWallPaintSegment,
  assignSpanSides,
  hitTestWallPaintSegment,
  popLastWallPaintSegment,
  setLastSpanVisibleLayers,
  setSpanVisibleLayers,
  spanLayerBadge,
  spanLayerSummary,
  wallProtocolBanner,
  cycleInterruptVerdict,
  depthScreenConflictsAi,
  interruptVerdictFromRaw,
  normalizeWallPaintSegments,
  paintLineHint,
  paintToolLabel,
  parseDoctorDepthScreen,
  parseWallVisibility,
  suggestedAnatomyFromScreen,
  wallPromptProse,
} from '../lib/reader/wall-prompt.ts';

assert.equal(anatomyTargetMeta(1).shortZh, '浆膜');
assert.equal(anatomyTargetMeta(2).shortZh, '固有肌');
assert.equal(anatomyTargetMeta(3).shortZh, '浅层');
assert.equal(parseWallVisibility('unseen'), 'unseen');
assert.equal(parseWallVisibility('broken'), null);

assert.equal(interruptVerdictFromRaw({ interrupted: true }), 'interrupted');
assert.equal(interruptVerdictFromRaw({ interrupted: true, visibility: 'blurry' }), 'suspected');
assert.equal(interruptVerdictFromRaw({ interrupted: true, visibility: 'unseen' }), 'cannot_judge');
assert.equal(interruptVerdictFromRaw({ interrupted: false, anchorMode: 'unanalyzable' }), 'cannot_judge');
assert.equal(interruptVerdictFromRaw({ suspected: true }), 'suspected');
assert.equal(interruptVerdictFromRaw({}), 'continuous');

assert.equal(cycleInterruptVerdict('continuous'), 'suspected');
assert.equal(cycleInterruptVerdict('suspected'), 'interrupted');
assert.equal(cycleInterruptVerdict('interrupted'), 'cannot_judge');
assert.equal(cycleInterruptVerdict('cannot_judge'), 'continuous');

const hint = paintLineHint(1, true);
assert.equal(hint, '浆膜预期走行线');
assert.doesNotMatch(hint, /一笔穿过|停笔|不表示连续|1 层|画 1 层/);
assert.equal(paintLineHint(1, false), 'expected serosal trajectory');

const prose = wallPromptProse({
  targetLayers: 1,
  visibility: 'unseen',
  anchorMode: 'unanalyzable',
  focusCount: 1,
  zh: true,
});
assert.match(prose, /浆膜最外缘是否连续/);
assert.match(prose, /看不清不等于中断/);
assert.match(prose, /已确认最深浸润区/);
assert.match(prose, /框选病灶并确认最深浸润区/);

const firstSeg = appendWallPaintSegment([], { points: [[0, 0], [8, 1], [16, 2]], visibleLayers: 3 });
const twoSeg = appendWallPaintSegment(firstSeg, { points: [[80, 4], [90, 6]], visibleLayers: 1 });
assert.equal(twoSeg.length, 2);
assert.equal(twoSeg[0].points.length, 3);
assert.equal(twoSeg[1].visibleLayers, 1);
const relayered = setLastSpanVisibleLayers(twoSeg, 2);
assert.equal(relayered[0].visibleLayers, 3);
assert.equal(relayered[1].visibleLayers, 2);
assert.equal(spanLayerBadge(1, true), '一层');
assert.equal(spanLayerSummary([{ visibleLayers: 3 }, { visibleLayers: 1 }], true), '左三层 / 右一层');
assert.equal(paintToolLabel(true, true, 0), '画一侧短线');
assert.equal(paintToolLabel(true, true, 1), '继续画对侧');
assert.equal(paintToolLabel(false, true, 1), '补画短线');
assert.match(wallProtocolBanner({ hasLesion: false, zh: true }).text, /先框选病灶/);
assert.match(wallProtocolBanner({ hasLesion: true, spanCount: 0, focusCount: 0, zh: true }).text, /选一处最深浸润区/);
assert.match(wallProtocolBanner({ hasLesion: true, spanCount: 2, focusCount: 0, proposedDeepestCount: 1, zh: true }).text, /选完才开始分析/);
assert.match(wallProtocolBanner({ hasLesion: true, spanCount: 0, focusCount: 1, autoAnchors: 'failed', zh: true }).text, /自动双侧锚点不够稳/);
assert.match(wallProtocolBanner({ hasLesion: true, spanCount: 1, focusCount: 1, zh: true }).text, /对侧/);
assert.match(wallProtocolBanner({
  hasLesion: true, spanCount: 2, focusCount: 1, deepestDisagree: true, zh: true,
}).text, /病灶和最深区已齐|两侧已留下/);
const confirmed = confirmAnalysisFocusPoint([[40, 20]], [42, 21]);
assert.equal(confirmed.length, 1);
const added = confirmAnalysisFocusPoint([], [40, 20]);
assert.equal(added.length, 1);
assert.deepEqual(added[0], [40, 20]);
assert.match(wallProtocolBanner({
  hasLesion: true, spanCount: 2, focusCount: 1, joinVerdict: 'joined', joinNoteZh: '两侧已按切线平滑连接。不定 cT。', spanLayers: '左三层 / 右一层', zh: true,
}).text, /左三层 \/ 右一层/);
assert.match(wallProtocolBanner({ ghost: true, keyframeTimeSec: 1.85, zh: true }).text, /邻帧残影/);
assert.match(wallProtocolBanner({ hasLesion: true, spanCount: 2, visibility: 'unseen', zh: true }).text, /看不清不等于中断/);
const restored = normalizeWallPaintSegments(twoSeg);
assert.equal(restored.length, 2);
assert.equal(restored[1].visibleLayers, 1);

const withMeta = appendWallPaintSegment([], {
  points: [[0, 10], [12, 10]],
  visibleLayers: 3,
  brushRadius: 7,
  frameIndex: 41,
  paintedAtMs: 1700000000000,
});
const sided = assignSpanSides([
  withMeta[0],
  { points: [[80, 12], [96, 12]], visibleLayers: 1 },
], [50, 10]);
assert.equal(sided[0].side, 'left');
assert.equal(sided[1].side, 'right');
assert.equal(sided[0].brushRadius, 7);
const selected = setSpanVisibleLayers(sided, 0, 2);
assert.equal(selected[0].visibleLayers, 2);
assert.equal(selected[1].visibleLayers, 1);
assert.equal(hitTestWallPaintSegment(sided, [6, 10], 8), 0);
assert.equal(popLastWallPaintSegment(sided).length, 1);
assert.equal(popLastWallPaintSegment(withMeta).length, 0);

const points = addAnalysisFocusPoint([], [40, 20]);
assert.equal(points.length, 1);
const removed = addAnalysisFocusPoint(points, [42, 21]);
assert.equal(removed.length, 0);
const replaced = [[10, 10], [80, 10], [10, 80]].reduce(
  (acc, point) => addAnalysisFocusPoint(acc, point),
  [],
);
assert.equal(replaced.length, 1);
assert.deepEqual(replaced[0], [10, 80]);
const moved = addAnalysisFocusPoint(replaced, [80, 80]);
assert.equal(moved.length, 1);
assert.deepEqual(moved[0], [80, 80]);

assert.equal(parseDoctorDepthScreen('boundary_unclear'), 'boundary_unclear');
assert.equal(parseDoctorDepthScreen('T3'), null);
assert.equal(suggestedAnatomyFromScreen('outer_clear'), 1);
assert.equal(suggestedAnatomyFromScreen('shallow_clear'), 3);
assert.equal(depthScreenConflictsAi('shallow_clear', 'T4+'), true);
assert.equal(depthScreenConflictsAi('outer_clear', 'T1'), true);
assert.equal(depthScreenConflictsAi('boundary_unclear', 'T3'), false);
assert.equal(depthScreenConflictsAi('shallow_clear', 'T1'), false);

console.log('wall-prompt ok');
