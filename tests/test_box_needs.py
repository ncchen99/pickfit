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


def test_services_for_a_database_or_an_http_client() -> None:
    from pickfit.verify.services import needs_services

    assert needs_services(ex(pre={"runtimes": [cited("PostgreSQL 14+", "Requires PostgreSQL 14+")]}))
    assert needs_services(ex(summary=cited("A REST client for the terminal.", "a terminal HTTP client")))
    assert not needs_services(ex())
    assert not needs_services(ex(), "Exports to Postgres if you want.")  # one passing mention in a README
    assert box_needs(ex(summary=cited("Redis TUI", "browse Redis keys"))).describe() == "services"


def test_the_services_image_and_helper() -> None:
    from pickfit.verify.linux_box import image_recipe
    from pickfit.verify.services import (HELPER, HELPER_PATH, MOCK_PATH, SERVICE_PACKAGES, SERVICES_COMMANDS,
                                         SERVICES_INSTALL)

    recipe = image_recipe(services=True)
    assert recipe.kinds == ("svc",) and set(SERVICE_PACKAGES) <= set(recipe.packages)
    assert recipe.commands == SERVICES_COMMANDS and recipe.tag("plain").startswith("pickfit-sbx-svc:")
    assert SERVICES_COMMANDS[-1] == SERVICES_INSTALL  # the helper last: editing it rebuilds one layer
    assert image_recipe().tag("plain") == "plain"  # the plain box is unchanged
    assert HELPER_PATH in SERVICES_INSTALL and MOCK_PATH in SERVICES_INSTALL
    # Every service binds to loopback only, and nothing in the helper asks for root.
    assert "--bind 127.0.0.1" in HELPER and "-h 127.0.0.1" in HELPER and "127.0.0.1 8080" in HELPER
    assert "sudo" not in HELPER and "su " not in HELPER and "0.0.0.0" not in HELPER


def test_packages_the_sources_name_are_planned_for_pickfits_root() -> None:
    tool = ex(pre={"system_packages": [cited("ffmpeg", "requires ffmpeg"), cited("libxkbcommon-dev", "xkb headers")]})
    need = box_needs(tool)
    assert need.packages == ("ffmpeg", "libxkbcommon-dev")
    assert need.describe() == "packages ffmpeg libxkbcommon-dev"
    assert "system packages -> pickfit's root installs ffmpeg, libxkbcommon-dev" in need.why
    assert box_needs(ex()).packages == () and box_needs(ex()).describe() == "plain box"
    # A README's apt line counts only after an attempt that stopped for lack of root; the tool is never its own package.
    readme = "sudo apt-get install -y libudev-dev tool"
    assert box_needs(ex(), readme=readme).packages == ()
    assert box_needs(ex(), readme=readme, earlier_reason="needs_root", own_names=("tool",)).packages == (
        "libudev-dev",)
