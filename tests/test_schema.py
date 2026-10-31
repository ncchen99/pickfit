import copy
import json
from pathlib import Path
from typing import Literal

import pytest
from pydantic import BaseModel, ValidationError, create_model

from pickfit.schema import (
    SETUP_MAX,
    Cited,
    ExtractionResult,
    SmokeTest,
    SoftwareRecord,
    binding_cap,
    meta_strict_schema,
    record_json_schema,
    render_schema_files,
    usage_outcomes_weight,
)

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = Path(__file__).parent / "fixtures" / "software_example.json"
STRICT_KEYWORDS = {
    "type", "properties", "required", "additionalProperties",
    "items", "enum", "anyOf", "description",
}


@pytest.fixture
def example() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def schema_nodes(node: dict):
    yield node
    for sub in node.get("properties", {}).values():
        yield from schema_nodes(sub)
    if "items" in node:
        yield from schema_nodes(node["items"])
    for sub in node.get("anyOf", []):
        yield from schema_nodes(sub)


def assert_strict(schema: dict) -> None:
    objects = 0
    for node in schema_nodes(schema):
        assert set(node) <= STRICT_KEYWORDS, f"unsupported keywords: {set(node) - STRICT_KEYWORDS}"
        if node.get("type") == "object":
            objects += 1
            assert node["additionalProperties"] is False
            assert node["required"] == list(node["properties"])
    assert objects > 0


# --- SoftwareRecord ----------------------------------------------------------


def test_example_record_validates_and_round_trips(example):
    record = SoftwareRecord.model_validate(example)
    assert record.slug == "frobtail"
    assert record.model_dump(mode="json") == example


@pytest.mark.parametrize(
    "slug",
    ["Frobtail", "frob_tail", "-frobtail", "frobtail-", "frob--tail", "frob tail", "", "a" * 65],
)
def test_bad_slug_rejected(example, slug):
    example["slug"] = slug
    with pytest.raises(ValidationError):
        SoftwareRecord.model_validate(example)


def set_path(*path_and_value):
    *path, value = path_and_value

    def apply(doc):
        target = doc
        for key in path[:-1]:
            target = target[key]
        target[path[-1]] = value

    return apply


def both(*steps):
    def apply(doc):
        for step in steps:
            step(doc)

    return apply


def capped(total: float, reason: str, cap: int):
    """Set a capped quality total; the entry is then no treasure."""

    def apply(doc):
        scores = doc["scores"]
        scores["quality"].update(total=total, cap=cap, cap_reason=reason)
        value = round(total * (1 - scores["popularity"]["score"] / 100), 2)
        scores["treasure"] = {"is_treasure": False, "value": value}

    return apply


def without_runs(doc):
    doc["verification"].update(
        level="unverified", unverified_reason="not_run", checked_at=None, runs=[]
    )
    doc["install"]["linux"] = None


ARTIFACT_CHECK = {
    "artifact": "https://files.example.invalid/frobtail-1.2.0-py3-none-any.whl",
    "sha256": "0" * 64,
    "finding": "only dist-info files; the console script's module frobtail is not in the wheel",
    "checked_at": "2026-11-02T08:00:00Z",
    "checked_by": "a person, by listing the wheel's files",
}


def with_failed_run(doc):
    """A person's failed run on linux, the way failed reaches a record."""
    run = doc["verification"]["runs"][0]
    run.update(level="failed", method="human", runner="mac-m5", replayed=False,
               blocking_error="frobtail: command not found")
    doc["verification"]["level"] = "failed"
    doc["install"]["linux"] = None


def with_failed_sandbox_run(doc):
    run = doc["verification"]["runs"][0]
    run.update(level="failed", blocking_error="frobtail: command not found")
    doc["verification"]["level"] = "failed"
    doc["install"]["linux"] = None


def with_newer_failed_run(doc):
    runs = doc["verification"]["runs"]
    newer = copy.deepcopy(runs[0]) | {
        "id": "run-20261102-linux-1",
        "level": "failed",
        "checked_at": "2026-11-02T08:00:00Z",
        "replayed": True,
        "smoke_tests": [],
        "judge": None,
        "blocking_error": "frobtail: command not found",
        "artifact_check": ARTIFACT_CHECK,
    }
    runs.append(newer)
    doc["verification"]["checked_at"] = newer["checked_at"]


PATTERN = "String should match pattern"
RUN = ("verification", "runs", 0)
QUALITY = ("scores", "quality")
USAGE = (*QUALITY, "components", "usage_outcomes")

