"""Static checks on notebooks/colab_backfill.ipynb and the logic in scripts/colab_backfill_checks.py."""
import json

import pytest

from scripts.check_colab_notebook import DEFAULT_NB, _blank_magics, check_notebook


def test_committed_notebook_is_clean():
    assert check_notebook(DEFAULT_NB) == []


def test_compaction_step_checks_committed_and_prints_warning():
    step = _steps()["7b"]
    assert "res['committed']" in step
    assert "res['warning']" in step
    assert "WARNING:" in step


def test_notebook_check_requires_compaction_warning(tmp_path):
    nb = json.loads(DEFAULT_NB.read_text())
    cell = next(c for c in nb["cells"] if c.get("id") == "step7b")
    cell["source"] = [line.replace("res['warning']", "False") for line in cell["source"]]
    path = tmp_path / "missing-warning.ipynb"
    path.write_text(json.dumps(nb))
    assert any("does not inspect compaction result 'warning'" in p for p in check_notebook(path))


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
    "CONFIRM_EXECUTE = False\nCONFIRM_COMPACT = False\nCONFIRM_STAGE = False\nSTAGING_REPO = 'egoh33/rag-staging'\nREPO_COMMIT = ''\n"
    "x = 'stage-upload append_only_proof dry_run() split_complete checkout_pinned compact_duckdb'"
)


def test_minimal_good_source_passes(tmp_path):
    assert check_notebook(_write(tmp_path, GOOD)) == []


@pytest.mark.parametrize("flag", ["CONFIRM_EXECUTE", "CONFIRM_COMPACT", "CONFIRM_STAGE"])
def test_confirm_flags_required_and_default_off(tmp_path, flag):
    assert any(flag in p and "not found" in p for p in check_notebook(_write(tmp_path, GOOD.replace(f"{flag} = False", "pass"))))
    on = GOOD.replace(f"{flag} = False", f"{flag} = True")
    assert any(f"{flag} is True" in p for p in check_notebook(_write(tmp_path, on)))


def test_staging_repo_must_not_be_production(tmp_path):
    prod = GOOD.replace("egoh33/rag-staging", "egoh33/Rag-workbench")
    assert any("production" in p for p in check_notebook(_write(tmp_path, prod)))
    assert any("STAGING_REPO literal" in p for p in check_notebook(_write(tmp_path, GOOD.replace("STAGING_REPO", "OTHER"))))


def test_repo_commit_must_be_pinned_literal(tmp_path):
    assert any("REPO_COMMIT literal" in p for p in check_notebook(_write(tmp_path, GOOD.replace("REPO_COMMIT", "X"))))
    assert check_notebook(_write(tmp_path, GOOD.replace("REPO_COMMIT = ''", f"REPO_COMMIT = '{'a' * 40}'"))) == []
    for bad in ("main", "a" * 39, "A" * 40, "chore/colab-refresh"):
        assert any("REPO_COMMIT must be" in p for p in
                   check_notebook(_write(tmp_path, GOOD.replace("REPO_COMMIT = ''", f"REPO_COMMIT = '{bad}'"))))


@pytest.mark.parametrize("call", ["api.create_commit(x)", "api.upload_file(x)", "CommitOperationAdd(x)",
                                  "api.restart_space(x)", "api.delete_file(x)"])
def test_notebook_may_not_publish(tmp_path, call):
    assert any("forbidden call" in p for p in check_notebook(_write(tmp_path, GOOD + "\n" + call)))


def test_required_steps_must_be_present(tmp_path):
    for needle in ("stage-upload", "append_only_proof", "dry_run()", "split_complete", "checkout_pinned", "compact_duckdb"):
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
            m = re.match(r"# STEP (\d+)(b?)", src)
            if m:
                out[int(m.group(1)) if not m.group(2) else m.group(1) + m.group(2)] = src
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
    assert sorted(steps, key=str) == sorted([*range(1, 10), "7b"], key=str)
    order = [k for k in steps]  # document order
    assert order == [1, 2, 3, 4, 5, 6, 7, "7b", 8, 9]
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
    assert ns["CONFIRM_EXECUTE"] is False and ns["CONFIRM_COMPACT"] is False and ns["CONFIRM_STAGE"] is False
    assert ns["ACCEPT_INCOMPLETE"] is False and ns["COMPACT_WORKDIR"].startswith("/content/")
    assert ns["STAGING_REPO"] == "egoh33/rag-staging" and ns["STAGING_REPO"].lower() != ns["DATASET_REPO"].lower()
    assert ns["EXTRA_TICKERS"] == ["ANTH"] and ns["FORMS"] == ["annual", "10-Q"]
    assert ns["REPO_COMMIT"] == "" and "REPO_REF" not in ns  # placeholder: step 3 refuses until it is filled
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


