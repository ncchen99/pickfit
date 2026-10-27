// Local runner: mount the Workers-style handler on node:http (127.0.0.1 only).
import { createServer } from 'node:http';
import { toNodeHandler, localhostHostValidation, localhostOriginValidation } from '@modelcontextprotocol/node';
import { handler } from './worker.mjs';

const port = Number(process.env.PORT ?? 8787);
const nodeHandler = toNodeHandler(handler);
const validateHost = localhostHostValidation();
const validateOrigin = localhostOriginValidation();

createServer((req, res) => {
  if (!validateHost(req, res) || !validateOrigin(req, res)) return;
  void nodeHandler(req, res);
}).listen(port, '127.0.0.1', () => console.error(`pickfit spike MCP on http://127.0.0.1:${port}/mcp`));