# name -> (expected error, mutation of the valid example)
MUTATIONS = {
    "repo id without gh prefix": (PATTERN, set_path("repo_id", "900000001")),
    "scheme-less homepage": (PATTERN, set_path("homepage", "example.invalid")),
    "source id with whitespace": (PATTERN, set_path("sources", 0, "id", "github api")),
    "naive datetime": ("timezone", set_path("first_seen_at", "2026-10-29T10:00:00")),
    "unknown top-level key": ("Extra inputs", set_path("stars", 87)),
    "unknown kind": ("Input should be", set_path("kind", "app")),
    "evidence cites unknown source": (
        "unknown source",
        set_path("evidence", 0, "source_id", "blog"),
    ),
    "evidence points to unknown field": (
        "unknown field",
        set_path("evidence", 0, "field", "/stars"),
    ),
    "model evidence without quote": ("verbatim quote", set_path("evidence", 0, "quote", None)),
    "install steps differ from replayed run": (
        "the run's steps",
        set_path("install", "linux", "steps", [{"command": "pip install x", "purpose": None}]),
    ),
    "install cites missing run": (
        "unknown run",
        set_path("install", "linux", "run_id", "run-missing"),
    ),
    "readme claim with run id": (
        "run_id is required",
        set_path("install", "macos", "run_id", "run-20261031-linux-1"),
    ),
    "level does not match runs": ("level must be", set_path("verification", "level", "inference")),
    "newer run on the same target kept": ("latest run per os", with_newer_failed_run),
    "passed sandbox run not replayed": ("replay", set_path(*RUN, "replayed", False)),
    "failed sandbox run on its own": ("never failed on its own", with_failed_sandbox_run),
    "passed run judged error_visible": (
        "judge's verdict",
        set_path(*RUN, "judge", "verdict", "error_visible"),
    ),
    "function run without passing smoke test": (
        "passing smoke test",
        both(
            set_path(*RUN, "smoke_tests", 0, "passed", False),
            set_path(*RUN, "smoke_tests", 1, "passed", False),
        ),
    ),
    "unverified without reason": (
        "unverified_reason is required",
        set_path(*RUN, "level", "unverified"),
    ),
    "absolute evidence path": (
        PATTERN,
        set_path(*RUN, "evidence", "trace_path", "/tmp/trace.json"),
    ),
    "dot-dot evidence path": (
        PATTERN,
        set_path(*RUN, "evidence", "trace_path", "data/../trace.json"),
    ),
    "weights do not sum to 100": ("sum to 100", set_path(*USAGE, "weight", 20)),
    "usage score below 3 external reports": ("external reports", set_path(*USAGE, "score", 0.9)),
    "usage score from eval reports": (
        "external reports",
        both(set_path("outcomes", "eval", "installed", 50), set_path(*USAGE, "score", 0.9)),
    ),
    "cap differs from B.3": (
        "cap for 'archived' must be 30",
        both(set_path("repo", "archived", True), capped(25.0, "archived", 90)),
    ),
    "archived without cap": ("cap_reason must be 'archived'", set_path("repo", "archived", True)),
    "library without cap": ("cap_reason must be 'not_a_tool'", set_path("kind", "library_sdk")),
    "unverified without cap": ("cap_reason must be 'unverified'", without_runs),
    "failed without cap": ("cap_reason must be 'verification_failed'", with_failed_run),
    "weaker of two caps": (
        "cap_reason must be 'archived'",
        both(
            set_path("repo", "archived", True),
            set_path("kind", "library_sdk"),
            capped(45.0, "not_a_tool", 50),
        ),
    ),
    "cap on a record no cap applies to": (
        "cap_reason must be None",
        capped(60.0, "unverified", 69),
    ),
    "treasure value off": (
        "treasure.value must equal",
        set_path("scores", "treasure", "value", 75.0),
    ),
    "treasure flag off while eligible": (
        "is_treasure must be",
        set_path("scores", "treasure", "is_treasure", False),
    ),
    "treasure with high popularity": (
        "is_treasure must be",
        both(
            set_path("scores", "popularity", "score", 60.0),
            set_path("scores", "treasure", "value", 32.5),
        ),
    ),
}


@pytest.mark.parametrize(("error", "mutate"), MUTATIONS.values(), ids=MUTATIONS.keys())
def test_invalid_records_rejected(example, error, mutate):
    mutate(example)
    with pytest.raises(ValidationError, match=error):
        SoftwareRecord.model_validate(example)


