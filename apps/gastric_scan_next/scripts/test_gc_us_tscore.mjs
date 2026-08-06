#!/usr/bin/env node
/**
 * Regression checks for the no-default T-score contract.
 *
 * Node 22's built-in TypeScript stripping is enough for this dependency-free
 * module; no test framework is required for the workstation smoke path.
 */

import assert from 'node:assert/strict';
import {
  buildImagingNarrative,
  computeGcUsTscore,
  structuralStageFromExplicitSigns,
} from '../lib/gc-us-tscore.ts';

function expectIncludes(values, expected) {
  assert.ok(values.includes(expected), `Expected ${expected} in ${JSON.stringify(values)}`);
}

const empty = computeGcUsTscore({});
assert.equal(empty.ctStage, 'cTx');
assert.equal(empty.status, 'not_assessable');
assert.equal(empty.items.length, 0);
expectIncludes(empty.uncertaintyReasons, 'no_scoring_evidence');

const proxyOnly = computeGcUsTscore({
  lengthCm: 5.8,
  thicknessCm: 1.8,
  layerLabel: 'L5 / serosa',
  tHint: 'T4a',
  inContact: true,
  occupationRatio: 0.9,
  structuralEvidence: 'proxy',
});
assert.equal(proxyOnly.ctStage, 'cTx');
assert.equal(proxyOnly.status, 'uncertain');
expectIncludes(proxyOnly.uncertaintyReasons, 'wall_layer_not_explicitly_confirmed');

const noContact = computeGcUsTscore({
  layerLabel: 'L4',
  inContact: false,
  structuralEvidence: 'explicit',
});
assert.equal(noContact.ctStage, 'cTx');
assert.equal(noContact.status, 'uncertain');
expectIncludes(noContact.uncertaintyReasons, 'lesion_wall_contact_not_reliable');

const explicit = computeGcUsTscore({
  lengthCm: 4.0,
  thicknessCm: 1.5,
  layerLabel: 'L4',
  inContact: true,
  structuralEvidence: 'explicit',
  structuralStage: 'cT2',
});
assert.equal(explicit.status, 'supported');
assert.equal(explicit.ctStage, 'cT2');

const ambiguousL5 = computeGcUsTscore({
  layerLabel: 'L5 / serosa',
  inContact: true,
  structuralEvidence: 'explicit',
  structuralStage: structuralStageFromExplicitSigns('L5 / serosa', null),
});
assert.equal(ambiguousL5.status, 'uncertain');
assert.equal(ambiguousL5.ctStage, 'cTx');

const explicitSerosa = computeGcUsTscore({
  layerLabel: '浆膜连续性中断',
  inContact: true,
  structuralEvidence: 'explicit',
  structuralStage: structuralStageFromExplicitSigns(null, '浆膜连续性中断'),
});
assert.equal(explicitSerosa.status, 'supported');
assert.equal(explicitSerosa.ctStage, 'cT4a');

const narrative = buildImagingNarrative({ tscore: proxyOnly, zh: true });
assert.match(narrative, /进一步评估/);
assert.doesNotMatch(narrative, /考虑cT[1-4]/);

console.log('gc_us_tscore regression: 7/7 passed');
