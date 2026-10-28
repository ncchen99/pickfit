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
