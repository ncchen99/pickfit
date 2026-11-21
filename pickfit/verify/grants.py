"""Grants: what a verification's box was given beyond the plain box, who asked, and who decides
(docs/proposals/privileges.md P1, P2 and the record side of P5).

The agent never takes a privilege. It asks with request_capability(kind, name, why) (agent.py), and the Desk here
answers from the policy table, a data file (grants_policy.json), never from the prompt:

- granted: a provider gives it in the same box now (a named system package installed by pickfit as root, a service
  the box user starts), and the grant is recorded;
- rerun: the box has no such thing, but a box one tier up does: this run ends, and the pipeline starts the record
  over in a fresh box of that kind (pipeline.verify_task). At most policy.max_escalations times per record;
- refused: with the reason and the existing needs_* code the agent reports the affected features under.

A request is only a request. What a README or a command's output tells the agent to ask for changes nothing: the
name must be one plain name, the rule that matches it is the policy's, and a record's spending limit is the policy's
too. Providers are a seam: kind (and optionally name) -> a callable that acts on a box. The system-package installer
(sysdeps.py), the root box and the billing proxy register theirs; until then such a request is refused.

Everything granted to the agent's box is given again by pickfit in the fresh replay box, in the same order between
the same install steps (replay.py), so the fresh-box rule stands: nothing carries over from one box to the next.

A run's record keeps five fields of each grant (kind, name, tier, requested_by, shown_in_guide) and, for each
feature, the fidelity of what it was checked against: real, compatible (a compatible endpoint with a real model
behind it: the billing proxy) or stand_in (a stand-in that only shows the wiring works). Those two fields reach
VerificationRun with loop/proposals/privileges-schema.patch; before it, and always in full, they are in the run's
own files (report.json, replay.json, grants.json).
"""

from __future__ import annotations

import fnmatch
import json
import os
import re
import shlex
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, get_args

from pickfit.schema import FeatureGap
from pickfit.verify.box import Box, BoxError

KINDS: tuple[str, ...] = ("system_package", "service", "model_endpoint", "root", "container_engine",
                          "test_identity", "virtual_device", "extra_machine")
FIDELITIES: tuple[str, ...] = ("stand_in", "compatible", "real")  # weakest first
REQUESTERS: tuple[str, ...] = ("agent", "plan")
GAPS: tuple[str, ...] = get_args(FeatureGap.__value__)
TIERS = range(1, 6)  # the ladder of privileges.md; tier 6 is "not verified", never a grant
POLICY_PATH = Path(__file__).with_name("grants_policy.json")
POLICY_ENV = "PICKFIT_GRANTS_POLICY"
POLICY_VERSION = "grants.v1"
# One plain name: a Debian package (libstdc++6, libc6:i386), a service, an identity. No path, space or shell syntax:
# the name goes into a root command and into the install guide.
NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9+._:@-]{0,79}$")
PROVIDER_TIMEOUT_S = 120
NO_PROVIDER = "pickfit cannot give this yet"
_SERVICES_START = re.compile(r"\bpickfit-services\s+start((?:[ \t]+[a-z0-9][a-z0-9-]*)+)")


# ---------------------------------------------------------------- grants


@dataclass(frozen=True)
class Grant:
    """One thing a box was given. The first five fields are the record's; the rest say how pickfit gives it again
    and which checks it touches, and stay in the run's own files."""

    kind: str
    name: str
    tier: int
    requested_by: str  # agent: it asked with request_capability; plan: the box came with it, from the extraction
    shown_in_guide: bool
    guide_step: str | None = None  # what a user does for it, when shown_in_guide
    fidelity: str | None = None  # what a check that used it was checked against
    markers: tuple[str, ...] = ()  # text that shows a command used it (its URL, its environment variable)
    after_command: int = 0  # the agent's last command_id before it was given: later checks may have used it

    def record(self) -> dict[str, Any]:
        return {"kind": self.kind, "name": self.name, "tier": self.tier, "requested_by": self.requested_by,
                "shown_in_guide": self.shown_in_guide}

    def to_dict(self) -> dict[str, Any]:
        return {**asdict(self), "markers": list(self.markers)}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Grant:
        return cls(kind=str(data["kind"]), name=str(data["name"]), tier=int(data["tier"]),
                   requested_by=str(data.get("requested_by") or "agent"),
                   shown_in_guide=bool(data.get("shown_in_guide")), guide_step=data.get("guide_step"),
                   fidelity=data.get("fidelity"), markers=tuple(data.get("markers") or ()),
                   after_command=int(data.get("after_command") or 0))


