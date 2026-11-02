/** how_we_know text, built by code from the verification record (never by the model). */
import type { GuiEvidence, GuiOperation, InstallGuide } from './catalog.ts';

const LEVEL_TEXT: Record<string, string> = {
  install: 'the install finished and the tool started',
  function: 'a smoke test of its main function passed',
  service: 'its service answered a test request',
  inference: 'it produced model output in a test run',
};

/** An MCP server's checks: its handshake, and a tool call when one ran. */
function mcpText(guide: InstallGuide): string | null {
  const m = guide.mcp;
  if (!m) return null;
  const listed = `an MCP client handshake over ${m.transport} listed its ${m.tool_count} tool${m.tool_count === 1 ? '' : 's'}`;
  const offline = m.offline ? ' with the network off' : '';
  return m.called_tool ? `${listed}${offline}, and a call to ${m.called_tool} returned a result` : `${listed}${offline}`;
}

const SCREEN_TEXT: Record<GuiEvidence['screen'], string> = {
  main_ui: 'its main screen rendered',
  first_run: 'its first-run (setup) screen rendered',
  sign_in_wall: 'it showed a sign-in screen, and nothing past it was checked',
  crash_or_error: 'it showed an error',
  blank_or_loading: 'the window was still blank or loading',
  other: 'it showed something other than its own UI',
};

const CHECK_TEXT: Record<GuiOperation['check'], string> = {
  file: 'a file the app saved, which pickfit read itself',
  clipboard: 'what the app put on the clipboard, which pickfit read itself',
  screen_text: "text the app showed, read off pickfit's own screenshot",
};

/**
 * The goals a GUI app was operated toward and passed, in words, or null when its tier is not action_checked.
 * "a model (Muse Spark Open) then operated it from screenshots, ...: save notes (checked by a file ...)"
 */
export function operatedText(gui: GuiEvidence): string | null {
  const passed = (gui.operations ?? []).filter((o) => o.passed);
  if (gui.tier !== 'action_checked' || passed.length === 0) return null;
  const what = passed.map((o) => `${o.feature ?? 'a task'} (checked by ${CHECK_TEXT[o.check]})`).join('; ');
  return (
    'a model (Muse Spark Open) then operated it from screenshots, pickfit performing every click and keystroke, ' +
    `and the result passed pickfit's own check in a fresh sandbox: ${what}`
  );
}

/** A GUI app's launch: what opened, what the screen judge saw, and whether a feature was operated and checked. */
function guiText(guide: InstallGuide): string | null {
  const g = guide.run.gui;
  if (!g) return null;
  const offline = g.launch_offline ? ', and the launch passed again with the network off' : '';
  const operated = operatedText(g);
  return (
    `the app opened a window of its own on a virtual display (${g.display}) and a separate model, ` +
    `reading a screenshot of that window, judged that ${SCREEN_TEXT[g.screen]}${offline}. ` +
    (operated ? operated[0].toUpperCase() + operated.slice(1) : 'That shows it installs and starts; pickfit did not use any of its features')
  );
}

/** What the sandbox had beyond the usual (a GPU, a simulated microphone), as a phrase; '' when nothing. */
export function boxExtras(run: InstallGuide['run']): string {
  const parts = [
    run.gpu ? `a GPU (${run.gpu})` : '',
    run.microphone ? 'a simulated microphone that played words pickfit spoke for each check' : '',
  ].filter(Boolean);
  return parts.join(' and ');
}

/**
 * A run's day as YYYY-MM-DD in UTC. checked_at carries the runner's own offset (a run at 01:45 +08:00 on
 * 31 Oct is 30 Oct in UTC), and the web page shows UTC days, so every text that dates a run uses this.
 */
export function runDay(checkedAt: string): string {
  const t = new Date(checkedAt);
  return Number.isNaN(t.getTime()) ? checkedAt.slice(0, 10) : t.toISOString().slice(0, 10);
}

/** "pickfit installed it in a fresh linux/x86_64 sandbox (...) on 2026-10-28; a smoke test ... passed." */
export function ranSentence(guide: InstallGuide): string {
  const r = guide.run;
  const runner = r.runner ? ` (${r.runner})` : '';
  const where =
    r.method === 'sandbox'
      ? `installed it in a fresh ${r.os}/${r.arch} sandbox${runner}${boxExtras(r) ? ` with ${boxExtras(r)}` : ''} and replayed the steps from scratch`
      : `installed it by hand on ${r.os}/${r.arch}${runner}`;
  return `pickfit ${where} on ${runDay(r.checked_at)}; ${mcpText(guide) ?? guiText(guide) ?? LEVEL_TEXT[r.level] ?? r.level}.`;
}
