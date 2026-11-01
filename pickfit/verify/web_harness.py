"""Runs inside the web sandbox as the browser's uid: Chromium, browser-use and the phases of one visit.

pickfit (web_verify, on the host) starts this script with `/opt/agent/bin/python` and talks to it in JSON
lines: the script's real stdout carries only protocol messages (everything printed by libraries goes to
stderr), stdin carries the answers. The script never holds a model key: browser-use's model calls are sent
to the host as {"type": "llm"} messages and the host makes them through call_meta (ledger, caps, traces).

Phases (the host decides between them):
1. install: open the URL, wait, record what the page shows (text, counts, links, PWA signals, screenshot).
2. function: browser-use operates the site toward its advertised use (step cap, slow pace, no web search,
   no JavaScript tool, no typing into credential fields); pickfit records the page before and after, the
   files that arrived and what the agent typed or chose.
3. offline (PWAs only): the host cuts the network; the page is reloaded with the browser offline and the
   agent's recorded actions are replayed without a model.

Only standard library and browser-use (pinned in the image) are imported. Evidence goes to EVIDENCE.
"""

# No `from __future__ import annotations`: browser-use checks action parameters' annotations as real types.
import asyncio
import base64
import hashlib
import json
import os
import subprocess
import sys
import threading
import time
import traceback
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

HOME = Path("/home/web")
EVIDENCE = HOME / "evidence"
DOWNLOADS = HOME / "downloads"
PROFILE = Path("/tmp/pickfit-chrome")
CHROME = "/usr/bin/chromium"
CDP_PORT = 9222
PROXY = "http://127.0.0.1:8080"
TEXT_LIMIT = 12_000
VIEWPORT = (1280, 900)
ELEMENTS_CHARS = 12_000  # browser-use's element list per step (default 40,000): most of each call's tokens
EXCLUDED_ACTIONS = ["search", "evaluate", "save_as_pdf", "write_file", "replace_file", "read_file"]
CREDENTIAL_HINTS = ("password", "passwd", "email", "e-mail", "phone", "mobile", "card", "cvv", "cvc", "iban",
                    "username", "user name", "login", "otp", "one-time", "verification code", "ssn")

_proto = os.fdopen(os.dup(1), "w", buffering=1, encoding="utf-8")
os.dup2(2, 1)
sys.stdout = sys.stderr


def send(message: dict[str, Any]) -> None:
    _proto.write(json.dumps(message, ensure_ascii=False) + "\n")
    _proto.flush()


def log(msg: str) -> None:
    print(f"[harness {time.strftime('%H:%M:%S')}] {msg}", file=sys.stderr, flush=True)


class Channel:
    """Answers from the host: llm results by id, everything else in order."""

    def __init__(self, loop: asyncio.AbstractEventLoop) -> None:
        self.loop = loop
        self.pending: dict[int, asyncio.Future[dict[str, Any]]] = {}
        self.control: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self.next_id = 0
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self) -> None:
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            try:
                message = json.loads(line)
            except ValueError:
                continue
            self.loop.call_soon_threadsafe(self._route, message)
        self.loop.call_soon_threadsafe(self._route, {"type": "eof"})

    def _route(self, message: dict[str, Any]) -> None:
        future = self.pending.pop(message.get("id", -1), None) if message.get("type", "").startswith("llm") else None
        if future is not None and not future.done():
            future.set_result(message)
        else:
            self.control.put_nowait(message)

    async def ask_llm(self, request: dict[str, Any]) -> dict[str, Any]:
        self.next_id += 1
        future: asyncio.Future[dict[str, Any]] = self.loop.create_future()
        self.pending[self.next_id] = future
        send({"type": "llm", "id": self.next_id, "request": request})
        return await future

    async def wait(self, *types: str) -> dict[str, Any]:
        while True:
            message = await self.control.get()
            if message.get("type") == "eof":
                raise SystemExit("host closed the channel")
            if message.get("type") in types:
                return message


