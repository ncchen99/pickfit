// The bundled index is built by scripts/build_index.py (npm run build:index).
import indexData from './generated/index.json' with { type: 'json' };
import { makeWorker } from './worker.ts';

export default makeWorker(indexData) satisfies ExportedHandler<import('./env.ts').Env>;
