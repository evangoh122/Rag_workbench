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
