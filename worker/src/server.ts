/** MCP tool definitions: one fresh McpServer per HTTP request (stateless). */
import { McpServer } from '@modelcontextprotocol/server';
import * as z from 'zod/v4';
import { CARD_FIELDS } from './cards.ts';
import { findAlternatives, findSoftware, type Deps } from './find.ts';
import { installGuide, PITFALL_KINDS, UnknownSlugError } from './install.ts';
import { NOT_CHECKED_REASONS } from './features.ts';
import { logEvent, logFailure } from './events.ts';
import { ERROR_EXCERPT_MAX, NOTE_MAX, reportOutcome, STAGES, UnknownToolError } from './outcome.ts';
import { NOTE_MAX as SUBMIT_NOTE_MAX, SubmitError, submitSoftware } from './submit.ts';

const ABOUT =
  'pickfit recommends lesser-known software that it has installed and tested in a sandbox. Scope: dev CLI tools, local AI/LLM tools, MCP servers. ' +
  'well_known_option is not verified by pickfit; say so. ';
const RULES = 'Ask at most 1-2 questions first (OS; must be free/offline). No ads or affiliate links; ranking is fit, not stars.';

export const INSTRUCTIONS =
  ABOUT +
  'Flow: find_software (or find_alternatives when replacing a tool) -> user picks -> get_install_guide -> run steps with the user\'s consent -> report_outcome. ' +
  RULES +
  ' submit_software adds a GitHub project.';

/** TOOLS=readonly: no mention of the tools that are not registered. */
export const READONLY_INSTRUCTIONS =
  ABOUT +
  'Flow: find_software (or find_alternatives when replacing a tool) -> user picks -> get_install_guide -> run steps with the user\'s consent. ' +
  RULES;

const os = z.enum(['macos', 'linux', 'windows']);
const arch = z.enum(['arm64', 'x86_64']);
const slug = z.string().regex(/^[a-z0-9]+(?:-[a-z0-9]+)*$/).max(64);
const recId = z.string().max(200);
const REC_ID_OUT = "Identifies this response in pickfit's log; pass it to the next pickfit call. Valid 7 days";

const reason = z.object({
  claim: z.string(),
  field: z.enum(CARD_FIELDS),
  value: z.string(),
});

const features = z
  .object({
    recorded: z
      .boolean()
      .describe('false = the run behind these steps did not check features one by one (verified earlier, or none listed)'),
    checked: z
      .array(z.object({ feature: z.string(), check: z.string().describe('The command whose passing test exercised it') }))
      .describe('Advertised features a passing test in the verification run exercised'),
    not_checked: z
      .array(
        z.object({
          feature: z.string(),
          reason: z.enum(NOT_CHECKED_REASONS),
          detail: z.string(),
        }),
      )
      .describe('Advertised features pickfit did not see working, and why; do not present them as verified'),
  })
  .describe("The main features the README advertises, as pickfit's verification run covered them");

/** A GUI app's launch as pickfit saw it; the level stays install (a launch is not a feature test). */
const gui = z
  .object({
    tier: z
      .enum(['window', 'ui_rendered'])
      .describe("window = a window of the app's own process opened; ui_rendered = a separate model saw the app's own UI drawn"),
    screen: z
      .enum(['main_ui', 'first_run', 'sign_in_wall', 'crash_or_error', 'blank_or_loading', 'other'])
      .describe("What that model saw in a screenshot of the app's own windows"),
    display: z.string().describe('The virtual display it ran on'),
    launch_offline: z.boolean().nullable().describe('The launch passed again with the network off in a fresh sandbox'),
  })
  .nullable()
  .describe('A GUI app: what pickfit saw when it launched it. null for other software');