# ---------------------------------------------------------------- the model, through the host


def bridge_llm(channel: Channel) -> Any:
    from browser_use.llm.openai.chat import ChatOpenAI
    from openai.types.chat.chat_completion import ChatCompletion

    class _Completions:
        async def create(self, **kwargs: Any) -> ChatCompletion:
            request = {k: v for k, v in kwargs.items() if k in ("messages", "response_format", "tools", "tool_choice")}
            answer = await channel.ask_llm(json.loads(json.dumps(request, default=str)))
            if answer.get("type") != "llm_result":
                raise RuntimeError(f"model call refused by the host: {answer.get('error', '?')}")
            return ChatCompletion.model_validate(answer["response"])

    class _Chat:
        completions = _Completions()

    class _Client:
        chat = _Chat()

    @dataclass
    class BridgeLLM(ChatOpenAI):
        def get_client(self) -> Any:  # type: ignore[override]
            return _Client()

    return BridgeLLM(model="muse-spark-open", api_key="none-held-here", temperature=None, frequency_penalty=None,
                     reasoning_models=None, max_completion_tokens=None, max_retries=0)


class StubLLM:
    """For the offline replay's closing summary: no model call."""

    model = "none"
    provider = "pickfit"
    name = "none"
    model_name = "none"
    _verified_api_keys = True

    async def ainvoke(self, messages: Any, output_format: Any = None, **kwargs: Any) -> Any:
        from browser_use.llm.views import ChatInvokeCompletion

        return ChatInvokeCompletion(completion="replayed", usage=None)


# ---------------------------------------------------------------- Chromium


def launch_chrome(user_agent: str) -> subprocess.Popen[bytes]:
    PROFILE.mkdir(parents=True, exist_ok=True)
    args = [CHROME, "--headless=new", f"--remote-debugging-port={CDP_PORT}", "--remote-debugging-address=127.0.0.1",
            f"--user-data-dir={PROFILE}", f"--proxy-server={PROXY}", "--proxy-bypass-list=<-loopback>",
            "--ignore-certificate-errors", f"--user-agent={user_agent}", "--window-size=1280,900",
            "--force-webrtc-ip-handling-policy=disable_non_proxied_udp", "--disable-quic",
            "--disable-background-networking", "--disable-component-update", "--disable-sync",
            "--disable-domain-reliability", "--disable-client-side-phishing-detection", "--no-pings",
            "--disable-features=OptimizationHints,MediaRouter,Translate,AutofillServerCommunication,"
            "InterestFeedContentSuggestions,CertificateTransparencyComponentUpdater",
            "--no-first-run", "--no-default-browser-check", "--metrics-recording-only", "--mute-audio",
            "--lang=en-US", "--hide-scrollbars", "--password-store=basic", "about:blank"]
    chrome_log = open(EVIDENCE / "chrome.log", "wb")
    proc = subprocess.Popen(args, stdout=chrome_log, stderr=chrome_log)
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        try:
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            opener.open(f"http://127.0.0.1:{CDP_PORT}/json/version", timeout=2).read()
            return proc
        except OSError:
            time.sleep(0.5)
    raise RuntimeError("Chromium did not open its DevTools port in 30 s")


