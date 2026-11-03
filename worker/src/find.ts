/**
 * find_software and find_alternatives (architecture F.2): hard filters
 * (code) -> at most MAX_CARDS candidate cards, the ones that best match the
 * request's words when more pass (filter.ts; English keywords for the request
 * from muse-spark-1.3 first, expand.ts) -> one muse-spark-1.3 call that
 * parses the request and chooses -> guard (code). Without the model (off, no
 * key, over budget, failure after one retry of a transient error, or every
 * pick rejected) it ranks by rules and says so: matched_by "rules", degraded
 * true. find_alternatives sends the current tool and its pain points too,
 * drops the current tool from the candidates, and may advise keeping it.
 */
import {
  bestGuide,
  isWebApp,
  nameKey,
  verifiedOnUserSystem,
  webCheck,
  type Arch,
  type Catalog,
  type Entry,
  type GuiEvidence,
  type InstallGuide,
  type OS,
} from './catalog.ts';
import { toCard, type Card } from './cards.ts';
import { checkBudget, recordSpend } from './budget.ts';
import { ranSentence, videoSentence } from './evidence.ts';
import { featureSentence, featuresOut, type FeaturesOut } from './features.ts';
import { securityOut, type SecurityOut } from './security.ts';
import type { Settings } from './env.ts';
import { logEvent, logFailure, newId, type Reporter } from './events.ts';
import { englishKeywords, EXPAND_TIMEOUT_MS, type Expansion } from './expand.ts';
import { fitNote, fitOf, jobOf, type Fit, type MatchQuality } from './fit.ts';
import { hardFilter, MAX_CARDS, needsOffline, replacesCurrent, type Conditions } from './filter.ts';
import { clip, guardPicks, guardWellKnown, NO_WELL_KNOWN, parseAnswer, type GuardedPick, type GuardedWellKnown } from './guard.ts';
import { callMeta, estimateCostUsd, MATCH_MODEL, MetaCallError, requestBody } from './meta.ts';
import { instructions, matchInput, matchSchema, type MatchKind, type ModelAnswer, type ModelReason } from './prompt.ts';
import { dropNegated, queryTerms, rulesRelevance, rulesTerms, termsAsSaid } from './relevance.ts';
import { leansInstall, rankByRules, templateReasons } from './rules.ts';
import { webAppOut, webRanSentence, type WebAppOut } from './webapp.ts';

export interface FindInput extends Conditions {
  need: string;
  ui_language?: string;
  limit?: number;
}

export interface AlternativesInput extends Conditions {
  current_software: string;
  pain_points: string;
  must_keep?: string[];
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
  /** From the X-Pickfit-Reporter header; labels report_outcome rows. */
  reporter?: Reporter;
  /** The wait before retrying Meta; a seam for tests. */
  sleep?: (ms: number) => Promise<void>;
  /** This deployment's origin when it serves /video/ (VIDEOS bound); null: no clip URLs. */
  videoBase?: string | null;
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
    /** A GUI app's launch as pickfit saw it (level stays install); null for anything else. */
    gui: GuiEvidence | null;
  };
  /** Advertised features the run behind the shown guide exercised, and the ones it did not, with why. */
  features: FeaturesOut;
  how_we_know: string;
  evidence_url: string | null;
  scores: { quality: number | null; popularity: number | null; treasure: boolean };
  /** Known high or critical vulnerabilities (OSV.dev) in what a fresh install brings; unchecked says why not. */
  security: SecurityOut;
  /** null for a web app with no public repository. */
  repo: string | null;
  homepage: string | null;
  /** A hosted web app: the URL to open (nothing to install) and what pickfit's browser saw; null for anything else. */
  web_app: WebAppOut | null;
  /** Rules only: how well the profile fits the request and which of its words it covers (fit.ts); absent when the model chose. */
  match?: Fit;
}

