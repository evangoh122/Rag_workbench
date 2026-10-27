"""Static checks on notebooks/colab_backfill.ipynb and the logic in scripts/colab_backfill_checks.py."""
import json

import pytest

from scripts.check_colab_notebook import DEFAULT_NB, _blank_magics, check_notebook


def test_committed_notebook_is_clean():
    assert check_notebook(DEFAULT_NB) == []


def test_nbformat_validates():
    nbformat = pytest.importorskip("nbformat")
    nbformat.validate(nbformat.read(str(DEFAULT_NB), as_version=4))


def _write(tmp_path, source, **extra):
    cell = {"cell_type": "code", "id": "a", "metadata": {}, "execution_count": None,
            "outputs": [], "source": source, **extra}
    nb = {"nbformat": 4, "nbformat_minor": 5, "metadata": {}, "cells": [cell]}
    p = tmp_path / "nb.ipynb"
    p.write_text(json.dumps(nb))
    return p


def test_syntax_error_is_caught(tmp_path):
    problems = check_notebook(_write(tmp_path, "def broken(:\n    pass"))
    assert any("SyntaxError" in p for p in problems)


def test_magics_are_tolerated():
    assert _blank_magics("!pip install x\n%cd foo\nx = 1") == "pass\npass\nx = 1"


GOOD = (
    "CONFIRM_EXECUTE = False\nCONFIRM_STAGE = False\nSTAGING_REPO = 'egoh33/rag-staging'\n"
    "x = 'stage-upload append_only_proof dry_run()'"
)


def test_minimal_good_source_passes(tmp_path):
    assert check_notebook(_write(tmp_path, GOOD)) == []


@pytest.mark.parametrize("flag", ["CONFIRM_EXECUTE", "CONFIRM_STAGE"])
def test_confirm_flags_required_and_default_off(tmp_path, flag):
    assert any(flag in p and "not found" in p for p in check_notebook(_write(tmp_path, GOOD.replace(f"{flag} = False", "pass"))))
    on = GOOD.replace(f"{flag} = False", f"{flag} = True")
    assert any(f"{flag} is True" in p for p in check_notebook(_write(tmp_path, on)))


def test_staging_repo_must_not_be_production(tmp_path):
    prod = GOOD.replace("egoh33/rag-staging", "egoh33/Rag-workbench")
    assert any("production" in p for p in check_notebook(_write(tmp_path, prod)))
    assert any("STAGING_REPO literal" in p for p in check_notebook(_write(tmp_path, GOOD.replace("STAGING_REPO", "OTHER"))))


@pytest.mark.parametrize("call", ["api.create_commit(x)", "api.upload_file(x)", "CommitOperationAdd(x)",
                                  "api.restart_space(x)", "api.delete_file(x)"])
def test_notebook_may_not_publish(tmp_path, call):
    assert any("forbidden call" in p for p in check_notebook(_write(tmp_path, GOOD + "\n" + call)))


def test_required_steps_must_be_present(tmp_path):
    for needle in ("stage-upload", "append_only_proof", "dry_run()"):
        assert any(needle in p for p in check_notebook(_write(tmp_path, GOOD.replace(needle, "zzz"))))


def test_token_and_secret_leaks_are_caught(tmp_path):
    for tok in ("hf_" + "a" * 30, "ghp_" + "b" * 30, "github_pat_" + "c" * 30):
        assert any("token-shaped" in p for p in check_notebook(_write(tmp_path, GOOD + f"\nt = '{tok}'")))
    for name in ("HF_TOKEN", "EDGAR_USER_AGENT"):
        assert any("print()" in p for p in check_notebook(_write(tmp_path, GOOD + f"\nprint(f'v {{{name}}}')")))
        assert any("shell magic" in p for p in check_notebook(_write(tmp_path, GOOD + f"\n!echo ${name}")))


def test_outputs_and_execution_count_are_caught(tmp_path):
    assert any("outputs" in x for x in check_notebook(_write(tmp_path, GOOD, outputs=[{"output_type": "stream"}])))
    p = _write(tmp_path, GOOD)
    nb = json.loads(p.read_text())
    nb["cells"][0]["execution_count"] = 3
    p.write_text(json.dumps(nb))
    assert any("execution_count" in x for x in check_notebook(p))


