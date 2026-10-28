/**
 * find_software (architecture F.2): hard filters (code) -> every candidate
 * card in one muse-spark-1.3 call that parses the request and chooses ->
 * guard (code). Without the model (off, no key, over budget, failure, or
 * every pick rejected) it ranks by rules and says so: matched_by "rules",
 * degraded true.
 */
import { bestGuide, type Arch, type Catalog, type Entry, type InstallGuide, type OS } from './catalog.ts';
import { toCard, type Card } from './cards.ts';
import { checkBudget, recordSpend } from './budget.ts';
import type { Settings } from './env.ts';
import { logEvent, newId } from './events.ts';
import { hardFilter, MAX_CARDS, type Conditions } from './filter.ts';
import { clip, guardPicks, parseAnswer, type GuardedPick } from './guard.ts';
import { callMeta, estimateCostUsd, MATCH_MODEL, MetaCallError, requestBody } from './meta.ts';
import { instructions, matchInput, matchSchema, type ModelAnswer, type ModelReason } from './prompt.ts';
import { rankByRules, templateReasons } from './rules.ts';

export interface FindInput extends Conditions {
  need: string;
  ui_language?: string;
  limit?: number;
}

export interface Deps {
  catalog: Catalog;
  db: D1Database;
  settings: Settings;
  now: () => Date;
  waitUntil: (promise: Promise<unknown>) => void;
  fetch?: typeof fetch;
  client?: string | null;
}

export interface PickOut {
  slug: string;
  name: string;
  summary: string;
  fit: string;
  why: ModelReason[];
  tradeoffs: string[];
  vs_well_known: string | null;
  platforms: OS[];
  pricing: 'free' | 'freemium' | 'paid' | 'unknown';
  processing: 'local' | 'cloud' | 'hybrid' | 'unknown';
  open_source: boolean | null;
  license: string | null;
  verification: {
    level: string;
    os: OS | null;
    arch: Arch | null;
    method: 'sandbox' | 'human' | null;
    replayed: boolean;
    checked_at: string | null;
    verified_on_user_os: boolean | null;
  };
  how_we_know: string;
  evidence_url: string | null;
  scores: { quality: number | null; popularity: number | null; treasure: boolean };
  repo: string;
  homepage: string | null;
}

export interface FindOutput {
  rec_id: string;
  matched_by: string;
  degraded: boolean;
  degraded_reason: string | null;
  considered: number;
  picks: PickOut[];
  best_free: { slug: string; reason: string } | null;
  no_install_option: string | null;
  clarifying_question: string | null;
  coverage_note: string | null;
}

const LEVEL_TEXT: Record<string, string> = {
  install: 'the install finished and the tool started',
  function: 'a smoke test of its main function passed',
  service: 'its service answered a test request',
  inference: 'it produced model output in a test run',
};

function howWeKnow(entry: Entry, guide: InstallGuide | null, matchedBy: string, considered: number): string {
  const parts: string[] = [];
  if (guide) {
    const r = guide.run;
    const runner = r.runner ? ` (${r.runner})` : '';
    const where =
      r.method === 'sandbox'
        ? `installed it in a fresh ${r.os}/${r.arch} sandbox${runner} and replayed the steps from scratch`
        : `installed it by hand on ${r.os}/${r.arch}${runner}`;
    parts.push(`pickfit ${where} on ${r.checked_at.slice(0, 10)}; ${LEVEL_TEXT[r.level] ?? r.level}.`);
  }
  if (entry.scores) {
    const q = entry.scores.quality === null ? 'n/a' : Math.round(entry.scores.quality);
    const p = entry.scores.popularity === null ? 'n/a' : Math.round(entry.scores.popularity);
    parts.push(`Quality ${q}/100 and popularity ${p}/100 are scored separately (formula ${entry.scores.formula_version}).`);
  }
  parts.push(
    matchedBy === 'rules'
      ? `Ranked by rules (request keywords, verification on your OS, treasure score) among ${considered} tools that passed the hard filters; no model was used.`
      : `Chosen by ${matchedBy} among ${considered} tools that passed pickfit's hard filters; code checked each reason against the profile.`,
  );
  return parts.join(' ');
}

