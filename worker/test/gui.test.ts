/** GUI apps: the evidence pickfit saw when it launched one reaches find_software and get_install_guide. */
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { test } from 'node:test';
import { loadCatalog, type GuiEvidence } from '../src/catalog.ts';
import { ranSentence } from '../src/evidence.ts';
import { guiSentence, levelLabel } from '../src/ui/facts.ts';
import { installGuide } from '../src/install.ts';
import { gui } from '../src/server.ts';
import { fixtureIndex } from './helpers.ts';

export const GUI: GuiEvidence = {
  tier: 'ui_rendered',
  screen: 'first_run',
  display: 'Xvfb 1280x800x24, no window manager, no GPU',
  launch_offline: true,
};

/** The fixture index with fixture-chat-tui's Linux run as a GUI app's launch. */
export function withGui(gui: GuiEvidence = GUI): unknown {
  const data = structuredClone(fixtureIndex()) as any;
  const entry = data.entries.find((e: any) => e.slug === 'fixture-chat-tui');
  entry.kind = 'desktop_app';
  entry.install.linux.run.gui = gui;
  for (const run of entry.verification.passed_runs) if (run.os === 'linux') run.gui = gui;
  return data;
}

test('how_we_know says what pickfit saw of a GUI launch, and that no feature was used', () => {
  const out = installGuide(loadCatalog(withGui()), { slug: 'fixture-chat-tui', os: 'linux' });
  assert.match(out.how_we_know, /the app opened a window of its own on a virtual display \(Xvfb 1280x800x24, no window manager, no GPU\)/);
  assert.match(out.how_we_know, /a separate model, reading a screenshot of that window, judged that its first-run \(setup\) screen rendered/);
  assert.match(out.how_we_know, /and the launch passed again with the network off/);
  assert.match(out.how_we_know, /pickfit did not use any of its features/);
  assert.doesNotMatch(out.how_we_know, /the install finished and the tool started/);
  assert.deepEqual([out.verification.level, out.verification.gui], ['install', GUI]);
});

test('each screen reads as what it is; other software keeps its own sentence', () => {
  const main = installGuide(loadCatalog(withGui({ ...GUI, screen: 'main_ui', launch_offline: false })), {
    slug: 'fixture-chat-tui',
    os: 'linux',
  });
  assert.match(main.how_we_know, /judged that its main screen rendered\. That shows/);
  const wall = installGuide(loadCatalog(withGui({ ...GUI, tier: 'window', screen: 'sign_in_wall' })), {
    slug: 'fixture-chat-tui',
    os: 'linux',
  });
  assert.match(wall.how_we_know, /it showed a sign-in screen, and nothing past it was checked/);
  const plain = installGuide(loadCatalog(fixtureIndex()), { slug: 'fixture-chat-tui', os: 'linux' });
  assert.equal(plain.verification.gui, null);
  assert.match(plain.how_we_know, /the install finished and the tool started/);
  const guide = loadCatalog(withGui()).bySlug.get('fixture-chat-tui')!.install.linux!;
  assert.match(ranSentence(guide), /^pickfit installed it in a fresh linux\/x86_64 sandbox/);
});

test('an operated GUI app says which feature passed pickfit\'s own check, and its headline says it worked', () => {
  const operated: GuiEvidence = {
    ...GUI,
    tier: 'action_checked',
    screen: 'main_ui',
    operations: [
      { feature: 'save notes', check: 'file', passed: true, replay: 'actions', goal: 'Type {nonce} and save it.', observed: 'file ...: contains "pickfit1a2b3c": yes' },
      { feature: 'export PDF', check: 'file', passed: false, replay: 'operated', goal: 'Export it as PDF.', observed: 'no file under /home/sbx/' },
    ],
  };
  const out = installGuide(loadCatalog(withGui(operated)), { slug: 'fixture-chat-tui', os: 'linux' });
  assert.match(out.how_we_know, /A model \(Muse Spark Open\) then operated it from screenshots, pickfit performing every click and keystroke/);
  assert.match(out.how_we_know, /save notes \(checked by a file the app saved, which pickfit read itself\)/);
  assert.doesNotMatch(out.how_we_know, /export PDF/);
  assert.doesNotMatch(out.how_we_know, /did not use any of its features/);
  assert.equal(levelLabel('function', { gui: operated }), 'A feature worked when operated');
  assert.match(guiSentence(operated), /its main screen rendered\. A model \(Muse Spark Open\) then operated it/);
  // Operations that did not reach action_checked change nothing.
  const tried: GuiEvidence = { ...operated, tier: 'ui_rendered', operations: [{ ...operated.operations![0], passed: false }] };
  assert.equal(levelLabel('install', { gui: tried }), 'It opens to its main screen');
  assert.match(guiSentence(tried), /pickfit did not use any of its features/);
});

test("the tools' output schema accepts every GUI tier a record can carry (a function-level GUI app broke find_software)", () => {
  const py = readFileSync(join(import.meta.dirname, '..', '..', 'pickfit', 'schema.py'), 'utf8');
  const tiers = [...py.match(/type GuiTier = Literal\[([^\]]*)\]/)![1].matchAll(/"([^"]+)"/g)].map((m) => m[1]);
  assert.ok(tiers.includes('action_checked'));
  for (const tier of tiers) assert.ok(gui.safeParse({ ...GUI, tier }).success, tier);
});
