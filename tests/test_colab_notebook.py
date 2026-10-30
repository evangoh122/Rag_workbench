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


GOOD = """\
import os
import subprocess
import sys

from scripts import colab_backfill_checks as chk

CONFIRM_EXECUTE = False
CONFIRM_STAGE = False
STAGING_REPO = 'egoh33/rag-staging'
REPO_COMMIT = ''
PROOF_SHA = None
REMAINING = None
DB = '/content/rag.duckdb'


def run(cmd, cwd=None, env=None):
    rc = subprocess.run(cmd, cwd=cwd, env=env).returncode
    if rc != 0:
        raise RuntimeError('Command failed')


def form_args(forms):
    return []


def save_checkpoint(meta):
    return meta


def checkout_pinned(commit):
    run(['git', 'checkout', '-q', '--detach', commit])
    return commit


def dry_run(tickers=None, forms_list=None):
    return []


def stage():
    run([sys.executable, '-m', 'scripts.hf_backfill', 'stage-check', '--repo', STAGING_REPO])
    run([sys.executable, '-m', 'scripts.hf_backfill', 'stage-upload', DB, '--repo', STAGING_REPO])
    print('staged')


REPO_HEAD = checkout_pinned(REPO_COMMIT)
PLANNED = dry_run()
done, short = chk.split_complete(['AAA'], [])
APPEND_ONLY_REPORT = chk.append_only_proof(DB, DB)
if CONFIRM_STAGE:
    stage()
else:
    print('Staging is DISABLED')
"""


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


@pytest.mark.parametrize("cmd", [
    "run([sys.executable, '-m', 'scripts.hf_backfill', 'publish', '--confirm'])",
    "subprocess.run('python -m scripts.hf_backfill publish --confirm', shell=True)",
    "cmd = ['python', '-m', 'scripts.hf_backfill', 'publish']\nrun(cmd)",
    "!python -m scripts.hf_backfill publish --confirm",
])
def test_direct_publish_command_is_rejected(tmp_path, cmd):
    assert any("forbidden call scripts.hf_backfill publish" in p for p in check_notebook(_write(tmp_path, GOOD + "\n" + cmd)))


def test_publish_instructions_in_print_are_allowed(tmp_path):
    src = GOOD + "\nprint('run: uv run python -m scripts.hf_backfill publish --run-id x --confirm')\n"
    assert check_notebook(_write(tmp_path, src)) == []


@pytest.mark.parametrize("expr", ["os.environ['HF_TOKEN']", "userdata.get('HF_TOKEN')", "os.environ.get('GH_TOKEN')",
                                  "os.getenv('EDGAR_USER_AGENT')", "f'tok={os.environ[\"HF_TOKEN\"]}'"])
def test_print_of_secret_read_by_key_is_caught(tmp_path, expr):
    assert any("print() references a secret" in p for p in check_notebook(_write(tmp_path, GOOD + f"\nprint({expr})\n")))


def test_print_of_secret_name_string_is_not_a_read(tmp_path):
    assert check_notebook(_write(tmp_path, GOOD + "\nprint('Secrets present: HF_TOKEN=yes')\n")) == []


@pytest.mark.parametrize("flag", ["CONFIRM_EXECUTE", "CONFIRM_STAGE"])
@pytest.mark.parametrize("later", ["{f} = bool(1)", "{f} = True", "{f} += 1", "{f}, other = True, 1",
                                   "{f}: bool = True"])
def test_later_assignment_overrides_the_default_off_flag(tmp_path, flag, later):
    """CodeRabbit #4: `False` then a non-literal-False reassignment must fail (last assignment wins)."""
    assert any(flag in p for p in check_notebook(_write(tmp_path, GOOD + "\n" + later.format(f=flag))))


def test_flag_order_follows_cells_not_text_position(tmp_path):
    def cell(src):
        return {"cell_type": "code", "id": src[:3], "metadata": {}, "execution_count": None, "outputs": [], "source": src}
    nb = {"nbformat": 4, "nbformat_minor": 5, "metadata": {},
          "cells": [cell(GOOD), cell("CONFIRM_STAGE = str(1)")]}
    p = tmp_path / "two.ipynb"
    p.write_text(json.dumps(nb))
    assert any("CONFIRM_STAGE" in x for x in check_notebook(p))
    nb["cells"] = [cell("CONFIRM_STAGE = str(1)"), cell(GOOD)]  # later cell resets it to False: safe
    p.write_text(json.dumps(nb))
    assert check_notebook(p) == []


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
    ns["PROOF_SHA"] = None
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
    ns2["REMAINING"] = None
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