const pick = z.object({
  slug: z.string(),
  name: z.string(),
  summary: z.string(),
  fit: z.string(),
  why: z.array(reason).describe('Reasons, each tied to one field of the verified profile'),
  tradeoffs: z.array(z.string()),
  vs_well_known: z.string().nullable(),
  platforms: z.array(os),
  pricing: z.enum(['free', 'freemium', 'paid', 'unknown']),
  processing: z.enum(['local', 'cloud', 'hybrid', 'unknown']),
  open_source: z.boolean().nullable(),
  license: z.string().nullable(),
  verification: z.object({
    level: z.string(),
    os: os.nullable(),
    arch: arch.nullable(),
    method: z.enum(['sandbox', 'human']).nullable(),
    replayed: z.boolean(),
    checked_at: z.string().nullable(),
    verified_on_user_os: z
      .boolean()
      .nullable()
      .describe('true = pickfit ran the install steps on your OS, and on your CPU architecture when arch was given; null = no os given'),
    gui: gui,
  }),
  features,
  how_we_know: z.string(),
  evidence_url: z.string().nullable(),
  scores: z.object({
    quality: z.number().nullable().describe('0-100'),
    popularity: z.number().nullable().describe('0-100; scored separately from quality'),
    treasure: z.boolean().describe('High quality, low popularity'),
  }),
  repo: z.string(),
  homepage: z.string().nullable(),
  match: z
    .object({
      quality: z.enum(['good', 'partial', 'weak']),
      covers: z.array(z.string()).describe("The request's words this profile mentions"),
      missing: z.array(z.string()).describe("The request's words it does not mention"),
    })
    .optional()
    .describe(
      "Rules-only answers: how well the profile covers the request's specific words (good: most of them; partial: some; weak: less). A label only: every pick is still listed. Absent when the model chose",
    ),
});

/** The user's conditions, shared by find_software and find_alternatives. */
const conditions = {
  category: z.enum(['dev_cli', 'local_ai', 'mcp_server', 'any']).optional().describe('Default any; mcp_server = an MCP server to add to an AI client'),
  os: os.optional(),
  arch: arch.optional(),
  budget: z.enum(['free_only', 'free_or_paid']).optional(),
  must_run_locally: z.boolean().optional().describe('true = must work offline; no data leaves the machine'),
  ui_language: z.string().max(35).optional().describe('BCP 47 tag, only if the user needs the UI or docs in that language'),
  exclude: z.array(slug).max(20).optional().describe('Slugs already shown or rejected'),
  limit: z.number().int().min(1).max(3).optional().describe('Default 3'),
};

/** find_software's input; the web page validates its form with the same schema. */
export const findInput = z.object({
  need: z
    .string()
    .min(3)
    .max(500)
    .describe("The job to get done, in the user's words. Describe the task, not a product name."),
  ...conditions,
});

const alternativesInput = z.object({
  current_software: z.string().min(1).max(100).describe('The tool the user uses now'),
  pain_points: z.string().min(3).max(500).describe('What the user dislikes about it, in their words'),
  must_keep: z.array(z.string().max(100)).max(5).optional().describe('What the replacement must still do'),
  ...conditions,
});

const findOutput = z.object({
  rec_id: z.string().describe(REC_ID_OUT),
  matched_by: z.string().describe('The Meta model that chose the picks, or "rules"'),
  degraded: z.boolean().describe('true = ranked by rules without the model (off, budget or failure)'),
  degraded_reason: z.string().nullable(),
  model_attempts: z
    .number()
    .int()
    .describe('Requests sent to Meta: 0 = model not used, 2 = retried once after a transient error'),
  model_http_status: z.number().int().nullable().describe('When degraded_reason is model_http: the HTTP status Meta returned'),
  considered: z.number().int().describe('Verified tools that met the hard conditions'),
  picks: z.array(pick).max(3),
  best_free: z.object({ slug: z.string(), reason: z.string() }).nullable(),
  no_install_option: z
    .string()
    .nullable()
    .describe("Something built in or already installed that would be enough; from the model's general knowledge, not checked by pickfit"),
  well_known_option: z
    .object({
      name: z.string(),
      why: z.string().describe('One sentence from the model: why this free tool may fit better than the picks'),
      verified: z.literal(false).describe('Always false: pickfit has not installed or checked it'),
      how_we_know: z.string(),
    })
    .nullable()
    .describe(
      "A well-known free tool outside pickfit's data that may fit this person better than the picks; usually null. " +
        'Not verified, no install guide (get_install_guide does not know it). Present it as such.',
    ),
  clarifying_question: z.string().nullable(),
  coverage_note: z.string().nullable(),
  match_quality: z
    .enum(['good', 'partial', 'none'])
    .optional()
    .describe(
      'Rules-only answers: the best pick\'s label; none = no pick reaches partial (coverage_note names what they miss; the picks are still listed). Absent when the model chose',
    ),
});