def test_committed_notebook_has_no_secret_values_or_outputs():
    nb = json.loads(DEFAULT_NB.read_text())
    for c in nb["cells"]:
        if c["cell_type"] == "code":
            assert c["outputs"] == [] and c["execution_count"] is None
    raw = DEFAULT_NB.read_text()
    assert "@" not in raw.replace("Your Name you@example.com", ""), "no email/identity may be embedded"


def _steps():
    import re
    nb = json.loads(DEFAULT_NB.read_text())
    out = {}
    for c in nb["cells"]:
        if c["cell_type"] == "code":
            src = "".join(c["source"])
            m = re.match(r"# STEP (\d+)", src)
            if m:
                out[int(m.group(1))] = src
    return out


def _bound_names(tree):
    import ast
    names = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Name) and isinstance(n.ctx, (ast.Store, ast.Del)):
            names.add(n.id)
        elif isinstance(n, (ast.FunctionDef, ast.ClassDef)):
            names.add(n.name)
        elif isinstance(n, ast.arg):
            names.add(n.arg)
        elif isinstance(n, (ast.Import, ast.ImportFrom)):
            names.update((a.asname or a.name).split(".")[0] for a in n.names)
        elif isinstance(n, ast.ExceptHandler) and n.name:
            names.add(n.name)
    return names


def _loads(nodes):
    import ast
    return {x.id for node in nodes for x in ast.walk(node) if isinstance(x, ast.Name) and isinstance(x.ctx, ast.Load)}


def test_steps_run_in_order_without_undefined_names():
    """Reconnect order is 1-4 then 5..9 sequentially. Module-level code may only use names bound by
    earlier steps; function bodies run later, so they may use any name some step binds."""
    import ast
    import builtins
    steps = _steps()
    assert sorted(steps) == list(range(1, 10))
    trees = {n: ast.parse(src) for n, src in steps.items()}
    everything = set(dir(builtins)).union(*(_bound_names(t) for t in trees.values()))
    defined = set(dir(builtins))
    for n, tree in trees.items():
        defined |= _bound_names(tree)
        funcs = [x for x in tree.body if isinstance(x, ast.FunctionDef)]
        top = [x for x in tree.body if not isinstance(x, ast.FunctionDef)]
        assert not (_loads(top) - defined), f"step {n} uses undefined {_loads(top) - defined}"
        assert not (_loads(funcs) - everything), f"step {n} function uses unbound {_loads(funcs) - everything}"


def _exec_config(monkeypatch, secrets):
    import sys
    import types
    colab = types.ModuleType("google.colab")
    colab.userdata = types.SimpleNamespace(get=lambda name: secrets.get(name))
    google = types.ModuleType("google")
    google.colab = colab
    monkeypatch.setitem(sys.modules, "google", google)
    monkeypatch.setitem(sys.modules, "google.colab", colab)
    for k in ("HF_TOKEN", "EDGAR_USER_AGENT", "DB_PATH", "EMBED_DOC_BATCH", "EMBEDDING_PROVIDER",
              "ST_EMBEDDING_MODEL", "EMBEDDING_DIM", "PYTORCH_CUDA_ALLOC_CONF"):
        monkeypatch.setenv(k, "orig")  # restored by monkeypatch afterwards
    ns = {}
    exec(compile(_steps()[2], "step2", "exec"), ns)  # noqa: S102
    return ns


