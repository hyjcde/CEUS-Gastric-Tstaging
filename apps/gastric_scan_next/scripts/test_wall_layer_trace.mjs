#!/usr/bin/env node
import assert from 'node:assert/strict';
import { readoutFromTrace, traceWallLayersFromPaint } from '../lib/wall-layer-trace.ts';

const empty = traceWallLayersFromPaint({
  gray: new Float32Array(16),
  width: 4,
  height: 4,
  stroke: [[1, 1], [2, 1]],
  brushRadius: 6,
});
assert.equal(empty.available, false);

const width = 240;
const height = 140;
const gray = new Float32Array(width * height);
const wallY = 72;
for (let x = 0; x < width; x += 1) {
  for (let y = 0; y < height; y += 1) {
    const offset = y - wallY;
    let value = 35;
    if (offset >= -12 && offset < -6) value = 205;
    else if (offset >= -6 && offset < 2) value = 42;
    else if (offset >= 2 && offset < 8) value = 190;
    gray[y * width + x] = value;
  }
}
const stroke = Array.from({ length: 40 }, (_, index) => [20 + index * 5, wallY]);
const lesion = [[118, 58], [162, 58], [160, 88], [120, 88]];
const lumen = [[40, 18], [200, 18], [200, 48], [40, 48]];

const traced = traceWallLayersFromPaint({
  gray,
  width,
  height,
  stroke,
  brushRadius: 8,
  lesion,
  lumen,
});
assert.equal(traced.available, true);
assert.equal(traced.method, 'directional');
assert.equal(traced.paintedLayers, 4);
assert.equal(traced.layers.length, 4);
assert.ok(traced.layers.every((layer) => layer.curve.length >= 16));
assert.equal(traced.ticks.length, 5);
assert.ok(traced.ticks[0].nameZh.includes('黏膜'));
const readout = readoutFromTrace(traced);
assert.equal(readout.method, 'directional');
assert.equal(readout.paintedLayers, 4);

const oneLayer = traceWallLayersFromPaint({
  gray,
  width,
  height,
  stroke,
  brushRadius: 8,
  lesion,
  lumen,
  targetLayers: 1,
});
assert.equal(oneLayer.available, true);
assert.equal(oneLayer.paintedLayers, 4, 'expected-line always tracks four interfaces');

console.log('wall-layer-trace ok', {
  painted: traced.paintedLayers,
  method: traced.method,
  pts: traced.layers[0].curve.length,
});
