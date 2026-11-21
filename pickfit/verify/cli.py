"""`pickfit verify`: agent, replay and judge for a fixture or a batch, in Docker, on Modal or EC2, or in a macOS or
Windows VM."""

from __future__ import annotations

import argparse
import json

LIFETIME_MARGIN_S = 120  # the box outlives the agent's time limit, so the last turn still has it
MAC_GUI_AGENT_S = 45 * 60  # tart + display: room for a desktop app's long download (tart_box.GUI_COMMAND_S)
TART_MAX_VMS = 2  # Apple's limit on macOS VMs running at once on one Mac
# Display boxes: room for operate_gui (one per listed feature) after the install and the launch.
GUI_LIMITS = {"max_turns": 32, "max_commands": 20, "max_seconds": 35 * 60, "scope_cap_usd": 5.00}
VBOX_MAX_VMS = 1  # one Windows base, reset from its snapshot for every box
EC2_CONCURRENCY = 2  # a batch on EC2 by default: two boxes, and room in a new account's quota for a pool member
# The full-privilege VM box (root_box.py, ec2_root.py): --runner ec2 --runtime rootvm. One record at a time: a record
# needs an agent's VM and a replay's, and the lane may hold two instances (docs/proposals/aws.md, A3).
ROOT_VM = "rootvm"
ROOT_VM_CONCURRENCY = 1
TOOLCHAIN_AGENT_S = 45 * 60  # --toolchain: a build from source runs once for the agent and once in the replay