# ── CodeRabbit #1: a stale WAL must never be replayed into a restored / fresh DB ─────────────────

def _step4(tmp_path, old):
    """Run the real step-4 cell with its imports replaced by recording test doubles."""
    import ast
    import pathlib
    import secrets
    import sys
    import time
    db = tmp_path / "rag.duckdb"
    wal = pathlib.Path(str(db) + ".wal")
    db.write_bytes(b"db")
    wal.write_text("stale wal from a killed embed run")
    seen = {}

    class Chk:
        @staticmethod
        def read_checkpoint(_d):
            return (old, "ok") if old else (None, "no checkpoint")

        @staticmethod
        def restore_checkpoint(*_a):
            seen["restore"] = wal.exists()
            pathlib.Path(tmp_path / "before.json").write_text(json.dumps({"sha256": "x"}))

        @staticmethod
        def write_checkpoint(*_a):
            pass

        @staticmethod
        def validate_caps(*_a):
            pass

    class Con:
        def execute(self, *_a):
            return self

        def fetchall(self):
            return [("AAA",)]

        def fetchone(self):
            return (None,)

        def close(self):
            pass

    class Api:
        def __init__(self, **_k):
            pass

        def repo_info(self, *_a, **_k):
            return type("I", (), {"sha": "s" * 40})()

    def copy_writable(*_a):
        seen["fresh"] = wal.exists()

    tree = ast.parse(_steps()[4])
    tree.body = [n for n in tree.body if not isinstance(n, (ast.Import, ast.ImportFrom))]
    ns = {"os": __import__("os"), "pathlib": pathlib, "json": json, "sys": sys, "time": time, "secrets": secrets,
          "duckdb": type("D", (), {"connect": staticmethod(lambda *a, **k: Con())}), "HfApi": Api,
          "hf_hub_download": lambda *a, **k: "orig", "chk": Chk, "sha256_file": lambda _p: "x",
          "copy_writable": copy_writable, "run": lambda *a, **k: None, "WORK": str(tmp_path), "DB": str(db),
          "USE_DRIVE": False, "CKPT_DIR": str(tmp_path / "ck"), "BEFORE_JSON": str(tmp_path / "before.json"),
          "GUARD_JSON": str(tmp_path / "g.json"), "HF_TOKEN": "t", "DATASET_REPO": "d", "PINNED_REVISION": None,
          "EXTRA_TICKERS": [], "QUARTERS": 3, "GROUP_SIZE": 8, "SESSION_DEADLINE_SECONDS": 7200}
    exec(compile(tree, "step4", "exec"), ns)  # noqa: S102
    return seen, wal


def test_stale_wal_is_removed_before_checkpoint_restore(tmp_path):
    seen, wal = _step4(tmp_path, {"pinned_sha": "s" * 40, "meta": {"run_id": "r", "completed": []}})
    assert seen == {"restore": False} and not wal.exists()


def test_stale_wal_is_removed_before_fresh_copy(tmp_path):
    seen, wal = _step4(tmp_path, None)
    assert seen == {"fresh": False} and not wal.exists()


# ── CodeRabbit #2: a failed EDGAR lookup is "unknown", never "nothing missing" ───────────────────

def _dry_run_ns(tmp_path, rc, log_text):
    import pathlib
    import re
    import subprocess
    import sys

    class Proc:
        returncode = rc
        stderr = "boom"

    def fake_run(cmd, **_k):
        pathlib.Path(cmd[cmd.index("--log") + 1]).write_text(log_text)
        return Proc()

    ns = {"re": re, "pathlib": pathlib, "sys": sys, "WORK": str(tmp_path), "FORMS": ["annual"], "TICKERS": ["AAA"],
          "QUARTERS": 3, "form_args": lambda _f: [], "subprocess": type("S", (), {"run": staticmethod(fake_run)})}
    import ast
    tree = ast.parse(_steps()[2].replace("/content/", str(tmp_path) + "/"))  # keep the logs inside tmp_path
    keep = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "dry_run"]
    keep += [n for n in tree.body if isinstance(n, ast.Assign) and getattr(n.targets[0], "id", "") in ("WOULD_FETCH", "LOOKUP_FAILED")]
    exec(compile(ast.Module(keep, []), "dry", "exec"), ns)  # noqa: S102
    assert subprocess  # silence unused import
    return ns["dry_run"]