# ── N3: pinned checkout (real git, no network) ──────────────────────────────

def _git(cwd, *args):
    import subprocess
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True,
                          env={"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@e.x", "GIT_COMMITTER_NAME": "t",
                                "GIT_COMMITTER_EMAIL": "t@e.x", "PATH": __import__("os").environ["PATH"],
                                "HOME": str(cwd)}).stdout.strip()


def _checkout_ns(tmp_path):
    import os
    import re
    import subprocess
    origin = tmp_path / "origin"
    origin.mkdir()
    _git(origin, "init", "-q", "-b", "main")
    shas = []
    for i in range(2):
        (origin / "f.txt").write_text(str(i))
        _git(origin, "add", "f.txt")
        _git(origin, "commit", "-q", "-m", f"c{i}")
        shas.append(_git(origin, "rev-parse", "HEAD"))
    work = tmp_path / "work"
    _git(tmp_path, "clone", "-q", str(origin), str(work))

    def run(cmd, cwd=None, env=None):
        rc = subprocess.run(cmd, cwd=cwd, env=env).returncode
        if rc != 0:
            raise RuntimeError(f"Command failed (exit {rc})")

    ns = {"os": os, "re": re, "subprocess": subprocess, "run": run, "WORK": str(work), "GITHUB_REPO": "x/y"}
    return _extract_func(3, "checkout_pinned", ns), work, shas


def test_checkout_pinned_checks_out_exactly_that_commit(tmp_path):
    checkout, work, shas = _checkout_ns(tmp_path)
    assert checkout(shas[0]) == shas[0] and _git(work, "rev-parse", "HEAD") == shas[0]
    assert (work / "f.txt").read_text() == "0"  # an older commit than the branch head
    assert checkout(shas[1]) == shas[1]


@pytest.mark.parametrize("bad", ["", None, "main", "abc123", "A" * 40, "g" * 40, "a" * 41])
def test_checkout_pinned_refuses_placeholder_or_non_sha(tmp_path, bad):
    checkout, work, shas = _checkout_ns(tmp_path)
    before = _git(work, "rev-parse", "HEAD")
    with pytest.raises(RuntimeError, match="REPO_COMMIT"):
        checkout(bad)
    assert _git(work, "rev-parse", "HEAD") == before


def test_checkout_pinned_fails_for_an_unknown_commit(tmp_path):
    checkout, work, shas = _checkout_ns(tmp_path)
    with pytest.raises(RuntimeError, match="Command failed"):
        checkout("0" * 40)


# ── B1: a group is only complete when nothing is still missing ──────────────

def _step6(tmp_path, missing_by_group, rc=0):
    import subprocess
    import sys
    import time
    from scripts import colab_backfill_checks as chk
    saved, runs, dry = [], [], []

    class Done:
        returncode = rc

    fake_subprocess = type("S", (), {"run": staticmethod(lambda cmd, **k: runs.append(cmd) or Done()),
                                     "TimeoutExpired": subprocess.TimeoutExpired})

    def dry_run(group, forms_list):
        dry.append((tuple(group), tuple(forms_list)))
        return [m for m in missing_by_group if m[0] in group]

    def save_checkpoint(meta):
        saved.append(meta)
        return meta

    ns = {"CONFIRM_EXECUTE": True, "time": time, "chk": chk, "meta": {"completed": [], "run_id": "r"},
          "TICKERS": ["AAA", "BBB", "CCC"], "FORMS": ["annual"], "GROUP_SIZE": 2, "SESSION_DEADLINE_SECONDS": 7200,
          "EMBED_BATCH": 16, "subprocess": fake_subprocess, "sys": sys, "WORK": str(tmp_path),
          "form_args": lambda forms: [], "dry_run": dry_run, "save_checkpoint": save_checkpoint}
    exec(compile(_steps()[6], "step6", "exec"), ns)  # noqa: S102
    return ns, saved, runs, dry


