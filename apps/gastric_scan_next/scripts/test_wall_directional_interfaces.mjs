#!/usr/bin/env node
import assert from 'node:assert/strict';
import {
  isFourInterfaceSet,
  trackDirectionalInterfaces,
  usableLumenCenter,
  wallStationsAndNormals,
} from '../lib/wall-directional-interfaces.ts';

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
for (let y = 56; y <= 88; y += 1) {
  for (let x = 92; x <= 148; x += 1) {
    const dx = (x - 120) / 28;
    const dy = (y - 72) / 16;
    if (dx * dx + dy * dy <= 1) gray[y * width + x] = 16;
  }
}

const stroke = Array.from({ length: 48 }, (_, index) => [16 + index * 4.4, wallY]);
const lesion = [[96, 58], [144, 58], [148, 86], [92, 86]];
const lumen = [[40, 18], [200, 18], [200, 48], [40, 48]];

const track = trackDirectionalInterfaces({
  gray,
  width,
  height,
  stroke,
  lesion,
  lumen,
  brushRadius: 8,
});
assert.equal(track.available, true, track.noteEn);
assert.equal(track.method, 'directional');
assert.equal(track.layers.length, 4);
assert.ok(isFourInterfaceSet(track.layers.map((layer) => layer.curve)));
assert.ok(track.layers.every((layer) => layer.curve.length >= 20));
const diffs = [];
for (let index = 0; index < track.layers[0].curve.length; index += 1) {
  for (let boundary = 1; boundary < 4; boundary += 1) {
    const a = track.layers[boundary - 1].curve[index];
    const b = track.layers[boundary].curve[index];
    diffs.push((b[1] - a[1]));
  }
}
assert.ok(diffs.every((gap) => gap >= 1.5), 'interfaces must stay ordered outward');
assert.ok(track.layers.some((layer) => layer.imaginaryMask.some(Boolean)), 'lesion interior should be dashed');
assert.equal(track.extraserosal, false);
assert.equal(track.layersBreached, 0);
assert.match(track.noteEn, /not a cT/i);

const above = wallStationsAndNormals([[20, 80], [200, 80]], [110, 24], []);
const below = wallStationsAndNormals([[20, 80], [200, 80]], [110, 140], []);
const meanNy = (normals) => normals.reduce((sum, item) => sum + item[1], 0) / normals.length;
assert.ok(meanNy(above.normals) > 0, 'lumen above should point +Y');
assert.ok(meanNy(below.normals) < 0, 'lumen below should point -Y');

const windowBox = usableLumenCenter([[0, 0], [239, 0], [239, 139], [0, 139]], width, height);
assert.equal(windowBox.center, null);
assert.equal(windowBox.source, 'unusable_image_window');

console.log('wall-directional-interfaces ok', {
  stations: track.wall.length,
  phase: track.phase,
  cavity: track.cavitySideSource,
  dashed: track.layers[0].imaginaryMask.filter(Boolean).length,
});