const alternativesOutput = findOutput.extend({
  current: z.object({
    matched_slug: z.string().nullable().describe('The current tool in pickfit, if listed; never among the picks'),
    known: z.boolean().describe('pickfit lists it, or names it as an alternative on some profile'),
  }),
  keep_current: z
    .object({ recommended: z.boolean(), reason: z.string() })
    .nullable()
    .describe('recommended true = no pick is clearly better than the current tool; null when ranked by rules'),
});

const installInput = z.object({
  slug,
  os,
  arch: arch.optional(),
  rec_id: recId.optional(),
});

const installOutput = z.object({
  rec_id: z.string().describe(REC_ID_OUT),
  matched_by: z.literal('rules').describe('No model is used here: these are the steps of a recorded run'),
  slug: z.string(),
  name: z.string(),
  how_we_know: z.string(),
  evidence_url: z.string().nullable().describe('Run record of the verification'),
  verification: z.object({
    status: z.enum(['verified', 'unverified']),
    level: z.string().nullable(),
    os: os.nullable(),
    arch: arch.nullable(),
    method: z.enum(['sandbox', 'human']).nullable(),
    replayed: z.boolean(),
    runner: z.string().nullable(),
    checked_at: z.string().nullable(),
    tool_version: z.string().nullable(),
    evidence_url: z.string().nullable(),
    works_offline: z
      .boolean()
      .nullable()
      .describe('true = its checks passed again with the network off after install; false = they needed the network; null = not checked'),
    gui: gui,
  }),
  applies_to_user_system: z.object({
    match: z.enum(['exact', 'same_os_other_arch', 'other_os', 'none']),
    note: z.string().nullable(),
  }),
  steps: z.array(
    z.object({
      order: z.number().int(),
      command: z.string(),
      purpose: z.string().nullable(),
      run_by: z.literal('agent'),
      needs_sudo: z.boolean(),
    }),
  ),
  manual_steps: z.array(z.object({ title: z.string(), run_by: z.literal('user') })),
  verify: z.object({ command: z.string(), expected_contains: z.string() }).nullable(),
  first_task: z.string().nullable(),
  first_task_setup: z
    .array(z.object({ command: z.string(), run_in_background: z.boolean() }))
    .describe('Commands the first task needs first (an input file, a server), from the same run'),
  features,
  known_issues: z.array(
    z.object({
      readme_said: z.string(),
      actually_needed: z.string(),
      kind: z
        .enum(PITFALL_KINDS)
        .nullable()
        .optional()
        .describe('readme_wrong = following the README hits it; sandbox = only the sandbox needed it; tool_handled = the tool did it itself; note = nothing to fix'),
    }),
  ),
  mcp_client_config: z
    .object({
      transport: z.enum(['stdio', 'streamable_http']),
      command: z.string().describe('stdio: what the client starts; streamable_http: what to start first and keep running'),
      args: z.array(z.string()),
      url: z.string().nullable().describe('streamable_http: where the client connects once the server runs'),
      claude_code: z.string().describe('A `claude mcp add` line for Claude Code'),
      json: z.string().describe('An mcpServers entry (JSON text) for Claude Desktop, Cursor and other clients'),
      env: z.array(
        z.object({
          name: z.string(),
          required: z.boolean().nullable(),
          purpose: z.string().nullable(),
          placeholder: z.string().describe('Replace with the user\'s own value; pickfit never had one'),
        }),
      ),
      tools: z.array(z.string()).describe('Tool names the server listed in the sandbox handshake'),
      tool_count: z.number().int(),
      called_tool: z.string().nullable().describe('A tool pickfit called without an error; null = only the handshake was checked'),
      works_offline: z.boolean().nullable().describe('true = the handshake also completed with the network off'),
      note: z.string().nullable(),
    })
    .nullable()
    .describe('MCP servers only: how to add it to an MCP client, from the launch command a fresh sandbox started; null for other software'),
  warnings: z.array(z.string()),
  sources: z.array(z.string()),
});

const outcomeInput = z.object({
  slug,
  stage: z
    .enum(STAGES)
    .describe('How far the user got: installed, install_failed, first_run_ok, first_run_failed, still_using, replaced, abandoned'),
  rec_id: recId.optional().describe('From find_software, find_alternatives or get_install_guide; without it the report is not counted'),
  satisfaction: z.enum(['satisfied', 'neutral', 'dissatisfied', 'unknown']).optional(),
  os: os.optional(),
  arch: arch.optional(),
  error_excerpt: z
    .string()
    .max(2000)
    .optional()
    .describe(`Last lines of the error, with user names, paths and tokens removed; pickfit keeps the last ${ERROR_EXCERPT_MAX} characters`),
  replaced_by: z.string().max(100).optional().describe('Only with stage "replaced": the slug or name of what replaced it'),
  note: z.string().max(NOTE_MAX).optional().describe('Optional short feedback, without personal data; read by people only'),
});

