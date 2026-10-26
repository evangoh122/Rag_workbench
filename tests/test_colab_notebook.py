"""Static checks on notebooks/colab_backfill.ipynb (syntax, cleared outputs, publish off)."""
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


def test_publish_flag_required_and_default_off(tmp_path):
    ok = "CONFIRM_PUBLISH = False\napi.create_commit(parent_commit=1)"
    assert check_notebook(_write(tmp_path, ok)) == []
    assert any("CONFIRM_PUBLISH" in p for p in check_notebook(_write(tmp_path, "x = 1")))
    on = "CONFIRM_PUBLISH = True\nparent_commit = 1"
    assert any("is True" in p for p in check_notebook(_write(tmp_path, on)))


def test_secret_print_and_outputs_are_caught(tmp_path):
    src = "CONFIRM_PUBLISH = False\nparent_commit = 1\nprint('t', HF_TOKEN)"
    assert any("secret" in p for p in check_notebook(_write(tmp_path, src)))
    p = _write(tmp_path, "CONFIRM_PUBLISH = False\nparent_commit = 1",
               outputs=[{"output_type": "stream"}])
    assert any("outputs" in x for x in check_notebook(p))


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


def test_documented_recovery_order_has_no_undefined_names():
    """After a disconnect the doc says: re-run steps 1-4, then 6 (and 7). Simulate it."""
    import ast
    import builtins
    steps = _steps()
    defined = set(dir(builtins))
    for n in (1, 2, 3, 4):
        defined |= _bound_names(ast.parse(steps[n]))
    for target in (6, 7):
        tree = ast.parse(steps[target])
        defined |= _bound_names(tree)  # names the cell itself binds (incl. locals)
        used = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)}
        assert not (used - defined), f"step {target} uses undefined {used - defined}"
        defined = set(dir(builtins))
        for n in (1, 2, 3, 4):
            defined |= _bound_names(ast.parse(steps[n]))


def test_config_cell_defines_plans_and_dry_run():
    """Exec the config cell with stubbed Colab secrets: PLANS / dry_run must exist after it."""
    import sys
    import types
    colab = types.ModuleType("google.colab")
    colab.userdata = types.SimpleNamespace(get=lambda name: "x")
    google = types.ModuleType("google")
    google.colab = colab
    saved = {k: sys.modules.get(k) for k in ("google", "google.colab")}
    sys.modules.update({"google": google, "google.colab": colab})
    try:
        ns = {}
        exec(compile(_steps()[2], "step2", "exec"), ns)  # noqa: S102
    finally:
        for k, v in saved.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v
    assert callable(ns["dry_run"]) and ns["PLANS"]
