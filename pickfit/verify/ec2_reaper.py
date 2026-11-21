"""The EC2 reaper: ends instances of pickfit's that outlived their purpose, by pickfit's own tags and their age.

Every pickfit instance is launched so that its own poweroff ends it, and ec2_machine.reap() ends one whose
`pickfit:expires` tag is past. Both rest on something that can fail to be there: the poweroff timer runs inside
the instance (and in a full-privilege VM box the software under test may hold root and stop it), and a tag may be
missing from an instance whose launch was cut short. This reaper needs neither. It reads what EC2 holds:

- An instance is pickfit's only when it carries both `pickfit=verify` and a `pickfit:role` tag, which every
  launch writes in the same call that creates the instance (Ec2Instance._box_tags, warm_kwargs). The account
  holds another project's instances; one without both tags is never touched, whatever its name, its other tags,
  its age or its state. The tags are checked here again on what EC2 returns, not left to the request's filter.
- Such an instance is ended when its `pickfit:expires` time is REAP_MARGIN_S past, or, when it has no readable
  lifetime at all, when EC2 says it was launched more than max_age_s ago. A pool member, stopped and waiting, has
  a lifetime of a week and is kept until then.

reap_leaked() runs at every start of a full-privilege box; scripts/ec2_reap.py runs it by hand or from a timer,
together with the sweep of that lane's network and its old images.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from pickfit.verify.ec2_machine import EXPIRES_TAG, LIVE_STATES, REAP_MARGIN_S, _tag

OURS_TAG = ("pickfit", "verify")
ROLE_TAG = "pickfit:role"
MAX_AGE_S = 6 * 3600  # no box, bake or warm-up lasts this long; only a tagged lifetime may say otherwise


def ours(instance: dict[str, Any]) -> bool:
    """Is this instance one pickfit launched: both of pickfit's own tags, as EC2 lists them on it."""
    return _tag(instance, OURS_TAG[0]) == OURS_TAG[1] and bool(_tag(instance, ROLE_TAG))


def launched_at(instance: dict[str, Any]) -> float | None:
    """When EC2 says the instance was launched, as unix time (None when it does not say)."""
    launched = instance.get("LaunchTime")
    stamp = getattr(launched, "timestamp", None)
    return float(stamp()) if callable(stamp) else None


def why_leaked(instance: dict[str, Any], now: float, max_age_s: float = MAX_AGE_S) -> str | None:
    """Why this instance should be ended now, or None. Never a reason for an instance that is not pickfit's."""
    if not ours(instance) or instance.get("State", {}).get("Name") not in LIVE_STATES:
        return None
    expires = _tag(instance, EXPIRES_TAG) or ""
    if expires.isdigit():
        late = now - int(expires)
        return f"{late / 60:.0f} min past its lifetime" if late > REAP_MARGIN_S else None
    born = launched_at(instance)
    if born is not None and now - born > max_age_s:
        return f"no lifetime tag, launched {(now - born) / 3600:.1f} h ago"
    return None


def reap_leaked(ec2: Any, log: Callable[[str], None] = print, now: float | None = None,
                max_age_s: float = MAX_AGE_S, apply: bool = True) -> list[tuple[str, str]]:
    """Terminate pickfit's leaked instances in the client's region; [(instance id, why)]. Without `apply` nothing is
    terminated and the list says what would be."""
    now = time.time() if now is None else now
    found = ec2.describe_instances(Filters=[{"Name": f"tag:{OURS_TAG[0]}", "Values": [OURS_TAG[1]]},
                                            {"Name": "instance-state-name", "Values": LIVE_STATES}])
    leaked = []
    for instance in (i for r in found.get("Reservations", []) for i in r.get("Instances", [])):
        why = why_leaked(instance, now, max_age_s)
        if why:
            leaked.append((str(instance["InstanceId"]), f"{_tag(instance, ROLE_TAG)}: {why}"))
    if leaked and apply:
        ec2.terminate_instances(InstanceIds=[iid for iid, _ in leaked])
    for iid, why in leaked:
        log(f"ec2 reaper: {'terminated' if apply else 'would terminate'} {iid} ({why})")
    return leaked