def grants_of(data: Mapping[str, Any] | None) -> list[Grant]:
    """The grants a saved report, replay or run holds; none for one written before grants were recorded."""
    return [Grant.from_dict(g) for g in ((data or {}).get("grants") or [])]


# ---------------------------------------------------------------- providers


@dataclass(frozen=True)
class Ask:
    kind: str
    name: str
    why: str = ""
    run_id: str | None = None
    role: str = "agent"  # agent, replay or confirm: which of the run's boxes this is


@dataclass(frozen=True)
class Provided:
    """A provider's answer. message is what the agent is told: how to use it, or why not."""

    granted: bool
    message: str = ""
    guide_step: str | None = None
    fidelity: str | None = None
    markers: tuple[str, ...] = ()
    usd: float = 0.0  # what giving it cost, or can cost at most (a proxy ticket's allowance)


Provider = Callable[[Box, Ask], Provided]


class Providers:
    """kind -> the callable that gives it in a box; a name of a kind may have its own."""

    def __init__(self, providers: Mapping[str, Provider] | None = None) -> None:
        self._by: dict[tuple[str, str | None], Provider] = {}
        for kind, provider in (providers or {}).items():
            self.register(kind, provider)

    def register(self, kind: str, provider: Provider, name: str | None = None) -> None:
        if kind not in KINDS:
            raise ValueError(f"unknown grant kind {kind!r}")
        self._by[(kind, name)] = provider

    def get(self, kind: str, name: str | None = None) -> Provider | None:
        return self._by.get((kind, name)) or self._by.get((kind, None))

    def give(self, box: Box, ask: Ask) -> Provided | None:
        """The provider's answer, or None when no provider gives this kind. A provider that raises has refused; a
        broken box (BoxError) is the run's, not a refusal."""
        provider = self.get(ask.kind, ask.name)
        if provider is None:
            return None
        try:
            return provider(box, ask)
        except BoxError:
            raise
        except Exception as err:  # noqa: BLE001 - a provider's fault never becomes a grant
            return Provided(False, f"pickfit could not give it ({type(err).__name__}: {_one_line(str(err), 200)})")


def pickfit_services(box: Box, ask: Ask) -> Provided:
    """service: the services box's own helper (services.py), started by the box user like an install step, on
    127.0.0.1 only. The policy sends the request to a services box first; this only starts what it names."""
    result = box.exec(f"pickfit-services start {shlex.quote(ask.name)}", PROVIDER_TIMEOUT_S)
    said = _one_line((result.stdout if result.ok else result.stderr or result.stdout).strip(), 300)
    if not result.ok:
        return Provided(False, f"pickfit-services could not start {ask.name}: {said or f'exit {result.exit_code}'}")
    return Provided(True, f"{said}. `pickfit-services env` prints the URLs as environment variables.")


def system_packages(install_named: Callable[..., Any], timeout_s: int = 300) -> Provider:
    """system_package through sysdeps.install_named(box, names, timeout_s), whose result names what it installed,
    what it refused and the command a user would run. pickfit runs it as root; the box user gets no root."""

    def provide(box: Box, ask: Ask) -> Provided:
        result = install_named(box, [ask.name], timeout_s)
        if ask.name not in (getattr(result, "installed", None) or ()):
            refused = getattr(result, "refused", None) or ()
            why = "it is not a named package of the distribution" if ask.name in refused else "the install failed"
            return Provided(False, f"pickfit did not install {ask.name}: {why}")
        # The guide shows what a user types. A command that is pickfit's own root call (no sudo) is not that:
        # the policy's line stands in.
        command = str(getattr(result, "command", None) or "")
        return Provided(True, f"pickfit installed the system package {ask.name} as root.",
                        guide_step=command if command.startswith("sudo ") else None)

    return provide


