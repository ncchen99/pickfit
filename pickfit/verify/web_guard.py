"""Web app guard: what pickfit's browser may send while it tests a real website (P3.12).

The verifier tests sites other people run, so side effects are refused in code, not left to the
model's manners. Every request the sandbox's Chromium makes goes through one mitmproxy process (the
browser's uid can reach nothing but loopback; nftables, see web_box), and this module is that proxy's
policy. It is self-contained (stdlib, plus tldextract for the public suffix list) because mitmdump
loads it as a script inside the sandbox; the same functions are unit tested here.

Refused, whatever the agent intends:
- leaving the site: a top-level navigation to another registrable domain (assets, iframes and API calls
  to other hosts load as the page asks);
- form submissions: a top-level navigation that is not GET/HEAD;
- sign-up, log-in, posting, commenting, messaging, email, buying and booking: a request that is not
  GET/HEAD/OPTIONS whose path, GraphQL operation or body fields name one of these, or that goes to an
  auth, payment, form-to-email or messaging service; any request carrying credential-like fields or an
  email address;
- pages robots.txt disallows for pickfit-verifier; private, loopback and link-local addresses; the
  browser tool's vendor; and, in the offline phase, everything.

It also records each flow (method, host, site, type, size, decision) so the run can say how many
third-party sites the page contacted, whether an ad network loaded, and whether what the agent typed or
the file it chose left the device (find_leaks).
"""

from __future__ import annotations

import base64
import ipaddress
import json
import re
import urllib.parse
import urllib.robotparser
from dataclasses import asdict, dataclass, field
from typing import Any

ROBOTS_TOKEN = "pickfit-verifier"
INFO_URL = "https://github.com/ncchen99/pickfit"
UA_SUFFIX = f"{ROBOTS_TOKEN}/0.1 (+{INFO_URL}; one test visit, no sign-ups or submissions)"
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
BODY_SCAN_BYTES = 256_000

# Path, GraphQL-operation and field words that mean a side effect on someone else's site when a request
# changes something (not GET/HEAD/OPTIONS). Matched as whole words after camelCase and separator splits,
# and as joined neighbours ("sign" "up" -> signup), so "/api/postprocess" is not "post".
SIDE_EFFECT_WORDS = frozenset("""
login logon signin signup register registration auth authenticate authorize oauth oauth2 sso session sessions
password passwd forgot verify magiclink otp twofactor 2fa
subscribe subscription subscriptions newsletter unsubscribe waitlist
checkout cart basket order orders purchase buy pay payment payments billing charge invoice donate donation
booking bookings reserve reservation reservations appointment appointments
comment comments reply replies post posts publish tweet
message messages msg dm dms inbox conversation conversations contact contacts feedback support ticket tickets
email emails mail mailer sendmail sms invite invites invitation share follow unfollow like likes upvote vote votes
review reviews rating ratings report flag account accounts user users profile signout logout statuses
""".split())

# Body field names that carry credentials or personal data: a request with one is never sent.
CREDENTIAL_FIELDS = frozenset("""
password passwd pwd passcode pass newpassword currentpassword confirmpassword
email emailaddress mail phone phonenumber telephone tel mobile
cardnumber ccnumber ccnum cardnum cvv cvc cvv2 securitycode expiry iban ssn taxid
otp onetimecode totp grecaptcharesponse hcaptcharesponse cfturnstileresponse captcha recaptcha
""".split())

# Hosts (and their subdomains) that only sign people in, take payments, send forms by email or post
# messages. A request that changes something is never sent to them; pages may still load their scripts.
SIDE_EFFECT_HOSTS = (
    "accounts.google.com", "oauth2.googleapis.com", "identitytoolkit.googleapis.com",
    "securetoken.googleapis.com", "appleid.apple.com", "login.microsoftonline.com", "login.live.com",
    "auth0.com", "clerk.com", "clerk.dev", "accounts.dev", "okta.com", "stytch.com", "workos.com",
    "stripe.com", "stripe.network", "paypal.com", "braintreegateway.com", "paddle.com", "lemonsqueezy.com",
    "gumroad.com", "checkout.shopify.com", "squareup.com", "adyen.com", "razorpay.com",
    "formspree.io", "getform.io", "formsubmit.co", "usebasin.com", "web3forms.com", "formcarry.com",
    "emailjs.com", "api.emailjs.com", "list-manage.com", "mailchimp.com", "sendgrid.net", "sendgrid.com",
    "mailgun.net", "mailgun.com", "postmarkapp.com", "convertkit.com", "kit.com", "buttondown.email",
    "substack.com", "beehiiv.com", "tally.so", "typeform.com", "jotform.com", "airtable.com",
    "hooks.slack.com", "discord.com", "discordapp.com", "api.telegram.org", "api.twitter.com", "x.com",
    "graph.facebook.com", "calendly.com", "cal.com", "disqus.com", "giscus.app", "utteranc.es",
    "intercom.io", "crisp.chat", "tawk.to",
)

