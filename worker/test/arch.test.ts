/**
 * "Verified on your system" honors the CPU architecture when the request gives
 * one: an arm64-only macOS run is not an Intel Mac. Without an arch the answer
 * is for the OS only, and the response says which CPU the run was on.
 * Fixture runs: fixture-llm-runner on macos arm64 and linux x86_64.
 */
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { toCard } from '../src/cards.ts';
import { findSoftware, type FindInput } from '../src/find.ts';
import { installGuide } from '../src/install.ts';
import { answer, fixtureCatalog, harness, metaResponse } from './helpers.ts';

const runner = () => fixtureCatalog().bySlug.get('fixture-llm-runner')!;
const LLM: FindInput = { need: 'run a language model offline on my laptop', must_run_locally: true };

test('the card the model reads: verified_on_user_os needs the arch to match when one is given', () => {
  const entry = runner();
  assert.equal(toCard(entry, 'macos', 'arm64').verified_on_user_os, true);
  assert.equal(toCard(entry, 'macos', 'x86_64').verified_on_user_os, false);
  assert.equal(toCard(entry, 'macos').verified_on_user_os, true); // OS only, as before
  assert.equal(toCard(entry, 'linux', 'arm64').verified_on_user_os, false); // the Linux run was x86_64
  assert.equal(toCard(entry, 'linux', 'x86_64').verified_on_user_os, true);
  assert.equal(toCard(entry).verified_on_user_os, null);
  // verified_on always names the run's CPU, so the model can tell an arm64 Mac run from an Intel one.
  assert.ok((toCard(entry, 'macos', 'x86_64').verified_on as string[]).some((label) => label.startsWith('macos arm64:')));
});

async function runnerPick(input: FindInput) {
  const h = harness(() => metaResponse(answer()));
  const out = await findSoftware(input, h.deps);
  const card = h.requests[0].body.input[1].content
    .split('\n')
    .map((line: string) => (line.startsWith('{') ? JSON.parse(line) : null))
    .find((c: any) => c?.slug === 'fixture-llm-runner');
  return { pick: out.picks.find((p) => p.slug === 'fixture-llm-runner')!, card };
}

test('an arm64-only macOS run: true for arm64, false for x86_64, OS-only without an arch', async () => {
  const arm = await runnerPick({ ...LLM, os: 'macos', arch: 'arm64' });
  assert.equal(arm.pick.verification.verified_on_user_os, true);
  assert.equal(arm.card.verified_on_user_os, true);
  assert.ok(!arm.pick.tradeoffs.some((t) => /Verified on/.test(t)));

  const intel = await runnerPick({ ...LLM, os: 'macos', arch: 'x86_64' });
  assert.equal(intel.pick.verification.verified_on_user_os, false);
  assert.equal(intel.card.verified_on_user_os, false); // the model sees the same answer
  assert.deepEqual([intel.pick.verification.os, intel.pick.verification.arch], ['macos', 'arm64']);
  assert.equal(intel.pick.tradeoffs[0], 'Verified on macos arm64 only; pickfit has not run its install steps on x86_64.');

  const unsaid = await runnerPick({ ...LLM, os: 'macos' });
  assert.equal(unsaid.pick.verification.verified_on_user_os, true);
  assert.equal(unsaid.pick.verification.arch, 'arm64'); // says which CPU it was verified on
});

test('a Linux x86_64 run asked as linux/arm64 is not verified on the user system', async () => {
  const { pick, card } = await runnerPick({ ...LLM, os: 'linux', arch: 'arm64' });
  assert.equal(pick.verification.verified_on_user_os, false);
  assert.equal(card.verified_on_user_os, false);
  assert.equal(pick.tradeoffs[0], 'Verified on linux x86_64 only; pickfit has not run its install steps on arm64.');
});

test('the guard drops a model reason that claims verification on an Intel Mac from an arm64 run', async () => {
  const claim = { claim: 'Verified on your system', field: 'verified_on_user_os', value: 'true' };
  const picks = answer().picks.map((p) => (p.slug === 'fixture-llm-runner' ? { ...p, reasons: [claim, ...p.reasons] } : p));
  for (const [arch, kept] of [
    ['arm64', true],
    ['x86_64', false],
  ] as const) {
    const h = harness(() => metaResponse(answer({ picks })));
    const out = await findSoftware({ ...LLM, os: 'macos', arch }, h.deps);
    const reasons = out.picks.find((p) => p.slug === 'fixture-llm-runner')!.why;
    assert.equal(reasons.some((r) => r.field === 'verified_on_user_os'), kept, arch);
  }
});

test('get_install_guide: no arch means exact for the OS, with a note naming the run CPU', () => {
  const catalog = fixtureCatalog();
  const unsaid = installGuide(catalog, { slug: 'fixture-llm-runner', os: 'macos' });
  assert.equal(unsaid.applies_to_user_system.match, 'exact');
  assert.match(unsaid.applies_to_user_system.note!, /macos\/arm64; the request did not say this machine's CPU architecture/);
  assert.deepEqual(installGuide(catalog, { slug: 'fixture-llm-runner', os: 'macos', arch: 'arm64' }).applies_to_user_system, {
    match: 'exact',
    note: null,
  });
  assert.equal(
    installGuide(catalog, { slug: 'fixture-llm-runner', os: 'linux', arch: 'arm64' }).applies_to_user_system.match,
    'same_os_other_arch',
  );
});
