"""`pickfit score-batch`: score records with the docs rubric graded through the Message Batches API (half price).

The rubric does not have to come back at once: nothing waits on it but the record's install_docs part. So this
runs pickfit.score.score_records twice through its `grade` seam, with no change to pickfit/score.py (a guarded file):

1. collect: every record scores as usual; one that needs a new rubric (its README changed, --force, --regrade-*)
   hands its request to this module instead of calling the model, and is left unwritten (the deferral reads as a
   per-record error, which score_records already leaves the file alone for);
2. one Message Batch with score.rubric_body for each of them (pickfit.msg_batch: half the price, usually within the
   hour; a request the batch did not answer goes to the plain API, unless --no-resend);
3. write: those records score again, the rubric read from the batch answer (score.rubric_from_items, as the plain
   call does).

--dry-run stops after step 1 and says how many rubrics a batch would hold and roughly what they would cost.
"""

from __future__ import annotations

import argparse
import json
import sys
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

STAGE_NOTE = "score-batch"
# A rubric call's mean cost on the watch (US$2.87 over 70 calls, 11/18-20); a batch is charged half of it.
MEAN_RUBRIC_USD = 0.041


class Deferred(RuntimeError):
    """A rubric left to the batch: score_records records it as an error and writes nothing for the record."""


@dataclass
class Pending:
    sources: list[Any]
    input_sha: str | None


@dataclass
class BatchScore:
    collected: dict[str, Pending] = field(default_factory=dict)  # scope -> request
    first: Any = None  # ScoreSummary of the collect pass
    second: Any = None  # ScoreSummary of the write pass
    outcomes: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"rubrics_batched": len(self.collected),
                               "estimated_batch_usd": round(len(self.collected) * MEAN_RUBRIC_USD / 2, 2)}
        if self.first is not None:
            first = self.first.to_dict()
            out["first_pass"] = {"written": first["written"], "unchanged": first["unchanged"],
                                 "errors": {k: v for k, v in (first.get("errors") or {}).items()
                                            if not str(v).startswith("Deferred")}}
        if self.outcomes:
            out["batch"] = {"answered": sum(1 for o in self.outcomes.values() if o.result is not None),
                            "via": _count(o.via for o in self.outcomes.values()),
                            "cost_usd": round(sum(o.result.cost_usd for o in self.outcomes.values()
                                                  if o.result is not None), 4)}
        if self.second is not None:
            second = self.second.to_dict()
            out["second_pass"] = {"written": second["written"], "unchanged": second["unchanged"],
                                  "errors": second.get("errors") or {}, "rubric_cost_usd": second["cost_usd"]}
        return out


def _count(items: Any) -> dict[str, int]:
    out: dict[str, int] = {}
    for item in items:
        out[item] = out.get(item, 0) + 1
    return out


def collector(into: dict[str, Pending]) -> Callable[..., Any]:
    """A `grade` for score_records that keeps the request and defers it. Thread-safe (records score in a pool)."""
    lock = threading.Lock()

    def grade(sources: list[Any], *, scope: str, input_sha: str | None = None, **_: Any) -> Any:
        with lock:
            into[scope] = Pending(list(sources), input_sha)
        raise Deferred("rubric deferred to the message batch")

    return grade


def batch_requests(pending: dict[str, Pending], model: str) -> list[Any]:
    """One msg_batch request per deferred rubric: score.rubric_body, the same request as the plain call's."""
    from pickfit import msg_batch, score
    from pickfit.schema import DocsRubricItems

    return [msg_batch.BatchRequest(key=scope, endpoint="responses", body=score.rubric_body(p.sources),
                                   stage=score.STAGE, max_output_tokens=score.MAX_OUTPUT_TOKENS, model=model,
                                   reasoning_effort=score.REASONING_EFFORT, output_model=DocsRubricItems,
                                   scope=scope, scope_cap_usd=score.SCOPE_CAP_USD)
            for scope, p in sorted(pending.items())]


def reader(outcomes: dict[str, Any]) -> Callable[..., Any]:
    """A `grade` for score_records that answers from the batch: a Graded as score.grade_docs would return it."""
    from pickfit import score

    def grade(sources: list[Any], *, scope: str, now: datetime, input_sha: str | None = None, **_: Any) -> Any:
        outcome = outcomes.get(scope)
        if outcome is None or outcome.result is None:
            return score.Graded(None, error=(outcome.error if outcome else None) or "no answer in the batch")
        meta = outcome.result
        if meta.parsed is None:
            return score.Graded(None, cost_usd=meta.cost_usd, error=f"no rubric: {meta.status} {meta.parse_error}")
        rubric = score.rubric_from_items(meta.parsed, sources, model=meta.model, now=now, input_sha=input_sha)
        return score.Graded(rubric, cost_usd=meta.cost_usd)

    return grade


