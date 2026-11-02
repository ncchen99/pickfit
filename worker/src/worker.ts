/** HTTP front: /mcp with DNS-rebinding protection (Host and Origin allowlists), and the web page (web.ts). */
import { createMcpHandler, localhostAllowedHostnames, validateHostHeader, validateOriginHeader } from '@modelcontextprotocol/server';
import { loadCatalog } from './catalog.ts';
import { settings, type Env } from './env.ts';
import { reporterFrom } from './events.ts';
import type { Translations } from './i18n.ts';
import { buildServer } from './server.ts';
import { serveVideo } from './video.ts';
import { makeWeb } from './web.ts';

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
  /** The web page's zh-TW sentences per tool (generated/zh-TW.json). */
  translations?: Translations;
}

export function makeWorker(indexData: unknown, options: WorkerOptions = {}) {
  const catalog = loadCatalog(indexData);
  const web = makeWeb(catalog, options);
  return {
    async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
      const url = new URL(request.url);
      const video = await serveVideo(request, env.VIDEOS, catalog);
      if (video) return video;
      if (url.pathname !== '/mcp') {
        const page = await web.fetch(request, env, ctx, allowedHosts(env));
        if (page) return page;
        if (url.pathname === '/' && request.method === 'GET') {
          // What this deployment serves, so two deployments can be checked for the same data.
          const config = settings(env);
          return Response.json({
            name: 'pickfit',
            mcp: '/mcp',
            entries: catalog.count,
            index_built_at: catalog.built_at,
            data_sha256: catalog.data_sha256 ?? null,
            tools: config.tools,
            match_mode: config.modelEnabled ? 'model' : 'off',
          }, { headers: { vary: 'Accept' } }); // browsers get the page here (web.ts)
        }
        return new Response('Not found', { status: 404 });
      }
      const hosts = allowedHosts(env);
      const host = validateHostHeader(request.headers.get('host') ?? url.host, hosts);
      if (!host.ok) return forbidden(host.message);
      const origin = validateOriginHeader(request.headers.get('origin'), hosts);
      if (!origin.ok) return forbidden(origin.message);

      const config = settings(env);
      const handler = createMcpHandler(() =>
        buildServer({
          catalog,
          db: env.DB,
          settings: config,
          now: options.now ?? (() => new Date()),
          waitUntil: (promise) => ctx.waitUntil(promise),
          fetch: options.fetch,
          reporter: reporterFrom(request.headers.get('x-pickfit-reporter')),
          // Clip URLs only where this deployment can serve them.
          videoBase: env.VIDEOS ? url.origin : null,
        }),
      );
      // Every call is matched anew; tell any cache on the way not to keep a response.
      const response = await handler.fetch(request);
      const uncached = new Response(response.body, response);
      uncached.headers.set('cache-control', 'no-store');
      return uncached;
    },
  };
}
