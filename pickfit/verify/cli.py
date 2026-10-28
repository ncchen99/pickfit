"""`pickfit verify`: agent, replay and judge for one fixture, in Docker or on Modal."""

from __future__ import annotations

import argparse
import json

LIFETIME_MARGIN_S = 120  # the box outlives the agent's time limit, so the last turn still has it


def add_parser(sub: argparse._SubParsersAction) -> None:
    v = sub.add_parser("verify", help="install, smoke-test, replay and judge one tool in a sandbox with Muse Spark")
    v.add_argument("--fixture", help="JSON with slug, repo_url, readme_url and an ExtractionResult")
    v.add_argument("--runner", choices=["docker", "modal"], default="docker",
                   help="local DockerBox (development) or ModalBox (gVisor on Modal)")
    v.add_argument("--model", default=None, help='"dev", "prod", or a model id (default: PICKFIT_MODE)')
    v.add_argument("--mode", choices=["chain", "replay"], default=None,
                   help="carry history by previous_response_id (chain) or resend it (replay)")
    v.add_argument("--max-turns", type=int, default=None, help="turn limit (default 25)")
    v.add_argument("--platform", default="linux/amd64", help="Docker platform (Modal runs x86_64)")
    v.add_argument("--keep-box", action="store_true", help="Docker: leave the agent's container running")
    v.add_argument("--write-back", action="store_true",
                   help="record a passed, replayed run in data/software/<slug>.json")
    v.add_argument("--limits-test", action="store_true",
                   help="no model: check the box's limits (user, metadata, network cut, memory, disk, pids)")
    v.set_defaults(func=run)


def box_factory(runner: str, lifetime_s: int, *, platform: str = "linux/amd64"):
    """(run_id, role) -> an unstarted box of the chosen runner."""
    from pickfit.verify.box import BoxLimits, DockerBox

    if runner == "modal":
        from pickfit.verify.modal_box import ModalBox

        return lambda run_id, role: ModalBox(tags={"pickfit.run": run_id, "pickfit.role": role},
                                             limits=BoxLimits(lifetime_s=lifetime_s))
    return lambda run_id, role: DockerBox(platform=platform, labels={"pickfit.run": run_id, "pickfit.role": role},
                                          limits=BoxLimits(lifetime_s=lifetime_s))


def run(args: argparse.Namespace) -> int:
    from dataclasses import replace

    from pickfit.verify.agent import DEFAULT_MODE, AgentLimits
    from pickfit.verify.pipeline import verify_task
    from pickfit.verify.task import load_fixture

    if args.limits_test:
        from pickfit.verify.agent import _runs_dir
        from pickfit.verify.limits import limits_test

        results, _ = limits_test(box_factory(args.runner, 900, platform=args.platform), _runs_dir(None))
        return 0 if all(r.ok for r in results) else 1
    if not args.fixture:
        print("pickfit verify: give --fixture")
        return 2
    limits = AgentLimits()
    if args.max_turns:
        limits = replace(limits, max_turns=args.max_turns)
    make_box = box_factory(args.runner, int(limits.max_seconds) + LIFETIME_MARGIN_S, platform=args.platform)
    outcome = verify_task(load_fixture(args.fixture), make_box, model=args.model, mode=args.mode or DEFAULT_MODE,
                          limits=limits, write=args.write_back, keep_agent_box=args.keep_box)
    print(json.dumps(outcome.summary(), ensure_ascii=False, indent=2))
    return 0 if outcome.passed else 1