def default_providers() -> Providers:
    """What pickfit can give today: services in a services box, and named system packages once sysdeps.py is in."""
    providers = Providers({"service": pickfit_services})
    try:
        from pickfit.verify.sysdeps import install_named  # type: ignore[import-not-found]
    except ImportError:
        return providers
    providers.register("system_package", system_packages(install_named))
    return providers


# ---------------------------------------------------------------- policy


@dataclass(frozen=True)
class Rule:
    kind: str
    names: tuple[str, ...]  # shell-style patterns; the first rule of the kind that matches the name decides
    answer: str  # grant: in this box, by its provider; rerun: needs a box with `box`; refuse
    gap: str  # the existing reason code a refusal is reported under
    tier: int | None = None
    box: str | None = None  # rerun: the box attribute it needs (services, audio, toolchain, root, container_engine)
    box_gives: bool = False  # rerun: the box itself is the grant (root in a root box); no provider acts
    shown_in_guide: bool = False
    guide: str | None = None  # the install guide's line for it, {name} filled in
    fidelity: str | None = None
    markers: tuple[str, ...] = ()
    usd: float = 0.0  # the most one such grant can cost
    why: str = ""  # refuse: what the agent is told

    def matches(self, kind: str, name: str) -> bool:
        return kind == self.kind and any(fnmatch.fnmatchcase(name, pattern) for pattern in self.names)


@dataclass(frozen=True)
class Policy:
    enabled: bool  # false: the agent gets no request_capability tool; plan grants are recorded all the same
    max_escalations: int  # reruns one tier up per record
    max_usd_per_record: float  # model and box cost of every attempt of one record, plus what its grants can cost
    max_requests_per_run: int
    rerun_reserve_usd: float  # a rerun starts only with this much of the record's limit left: it is a whole run
    rules: tuple[Rule, ...]
    version: str = POLICY_VERSION

    def rule(self, kind: str, name: str) -> Rule | None:
        return next((r for r in self.rules if r.matches(kind, name)), None)


def parse_policy(data: Mapping[str, Any]) -> Policy:
    """The policy a data file holds. Refuses a table that names a kind, an answer or a reason code pickfit does not
    have (no new gap codes are made here), or that leaves a kind without a rule for every name."""
    if data.get("version") != POLICY_VERSION:
        raise ValueError(f"grants policy version must be {POLICY_VERSION!r}, not {data.get('version')!r}")
    limits = data.get("limits") or {}
    rules = []
    for n, raw in enumerate(data.get("rules") or [], 1):
        where = f"grants policy rule {n}"
        unknown = set(raw) - set(Rule.__dataclass_fields__)
        if unknown:
            raise ValueError(f"{where}: unknown field(s) {sorted(unknown)}")
        rule = Rule(**{**raw, "names": tuple(raw.get("names") or ()), "markers": tuple(raw.get("markers") or ())})
        if rule.kind not in KINDS:
            raise ValueError(f"{where}: unknown kind {rule.kind!r}")
        if rule.answer not in ("grant", "rerun", "refuse"):
            raise ValueError(f"{where}: answer must be grant, rerun or refuse, not {rule.answer!r}")
        if rule.gap not in GAPS:
            raise ValueError(f"{where}: {rule.gap!r} is not one of pickfit's reason codes")
        if not rule.names:
            raise ValueError(f"{where}: needs names")
        if rule.answer != "refuse" and rule.tier not in TIERS:
            raise ValueError(f"{where}: a grant needs a tier from {TIERS.start} to {TIERS.stop - 1}")
        if (rule.answer == "rerun") != bool(rule.box) or (rule.box_gives and not rule.box):
            raise ValueError(f"{where}: a rerun rule, and only one, names the box it needs")
        if rule.fidelity is not None and rule.fidelity not in FIDELITIES:
            raise ValueError(f"{where}: unknown fidelity {rule.fidelity!r}")
        if rule.usd < 0:
            raise ValueError(f"{where}: usd cannot be negative")
        rules.append(rule)
    for kind in KINDS:
        if not any(r.kind == kind and "*" in r.names for r in rules):
            raise ValueError(f"grants policy: kind {kind!r} needs a rule for every other name (names [\"*\"])")
    policy = Policy(enabled=bool(data.get("enabled")), max_escalations=int(limits.get("max_escalations", -1)),
                    max_usd_per_record=float(limits.get("max_usd_per_record", -1)),
                    max_requests_per_run=int(limits.get("max_requests_per_run", -1)),
                    rerun_reserve_usd=float(limits.get("rerun_reserve_usd", 0.0)), rules=tuple(rules))
    if policy.max_escalations < 0 or policy.max_usd_per_record < 0 or policy.max_requests_per_run < 1:
        raise ValueError("grants policy: limits needs max_escalations, max_usd_per_record and max_requests_per_run")
    return policy


