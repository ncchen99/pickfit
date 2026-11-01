/** get_install_guide's check_in: read-only commands from the recorded steps, and how to report back. */
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { loadCatalog } from '../src/catalog.ts';
import { installGuide } from '../src/install.ts';
import { fixtureCatalog, fixtureIndex } from './helpers.ts';

const catalog = fixtureCatalog();
const NOW = new Date('2026-11-01T08:00:00Z');
const commands = (out: ReturnType<typeof installGuide>) => out.check_in!.commands.map((c) => c.command);

test('a brew install from a tap: the command on PATH and the formula by its own name', () => {
  const out = installGuide(catalog, { slug: 'fixture-llm-runner', os: 'macos', arch: 'arm64' }, NOW);
  assert.deepEqual(commands(out), ['command -v fixture-llm-runner', 'brew list --versions fixture-llm-runner']);
  assert.equal(out.check_in!.after_days, 7);
  assert.equal(out.check_in!.valid_until, '2027-03-01'); // 120 days on
  const how = out.check_in!.how;
  assert.match(how, /^Not now\./);
  assert.match(how, /ask whether you may check if they still use Fixture LLM Runner\. Only after a yes/);
  assert.match(how, /still_using if it is installed and they still use it; abandoned if it is gone or they stopped/);
  assert.match(how, /last_used: this_week, this_month, older or unknown/);
  assert.match(how, /never the command output, an exact date, a path, or other software\. If the user says no, report nothing\./);
});

test('a script install has no package to list; a pipe-to-shell step is never a check', () => {
  const out = installGuide(catalog, { slug: 'fixture-llm-runner', os: 'linux' }, NOW);
  assert.deepEqual(commands(out), ['command -v fixture-llm-runner']);
});

test('pipx, cargo and npm list only this tool; Windows gets PowerShell', () => {
  assert.deepEqual(commands(installGuide(catalog, { slug: 'fixture-transcribe', os: 'linux' }, NOW)), [
    'command -v fixture-transcribe',
    "pipx list --short | grep -i -- '^fixture-transcribe '",
  ]);
  assert.deepEqual(commands(installGuide(catalog, { slug: 'fixture-transcribe', os: 'windows' }, NOW)), [
    'Get-Command fixture-transcribe -ErrorAction SilentlyContinue',
    "pipx list --short | Select-String -Pattern '^fixture-transcribe '",
  ]);
  assert.deepEqual(commands(installGuide(catalog, { slug: 'fixture-chat-tui', os: 'linux' }, NOW)), [
    'command -v fixture-chat-tui',
    "cargo install --list | grep -i -- '^fixture-chat-tui '",
  ]);
  // go install has no list command; the check still finds the binary.
  assert.deepEqual(commands(installGuide(catalog, { slug: 'fixture-json-query', os: 'linux' }, NOW)), [
    'command -v fixture-json-query',
  ]);
});

test('an MCP server: is it still in the client config, and its npm package', () => {
  const out = installGuide(catalog, { slug: 'fixture-notes-mcp', os: 'linux' }, NOW);
  assert.deepEqual(commands(out), ['claude mcp get fixture-notes-mcp', 'npm ls -g --depth=0 notes-mcp']);
  assert.match(out.check_in!.commands[0].shows, /look for "fixture-notes-mcp" in its mcpServers config only/);
});

test('a macOS app: when macOS last saw it opened, turned into last_used, never sent as a date', () => {
  const data = structuredClone(fixtureIndex()) as any;
  const entry = data.entries.find((e: any) => e.slug === 'fixture-chat-tui');
  entry.kind = 'desktop_app';
  entry.install.macos = { ...entry.install.linux, steps: [{ command: 'brew install --cask fixture-chat-tui', purpose: null }] };
  const out = installGuide(loadCatalog(data), { slug: 'fixture-chat-tui', os: 'macos' }, NOW);
  const mdls = out.check_in!.commands.find((c) => c.command.startsWith('mdls'));
  assert.equal(mdls?.command, `mdls -name kMDItemLastUsedDate -raw "/Applications/${entry.name}.app"`);
  assert.match(mdls!.shows, /never send the date/);
  assert.ok(commands(out).includes('brew list --versions fixture-chat-tui'));
  // Linux records no app use, so the same app there gets no mdls line.
  assert.ok(!commands(installGuide(loadCatalog(data), { slug: 'fixture-chat-tui', os: 'linux' }, NOW)).some((c) => c.startsWith('mdls')));
});

test('no recorded guide, no check_in', () => {
  const data = structuredClone(fixtureIndex()) as any;
  const entry = { ...data.entries.find((e: any) => e.slug === 'fixture-json-query'), install: {} };
  const bare = loadCatalog({ ...data, entries: [entry] });
  assert.equal(installGuide(bare, { slug: 'fixture-json-query', os: 'linux' }, NOW).check_in, null);
});
