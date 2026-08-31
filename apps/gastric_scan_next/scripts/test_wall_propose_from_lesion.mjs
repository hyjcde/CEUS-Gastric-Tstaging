#!/usr/bin/env node
import assert from 'node:assert/strict';
import {
  deepestRegionRadius,
  deepestRegionsDisagree,
  hasDoctorPaintedSpans,
  mergeAutoProposedSpans,
  hitProposedDeepestRegion,
  proposeWallFromLesion,
  provisionalHeadingFromLesion,
} from '../lib/wall-propose-from-lesion.ts';

const lesion = [
  [80, 70],
  [140, 68],
  [148, 110],
  [136, 128],
  [88, 126],
  [72, 100],
];
const lumen = [
  [70, 18],
  [150, 18],
  [150, 48],
  [70, 48],
];

const heading = provisionalHeadingFromLesion(lesion, { width: 220, height: 180 }, lumen);
assert.ok(heading.length >= 20);
assert.ok(heading.every((point) => point[0] >= 1 && point[0] <= 218 && point[1] >= 1 && point[1] <= 178));

const ok = proposeWallFromLesion({
  lesion,
  lumen,
  frameSize: { width: 220, height: 180 },
  visibleLayers: 3,
  brushRadius: 8,
  frameIndex: 12,
});
assert.equal(ok.available, true);
assert.equal(ok.reason, 'ok');
assert.equal(ok.segments.length, 2);
assert.ok(ok.segments.every((segment) => segment.source === 'ai_propose'));
assert.ok(ok.segments.some((segment) => segment.side === 'left'));
assert.ok(ok.segments.some((segment) => segment.side === 'right'));
assert.ok(ok.aiDeepest && ok.aiDeepest.center[1] > 60, 'deepest should sit on the deep face');
assert.equal(ok.deepestCandidates.length, 1);
assert.match(ok.noteZh, /选完才开始分析/);
assert.doesNotMatch(ok.noteZh, /确定 cT|突破点/);

const empty = proposeWallFromLesion({ lesion: [[1, 1]] });
assert.equal(empty.available, false);
assert.equal(empty.reason, 'need_lesion');

const tight = [
  [100, 80],
  [108, 80],
  [108, 88],
  [100, 88],
];
const failed = proposeWallFromLesion({
  lesion: tight,
  frameSize: { width: 120, height: 100 },
});
assert.equal(failed.available, false);
assert.equal(failed.reason, 'need_more_spans');
assert.ok(failed.deepestCandidates.length >= 1);
assert.match(failed.noteZh, /手画|选一处最深/);

assert.equal(hasDoctorPaintedSpans([{ source: 'ai_propose' }, { source: 'ai_propose' }]), false);
assert.equal(hasDoctorPaintedSpans([{ source: 'ai_propose' }, { points: [[1, 1]] }]), true);
assert.equal(hasDoctorPaintedSpans([{ source: 'doctor' }]), true);
const leftover = mergeAutoProposedSpans(
  [{ points: [[1, 1], [8, 1]], visibleLayers: 3, source: 'ai_propose' }],
  [],
);
assert.equal(leftover.length, 0);
const keptDoctor = mergeAutoProposedSpans(
  [{ points: [[1, 1], [8, 1]], visibleLayers: 3, source: 'doctor' }],
  ok.segments,
);
assert.equal(keptDoctor[0].source, 'doctor');
const replaced = mergeAutoProposedSpans(
  [{ points: [[1, 1], [8, 1]], visibleLayers: 3, source: 'ai_propose' }],
  ok.segments,
);
assert.equal(replaced.length, 2);

const radius = deepestRegionRadius(lesion);
assert.ok(radius >= 10 && radius <= 28);

const hit = hitProposedDeepestRegion(ok.deepestCandidates, ok.aiDeepest.center);
assert.ok(hit);
assert.equal(deepestRegionsDisagree(ok.aiDeepest.center, ok.aiDeepest), false);
assert.equal(deepestRegionsDisagree([10, 10], ok.aiDeepest, 12), true);

console.log('wall-propose-from-lesion ok', {
  spans: ok.segments.length,
  candidates: ok.deepestCandidates.length,
  deep: ok.aiDeepest.center.map((n) => Math.round(n)),
  failReason: failed.reason,
});