def test_config_defaults_are_safe_and_secrets_never_printed(monkeypatch, capsys):
    ns = _exec_config(monkeypatch, {"HF_TOKEN": "tok-SECRET-1", "EDGAR_USER_AGENT": "ua SECRET-2 a@b.c"})
    out = capsys.readouterr()
    assert "SECRET" not in out.out + out.err
    assert ns["CONFIRM_EXECUTE"] is False and ns["CONFIRM_STAGE"] is False and ns["ACCEPT_INCOMPLETE"] is False
    assert ns["STAGING_REPO"] == "egoh33/rag-staging" and ns["STAGING_REPO"].lower() != ns["DATASET_REPO"].lower()
    assert ns["EXTRA_TICKERS"] == ["ANTH"] and ns["FORMS"] == ["annual", "10-Q"]
    assert callable(ns["dry_run"]) and ns["form_args"]("10-Q") == ["--quarters", "3"] and ns["form_args"]("annual") == []
    import os
    assert os.environ["EDGAR_USER_AGENT"] == "ua SECRET-2 a@b.c"  # set for the embed subprocesses only
    from scripts import colab_backfill_checks as chk
    chk.validate_caps(["AAPL"], ns["QUARTERS"], ns["GROUP_SIZE"], ns["SESSION_DEADLINE_SECONDS"])


@pytest.mark.parametrize("missing", ["HF_TOKEN", "EDGAR_USER_AGENT"])
def test_config_fails_without_a_required_secret(monkeypatch, missing):
    secrets = {"HF_TOKEN": "t", "EDGAR_USER_AGENT": "u"}
    secrets[missing] = "  "
    with pytest.raises(RuntimeError, match=missing):
        _exec_config(monkeypatch, secrets)


def _extract_func(step, name, ns):
    import ast
    node = next(n for n in ast.parse(_steps()[step]).body if isinstance(n, ast.FunctionDef) and n.name == name)
    exec(compile(ast.Module([node], []), f"step{step}:{name}", "exec"), ns)  # noqa: S102
    return ns[name]


def _stage_ns(tmp_path, **over):
    import hashlib
    import os
    import sys
    db = tmp_path / "rag.duckdb"
    db.write_bytes(b"db-bytes")
    sha = lambda p: hashlib.sha256(open(p, "rb").read()).hexdigest()  # noqa: E731
    calls = []
    ns = {"os": os, "sys": sys, "DB": str(db), "PROOF_SHA": sha(db), "REMAINING": [], "ACCEPT_INCOMPLETE": False,
          "sha256_file": sha, "run": lambda cmd, **k: calls.append(cmd), "WORK": str(tmp_path),
          "BEFORE_JSON": "/b.json", "STAGING_REPO": "egoh33/rag-staging", "DATASET_REPO": "egoh33/Rag-workbench",
          "meta": {"run_id": "colab-r1"}, **over}
    return _extract_func(9, "stage", ns), ns, calls


def test_stage_happy_path_checks_then_uploads_to_staging_only(tmp_path):
    stage, ns, calls = _stage_ns(tmp_path)
    stage()
    assert [c[3] for c in calls] == ["stage-check", "stage-upload"]
    upload = calls[1]
    assert upload[upload.index("--repo") + 1] == "egoh33/rag-staging"
    assert upload[upload.index("--prod-repo") + 1] == "egoh33/Rag-workbench"
    assert upload[upload.index("--run-id") + 1] == "colab-r1"
    assert not any("publish" in c for cmd in calls for c in cmd)


def test_stage_refuses_without_proof_or_after_db_change(tmp_path):
    stage, ns, calls = _stage_ns(tmp_path)
    del ns["PROOF_SHA"]
    with pytest.raises(RuntimeError, match="append-only proof"):
        stage()
    stage, ns, calls = _stage_ns(tmp_path)
    open(ns["DB"], "ab").write(b"x")  # DB changed after the proof
    with pytest.raises(RuntimeError, match="changed after"):
        stage()
    assert calls == []


def test_stage_refuses_wal_remaining_and_missing_completeness(tmp_path):
    stage, ns, calls = _stage_ns(tmp_path)
    (tmp_path / "rag.duckdb.wal").write_bytes(b"w")
    with pytest.raises(RuntimeError, match="wal"):
        stage()
    (tmp_path / "rag.duckdb.wal").unlink()
    ns["REMAINING"] = [("AAPL", "10-K", "0-1")]
    with pytest.raises(RuntimeError, match="still missing"):
        stage()
    ns["ACCEPT_INCOMPLETE"] = True
    stage()  # the explicit override is honoured
    stage2, ns2, calls2 = _stage_ns(tmp_path)
    del ns2["REMAINING"]
    with pytest.raises(RuntimeError, match="step 7"):
        stage2()
    assert calls2 == []