def add_parser(sub: argparse._SubParsersAction) -> None:
    from pickfit.schema import LISTED_CATEGORIES

    v = sub.add_parser("verify", help="install, smoke-test, replay and judge one tool in a sandbox with Claude")
    v.add_argument("--fixture", help="JSON with slug, repo_url, readme_url and an ExtractionResult")
    v.add_argument("--batch", type=int, metavar="N", help="verify N extracted candidates from the pipeline database")
    v.add_argument("--concurrency", type=int, default=None,
                   help=f"batch: tools verified at once (default 5; {EC2_CONCURRENCY} on EC2, where a new account's "
                        "quota holds about three boxes)")
    v.add_argument("--db", default=None, help="batch: pipeline database (default runs/pipeline.db), read-only")
    v.add_argument("--repo", action="append", help="batch: only this repo id (gh:<id>) or owner/name")
    v.add_argument("--records", action="store_true",
                   help="batch: only candidates that have a record in --data-dir (the profiles)")
    v.add_argument("--category", action="append", choices=LISTED_CATEGORIES,
                   help="batch: only this category (repeatable)")
    v.add_argument("--force", action="store_true", help="batch: also tools that already have a run")
    v.add_argument("--since", metavar="YYYYmmdd-HHMMSS",
                   help="batch: skip only tools with a run started at or after this Taipei time")
    v.add_argument("--data-dir", default=None,
                   help="records to take slugs from and write back to (default data/software)")
    v.add_argument("--dry-run", action="store_true", help="batch: list what would run and why others are skipped")
    v.add_argument("--runner", choices=["docker", "modal", "ec2", "ec2-windows", "tart", "vbox"], default="docker",
                   help="local DockerBox (development), ModalBox (gVisor on Modal), Ec2Box (a Linux VM on AWS EC2), "
                        "Ec2WindowsBox (Windows Server 2025 on AWS EC2), TartBox (macOS VM on this Mac) or VBoxBox "
                        "(Windows 11 VM in VirtualBox on this PC)")
    v.add_argument("--model", default=None,
                   help='agent model: "prod" (Claude Opus), "dev" or "open" (Claude Haiku) or a model id '
                        '(default: PICKFIT_MODE, else prod); the judges stay on the prod model when it is a cheaper tier')
    v.add_argument("--extraction-model", default=None,
                   help='batch: verify only extractions by this model ("prod", "open" or an id)')
    v.add_argument("--mode", choices=["chain", "replay"], default=None,
                   help="resend the history each turn (replay, the default) or carry it by previous_response_id "
                        "(chain: Meta's API only)")
    v.add_argument("--max-turns", type=int, default=None, help="turn limit (default 25)")
    v.add_argument("--max-operations", type=int, default=None,
                   help="--display: operate_gui calls per run (default 6); 0 checks install only")
    v.add_argument("--gpu", choices=["T4", "L4", "A10"], default=None,
                   help="Modal: give each box this NVIDIA GPU (for tools whose core job needs one)")
    v.add_argument("--runtime", choices=["gvisor", "vm", ROOT_VM], default="gvisor",
                   help="Modal: gVisor (default) or a microVM; a VM also drops DNS while the network is off. "
                        f"ec2: {ROOT_VM} is the full-privilege VM box, for software that needs root and systemd, "
                        "Docker or kernel modules: the box user has sudo on a whole throwaway VM and the limits are "
                        "outside it (one record at a time; run its --limits-test on a real instance first)")
    v.add_argument("--extra-disk-gb", type=int, default=0,
                   help=f"ec2 --runtime {ROOT_VM}: also attach a blank disk of this size, for partitioning and disk "
                        "tools to work on (deleted with the VM)")
    v.add_argument("--kvm", action="store_true",
                   help=f"ec2 --runtime {ROOT_VM}: launch with nested virtualization, so /dev/kvm is there")
    v.add_argument("--display", action="store_true",
                   help="Modal and ec2: a virtual display (Xvfb); tart: a desktop seen over VNC (the GUI base); "
                        "ec2-windows: the desktop seen over VNC (the display image). Adds "
                        "launch_gui and operate_gui, so GUI apps can be launched, operated and checked (with more "
                        "time and commands per app)")
    v.add_argument("--audio", action="store_true",
                   help="Modal: a simulated microphone (PulseAudio) and the listen tool: pickfit speaks fresh words "
                        "into it and checks them in what the tool produced")
    v.add_argument("--toolchain", action="store_true",
                   help="Modal: a build box, for a tool whose only install path here is a build from source: gcc, "
                        "g++, clang, make, cmake, Rust and Go in the image, 4 vCPU, 6 GiB and 30 minutes per command "
                        "(the agent gets 45 minutes). The box user is still not root")
    v.add_argument("--services", action="store_true",
                   help="Modal, EC2: PostgreSQL, Redis, MariaDB, an HTTP mock, a mail sink, an AWS emulator, a git "
                        "remote and a stand-in model endpoint the box user starts with pickfit-services, on 127.0.0.1 "
                        "only (verify/services.py)")
    v.add_argument("--apt", action="append", metavar="PACKAGE",
                   help="Linux boxes: pickfit's root installs this Debian package in every box of the run, from the "
                        "distribution's own repository (repeatable; verify/sysdeps.py). The box user is still not "
                        "root, and the install guide gains `sudo apt-get install -y ...` as its first step")
    v.add_argument("--memory-mb", type=int, default=None,
                   help="Modal: the box's memory (default 2048), for a model that needs more")
    v.add_argument("--file-mb", type=int, default=None,
                   help="Modal: the largest file the box user may write (default 1536), for model weights")
    v.add_argument("--platform", default="linux/amd64", help="Docker platform (Modal runs x86_64)")
    v.add_argument("--keep-box", action="store_true", help="Docker: leave the agent's container running")
    v.add_argument("--write-back", action="store_true",
                   help="record a passed, replayed run in data/software/<slug>.json")
    v.add_argument("--rejudge-features", action="store_true",
                   help="no box: run the feature judge on records' runs checked before it (from runs/verify evidence)")
    v.add_argument("--slug", action="append", help="--rejudge-features: only this record (repeatable)")
    v.add_argument("--limits-test", action="store_true",
                   help="no model: check the box's limits (user, metadata, network cut, memory, disk, pids)")
    v.add_argument("--prepare-base", action="store_true",
                   help="tart: build the base macOS VM the boxes clone (needs `tart pull` of the source image); "
                        "vbox: build the router VM and the Windows base (needs the ISOs in ~/.pickfit/vbox/iso); "
                        "ec2, ec2-windows: bake the image if the account lacks it and fill the pool of started-once "
                        "instances (PICKFIT_EC2_POOL, 0 for none)")
    v.add_argument("--iso", default=None, help="vbox --prepare-base: the Windows 11 Enterprise evaluation ISO")
    v.set_defaults(func=run)