CAPTURE_JS = r"""(async () => {
  const vis = (el) => { const r = el.getBoundingClientRect(); const s = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none'; };
  const q = (s) => Array.from(document.querySelectorAll(s));
  let sw = [];
  try { if (navigator.serviceWorker) sw = (await navigator.serviceWorker.getRegistrations())
          .map(r => ({scope: r.scope, active: !!r.active})); } catch (e) {}
  return JSON.stringify({
    url: location.href, title: document.title, lang: document.documentElement.lang || '',
    text: (document.body ? document.body.innerText : '').slice(0, %d),
    inputs: q('input:not([type=hidden]),textarea,select,[contenteditable=true]').filter(vis).length,
    passwords: q('input[type=password]').filter(vis).length,
    buttons: q('button,[role=button],input[type=submit],input[type=button]').filter(vis).length,
    canvas: q('canvas').filter(vis).length,
    forms: q('form').length,
    iframes: q('iframe').map(f => f.src).filter(Boolean).slice(0, 20),
    manifest: (document.querySelector('link[rel=manifest]') || {}).href || null,
    service_workers: sw,
    sw_controlled: !!(navigator.serviceWorker && navigator.serviceWorker.controller),
    online: navigator.onLine,
    ad_slots: q('ins.adsbygoogle,[id^=google_ads],[data-ad-slot],iframe[src*="doubleclick"],iframe[id^=google_ads]').length,
    links: q('a[href]').map(a => ({text: (a.innerText || a.getAttribute('aria-label') || '').trim().slice(0, 80),
                                  href: a.href})).slice(0, 300),
  });
})()""" % TEXT_LIMIT


async def page_session(session: Any) -> tuple[Any, str]:
    page = await session.must_get_current_page()
    return page, await page.session_id


async def evaluate(session: Any, expression: str) -> Any:
    page, sid = await page_session(session)
    result = await session.cdp_client.send.Runtime.evaluate(
        params={"expression": expression, "returnByValue": True, "awaitPromise": True}, session_id=sid)
    value = result.get("result", {}).get("value")
    return json.loads(value) if isinstance(value, str) else value


async def capture(session: Any, name: str, *, inline: bool = False) -> dict[str, Any]:
    """The page as pickfit sees it: state from the DOM, a screenshot saved as evidence."""
    try:
        state = await evaluate(session, CAPTURE_JS) or {}
    except Exception as err:  # a crashed or navigating page
        state = {"error": f"{type(err).__name__}: {err}"[:300]}
    try:
        png = await session.take_screenshot(full_page=False, format="png")
        (EVIDENCE / f"{name}.png").write_bytes(png)
        state["screenshot"] = f"{name}.png"
        if inline:
            jpeg = await session.take_screenshot(full_page=False, format="jpeg", quality=70)
            state["screenshot_jpeg_b64"] = base64.b64encode(jpeg).decode()
    except Exception as err:
        state["screenshot_error"] = f"{type(err).__name__}: {err}"[:300]
    (EVIDENCE / f"{name}.json").write_text(json.dumps({k: v for k, v in state.items() if k != "screenshot_jpeg_b64"},
                                                      ensure_ascii=False, indent=1))
    return state


async def settle(seconds: float) -> None:
    await asyncio.sleep(seconds)


def downloads(since: float) -> list[dict[str, Any]]:
    files = []
    for path in sorted(DOWNLOADS.glob("**/*")):
        if not path.is_file() or path.stat().st_mtime < since:
            continue
        data = path.read_bytes()
        files.append({"name": path.name, "size": len(data), "sha256": hashlib.sha256(data).hexdigest(),
                      "head_hex": data[:16].hex(), "text_head": data[:2000].decode("utf-8", "replace")})
    return files


# ---------------------------------------------------------------- browser-use


