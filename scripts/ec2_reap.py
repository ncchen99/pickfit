"""End what pickfit left running on EC2, and what the full-privilege VM lane left behind.

    uv run python scripts/ec2_reap.py                 # say what would be removed (calls Describe* only)
    uv run python scripts/ec2_reap.py --apply         # remove it
    uv run python scripts/ec2_reap.py --region us-east-1 --max-age-hours 3

Three things, each only on what carries pickfit's own tags (pickfit/verify/ec2_reaper.py says how an instance is
known to be pickfit's; the account holds another project's):

1. instances past their tagged lifetime, or with no lifetime tag and older than --max-age-hours;
2. in the full-privilege lane's VPC: subnets no instance lives in, probe rules whose instance is gone, and offline
   ACLs for an address the harness had a week ago (ec2_root.sweep_network);
3. root-VM images other than the one the code names now, with their snapshots (ec2_root.prune_root_images).

Needs an AWS session (`aws login`); meant for a person or a timer on the watch host. A dry run is the default.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def main(argv: list[str] | None = None, ec2: object | None = None) -> int:
    from pickfit.verify.ec2_machine import CONTROL_CIDR_ENV, ec2_client, region_name
    from pickfit.verify.ec2_reaper import MAX_AGE_S, reap_leaked
    from pickfit.verify.ec2_root import prune_root_images, sweep_network

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--region", default=None, help="the AWS region (default: PICKFIT_EC2_REGION, else ap-east-2)")
    parser.add_argument("--apply", action="store_true", help="remove what is found (default: only list it)")
    parser.add_argument("--max-age-hours", type=float, default=MAX_AGE_S / 3600,
                        help="an instance of pickfit's with no lifetime tag is ended when older than this")
    parser.add_argument("--control", default=None,
                        help="the harness's address as a CIDR, whose offline ACL is kept "
                             f"(default: {CONTROL_CIDR_ENV})")
    args = parser.parse_args(argv)
    import os

    region = args.region or region_name()
    client = ec2 or ec2_client(region)
    control = args.control or os.environ.get(CONTROL_CIDR_ENV) or None
    word = "removed" if args.apply else "would be removed"
    instances = reap_leaked(client, max_age_s=args.max_age_hours * 3600, apply=args.apply)
    network = sweep_network(client, control, apply=args.apply)
    images = prune_root_images(client, apply=args.apply)
    print(f"ec2 reap · {region} · {len(instances)} instance(s), {len(network)} network item(s), "
          f"{len(images)} image or snapshot id(s) {word}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
