"""`pickfit verify`: run the verification agent on one fixture in a local DockerBox."""

from __future__ import annotations

import argparse

LIFETIME_MARGIN_S = 120  # the box outlives the agent's time limit, so the last turn still has it


def add_parser(sub: argparse._SubParsersAction) -> None:
    v = sub.add_parser("verify", help="install and smoke-test one tool in a local Docker box with Muse Spark")
    v.add_argument("--fixture", required=True,
                   help="JSON with slug, repo_url, readme_url and an ExtractionResult")
    v.add_argument("--model", default=None, help='"dev", "prod", or a model id (default: PICKFIT_MODE)')
    v.add_argument("--mode", choices=["chain", "replay"], default=None,
                   help="carry history by previous_response_id (chain) or resend it (replay)")
    v.add_argument("--max-turns", type=int, default=None, help="turn limit (default 25)")
    v.add_argument("--platform", default="linux/amd64", help="container platform (Modal runs x86_64)")
    v.add_argument("--keep-box", action="store_true", help="leave the container running for debugging")
    v.set_defaults(func=run)


def run(args: argparse.Namespace) -> int:
    from dataclasses import replace

    from pickfit.schema import is_passed
    from pickfit.verify.agent import DEFAULT_MODE, AgentLimits, VerifyAgent, new_run_id
    from pickfit.verify.box import BoxLimits, DockerBox
    from pickfit.verify.task import load_fixture

    task = load_fixture(args.fixture)
    limits = AgentLimits()
    if args.max_turns:
        limits = replace(limits, max_turns=args.max_turns)
    run_id = new_run_id(task.slug)
    box = DockerBox(platform=args.platform, labels={"pickfit.run": run_id},
                    limits=BoxLimits(lifetime_s=int(limits.max_seconds) + LIFETIME_MARGIN_S))
    try:
        box.start()
        report = VerifyAgent(task, box, model=args.model, mode=args.mode or DEFAULT_MODE,
                             limits=limits, run_id=run_id).run()
    finally:
        if args.keep_box:
            print(f"box kept: docker exec -it {box.name} bash  (remove: docker rm -f {box.name})")
        else:
            box.close()
    level = report.check["level"] if report.check else None
    return 0 if level and is_passed(level) else 1