# The browser tool's own services and Chrome's background services: refused and left out of every count.
NOISE_HOSTS = (
    "browser-use.com", "clients2.google.com", "update.googleapis.com", "optimizationguide-pa.googleapis.com",
    "safebrowsing.googleapis.com", "content-autofill.googleapis.com", "redirector.gvt1.com",
)

# Ad networks (our own short list of well-known ad-serving domains, not a third-party tracker list).
AD_HOSTS = (
    "doubleclick.net", "googlesyndication.com", "googleadservices.com", "adservice.google.com",
    "amazon-adsystem.com", "adnxs.com", "taboola.com", "outbrain.com", "criteo.com", "criteo.net",
    "pubmatic.com", "rubiconproject.com", "openx.net", "media.net", "carbonads.net", "carbonads.com",
    "buysellads.com", "buysellads.net", "ethicalads.io", "ezoic.net", "adsterra.com", "propellerads.com",
    "popads.net", "mgid.com", "revcontent.com", "sharethrough.com", "adform.net", "yieldmo.com",
)

_EMAIL = re.compile(r"[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9-]{1,63}(?:\.[A-Za-z0-9-]{1,63})*\.[A-Za-z]{2,24}")
_CAMEL = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")
_WORD_SPLIT = re.compile(r"[^a-z0-9]+")
_GRAPHQL_OP = re.compile(r"\b(?:mutation)\s+([A-Za-z_][A-Za-z0-9_]*)")


# ---------------------------------------------------------------- domains


_extractor: Any = None


def registrable(host: str) -> str:
    """The registrable domain (eTLD+1, private suffixes included, so a.github.io and b.github.io differ).

    Uses tldextract's bundled public suffix list; it never fetches the list. An IP literal or a bare
    name is its own site.
    """
    global _extractor
    host = (host or "").lower().strip(".")
    if not host or _is_ip(host) or "." not in host:
        return host
    if _extractor is None:
        import tldextract

        _extractor = tldextract.TLDExtract(suffix_list_urls=(), include_psl_private_domains=True,
                                           cache_dir=None)
    parts = _extractor(host)
    return parts.top_domain_under_public_suffix or host


def _is_ip(host: str) -> bool:
    try:
        ipaddress.ip_address(host.strip("[]"))
    except ValueError:
        return False
    return True


def _under(host: str, domains: tuple[str, ...]) -> bool:
    host = host.lower().strip(".")
    return any(host == d or host.endswith("." + d) for d in domains)


def is_private_host(host: str) -> bool:
    host = host.lower().strip(".").strip("[]")
    if host == "localhost" or host.endswith(".localhost") or host.endswith(".local") or host.endswith(".internal"):
        return True
    if not _is_ip(host):
        return False
    ip = ipaddress.ip_address(host)
    return not ip.is_global or ip.is_multicast


def is_noise(host: str) -> bool:
    return _under(host, NOISE_HOSTS)


def is_ad_host(host: str) -> bool:
    return _under(host, AD_HOSTS)


# ---------------------------------------------------------------- words


def words(text: str) -> set[str]:
    """Whole words of a path, operation name or field name, plus joined neighbours."""
    parts = [w for w in _WORD_SPLIT.split(_CAMEL.sub(" ", text).lower()) if w]
    joined = {a + b for a, b in zip(parts, parts[1:])}
    return set(parts) | joined