def box_factory(runner: str, lifetime_s: int, *, platform: str = "linux/amd64", gpu: str | None = None,
                runtime: str = "gvisor", display: bool = False, audio: bool = False, memory_mb: int | None = None,
                file_mb: int | None = None, toolchain: bool = False, services: bool = False,
                extra_disk_gb: int = 0, kvm: bool = False):
    """(run_id, role) -> an unstarted box of the chosen runner. services: the databases and stand-in servers the
    box user can start (verify/services.py), Modal and EC2 only. runtime "rootvm" (EC2 only) is the full-privilege
    VM box; extra_disk_gb and kvm are its options."""
    from pickfit.verify.box import TOOLCHAIN_LIMITS, BoxLimits, DockerBox

    if runtime == ROOT_VM:
        if runner != "ec2":
            raise ValueError(f"--runtime {ROOT_VM} needs --runner ec2 (the one provider of a full-privilege VM so far)")
        if display or audio or toolchain or services or gpu or file_mb:
            raise ValueError(f"--runtime {ROOT_VM} takes none of --display, --audio, --toolchain, --services, --gpu "
                             "and --file-mb: the box user has root there and installs what the software needs")
        from pickfit.verify.ec2_root import Ec2RootBox

        size = {"memory_mb": memory_mb} if memory_mb else {}
        return lambda run_id, role: Ec2RootBox(tags={"pickfit.run": run_id, "pickfit.role": role},
                                               limits=BoxLimits(lifetime_s=lifetime_s, **size),
                                               extra_disk_gb=extra_disk_gb, kvm=kvm)
    if extra_disk_gb or kvm:
        raise ValueError(f"--extra-disk-gb and --kvm need --runner ec2 --runtime {ROOT_VM}")
    if runner not in ("modal", "ec2") and (runtime != "gvisor" or audio or memory_mb or file_mb or toolchain
                                           or services):
        raise ValueError("--runtime, --audio, --toolchain, --services, --memory-mb and --file-mb need --runner modal "
                         "or ec2")
    if display and runner not in ("modal", "ec2", "tart", "ec2-windows"):
        raise ValueError("--display needs --runner modal, ec2, ec2-windows or tart")
    sized = {k: v for k, v in (("memory_mb", memory_mb), ("home_mb", file_mb)) if v}
    if toolchain:  # room for a build; a size that was asked for wins
        sized = {**TOOLCHAIN_LIMITS, **sized}
    if runner == "tart":
        if gpu:
            raise ValueError("--gpu needs --runner modal")
        from pickfit.verify.tart_box import GUI_COMMAND_S, TartBox

        longer = {"max_command_s": GUI_COMMAND_S} if display else {}
        return lambda run_id, role: TartBox(limits=BoxLimits(lifetime_s=lifetime_s, **longer), display=display,
                                            tags={"pickfit.run": run_id, "pickfit.role": role})
    if runner == "vbox":
        if gpu:
            raise ValueError("--gpu needs --runner modal")
        from pickfit.verify.vbox_box import VBoxBox

        return lambda run_id, role: VBoxBox(limits=BoxLimits(lifetime_s=lifetime_s))
    if runner == "ec2-windows":
        if gpu:
            raise ValueError("--gpu needs --runner modal")
        from pickfit.verify.ec2_windows import Ec2WindowsBox

        return lambda run_id, role: Ec2WindowsBox(tags={"pickfit.run": run_id, "pickfit.role": role},
                                                  limits=BoxLimits(lifetime_s=lifetime_s), display=display)
    if runner == "ec2":  # always a VM, whatever --runtime says; no GPU types are listed yet
        if gpu:
            raise ValueError("--gpu needs --runner modal")
        from pickfit.verify.ec2_machine import Ec2Box

        return lambda run_id, role: Ec2Box(tags={"pickfit.run": run_id, "pickfit.role": role},
                                           limits=BoxLimits(lifetime_s=lifetime_s, **sized), display=display,
                                           audio=audio, toolchain=toolchain, services=services)
    if runner == "modal":
        from pickfit.verify.modal_box import ModalBox

        return lambda run_id, role: ModalBox(tags={"pickfit.run": run_id, "pickfit.role": role},
                                             limits=BoxLimits(lifetime_s=lifetime_s, **sized), gpu=gpu,
                                             runtime=runtime, display=display, audio=audio, toolchain=toolchain,
                                             services=services)
    if gpu:
        raise ValueError("--gpu needs --runner modal")
    return lambda run_id, role: DockerBox(platform=platform, labels={"pickfit.run": run_id, "pickfit.role": role},
                                          limits=BoxLimits(lifetime_s=lifetime_s))