def test_group_with_a_missing_accession_is_not_marked_complete(tmp_path, capsys):
    ns, saved, runs, dry = _step6(tmp_path, [("BBB", "10-K", "0000000001-26-000001")])
    # embed_additional exited 0 for every group, but BBB still lacks a filing
    assert saved[0]["completed"] == ["annual:AAA"]
    assert saved[1]["completed"] == ["annual:AAA", "annual:CCC"]
    assert ns["INCOMPLETE"] == ["annual:BBB"]
    out = capsys.readouterr().out
    assert "INCOMPLETE annual: BBB" in out and "0000000001-26-000001" in out
    assert "Embedding finished" not in out and "incomplete" in out
    assert dry == [(("AAA", "BBB"), ("annual",)), (("CCC",), ("annual",))]  # re-checked after every group


def test_fully_present_groups_are_marked_complete(tmp_path, capsys):
    ns, saved, runs, dry = _step6(tmp_path, [])
    assert saved[-1]["completed"] == ["annual:AAA", "annual:BBB", "annual:CCC"] and ns["INCOMPLETE"] == []
    assert "Embedding finished" in capsys.readouterr().out


def test_nonzero_exit_still_fails_before_any_checkpoint(tmp_path):
    with pytest.raises(RuntimeError, match="embed_additional.py failed"):
        _step6(tmp_path, [], rc=1)


def test_disabled_step6_runs_nothing(tmp_path, capsys):
    import subprocess
    ns = {"CONFIRM_EXECUTE": False, "subprocess": subprocess}
    exec(compile(_steps()[6], "step6", "exec"), ns)  # noqa: S102
    assert "DISABLED" in capsys.readouterr().out


def test_checkout_pinned_verifies_head_after_checkout(tmp_path):
    import subprocess
    checkout, work, shas = _checkout_ns(tmp_path)
    ns = checkout.__globals__
    ns["subprocess"] = type("S", (), {"run": staticmethod(subprocess.run),
                                      "check_output": staticmethod(lambda *a, **k: "b" * 40 + "\n")})
    with pytest.raises(RuntimeError, match="expected"):
        checkout(shas[0])


# ── STEP 7b: compaction ─────────────────────────────────────────────────────

def _cell_order():
    import re
    nb = json.loads(DEFAULT_NB.read_text())
    return [m.group(1) for c in nb["cells"] if c["cell_type"] == "code"
            if (m := re.match(r"# STEP (\d+b?)\b", "".join(c["source"])))]


def test_compact_step_sits_between_verify_and_append_only_proof():
    order = _cell_order()
    assert order.index("7") + 1 == order.index("7b") and order.index("7b") + 1 == order.index("8")
    assert "| 7b |" in "".join(json.loads(DEFAULT_NB.read_text())["cells"][0]["source"])


def test_compact_cell_is_local_only_and_gated():
    import re
    src = _steps()["7b"]
    assert "if CONFIRM_COMPACT:" in src and "protect=[ORIG_DB]" in src
    assert not re.search(r"HfApi|hf_hub_download|upload|stage-upload|stage-check|publish|create_commit|api\.", src)


def test_checker_flags_misplaced_or_missing_compact_step(tmp_path):
    nb = json.loads(DEFAULT_NB.read_text())
    cells = nb["cells"]
    i7b = next(i for i, c in enumerate(cells) if c.get("id") == "step7b")
    i8 = next(i for i, c in enumerate(cells) if c.get("id") == "step8")
    swapped = json.loads(json.dumps(nb))
    swapped["cells"][i7b], swapped["cells"][i8] = swapped["cells"][i8], swapped["cells"][i7b]
    p = tmp_path / "swapped.ipynb"
    p.write_text(json.dumps(swapped))
    assert any("must sit between STEP 7 and STEP 8" in x for x in check_notebook(p))
    missing = json.loads(json.dumps(nb))
    del missing["cells"][i7b]
    p = tmp_path / "missing.ipynb"
    p.write_text(json.dumps(missing))
    assert any("STEP 7b (compact) cell not found" in x for x in check_notebook(p))
    leaky = json.loads(json.dumps(nb))
    leaky["cells"][i7b]["source"] += ["\n", "HfApi(token=HF_TOKEN)\n"]
    p = tmp_path / "leaky.ipynb"
    p.write_text(json.dumps(leaky))
    assert any("STEP 7b makes a Hugging Face call" in x for x in check_notebook(p))
    on = json.loads(DEFAULT_NB.read_text().replace("CONFIRM_COMPACT = False", "CONFIRM_COMPACT = True"))
    p = tmp_path / "on.ipynb"
    p.write_text(json.dumps(on))
    assert any("CONFIRM_COMPACT is True" in x for x in check_notebook(p))


