import assert from 'node:assert/strict';
import { test } from 'node:test';
import { loadCatalog } from '../src/catalog.ts';
import { normalizeRepoUrl, SubmitError, submitSoftware, type SubmitDeps } from '../src/submit.ts';
import { fixtureIndex, harness, type Harness } from './helpers.ts';

function deps(h: Harness, extra: Partial<SubmitDeps> = {}): SubmitDeps {
  return { catalog: h.deps.catalog, db: h.deps.db, now: h.deps.now, hourlyCap: 20, ...extra };
}

test('GitHub repository URLs are normalized; anything else is refused', () => {
  for (const url of [
    'https://github.com/Owner/Repo',
    'http://www.github.com/owner/repo.git',
    'github.com/owner/repo/',
    'https://github.com/owner/repo/tree/main/src?tab=readme#install',
  ]) {
    assert.equal(normalizeRepoUrl(url), 'https://github.com/owner/repo', url);
  }
  for (const url of [
    'https://gitlab.com/owner/repo',
    'https://github.com/owner',
    'https://github.com/topics/cli',
    'https://github.com/orgs/owner/repositories',
    'https://evilgithub.com/owner/repo',
    'https://github.com.evil.example/owner/repo',
    'https://www.threads.net/@someone/post/abc',
    'https://github.com/owner/..',
  ]) {
    assert.equal(normalizeRepoUrl(url), null, url);
  }
});

test('a new repository is queued; submitting it again reads the status', async () => {
  const h = harness(null);
  const first = await submitSoftware(
    { url: 'https://github.com/Someone/new-cli', submitter_role: 'author', note: 'A CLI. Contact me: me@example.com' },
    deps(h),
  );
  assert.equal(first.status, 'queued');
  assert.equal(first.already_submitted, false);
  assert.equal(first.url, 'https://github.com/someone/new-cli');
  assert.match(first.submission_id ?? '', /^sub_[0-9a-f]{32}$/);
  assert.equal(first.check_again_after_s, 120);

  const row = h.sqlite.prepare('SELECT * FROM submissions').get() as any;
  assert.equal(row.submitter_role, 'author');
  assert.equal(row.note, 'A CLI. Contact me: <email>');

  // The pipeline moves it on; the same URL in another spelling only reads that.
  h.sqlite.prepare("UPDATE submissions SET status = 'rejected', reason = 'A library, not a tool.'").run();
  const again = await submitSoftware({ url: 'github.com/someone/NEW-CLI.git' }, deps(h));
  assert.equal(again.already_submitted, true);
  assert.equal(again.submission_id, first.submission_id);
  assert.equal(again.status, 'rejected');
  assert.equal(again.reason, 'A library, not a tool.');
  assert.equal(again.check_again_after_s, null);
  assert.equal(h.sqlite.prepare('SELECT count(*) AS n FROM submissions').get()!.n, 1);
  // The note is never echoed back.
  assert.ok(!JSON.stringify(again).includes('Contact me'));
});

test('a repository already in the catalog is reported as listed without a new row', async () => {
  const h = harness(null);
  const index = fixtureIndex() as any;
  index.entries[0].repo_url = 'https://github.com/fixture/fixture-chat-tui';
  const out = await submitSoftware({ url: 'https://github.com/fixture/fixture-chat-tui' }, deps(h, { catalog: loadCatalog(index) }));
  assert.equal(out.status, 'listed');
  assert.equal(out.slug, 'fixture-chat-tui');
  assert.equal(out.submission_id, null);
  assert.equal(h.sqlite.prepare('SELECT count(*) AS n FROM submissions').get()!.n, 0);
  await h.settle();
  const event = h.sqlite.prepare("SELECT slug, results FROM events WHERE type = 'submit'").get() as any;
  assert.deepEqual([event.slug, JSON.parse(event.results)], ['fixture-chat-tui', ['listed']]);
});

test('new submissions stop at the hourly cap; status checks still work', async () => {
  const h = harness(null);
  await submitSoftware({ url: 'https://github.com/a/one' }, deps(h, { hourlyCap: 2 }));
  await submitSoftware({ url: 'https://github.com/a/two' }, deps(h, { hourlyCap: 2 }));
  await assert.rejects(submitSoftware({ url: 'https://github.com/a/three' }, deps(h, { hourlyCap: 2 })), SubmitError);
  assert.equal((await submitSoftware({ url: 'https://github.com/a/one' }, deps(h, { hourlyCap: 2 }))).already_submitted, true);
  // An hour later there is room again.
  const later = deps(h, { hourlyCap: 2, now: () => new Date('2026-10-30T13:00:01Z') });
  assert.equal((await submitSoftware({ url: 'https://github.com/a/three' }, later)).status, 'queued');
});

test('a non-GitHub URL is a tool error', async () => {
  const h = harness(null);
  await assert.rejects(submitSoftware({ url: 'https://example.com/tool' }, deps(h)), /only GitHub repository URLs/);
});
