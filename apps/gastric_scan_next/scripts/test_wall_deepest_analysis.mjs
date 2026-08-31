#!/usr/bin/env node
import assert from 'node:assert/strict';
import { analyzeDeepestChannels, pickFlankStroke } from '../lib/wall-deepest-analysis.ts';
import { clarifyDeepestEcho } from '../lib/wall-echo-clarify.ts';

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

const pinned = clarifyDeepestEcho({
  gray,
  width,
  height,
  lesion,
  lumen,
  wall,
  origin: [100, wallY],
  brushRadius: 10,
});
assert.equal(pinned.available, true);
assert.ok(Math.abs(pinned.origin[0] - 100) < 8);

const waiting = analyzeDeepestChannels({
  gray,
  width,
  height,
  lesion,
  lumen,
  wall,
  brushRadius: 10,
  aiDeepest: { center: [110, wallY], radius: 12, source: 'ai' },
});
assert.equal(waiting.primary, null);
assert.equal(waiting.doctor, null);
assert.match(waiting.noteZh, /选完才开始分析|选择一处/);
assert.doesNotMatch(waiting.noteZh, /确定 cT/);

const chosen = analyzeDeepestChannels({
  gray,
  width,
  height,
  lesion,
  lumen,
  wall,
  brushRadius: 10,
  doctorDeepest: [100, wallY],
  aiDeepest: { center: [140, wallY], radius: 12, source: 'ai' },
});
assert.equal(chosen.disagree, false);
assert.ok(chosen.doctor?.echo?.available);
assert.equal(chosen.ai, null);
assert.match(chosen.noteZh, /最深区回声/);
assert.doesNotMatch(chosen.noteZh, /复核|AI 候选区/);

const stroke = pickFlankStroke([
  { points: [[8, 70], [16, 71]], visibleLayers: 3 },
  { points: [[80, 70], [90, 70], [100, 71], [110, 70]], visibleLayers: 3, source: 'ai_propose' },
]);
assert.equal(stroke.length, 4);

console.log('wall-deepest-analysis ok', {
  waiting: Boolean(waiting.primary),
  chosen: chosen.doctor?.echo?.patternZh,
});