function pickOut(entry: Entry, chosen: GuardedPick, os: OS | undefined, matchedBy: string, considered: number): PickOut {
  const guide = bestGuide(entry, os);
  const onUserOs = os ? entry.install[os] !== undefined : null;
  const tradeoffs = [...chosen.tradeoffs];
  if (os && !onUserOs && guide) {
    const said = tradeoffs.some((t) => /verif|tested|checked/i.test(t) && t.toLowerCase().includes(guide.run.os));
    if (!said) {
      tradeoffs.unshift(`Verified on ${guide.run.os} only; pickfit has not run its ${os} install steps yet.`);
    }
  }
  return {
    slug: entry.slug,
    name: entry.name,
    summary: entry.summary,
    fit: chosen.fit,
    why: chosen.reasons,
    tradeoffs: tradeoffs.slice(0, 3),
    vs_well_known: chosen.vs_well_known,
    platforms: entry.platforms,
    pricing: entry.pricing ?? 'unknown',
    processing: entry.processing ?? 'unknown',
    open_source: entry.open_source,
    license: entry.license,
    verification: {
      level: guide?.run.level ?? entry.verification.level,
      os: guide?.run.os ?? null,
      arch: guide?.run.arch ?? null,
      method: guide?.run.method ?? null,
      replayed: guide?.run.replayed ?? false,
      checked_at: guide?.run.checked_at ?? null,
      verified_on_user_os: onUserOs,
    },
    how_we_know: howWeKnow(entry, guide, matchedBy, considered),
    evidence_url: guide?.run.evidence_url ?? null,
    scores: {
      quality: entry.scores?.quality ?? null,
      popularity: entry.scores?.popularity ?? null,
      treasure: entry.scores?.treasure ?? false,
    },
    repo: entry.repo_url,
    homepage: entry.homepage,
  };
}

interface Choice {
  picks: GuardedPick[];
  bestFree: { slug: string; reason: string } | null;
  noInstall: string | null;
  question: string | null;
  parsedNeed: Record<string, unknown> | null;
  emptyByModel: boolean;
}

function fromModel(answer: ModelAnswer, picks: GuardedPick[], entries: Map<string, Entry>): Choice {
  const free = answer.best_free_slug ? entries.get(answer.best_free_slug) : undefined;
  const need = answer.need;
  return {
    picks,
    bestFree:
      free?.pricing === 'free'
        ? { slug: free.slug, reason: clip(answer.best_free_reason, 200) ?? 'Free and fits the request.' }
        : null,
    noInstall: clip(answer.no_install_option, 300),
    question: clip(answer.clarifying_question, 200),
    parsedNeed: {
      task: clip(need.task, 120),
      category: need.category,
      os: need.os,
      budget: need.budget,
      must_run_locally: need.must_run_locally,
      must_have: (need.must_have ?? []).slice(0, 6).map((s) => s.slice(0, 60)),
      search_terms: (need.search_terms ?? []).slice(0, 6).map((s) => s.slice(0, 40)),
    },
    emptyByModel: answer.picks.length === 0,
  };
}

function fromRules(input: FindInput, candidates: Entry[], cards: Map<string, Card>, limit: number): Choice {
  const ranked = rankByRules(candidates, input.need, input.os);
  const top = ranked.slice(0, limit);
  const free = ranked.find((entry) => entry.pricing === 'free');
  const osSets = new Set(top.map((entry) => entry.platforms.slice().sort().join(',')));
  return {
    picks: top.map((entry) => ({
      slug: entry.slug,
      fit: entry.summary,
      reasons: templateReasons(entry, cards.get(entry.slug)!, input.os),
      tradeoffs: [],
      vs_well_known: null,
    })),
    bestFree: free ? { slug: free.slug, reason: 'The highest-ranked free tool by rules.' } : null,
    noInstall: null,
    question: !input.os && osSets.size > 1 ? 'Which OS will you use it on: macOS, Linux or Windows?' : null,
    parsedNeed: null,
    emptyByModel: false,
  };
}

type Attempt = { answer: ModelAnswer; picks: GuardedPick[]; cost: number } | { failure: string; cost: number };

