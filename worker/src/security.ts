/**
 * The vulnerability check in MCP answers (find_software, find_alternatives,
 * get_install_guide): known high or critical vulnerabilities (OSV.dev) in what
 * a fresh install brings. Built field by field from the index, so nothing
 * else it carries (the advisories' own summaries) leaks.
 */
import { securityOf, type Entry, type SecurityCheck, type SecurityReason } from './catalog.ts';

/** How many findings an answer lists; count still says how many there are. */
export const SECURITY_FINDINGS_MAX = 5;

export interface SecurityOut {
  status: SecurityCheck['status'];
  /** unchecked only: why pickfit could not check it. */
  reason: SecurityReason | null;
  checked_at: string | null;
  /** vulnerable: how many findings in all, one per advisory on each package version; 0 otherwise. */
  count: number;
  /** vulnerable: distinct known high or critical vulnerabilities among them; 0 otherwise. */
  advisories: number;
  findings: { package: string; version: string; advisory: string; severity: 'CRITICAL' | 'HIGH'; fixed_in: string | null; malicious: boolean }[];
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
    })),
  };
}

/** get_install_guide's warnings: one plain line naming the known vulnerabilities (and one per malicious package), so
 * the agent tells the user before installing; for a hosted web app, before they use it (the packages the site is built from). */
export function securityWarnings(out: SecurityOut, web = false): string[] {
  if (out.status !== 'vulnerable') return [];
  const lines = out.findings
    .filter((f) => f.malicious)
    .map((f) => `Malicious package: ${f.package} ${f.version} (${f.advisory}). Tell the user; ${web ? 'do not use the site' : 'do not install it'}.`);
  const known = out.findings
    .filter((f) => !f.malicious)
    .map((f) => `${f.package} ${f.version} ${f.advisory} (${f.severity}), ${f.fixed_in ? `fixed in ${f.fixed_in}` : 'no fix yet'}`);
  const more = out.count - out.findings.length;
  if (known.length || more > 0 || !lines.length) {
    const head = out.advisories === 1 ? 'Known vulnerability' : `Known vulnerabilities (${out.advisories} high or critical)`;
    const list = [...known, ...(more > 0 ? [`${more} more ${more === 1 ? 'finding' : 'findings'}`] : [])].join('; ');
    lines.push(`${head}${list ? `: ${list}` : web ? ' in the packages the site is built from' : ' in a package it installs'}. ${web ? 'Tell the user before they use it.' : 'Tell the user before installing.'}`);
  }
  return lines;
}