@pytest.mark.parametrize("failed", [with_failed_run, both(with_failed_sandbox_run,
                                                          set_path(*RUN, "artifact_check", ARTIFACT_CHECK))])
def test_failed_needs_a_person_or_a_check_of_the_published_package(example, failed):
    both(failed, capped(40.0, "verification_failed", 40))(example)
    record = SoftwareRecord.model_validate(example)
    assert record.verification.level == "failed"
    assert record.model_dump(mode="json") == example  # artifact_check is left out when there is none


def test_capped_record_validates(example):
    both(
        set_path("repo", "archived", True),
        set_path("kind", "library_sdk"),
        capped(25.0, "archived", 30),
    )(example)
    record = SoftwareRecord.model_validate(example)
    assert record.scores.quality.cap == 30


def test_usage_score_counts_from_three_external_reports(example):
    example["outcomes"]["external"].update(installed=2, first_run_ok=1)
    set_path(*USAGE, "score", 0.9)(example)
    SoftwareRecord.model_validate(example)


def test_values_as_github_reports_them(example):
    example["homepage"] = "http://example.invalid/frobtail"
    example["sources"][2]["id"] = "release:cli/v1.2.0-RC1+build@x"
    example["evidence"][9]["source_id"] = "release:cli/v1.2.0-RC1+build@x"
    SoftwareRecord.model_validate(example)


def test_binding_cap_picks_the_lowest():
    assert binding_cap("cli_tool", False, "function") is None
    assert binding_cap("cli_tool", False, "unverified") == "unverified"
    assert binding_cap("library_sdk", False, "unverified") == "not_a_tool"
    assert binding_cap("library_sdk", False, "failed") == "verification_failed"
    assert binding_cap("library_sdk", True, "failed") == "archived"


def test_usage_outcomes_weight_tiers():
    weights = {n: usage_outcomes_weight(n) for n in (0, 2, 3, 9, 10, 29, 30, 500)}
    assert weights == {0: 10, 2: 10, 3: 10, 9: 10, 10: 20, 29: 20, 30: 30, 500: 30}


def test_smoke_test_setup_and_offline():
    heredoc = "cat > graph.json <<'EOF'\n" + '{"nodes": ["a"]}\n' * 150 + "EOF"
    test = SmokeTest.model_validate({
        "command": "graphtty graph.json", "expected_signal": "a", "exit_code": 0, "passed": True,
        "setup": [{"command": heredoc}, {"command": "tinyserve --port 8080", "background": True, "port": 8080}],
        "offline": False})
    assert len(heredoc) > 500 and test.setup[1].background and test.offline is False
    assert SmokeTest.model_validate({"command": "x", "expected_signal": "", "exit_code": 0,
                                     "passed": True}).offline is None  # older runs: not run offline
    for bad in ({"command": "x" * (SETUP_MAX + 1)}, {"command": "s", "port": 0}, {"command": ""}):
        with pytest.raises(ValidationError):
            SmokeTest.model_validate({"command": "x", "expected_signal": "", "exit_code": 0, "passed": True,
                                      "setup": [bad]})


def test_record_schema_forbids_unknown_keys():
    schema = record_json_schema()
    assert schema["additionalProperties"] is False
    assert schema["properties"]["slug"] == {
        "$ref": "#/$defs/Slug",
        "description": schema["properties"]["slug"]["description"],
    }
    assert schema["$defs"]["Slug"]["pattern"] == r"^[a-z0-9]+(?:-[a-z0-9]+)*$"
    components = schema["$defs"]["QualityComponents"]["properties"]
    assert list(components) == [
        "sandbox_verification",
        "install_docs",
        "maintenance",
        "engineering_hygiene",
        "responsiveness",
        "usage_outcomes",
    ]


# --- ExtractionResult ----------------------------------------------------------


def _cited(value, quote):
    return {"value": value, "quote": quote}