const outcomeOutput = z.object({
  accepted: z.boolean(),
  report_id: z.string(),
  rec_id: z.string().nullable().describe('The recommendation this report is tied to, when counted'),
  deduplicated: z.boolean().describe('true = this rec_id, slug, stage and result were already reported; nothing changed'),
  counted_in_score: z.boolean(),
  not_counted_reason: z.enum(['no_rec_id', 'unknown_or_expired_rec_id']).nullable(),
  reverify: z.enum(['queued', 'already_queued', 'none']).describe('Whether pickfit will re-run the install steps in a fresh sandbox'),
  next: z.string().nullable(),
});

const submitInput = z.object({
  url: z.string().min(10).max(300).describe('https URL of a GitHub repository, e.g. https://github.com/owner/repo'),
  submitter_role: z.enum(['author', 'user', 'unknown']).optional().describe('Is the user its author? Default unknown'),
  note: z.string().max(SUBMIT_NOTE_MAX).optional().describe('Optional: what the tool is for, without personal data; read by people only'),
});

const submitOutput = z.object({
  submission_id: z.string().nullable().describe('null when the repository is already listed'),
  url: z.string().describe('The normalized repository URL'),
  status: z.enum(['queued', 'reading', 'verifying', 'listed', 'listed_unverified', 'rejected']),
  slug: z.string().nullable(),
  reason: z.string().nullable().describe('Why it was rejected, when it was'),
  already_submitted: z.boolean().describe('true = this call only read the status'),
  check_again_after_s: z.number().int().nullable(),
  next: z.string(),
});

function toolError(message: string) {
  return { content: [{ type: 'text' as const, text: message }], isError: true };
}

function result(out: object) {
  return {
    content: [{ type: 'text' as const, text: JSON.stringify(out) }],
    structuredContent: out as Record<string, unknown>,
  };
}

