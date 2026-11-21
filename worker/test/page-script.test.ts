/**
 * The page script (src/ui/script.ts) is one inline <script>: a single syntax error stops all of it on every
 * page (search suggestions, the search animation, the browse filter). On 2026-11-21 a second `const track` in
 * the chapter player did exactly that on pickfit.app. Compile it here so such an error fails the tests.
 */
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { Script } from 'node:vm';
import { withLang } from '../src/i18n.ts';
import { script } from '../src/ui/script.ts';

for (const lang of ['en', 'zh-TW'] as const) {
  test(`the page script compiles (${lang})`, () => {
    const source = withLang(lang, () => script());
    assert.doesNotThrow(() => new Script(source, { filename: `page-script.${lang}.js` }));
  });
}
