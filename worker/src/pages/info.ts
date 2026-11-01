/** The reading pages: how pickfit works (and what its labels mean), connecting an agent, and not found. */
import type { Catalog } from '../catalog.ts';
import { catalogStats, rulesLabel } from '../page.ts';
import { LEVEL_LABEL } from '../ui/facts.ts';
import { esc } from '../ui/html.ts';
import { icon } from '../ui/icons.ts';
import { badge, command, fitz, tape } from '../ui/kit.ts';
import { renderShell } from '../ui/shell.ts';

const head = (title: string, lede: string, who: Parameters<typeof fitz>[0]) =>
  `<section class="head mat after-top"><div class="wrap head-row"><div><h1>${esc(title)}</h1><p class="lede">${esc(lede)}</p></div>` +
  `${fitz(who, 150, { eager: true })}</div><div class="ruler" aria-hidden="true"></div></section>`;

export function renderHow(catalog: Catalog, nonce: string): string {
  const s = catalogStats(catalog);
  const levels: [string, string][] = [
    ['install', 'The command runs and prints its version or help. A GUI app opened its own window.'],
    ['function', 'The run gave it real input and checked the output: a file converted, a query answered.'],
    ['service', 'A local server came up and answered. For an MCP server, a client called one of its tools.'],
    ['inference', 'A local AI tool loaded a model and generated text, speech or an image.'],
  ];
  const main =
    head('How Fitz checks a tool', 'Every suggestion rests on a run pickfit did itself, and every reason points at the field it came from. Here is the whole method, and what each label on a ticket means.', 'testing') +
    `<div class="wrap"><article class="prose">` +
    `<h2>Four steps, one tool at a time</h2>` +
    `<ol><li><b>Find.</b> Agents scan new GitHub projects and Show HN posts for software that may be good and little known. So far pickfit has read ${s.listed} READMEs.</li>` +
    `<li><b>Read.</b> Meta’s Muse Spark reads each README and writes a profile: what it does, where it runs, what it costs, whether it works offline. Every field quotes its source; a field with no source is left empty, not guessed.</li>` +
    `<li><b>Try it on.</b> A verification agent installs the tool in a fresh sandbox (Linux in gVisor; some by hand on a real Mac), fixes what the README got wrong, checks the main features one by one, then replays the working steps in a brand-new sandbox. ${s.replayed} tools passed a replay.</li>` +
    `<li><b>Match.</b> Your sentence and every verified profile that meets your conditions go to Muse Spark in one call. Each reason it gives must name a profile field; code checks the value and drops any reason that doesn’t hold. If the model is unavailable, pickfit ranks by rules and says so.</li></ol>` +
    `<h2 id="levels">What “verified” proves</h2><p>A ticket says how far the run got. Higher is stronger evidence:</p>` +
    `<ul class="levels">${levels.map(([k, t]) => `<li><b>${esc(LEVEL_LABEL[k])}</b>${esc(t)}</li>`).join('')}</ul>` +
    `<p>A run says where it happened (OS and CPU) and when. “Verified on your OS” appears only when the steps ran on the system you chose; otherwise the ticket says where they did run.</p>` +
    `<h2 id="labels">What the labels mean</h2>` +
    `<h3>Stitching</h3><p>The rufous running stitch on a ticket separates the claim from the run record. pickfit draws it only under evidence from its own run. A tool pickfit has not run, such as a well-known option Fitz mentions from general knowledge, never gets stitches, a badge, steps or a link.</p>` +
    `<h3 id="scores">Quality and popularity</h3><div class="levels">${tape('Quality', 84)}${tape('Popularity', 22, { tone: 'quiet' })}</div>` +
    `<p>Two scores out of 100, computed apart (formula b3.v5). <b>Quality</b> is a weighted mean: the sandbox run (how far it got, how many install actions, how many README fixes it needed) 40%, how complete the install docs are 25% (Muse Spark grades them, quoting the README), maintenance 10%, issue responsiveness 10%, engineering hygiene 5%; reports from real use join as they accumulate. <b>Popularity</b> compares stars, forks, downloads and Hacker News points with other tools of the same kind. The example tapes above are illustrative.</p>` +
    `<p>${badge('gem', 'Hidden gem', { icon: 'gem' })} marks a verified tool with quality 80 or more and popularity 45 or less: ${s.gems} tools today. Fitz ranks by fit to your need, not by either score.</p>` +
    `<h3>Features checked</h3><p>The run tries each main feature the README advertises. Some need an account, a GPU, a display or hardware the sandbox doesn’t have; those stay unchecked, and the ticket gives the reason. A feature whose test failed with the tool’s own error is marked as failed.</p>` +
    `<h3>Match labels</h3><p>When the model is paused, pickfit ranks by rules and labels each pick ${badge('pass', 'Good match')} ${badge('caution', 'Partial match')} or ${badge('caution', 'Weak match')} by which of your words its profile mentions. With the model, Muse Spark writes the fit sentence and code checks each of its reasons.</p>` +
    `<h2 id="rules">Fitz’s rules</h2><div class="care"><div><p>pickfit is neutral on purpose. It belongs to no agent maker and no software vendor, takes no money for placement, and doesn’t make any of the software it suggests. That is what lets it say a little-known tool fits better, or that what you already have is enough.</p>` +
    `<p>Privacy: no account, no IP address stored. Your sentence goes to Meta’s Muse Spark with storage turned off; pickfit keeps only the conditions it parsed, such as the task and the OS. Compare picks stay in your own browser.</p></div>${rulesLabel()}</div>` +
    `<div class="tip">${fitz('peek', 52)}<h3>Found a tool that should be here?</h3><p>Authors and users can submit a GitHub project through the MCP <code>submit_software</code> tool. It gets the same review: read, installed, replayed, scored. Submitting never earns a better rank.</p><p><a class="more" href="/agents">Connect an agent${icon('arrow-right')}</a></p></div>` +
    `</article></div>`;
  return renderShell({ nonce, title: 'How pickfit works · pickfit', description: 'How pickfit finds, reads, installs, verifies and matches software, and what each label means.', active: 'how', main });
}

