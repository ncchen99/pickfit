from pickfit.cli import main


def test_help_runs():
    assert main([]) == 0


def test_discover_needs_a_github_token(tmp_path, monkeypatch, capsys):
    import pickfit.env

    monkeypatch.setattr(pickfit.env, "DOTENV_PATH", tmp_path / "missing.env")
    monkeypatch.delenv("GH_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.setenv("PICKFIT_RUNS_DIR", str(tmp_path / "runs"))
    assert main(["discover"]) == 2
    assert "GH_TOKEN" in capsys.readouterr().err


def test_funnel_on_an_empty_store(tmp_path, monkeypatch, capsys):
    import json

    import pickfit.env

    monkeypatch.setattr(pickfit.env, "DOTENV_PATH", tmp_path / "missing.env")
    monkeypatch.delenv("BASETEN_API_KEY", raising=False)
    monkeypatch.setenv("PICKFIT_RUNS_DIR", str(tmp_path / "runs"))
    assert main(["funnel"]) == 0
    funnel = json.loads(capsys.readouterr().out)
    assert list(funnel) == ["discover", "details", "rules", "prescreen", "extract"]
    assert funnel["prescreen"]["status"] == "skipped"