export interface FindOutput {
  rec_id: string;
  matched_by: string;
  degraded: boolean;
  degraded_reason: string | null;
  /** Requests sent to Meta: 0 (model not used), 1, or 2 when a transient error was retried. */
  model_attempts: number;
  /** When degraded_reason is model_http: the status of Meta's last answer. */
  model_http_status: number | null;
  considered: number;
  picks: PickOut[];
  best_free: { slug: string; reason: string } | null;
  no_install_option: string | null;
  /** A well-known free tool outside pickfit's data that may fit better; never verified by pickfit. */
  well_known_option: { name: string; why: string; verified: false; how_we_know: string } | null;
  clarifying_question: string | null;
  coverage_note: string | null;
  /** Rules only: the best pick's label, or none when no pick reaches partial; absent when the model chose. */
  match_quality?: MatchQuality;
}

export interface AlternativesOutput extends FindOutput {
  current: { matched_slug: string | null; known: boolean };
  keep_current: { recommended: boolean; reason: string } | null;
}

function howWeKnow(entry: Entry, guide: InstallGuide | null, matchedBy: string, considered: number, videoBase?: string | null): string {
  const parts: string[] = [];
  const web = webCheck(entry);
  if (guide) parts.push(ranSentence(guide));
  const clip = guide ? videoSentence(entry.slug, guide.run.video, videoBase) : null;
  if (clip) parts.push(clip);
  else if (web) parts.push(webRanSentence(web));
  const covered = featureSentence(featuresOut(entry, guide));
  if (covered) parts.push(covered);
  if (entry.scores) {
    const q = entry.scores.quality === null ? 'n/a' : Math.round(entry.scores.quality);
    const p = entry.scores.popularity === null ? 'n/a' : Math.round(entry.scores.popularity);
    parts.push(`Quality ${q}/100 and popularity ${p}/100 are scored separately (formula ${entry.scores.formula_version}).`);
  }
  parts.push(
    matchedBy === 'rules'
      ? `Ranked by rules (request keywords, a web app first among close fits, verification on your OS, treasure score) among ${considered} tools that passed the hard filters; no model was used. Fit is judged by which of the request's specific words the profile mentions.`
      : `Chosen by ${matchedBy} among ${considered} tools that passed pickfit's hard filters; code checked each reason against the profile.`,
  );
  return parts.join(' ');
}

/** What pickfit did not check about a tool it only names; built from the request, not the model. */
function outsideHowWeKnow(matchedBy: string, cond: Conditions): string {
  const unchecked = ['its price'];
  if (cond.os) unchecked.push(`that it runs on ${cond.os}`);
  if (needsOffline(cond)) unchecked.push('that it works offline');
  const last = unchecked.pop()!;
  const list = unchecked.length ? `${unchecked.join(', ')} or ${last}` : last;
  return (
    `Named by ${matchedBy} from general knowledge, not from pickfit's data. ` +
    `pickfit has not installed it, has no install guide for it and has not checked ${list}.`
  );
}

function pickOut(
  entry: Entry,
  chosen: GuardedPick & { match?: Fit },
  os: OS | undefined,
  arch: Arch | undefined,
  matchedBy: string,
  considered: number,
  videoBase?: string | null,
): PickOut {
  const guide = bestGuide(entry, os);
  const web = isWebApp(entry) ? webCheck(entry) : null;
  // A web app opens in any browser: no install steps ran on any OS.
  const onUserOs = isWebApp(entry) ? null : verifiedOnUserSystem(entry, os, arch);
  const tradeoffs = [...chosen.tradeoffs];
  if (os && !onUserOs && guide) {
    // Run on the user's OS but another CPU architecture, or on another OS.
    const otherArch = guide.run.os === os;
    const ranOn = otherArch ? guide.run.arch : guide.run.os;
    const said = tradeoffs.some((t) => /verif|tested|checked/i.test(t) && t.toLowerCase().includes(ranOn));
    if (!said) {
      tradeoffs.unshift(
        otherArch
          ? `Verified on ${os} ${guide.run.arch} only; pickfit has not run its install steps on ${arch}.`
          : `Verified on ${guide.run.os} only; pickfit has not run its ${os} install steps yet.`,
      );
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
      level: guide?.run.level ?? web?.level ?? entry.verification.level,
      os: guide?.run.os ?? null,
      arch: guide?.run.arch ?? null,
      method: guide?.run.method ?? (web ? 'sandbox' : null),
      replayed: guide?.run.replayed ?? false,
      checked_at: guide?.run.checked_at ?? web?.checked_at ?? null,
      verified_on_user_os: onUserOs,
      gui: guide?.run.gui ?? null,
    },
    features: featuresOut(entry, guide),
    how_we_know: howWeKnow(entry, guide, matchedBy, considered, videoBase),
    evidence_url: guide?.run.evidence_url ?? web?.evidence_url ?? null,
    scores: {
      quality: entry.scores?.quality ?? null,
      popularity: entry.scores?.popularity ?? null,
      treasure: entry.scores?.treasure ?? false,
    },
    security: securityOut(entry),
    repo: entry.repo_url,
    homepage: entry.homepage,
    web_app: webAppOut(entry),
    ...(chosen.match ? { match: chosen.match } : {}),
  };
}

