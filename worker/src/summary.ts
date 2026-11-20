/**
 * The text block of an MCP answer (X2). A tool result carries the full answer once, in structuredContent; the text
 * block used to repeat it as JSON, so a client that hands both to its model paid for it twice. It is now a short
 * plain-text answer with what an agent needs to reply and act: the picks with their fit, reasons, trade-offs and
 * warnings, the rec_id, and for an install guide every step and check. Evidence URLs, scores, per-feature checks and
 * advisory lists stay in structuredContent only. A client that shows the model only the text can still answer and
 * install from it.
 */
import type { AlternativesOutput, FindOutput, PickOut } from './find.ts';
import type { InstallOutput } from './install.ts';

const STRUCTURED = 'Evidence links, scores, feature checks and advisory details are in structuredContent.';

function facts(p: PickOut): string {
  const parts: string[] = [p.pricing];
  if (p.open_source) parts.push('open source');
  if (p.processing !== 'unknown') parts.push(p.processing);
  if (p.web_app) parts.push(`web app: ${p.web_app.url}`);
  else if (p.verification.os) {
    const where = [p.verification.os, p.verification.arch].filter(Boolean).join(' ');
    const when = p.verification.checked_at ? ` ${p.verification.checked_at.slice(0, 10)}` : '';
    parts.push(`install checked on ${where}${when}${p.verification.replayed ? ', replayed' : ''}`);
  } else parts.push('install not checked');
  return parts.join(' · ');
}

function pickLines(p: PickOut, n: number): string[] {
  const lines = [`${n}. ${p.name} (${p.slug}): ${facts(p)}`, `   Fit: ${p.fit}`];
  if (p.match) lines.push(`   Match: ${p.match.quality}${p.match.missing.length ? `; does not mention ${p.match.missing.join(', ')}` : ''}`);
  if (p.why.length) lines.push(`   Why: ${p.why.map((r) => r.claim).join('; ')}`);
  if (p.tradeoffs.length) lines.push(`   Trade-offs: ${p.tradeoffs.join('; ')}`);
  if (p.vs_well_known) lines.push(`   vs the well-known choice: ${p.vs_well_known}`);
  if (p.security_warning) lines.push(`   Security: ${p.security_warning}`);
  for (const r of p.readme_wrong) lines.push(`   README is wrong: ${r}`);
  return lines;
}

/** find_software and find_alternatives. */
export function findSummary(out: FindOutput | AlternativesOutput, readonly = false): string {
  const lines: string[] = [];
  if (out.clarifying_question) lines.push(`Ask the user first: ${out.clarifying_question}`);
  if ('keep_current' in out && out.keep_current?.recommended) lines.push(`Keep the current tool: ${out.keep_current.reason}`);
  if (out.matched_by === 'rules') {
    lines.push(`Ranked by rules, without the model${out.match_quality ? `; best match: ${out.match_quality}` : ''}. Present partial or weak picks as such.`);
  }
  out.picks.forEach((p, i) => lines.push(...pickLines(p, i + 1)));
  if (out.picks.length === 0 && out.coverage_note) lines.push(out.coverage_note);
  if (out.best_free && !out.picks.some((p, i) => i === 0 && p.slug === out.best_free!.slug)) {
    lines.push(`Best free: ${out.best_free.slug}: ${out.best_free.reason}`);
  }
  if (out.no_install_option) lines.push(`Without installing anything: ${out.no_install_option}`);
  if (out.well_known_option) lines.push(`Well-known option (not verified by pickfit): ${out.well_known_option.name}: ${out.well_known_option.why}`);
  lines.push(`rec_id: ${out.rec_id} (pass it to get_install_guide${readonly ? '' : ' and report_outcome'}).`, STRUCTURED);
  return lines.join('\n');
}

/** get_install_guide. */
export function installSummary(out: InstallOutput, readonly = false): string {
  const v = out.verification;
  const lines: string[] = [];
  const where = [v.os, v.arch].filter(Boolean).join(' ');
  lines.push(
    v.status === 'verified'
      ? `${out.name} (${out.slug}): steps checked on ${where}${v.checked_at ? ` ${v.checked_at.slice(0, 10)}` : ''}${v.replayed ? ', replayed in a fresh sandbox' : ''}.`
      : `${out.name} (${out.slug}): pickfit has not run these steps.`,
  );
  if (out.applies_to_user_system.match !== 'exact' && out.applies_to_user_system.note) lines.push(`Your system: ${out.applies_to_user_system.note}`);
  for (const w of out.warnings) lines.push(`Warning: ${w}`);
  if (out.web_app) lines.push(`Open ${out.web_app.url} in a browser; there is nothing to install.`);
  if (out.steps.length) {
    lines.push('Steps (show each command to the user before running it):');
    for (const s of out.steps) lines.push(`${s.order}. ${s.command}${s.needs_sudo ? '   [needs sudo: ask first]' : ''}${s.purpose ? `   # ${s.purpose}` : ''}`);
  }
  for (const m of out.manual_steps) lines.push(`The user does: ${m.title}`);
  if (out.verify) lines.push(`Verify: ${out.verify.command}   (expect "${out.verify.expected_contains}")`);
  for (const s of out.first_task_setup) lines.push(`Before the first task${s.run_in_background ? ' (keep running)' : ''}: ${s.command}`);
  if (out.first_task) lines.push(`First task: ${out.first_task}`);
  for (const k of out.known_issues.filter((k) => k.kind === 'readme_wrong' || !k.kind)) {
    lines.push(`README is wrong: it says ${k.readme_said}; actually needed: ${k.actually_needed}`);
  }
  if (out.mcp_client_config) lines.push(`Add to Claude Code: ${out.mcp_client_config.claude_code}`);
  lines.push(readonly ? `rec_id: ${out.rec_id}` : `rec_id: ${out.rec_id} (pass it to report_outcome after the user tries it).`, STRUCTURED);
  return lines.join('\n');
}
