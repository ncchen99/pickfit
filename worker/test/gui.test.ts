/** GUI apps: the evidence pickfit saw when it launched one reaches find_software and get_install_guide. */
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { test } from 'node:test';
import { z } from 'zod';
import { loadCatalog, type Entry, type GuiEvidence } from '../src/catalog.ts';
import type { FeaturesOut } from '../src/features.ts';
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
  assert.equal(guiSentence(operated), 'When pickfit opened it, its main screen rendered. pickfit then used it, and this worked: save notes. The launch passed again with the network off.');
  // Operations that did not reach action_checked change nothing.
  const tried: GuiEvidence = { ...operated, tier: 'ui_rendered', operations: [{ ...operated.operations![0], passed: false }] };
  assert.equal(levelLabel('install', { gui: tried }), 'It opens to its main screen');
  assert.match(guiSentence(tried), /pickfit did not use any of its features/);
});

test('the run sentence names only the features its feature list counts as working, each once, as their rows name them', () => {
  // OpenPets' case: every operation passed its own check, but the feature judge found one of them did not show the
  // feature doing its job, so the feature list marks it not shown working. The sentence must not say it worked.
  const op = (feature: string, replay: 'actions' | 'operated') => ({ feature, check: 'screen_text' as const, passed: true, replay, goal: '', observed: '' });
  const gui: GuiEvidence = {
    ...GUI,
    tier: 'action_checked',
    screen: 'main_ui',
    launch_offline: false,
    operations: [op('save notes', 'actions'), op('save notes', 'operated'), op('show pets', 'operated')],
  };
  const entry = { usage_guide: { features: [{ feature: 'save notes', title: 'Save your notes', steps: [] }] } } as unknown as Entry;
  const features: FeaturesOut = {
    recorded: true,
    checked: [{ feature: 'save notes', check: 'gui: save notes' }],
    not_checked: [{ feature: 'show pets', reason: 'not_shown', detail: 'not shown' }],
  };
  assert.equal(guiSentence(gui, { entry, features }), 'When pickfit opened it, its main screen rendered. pickfit then used it, and this worked: Save your notes.');
  // Without a feature list to go by (a run that did not judge features one by one), each passed operation, once.
  assert.equal(guiSentence(gui), 'When pickfit opened it, its main screen rendered. pickfit then used it, and this worked: save notes; show pets.');
  // Used, but nothing it used counts as working: it says so, neither "this worked" nor "did not use any".
  const none: FeaturesOut = { recorded: true, checked: [], not_checked: [...features.not_checked, { feature: 'save notes', reason: 'not_shown', detail: '' }] };
  assert.equal(guiSentence(gui, { entry, features: none }), 'When pickfit opened it, its main screen rendered. pickfit then used it, but what it saw didn’t show a feature working.');
});

test("the tools' output schema accepts every GUI tier a record can carry (a function-level GUI app broke find_software)", () => {
  const py = readFileSync(join(import.meta.dirname, '..', '..', 'pickfit', 'schema.py'), 'utf8');
  const tiers = [...py.match(/type GuiTier = Literal\[([^\]]*)\]/)![1].matchAll(/"([^"]+)"/g)].map((m) => m[1]);
  assert.ok(tiers.includes('action_checked'));
  for (const tier of tiers) assert.ok(gui.safeParse({ ...GUI, tier }).success, tier);
});

test("the tools' published output schema allows every key an operated GUI app carries (openpets broke find_software)", () => {
  const operated: GuiEvidence = {
    ...GUI,
    tier: 'action_checked',
    operations: [{ feature: 'set reminders', check: 'screen_text', passed: true, replay: 'operated', goal: 'Right-click the pet.', observed: 'on screen: yes' }],
  };
  // A client checks structured content against this JSON Schema, where every object forbids other keys.
  const schema = z.toJSONSchema(gui, { io: 'output' }) as { anyOf: Array<{ type?: string; properties?: Record<string, any>; additionalProperties?: boolean }> };
  const object = schema.anyOf.find((s) => s.type === 'object')!;
  assert.equal(object.additionalProperties, false);
  assert.deepEqual(Object.keys(operated).filter((k) => !(k in object.properties!)), []);
  const item = object.properties!.operations.items;
  assert.deepEqual(Object.keys(operated.operations![0]).filter((k) => !(k in item.properties)), []);
  assert.ok(gui.safeParse(operated).success);
});