interface Choice {
  /** match: rules only, how well the pick fits (fit.ts). */
  picks: (GuardedPick & { match?: Fit })[];
  bestFree: { slug: string; reason: string } | null;
  noInstall: string | null;
  question: string | null;
  parsedNeed: Record<string, unknown> | null;
  emptyByModel: boolean;
  keepCurrent: { recommended: boolean; reason: string } | null;
  wellKnown: GuardedWellKnown;
  /** Rules only: the best label among the picks; "none" when no pick reaches partial. */
  matchQuality?: MatchQuality;
  /** Rules only, partial or none: the request's words to name as missing. */
  gaps?: string[];
  /** Rules only, none: the gaps are missing from every pick, not only the top one. */
  gapsInAll?: boolean;
  /** Rules only, partial: the highest-ranked partial pick, whose gaps the note names. */
  closest?: string;
  /** Rules only, none: some tool past the picks reaches partial, so the note speaks of the picks only. */
  fitsBeyond?: boolean;
}

const NO_CHOICE: Choice = {
  picks: [],
  bestFree: null,
  noInstall: null,
  question: null,
  parsedNeed: null,
  emptyByModel: false,
  keepCurrent: null,
  wellKnown: NO_WELL_KNOWN,
};

const shortList = (items: string[] | undefined, n: number, max: number) =>
  (Array.isArray(items) ? items : []).slice(0, n).map((s) => String(s).slice(0, max));

function fromModel(
  answer: ModelAnswer,
  picks: GuardedPick[],
  entries: Map<string, Entry>,
  kind: MatchKind,
  wellKnown: GuardedWellKnown,
): Choice {
  const free = answer.best_free_slug ? entries.get(answer.best_free_slug) : undefined;
  const need = answer.need;
  const keep = answer.keep_current;
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
      must_have: shortList(need.must_have, 6, 60),
      search_terms: shortList(need.search_terms, 6, 40),
      ...(kind === 'alternatives'
        ? { current_tool: clip(need.current_tool, 40), pain_points: shortList(need.pain_points, 4, 60) }
        : {}),
    },
    emptyByModel: answer.picks.length === 0,
    keepCurrent:
      kind === 'alternatives' && typeof keep?.recommended === 'boolean'
        ? { recommended: keep.recommended, reason: clip(keep.reason, 300) ?? '' }
        : null,
    wellKnown,
  };
}