def make_tools() -> Any:
    """browser-use's tools minus web search, JavaScript and its scratch files; typing refuses credential fields."""
    from browser_use import Tools
    from browser_use.agent.views import ActionResult
    from browser_use.browser import BrowserSession
    from browser_use.tools.views import InputTextAction

    tools = Tools(exclude_actions=EXCLUDED_ACTIONS)
    original = tools.registry.registry.actions["input"].function

    @tools.registry.action(
        "Input text into element by index. Clears existing text by default; pass text=\"\" to clear only, or "
        "clear=False to append. Never type into password, email, phone, card or login fields.",
        param_model=InputTextAction,
    )
    async def input(params: InputTextAction, browser_session: BrowserSession, has_sensitive_data: bool = False,
                    sensitive_data: dict[str, str | dict[str, str]] | None = None) -> Any:
        node = await browser_session.get_element_by_index(params.index)
        attrs = {k.lower(): str(v).lower() for k, v in ((node.attributes or {}) if node else {}).items()}
        described = " ".join(attrs.get(k, "") for k in ("type", "name", "id", "autocomplete", "placeholder",
                                                         "aria-label", "inputmode"))
        refused = attrs.get("type") in ("password", "email", "tel") or any(h in described for h in CREDENTIAL_HINTS)
        if refused or _looks_personal(params.text):
            log(f"refused typing into a credential field: {described[:120]!r}")
            return ActionResult(error="pickfit refuses typing into credential, contact or login fields and typing "
                                      "personal data. Use the site's tool without an account.")
        return await original(params=params, browser_session=browser_session, has_sensitive_data=has_sensitive_data,
                              sensitive_data=sensitive_data)

    return tools