def run(args: argparse.Namespace) -> int:
    from dataclasses import replace

    from pickfit.verify.agent import DEFAULT_MODE, AgentLimits
    from pickfit.verify.pipeline import verify_task
    from pickfit.verify.task import load_fixture

    if args.prepare_base:
        if args.runner == "vbox":
            from pathlib import Path

            from pickfit.verify.vbox_box import ROUTER_VM, VBox, prepare_base, prepare_router

            if VBox()("showvminfo", ROUTER_VM, check=False).returncode != 0:
                prepare_router()
            prepare_base(iso=Path(args.iso) if args.iso else None)
            return 0
        if args.runner in ("ec2", "ec2-windows"):
            root_vm = args.runner == "ec2" and args.runtime == ROOT_VM  # its own image and its own network
            box = box_factory(args.runner, 900, display=args.display and not root_vm,
                              runtime=ROOT_VM if root_vm else "gvisor",
                              audio=args.audio and args.runner == "ec2" and not root_vm,
                              toolchain=args.toolchain and args.runner == "ec2" and not root_vm)("prepare", "prepare")
            image = box.machine.prepare()
            print(f"pickfit verify: {args.runner} image {image.get('Name')} ({image['ImageId']}) is ready")
            return 0
        if args.runner != "tart":
            print("pickfit verify: --prepare-base needs --runner tart, vbox, ec2 or ec2-windows")
            return 2
        from pickfit.verify.tart_box import prepare_base, prepare_gui_base

        prepare_gui_base() if args.display else prepare_base()
        return 0
    if args.rejudge_features:
        return _rejudge(args)
    if (args.runtime != "gvisor" or args.audio or args.memory_mb or args.file_mb or args.toolchain
            or args.services) and args.runner not in ("modal", "ec2"):
        print("pickfit verify: --runtime, --audio, --toolchain, --services, --memory-mb and --file-mb need --runner "
              "modal or ec2")
        return 2
    if args.display and args.runner not in ("modal", "ec2", "tart", "ec2-windows"):
        print("pickfit verify: --display needs --runner modal, ec2, ec2-windows or tart")
        return 2
    root_vm = args.runtime == ROOT_VM
    if root_vm or args.extra_disk_gb or args.kvm:
        try:  # the same refusals the factory makes, before anything is started
            box_factory(args.runner, 900, gpu=args.gpu, runtime=args.runtime, display=args.display, audio=args.audio,
                        memory_mb=args.memory_mb, file_mb=args.file_mb, toolchain=args.toolchain,
                        services=args.services, extra_disk_gb=args.extra_disk_gb, kvm=args.kvm)
        except ValueError as err:
            print(f"pickfit verify: {err}")
            return 2
    if args.limits_test:
        from pickfit.verify.agent import _runs_dir
        from pickfit.verify.limits import limits_test

        if args.gpu and args.runner != "modal":
            print("pickfit verify: --gpu needs --runner modal")
            return 2
        if root_vm:
            # limits.py's probes check that the box user is held by root; here the box user is root, and the probes
            # are the ones of limits_root (until loop/proposals/limits-root-vm-hook.patch makes limits.py hand over).
            from pickfit.verify.limits_root import root_limits_test

            results, _ = root_limits_test(box_factory(args.runner, 1800, runtime=ROOT_VM, memory_mb=args.memory_mb,
                                                      extra_disk_gb=args.extra_disk_gb, kvm=args.kvm),
                                          _runs_dir(None))
            return 0 if all(r.ok for r in results) else 1
        if args.display and args.runner == "tart":
            # limits.py's display probes are Xvfb's (xdpyinfo, pgrep Xvfb) and can only fail in a macOS guest (11/18,
            # loop/issues.md H-014): limits_mac runs limits.py's other checks unchanged, then the macOS GUI box's own.
            from pickfit.verify.limits_mac import gui_limits_test

            results, _ = gui_limits_test(box_factory(args.runner, 900, display=True), _runs_dir(None))
            return 0 if all(r.ok for r in results) else 1
        results, _ = limits_test(box_factory(args.runner, 900, platform=args.platform, gpu=args.gpu,
                                             runtime=args.runtime, display=args.display, audio=args.audio,
                                             memory_mb=args.memory_mb, file_mb=args.file_mb,
                                             toolchain=args.toolchain, services=args.services), _runs_dir(None))
        return 0 if all(r.ok for r in results) else 1
    if not args.fixture and not args.batch:
        print("pickfit verify: give --fixture or --batch N")
        return 2
    limits = AgentLimits()
    if args.display:  # a GUI app also gets one operation per listed feature, each a few minutes of model turns
        limits = replace(limits, **GUI_LIMITS)
    if args.max_turns:
        limits = replace(limits, max_turns=args.max_turns)
    if args.max_operations is not None:
        limits = replace(limits, max_operations=max(0, args.max_operations))
    if args.gpu and args.runner != "modal":
        print("pickfit verify: --gpu needs --runner modal")
        return 2
    if args.runner == "tart" and args.display:
        limits = replace(limits, max_seconds=max(limits.max_seconds, MAC_GUI_AGENT_S))
    if args.toolchain:
        limits = replace(limits, max_seconds=max(limits.max_seconds, TOOLCHAIN_AGENT_S))
    make_box = box_factory(args.runner, int(limits.max_seconds) + LIFETIME_MARGIN_S, platform=args.platform,
                           gpu=args.gpu, runtime=args.runtime, display=args.display, audio=args.audio,
                           memory_mb=args.memory_mb, file_mb=args.file_mb, toolchain=args.toolchain,
                           services=args.services, extra_disk_gb=args.extra_disk_gb, kvm=args.kvm)
    if args.batch:
        if args.concurrency is None:
            args.concurrency = EC2_CONCURRENCY if args.runner in ("ec2", "ec2-windows") else 5
        if root_vm and args.concurrency > ROOT_VM_CONCURRENCY:
            print(f"pickfit verify: the full-privilege lane takes one record at a time (an agent's VM and a replay's "
                  f"are its two instances); concurrency {args.concurrency} -> {ROOT_VM_CONCURRENCY}")
            args.concurrency = ROOT_VM_CONCURRENCY
        if args.runner == "tart" and args.concurrency > TART_MAX_VMS:
            print(f"pickfit verify: macOS allows {TART_MAX_VMS} VMs at once; concurrency {args.concurrency} -> "
                  f"{TART_MAX_VMS}")
            args.concurrency = TART_MAX_VMS
        if args.runner == "vbox" and args.concurrency > VBOX_MAX_VMS:
            print(f"pickfit verify: one Windows box at a time; concurrency {args.concurrency} -> {VBOX_MAX_VMS}")
            args.concurrency = VBOX_MAX_VMS
        return _batch(args, make_box, limits)
    from pickfit.verify.box import sized_for_build

    task = load_fixture(args.fixture)
    outcome = verify_task(task, _packaged(args, sized_for_build(make_box, task)), model=args.model,
                          mode=args.mode or DEFAULT_MODE, limits=limits, write=args.write_back,
                          keep_agent_box=args.keep_box)
    print(json.dumps(outcome.summary(), ensure_ascii=False, indent=2))
    return 0 if outcome.passed else 1