def score_with_batch(data_dir: Path, *, db_path: Path | None, model: str, dry_run: bool = False,
                     run_id: str | None = None, batch_options: dict[str, Any] | None = None,
                     log: Callable[[str], None] | None = None, **score_kwargs: Any) -> BatchScore:
    """The three steps above. score_kwargs go to both score_records passes (slugs, force, use_github, ...)."""
    from pickfit import msg_batch
    from pickfit.score import score_records

    log = log or (lambda line: None)
    result = BatchScore()
    result.first = score_records(data_dir, db_path=db_path, model=model, dry_run=dry_run, log=log,
                                 grade=collector(result.collected), **score_kwargs)
    log(f"score-batch: {len(result.collected)} rubric(s) to grade in a batch")
    if dry_run or not result.collected:
        return result
    run_id = run_id or "score-batch-" + time.strftime("%Y%m%d-%H%M%S")
    result.outcomes = msg_batch.run(batch_requests(result.collected, model), run_id=run_id, log=log,
                                    **(batch_options or {}))
    slugs = sorted(scope.split(":", 1)[1] for scope in result.collected)
    kwargs = {k: v for k, v in score_kwargs.items() if k not in ("slugs", "limit")}
    result.second = score_records(data_dir, db_path=db_path, model=model, slugs=slugs, log=log,
                                  grade=reader(result.outcomes), **kwargs)
    return result


def add_parser(sub: argparse._SubParsersAction) -> None:
    from pickfit.score import DEFAULT_CONCURRENCY

    s = sub.add_parser("score-batch", help="pickfit score with the docs rubric graded in a Message Batch "
                                           "(half price, answers within about an hour)")
    s.add_argument("--slug", action="append", help="score only this record (repeatable; default all)")
    s.add_argument("--kind", default=None, help="score only records of this kind")
    s.add_argument("--limit", type=int, default=None, help="score at most N records (in slug order)")
    s.add_argument("--data-dir", default=None, help="records to score (default data/software)")
    s.add_argument("--db", default=None, help="pipeline database with the GitHub snapshots (default runs/pipeline.db)")
    s.add_argument("--model", default="prod", help='rubric model: "prod" (default), "dev" or a model id')
    s.add_argument("--force", action="store_true", help="grade the README again even if it has not changed")
    s.add_argument("--regrade-before", default=None, metavar="VERSION", help="as pickfit score")
    s.add_argument("--regrade-model", action="append", metavar="MODEL", help="as pickfit score")
    s.add_argument("--no-github", action="store_true", help="as pickfit score")
    s.add_argument("--no-registries", action="store_true", help="as pickfit score")
    s.add_argument("--concurrency", type=int, default=DEFAULT_CONCURRENCY, help="records at once")
    s.add_argument("--no-resend", action="store_true",
                   help="leave a request the batch did not answer unanswered instead of calling the plain API")
    s.add_argument("--dry-run", action="store_true",
                   help="score without writing and say how many rubrics a batch would hold and their cost; no call")
    s.set_defaults(func=main)


def main(args: Any) -> int:
    from pickfit.discover.github import GitHubError
    from pickfit.discover.run import pipeline_db_path
    from pickfit.meta import resolve_model
    from pickfit.profiles import DEFAULT_OUT

    started = time.monotonic()
    try:
        result = score_with_batch(
            Path(args.data_dir) if args.data_dir else DEFAULT_OUT,
            db_path=Path(args.db) if args.db else pipeline_db_path(), model=resolve_model(args.model),
            dry_run=args.dry_run, batch_options={"resend": not args.no_resend},
            log=lambda line: print(line, file=sys.stderr),
            slugs=args.slug, kind=args.kind, limit=args.limit, force=args.force,
            use_github=not args.no_github, use_registries=not args.no_registries, concurrency=args.concurrency,
            regrade_before=args.regrade_before, regrade_models=args.regrade_model or ())
    except GitHubError as err:
        print(f"pickfit score-batch: {err} (or pass --no-github)", file=sys.stderr)
        return 2
    out = result.to_dict()
    out["seconds"] = round(time.monotonic() - started, 1)
    print(json.dumps(out, ensure_ascii=False, indent=2))
    errors = (out.get("first_pass") or {}).get("errors") or (out.get("second_pass") or {}).get("errors")
    return 1 if errors else 0