function fromRules(
  req: MatchRequest,
  candidates: Entry[],
  relevance: Map<string, number>,
  cards: Map<string, Card>,
  limit: number,
  corpus: Entry[],
): Choice {
  const os = req.conditions.os;
  const ranked = rankByRules(candidates, relevance, os, req.currentTool, leansInstall(req.rulesText));
  const top = ranked.slice(0, limit);
  const free = ranked.find((entry) => entry.pricing === 'free');
  const osSets = new Set(top.map((entry) => entry.platforms.slice().sort().join(',')));
  // Labels only: the fit decision never removes or reorders a pick.
  const job = req.painPoints ? jobOf(corpus, req.painPoints.rest, req.painPoints.said) : jobOf(corpus, req.rulesText);
  const fitFor = (entry: Entry) => (replacesCurrent(entry, req.currentTool) ? replacing(req.currentTool!) : fitOf(entry, job));
  const fits = top.map(fitFor);
  const best = fits.find((f) => f.quality === 'good') ?? fits.find((f) => f.quality === 'partial');
  // Words no pick mentions, else what the top pick does not mention.
  const unmentioned = fits[0]?.missing.filter((word) => fits.every((f) => f.missing.includes(word))) ?? [];
  return {
    picks: top.map((entry, i) => ({
      slug: entry.slug,
      fit: entry.summary,
      reasons: templateReasons(entry, cards.get(entry.slug)!, os),
      tradeoffs: [fitNote(fits[i])].filter((note): note is string => note !== null),
      vs_well_known: null,
      match: fits[i],
    })),
    bestFree: free ? { slug: free.slug, reason: 'The highest-ranked free tool by rules.' } : null,
    noInstall: null,
    question: !os && osSets.size > 1 ? 'Which OS will you use it on: macOS, Linux or Windows?' : null,
    parsedNeed: null,
    emptyByModel: false,
    keepCurrent: null, // rules cannot judge the current tool
    wellKnown: NO_WELL_KNOWN, // rules know only pickfit's data
    matchQuality: best ? (best.quality === 'good' ? 'good' : 'partial') : 'none',
    gaps: (best ? best.missing : unmentioned.length ? unmentioned : (fits[0]?.missing ?? [])).slice(0, 5),
    gapsInAll: unmentioned.length > 0,
    closest: best ? top[fits.indexOf(best)].slug : undefined,
    fitsBeyond: !best && ranked.slice(limit).some((entry) => fitFor(entry).quality !== 'weak'),
  };
}

/** find_alternatives: a profile that names the current tool as what it replaces. */
const replacing = (current: string): Fit => ({ quality: 'good', covers: [`an alternative to ${current}`], missing: [] });

/** statuses: HTTP status of each request sent to Meta (null where none came back). */
type Attempt = { cost: number; statuses: (number | null)[] } & (
  | { answer: ModelAnswer; picks: GuardedPick[] }
  | { failure: string; httpStatus: number | null; rejected?: ModelAnswer }
);

const notSent = (failure: string): Attempt => ({ failure, httpStatus: null, cost: 0, statuses: [] });

async function askModel(
  request: Record<string, unknown>,
  kind: MatchKind,
  cards: Map<string, Card>,
  limit: number,
  deps: Deps,
  now: Date,
  timeoutMs: number,
): Promise<Attempt> {
  const { settings } = deps;
  if (!settings.modelEnabled) return notSent('model_off');
  if (!settings.apiKey) return notSent('no_api_key');
  const body = requestBody({
    instructions: instructions(limit, kind),
    input: matchInput(request, [...cards.values()]),
    schemaName: kind === 'alternatives' ? 'pickfit_alternatives' : 'pickfit_match',
    schema: matchSchema([...cards.keys()], kind),
  });
  try {
    const budget = await checkBudget(deps.db, now, estimateCostUsd(JSON.stringify(body).length), settings);
    if (!budget.ok) return notSent('over_budget');
  } catch {
    return notSent('budget_unavailable'); // cannot count spend, so do not spend
  }
  let cost = 0;
  try {
    // A retry fits in the cap checked above: the failed try was not charged.
    const result = await callMeta(settings.apiKey, body, {
      timeoutMs,
      via: settings.via,
      fetch: deps.fetch,
      clock: () => deps.now().getTime(),
      sleep: deps.sleep,
    });
    cost = result.costUsd;
    const { statuses } = result;
    // Token use for tuning; no request text.
    console.log(
      JSON.stringify({ event: 'meta_call', kind, model: MATCH_MODEL, cards: cards.size, ...result.usage, cost_usd: cost, latency_ms: result.latencyMs, statuses }),
    );
    // From here on Meta has answered: a bad or rejected answer is never retried.
    const answer = parseAnswer(result.text);
    if (!answer) return { failure: 'model_bad_output', httpStatus: null, cost, statuses };
    const guarded = guardPicks(answer, cards, limit);
    if (answer.picks.length > 0 && guarded.picks.length === 0) {
      return { failure: 'guard_rejected_all', httpStatus: null, cost, statuses, rejected: answer };
    }
    return { answer, picks: guarded.picks, cost, statuses };
  } catch (err) {
    if (err instanceof MetaCallError) {
      cost = err.costUsd;
      const httpStatus = err.kind === 'http' ? err.status : null;
      return { failure: `model_${err.kind}`, httpStatus, cost, statuses: err.statuses };
    }
    throw err;
  } finally {
    deps.waitUntil(recordSpend(deps.db, now, cost).catch(logFailure('meta_budget')));
  }
}

