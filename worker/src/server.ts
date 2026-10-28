/** MCP tool definitions: one fresh McpServer per HTTP request (stateless). */
import { McpServer } from '@modelcontextprotocol/server';
import * as z from 'zod/v4';
import { CARD_FIELDS } from './cards.ts';
import { findSoftware, type Deps } from './find.ts';
import { installGuide, UnknownSlugError } from './install.ts';
import { logEvent } from './events.ts';

export const INSTRUCTIONS =
  'pickfit recommends lesser-known software that it has installed and tested in a sandbox. Scope today: developer CLI tools and local AI/LLM tools. ' +
  'Flow: find_software -> user picks -> get_install_guide -> run steps with the user\'s consent -> report_outcome. ' +
  'Ask at most 1-2 questions first (OS; must be free/offline). No ads or affiliate links; ranking is fit, not stars.';

const os = z.enum(['macos', 'linux', 'windows']);
const arch = z.enum(['arm64', 'x86_64']);
const slug = z.string().regex(/^[a-z0-9]+(?:-[a-z0-9]+)*$/).max(64);
const recId = z.string().max(200);

const reason = z.object({
  claim: z.string(),
  field: z.enum(CARD_FIELDS),
  value: z.string(),
});

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
    verified_on_user_os: z.boolean().nullable(),
  }),
  how_we_know: z.string(),
  evidence_url: z.string().nullable(),
  scores: z.object({
    quality: z.number().nullable().describe('0-100'),
    popularity: z.number().nullable().describe('0-100; scored separately from quality'),
    treasure: z.boolean().describe('High quality, low popularity'),
  }),
  repo: z.string(),
  homepage: z.string().nullable(),
});

const findInput = z.object({
  need: z
    .string()
    .min(3)
    .max(500)
    .describe("The job to get done, in the user's words. Describe the task, not a product name."),
  category: z.enum(['dev_cli', 'local_ai', 'any']).optional().describe('Default any'),
  os: os.optional(),
  arch: arch.optional(),
  budget: z.enum(['free_only', 'free_or_paid']).optional(),
  must_run_locally: z.boolean().optional().describe('true = must work offline; no data leaves the machine'),
  ui_language: z.string().max(35).optional().describe('BCP 47 tag, only if the user needs the UI or docs in that language'),
  exclude: z.array(slug).max(20).optional().describe('Slugs already shown or rejected'),
  limit: z.number().int().min(1).max(3).optional().describe('Default 3'),
});

const findOutput = z.object({
  rec_id: z.string().describe('Pass to get_install_guide and report_outcome; valid 7 days'),
  matched_by: z.string().describe('The Meta model that chose the picks, or "rules"'),
  degraded: z.boolean().describe('true = ranked by rules without the model (off, budget or failure)'),
  degraded_reason: z.string().nullable(),
  considered: z.number().int().describe('Verified tools that met the hard conditions'),
  picks: z.array(pick).max(3),
  best_free: z.object({ slug: z.string(), reason: z.string() }).nullable(),
  no_install_option: z.string().nullable(),
  clarifying_question: z.string().nullable(),
  coverage_note: z.string().nullable(),
});

const installInput = z.object({
  slug,
  os,
  arch: arch.optional(),
  rec_id: recId.optional(),
});

const installOutput = z.object({
  slug: z.string(),
  name: z.string(),
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
  known_issues: z.array(z.object({ readme_said: z.string(), actually_needed: z.string() })),
  warnings: z.array(z.string()),
  sources: z.array(z.string()),
});

function result(out: object) {
  return {
    content: [{ type: 'text' as const, text: JSON.stringify(out) }],
    structuredContent: out as Record<string, unknown>,
  };
}

export function buildServer(deps: Deps): McpServer {
  const server = new McpServer({ name: 'pickfit', version: '0.1.0' }, { instructions: INSTRUCTIONS });

  server.registerTool(
    'find_software',
    {
      title: 'Find software',
      description:
        'Use when the user wants a tool for a job and has not settled on a product (e.g. "a free offline CLI to transcribe audio on my Mac"). ' +
        'Before calling, ask at most one or two questions, and only if unknown: which OS, and whether it must be free or run fully offline. ' +
        'Returns up to 3 lesser-known tools whose install pickfit actually ran, ranked by fit (not popularity), each with reasons tied to its verified profile, trade-offs, verification evidence and separate quality/popularity scores, plus the best free option. ' +
        'If clarifying_question is set, ask it and call again. Next: get_install_guide(slug, os, rec_id). Coverage: developer CLI tools and local AI/LLM tools.',
      inputSchema: findInput,
      outputSchema: findOutput,
      annotations: { readOnlyHint: true, openWorldHint: false },
    },
    async (args) => result(await findSoftware(args, deps)),
  );

  server.registerTool(
    'get_install_guide',
    {
      title: 'Get a verified install guide',
      description:
        'Use after the user picks a tool from find_software. Returns install steps pickfit actually ran (replayed in a fresh sandbox, or done by hand), with the OS, date and evidence, ' +
        'the steps only the user can do (permissions, accounts), a command to verify the install and a first task to try. ' +
        'Show each command to the user before running it, and ask before any step that needs sudo or pipes a script into a shell. ' +
        'If applies_to_user_system.match is not "exact", tell the user the steps were checked on a different system. After the user tries it, call report_outcome.',
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
            rec_id: args.rec_id ?? null,
            results: [out.applies_to_user_system.match],
          }).catch(() => undefined),
        );
        return result(out);
      } catch (err) {
        if (err instanceof UnknownSlugError) {
          return { content: [{ type: 'text' as const, text: err.message }], isError: true };
        }
        throw err;
      }
    },
  );

  return server;
}
