import assert from 'node:assert/strict';
import { test } from 'node:test';
import { installGuide, UnknownSlugError } from '../src/install.ts';
import { fixtureCatalog } from './helpers.ts';

const catalog = fixtureCatalog();

test('exact match: steps checked by hand on macOS', () => {
  const out = installGuide(catalog, { slug: 'fixture-llm-runner', os: 'macos', arch: 'arm64' });
  assert.equal(out.applies_to_user_system.match, 'exact');
  assert.equal(out.verification.status, 'verified');
  assert.equal(out.verification.method, 'human');
  assert.deepEqual(out.steps.map((s) => s.command), ['brew install fixture/tap/fixture-llm-runner']);
  assert.deepEqual(out.manual_steps, [
    { title: 'Allow incoming connections if macOS asks (only for access from other devices)', run_by: 'user' },
  ]);
  assert.deepEqual(out.verify, { command: 'fixture-llm-runner --version', expected_contains: 'fixture-llm-runner 0.4.1' });
  assert.deepEqual(out.warnings, []);
});

test('replayed sandbox steps carry evidence, pitfalls and a pipe-to-shell warning', () => {
  const out = installGuide(catalog, { slug: 'fixture-llm-runner', os: 'linux' });
  assert.equal(out.verification.replayed, true);
  assert.equal(out.verification.runner, 'modal-gvisor');
  assert.equal(out.verification.evidence_url, 'https://example.invalid/runs/run-20261028-linux-1');
  assert.equal(out.known_issues.length, 1);
  assert.match(out.warnings.join(' '), /pipes a downloaded script/);
  assert.equal(out.verification.works_offline, true);
  assert.equal(out.first_task, 'fixture-llm-runner serve --model tiny-test --once');
  assert.deepEqual(out.first_task_setup, [{ command: 'fixture-llm-runner pull tiny-test', run_in_background: false }]);
});

test('a run with no offline check says so', () => {
  const out = installGuide(catalog, { slug: 'fixture-llm-runner', os: 'macos', arch: 'arm64' });
  assert.equal(out.verification.works_offline, null);
  assert.deepEqual(out.first_task_setup, []);
});

test('README-only steps are never returned: other OS steps come with a note', () => {
  const out = installGuide(catalog, { slug: 'fixture-transcribe', os: 'macos' });
  assert.equal(out.applies_to_user_system.match, 'other_os');
  assert.match(out.applies_to_user_system.note ?? '', /not run .* on macos; these steps were checked on linux/);
  assert.ok(out.steps.every((s) => !s.command.includes('brew')));
  assert.equal(out.steps[0].needs_sudo, true);
  assert.match(out.warnings.join(' '), /sudo/);
});

test('same OS on another architecture is flagged', () => {
  const out = installGuide(catalog, { slug: 'fixture-transcribe', os: 'linux', arch: 'arm64' });
  assert.equal(out.applies_to_user_system.match, 'same_os_other_arch');
});

test('unknown slug is an error that points back to find_software', () => {
  assert.throws(() => installGuide(catalog, { slug: 'nope', os: 'linux' }), UnknownSlugError);
});

test('every guide carries a rec_id, how_we_know, evidence_url and matched_by rules', () => {
  const issued = installGuide(catalog, { slug: 'fixture-llm-runner', os: 'linux' });
  assert.match(issued.rec_id, /^rec_[0-9a-f]{32}$/);
  assert.equal(issued.matched_by, 'rules');
  assert.equal(issued.evidence_url, 'https://example.invalid/runs/run-20261028-linux-1');
  assert.match(issued.how_we_know, /fresh linux\/x86_64 sandbox \(modal-gvisor\) and replayed the steps from scratch/);
  assert.match(issued.how_we_know, /no model wrote or changed them/);
  assert.match(
    installGuide(catalog, { slug: 'fixture-transcribe', os: 'linux' }).how_we_know,
    /sandbox \(modal-gvisor\) with a GPU \(Tesla T4\) and a simulated microphone that played words pickfit spoke for each check and replayed/,
  );

  const rec = 'rec_' + 'a'.repeat(32);
  assert.equal(installGuide(catalog, { slug: 'fixture-llm-runner', os: 'linux', rec_id: rec }).rec_id, rec);
  // Not one of ours: a fresh handle replaces it.
  assert.notEqual(installGuide(catalog, { slug: 'fixture-llm-runner', os: 'linux', rec_id: 'made-up' }).rec_id, 'made-up');
});
