/**
 * The Worker's Cloudflare bindings, reached from Cloud Run over HTTP:
 * D1 through the Cloudflare REST API, R2 through its S3-compatible API.
 * Only what src/ uses is here: D1 prepare/bind/first/all/run, R2 head/get with a range and conditions.
 */
import { AwsClient } from 'aws4fetch';

type Value = string | number | boolean | null;

interface D1Result<T> {
  results: T[];
  success: boolean;
  meta: { changes: number; last_row_id: number; duration: number; [k: string]: unknown };
}

export interface D1Options {
  accountId: string;
  databaseId: string;
  token: string;
  fetch?: typeof fetch;
}

/** A D1Database whose statements are sent to POST /accounts/:a/d1/database/:d/query. */
export function remoteD1(options: D1Options) {
  const doFetch = options.fetch ?? fetch;
  const url = `https://api.cloudflare.com/client/v4/accounts/${options.accountId}/d1/database/${options.databaseId}/query`;

  async function query<T>(sql: string, params: Value[]): Promise<D1Result<T>> {
    const response = await doFetch(url, {
      method: 'POST',
      headers: { authorization: `Bearer ${options.token}`, 'content-type': 'application/json' },
      body: JSON.stringify({ sql, params }),
    });
    const body = (await response.json().catch(() => null)) as
      | { success?: boolean; errors?: { message?: string }[]; result?: D1Result<T>[] }
      | null;
    if (!response.ok || !body?.success || !body.result?.[0]) {
      const message = body?.errors?.map((e) => e.message).join('; ') || `HTTP ${response.status}`;
      throw new Error(`D1_ERROR: ${message}`);
    }
    const result = body.result[0];
    return {
      results: result.results ?? [],
      success: true,
      meta: { ...{ changes: 0, last_row_id: 0, duration: 0 }, ...result.meta },
    };
  }

  class Statement {
    readonly sql: string;
    readonly params: Value[];
    constructor(sql: string, params: Value[] = []) {
      this.sql = sql;
      this.params = params;
    }
    bind(...values: unknown[]): Statement {
      return new Statement(this.sql, values.map((v) => (v === undefined ? null : (v as Value))));
    }
    async all<T = Record<string, unknown>>(): Promise<D1Result<T>> {
      return query<T>(this.sql, this.params);
    }
    async run<T = Record<string, unknown>>(): Promise<D1Result<T>> {
      return query<T>(this.sql, this.params);
    }
    async first<T = Record<string, unknown>>(column?: string): Promise<T | null> {
      const { results } = await query<Record<string, unknown>>(this.sql, this.params);
      const row = results[0];
      if (!row) return null;
      return (column ? row[column] : row) as T;
    }
    async raw<T = unknown[]>(): Promise<T[]> {
      const { results } = await query<Record<string, unknown>>(this.sql, this.params);
      return results.map((row) => Object.values(row)) as T[];
    }
  }

  return {
    prepare: (sql: string) => new Statement(sql),
    async batch(statements: Statement[]) {
      const out = [];
      for (const s of statements) out.push(await s.run());
      return out;
    },
    async exec(sql: string) {
      await query(sql, []);
      return { count: 1, duration: 0 };
    },
  };
}

export interface R2Options {
  accountId: string;
  bucket: string;
  /** S3 credentials: an R2 API token's id, and the SHA-256 of its value. */
  accessKeyId: string;
  secretAccessKey: string;
}

const PASSED = ['range', 'if-none-match', 'if-modified-since', 'if-match', 'if-unmodified-since'];

/** The bucket's objects through https://<account>.r2.cloudflarestorage.com/<bucket>/<key>. */
export function remoteR2(options: R2Options) {
  const client = new AwsClient({
    accessKeyId: options.accessKeyId,
    secretAccessKey: options.secretAccessKey,
    service: 's3',
    region: 'auto',
  });
  const base = `https://${options.accountId}.r2.cloudflarestorage.com/${options.bucket}/`;
  const objectUrl = (key: string) => base + key.split('/').map(encodeURIComponent).join('/');

  function describe(key: string, response: Response) {
    const contentRange = response.headers.get('content-range');
    const whole = contentRange ? /\/(\d+)$/.exec(contentRange) : null;
    const size = whole ? Number(whole[1]) : Number(response.headers.get('content-length') ?? 0);
    const etag = response.headers.get('etag') ?? '';
    const lastModified = response.headers.get('last-modified');
    const part = contentRange ? /bytes (\d+)-(\d+)\//.exec(contentRange) : null;
    return {
      key,
      size,
      etag: etag.replace(/"/g, ''),
      httpEtag: etag,
      uploaded: lastModified ? new Date(lastModified) : new Date(0),
      range: part ? { offset: Number(part[1]), length: Number(part[2]) - Number(part[1]) + 1 } : undefined,
    };
  }

  return {
    async head(key: string) {
      const response = await client.fetch(objectUrl(key), { method: 'HEAD' });
      if (response.status === 404) return null;
      if (!response.ok) throw new Error(`R2 HEAD ${response.status}`);
      return describe(key, response);
    },
    async get(key: string, opts: { range?: Headers; onlyIf?: Headers } = {}) {
      const headers = new Headers();
      for (const name of PASSED) {
        const value = opts.range?.get(name) ?? opts.onlyIf?.get(name);
        if (value) headers.set(name, value);
      }
      const response = await client.fetch(objectUrl(key), { method: 'GET', headers });
      if (response.status === 404) {
        await response.body?.cancel();
        return null;
      }
      if (response.status === 416) {
        await response.body?.cancel();
        throw new Error('R2 range not satisfiable');
      }
      if (response.status === 304 || response.status === 412) {
        await response.body?.cancel();
        // R2's own get() returns the object without a body when a condition fails.
        const head = await this.head(key);
        return head;
      }
      if (!response.ok) {
        await response.body?.cancel();
        throw new Error(`R2 GET ${response.status}`);
      }
      return { ...describe(key, response), body: response.body };
    },
  };
}
