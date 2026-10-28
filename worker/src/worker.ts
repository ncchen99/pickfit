/** HTTP front: /mcp only, with DNS-rebinding protection (Host and Origin allowlists). */
import { createMcpHandler, localhostAllowedHostnames, validateHostHeader, validateOriginHeader } from '@modelcontextprotocol/server';
import { loadCatalog } from './catalog.ts';
import { settings, type Env } from './env.ts';
import { buildServer } from './server.ts';

function allowedHosts(env: Env): string[] {
  const extra = (env.ALLOWED_HOSTS ?? '')
    .split(',')
    .map((host) => host.trim().toLowerCase())
    .filter(Boolean);
  return [...localhostAllowedHostnames(), ...extra];
}

function forbidden(message: string): Response {
  return Response.json({ jsonrpc: '2.0', id: null, error: { code: -32000, message } }, { status: 403 });
}

export interface WorkerOptions {
  /** Test hook: replaces global fetch for the Meta call. */
  fetch?: typeof fetch;
  now?: () => Date;
}

export function makeWorker(indexData: unknown, options: WorkerOptions = {}) {
  const catalog = loadCatalog(indexData);
  return {
    async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
      const url = new URL(request.url);
      if (url.pathname !== '/mcp') {
        if (url.pathname === '/' && request.method === 'GET') {
          return Response.json({ name: 'pickfit', mcp: '/mcp', entries: catalog.count, index_built_at: catalog.built_at });
        }
        return new Response('Not found', { status: 404 });
      }
      const hosts = allowedHosts(env);
      const host = validateHostHeader(request.headers.get('host') ?? url.host, hosts);
      if (!host.ok) return forbidden(host.message);
      const origin = validateOriginHeader(request.headers.get('origin'), hosts);
      if (!origin.ok) return forbidden(origin.message);

      const handler = createMcpHandler(() =>
        buildServer({
          catalog,
          db: env.DB,
          settings: settings(env),
          now: options.now ?? (() => new Date()),
          waitUntil: (promise) => ctx.waitUntil(promise),
          fetch: options.fetch,
        }),
      );
      return handler.fetch(request);
    },
  };
}