def load_policy(path: Path | str | None = None) -> Policy:
    """The policy table: grants_policy.json beside this file, or the file PICKFIT_GRANTS_POLICY names."""
    source = Path(path or os.environ.get(POLICY_ENV, "").strip() or POLICY_PATH)
    return parse_policy(json.loads(source.read_text(encoding="utf-8")))


def has(box: Box, need: str | None) -> bool:
    """Does the box have what a rerun rule needs (Box.services, .audio, .toolchain, .root, ...)?"""
    return bool(need) and bool(getattr(box, need, False))


def provide(policy: Policy, providers: Providers, box: Box, ask: Ask) -> tuple[Rule | None, Provided]:
    """Give one thing in one box as the policy allows: the agent's box on a request, a fresh box when the replay
    gives it again. Never more than the rule says; a box that lacks what the rule needs gets nothing."""
    rule = policy.rule(ask.kind, ask.name) if NAME.match(ask.name) else None
    if rule is None or rule.answer == "refuse":
        return rule, Provided(False, (rule.why if rule else "") or "pickfit's policy does not give this")
    if rule.answer == "rerun" and not has(box, rule.box):
        return rule, Provided(False, f"this box has no {rule.box}")
    if rule.box_gives:
        return rule, Provided(True, f"this box has it ({rule.box})")
    return rule, providers.give(box, ask) or Provided(False, NO_PROVIDER)


# ---------------------------------------------------------------- the desk


@dataclass(frozen=True)
class Decision:
    """The harness's answer to one request."""

    answer: str  # granted, rerun or refused
    kind: str
    name: str
    message: str
    tier: int | None = None
    gap: str | None = None  # refused: the reason code for the features that needed it
    box: str | None = None  # rerun: what the next box must have
    grant: Grant | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"answer": self.answer, "kind": self.kind, "name": self.name, "message": self.message,
                "tier": self.tier, "gap": self.gap, "box": self.box}


