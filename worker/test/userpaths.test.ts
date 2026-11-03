/** Install commands a user runs vs. the commands pickfit's sandbox ran: get_install_guide and the tool page. */
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { z } from 'zod';
import { loadCatalog, type UserGuide } from '../src/catalog.ts';
import { installGuide } from '../src/install.ts';
import { installSection, type FormValues } from '../src/page.ts';
import { renderTool } from '../src/pages/tool.ts';
import { installOutput } from '../src/server.ts';
import { fixtureIndex } from './helpers.ts';

const RAN = 'cargo install --root /home/sbx/.local fixture-chat-tui';
const CHECK = '/home/sbx/.local/bin/fixture-chat-tui --version';
const FIRST = 'cd /home/sbx/work && fixture-chat-tui --endpoint http://127.0.0.1:8080/v1';

/** fixture-chat-tui as the index carries a run that named the Linux box's home (pickfit/index.py _user_guide). */
function withSandboxPaths(user: Partial<UserGuide> | null = {}): unknown {
  const data = structuredClone(fixtureIndex()) as any;
  const guide = data.entries.find((e: any) => e.slug === 'fixture-chat-tui').install.linux;
  guide.steps = [{ command: RAN, purpose: 'Build and install with cargo' }];
  guide.check = { command: CHECK, expected_signal: '0.2.0' };
  guide.first_task = FIRST;
  if (user === null) delete guide.user;
  else
    guide.user = {
      steps: [{ command: 'cargo install --root "$HOME"/.local fixture-chat-tui', purpose: 'Build and install with cargo' }],
      first_task_setup: [],
      first_task: 'cd "$HOME"/work && fixture-chat-tui --endpoint http://127.0.0.1:8080/v1',
      check: { command: '"$HOME"/.local/bin/fixture-chat-tui --version', expected_signal: '0.2.0' },
      changed: true,
      not_portable: [],
      needs_workdir: true,
      sandbox_home: '/home/sbx',
      ...user,
    };
  return data;
}

const SANDBOX = /\/home\/sbx/;
const FORM: FormValues = { need: '', os: 'linux', arch: '', free_only: false, offline: false, private: false };

test("get_install_guide gives a user's commands and keeps the run's own under verified_in_pickfit", () => {
  const out = installGuide(loadCatalog(withSandboxPaths()), { slug: 'fixture-chat-tui', os: 'linux' });
  assert.deepEqual(out.steps.map((s) => s.command), ['cargo install --root "$HOME"/.local fixture-chat-tui']);
  assert.deepEqual(out.verify, { command: '"$HOME"/.local/bin/fixture-chat-tui --version', expected_contains: '0.2.0' });
  assert.equal(out.first_task, 'cd "$HOME"/work && fixture-chat-tui --endpoint http://127.0.0.1:8080/v1');
  for (const text of [...out.steps.map((s) => s.command), out.verify!.command, out.first_task!]) assert.doesNotMatch(text, SANDBOX);
  const ran = out.verified_in_pickfit!;
  assert.equal(ran.sandbox_home, '/home/sbx');
  assert.deepEqual(ran.steps, [{ order: 1, command: RAN }]);
  assert.deepEqual(ran.verify, { command: CHECK, expected_contains: '0.2.0' });
  assert.equal(ran.first_task, FIRST);
  assert.match(out.how_we_know, /sandbox home \(\/home\/sbx\) written as \$HOME/);
  assert.ok(out.warnings.some((w) => /folder named work/.test(w) && w.includes('mkdir -p "$HOME/work"')));
});

test('a command the rule could not adapt is said to name the sandbox home; an older index gives the run\'s own', () => {
  const kept = installGuide(loadCatalog(withSandboxPaths({ not_portable: ['step 1'], needs_workdir: false })), {
    slug: 'fixture-chat-tui',
    os: 'linux',
  });
  assert.ok(kept.warnings.some((w) => w.startsWith('step 1 still names pickfit\'s sandbox home (/home/sbx) inside single quotes')));
  assert.deepEqual(kept.verified_in_pickfit!.not_portable, ['step 1']);
  const old = installGuide(loadCatalog(withSandboxPaths(null)), { slug: 'fixture-chat-tui', os: 'linux' });
  assert.deepEqual(old.steps.map((s) => s.command), [RAN]);
  assert.equal(old.verified_in_pickfit, null);
  const plain = installGuide(loadCatalog(fixtureIndex()), { slug: 'fixture-chat-tui', os: 'linux' });
  assert.equal(plain.verified_in_pickfit, null); // built by the pipeline: nothing named the sandbox, nothing to show
  assert.match(plain.how_we_know, /These are the recorded steps of that run; no model wrote or changed them\./);
});

test("the published output schema allows every key of verified_in_pickfit (a client checks the JSON Schema)", () => {
  const out = installGuide(loadCatalog(withSandboxPaths()), { slug: 'fixture-chat-tui', os: 'linux' });
  const schema = z.toJSONSchema(installOutput, { io: 'output' }) as any;
  const field = schema.properties.verified_in_pickfit.anyOf.find((s: any) => s.type === 'object');
  assert.equal(field.additionalProperties, false);
  assert.deepEqual(Object.keys(out.verified_in_pickfit!).filter((k) => !(k in field.properties)), []);
  assert.ok(installOutput.safeParse(out).success);
});

test('the tool page shows a user\'s commands first and the run\'s own only in the folded record', () => {
  const catalog = loadCatalog(withSandboxPaths());
  const html = renderTool(catalog, catalog.bySlug.get('fixture-chat-tui')!, 'n0nce');
  const fold = html.indexOf('<details class="as-run">');
  assert.ok(fold > 0, 'the verified commands are on the page');
  // Above the fold the sandbox home is named once, in the note that says how the commands were adapted; no command has it.
  const note = /<p class="quiet small">pickfit ran these steps in its sandbox, whose home folder is <code translate="no">\/home\/sbx<\/code>\.[^<]*<code[^>]*>\$HOME<\/code>[^<]*<\/p>/;
  assert.match(html.slice(0, fold), note);
  assert.doesNotMatch(html.slice(0, fold).replace(note, ''), SANDBOX, 'the sandbox home is in no command above the fold');
  assert.match(html, /cargo install --root &quot;\$HOME&quot;\/.local fixture-chat-tui/);
  assert.match(html, /mkdir -p &quot;\$HOME\/work&quot; &amp;&amp; cd &quot;\$HOME\/work&quot;/);
  const section = installSection(installGuide(catalog, { slug: 'fixture-chat-tui', os: 'linux' }), FORM, true);
  assert.match(section, /Verified in pickfit: the commands exactly as its sandbox ran them/);
});
