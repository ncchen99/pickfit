/**
 * Which advertised features the run behind an install guide exercised, built by code from the
 * index. A feature is shown as checked only when a smoke test of that run that covers it passed;
 * every other feature is not checked, with the reason. No model writes any of it.
 *
 * A checked feature also says what its check ran against when that was something outside the tool
 * (fidelity, docs/proposals/privileges.md P1). One checked against a stand-in stays in `checked`,
 * because its test did pass, but it shows only that the tool connects: nothing here, on a page or in
 * an answer may present it as verified to work (standInOnly, shownWorking).
 */
import { FIDELITIES, webCheck, type Entry, type FeatureCoverage, type Fidelity, type InstallGuide } from './catalog.ts';

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
  'operator_limit',
  'check_not_met',
  'app_error',
  'needs_desktop',
  'beyond_budget',
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
  operator_limit: "pickfit's GUI operator did not get through the app to it (out of steps, going in circles, or gave up)",
  check_not_met: "pickfit operated the app, but its own check did not find the result",
  app_error: 'the app showed no window, crashed or showed an error while pickfit operated it',
  needs_desktop: "needs a desktop piece the sandbox's display lacks (a file-chooser portal, a URL handler, Wayland)",
  beyond_budget: 'pickfit checks only the first 4 listed features one by one; this one is past them',
  test_failed_in_sandbox: "its test failed, but the sandbox's limits explain the failure",
  test_failed:
    "its test failed with the tool's own error, after a working install; a user following the README may hit it too (not confirmed on a real machine)",
  not_recorded: 'pickfit verified this tool before it checked features one by one',
  other: 'not checked',
};

export interface CheckedFeature {
  feature: string;
  check: string;
  /** What the check ran against, when that was outside the tool; left out when the run recorded none. */
  fidelity?: Fidelity;
}

export interface FeaturesOut {
  /** false: the run behind these steps did not record features (verified earlier, or none listed). */
  recorded: boolean;
  checked: CheckedFeature[];
  not_checked: { feature: string; reason: NotCheckedReason; detail: string }[];
}

/** Checked only against a stand-in: the tool connected, and nothing shows it works with the real service. */
export const standInOnly = (features: FeaturesOut): CheckedFeature[] => features.checked.filter((f) => f.fidelity === 'stand_in');

/** Checked through a compatible endpoint with a real model behind it, not the service the tool names. */
export const viaCompatible = (features: FeaturesOut): CheckedFeature[] => features.checked.filter((f) => f.fidelity === 'compatible');

/** The checked features a page may tick, or count as working: every one but those a stand-in backs. */
export const shownWorking = (features: FeaturesOut): CheckedFeature[] => features.checked.filter((f) => f.fidelity !== 'stand_in');

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
    // Only a value the index is known to write; the key is left out otherwise, as before fidelity was recorded.
    const fidelity = (FIDELITIES as readonly string[]).includes(f.fidelity ?? '') ? (f.fidelity as Fidelity) : null;
    if (passed) out.checked.push({ feature: f.feature, check: passed.command, ...(fidelity ? { fidelity } : {}) });
    else out.not_checked.push({ feature: f.feature, ...notChecked(f) });
  }
  return out;
}

const named = (list: CheckedFeature[]) => list.map((f) => f.feature).join('; ');

/** "Checked only against a stand-in (...): <features>." for an answer's text, or null when there are none. */
export function standInSentence(features: FeaturesOut): string | null {
  const list = features.recorded ? standInOnly(features) : [];
  if (!list.length) return null;
  return (
    `Checked only against a stand-in, not the real service: ${named(list)}. ` +
    'That shows the tool connects; do not say these were verified to work.'
  );
}

/** "Checked through a compatible endpoint ...: <features>." for an answer's text, or null when there are none. */
export function compatibleSentence(features: FeaturesOut): string | null {
  const list = features.recorded ? viaCompatible(features) : [];
  return list.length ? `Checked through a compatible endpoint with a real model behind it, not the service the tool names: ${named(list)}.` : null;
}

/**
 * "It exercised 2 of the 3 features its README advertises; ..." for how_we_know, or null. The count is of features
 * whose test passed; when a stand-in backed some of them, the next sentence says how many and which.
 */
export function featureSentence(features: FeaturesOut): string | null {
  const total = features.checked.length + features.not_checked.length;
  if (!features.recorded || total === 0) return null;
  const rest = features.not_checked.length ? '; see features for the ones it did not check and why' : '';
  const standIn = standInOnly(features);
  const compatible = viaCompatible(features);
  return (
    `The run exercised ${features.checked.length} of the ${total} main features its README advertises${rest}.` +
    (standIn.length
      ? ` ${standIn.length} of those ${features.checked.length} ran only against a stand-in, not the real service (${named(standIn)}): that shows the tool connects, not that the feature works.`
      : '') +
    (compatible.length ? ` ${compatible.length} ran through a compatible endpoint with a real model behind it (${named(compatible)}).` : '')
  );
}
