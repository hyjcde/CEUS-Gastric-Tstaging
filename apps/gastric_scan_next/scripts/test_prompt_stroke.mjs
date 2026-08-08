#!/usr/bin/env node
/**
 * Pure-function checks for scribble / lasso stroke stabilization.
 */

import assert from 'node:assert/strict';
import {
  appendFinalPromptPoint,
  appendPromptPoint,
  prepareSubmitPromptStroke,
  resamplePromptPath,
} from '../lib/human-assist/prompt-stroke.ts';

const stroke = [[0, 0], [10, 0], [20, 0], [30, 0]];
const withEndpoint = appendFinalPromptPoint(stroke, [40, 0], 0.5);
assert.equal(withEndpoint[withEndpoint.length - 1][0], 40);
assert.equal(withEndpoint[withEndpoint.length - 1][1], 0);

const dense = [];
for (let index = 0; index < 200; index += 1) dense.push([index, Math.sin(index / 8)]);
const capped = resamplePromptPath(dense, 48, false);
assert.ok(capped.length <= 48);
assert.equal(capped[0][0], dense[0][0]);
assert.ok(Math.abs(capped[capped.length - 1][0] - dense[dense.length - 1][0]) < 1.5);

const short = prepareSubmitPromptStroke([[0, 0], [1, 0]], 'scribble');
assert.equal(short.ok, false);
assert.equal(short.reason, 'too_short');

const tinyLasso = prepareSubmitPromptStroke(
  [[0, 0], [2, 0], [2, 2], [0, 2]],
  'lasso',
  { minAreaPx2: 64 },
);
assert.equal(tinyLasso.ok, false);
assert.equal(tinyLasso.reason, 'lasso_area_too_small');

const goodLasso = prepareSubmitPromptStroke(
  [[0, 0], [20, 0], [20, 20], [0, 20]],
  'lasso',
);
assert.equal(goodLasso.ok, true);
assert.ok(goodLasso.points.length >= 3);
assert.ok(
  Math.hypot(
    goodLasso.points[0][0] - goodLasso.points[goodLasso.points.length - 1][0],
    goodLasso.points[0][1] - goodLasso.points[goodLasso.points.length - 1][1],
  ) < 1e-6,
);

const sampled = appendPromptPoint([[0, 0]], [0.5, 0], 2);
assert.equal(sampled.length, 1);
const moved = appendPromptPoint([[0, 0]], [3, 0], 2);
assert.equal(moved.length, 2);

console.log('prompt-stroke checks passed');