export function renderAgents(origin: string, nonce: string): string {
  const mcp = `${origin}/mcp`;
  const tools: [string, string][] = [
    ['find_software', 'Two or three verified tools for a need and conditions (OS, CPU, free only, offline), with reasons, tradeoffs, the best free option and, when it fits, “built-in is enough”.'],
    ['find_alternatives', 'Replacements for a tool you use now, given what you don’t like about it and what you must keep.'],
    ['get_install_guide', 'The steps that worked in pickfit’s run, for your OS, with what you do by hand and how to check the install.'],
    ['report_outcome', 'Did it install, did it work, are you still using it. Failures queue the tool for a fresh run.'],
    ['submit_software', 'Send a GitHub project for review. It goes through the same read, install and replay as everything else.'],
  ];
  const main =
    head('Same answers, in your agent', 'pickfit is an MCP server. Your coding agent gets the same verified data and the same matching as this page, and can install a pick for you with the steps that worked.', 'recommending') +
    `<div class="wrap"><article class="prose">` +
    `<h2>Connect</h2><p>Any MCP client that speaks streamable HTTP can connect to <code translate="no">${esc(mcp)}</code>. For Claude Code:</p>` +
    command(`claude mcp add --transport http pickfit ${mcp}`) +
    `<p>For Claude Desktop, Cursor and other clients, add it to the MCP config:</p>` +
    command(JSON.stringify({ mcpServers: { pickfit: { type: 'http', url: mcp } } }, null, 2)) +
    `<h2>Tools</h2><div class="table-wrap"><table class="dt"><thead><tr><th scope="col">Tool</th><th scope="col">What it does</th></tr></thead><tbody>` +
    tools.map(([n, t]) => `<tr><th scope="row"><code>${esc(n)}</code></th><td>${esc(t)}</td></tr>`).join('') +
    `</tbody></table></div>` +
    `<h2>Try it</h2><p>Ask your agent in plain words, for example:</p>${command('Find me a free tool that works offline on my Mac to turn meeting recordings into subtitles, and install it.')}` +
    `<div class="tip">${fitz('peek', 52)}<h3>No sign-up, no ads</h3><p>The MCP needs no account and returns no referral links. Answers carry a <code>how_we_know</code> line and the run’s <code>evidence_url</code>, so your agent can tell you where each claim came from.</p></div>` +
    `</article></div>`;
  return renderShell({ nonce, title: 'Connect your agent · pickfit', description: 'Use pickfit from Claude Code, Claude Desktop, Cursor or any MCP client.', active: 'agents', main });
}

export function renderNotFound(nonce: string): string {
  const main =
    `<section class="head mat after-top"><div class="wrap nf">${fitz('surprised', 160, { eager: true })}<h1>This page doesn’t fit</h1>` +
    `<p class="lede">The address may be old, or the tool isn’t in pickfit’s catalog.</p>` +
    `<p class="badges"><a class="btn btn-primary" href="/">${icon('search')}Find software</a><a class="btn btn-on-mat" href="/browse">Browse verified tools</a></p></div>` +
    `<div class="ruler" aria-hidden="true"></div></section>`;
  return renderShell({ nonce, title: 'Not found · pickfit', description: 'This page does not exist.', active: null, main });
}