def test_dry_run_still_parses_would_fetch_lines(tmp_path):
    run = _dry_run_ns(tmp_path, 0, "[AAA] DRY-RUN would fetch: 10-K 0000000001-26-000001\n")
    assert run() == [("AAA", "10-K", "0000000001-26-000001")]


def test_dry_run_with_clean_empty_log_means_nothing_missing(tmp_path):
    assert _dry_run_ns(tmp_path, 0, "[AAA] skip (already present): 10-K a\n")() == []


def test_dry_run_raises_on_a_lookup_failure_even_if_exit_is_zero(tmp_path):
    run = _dry_run_ns(tmp_path, 0, "DRY-RUN lookup FAILED: AAA 10-K\n")
    with pytest.raises(RuntimeError, match="EDGAR lookup failed"):
        run()


def test_dry_run_raises_on_nonzero_exit(tmp_path):
    with pytest.raises(RuntimeError, match="dry run failed"):
        _dry_run_ns(tmp_path, 2, "DRY-RUN lookup FAILED: AAA 10-K\n")()


def test_lookup_failure_never_reaches_the_checkpoint(tmp_path):
    """Step 6 re-checks with dry_run(); when that raises, nothing is marked done or saved."""
    saved = []

    def failing_dry_run(group, forms_list):
        raise RuntimeError("EDGAR lookup failed")

    import subprocess
    import sys
    import time
    from scripts import colab_backfill_checks as chk

    class Done:
        returncode = 0
    ns = {"CONFIRM_EXECUTE": True, "time": time, "chk": chk, "meta": {"completed": [], "run_id": "r"},
          "TICKERS": ["AAA"], "FORMS": ["annual"], "GROUP_SIZE": 2, "SESSION_DEADLINE_SECONDS": 7200,
          "EMBED_BATCH": 16, "subprocess": type("S", (), {"run": staticmethod(lambda *a, **k: Done()),
                                                        "TimeoutExpired": subprocess.TimeoutExpired}),
          "sys": sys, "WORK": str(tmp_path), "form_args": lambda f: [], "dry_run": failing_dry_run,
          "save_checkpoint": lambda m: saved.append(m) or m}
    with pytest.raises(RuntimeError, match="EDGAR lookup failed"):
        exec(compile(_steps()[6], "step6", "exec"), ns)  # noqa: S102
    assert saved == [] and ns["meta"]["completed"] == []


# ── round 3: allowlist design. Every probe below PASSED the round-2 blacklist checker. ──────────────

PROOF = "APPEND_ONLY_REPORT = chk.append_only_proof(DB, DB)\n"
UPLOAD_LINE = "    run([sys.executable, '-m', 'scripts.hf_backfill', 'stage-upload', DB, '--repo', STAGING_REPO])\n"


def _problems(tmp_path, src):
    return check_notebook(_write(tmp_path, src))


def _expect(tmp_path, src, *needles):
    problems = _problems(tmp_path, src)
    assert problems, "the checker accepted a bypass"
    for n in needles:
        assert any(n in p for p in problems), (n, problems)


PROOF_BYPASSES = {
    "flag_false_if": "if CONFIRM_EXECUTE:\n    " + PROOF,
    "for_empty": "for x in []:\n    " + PROOF,
    "after_return_in_called_helper": "def helper():\n    return 1\n    " + PROOF + "helper()\n",
    "swallowed_try": "try:\n    " + PROOF + "except Exception:\n    pass\n",
    "dead_if": "if False:\n    " + PROOF,
    "inside_uncalled_def": "def never():\n    " + PROOF,
    "and_short_circuit": "x = False and chk.append_only_proof(DB, DB)\n",
    "print_arg": "print(chk.append_only_proof(DB, DB))\n",
    "marker_text": "note = 'append_only_proof'\n",
    "after_toplevel_raise": "raise SystemExit\n" + PROOF,
}


@pytest.mark.parametrize("name", sorted(PROOF_BYPASSES))
def test_append_only_proof_must_be_an_unconditional_top_level_statement(tmp_path, name):
    src = GOOD.replace(PROOF, PROOF_BYPASSES[name])
    assert src != GOOD
    _expect(tmp_path, src)
    assert any("append_only_proof" in p or "top-level" in p or "not allowed" in p for p in _problems(tmp_path, src))