interface MatchRequest {
  kind: MatchKind;
  conditions: Conditions & { ui_language?: string; limit?: number };
  /** What the model reads inside <request>. */
  modelRequest: Record<string, unknown>;
  /** Text the rules fallback ranks profiles against (the keyword call and the shortlist read it too). */
  rulesText: string;
  /**
   * find_alternatives: rulesText in two parts. In the pain points a negation names what the user wants
   * ("no dark mode"), so the rules and the fit labels keep those words; what must be kept is negated as usual.
   */
  painPoints?: { said: string; rest: string };
  /** find_alternatives: the rules rank profiles that name this tool first. */
  currentTool?: string;
  /** Extra parsed conditions to log (never the user's words). */
  logged?: Record<string, unknown>;
}

async function recommend(req: MatchRequest, deps: Deps): Promise<{ output: FindOutput; keepCurrent: Choice['keepCurrent'] }> {
  const started = Date.now();
  const now = deps.now();
  const cond = req.conditions;
  const limit = Math.min(Math.max(cond.limit ?? 3, 1), 3);
  const corpus = deps.catalog.entries;
  // Without Meta's keywords (rules only, the call failed, or no shortlist cut) the rules' scorer chooses and ranks.
  // The rules' words: a negation is a constraint, except in pain points.
  const ruleTerms = (...keywords: string[]) =>
    req.painPoints ? [...new Set([...termsAsSaid(req.painPoints.said), ...rulesTerms(req.painPoints.rest, ...keywords)])] : rulesTerms(req.rulesText, ...keywords);
  let filtered = hardFilter(corpus, cond, { terms: ruleTerms(), current: req.currentTool, scorer: 'rules' });
  // Only a shortlist that must cut needs the request in the profiles' words.
  let expansion: Expansion | null = null;
  if (filtered.passed > MAX_CARDS) {
    expansion = await englishKeywords(req.rulesText, deps, now, Math.min(EXPAND_TIMEOUT_MS, deps.settings.timeoutMs));
    if (expansion.keywords) {
      // A need's negated words are constraints ("不需要 GPU"). Pain points stay as they are: there "no dark mode"
      // names what the current tool lacks, so find_alternatives' shortlist is unchanged.
      const own = req.kind === 'find' ? dropNegated(req.rulesText) : req.rulesText;
      const terms = queryTerms(own, ...expansion.keywords);
      filtered = hardFilter(corpus, cond, { terms, current: req.currentTool });
    }
  }
  const { candidates, passed, byRelevance } = filtered;
  // The rules rank with their own scorer, adding Meta's keywords when there are some.
  const rulesScores = () =>
    expansion?.keywords
      ? rulesRelevance(corpus, candidates, ruleTerms(...expansion.keywords))
      : filtered.relevance;
  const entries = new Map(candidates.map((entry) => [entry.slug, entry]));
  const cards = new Map(candidates.map((entry) => [entry.slug, toCard(entry, cond.os, cond.arch)]));

  let choice: Choice;
  let matchedBy = 'rules';
  let degradedReason: string | null = null;
  let httpStatus: number | null = null;
  let statuses: (number | null)[] = [];
  let cost = 0;
  if (candidates.length === 0) {
    choice = NO_CHOICE;
  } else {
    // META_TIMEOUT_MS bounds every Meta request of this call: the match gets what the keywords left.
    const timeoutMs = Math.max(0, deps.settings.timeoutMs - (expansion?.latencyMs ?? 0));
    const attempt = await askModel({ ...req.modelRequest, limit }, req.kind, cards, limit, deps, now, timeoutMs);
    cost = attempt.cost;
    statuses = attempt.statuses;
    if ('answer' in attempt) {
      matchedBy = MATCH_MODEL;
      const wellKnown = guardWellKnown(attempt.answer, deps.catalog.entries, req.currentTool);
      choice = fromModel(attempt.answer, attempt.picks, entries, req.kind, wellKnown);
    } else {
      degradedReason = attempt.failure;
      httpStatus = attempt.httpStatus;
      choice = fromRules(req, candidates, rulesScores(), cards, limit, corpus);
      if (attempt.rejected) {
        // Not shown (the whole answer was rejected), but the log still says what the model named.
        const named = guardWellKnown(attempt.rejected, deps.catalog.entries, req.currentTool);
        choice.wellKnown = { option: null, name: named.name, dropped: named.option ? 'answer_rejected' : named.dropped };
      }
    }
  }

  const what = req.kind === 'alternatives' ? 'alternative' : 'tool';
  const notes: string[] = [];
  if (candidates.length === 0) {
    notes.push(
      `No verified ${what} in pickfit meets these conditions. Coverage today: developer CLI tools, local AI/LLM tools, MCP servers, desktop GUI apps and some web apps. ` +
        "pickfit's catalog doesn't cover every tool yet, so a well-known one may still fit.",
    );
  } else if (choice.emptyByModel) {
    notes.push(`None of the ${candidates.length} verified tools that meet the conditions fits this request.`);
  } else if (choice.matchQuality === 'none') {
    // Labels only: the picks stay listed; the note says how far they are from the request, not to drop them.
    const gaps = choice.gaps?.length ? choice.gaps.join(', ') : '';
    const miss = !gaps ? 'none of them covers enough of the request' : choice.gapsInAll ? `none of them mentions ${gaps}` : `each mentions only part of it (the top one does not mention ${gaps})`;
    notes.push(
      choice.fitsBeyond
        ? `None of the listed ${what}s clearly does this job: judging by their profiles, ${miss}. They are listed as the top-ranked ${what}s; each pick's match says what it covers.`
        : `pickfit has no verified ${what} that clearly does this job. Judging by their profiles, the listed ${what}s are the closest it has, but ${miss}; each pick's match says what it covers. ` +
            "pickfit's catalog doesn't cover every tool yet, so a well-known one may still fit.",
    );
  } else if (choice.matchQuality === 'partial') {
    const gaps = choice.gaps?.length ? `: the closest, ${choice.closest}, does not mention ${choice.gaps.join(', ')}` : '';
    notes.push(`No listed ${what} covers the whole request${gaps}. Each pick's match says what it covers.`);
  }
  if (passed > MAX_CARDS) {
    notes.push(
      byRelevance > 0
        ? `${passed} tools met the conditions; the ${MAX_CARDS} compared were the ${byRelevance} whose profiles best match the request's words and the ${MAX_CARDS - byRelevance} other tools with the highest treasure scores.`
        : `${passed} tools met the conditions; no profile matched the request's words, so the ${MAX_CARDS} with the highest treasure scores were compared.`,
    );
  }

  const output: FindOutput = {
    rec_id: newId('rec'),
    matched_by: matchedBy,
    degraded: degradedReason !== null,
    degraded_reason: degradedReason,
    model_attempts: statuses.length,
    model_http_status: httpStatus,
    considered: passed,
    picks: choice.picks.map((chosen) => pickOut(entries.get(chosen.slug)!, chosen, cond.os, cond.arch, matchedBy, passed, deps.videoBase)),
    best_free: choice.bestFree,
    no_install_option: choice.noInstall,
    well_known_option: choice.wellKnown.option
      ? { ...choice.wellKnown.option, verified: false, how_we_know: outsideHowWeKnow(matchedBy, cond) }
      : null,
    clarifying_question: choice.question,
    coverage_note: notes.length ? notes.join(' ') : null,
    ...(choice.matchQuality ? { match_quality: choice.matchQuality } : {}),
  };

  deps.waitUntil(
    logEvent(deps.db, now, {
      type: req.kind,
      rec_id: output.rec_id,
      os: cond.os ?? null,
      arch: cond.arch ?? null,
      category: cond.category ?? 'any',
      // Conditions only; the user's own words are never stored.
      need: {
        given: {
          category: cond.category ?? null,
          os: cond.os ?? null,
          arch: cond.arch ?? null,
          budget: cond.budget ?? null,
          must_run_locally: cond.must_run_locally ?? null,
          ...(cond.offline !== undefined ? { offline: cond.offline } : {}),
          ...(cond.data_stays_local !== undefined ? { data_stays_local: cond.data_stays_local } : {}),
          ui_language: cond.ui_language ?? null,
          limit,
        },
        parsed: choice.parsedNeed,
        // The model's own words, not the user's: which outside tool it named and whether code kept it.
        well_known:
          choice.wellKnown.name || choice.wellKnown.dropped
            ? { name: choice.wellKnown.name, dropped: choice.wellKnown.dropped }
            : null,
        ...(choice.matchQuality ? { match_quality: choice.matchQuality } : {}),
        // How the cards were chosen when not all could be sent; counts and outcomes only.
        shortlist:
          passed > MAX_CARDS ? { by_relevance: byRelevance, keywords: expansion?.outcome ?? null } : null,
        ...req.logged,
      },
      results: output.picks.map((pick) => pick.slug),
      client: deps.client ?? null,
      matched_by: matchedBy,
      degraded: output.degraded,
      degraded_reason: degradedReason,
      model_attempts: statuses.length,
      model_statuses: statuses,
      meta_cost_usd: cost + (expansion?.costUsd ?? 0),
      latency_ms: Date.now() - started,
    }).catch(logFailure(req.kind, output.rec_id)),
  );
  return { output, keepCurrent: choice.keepCurrent };
}