EXTRACTION_SAMPLE = {
    "name": _cited("frobtail", "# frobtail"),
    "summary": _cited(
        "Follows JSON Lines logs and filters them.", "Tail JSON Lines logs and filter them."
    ),
    "kind": _cited("cli_tool", "frobtail is a small command-line tool"),
    "category": _cited("dev_cli", "frobtail is a small command-line tool"),
    "audience": _cited("end_user", "pipx install frobtail"),
    "maturity": _cited("beta", "frobtail is in beta"),
    "processing": _cited("local", "Everything runs locally"),
    "pricing": _cited(None, None),
    "platforms": _cited(["linux", "macos"], "Works on Linux and macOS."),
    "prerequisites": {
        "runtimes": [_cited("python>=3.10", "Requires Python 3.10 or newer.")],
        "system_packages": [],
        "gpu": _cited(None, None),
        "apple_silicon_only": _cited(None, None),
        "min_ram_gb": _cited(None, None),
        "network": _cited(None, None),
        "api_keys": [],
    },
    "install_methods": [
        {"method": "pipx", "command": "pipx install frobtail", "platforms": []},
        {"method": "brew", "command": "brew install example/tap/frobtail", "platforms": ["macos"]},
    ],
    "smoke_test_candidates": [{"command": "frobtail --version", "expected_output": None}],
    "manual_steps": [],
    "use_cases": [_cited("follow a JSON log and show warnings", "frobtail app.jsonl --level warn")],
    "alternatives_to": [],
}


def test_extraction_sample_validates():
    result = ExtractionResult.model_validate(EXTRACTION_SAMPLE)
    assert result.kind.value == "cli_tool"
    assert result.pricing.value is None


def test_cited_value_without_quote_becomes_unknown():
    assert Cited[str].model_validate(_cited("MIT", None)).value is None
    assert Cited[str].model_validate(_cited("MIT", "  ")).value is None
    assert Cited[str].model_validate(_cited(None, "stray quote")).quote is None
    no_apple_only = Cited[bool].model_validate(_cited(False, "Runs on Intel and Apple silicon"))
    assert no_apple_only.value is False


def test_long_quote_is_clipped_not_rejected():
    cited = Cited[str].model_validate(_cited("MIT", "x" * 400))
    assert cited.value == "MIT" and cited.quote == "x" * 300


def test_extraction_drops_unusable_items_instead_of_failing():
    sample = copy.deepcopy(EXTRACTION_SAMPLE)
    sample["install_methods"] += [
        {"method": "pip", "command": "", "platforms": []},
        {"method": "script", "command": "x" * 501, "platforms": []},
    ]
    sample["smoke_test_candidates"] += [
        {"command": "  ", "expected_output": None},
        {"command": "frobtail --help", "expected_output": "y" * 400},
    ]
    sample["use_cases"].append(_cited("a guess", None))
    sample["prerequisites"]["runtimes"].append(_cited("node", ""))

    result = ExtractionResult.model_validate(sample)
    assert [c.command for c in result.install_methods] == [
        "pipx install frobtail",
        "brew install example/tap/frobtail",
    ]
    assert [c.command for c in result.smoke_test_candidates] == [
        "frobtail --version",
        "frobtail --help",
    ]
    assert len(result.smoke_test_candidates[1].expected_output) == 300
    assert [c.value for c in result.use_cases] == ["follow a JSON log and show warnings"]
    assert [c.value for c in result.prerequisites.runtimes] == ["python>=3.10"]


def test_extraction_has_no_api_facts():
    fields = set(ExtractionResult.model_fields)
    assert not fields & {"license", "last_release", "repo", "slug", "stars", "scores"}


# --- meta_strict_schema -----------------------------------------------------------


def test_meta_strict_extraction_schema_is_strict():
    schema = meta_strict_schema(ExtractionResult)
    assert_strict(schema)
    assert "$defs" not in json.dumps(schema) and "$ref" not in json.dumps(schema)
    kind_value = schema["properties"]["kind"]["properties"]["value"]
    assert kind_value["type"] == ["string", "null"]
    assert None in kind_value["enum"] and "cli_tool" in kind_value["enum"]


def test_meta_strict_makes_optional_fields_required_and_nullable():
    class Inner(BaseModel):
        a: int

    class Outer(BaseModel):
        inner: Inner | None = None
        note: str | None = None
        tags: list[str] = []
        mode: Literal["x"] = "x"

    schema = meta_strict_schema(Outer)
    assert_strict(schema)
    assert schema["required"] == ["inner", "note", "tags", "mode"]
    assert schema["properties"]["note"]["type"] == ["string", "null"]
    assert schema["properties"]["mode"]["enum"] == ["x"]
    inner_object = schema["properties"]["inner"]["anyOf"][0]
    assert inner_object["additionalProperties"] is False


def test_meta_strict_rejects_dicts_and_deep_nesting():
    with pytest.raises(ValueError, match="free-form"):
        meta_strict_schema(SoftwareRecord)

    model = create_model("Leaf", x=(int, ...))
    for level in range(11):
        model = create_model(f"Level{level}", child=(model, ...))
    with pytest.raises(ValueError, match="nesting depth"):
        meta_strict_schema(model)