def _looks_personal(text: str) -> bool:
    import re

    return bool(re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", text) or re.search(r"\b(?:\d[ -]?){13,19}\b", text))


def outcome_model() -> Any:
    from pydantic import BaseModel, Field

    class WebOutcome(BaseModel):
        feature: str = Field(description="The advertised feature you exercised, in a few words")
        result_kind: Literal["text_on_page", "downloaded_file", "page_state", "none"] = Field(
            description="What now shows the result: text visible on the page, a file the site gave you, a "
                        "changed page state (an item added, a board moved), or none")
        result_text: str = Field(description="Copy exactly a short piece of visible page text (under 120 "
                                             "characters) that shows the result, or the downloaded file's name")
        blocked_by: Literal["nothing", "account_required", "paywall", "captcha", "site_error", "guard_refused",
                            "other"] = Field(description="What stopped you, if anything")
        notes: str = Field(description="One sentence on what you did and saw")

    return WebOutcome


def browser_profile(site: str, wait_between_actions: float) -> Any:
    from browser_use import BrowserProfile

    return BrowserProfile(
        cdp_url=f"http://127.0.0.1:{CDP_PORT}", is_local=False, headless=True, keep_alive=True,
        allowed_domains=[site, f"*.{site}"], enable_default_extensions=False, captcha_solver=False,
        demo_mode=False, downloads_path=str(DOWNLOADS), accept_downloads=True, auto_download_pdfs=False,
        wait_between_actions=wait_between_actions, minimum_wait_page_load_time=1.0,
        wait_for_network_idle_page_load_time=1.5, highlight_elements=False, dom_highlight_elements=False,
        viewport={"width": VIEWPORT[0], "height": VIEWPORT[1]}, device_scale_factor=1.0)


def typed_inputs(history: Any) -> tuple[list[str], list[str]]:
    typed, uploaded = [], []
    for action in history.model_actions():
        if "input" in action and isinstance(action["input"], dict):
            typed.append(str(action["input"].get("text", "")))
        if "upload_file" in action and isinstance(action["upload_file"], dict):
            uploaded.append(str(action["upload_file"].get("path", "")))
    return typed, uploaded


# ---------------------------------------------------------------- the visit


async def run(channel: Channel) -> None:
    start = await channel.wait("start")
    for d in (EVIDENCE, DOWNLOADS):
        d.mkdir(parents=True, exist_ok=True)
    chrome = launch_chrome(start["user_agent"])
    from browser_use import Agent, BrowserSession

    session = BrowserSession(browser_profile=browser_profile(start["site"], start["wait_between_actions"]))
    await session.start()
    report: dict[str, Any] = {"type": "done"}
    try:
        began = time.time()
        page, _ = await page_session(session)
        try:
            await page.goto(start["url"])
        except Exception as err:
            report["navigation_error"] = str(err)[:300]
        await settle(start.get("settle_s", 6))
        install = await capture(session, "install", inline=True)
        if install.get("service_workers"):
            await settle(4)  # let a just-registered worker activate and cache
            install["service_workers"] = (await capture(session, "install_sw")).get("service_workers")
        send({"type": "observe", "phase": "install", "state": install})
        go = await channel.wait("continue")
        if not go.get("function"):
            return
        before = await capture(session, "before")
        llm = bridge_llm(channel)
        started = time.time()
        agent = Agent(task=go["task"], llm=llm, browser_session=session, tools=make_tools(),
                      output_model_schema=outcome_model(), use_judge=False, enable_planning=False,
                      use_vision=True, max_actions_per_step=3, max_failures=3, calculate_cost=False,
                      directly_open_url=False, available_file_paths=start.get("sample_files") or None,
                      generate_gif=False, llm_timeout=180, step_timeout=300, page_extraction_llm=llm,
                      final_response_after_failure=True, max_clickable_elements_length=ELEMENTS_CHARS)
        history = await agent.run(max_steps=start["max_steps"])
        await settle(2)
        after = await capture(session, "after", inline=True)
        history.save_to_file(EVIDENCE / "agent_history.json")
        typed, uploaded = typed_inputs(history)
        structured = history.structured_output
        function = {
            "before_text": before.get("text", ""), "after": after, "downloads": downloads(started),
            "typed": typed, "uploaded": uploaded, "steps": history.number_of_steps(),
            "done": history.is_done(), "successful": history.is_successful(),
            "outcome": structured.model_dump() if structured is not None else None,
            "final_result": (history.final_result() or "")[:2000],
            "errors": [e for e in history.errors() if e][-5:],
            "urls": [u for u in history.urls() if u][-10:],
            "duration_s": round(time.time() - started, 1),
        }
        send({"type": "observe", "phase": "function", "result": function})
        go = await channel.wait("continue")
        if not go.get("offline"):
            return
        send({"type": "need_offline"})
        await channel.wait("offline_on")
        page, sid = await page_session(session)
        await session.cdp_client.send.Network.enable(session_id=sid)
        await session.cdp_client.send.Network.emulateNetworkConditions(
            params={"offline": True, "latency": 0, "downloadThroughput": -1, "uploadThroughput": -1}, session_id=sid)
        offline_started = time.time()
        try:
            await page.goto(start["url"])
        except Exception as err:
            report["offline_navigation_error"] = str(err)[:300]
        await settle(5)
        loaded = await capture(session, "offline", inline=True)
        replay: dict[str, Any] = {}
        if go.get("replay") and history.is_done():
            replayer = Agent(task=go["task"], llm=StubLLM(), browser_session=session, tools=make_tools(),
                             output_model_schema=outcome_model(), use_judge=False, enable_planning=False,
                             directly_open_url=False, available_file_paths=start.get("sample_files") or None)
            try:
                results = await replayer.rerun_history(history, skip_failures=True, delay_between_actions=1.5,
                                                       max_step_interval=5.0, summary_llm=StubLLM(),
                                                       ai_step_llm=StubLLM())
                replay["errors"] = [r.error for r in results if getattr(r, "error", None)][:5]
            except Exception as err:
                replay["error"] = f"{type(err).__name__}: {err}"[:300]
            await settle(2)
            replay["after"] = await capture(session, "offline_after", inline=True)
            replay["downloads"] = downloads(offline_started)
        send({"type": "observe", "phase": "offline", "loaded": loaded, "replay": replay})
        await channel.wait("continue")
    except Exception as err:
        report["error"] = f"{type(err).__name__}: {err}"[:1000]
        log(traceback.format_exc())
    finally:
        report["elapsed_s"] = round(time.time() - began, 1) if "began" in locals() else None
        send(report)
        try:
            await session.kill()
        except Exception:
            pass
        chrome.terminate()


def main() -> None:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    channel = Channel(loop)
    try:
        loop.run_until_complete(run(channel))
    except BaseException as err:
        send({"type": "error", "error": f"{type(err).__name__}: {err}"[:1000]})
        raise


if __name__ == "__main__":
    main()
