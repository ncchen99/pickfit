/** --model-id for a paid bench run: which model the match and keyword calls use. Default MATCH_MODEL; only a model
 * with a price in MODEL_PRICES, so the run's --cap counts its spend at the right price. */
import { MATCH_MODEL, MODEL_PRICES } from '../src/meta.ts';

export function modelArg(args: string[]): string {
  const at = args.indexOf('--model-id');
  if (at < 0) return MATCH_MODEL;
  const model = args[at + 1];
  if (!model || model.startsWith('--')) throw new Error('--model-id needs a model id, e.g. --model-id claude-sonnet-5-5');
  if (!MODEL_PRICES[model]) throw new Error(`--model-id ${model}: no price for it in src/meta.ts MODEL_PRICES (${Object.keys(MODEL_PRICES).join(', ')})`);
  return model;
}