def _packaged(args: argparse.Namespace, make_box, log=print):
    """The factory of one run's boxes, with --apt's packages installed by pickfit's root in each (sysdeps.py)."""
    if not getattr(args, "apt", None):
        return make_box
    from pickfit.verify.sysdeps import PackagedBoxes

    return PackagedBoxes(make_box, args.apt, log=log)


def _rejudge(args: argparse.Namespace) -> int:
    from pathlib import Path

    from pickfit.verify.agent import _runs_dir
    from pickfit.verify.feature_judge import rejudge_record
    from pickfit.verify.pipeline import judge_model_for
    from pickfit.verify.result import DATA_DIR

    data_dir = Path(args.data_dir) if args.data_dir else DATA_DIR
    rows = []
    for path in sorted(data_dir.glob("*.json")):
        if args.slug and path.stem not in args.slug:
            continue
        row = rejudge_record(path, _runs_dir(None), model=judge_model_for(args.model), force=args.force,
                             log=lambda line, s=path.stem: print(f"[{s}] {line}"))
        if row["judged"] or row["skipped"]:
            rows.append(row)
    print(json.dumps({"records": len(rows), "features_judged": sum(r["judged"] for r in rows),
                      "lowered": sum(r["lowered"] for r in rows),
                      "cost_usd": round(sum(r["cost_usd"] for r in rows), 4),
                      "rows": rows}, ensure_ascii=False, indent=2))
    return 0