async function askModel(
  input: FindInput,
  cards: Map<string, Card>,
  limit: number,
  deps: Deps,
  now: Date,
): Promise<Attempt> {
  const { settings } = deps;
  if (!settings.modelEnabled) return { failure: 'model_off', cost: 0 };
  if (!settings.apiKey) return { failure: 'no_api_key', cost: 0 };
  const request = {
    need: input.need,
    category: input.category ?? 'any',
    os: input.os ?? null,
    arch: input.arch ?? null,
    budget: input.budget ?? null,
    must_run_locally: input.must_run_locally ?? null,
    ui_language: input.ui_language ?? null,
    limit,
  };
  const body = requestBody({
    instructions: instructions(limit),
    input: matchInput(request, [...cards.values()]),
    schemaName: 'pickfit_match',
    schema: matchSchema([...cards.keys()]),
  });
  try {
    const budget = await checkBudget(deps.db, now, estimateCostUsd(JSON.stringify(body).length), settings);
    if (!budget.ok) return { failure: 'over_budget', cost: 0 };
  } catch {
    return { failure: 'budget_unavailable', cost: 0 }; // cannot count spend, so do not spend
  }
  let cost = 0;
  try {
    const result = await callMeta(settings.apiKey, body, { timeoutMs: settings.timeoutMs, fetch: deps.fetch });
    cost = result.costUsd;
    // Token use for tuning; no request text.
    console.log(
      JSON.stringify({ event: 'meta_call', model: MATCH_MODEL, cards: cards.size, ...result.usage, cost_usd: cost, latency_ms: result.latencyMs }),
    );
    const answer = parseAnswer(result.text);
    if (!answer) return { failure: 'model_bad_output', cost };
    const guarded = guardPicks(answer, cards, limit);
    if (answer.picks.length > 0 && guarded.picks.length === 0) return { failure: 'guard_rejected_all', cost };
    return { answer, picks: guarded.picks, cost };
  } catch (err) {
    if (err instanceof MetaCallError) {
      cost = err.costUsd;
      return { failure: `model_${err.kind}`, cost };
    }
    throw err;
  } finally {
    deps.waitUntil(recordSpend(deps.db, now, cost).catch(() => undefined));
  }
}

export async function findSoftware(input: FindInput, deps: Deps): Promise<FindOutput> {
  const started = Date.now();
  const now = deps.now();
  const limit = Math.min(Math.max(input.limit ?? 3, 1), 3);
  const { candidates, passed } = hardFilter(deps.catalog.entries, input);
  const entries = new Map(candidates.map((entry) => [entry.slug, entry]));
  const cards = new Map(candidates.map((entry) => [entry.slug, toCard(entry, input.os)]));

  let choice: Choice;
  let matchedBy = 'rules';
  let degradedReason: string | null = null;
  let cost = 0;
  if (candidates.length === 0) {
    choice = { picks: [], bestFree: null, noInstall: null, question: null, parsedNeed: null, emptyByModel: false };
  } else {
    const attempt = await askModel(input, cards, limit, deps, now);
    cost = attempt.cost;
    if ('answer' in attempt) {
      matchedBy = MATCH_MODEL;
      choice = fromModel(attempt.answer, attempt.picks, entries);
    } else {
      degradedReason = attempt.failure;
      choice = fromRules(input, candidates, cards, limit);
    }
  }

  const notes: string[] = [];
  if (candidates.length === 0) {
    notes.push(
      'No verified tool in pickfit meets these conditions. Coverage today: developer CLI tools and local AI/LLM tools.',
    );
  } else if (choice.emptyByModel) {
    notes.push(`None of the ${candidates.length} verified tools that meet the conditions fits this request.`);
  }
  if (passed > MAX_CARDS) {
    notes.push(`${passed} tools met the conditions; the ${MAX_CARDS} with the highest treasure scores were compared.`);
  }

  const output: FindOutput = {
    rec_id: newId('rec'),
    matched_by: matchedBy,
    degraded: degradedReason !== null,
    degraded_reason: degradedReason,
    considered: passed,
    picks: choice.picks.map((chosen) => pickOut(entries.get(chosen.slug)!, chosen, input.os, matchedBy, passed)),
    best_free: choice.bestFree,
    no_install_option: choice.noInstall,
    clarifying_question: choice.question,
    coverage_note: notes.length ? notes.join(' ') : null,
  };

  deps.waitUntil(
    logEvent(deps.db, now, {
      type: 'find',
      rec_id: output.rec_id,
      os: input.os ?? null,
      arch: input.arch ?? null,
      category: input.category ?? 'any',
      // Conditions only; the user's own words are never stored.
      need: {
        given: {
          category: input.category ?? null,
          os: input.os ?? null,
          arch: input.arch ?? null,
          budget: input.budget ?? null,
          must_run_locally: input.must_run_locally ?? null,
          ui_language: input.ui_language ?? null,
          limit,
        },
        parsed: choice.parsedNeed,
      },
      results: output.picks.map((pick) => pick.slug),
      client: deps.client ?? null,
      matched_by: matchedBy,
      degraded: output.degraded,
      meta_cost_usd: cost,
      latency_ms: Date.now() - started,
    }).catch(() => undefined),
  );
  return output;
}
