"""pickfit.verify.box_needs: which box a record needs, read from its extraction (no network, no model)."""

from __future__ import annotations

from typing import Any

import pytest

from pickfit.schema import ExtractionResult
from pickfit.verify.box_needs import (GPU_MAX_USD_ENV, box_needs, gpu_cost_ceiling, gpu_tier, needs_audio,
                                      needs_toolchain, vram_gb)
from test_profiles import cited, extraction


def ex(**over: Any) -> ExtractionResult:
    data = extraction(install_methods=[{"method": "pipx", "command": "pipx install tool", "platforms": []}])
    pre = over.pop("pre", None)
    if pre:
        data["prerequisites"] = {**data["prerequisites"], **pre}
    data.update(over)
    return ExtractionResult.model_validate(data)


@pytest.mark.parametrize("text, gb", [("Needs 8GB VRAM", 8.0), ("at least 12 GB of GPU memory", 12.0),
                                      ("VRAM: 24 GB", 24.0), ("VRAM >= 6GB", 6.0), ("runs on 16G video memory", 16.0),
                                      ("needs 32 GB RAM", None), ("A GPU helps", None)])
def test_vram_is_read_only_when_it_names_gpu_memory(text: str, gb: float | None) -> None:
    assert vram_gb([text]) == gb


def test_the_smallest_card_with_the_memory() -> None:
    assert [gpu_tier(g) for g in (None, 8, 16, 16.5, 24, 40)] == ["T4", "T4", "T4", "L4", "L4", None]


def test_an_optional_gpu_stays_on_the_cpu() -> None:
    assert box_needs(ex(pre={"gpu": cited("optional", "CUDA is optional")})).gpu is None
    need = box_needs(ex(pre={"gpu": cited("required", "requires CUDA")}))
    assert need.gpu == "T4" and need.blocked is None and need.describe() == "GPU T4"


def test_the_gpu_cost_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    gpu = ex(pre={"gpu": cited("required", "requires CUDA")})
    assert gpu_cost_ceiling("T4", 1320) == pytest.approx(2 * 1320 * 0.59 / 3600)
    assert box_needs(gpu, max_gpu_usd=0.2).blocked.startswith("needs a GPU; a T4 box could cost up to US$0.43")
    # A build box lives longer, so the same card costs more and may cross the cap.
    built = ex(pre={"gpu": cited("required", "requires CUDA")},
               install_methods=[{"method": "cargo", "command": "cargo install tool", "platforms": []}])
    assert box_needs(built, max_gpu_usd=0.6).gpu == "T4"
    assert box_needs(built, toolchain_lifetime_s=2820, max_gpu_usd=0.6).blocked
    monkeypatch.setenv(GPU_MAX_USD_ENV, "0.01")
    assert box_needs(gpu).gpu is None
    assert box_needs(gpu, gpu_available=False).blocked == "needs a GPU"


def test_audio_from_packages_words_or_a_readme_that_means_it() -> None:
    assert needs_audio(ex(pre={"system_packages": [cited("portaudio19-dev", "apt install portaudio19-dev")]}))
    assert needs_audio(ex(summary=cited("Local speech-to-text for the terminal.", "speech-to-text")))
    assert needs_audio(ex(features=[cited("push-to-talk dictation", "Hold a key to dictate")]))
    assert not needs_audio(ex())
    # A README that mentions a microphone once, in passing, is not enough; twice is.
    assert not needs_audio(ex(), "Unlike voice-recording apps, this edits text.")
    assert needs_audio(ex(), "Records from your microphone. Pick the microphone with --device.")


def test_toolchain_when_the_first_install_path_builds() -> None:
    assert needs_toolchain(ex(install_methods=[{"method": "go", "command": "go install example.com/t@latest",
                                                "platforms": []}]))
    assert needs_toolchain(ex(install_methods=[{"method": "source", "command": "git clone x && cd x && make install",
                                                "platforms": []}]))
    assert not needs_toolchain(ex())
    assert not needs_toolchain(ex(install_methods=[]))