def test_proof_after_stage_call_is_rejected(tmp_path):
    src = GOOD.replace(PROOF, "") + "\n" + PROOF
    _expect(tmp_path, src, "must run before stage-upload")


def test_missing_proof_is_rejected(tmp_path):
    _expect(tmp_path, GOOD.replace(PROOF, ""), "append_only_proof not found")


STAGE_BYPASSES = {
    "print_marker": UPLOAD_LINE.replace("run([", "print([").replace("])\n", "])\n"),
    "marker_text": "    note = 'stage-upload'\n",
    "conditional": "    if DB:\n    " + UPLOAD_LINE,
    "in_for": "    for x in []:\n    " + UPLOAD_LINE,
    "variable_subcommand": "    sub = 'stage-upload'\n    run([sys.executable, '-m', 'scripts.hf_backfill', sub])\n",
}


@pytest.mark.parametrize("name", sorted(STAGE_BYPASSES))
def test_stage_upload_must_be_an_unconditional_run_call_in_stage(tmp_path, name):
    src = GOOD.replace(UPLOAD_LINE, STAGE_BYPASSES[name])
    assert src != GOOD
    problems = _problems(tmp_path, src)
    assert any("stage-upload not found" in p or "not allowed" in p or "not allowlisted" in p for p in problems), problems


def test_stage_with_an_early_return_is_rejected(tmp_path):
    src = GOOD.replace("def stage():\n", "def stage():\n    if DB:\n        return\n")
    _expect(tmp_path, src, "stage: return only as the last statement")


@pytest.mark.parametrize("call", ["stage()\n", "if CONFIRM_STAGE or True:\n    stage()\n", "if x:\n    stage()\n"])
def test_stage_may_only_be_called_under_the_confirm_flag(tmp_path, call):
    src = GOOD.replace("if CONFIRM_STAGE:\n    stage()\nelse:\n    print('Staging is DISABLED')\n", call)
    assert src != GOOD
    assert _problems(tmp_path, src)


def test_stage_called_twice_is_rejected(tmp_path):
    _expect(tmp_path, GOOD + "stage()\n", "stage() must be called exactly once")


# The probes the round-2 review reported as passing:

def test_probe_local_run_redefinition_with_the_expected_stage_argv(tmp_path):
    fake_added = GOOD.replace("def form_args(forms):", "def run(*a):\n    pass\n\n\ndef form_args(forms):")
    _expect(tmp_path, fake_added, "run must be defined exactly once")
    only_fake = GOOD.replace("    rc = subprocess.run(cmd, cwd=cwd, env=env).returncode\n    if rc != 0:\n"
                             "        raise RuntimeError('Command failed')\n", "    pass\n")
    _expect(tmp_path, only_fake, "run must call subprocess.run")
    rebound = GOOD + "run = print\n"
    _expect(tmp_path, rebound, "run must be defined exactly once")


def test_probe_constructed_argv(tmp_path):
    src = GOOD + "run([sys.executable, '-m', 'scripts.hf_backfill', 'pub' + 'lish'])\n"
    _expect(tmp_path, src, "not allowlisted")


def test_probe_fstring_with_publish_from_a_variable(tmp_path):
    src = GOOD + "sub = 'publish'\nrun([sys.executable, '-m', 'scripts.hf_backfill', f'{sub}'])\n"
    _expect(tmp_path, src, "not allowlisted")
    shell = GOOD + "sub = 'publish'\nos.system(f'python -m scripts.hf_backfill {sub}')\n"
    _expect(tmp_path, shell, "os.system is not allowed")


def test_probe_exec_with_separately_quoted_argv(tmp_path):
    src = GOOD + "exec(\"run([sys.executable, '-m', 'scripts.hf_backfill', 'pub' 'lish'])\")\n"
    _expect(tmp_path, src, "use of exec is not allowed")


@pytest.mark.parametrize("snippet,needle", [
    ("eval('1')", "eval"), ("compile('1', 'x', 'eval')", "compile"), ("__import__('os')", "__import__"),
    ("getattr(os, 'system')", "getattr"), ("setattr(os, 'x', 1)", "setattr"), ("globals()['x'] = 1", "globals"),
    ("locals()", "locals"), ("importlib.import_module('os')", "importlib"), ("open('/etc/passwd')", "open"),
])
def test_dynamic_code_and_introspection_are_rejected(tmp_path, snippet, needle):
    _expect(tmp_path, GOOD + snippet + "\n", needle)