@dataclass
class Desk:
    """Answers one run's requests. One per attempt: the pipeline tells it how often the record was rerun already,
    what its earlier attempts spent and which boxes a rerun can have here."""

    policy: Policy
    providers: Providers = field(default_factory=default_providers)
    escalations: int = 0
    spent_usd: float = 0.0  # the record's earlier attempts: model and box
    raisable: frozenset[str] = frozenset()  # the box needs a rerun can add on this runner
    run_id: str | None = None
    carried: tuple[str, ...] = ()  # what earlier attempts asked for and this box now has, said to the agent
    grants: list[Grant] = field(default_factory=list)
    requests: list[dict[str, Any]] = field(default_factory=list)
    granted_usd: float = 0.0
    rerun: Decision | None = None  # set once: the run ends here

    def request(self, box: Box, kind: str, name: str, why: str = "", *, spent_usd: float = 0.0,
                after_command: int = 0) -> Decision:
        """spent_usd: what this attempt has spent so far; after_command: its last command_id."""
        name = name.strip()
        earlier = next((r for r in self.requests if (r["kind"], r["name"]) == (kind, name)), None)
        if earlier is not None:  # asking again gets the same answer, and nothing is given twice
            decision = Decision(**{k: earlier[k] for k in ("answer", "kind", "name", "message", "tier", "gap", "box")})
        else:
            decision = self._decide(box, kind, name, why, self.spent_usd + spent_usd + self.granted_usd,
                                    after_command)
            self.requests.append({**decision.to_dict(), "why": _one_line(why, 300), "after_command": after_command})
            if decision.grant is not None:
                self.grants.append(decision.grant)
            if decision.answer == "rerun":
                self.rerun = decision
        return decision

    def _refuse(self, kind: str, name: str, rule: Rule | None, why: str) -> Decision:
        gap = rule.gap if rule else "other"
        return Decision("refused", kind, name, why, tier=rule.tier if rule else None, gap=gap)

    def _decide(self, box: Box, kind: str, name: str, why: str, spent: float, after_command: int) -> Decision:
        policy = self.policy
        if kind not in KINDS:
            return self._refuse(kind, name, None, f"{kind!r} is not something pickfit gives")
        fallback = policy.rule(kind, "*")
        if not NAME.match(name):
            return self._refuse(kind, name, fallback, "name one thing by its plain name (a package, a service): no "
                                                      "path, version rule, option or command")
        if len(self.requests) >= policy.max_requests_per_run:
            return self._refuse(kind, name, fallback, f"this run has made its {policy.max_requests_per_run} requests")
        rule = policy.rule(kind, name)
        if rule is None or rule.answer == "refuse":
            return self._refuse(kind, name, rule or fallback, (rule.why if rule else "") or
                                "pickfit's policy does not give this")
        if not rule.box_gives and self.providers.get(kind, name) is None:  # before a rerun that could not help
            return self._refuse(kind, name, rule, NO_PROVIDER)
        limit = f"US${policy.max_usd_per_record:.2f}"
        if rule.answer == "rerun" and not has(box, rule.box):
            if self.escalations >= policy.max_escalations:
                return self._refuse(kind, name, rule, f"it needs a box with {rule.box}, and this record has already "
                                                      f"been rerun {self.escalations} times, the most pickfit allows")
            if rule.box not in self.raisable:
                return self._refuse(kind, name, rule, f"it needs a box with {rule.box}, which pickfit does not have "
                                                      "for this run")
            if policy.max_usd_per_record - spent < max(policy.rerun_reserve_usd, 0.01):
                return self._refuse(kind, name, rule, f"it needs a rerun, and this record is too near its spending "
                                                      f"limit ({limit}) for one; a person decides")
            return Decision("rerun", kind, name, f"This run ends now: pickfit starts over in a fresh box with "
                                                 f"{rule.box}. Call nothing else.", tier=rule.tier, box=rule.box)
        if spent + rule.usd > policy.max_usd_per_record:
            return self._refuse(kind, name, rule, f"it would take this record over its spending limit ({limit}); "
                                                  "a person decides")
        _, given = provide(policy, self.providers, box, Ask(kind, name, why, self.run_id, "agent"))
        if not given.granted:
            return self._refuse(kind, name, rule, given.message or "pickfit could not give it")
        self.granted_usd += max(given.usd, rule.usd)
        grant = Grant(kind, name, rule.tier or 1, "agent", rule.shown_in_guide,
                      guide_step=given.guide_step or guide_line(rule, name), fidelity=given.fidelity or rule.fidelity,
                      markers=(*rule.markers, *given.markers), after_command=after_command)
        return Decision("granted", kind, name, given.message or "given", tier=rule.tier, grant=grant)


def regrant(policy: Policy, providers: Providers, box: Box, grant: Grant, *, run_id: str | None = None,
            role: str = "replay") -> Provided:
    """Give a fresh box what the agent's box was given, by the same rule; plan grants came with the box."""
    if grant.requested_by != "agent":
        return Provided(True, "came with the box")
    return provide(policy, providers, box, Ask(grant.kind, grant.name, "", run_id, role))[1]


# ---------------------------------------------------------------- what a run records


def guide_line(rule: Rule | None, name: str) -> str | None:
    return rule.guide.replace("{name}", name) if rule and rule.guide else None


