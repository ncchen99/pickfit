"""What kind of Linux box a record needs: an NVIDIA GPU (and how much memory on it), a simulated microphone, a build
toolchain. The watch reads this for every repository it verifies (watch.live_steps), so a speech tool, a local model
or a Rust CLI built from source gets the box it can run in instead of failing in the plain one.

Only signals the extraction already holds are read (its fields and their verbatim quotes), plus the README when the
caller has it; nothing is fetched and no model is asked.

- GPU: prerequisites.gpu is "required". The card is the smallest whose memory covers what the sources state
  (T4 16 GB, L4 24 GB); a stated need above 24 GB cannot be met and is said so. An "optional" GPU stays on the CPU:
  the smoke test runs the smallest model on the CPU path. A GPU box costs per second while it lives, the agent's box
  and the replay's each, so a worst-case GPU cost above GPU_MAX_USD (PICKFIT_GPU_MAX_USD) refuses the GPU rather
  than run it.
- Audio: the sources describe recording, a microphone, speech to text, dictation or voice input, or the tool needs
  an audio capture library (PortAudio, ALSA, PulseAudio). The box gets audio.py's simulated microphone, which
  limits.py's audio checks already cover.
- Services: the tool needs PostgreSQL or Redis, or it is an HTTP/API client with nothing to talk to: the box gets
  services.py's PostgreSQL, Redis and HTTP mock, which the box user starts on 127.0.0.1 only.
- Toolchain: the install step pickfit would run first builds from source (cargo or go install/build, make, cmake,
  meson, ./configure), or every install path does. A prebuilt binary or a package manager path ranked first needs
  no build box.

GPU only runs under gVisor on Modal (modal_box.py), so a GPU box is never a VM; the EC2 and Docker runners have no
GPU, so callers ask for one only with the Modal runner.
"""

from __future__ import annotations

import os
import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from pickfit.verify.box import COMPILES
from pickfit.verify.modal_box import GPU_USD_PER_S

# (card, its memory in GB), smallest first. A10 has the same 24 GB as L4 at a higher rate, so it is never chosen.
GPU_TIERS: tuple[tuple[str, float], ...] = (("T4", 16.0), ("L4", 24.0))
GPU_MAX_USD_ENV = "PICKFIT_GPU_MAX_USD"
GPU_MAX_USD = 1.50  # the most one record's GPU time may cost: agent box and replay box, each its whole lifetime
BOXES_PER_RUN = 2  # the agent's box and the fresh replay box

_GB = r"(\d+(?:\.\d+)?)\s*(?:GB|GiB|G)\b"
_VRAM_WORDS = r"(?:VRAM|vram|GPU\s*(?:memory|RAM|mem)|video\s*(?:memory|RAM)|graphics\s*memory)"
_VRAM = (re.compile(_GB + r"\s*(?:of\s+)?" + _VRAM_WORDS, re.I),
         re.compile(_VRAM_WORDS + r"\s*(?:of|:|>=|≥|at\s+least|minimum)?\s*" + _GB, re.I))
_AUDIO_WORDS = re.compile(
    r"\bmicrophones?\b|\bmic\b|speech[- ]to[- ]text|\bSTT\b|\btranscrib\w*|\btranscription\b|\bdictat\w*|"
    r"voice[- ](?:input|typing|commands?|recording|recorder|assistant|chat|notes?|control)|"
    r"record(?:s|ing)?\s+(?:audio|sound|voice|your\s+voice)|audio\s+record\w*|push[- ]to[- ]talk|wake[- ]?word|"
    r"\blive\s+captions?\b", re.I)
_AUDIO_PACKAGES = re.compile(r"portaudio|libasound|\balsa\b|pulseaudio|libpulse|pipewire|\bsox\b|pyaudio|"
                             r"sounddevice", re.I)
_BUILDS = re.compile(r"(?:^|[;&|]\s*|\s)(?:make|cmake|meson|ninja)\b|\./configure\b|\bautogen\.sh\b", re.I)


@dataclass(frozen=True)
class BoxNeeds:
    gpu: str | None = None  # "T4" or "L4"
    audio: bool = False
    toolchain: bool = False
    services: bool = False
    blocked: str | None = None  # why no box pickfit can give runs it (a GPU it cannot have), or None
    why: tuple[str, ...] = field(default_factory=tuple)  # one short reason per need, for the log

    def describe(self) -> str:
        parts = [p for p, on in ((f"GPU {self.gpu}", self.gpu), ("microphone", self.audio),
                                 ("toolchain", self.toolchain), ("services", self.services)) if on]
        return ", ".join(parts) or "plain box"


def gpu_max_usd() -> float:
    given = os.environ.get(GPU_MAX_USD_ENV, "").strip()
    try:
        return float(given) if given else GPU_MAX_USD
    except ValueError:
        return GPU_MAX_USD


def gpu_cost_ceiling(gpu: str, lifetime_s: float, boxes: int = BOXES_PER_RUN) -> float:
    """The most the GPU of one record's boxes can cost: each box alive for its whole lifetime."""
    return boxes * lifetime_s * GPU_USD_PER_S[gpu]