export function buildServer(deps: Deps): McpServer {
  const readonly = deps.settings.tools === 'readonly';
  const server = new McpServer(
    { name: 'pickfit', version: '0.1.0' },
    { instructions: readonly ? READONLY_INSTRUCTIONS : INSTRUCTIONS },
  );

  server.registerTool(
    'find_software',
    {
      title: 'Find software',
      description:
        'Use when the user wants a tool for a job and has not settled on a product (e.g. "a free offline CLI to transcribe audio on my Mac"). ' +
        'Before calling, ask at most one or two questions, and only if unknown: which OS, and whether it must be free or run fully offline. ' +
        'Returns up to 3 lesser-known tools whose install pickfit actually ran, ranked by fit (not popularity), each with reasons tied to its verified profile, trade-offs, verification evidence and separate quality/popularity scores, plus the best free option. ' +
        'If a well-known free tool pickfit does not list may fit better, well_known_option names it: tell the user pickfit has not verified it. ' +
        'If clarifying_question is set, ask it and call again. When matched_by is "rules", match_quality and each pick\'s match say how well the profiles cover the request; present partial or weak picks as such. ' +
        'Next: get_install_guide(slug, os, rec_id). Coverage: developer CLI tools, local AI/LLM tools and MCP servers.',
      inputSchema: findInput,
      outputSchema: findOutput,
      annotations: { readOnlyHint: true, openWorldHint: false },
    },
    async (args) => result(await findSoftware(args, deps)),
  );

  server.registerTool(
    'find_alternatives',
    {
      title: 'Find alternatives to a tool',
      description:
        'Use when the user already uses a specific tool and wants something different ("replace X", "X is too slow / too expensive / needs an account"). ' +
        'Requires the current tool\'s name and what the user dislikes about it: ask for the dislike if they have not said it; do not guess. Ask for the OS only if unknown. ' +
        'Returns up to 3 lesser-known tools whose install pickfit actually ran, each with reasons tied to its verified profile, trade-offs against the current tool and verification evidence, ' +
        'or keep_current advice when nothing fits better, plus the best free option and, rarely, an unverified well-known free tool (well_known_option). Next: get_install_guide(slug, os, rec_id).',
      inputSchema: alternativesInput,
      outputSchema: alternativesOutput,
      annotations: { readOnlyHint: true, openWorldHint: false },
    },
    async (args) => result(await findAlternatives(args, deps)),
  );

  server.registerTool(
    'get_install_guide',
    {
      title: 'Get a verified install guide',
      description:
        'Use after the user picks a tool from find_software or find_alternatives. Returns install steps pickfit actually ran (replayed in a fresh sandbox, or done by hand), with the OS, date and evidence, ' +
        'the steps only the user can do (permissions, accounts), a command to verify the install and a first task to try. ' +
        'For an MCP server, mcp_client_config gives the `claude mcp add` line and the mcpServers JSON for the launch command pickfit started, with placeholders for keys the user must supply. ' +
        'Show each command to the user before running it, and ask before any step that needs sudo or pipes a script into a shell. ' +
        'If applies_to_user_system.match is not "exact", tell the user the steps were checked on a different system.' +
        (readonly ? '' : ' After the user tries it, call report_outcome with the rec_id.'),
      inputSchema: installInput,
      outputSchema: installOutput,
      annotations: { readOnlyHint: true, openWorldHint: false },
    },
    async (args) => {
      try {
        const out = installGuide(deps.catalog, args);
        const now = deps.now();
        deps.waitUntil(
          logEvent(deps.db, now, {
            type: 'install_guide',
            slug: out.slug,
            os: args.os,
            arch: args.arch ?? null,
            rec_id: out.rec_id,
            results: [out.applies_to_user_system.match],
            client: deps.client ?? null,
          }).catch(logFailure('install_guide', out.rec_id)),
        );
        return result(out);
      } catch (err) {
        if (err instanceof UnknownSlugError) return toolError(err.message);
        throw err;
      }
    },
  );

  // An evaluation deployment (TOOLS=readonly) exposes no tool that writes user data.
  if (readonly) return server;

  server.registerTool(
    'report_outcome',
    {
      title: 'Report how a recommended tool worked out',
      description:
        'Call after the user tried a tool pickfit recommended, once for each stage reached: installed or install_failed, first_run_ok or first_run_failed, and later still_using, replaced or abandoned. ' +
        'Pass the rec_id from find_software, find_alternatives or get_install_guide; without it the report is stored but not counted. ' +
        'Remove user names, file paths, tokens and other personal data from error_excerpt and note; pickfit stores no account or IP. ' +
        'A failed install with an error excerpt makes pickfit re-run the install steps in a fresh sandbox. Repeating the same report changes nothing.',
      inputSchema: outcomeInput,
      outputSchema: outcomeOutput,
      annotations: { readOnlyHint: false, destructiveHint: false, idempotentHint: true, openWorldHint: false },
    },
    async (args) => {
      try {
        return result(
          await reportOutcome(args, {
            catalog: deps.catalog,
            db: deps.db,
            now: deps.now,
            reporter: deps.reporter ?? 'external',
            client: deps.client,
          }),
        );
      } catch (err) {
        if (err instanceof UnknownToolError) return toolError(err.message);
        throw err;
      }
    },
  );

  server.registerTool(
    'submit_software',
    {
      title: 'Submit a GitHub project to pickfit',
      description:
        'Use only when the user asks to add a software project to pickfit, often their own. Takes the GitHub repository URL. ' +
        "pickfit's pipeline reads it with Meta's Muse Spark, tries the install in a sandbox and lists it if it works; this takes minutes, so call again with the same url to check the status. " +
        'Developer CLI tools, local AI/LLM tools and MCP servers are verified today; other software may be rejected or listed unverified. Nothing is published under the user\'s name.',
      inputSchema: submitInput,
      outputSchema: submitOutput,
      annotations: { readOnlyHint: false, destructiveHint: false, idempotentHint: true, openWorldHint: true },
    },
    async (args) => {
      try {
        return result(
          await submitSoftware(args, {
            catalog: deps.catalog,
            db: deps.db,
            now: deps.now,
            hourlyCap: deps.settings.submitHourlyCap,
            client: deps.client,
          }),
        );
      } catch (err) {
        if (err instanceof SubmitError) return toolError(err.message);
        throw err;
      }
    },
  );

  return server;
}
