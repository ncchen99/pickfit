// Spike: minimal stateless Streamable HTTP MCP server for pickfit.
// Uses the official MCP TypeScript SDK v2 (@modelcontextprotocol/server).
// The same `handler` is a Cloudflare Workers default export ({ fetch }).
// Data below is FAKE and hard-coded; it is not real software.
import { createMcpHandler, McpServer } from '@modelcontextprotocol/server';
import * as z from 'zod/v4';

const FAKE = [
  {
    slug: 'demo-local-llm-runner',
    name: 'Demo Local LLM Runner',
    summary: 'FAKE entry for the spike. Runs a small model offline.',
    repo: 'https://example.invalid/demo-local-llm-runner',
    platforms: ['macos', 'linux'],
    pricing: 'free',
    processing: 'local',
    verification: { status: 'passed', checked_at: '2026-10-28T00:00:00Z', os: 'linux' },
    scores: { quality: 0.82, popularity: 0.07 }
  },
  {
    slug: 'demo-json-cli',
    name: 'Demo JSON CLI',
    summary: 'FAKE entry for the spike. Pretty-prints and queries JSON.',
    repo: 'https://example.invalid/demo-json-cli',
    platforms: ['macos', 'linux', 'windows'],
    pricing: 'free',
    processing: 'local',
    verification: { status: 'unverified', checked_at: null, os: null },
    scores: { quality: 0.61, popularity: 0.12 }
  }
];

const Pick = z.object({
  slug: z.string(),
  name: z.string(),
  why: z.string(),
  repo: z.string(),
  platforms: z.array(z.enum(['macos', 'linux', 'windows'])),
  pricing: z.enum(['free', 'freemium', 'paid', 'unknown']),
  processing: z.enum(['local', 'cloud', 'hybrid', 'unknown']),
  verification: z.object({
    status: z.enum(['passed', 'failed', 'unverified']),
    checked_at: z.string().nullable(),
    os: z.string().nullable()
  }),
  scores: z.object({ quality: z.number(), popularity: z.number() })
});

function buildServer({ era } = {}) {
  const server = new McpServer(
    { name: 'pickfit-spike', version: '0.0.1' },
    {
      instructions:
        'pickfit finds lesser-known but verified software (developer CLI tools, local AI/LLM tools). ' +
        'Call find_software when the user wants a tool for a task. Ask at most one or two questions first (OS, budget, must run offline).'
    }
  );

  server.registerTool(
    'find_software',
    {
      title: 'Find software (spike)',
      description:
        'Recommend 2-3 lesser-known, sandbox-verified tools for a task. SPIKE: returns hard-coded fake data.',
      inputSchema: z.object({
        need: z.string().min(3).max(500).describe("The user's task in their own words"),
        os: z.enum(['macos', 'linux', 'windows']).optional(),
        budget: z.enum(['free', 'any']).optional(),
        offline_required: z.boolean().optional()
      }),
      outputSchema: z.object({
        picks: z.array(Pick),
        best_free_slug: z.string().nullable(),
        era: z.string()
      }),
      annotations: { readOnlyHint: true, openWorldHint: false }
    },
    async ({ need, os, offline_required }) => {
      const picks = FAKE.filter(s => (!os || s.platforms.includes(os)) && (!offline_required || s.processing === 'local')).map(
        ({ summary, ...rest }) => ({ ...rest, why: `${summary} Matches "${need}".` })
      );
      const out = { picks, best_free_slug: picks.find(p => p.pricing === 'free')?.slug ?? null, era: era ?? 'unknown' };
      return { content: [{ type: 'text', text: JSON.stringify(out) }], structuredContent: out };
    }
  );

  return server;
}

export const handler = createMcpHandler(buildServer);
export default handler;
