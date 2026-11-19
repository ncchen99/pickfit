/**
 * The vulnerability check in MCP answers (find_software, find_alternatives,
 * get_install_guide): known vulnerabilities (OSV.dev) in what the tool brings.
 * A sec.v2 check carries a level (pickfit/security.py): blocked (do not
 * recommend), exposed (warn first), conditional (say in one line when it
 * applies), partial or unchecked (never call it safe), and present_unreachable,
 * not_shipped or clean (nothing to warn about). A sec.v1 check has no level;
 * its status says vulnerable, clean or unchecked as before. Built field by
 * field from the index, so nothing else it carries (the advisories' own
 * summaries) leaks.
 */
import { securityOf, type Entry, type FindingLevel, type SecurityCheck, type SecurityLevel, type SecurityReason } from './catalog.ts';

/** How many findings an answer lists; count still says how many there are. */
export const SECURITY_FINDINGS_MAX = 5;

export interface SecurityOut {
  status: SecurityCheck['status'];
  /** sec.v2's level; null for a check from before it (read status then). */
  level: SecurityLevel | null;
  /** unchecked only: why pickfit could not check it (or check all of it). */
  reason: SecurityReason | null;
  checked_at: string | null;
  /** vulnerable: how many findings in all, one per advisory on each package version; 0 otherwise. */
  count: number;
  /** vulnerable: distinct known high or critical vulnerabilities among them; 0 otherwise. */
  advisories: number;
  findings: {
    package: string;
    version: string;
    advisory: string;
    severity: NonNullable<SecurityCheck['findings']>[number]['severity'];
    fixed_in: string | null;
    malicious: boolean;
    level: FindingLevel | null;
    preconditions: string[];
  }[];
}

/** Distinct vulnerabilities of a vulnerable check, at least 1 and at most its findings; an older check without the
 * field reads as its findings. */
export function advisoriesOf(s: SecurityCheck, count: number): number {
  return Math.max(1, Math.min(s.advisories ?? count, count));
}

export function securityOut(entry: Entry): SecurityOut {
  const s = securityOf(entry);
  const findings = s.status === 'vulnerable' ? (s.findings ?? []) : [];
  const count = s.status === 'vulnerable' ? Math.max(s.count ?? 0, findings.length, 1) : 0;
  return {
    status: s.status,
    level: s.level ?? null,
    reason: s.status === 'unchecked' ? (s.reason ?? 'not_run') : null,
    checked_at: s.checked_at ?? null,
    count,
    advisories: s.status === 'vulnerable' ? advisoriesOf(s, count) : 0,
    findings: findings.slice(0, SECURITY_FINDINGS_MAX).map((f) => ({
      package: f.package,
      version: f.version,
      advisory: f.advisory,
      severity: f.severity,
      fixed_in: f.fixed_in,
      malicious: f.malicious === true,
      level: f.level ?? null,
      preconditions: (f.preconditions ?? []).slice(0, 4),
    })),
  };
}

/** A finding's preconditions (pickfit/security.py's codes) as the end of "only when ..."; '' when it names none. */
export function conditionWords(codes: string[]): string {
  const words = codes
    .map((c) => {
      if (c.startsWith('option:')) return `${c.slice(7)} is turned on`;
      if (c.startsWith('symbol:')) return `its code calls ${c.slice(7)}`;
      if (c.startsWith('entry:')) return `it uses ${c.slice(6)}`;
      return (
        {
          local_access: 'someone already has access to the machine',
          adjacent_network: 'the attacker is on the same network',
          physical_access: 'someone has the device in hand',
          user_interaction: 'the user opens crafted input',
          high_privileges: 'the attacker has high privileges',
          high_complexity: 'specific conditions line up',
          denial_of_service: 'someone feeds it crafted input (it can crash or hang, nothing leaks)',
          server_side: 'it runs as a server',
        } as Record<string, string>
      )[c];
    })
    .filter(Boolean);
  return [...new Set(words)].slice(0, 3).join(', or ');
}

/** get_install_guide's warnings: one plain line naming the known vulnerabilities (and one per malicious package), so
 * the agent tells the user before installing; for a hosted web app, before they use it (the packages the site is built
 * from). By level for a sec.v2 check: blocked says not to recommend it, conditional says when it applies; the levels
 * that do not warn add nothing. */
export function securityWarnings(out: SecurityOut, web = false): string[] {
  if (out.status !== 'vulnerable') return [];
  const lines = out.findings
    .filter((f) => f.malicious)
    .map((f) => `Malicious package: ${f.package} ${f.version} (${f.advisory}). Tell the user; ${web ? 'do not use the site' : 'do not install it'}.`);
  if (out.level === 'blocked') {
    const exploited = out.findings.filter((f) => !f.malicious && f.level === 'blocked');
    for (const f of exploited) {
      lines.push(`Known exploited vulnerability (CISA KEV): ${f.package} ${f.version} ${f.advisory}${f.fixed_in ? `, fixed in ${f.fixed_in}` : ''}. Do not recommend it; tell the user.`);
    }
    if (lines.length) return lines;
  }
  const known = out.findings.filter((f) => !f.malicious);
  const more = out.count - out.findings.length;
  if (out.level === 'conditional') {
    const list = known.map((f) => {
      const when = conditionWords(f.preconditions);
      return `${f.package} ${f.version} ${f.advisory} (${f.severity}${when ? `; only when ${when}` : ''}), ${f.fixed_in ? `fixed in ${f.fixed_in}` : 'no fix yet'}`;
    });
    const items = [...list, ...(more > 0 ? [`${more} more ${more === 1 ? 'finding' : 'findings'}`] : [])].join('; ');
    lines.push(
      `Known ${out.advisories === 1 ? 'vulnerability' : `vulnerabilities (${out.advisories} high or critical)`} that pickfit could not rule out in normal use${items ? `: ${items}` : ''}. ` +
        `Mention it to the user in one line${web ? '' : ' before installing'}.`,
    );
    return lines;
  }
  const items = known.map((f) => `${f.package} ${f.version} ${f.advisory} (${f.severity}), ${f.fixed_in ? `fixed in ${f.fixed_in}` : 'no fix yet'}`);
  if (items.length || more > 0 || !lines.length) {
    const head = out.advisories === 1 ? 'Known vulnerability' : `Known vulnerabilities (${out.advisories} high or critical)`;
    const reach = out.level === 'exposed' ? ' reached in normal use' : '';
    const list = [...items, ...(more > 0 ? [`${more} more ${more === 1 ? 'finding' : 'findings'}`] : [])].join('; ');
    lines.push(`${head}${reach}${list ? `: ${list}` : web ? ' in the packages the site is built from' : ' in a package it installs'}. ${web ? 'Tell the user before they use it.' : 'Tell the user before installing.'}`);
  }
  return lines;
}
