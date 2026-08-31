#!/usr/bin/env node
import assert from 'node:assert/strict';
import {
  clampWallBrushRadius,
  completeWallThicknessMeasure,
  recenterWallStroke,
  recommendedBrushFromThickness,
  thicknessPxFromCaliper,
} from '../lib/wall-thickness-caliper.ts';

assert.equal(thicknessPxFromCaliper([0, 0], [0, 16]), 16);
assert.equal(recommendedBrushFromThickness(16), 8);
assert.equal(recommendedBrushFromThickness(2), 3);
assert.equal(recommendedBrushFromThickness(80), 22);
assert.equal(clampWallBrushRadius(9.6), 10);

const measure = completeWallThicknessMeasure({
  inner: [40, 20],
  outer: [40, 36],
  frameIndex: 12,
  videoTimeSec: 0.48,
});
assert.ok(measure);
assert.equal(measure.thicknessPx, 16);
assert.equal(measure.recommendedBrush, 8);
assert.equal(measure.brushUsed, 8);
assert.equal(measure.frameIndex, 12);

const centered = recenterWallStroke([
  [30, 31],
  [40, 31],
  [50, 31],
], measure);
assert.equal(centered.applied, true);
assert.equal(centered.reason, 'recentered');
assert.equal(centered.offsetPx, 3);
assert.ok(centered.points.every((point) => Math.abs(point[1] - 28) < 1e-6));

const far = recenterWallStroke([
  [30, 56],
  [40, 56],
  [50, 56],
], measure);
assert.equal(far.applied, false);
assert.equal(far.reason, 'offset_too_large');

const unrelated = recenterWallStroke([
  [130, 31],
  [140, 31],
  [150, 31],
], measure);
assert.equal(unrelated.applied, false);
assert.equal(unrelated.reason, 'outside_local_window');

const tooClose = completeWallThicknessMeasure({
  inner: [10, 10],
  outer: [10, 10.5],
});
assert.equal(tooClose, null);

console.log('wall-thickness-caliper ok', measure.recommendedBrush);
