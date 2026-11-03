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
  /** vulnerable: how many known high or critical vulnerabilities in all; 0 otherwise. */
  count: number;
  findings: { package: string; version: string; advisory: string; severity: 'CRITICAL' | 'HIGH'; fixed_in: string | null; malicious: boolean }[];
}

export function securityOut(entry: Entry): SecurityOut {
  const s = securityOf(entry);
  const findings = s.status === 'vulnerable' ? (s.findings ?? []) : [];
  return {
    status: s.status,
    reason: s.status === 'unchecked' ? (s.reason ?? 'not_run') : null,
    checked_at: s.checked_at ?? null,
    count: s.status === 'vulnerable' ? Math.max(s.count ?? 0, findings.length, 1) : 0,
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
 * the agent tells the user before installing. */
export function securityWarnings(out: SecurityOut): string[] {
  if (out.status !== 'vulnerable') return [];
  const lines = out.findings
    .filter((f) => f.malicious)
    .map((f) => `Malicious package: ${f.package} ${f.version} (${f.advisory}). Tell the user; do not install it.`);
  const known = out.findings
    .filter((f) => !f.malicious)
    .map((f) => `${f.package} ${f.version} ${f.advisory} (${f.severity}), ${f.fixed_in ? `fixed in ${f.fixed_in}` : 'no fix yet'}`);
  const more = out.count - out.findings.length;
  if (known.length || more > 0 || !lines.length) {
    const head = out.count === 1 ? 'Known vulnerability' : `Known vulnerabilities (${out.count} high or critical)`;
    const list = [...known, ...(more > 0 ? [`${more} more`] : [])].join('; ');
    lines.push(`${head}${list ? `: ${list}` : ' in a package it installs'}. Tell the user before installing.`);
  }
  return lines;
}