def _compact_ns(tmp_path, **over):
    """Run step 7b's compact() against a real, fragmented DuckDB file."""
    import os
    import sys
    from scripts import colab_backfill_checks as chk
    from tests.test_colab_backfill_checks import _fragmented
    db = tmp_path / "rag.duckdb"
    orig = tmp_path / "orig.duckdb"
    _fragmented(db)
    orig.write_bytes(b"pinned-original")
    calls, saved = [], []
    ns = {"os": os, "sys": sys, "chk": chk, "DB": str(db), "ORIG_DB": str(orig), "COMPACT_WORKDIR": str(tmp_path / "w"),
          "WORK": str(tmp_path), "BEFORE_JSON": "/b.json", "GUARD_JSON": "/g.json", "REMAINING": [],
          "PROOF_SHA": "stale", "meta": {"run_id": "r", "completed": []}, "CONFIRM_COMPACT": True,
          "run": lambda cmd, **k: calls.append(cmd), "save_checkpoint": lambda m: saved.append(m) or m, **over}
    return _extract_func("7b", "compact", ns), ns, calls, saved


def test_compact_runs_guards_checkpoints_and_invalidates_the_proof(tmp_path, capsys):
    compact, ns, calls, saved = _compact_ns(tmp_path)
    size = (tmp_path / "rag.duckdb").stat().st_size
    compact()
    assert (tmp_path / "rag.duckdb").stat().st_size < size
    assert "PROOF_SHA" not in ns  # a proof from before compaction no longer applies
    assert [c[2] if c[1] == "-m" else c[1] for c in calls] == ["scripts.hf_backfill", "scripts/etl_guardrail.py"]
    assert saved and saved[0]["compacted_sha256"] == ns["meta"]["compacted_sha256"]
    assert (tmp_path / "orig.duckdb").read_bytes() == b"pinned-original"
    out = capsys.readouterr().out
    assert "free blocks" in out and "Content identity proven" in out


def test_stage_refuses_after_compaction_that_followed_the_proof(tmp_path):
    """Mutation proof: the guarantee that step 9 needs the proof on the CURRENT db."""
    from scripts import colab_backfill_checks as chk
    compact, ns, calls, saved = _compact_ns(tmp_path)
    ns["PROOF_SHA"] = chk.sha256_file(ns["DB"])  # step 8 ran on the uncompacted file...
    compact()
    ns["PROOF_SHA"] = "stale-from-before"  # ...even if a stale sha survives, it cannot match
    stage, sns, scalls = _stage_ns(tmp_path, DB=ns["DB"], PROOF_SHA=ns["PROOF_SHA"])
    with pytest.raises(RuntimeError, match="changed after"):
        stage()
    assert scalls == []
    stage, sns, scalls = _stage_ns(tmp_path)
    del sns["PROOF_SHA"]
    with pytest.raises(RuntimeError, match="append-only proof"):
        stage()


def test_compact_refuses_wal_unrun_step7_and_proof_failure(tmp_path, monkeypatch):
    from scripts import colab_backfill_checks as chk
    compact, ns, calls, saved = _compact_ns(tmp_path)
    (tmp_path / "rag.duckdb.wal").write_bytes(b"w")
    with pytest.raises(RuntimeError, match="wal"):
        compact()
    (tmp_path / "rag.duckdb.wal").unlink()
    del ns["REMAINING"]
    with pytest.raises(RuntimeError, match="step 7"):
        compact()
    ns["REMAINING"] = []
    sha = chk.sha256_file(ns["DB"])

    def bad_proof(src, dst):
        raise RuntimeError("COMPACTION PROOF FAILED: injected")

    monkeypatch.setattr(chk, "compact_identity_proof", bad_proof)
    with pytest.raises(RuntimeError, match="PROOF FAILED"):
        compact()
    assert chk.sha256_file(ns["DB"]) == sha and ns["PROOF_SHA"] == "stale" and saved == [] and calls == []


def test_compact_protects_the_pinned_original(tmp_path):
    compact, ns, calls, saved = _compact_ns(tmp_path)
    ns["ORIG_DB"] = ns["DB"]  # mutation: if DB were the pinned file, compaction must refuse
    with pytest.raises(RuntimeError, match="protected"):
        compact()


def test_disabled_step_7b_changes_nothing(tmp_path, capsys):
    ns = {"CONFIRM_COMPACT": False}
    exec(compile(_steps()["7b"], "step7b", "exec"), ns)  # noqa: S102
    assert "DISABLED" in capsys.readouterr().out
