#!/usr/bin/env node
import assert from 'node:assert/strict';
import { clarifyDeepestEcho, deepestInvasionPoint } from '../lib/wall-echo-clarify.ts';

const empty = clarifyDeepestEcho({
  gray: new Float32Array(16),
  width: 4,
  height: 4,
});
assert.equal(empty.available, false);

const width = 200;
const height = 140;
const gray = new Float32Array(width * height);
const wallY = 72;
for (let y = 0; y < height; y += 1) {
  for (let x = 0; x < width; x += 1) {
    if (y < wallY - 6) gray[y * width + x] = 40;
    else if (y < wallY - 2) gray[y * width + x] = 210;
    else if (y < wallY + 2) gray[y * width + x] = 50;
    else if (y < wallY + 6) gray[y * width + x] = 200;
    else gray[y * width + x] = 35;
  }
}
const wall = [];
for (let i = 0; i < 40; i += 1) wall.push([30 + i * 3, wallY]);
const lesion = [
  [80, 90],
  [120, 90],
  [118, 118],
  [82, 118],
];
const lumen = [
  [70, 20],
  [130, 20],
  [130, 48],
  [70, 48],
];

const deep = deepestInvasionPoint({ lesion, lumen, wall });
assert.ok(deep);
assert.ok(Math.abs(deep[1] - wallY) < 8);

const result = clarifyDeepestEcho({
  gray,
  width,
  height,
  lesion,
  lumen,
  wall,
  brushRadius: 10,
});
assert.equal(result.available, true);
assert.ok(result.classCount >= 2);
assert.ok(result.acrossPx < 18, `across ${result.acrossPx} should be narrower than a 10px brush span`);
assert.ok(result.alongPx <= 48);
assert.match(result.patternZh, /亮|暗/);
assert.match(result.noteZh, /不是全图超分/);
assert.ok(result.box.x2 - result.box.x1 < width * 0.5);
assert.ok(result.original.length === result.cropW * result.cropH);

const pinned = clarifyDeepestEcho({
  gray,
  width,
  height,
  lesion,
  lumen,
  wall,
  origin: [48, wallY],
  brushRadius: 10,
});
assert.equal(pinned.available, true);
assert.ok(Math.abs(pinned.origin[0] - 48) < 6);

console.log('wall-echo-clarify ok', {
  pattern: result.patternZh,
  classes: result.classCount,
  across: result.acrossPx,
  along: result.alongPx,
});