def test_meta_strict_does_not_mutate_pydantic_schema():
    before = copy.deepcopy(ExtractionResult.model_json_schema())
    meta_strict_schema(ExtractionResult)
    assert ExtractionResult.model_json_schema() == before


# --- generated files ------------------------------------------------------------


def test_committed_schema_files_match_models():
    for name, text in render_schema_files().items():
        path = ROOT / "schema" / name
        assert path.exists(), f"schema/{name} missing; run: uv run python scripts/export_schema.py"
        assert path.read_text(encoding="utf-8") == text, (
            f"schema/{name} is stale; run: uv run python scripts/export_schema.py"
        )


# --- Features and feature coverage --------------------------------------------


def test_extraction_features_keep_four_short_quoted_labels():
    sample = copy.deepcopy(EXTRACTION_SAMPLE)
    assert ExtractionResult.model_validate(sample).features == []  # older extractions have none
    sample["features"] = [
        _cited("follow a JSON log", "Tail JSON Lines logs"),
        _cited("a guess", None),
        _cited("x" * 81, "too long a label"),
        _cited("filter by level", "--level warn"),
        _cited("pretty-print fields", "pretty fields"),
        _cited("color output", "colors"),
        _cited("one too many", "more"),
    ]
    result = ExtractionResult.model_validate(sample)
    assert [f.value for f in result.features] == [
        "follow a JSON log", "filter by level", "pretty-print fields", "color output"]
    strict = meta_strict_schema(ExtractionResult)
    assert "features" in strict["required"]


def with_features(doc, *features):
    run = doc["verification"]["runs"][0]
    run["features"] = list(features)
    doc["features"] = [f["feature"] for f in features]
    return doc


CHECKED = {"feature": "follow a JSON log", "status": "checked", "smoke_tests": [1]}
NOT_CHECKED = {"feature": "send alerts to Slack", "status": "not_checked", "reason": "needs_account",
               "note": "needs a Slack webhook"}


def test_run_records_which_features_its_smoke_tests_covered(example):
    record = SoftwareRecord.model_validate(with_features(example, CHECKED, NOT_CHECKED))
    run = record.verification.runs[0]
    assert [(f.feature, f.status, f.reason) for f in run.features] == [
        ("follow a JSON log", "checked", None), ("send alerts to Slack", "not_checked", "needs_account")]
    assert record.features == ["follow a JSON log", "send alerts to Slack"]


def test_records_without_features_render_as_before(example):
    dumped = SoftwareRecord.model_validate(example).model_dump(mode="json")
    assert "features" not in dumped and "features" not in dumped["verification"]["runs"][0]


def failed_test(doc):
    doc["verification"]["runs"][0]["smoke_tests"].append({
        "command": "frobtail app.jsonl --follow", "expected_signal": "", "exit_code": 1, "passed": False,
        "observed_excerpt": "inotify: too many watches"})
    return doc


@pytest.mark.parametrize("mutate", [
    lambda d: with_features(d, {**CHECKED, "smoke_tests": []}),  # checked with no test
    lambda d: with_features(d, {**CHECKED, "smoke_tests": [5]}),  # no such test
    lambda d: with_features(d, {**NOT_CHECKED, "smoke_tests": [1]}),  # a passing test covers it
    lambda d: with_features(d, {**NOT_CHECKED, "reason": None}),  # not checked without a reason
    lambda d: with_features(d, {**CHECKED, "reason": "other"}),
    lambda d: with_features(d, CHECKED, {**CHECKED, "smoke_tests": [0]}),  # the same label twice
    lambda d: with_features(failed_test(d), {"feature": "follow", "status": "test_failed", "smoke_tests": [2]}),
    lambda d: with_features(d, {"feature": "follow", "status": "test_failed", "smoke_tests": [1],
                                "failure": "tool"}),  # its test passed
    lambda d: with_features(d, *[{**NOT_CHECKED, "feature": f"f{i}"} for i in range(5)]),
])
def test_feature_coverage_must_match_the_smoke_tests(example, mutate):
    with pytest.raises(ValidationError):
        SoftwareRecord.model_validate(mutate(example))


def test_a_failed_feature_test_says_whom_it_points_at(example):
    doc = with_features(failed_test(example), {"feature": "follow a growing file", "status": "test_failed",
                                               "smoke_tests": [2], "failure": "sandbox",
                                               "reason": "needs_more_resources"})
    run = SoftwareRecord.model_validate(doc).verification.runs[0]
    assert (run.features[0].failure, run.smoke_tests[2].passed) == ("sandbox", False)