def _value(cited: Any) -> Any:
    return getattr(cited, "value", None) if cited is not None else None


def _texts(ex: Any, readme: str | None) -> list[str]:
    """The extraction's own words: values and their quotes, then the README."""
    out: list[str] = []

    def add(cited: Any) -> None:
        for part in (_value(cited), getattr(cited, "quote", None)):
            if isinstance(part, str) and part:
                out.append(part)

    for name in ("name", "summary"):
        add(getattr(ex, name, None))
    pre = getattr(ex, "prerequisites", None)
    if pre is not None:
        for name in ("gpu", "min_ram_gb"):
            add(getattr(pre, name, None))
        for name in ("runtimes", "system_packages"):
            for item in getattr(pre, name, None) or []:
                add(item)
    for name in ("features", "use_cases", "manual_steps"):
        for item in getattr(ex, name, None) or []:
            add(item)
    if readme:
        out.append(readme)
    return out


def vram_gb(texts: Iterable[str]) -> float | None:
    """The largest GPU memory the sources state, in GB, or None."""
    found = [float(m.group(1)) for text in texts for pattern in _VRAM for m in pattern.finditer(text)]
    return max(found) if found else None


def gpu_tier(need_gb: float | None) -> str | None:
    """The smallest card that has `need_gb` (T4 when nothing is stated), or None when none has it."""
    for card, memory in GPU_TIERS:
        if need_gb is None or need_gb <= memory:
            return card
    return None


def needs_audio(ex: Any, readme: str | None = None) -> bool:
    pre = getattr(ex, "prerequisites", None)
    packages = [_value(p) or "" for p in (getattr(pre, "system_packages", None) or [])]
    packages += [_value(p) or "" for p in (getattr(pre, "runtimes", None) or [])]
    if any(_AUDIO_PACKAGES.search(p) for p in packages):
        return True
    own = _texts(ex, None)  # the extraction's words first; a README mentions a microphone in passing more often
    if any(_AUDIO_WORDS.search(t) for t in own):
        return True
    return bool(readme) and len(_AUDIO_WORDS.findall(readme)) >= 2


def needs_toolchain(ex: Any) -> bool:
    """Does the install step pickfit runs first build from source (or does every path)?"""
    from pickfit.verify.plan import plan_for

    try:
        candidates = plan_for(ex, "linux").candidates
    except Exception:  # noqa: BLE001 - an odd extraction gets the plain box, as before
        candidates = []
    commands = [c.command for c in candidates] or [m.command for m in getattr(ex, "install_methods", None) or []]
    if not commands:
        return False

    def builds(command: str) -> bool:
        return bool(COMPILES.search(command) or _BUILDS.search(command))

    return builds(commands[0]) or all(builds(c) for c in commands)


def box_needs(ex: Any, *, readme: str | None = None, lifetime_s: float = 22 * 60,
              toolchain_lifetime_s: float | None = None, gpu_available: bool = True,
              max_gpu_usd: float | None = None) -> BoxNeeds:
    """The box this record needs.

    gpu_available: the runner can give a GPU (Modal). lifetime_s: each box's lifetime; toolchain_lifetime_s: a build
    box's (longer), used for the GPU cost when the record also builds from source.
    """
    why: list[str] = []
    audio = needs_audio(ex, readme)
    if audio:
        why.append("records audio -> simulated microphone")
    toolchain = needs_toolchain(ex)
    if toolchain:
        why.append("builds from source -> toolchain")
    from pickfit.verify.services import needs_services

    services = needs_services(ex, readme)
    if services:
        why.append("needs a database or a server to talk to -> PostgreSQL, Redis, HTTP mock")
    lifetime = max(lifetime_s, toolchain_lifetime_s or 0) if toolchain else lifetime_s
    gpu = None
    blocked = None
    pre = getattr(ex, "prerequisites", None)
    if _value(getattr(pre, "gpu", None)) == "required":
        need = vram_gb(_texts(ex, readme))
        card = gpu_tier(need)
        cap = gpu_max_usd() if max_gpu_usd is None else max_gpu_usd
        if not gpu_available:
            blocked = "needs a GPU"
        elif card is None:
            blocked = f"needs a GPU with {need:g} GB of memory; pickfit's largest has {GPU_TIERS[-1][1]:g} GB"
        elif gpu_cost_ceiling(card, lifetime) > cap:
            blocked = (f"needs a GPU; a {card} box could cost up to US${gpu_cost_ceiling(card, lifetime):.2f}, "
                       f"over the US${cap:.2f} cap for one record ({GPU_MAX_USD_ENV})")
        else:
            gpu = card
            why.insert(0, f"GPU required{f' ({need:g} GB stated)' if need else ''} -> {card}")
    return BoxNeeds(gpu=gpu, audio=audio, toolchain=toolchain, services=services, blocked=blocked, why=tuple(why))