def _norm_field(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", _CAMEL.sub("", name).lower())


def body_fields(body: bytes, content_type: str) -> tuple[set[str], str]:
    """(field names, text) of a request body: form, multipart or JSON keys at any depth."""
    text = body[:BODY_SCAN_BYTES].decode("utf-8", "replace")
    ctype = content_type.lower()
    names: set[str] = set()
    if "json" in ctype or text.lstrip().startswith(("{", "[")):
        try:
            names |= _json_keys(json.loads(text))
        except ValueError:
            pass
    if "x-www-form-urlencoded" in ctype or (not names and "=" in text and "\n" not in text.strip()):
        names |= {k for k, _ in urllib.parse.parse_qsl(text, keep_blank_values=True)}
    if "multipart/form-data" in ctype:
        names |= set(re.findall(r'content-disposition:[^\r\n]*\bname="([^"]*)"', text, re.I))
    return names, text


def _json_keys(value: Any, depth: int = 0) -> set[str]:
    if depth > 12:
        return set()
    if isinstance(value, dict):
        keys = {str(k) for k in value}
        for v in value.values():
            keys |= _json_keys(v, depth + 1)
        return keys
    if isinstance(value, list):
        keys: set[str] = set()
        for v in value[:200]:
            keys |= _json_keys(v, depth + 1)
        return keys
    return set()


def credential_fields(names: set[str]) -> set[str]:
    return {n for n in names if _norm_field(n) in CREDENTIAL_FIELDS or _norm_field(n).endswith("password")}


# ---------------------------------------------------------------- robots.txt


def robots_parser(robots_txt: str | None, status: int | None) -> urllib.robotparser.RobotFileParser:
    """A parser for a fetched robots.txt; 401/403 and 5xx disallow everything, 404 allows everything."""
    parser = urllib.robotparser.RobotFileParser()
    if status is None or status >= 500 or status in (401, 403):
        parser.disallow_all = True
    elif status >= 400 or robots_txt is None:
        parser.allow_all = True
    else:
        parser.parse(robots_txt.splitlines())
    return parser


def robots_allows(parser: urllib.robotparser.RobotFileParser, url: str) -> bool:
    return parser.can_fetch(ROBOTS_TOKEN, url)


def crawl_delay(parser: urllib.robotparser.RobotFileParser) -> float | None:
    delay = parser.crawl_delay(ROBOTS_TOKEN)
    return float(delay) if delay is not None else None


# ---------------------------------------------------------------- the decision


@dataclass(frozen=True)
class Policy:
    site: str  # the registrable domain under test
    robots_txt: str | None = None
    robots_status: int | None = 404
    offline: bool = False

    def robots(self) -> urllib.robotparser.RobotFileParser:
        return robots_parser(self.robots_txt, self.robots_status)


@dataclass(frozen=True)
class Request:
    method: str
    url: str
    headers: dict[str, str] = field(default_factory=dict)  # lower-case names
    body: bytes = b""

    @property
    def parts(self) -> urllib.parse.SplitResult:
        return urllib.parse.urlsplit(self.url)

    @property
    def host(self) -> str:
        return (self.parts.hostname or "").lower()

    @property
    def mode(self) -> str:
        return self.headers.get("sec-fetch-mode", "")

    @property
    def dest(self) -> str:
        return self.headers.get("sec-fetch-dest", "")

    @property
    def top_level(self) -> bool:
        """A top-level navigation: the address bar, a link, a form, a redirect of one.

        Chrome sends Sec-Fetch-* only to secure origins; on plain http a navigation is told by the
        Upgrade-Insecure-Requests and HTML Accept headers every navigation carries (frames too: refused
        off the site, which mixed-content rules mostly do anyway).
        """
        if self.mode:
            return self.mode == "navigate" and self.dest in ("document", "")
        return (self.headers.get("upgrade-insecure-requests") == "1"
                and self.headers.get("accept", "").startswith("text/html"))

    @property
    def kind(self) -> str:
        if self.top_level:
            return "navigation"
        if self.mode == "navigate":
            return "frame"
        if self.headers.get("upgrade", "").lower() == "websocket" or self.mode == "websocket":
            return "websocket"
        return self.dest or ("fetch" if self.mode in ("cors", "same-origin", "no-cors") else "other")


@dataclass(frozen=True)
class Decision:
    allow: bool
    reason: str


ALLOW = Decision(True, "")


SECRET_QUERY_FIELDS = frozenset({"password", "passwd", "pwd", "passcode", "cvv", "cvc", "cardnumber", "ccnumber",
                                 "otp", "onetimecode"})


def _query_credentials(parts: urllib.parse.SplitResult) -> set[str]:
    """Secret-looking query parameters (an email field with no address in it is left to _EMAIL)."""
    names = {k for k, _ in urllib.parse.parse_qsl(parts.query, keep_blank_values=True)}
    return {n for n in names if _norm_field(n) in SECRET_QUERY_FIELDS or _norm_field(n).endswith("password")}


def decide(req: Request, policy: Policy) -> Decision:
    """Allow or refuse one request (see the module docstring)."""
    parts = req.parts
    method = req.method.upper()
    host = req.host
    if parts.scheme not in ("http", "https", "ws", "wss"):
        return Decision(False, f"scheme {parts.scheme or '?'}")
    if not host:
        return Decision(False, "no host")
    if is_noise(host):
        return Decision(False, "browser or tool background service")
    if is_private_host(host):
        return Decision(False, "private, loopback or link-local address")
    if policy.offline:
        return Decision(False, "offline phase")
    same_site = registrable(host) == policy.site
    if req.top_level:
        if not same_site:
            return Decision(False, f"navigation off the site to {registrable(host)}")
        if method not in ("GET", "HEAD"):
            return Decision(False, f"form submission ({method} navigation)")
        if not robots_allows(policy.robots(), req.url):
            return Decision(False, "robots.txt disallows this page")
    if _query_credentials(parts):
        return Decision(False, "credentials in the address")
    if _EMAIL.search(urllib.parse.unquote_plus(parts.query)):
        return Decision(False, "an email address in the address")
    if method in SAFE_METHODS:
        return ALLOW
    if req.kind == "frame":
        return Decision(False, f"form submission in a frame ({method})")
    if _under(host, SIDE_EFFECT_HOSTS):
        return Decision(False, f"{method} to a sign-in, payment, form or messaging service ({host})")
    hits = words(urllib.parse.unquote(parts.path)) & SIDE_EFFECT_WORDS
    if hits:
        return Decision(False, f"{method} to a side-effect path ({', '.join(sorted(hits))})")
    names, text = body_fields(req.body, req.headers.get("content-type", ""))
    ops = {w for op in _GRAPHQL_OP.findall(text) for w in words(op)} & SIDE_EFFECT_WORDS
    if ops:
        return Decision(False, f"GraphQL mutation ({', '.join(sorted(ops))})")
    creds = credential_fields(names)
    if creds:
        return Decision(False, f"credential or personal fields ({', '.join(sorted(creds)[:4])})")
    if {w for n in names for w in words(n)} & {"subject", "recipient", "recipients"}:
        return Decision(False, "a message form (subject or recipient fields)")
    if _EMAIL.search(text):
        return Decision(False, "an email address in the body")
    return ALLOW


# ---------------------------------------------------------------- what left the device


def encodings(needle: str) -> set[str]:
    """Forms a typed string takes on the wire: as is, URL-encoded (both ways), JSON-escaped, base64."""
    forms = {needle, urllib.parse.quote(needle), urllib.parse.quote_plus(needle),
             json.dumps(needle)[1:-1], base64.b64encode(needle.encode()).decode().rstrip("=")}
    return {f for f in forms if f}


def find_leaks(flows: list[dict[str, Any]], needles: list[str]) -> list[dict[str, Any]]:
    """Flows whose address or body carries one of `needles` (typed text, a chosen file's marker).

    Needles shorter than 4 characters are skipped: they match by chance. Each hit says which needle,
    which host and whether the guard let it through.
    """
    hits: list[dict[str, Any]] = []
    wanted = [(n, encodings(n)) for n in dict.fromkeys(needles) if len(n.strip()) >= 4]
    for flow in flows:
        if is_noise(flow.get("host", "")):
            continue
        haystack = f"{flow.get('url', '')}\n{flow.get('body', '')}\n{flow.get('ws', '')}"
        lowered = haystack.lower()
        for needle, forms in wanted:
            if any(f in haystack or f.lower() in lowered for f in forms):
                hits.append({"needle": needle, "host": flow.get("host"), "site": flow.get("site"),
                             "method": flow.get("method"), "kind": flow.get("kind"),
                             "sent": bool(flow.get("allowed"))})
    return hits


def summarize(flows: list[dict[str, Any]], site: str) -> dict[str, Any]:
    """Counts for the run: hosts and third-party sites contacted, ad networks, refused requests."""
    real = [f for f in flows if not is_noise(f.get("host", ""))]
    sent = [f for f in real if f.get("allowed")]
    third = sorted({f["site"] for f in sent if f.get("site") and f["site"] != site})
    ads = sorted({f["site"] for f in sent if is_ad_host(f.get("host", ""))})
    refused = [{"method": f.get("method"), "host": f.get("host"), "kind": f.get("kind"), "reason": f.get("reason")}
               for f in real if not f.get("allowed")]
    return {"requests": len(sent), "hosts": len({f.get("host") for f in sent}), "third_party_sites": third,
            "third_party_count": len(third), "ad_networks": ads, "refused": refused[:50],
            "refused_count": len(refused)}


# ---------------------------------------------------------------- the mitmproxy addon


@dataclass
class FlowLog:
    method: str
    url: str
    host: str
    site: str
    kind: str
    allowed: bool
    reason: str
    status: int | None = None
    body: str = ""
    ws: str = ""
    size: int = 0


class Guard:
    """mitmproxy addon: decide every request, log every flow (inside the sandbox only)."""

    def __init__(self, config_path: str, log_path: str, offline_flag: str) -> None:
        with open(config_path, encoding="utf-8") as f:
            config = json.load(f)
        self.policy = Policy(site=config["site"], robots_txt=config.get("robots_txt"),
                             robots_status=config.get("robots_status"))
        self.log_path = log_path
        self.offline_flag = offline_flag
        self.logs: dict[int, FlowLog] = {}

    def _offline(self) -> bool:
        import os

        return os.path.exists(self.offline_flag)

    def _write(self, log: FlowLog) -> None:
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(asdict(log), ensure_ascii=False) + "\n")

    def request(self, flow: Any) -> None:
        from mitmproxy import http

        req = flow.request
        headers = {k.lower(): v for k, v in req.headers.items()}
        body = req.raw_content or b""
        r = Request(method=req.method, url=req.pretty_url, headers=headers, body=body)
        policy = Policy(self.policy.site, self.policy.robots_txt, self.policy.robots_status, self._offline())
        decision = decide(r, policy)
        if policy.offline:  # fail like a cut cable, not with a page: a service worker falls back on errors only
            self._write(FlowLog(method=r.method, url=r.url[:2000], host=r.host, site=registrable(r.host),
                                kind=r.kind, allowed=False, reason="offline phase"))
            flow.kill()
            return
        log = FlowLog(method=r.method, url=r.url[:2000], host=r.host, site=registrable(r.host), kind=r.kind,
                      allowed=decision.allow, reason=decision.reason, body=body[:BODY_SCAN_BYTES].decode("utf-8", "replace"),
                      size=len(body))
        if not decision.allow:
            flow.response = http.Response.make(
                403, f"Blocked by pickfit's test guard: {decision.reason}".encode(),
                {"Content-Type": "text/plain; charset=utf-8", "X-Pickfit-Guard": "blocked"})
            self._write(log)
            return
        self.logs[id(flow)] = log

    def response(self, flow: Any) -> None:
        log = self.logs.pop(id(flow), None)
        if log is not None:
            log.status = flow.response.status_code if flow.response else None
            self._write(log)

    def error(self, flow: Any) -> None:
        log = self.logs.pop(id(flow), None)
        if log is not None:
            log.reason = f"error: {flow.error}"[:200] if flow.error else "error"
            self._write(log)

    def websocket_message(self, flow: Any) -> None:
        message = flow.websocket.messages[-1]
        if not message.from_client:
            return
        if self._offline():
            flow.kill()
            return
        text = message.content[:BODY_SCAN_BYTES].decode("utf-8", "replace") if isinstance(message.content, bytes) \
            else str(message.content)[:BODY_SCAN_BYTES]
        host = flow.request.host
        self._write(FlowLog(method="WS", url=flow.request.pretty_url[:2000], host=host, site=registrable(host),
                            kind="websocket", allowed=True, reason="", ws=text, size=len(text)))


def _addons() -> list[Any]:
    import os

    config = os.environ.get("PICKFIT_GUARD_CONFIG")
    if not config:
        return []
    return [Guard(config, os.environ["PICKFIT_GUARD_LOG"], os.environ["PICKFIT_GUARD_OFFLINE"])]


try:  # mitmdump -s web_guard.py: register the addon; a plain import (tests, pickfit) gets none
    import mitmproxy  # noqa: F401

    addons = _addons()
except ImportError:
    addons = []