@pytest.mark.parametrize("snippet", [
    "try:\n    pass\nexcept Exception:\n    pass\n", "try:\n    pass\nfinally:\n    pass\n",
    "with open_it() as f:\n    pass\n", "while True:\n    break\n", "class C:\n    pass\n", "f = lambda: 1\n",
    "sys.exit(0)\n", "os._exit(0)\n", "import ctypes\n", "from os import system\n", "import subprocess as sp\n",
    "raise SystemExit\n",
])
def test_statement_and_callable_allowlist_rejects(tmp_path, snippet):
    assert _problems(tmp_path, GOOD + snippet)


@pytest.mark.parametrize("rebind", ["chk = None\n", "sys = None\n", "subprocess = None\n", "os = None\n",
                                    "for dry_run in []:\n    pass\n", "checkout_pinned = print\n",
                                    "stage = print\n", "import chk\n", "def f(run):\n    return run\n"])
def test_helper_and_module_names_cannot_be_rebound(tmp_path, rebind):
    assert _problems(tmp_path, GOOD + rebind)


@pytest.mark.parametrize("helper", ["run", "checkout_pinned", "dry_run", "stage", "form_args", "save_checkpoint"])
def test_every_helper_must_be_defined_once(tmp_path, helper):
    import re as _re
    # remove the def entirely
    missing = _re.sub(rf"def {helper}\(.*?(?=\n\n\n)", "pass", GOOD, count=1, flags=_re.S)
    assert missing != GOOD
    assert any(f"{helper} must be defined exactly once" in p for p in _problems(tmp_path, missing))


def test_helpers_may_not_return_early(tmp_path):
    src = GOOD.replace("def dry_run(tickers=None, forms_list=None):\n    return []",
                       "def dry_run(tickers=None, forms_list=None):\n    if tickers:\n        return []\n    return []")
    _expect(tmp_path, src, "dry_run: return only as the last statement")


@pytest.mark.parametrize("argv", [
    "['rm', '-rf', 'x']", "[sys.executable, '-m', 'scripts.hf_backfill', 'publish']",
    "[sys.executable, '-m', 'scripts.hf_backfill']", "'python -m scripts.hf_backfill stage-upload'", "cmd",
])
def test_every_command_needs_a_literal_allowlisted_argv(tmp_path, argv):
    assert _problems(tmp_path, GOOD + f"run({argv})\n")


def test_informational_publish_hint_must_be_plain_constants(tmp_path):
    ok = GOOD + "print('uv run python -m scripts.hf_backfill publish --run-id <run id> --confirm')\n"
    assert check_notebook(_write(tmp_path, ok)) == []
    for bad in ("print(f'uv run python -m scripts.hf_backfill publish --run-id {DB}')",
                "print('x', DB, 'hf_backfill publish')",
                "print(run([sys.executable, '-m', 'scripts.hf_backfill', 'publish']))"):
        assert _problems(tmp_path, GOOD + bad + "\n")


def test_shell_magics_are_rejected(tmp_path):
    _expect(tmp_path, GOOD + "!pip install requests\n", "magics are not allowed")


# ── round 2: a failed completeness check must not leave a stale REMAINING behind ────────────────

def test_failed_dry_run_leaves_remaining_unset_and_staging_refuses(tmp_path):
    """One shared kernel namespace: step 7 passes (REMAINING == []), a later step 7 raises on a lookup failure,
    and the stage attempt after that must be refused (not accept the stale empty list)."""
    state = {"fail": False}

    def dry_run(*_a, **_k):
        if state["fail"]:
            raise RuntimeError("EDGAR lookup failed")
        return []

    stage, ns, calls = _stage_ns(tmp_path, dry_run=dry_run, GUARD_JSON="/g.json")
    ns["REMAINING"] = None
    exec(compile(_steps()[7], "step7", "exec"), ns)  # noqa: S102
    assert ns["REMAINING"] == []
    state["fail"] = True
    with pytest.raises(RuntimeError, match="EDGAR lookup failed"):
        exec(compile(_steps()[7], "step7", "exec"), ns)  # noqa: S102
    assert ns["REMAINING"] is None  # unset: the earlier empty list must not survive
    with pytest.raises(RuntimeError, match="step 7"):
        ns["stage"]()
    assert [c for c in calls if "stage-upload" in c] == []
