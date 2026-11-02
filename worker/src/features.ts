/**
 * Which advertised features the run behind an install guide exercised, built by code from the
 * index. A feature is shown as checked only when a smoke test of that run that covers it passed;
 * every other feature is not checked, with the reason. No model writes any of it.
 */
import { webCheck, type Entry, type FeatureCoverage, type InstallGuide } from './catalog.ts';

export const NOT_CHECKED_REASONS = [
  'needs_account',
  'needs_gpu',
  'needs_display',
  'needs_hardware',
  'needs_service',
  'needs_more_resources',
  'needs_container',
  'needs_root',
  'needs_toolchain',
  'other_os',
  'not_attempted',
  'not_shown',
  'test_failed_in_sandbox',
  'test_failed',
  'not_recorded',
  'other',
] as const;
export type NotCheckedReason = (typeof NOT_CHECKED_REASONS)[number];

const REASON_TEXT: Record<NotCheckedReason, string> = {
  needs_account: 'needs an account or API key, which the sandbox does not have',
  needs_gpu: 'needs a GPU, which the sandbox does not have',
  needs_display: 'needs a display, GUI or browser',
  needs_hardware: 'needs hardware the sandbox lacks (a microphone, camera or device)',
  needs_service: 'needs an outside service or server pickfit does not run',
  needs_more_resources: 'too heavy for the sandbox (memory, disk, time, model size or more than one machine)',
  needs_container: 'needs Docker or another container engine, which the sandbox does not run',
  needs_root: 'needs root or a system service, which the sandbox does not allow',
  needs_toolchain: 'needs a source build with a compiler toolchain the sandbox does not install',
  other_os: 'runs only on another OS than the sandbox',
  not_attempted: 'the run did not get to it',
  not_shown: "a check ran and passed, but its output did not show this feature doing its job (pickfit's feature judge)",
  test_failed_in_sandbox: "its test failed, but the sandbox's limits explain the failure",
  test_failed:
    "its test failed with the tool's own error, after a working install; a user following the README may hit it too (not confirmed on a real machine)",
  not_recorded: 'pickfit verified this tool before it checked features one by one',
  other: 'not checked',
};

export interface FeaturesOut {
  /** false: the run behind these steps did not record features (verified earlier, or none listed). */
  recorded: boolean;
  checked: { feature: string; check: string }[];
  not_checked: { feature: string; reason: NotCheckedReason; detail: string }[];
}

function notChecked(f: FeatureCoverage): { reason: NotCheckedReason; detail: string } {
  let reason: NotCheckedReason;
  if (f.status === 'test_failed') {
    reason = f.failure === 'tool' ? 'test_failed' : 'test_failed_in_sandbox';
  } else {
    reason = (NOT_CHECKED_REASONS as readonly string[]).includes(f.reason ?? '') ? (f.reason as NotCheckedReason) : 'other';
  }
  let detail = REASON_TEXT[reason];
  if (f.status === 'test_failed' && f.failure !== 'tool' && f.reason && f.reason !== 'other' && f.reason in REASON_TEXT) {
    detail += ` (${REASON_TEXT[f.reason as NotCheckedReason]})`;
  }
  return { reason, detail: f.note ? `${detail}: ${f.note}` : detail };
}

/** The features view of one guide's run (a web app's browser run: it has no guides); the entry's own list when that run recorded none. */
export function featuresOut(entry: Entry, guide: InstallGuide | null): FeaturesOut {
  const web = guide ? null : webCheck(entry);
  const ran = guide !== null || web !== null;
  const coverage = guide?.features ?? web?.features ?? [];
  if (coverage.length === 0) {
    return {
      recorded: false,
      checked: [],
      not_checked: (entry.features ?? []).map((feature) => ({
        feature,
        reason: ran ? ('not_recorded' as const) : ('other' as const),
        detail: ran ? REASON_TEXT.not_recorded : 'pickfit has not run this tool',
      })),
    };
  }
  const out: FeaturesOut = { recorded: true, checked: [], not_checked: [] };
  for (const f of coverage) {
    const passed = f.checks.find((c) => c.passed);
    if (passed) out.checked.push({ feature: f.feature, check: passed.command });
    else out.not_checked.push({ feature: f.feature, ...notChecked(f) });
  }
  return out;
}

/** "It exercised 2 of the 3 features its README advertises; ..." for how_we_know, or null. */
export function featureSentence(features: FeaturesOut): string | null {
  const total = features.checked.length + features.not_checked.length;
  if (!features.recorded || total === 0) return null;
  const rest = features.not_checked.length ? '; see features for the ones it did not check and why' : '';
  return `The run exercised ${features.checked.length} of the ${total} main features its README advertises${rest}.`;
}
