// The bundled index is built by scripts/build_index.py (npm run build:index), with the web page's zh-TW sentences beside it.
import indexData from './generated/index.json' with { type: 'json' };
import translations from './generated/zh-TW.json' with { type: 'json' };
import { makeWorker } from './worker.ts';

export default makeWorker(indexData, { translations }) satisfies ExportedHandler<import('./env.ts').Env>;