function sharedRequest(input: Conditions & { ui_language?: string }) {
  return {
    category: input.category ?? 'any',
    os: input.os ?? null,
    arch: input.arch ?? null,
    budget: input.budget ?? null,
    must_run_locally: input.must_run_locally ?? null,
    // Only when given, so a request without them reads as before.
    ...(input.offline !== undefined ? { offline: input.offline } : {}),
    ...(input.data_stays_local !== undefined ? { data_stays_local: input.data_stays_local } : {}),
    ui_language: input.ui_language ?? null,
  };
}

export async function findSoftware(input: FindInput, deps: Deps): Promise<FindOutput> {
  const { output } = await recommend(
    {
      kind: 'find',
      conditions: input,
      modelRequest: { need: input.need, ...sharedRequest(input) },
      rulesText: input.need,
    },
    deps,
  );
  return output;
}

/** The user's current tool in the catalog (by slug or name), and whether pickfit knows it at all. */
export function matchCurrent(catalog: Catalog, name: string): AlternativesOutput['current'] {
  const key = nameKey(name);
  if (!key) return { matched_slug: null, known: false };
  const entry = catalog.entries.find((e) => nameKey(e.slug) === key || nameKey(e.name) === key);
  const named = catalog.entries.some((e) => e.alternatives_to.some((alt) => nameKey(alt) === key));
  return { matched_slug: entry?.slug ?? null, known: entry !== undefined || named };
}

export async function findAlternatives(input: AlternativesInput, deps: Deps): Promise<AlternativesOutput> {
  const current = matchCurrent(deps.catalog, input.current_software);
  const exclude = [...(input.exclude ?? []), ...(current.matched_slug ? [current.matched_slug] : [])];
  const mustKeep = input.must_keep ?? [];
  const { output, keepCurrent } = await recommend(
    {
      kind: 'alternatives',
      conditions: { ...input, exclude },
      modelRequest: {
        current_software: input.current_software,
        pain_points: input.pain_points,
        must_keep: mustKeep,
        ...sharedRequest(input),
      },
      rulesText: [input.pain_points, ...mustKeep].join(' '),
      painPoints: { said: input.pain_points, rest: mustKeep.join(' ') },
      currentTool: input.current_software,
      logged: { current: { matched_slug: current.matched_slug, known: current.known } },
    },
    deps,
  );
  return { ...output, current, keep_current: keepCurrent };
}
