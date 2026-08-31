#!/usr/bin/env node
import assert from 'node:assert/strict';
import { searchFlankAxesFromLesion } from '../lib/wall-flank-axis-from-lesion.ts';
import { nearLesion, trackOrderedLayers } from '../lib/wall-ordered-track.ts';

const width = 280;
const height = 160;
const wallY = 80;
const gray = new Float32Array(width * height);
for (let y = 0; y < height; y += 1) {
  for (let x = 0; x < width; x += 1) {
    let value = 28;
    if (y >= wallY - 7 && y < wallY - 3) value = 210;
    else if (y >= wallY - 3 && y < wallY + 2) value = 46;
    else if (y >= wallY + 2 && y < wallY + 6) value = 198;
    gray[y * width + x] = value;
  }
}
const lesion = [[118, 70], [162, 70], [160, 104], [120, 104]];
for (let y = 70; y <= 104; y += 1) {
  for (let x = 118; x <= 162; x += 1) gray[y * width + x] = 22;
}
const lumen = [[40, 18], [240, 18], [240, 48], [40, 48]];

const axes = searchFlankAxesFromLesion({ gray, width, height, lesion, lumen });
assert.equal(axes.length, 2);
assert.deepEqual(axes.map((axis) => axis.side).sort(), ['left', 'right']);
assert.ok(axes.every((axis) => axis.validStations >= 4 && axis.source === 'layer_search'));
axes.forEach((axis) => {
  assert.ok(axis.heading.every((point) => !nearLesion(point, lesion, 12)));
  const traced = trackOrderedLayers({
    gray,
    width,
    height,
    stroke: axis.heading,
    lesion,
    lumen,
    targetLayers: 3,
    brushRadius: 6,
  });
  assert.equal(traced.available, true, traced.noteEn);
  assert.equal(traced.method, 'ordered');
});

const noLesion = searchFlankAxesFromLesion({ gray, width, height, lesion: [[1, 1]] });
assert.equal(noLesion.length, 0);

console.log('wall-flank-axis-from-lesion ok', axes.map((axis) => ({
  side: axis.side,
  source: axis.source,
  stations: axis.validStations,
})));
