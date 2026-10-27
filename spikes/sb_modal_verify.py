#!/usr/bin/env python3
"""Spike：在 Modal Sandbox 裡照 README 安裝一個 CLI，再斷網跑 smoke test。

驗證什麼：
  1. Sandbox 從建立到可執行指令要幾秒（含第一次建 image 與之後的冷啟動）。
  2. 「安裝時開網路 → 執行時斷網」這條路走不走得通
     （Modal 文件：建立時設 outbound_domain_allowlist=["*"] 與 outbound_cidr_allowlist=["0.0.0.0/0"]，
       之後用 _experimental_set_outbound_network_policy 收緊；此 API 為 Alpha）。
  3. 一次驗證實際花多少錢（Sandbox 以 max(request, actual) 計費，CPU/記憶體是一般價的 3 倍）。

怎麼跑：
  pip install modal
  modal token new                      # 或 export MODAL_TOKEN_ID=... MODAL_TOKEN_SECRET=...
  python3 spikes/sb_modal_verify.py \
      --install "pip install httpie" \
      --smoke "http --version"

輸出一行 JSON：各階段秒數、exit code、stdout/stderr 尾段。
狀態：未實測（2026-10-28 撰寫時沒有 Modal 金鑰）。API 名稱取自 modal.com/docs/guide/sandbox 與
sandbox-networking（2026-10-28 讀取）。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time


def tail(text: str, n: int = 1500) -> str:
    return text[-n:] if text else ""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--install", required=True, help="安裝指令（照 README），在有網路時執行")
    ap.add_argument("--smoke", required=True, help="smoke test 指令，在斷網後執行")
    ap.add_argument("--keep-network", action="store_true", help="smoke test 時不斷網")
    ap.add_argument("--timeout", type=int, default=900, help="Sandbox 最長存活秒數")
    args = ap.parse_args()

    if not (os.environ.get("MODAL_TOKEN_ID") or os.path.exists(os.path.expanduser("~/.modal.toml"))):
        print("沒有 Modal 憑證：先跑 `modal token new`，或設定 MODAL_TOKEN_ID / MODAL_TOKEN_SECRET。", file=sys.stderr)
        return 2

    import modal  # 延後 import，沒裝 modal 時也能看到上面的說明

    result: dict = {"install": args.install, "smoke": args.smoke}
    t0 = time.monotonic()
    app = modal.App.lookup("pickfit-verify-spike", create_if_missing=True)
    # 正式版應改用事先 publish 的 named image（Image.from_name），避免每次建立時才 build。
    image = modal.Image.debian_slim().apt_install("curl", "git", "ca-certificates")

    sb = modal.Sandbox.create(
        app=app,
        image=image,
        timeout=args.timeout,
        cpu=1.0,  # 1 physical core = 2 vCPU
        memory=2048,  # MiB
        outbound_domain_allowlist=["*"],
        outbound_cidr_allowlist=["0.0.0.0/0"],
    )
    try:
        p = sb.exec("true")
        p.wait()
        result["ready_s"] = round(time.monotonic() - t0, 2)

        t1 = time.monotonic()
        p = sb.exec("bash", "-lc", args.install, timeout=600)
        p.wait()
        result["install_s"] = round(time.monotonic() - t1, 2)
        result["install_rc"] = p.returncode
        result["install_out"] = tail(p.stdout.read() + p.stderr.read())

        if not args.keep_network:
            # 空的 allowlist = 全部擋掉（block_network=True 不能和動態更新並用）
            sb._experimental_set_outbound_network_policy(
                outbound_domain_allowlist=[],
                outbound_cidr_allowlist=[],
            )
            result["network_locked"] = True

        t2 = time.monotonic()
        p = sb.exec("bash", "-lc", args.smoke, timeout=120)
        p.wait()
        result["smoke_s"] = round(time.monotonic() - t2, 2)
        result["smoke_rc"] = p.returncode
        result["smoke_out"] = tail(p.stdout.read() + p.stderr.read())
    finally:
        sb.terminate()
        result["total_s"] = round(time.monotonic() - t0, 2)

    print(json.dumps(result, ensure_ascii=False))
    return 0 if result.get("smoke_rc") == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