def _batch(args: argparse.Namespace, make_box, limits) -> int:
    from pathlib import Path

    from pickfit.discover.run import pipeline_db_path
    from pickfit.meta import resolve_model
    from pickfit.verify.agent import DEFAULT_MODE, _runs_dir
    from pickfit.verify.batch import (
        load_candidates,
        recheck_slugs,
        record_categories,
        record_slugs,
        run_batch,
        verified_slugs,
    )
    from pickfit.verify.pipeline import judge_model_for, verify_task
    from pickfit.verify.result import DATA_DIR

    runs_dir = _runs_dir(None)
    db = Path(args.db) if args.db else pipeline_db_path()
    if not db.exists():
        print(f"pickfit verify: no pipeline database at {db} (use --db)")
        return 2
    data_dir = Path(args.data_dir) if args.data_dir else DATA_DIR
    # macOS and Windows runs do not count Linux ones, nor one Windows box another's
    runner = {"tart": "tart-vz", "vbox": "vbox", "ec2-windows": "ec2-windows"}.get(args.runner)
    skip = verified_slugs(runs_dir, since=args.since, runner=runner) if args.since else \
        set() if args.force else verified_slugs(runs_dir, runner=runner)
    skip -= recheck_slugs(data_dir, runs_dir)  # a new release since the last attempt, which did not pass
    known = record_slugs(data_dir)
    extraction_model = resolve_model(args.extraction_model) if args.extraction_model else None
    repos = [*(args.repo or []), *(known if args.records else [])] or None
    if args.records and not known:
        print(f"pickfit verify: no records in {data_dir}")
        return 2
    items, skipped = load_candidates(db, limit=args.batch, repos=repos, categories=args.category,
                                     skip_slugs=skip, known_slugs=known,
                                     known_categories=record_categories(data_dir), gpu=bool(args.gpu),
                                     os={"tart": "macos", "vbox": "windows", "ec2-windows": "windows"}.get(
                                         args.runner, "linux"),
                                     display=args.display, extraction_model=extraction_model)
    print(f"batch · {len(items)} to verify · {len(skipped)} set aside · {args.runner}"
          f"{' ' + args.runtime if args.runner == 'modal' else ''}{' + display' if args.display else ''}"
          f"{' + microphone' if args.audio else ''}{' + toolchain' if args.toolchain else ''}"
          f"{' + ' + args.gpu if args.gpu else ''} · "
          f"concurrency {args.concurrency} · agent {resolve_model(args.model)} · "
          f"judges {resolve_model(judge_model_for(args.model))}"
          f"{' · extractions by ' + extraction_model if extraction_model else ''}")
    for item in items:
        print(f"  {item.priority:+d} {item.task.slug:<28} {item.category:<9} {item.kind or '-':<12} "
              f"{item.full_name}")
    if args.dry_run:
        for s in skipped:
            print(f"  skip {s['slug']:<28} {s['reason']}")
        return 0
    if args.runner == "modal":  # build or fetch the image once, not in every thread
        from pickfit.verify.modal_box import ensure_published_image

        ensure_published_image(runtime=args.runtime, display=args.display, audio=args.audio,
                               toolchain=args.toolchain, services=args.services)
    if args.runner == "ec2" and args.runtime == ROOT_VM:  # its own AMI
        from pickfit.verify.ec2_root import ensure_root_image

        ensure_root_image()
    elif args.runner == "ec2":  # bake or find the AMI once, not in every thread
        from pickfit.verify.ec2_machine import ensure_image
        from pickfit.verify.linux_box import image_recipe

        ensure_image(recipe=image_recipe("vm", args.display, args.audio, args.toolchain, args.services))
    if args.runner == "ec2-windows":
        from pickfit.verify.ec2_windows import ensure_win_image

        ensure_win_image(display=args.display)

    from pickfit.verify.box import sized_for_build

    def verify(task, log):  # a build box that compiles Rust or Go gets more cores (sized_for_build)
        return verify_task(task, _packaged(args, sized_for_build(make_box, task), log), model=args.model,
                           mode=args.mode or DEFAULT_MODE, limits=limits, runs_dir=runs_dir, log=log,
                           write=args.write_back, data_dir=data_dir)

    summary = run_batch(items, verify, concurrency=args.concurrency, runs_dir=runs_dir,
                        meta={"db": str(db), "runner": args.runner, "runtime": args.runtime, "display": args.display,
                              "gpu": args.gpu, "audio": args.audio, "toolchain": args.toolchain,
                              "model": resolve_model(args.model),
                              "judge_model": resolve_model(judge_model_for(args.model)),
                              "extraction_model": extraction_model,
                              "skipped": skipped})
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0