def guide_steps(grants: Iterable[Grant | Mapping[str, Any]], policy: Policy | None = None) -> list[str]:
    """The install guide's lines for what a user must have or do first (a `sudo apt-get install` line): one per
    grant with shown_in_guide, in the order given. A record's grant (five fields) gets its line from the policy."""
    lines: list[str] = []
    for item in grants:
        grant = item if isinstance(item, Grant) else Grant.from_dict(item)
        if not grant.shown_in_guide:
            continue
        line = grant.guide_step
        if not line:
            policy = policy or load_policy()
            line = guide_line(policy.rule(grant.kind, grant.name), grant.name)
        if line and line not in lines:
            lines.append(line[:300])
    return lines


def plan_grants(box: Mapping[str, Any], commands: Iterable[str], policy: Policy,
                held: Iterable[Grant] = ()) -> list[Grant]:
    """What the box had because the extraction said the tool needs it (box_needs.py), not because the agent asked:
    the simulated microphone, and each service a cited command started with pickfit-services."""
    have = {(g.kind, g.name) for g in held}
    found: list[tuple[str, str]] = [("virtual_device", "microphone")] if box.get("audio") else []
    for command in commands:
        for match in _SERVICES_START.finditer(command or ""):
            found += [("service", name) for name in match.group(1).split()]
    grants: list[Grant] = []
    for kind, name in found:
        rule = policy.rule(kind, name)
        if (kind, name) in have or rule is None or rule.answer == "refuse":
            continue
        have.add((kind, name))
        grants.append(Grant(kind, name, rule.tier or 1, "plan", rule.shown_in_guide, guide_step=guide_line(rule, name),
                            fidelity=rule.fidelity, markers=rule.markers))
    return grants


def cited_commands(verdict: Mapping[str, Any] | None, commands: Mapping[int, str]) -> list[str]:
    """The commands a log verdict stands on: its steps, its checks and their setups."""
    verdict = verdict or {}
    ids = list(verdict.get("step_ids") or [])
    for check in verdict.get("checks") or []:
        ids += [*(check.get("setup_ids") or []), check.get("command_id")]
    return [commands[i] for i in dict.fromkeys(ids) if i in commands]


def run_grants(report: Any, policy: Policy) -> list[Grant]:
    """One run's grants: what the agent asked for and got, then what its box came with."""
    asked = grants_of({"grants": getattr(report, "grants", None)})
    by_id = {c.command_id: c.command for c in report.commands if c.command_id is not None}
    return asked + plan_grants(report.box or {}, cited_commands(report.verdict, by_id), policy, asked)


def feature_fidelity(features: Iterable[Mapping[str, Any]], verdict: Mapping[str, Any] | None,
                     commands: Mapping[int, str], grants: Sequence[Grant]) -> dict[str, str]:
    """feature label -> the fidelity of what its checks ran against, for features whose checks used a grant that has
    one; the weakest wins. A check used a grant when it ran after it and its command or setup shows one of the
    grant's markers. A grant weaker than real none of whose markers shows anywhere (the tool read its endpoint from
    a file nothing cited) counts for every check after it: a stand-in is never passed off as the real thing."""
    setups = {c.get("command_id"): c.get("setup_ids") or [] for c in (verdict or {}).get("checks") or []}

    def text(cid: int) -> str:
        return "\n".join(commands.get(i, "") for i in (*setups.get(cid, []), cid))

    features = [f for f in features if f.get("status") in ("checked", "test_failed") and f.get("command_ids")]
    every = [cid for f in features for cid in f["command_ids"]]
    out: dict[str, str] = {}
    for grant in grants:
        if grant.fidelity not in FIDELITIES:
            continue
        after = [cid for cid in every if cid > grant.after_command]
        shown = {cid for cid in after if any(m in text(cid) for m in grant.markers)}
        if not shown and grant.fidelity != "real":
            shown = set(after)
        for f in features:
            if shown & set(f["command_ids"]):
                held = out.get(f["feature"])
                if held is None or FIDELITIES.index(grant.fidelity) < FIDELITIES.index(held):
                    out[f["feature"]] = grant.fidelity
    return out


def _one_line(text: str, limit: int) -> str:
    flat = " ".join((text or "").split())
    return flat if len(flat) <= limit else flat[: limit - 1] + "…"
