"""Static checks for notebooks/colab_backfill.ipynb (no Colab, GPU or network needed).

    uv run python scripts/check_colab_notebook.py [notebook.ipynb]
    uv run --with nbformat python scripts/check_colab_notebook.py   # also nbformat.validate

This is best-effort defense-in-depth for reviewers, NOT a proof of safety: it cannot see what an
imported module or a Colab runtime does. It is an ALLOWLIST: code cells may only use a small fixed set
of statement and expression shapes, callable names, imports and subprocess argv prefixes, so a new
trick fails closed instead of needing another blacklist entry. The rules:

* valid JSON, every code cell parses, outputs and execution counts cleared, no hardcoded token, no
  shell/cell magics, no print of a secret (including `os.environ["HF_TOKEN"]`, `userdata.get("HF_TOKEN")`);
* no try/except/finally, with, while, class, lambda, global, exec/eval/compile/__import__/importlib/
  getattr/setattr/globals/locals; only allowlisted callables and imports;
* the helpers `run`, `checkout_pinned`, `dry_run`, `stage`, `form_args`, `save_checkpoint` are defined
  exactly once as top-level defs; `chk`, `subprocess`, `sys`, `os` are bound only by their one expected
  import; the helpers have no early `return`;
* every command goes through `run([...])` / `subprocess.run([...])` with a literal argv list whose first
  elements match an allowlisted prefix (so `scripts.hf_backfill publish`, built or not, is rejected);
  `stage-upload` may ONLY be invoked by the one unconditional stage-upload statement inside `stage()`
  (a direct call anywhere else would skip stage()'s proof/completeness gates), and a `python -c` payload
  must be a plain string literal free of staging/publish escape markers (it is code the checker cannot
  parse, so any mention of publish/stage-upload/hf_backfill/subprocess/... fails closed);
* the append-only proof (`chk.append_only_proof`) is an unconditional top-level statement comparing two
  DIFFERENT databases named as plain names (a self-proof proves nothing), the stage-upload `run([...])`
  is an unconditional top-level statement of `stage()`, `stage()` is called once, only as the body of
  `if CONFIRM_STAGE:`, and strictly after the proof; `PROOF_SHA` (the proof hash stage() re-checks) may
  only ever be `None` or `sha256_file(<the proven DB>)` — a literal or wrong-source hash is fabricated
  and rejected — and `PROOF_SHA = None` must precede the proof in the same cell, so a failed re-check
  leaves it unset instead of keeping a stale proof from an earlier run;
* the LAST assignment of CONFIRM_EXECUTE / CONFIRM_STAGE, in cell order, is a literal False; the repo
  checkout is pinned; STAGING_REPO is not the production dataset.
"""
import ast
import json
import re
import sys
from pathlib import Path

DEFAULT_NB = Path(__file__).resolve().parent.parent / "notebooks" / "colab_backfill.ipynb"
SECRET_NAMES = ("HF_TOKEN", "GH_TOKEN", "EDGAR_USER_AGENT", "auth")
PROD_REPO = "egoh33/rag-workbench"
FLAGS = ("CONFIRM_EXECUTE", "CONFIRM_STAGE")
TOKEN_RE = re.compile(r"\b(hf_[A-Za-z0-9]{20,}|ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})")
# The notebook may only stage through `scripts.hf_backfill stage-upload`; publishing is out of scope.
FORBIDDEN_CALLS = ("create_commit", "upload_file", "upload_folder", "CommitOperationAdd",
                   "CommitOperationDelete", "delete_file", "delete_repo", "restart_space",
                   "scripts.hf_backfill publish")
PUBLISH_CMD_RE = re.compile(r"hf_backfill(?:\.py)?\s+publish\b")

# ── the allowlist ───────────────────────────────────────────────────────────────────────────────
ALLOWED_STMTS = (ast.Import, ast.ImportFrom, ast.FunctionDef, ast.Assign, ast.Expr, ast.If, ast.For,
                 ast.Raise, ast.Return, ast.Break, ast.Pass)
ALLOWED_EXPRS = (ast.Name, ast.Constant, ast.Call, ast.Attribute, ast.FormattedValue, ast.JoinedStr,
                 ast.Subscript, ast.List, ast.Tuple, ast.Compare, ast.BoolOp, ast.UnaryOp, ast.BinOp,
                 ast.Dict, ast.IfExp, ast.Slice, ast.Starred, ast.GeneratorExp, ast.ListComp, ast.SetComp)
BANNED_NAMES = {"exec", "eval", "compile", "__import__", "importlib", "getattr", "setattr", "delattr",
                "globals", "locals", "vars", "open", "input", "breakpoint", "__builtins__"}
BANNED_ATTRS = {"__import__", "import_module", "__globals__", "__dict__", "__builtins__", "__class__",
                "__subclasses__", "__code__"}
# `import x` / `from x import y` that the notebook uses; `as` only for the one chk import.
IMPORTS = {"torch", "json", "os", "pathlib", "re", "subprocess", "sys", "time", "secrets", "duckdb"}
FROM_IMPORTS = {"google.colab", "huggingface_hub", "scripts", "scripts.hf_backfill", "scripts.prepare_db_copy"}
# Helpers the notebook defines itself: exactly one top-level def each.
HELPERS = ("run", "checkout_pinned", "dry_run", "stage", "form_args", "save_checkpoint")
CALL_NAMES = {"print", "len", "sorted", "set", "list", "dict", "str", "int", "round", "any", "map",
              "enumerate", "RuntimeError", "_secret", "HfApi", "hf_hub_download", "copy_writable",
              "sha256_file", *HELPERS}
MODULES = {"os", "subprocess", "chk", "sys", "json", "re", "time", "secrets", "pathlib", "duckdb", "torch",
           "drive", "userdata", "api"}
CALL_DOTTED = {"chk.append_only_proof", "chk.mark_done", "chk.pending_groups", "chk.read_checkpoint",
               "chk.restore_checkpoint", "chk.split_complete", "chk.validate_caps", "chk.write_checkpoint",
               "api.repo_info", "drive.mount", "duckdb.connect", "json.loads", "os.makedirs", "os.path.exists",
               "os.path.getsize", "os.path.isdir", "pathlib.Path", "re.compile", "re.fullmatch",
               "secrets.token_hex", "subprocess.run", "subprocess.check_output", "sys.path.insert",
               "time.gmtime", "time.monotonic", "time.strftime", "torch.cuda.get_device_name",
               "torch.cuda.is_available", "userdata.get"}
METHODS = {"append", "extend", "split", "splitlines", "strip", "join", "items", "get", "groups", "match",
           "findall", "finditer", "read_text", "write_text", "unlink", "execute", "fetchall", "fetchone", "close"}
# Command argv prefixes: `<py>` is `sys.executable`; every prefix element must be a plain string literal.
PY = "<py>"
ARGV_PREFIXES = [
    ("git", "clone"), ("git", "fetch"), ("git", "checkout"), ("git", "rev-parse"), ("git", "cat-file"),
    (PY, "-m", "pip", "install"), (PY, "-m", "uv", "export"), (PY, "-m", "uv", "pip", "install"), (PY, "-c"),
    (PY, "-m", "scripts.hf_backfill", "snapshot"), (PY, "-m", "scripts.hf_backfill", "effective-db"),
    (PY, "-m", "scripts.hf_backfill", "verify"), (PY, "-m", "scripts.hf_backfill", "stage-check"),
    (PY, "-m", "scripts.hf_backfill", "stage-upload"),
    (PY, "scripts/etl_guardrail.py", "snapshot"), (PY, "scripts/etl_guardrail.py", "verify"),
    (PY, "scripts/prepare_db_copy.py", "check"), (PY, "scripts/embed_additional.py"),
]
STAGE_UPLOAD = (PY, "-m", "scripts.hf_backfill", "stage-upload")
PY_C = (PY, "-c")
# A `python -c` payload is arbitrary code the allowlist cannot see. It must be a plain string literal,
# and that literal is then scanned: any staging/publish escape marker fails closed (the one legitimate
# use, step 3's fresh-interpreter dependency check, mentions none of these).
CODE_ESCAPE_RE = re.compile(
    r"publish|stage[-_]upload|guarded_publish|hf_backfill|create_commit|upload_file|upload_folder|"
    r"delete_repo|delete_file|restart_space|HfApi|subprocess|__import__|\beval\b|\bexec\b|"
    r"os\.system|popen|shell\s*=", re.IGNORECASE)
_NOT_LITERAL = object()


def _source(cell: dict) -> str:
    src = cell.get("source", "")
    return "".join(src) if isinstance(src, list) else src


def _blank_magics(code: str) -> str:
    """Replace IPython `!cmd` / `%magic` lines with `pass` so ast can parse the rest."""
    lines = []
    for line in code.splitlines():
        stripped = line.lstrip()
        if stripped.startswith(("!", "%")):
            line = line[: len(line) - len(stripped)] + "pass"
        lines.append(line)
    return "\n".join(lines)


def _dotted(node: ast.AST):
    """'a.b.c' for a pure Name/Attribute chain, else None."""
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        return ".".join([node.id, *reversed(parts)])
    return None


def _reads_secret(node: ast.AST) -> bool:
    """True when a node names a secret directly or reads one by a constant key."""
    if isinstance(node, ast.Name):
        return node.id in SECRET_NAMES
    key = None
    if isinstance(node, ast.Subscript):  # os.environ["HF_TOKEN"]
        key = node.slice
    elif (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
          and node.func.attr in ("get", "getenv") and node.args):  # userdata.get("HF_TOKEN")
        key = node.args[0]
    return isinstance(key, ast.Constant) and key.value in SECRET_NAMES


def _render(el: ast.AST):
    """A literal argv element as a string, `<py>` for sys.executable, None for anything else."""
    if isinstance(el, ast.Constant) and isinstance(el.value, str):
        return el.value
    return PY if _dotted(el) == "sys.executable" else None


def _argv_prefix(call: ast.Call):
    """The allowlisted prefix an argv list starts with, or None."""
    if not call.args or not isinstance(call.args[0], (ast.List, ast.Tuple)):
        return None
    got = tuple(_render(e) for e in call.args[0].elts)
    for prefix in ARGV_PREFIXES:
        if got[: len(prefix)] == prefix:
            return prefix
    return None


def _is_runner(call: ast.Call) -> bool:
    return (isinstance(call.func, ast.Name) and call.func.id == "run") or \
        _dotted(call.func) in ("subprocess.run", "subprocess.check_output")


def _flag_assignments(tree: ast.AST, flag: str):
    """(lineno, col, value) for every assignment to `flag`; value is the Constant's value, or
    `_NOT_LITERAL` when it is anything else (bool(1), a tuple unpack, +=, ...)."""
    out = []
    for n in ast.walk(tree):
        if isinstance(n, ast.Assign):
            for t in n.targets:
                if isinstance(t, ast.Name) and t.id == flag:
                    out.append((n.lineno, n.col_offset,
                                n.value.value if isinstance(n.value, ast.Constant) else _NOT_LITERAL))
                elif any(isinstance(x, ast.Name) and x.id == flag and isinstance(x.ctx, ast.Store)
                         for x in ast.walk(t)):
                    out.append((n.lineno, n.col_offset, _NOT_LITERAL))
        elif isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name) and n.target.id == flag and n.value:
            out.append((n.lineno, n.col_offset,
                        n.value.value if isinstance(n.value, ast.Constant) else _NOT_LITERAL))
        elif isinstance(n, ast.AugAssign) and isinstance(n.target, ast.Name) and n.target.id == flag:
            out.append((n.lineno, n.col_offset, _NOT_LITERAL))
    return out


def _is_info_print(node: ast.AST) -> bool:
    """print() of plain string constants only (no f-string, name or call): the one place the word
    `publish` may appear, as a hint to the user."""
    return (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "print"
            and not node.keywords
            and all(isinstance(a, ast.Constant) and isinstance(a.value, str) for a in node.args))


def _mentions_publish(tree: ast.AST) -> bool:
    skip: set[int] = set()
    for n in ast.walk(tree):
        if _is_info_print(n):
            skip.update(id(x) for x in ast.walk(n))
    for n in ast.walk(tree):
        if id(n) in skip:
            continue
        if isinstance(n, (ast.List, ast.Tuple)):
            text = " ".join(e.value for e in n.elts if isinstance(e, ast.Constant) and isinstance(e.value, str))
        elif isinstance(n, ast.Constant) and isinstance(n.value, str):
            text = n.value
        else:
            continue
        if PUBLISH_CMD_RE.search(text) or any(
                isinstance(e, ast.Constant) and e.value == "publish" for e in getattr(n, "elts", [])):
            return True
    return False


def _bindings(trees):
    """name -> [(kind, node, is_top_level_def)] for every place a name is bound."""
    out: dict[str, list] = {}

    def add(name, kind, node, top=False):
        out.setdefault(name, []).append((kind, node, top))
    for _, tree in trees:
        top_defs = {id(n) for n in tree.body if isinstance(n, ast.FunctionDef)}
        assign_targets = {id(t) for n in ast.walk(tree) if isinstance(n, ast.Assign) for t in n.targets}
        for n in ast.walk(tree):
            if isinstance(n, ast.FunctionDef):
                add(n.name, "def", n, id(n) in top_defs)
                for a in [*n.args.args, *n.args.kwonlyargs, n.args.vararg, n.args.kwarg]:
                    if a is not None:
                        add(a.arg, "arg", a)
            elif isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store):
                add(n.id, "assign" if id(n) in assign_targets else "store", n)
            elif isinstance(n, (ast.Import, ast.ImportFrom)):
                for al in n.names:
                    add((al.asname or al.name).split(".")[0], "import", n)
    return out


def _direct_call(stmt: ast.stmt):
    """The Call a simple statement evaluates directly (`x = f()`, `f()`, `x = sorted(set(f()))`)."""
    v = stmt.value if isinstance(stmt, (ast.Expr, ast.Assign)) else None
    while (isinstance(v, ast.Call) and isinstance(v.func, ast.Name) and v.func.id in ("sorted", "set", "list")
           and len(v.args) == 1 and isinstance(v.args[0], ast.Call)):
        v = v.args[0]
    return v if isinstance(v, ast.Call) else None


def _proof_sha_values(trees):
    """(cell index, is_top_level, value node, lineno) for every assignment to PROOF_SHA.

    AnnAssign with a value and AugAssign are reported too (with the statement itself as the
    `value`), so every binding shape has to justify itself against the proof rules.
    """
    out = []
    for i, tree in trees:
        top = {id(s) for s in tree.body}
        for n in ast.walk(tree):
            if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "PROOF_SHA" for t in n.targets):
                out.append((i, id(n) in top, n.value, n.lineno))
            elif isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name) and n.target.id == "PROOF_SHA":
                out.append((i, id(n) in top, n.value if n.value is not None else n, n.lineno))
            elif isinstance(n, ast.AugAssign) and isinstance(n.target, ast.Name) and n.target.id == "PROOF_SHA":
                out.append((i, id(n) in top, n, n.lineno))
    return out


def _check_code(trees, problems):
    """The allowlist rules over all parsed code cells ((cell index, tree) in cell order)."""
    calls_all = [(i, n) for i, t in trees for n in ast.walk(t) if isinstance(n, ast.Call)]
    for i, tree in trees:
        for n in ast.walk(tree):
            if isinstance(n, ast.stmt) and not isinstance(n, ALLOWED_STMTS):
                problems.append(f"cell {i}: {type(n).__name__} statement is not allowed (line {n.lineno})")
            elif isinstance(n, ast.expr) and not isinstance(n, ALLOWED_EXPRS):
                problems.append(f"cell {i}: {type(n).__name__} expression is not allowed (line {n.lineno})")
            if isinstance(n, ast.Name) and n.id in BANNED_NAMES:
                problems.append(f"cell {i}: use of {n.id} is not allowed (line {n.lineno})")
            if isinstance(n, ast.Attribute) and n.attr in BANNED_ATTRS:
                problems.append(f"cell {i}: use of .{n.attr} is not allowed (line {n.lineno})")
            if isinstance(n, ast.Import):
                for al in n.names:
                    if al.name not in IMPORTS or al.asname:
                        problems.append(f"cell {i}: import {al.name} is not allowed")
            if isinstance(n, ast.ImportFrom):
                if n.module not in FROM_IMPORTS or (
                        any(al.asname for al in n.names)
                        and not (n.module == "scripts" and [al.name for al in n.names] == ["colab_backfill_checks"])):
                    problems.append(f"cell {i}: from {n.module} import ... is not allowed")
        for st in tree.body:
            if isinstance(st, (ast.Raise, ast.Return, ast.Break)):
                problems.append(f"cell {i}: unconditional top-level {type(st).__name__.lower()} (line {st.lineno})")

    # callables
    for i, c in calls_all:
        f = c.func
        if isinstance(f, ast.Name):
            ok = f.id in CALL_NAMES
            name = f.id
        elif isinstance(f, ast.Attribute):
            dotted = _dotted(f)
            name = dotted or f".{f.attr}"
            ok = (dotted in CALL_DOTTED) if dotted and dotted.split(".")[0] in MODULES else f.attr in METHODS
        else:
            ok, name = False, ast.dump(f)[:30]
        if not ok:
            problems.append(f"cell {i}: call to {name} is not allowed (line {c.lineno})")

    # helper / module names
    binds = _bindings(trees)
    for h in HELPERS:
        found = binds.get(h, [])
        if len(found) != 1 or found[0][0] != "def" or not found[0][2]:
            problems.append(f"{h} must be defined exactly once, as a top-level def (found {[b[0] for b in found]})")
    chk_b = binds.get("chk", [])
    if len(chk_b) != 1 or not (isinstance(chk_b[0][1], ast.ImportFrom) and chk_b[0][1].module == "scripts"
                               and [(a.name, a.asname) for a in chk_b[0][1].names] == [("colab_backfill_checks", "chk")]):
        problems.append("chk must be bound exactly once, by `from scripts import colab_backfill_checks as chk`")
    for mod in ("subprocess", "sys", "os"):
        if any(kind != "import" for kind, _, _ in binds.get(mod, [])):
            problems.append(f"{mod} must only be bound by `import {mod}`")
    for flag in FLAGS:
        if any(kind != "assign" for kind, _, _ in binds.get(flag, [])):
            problems.append(f"{flag} must only be bound by plain assignment")
    for name in ("PROOF_SHA", "REMAINING"):
        if any(kind not in ("assign",) for kind, _, _ in binds.get(name, [])):
            problems.append(f"{name} must only be bound by plain assignment")

    # helper bodies: no early return
    defs = {n.name: n for _, t in trees for n in t.body if isinstance(n, ast.FunctionDef)}
    for h in HELPERS:
        if h in defs:
            for r in (n for n in ast.walk(defs[h]) if isinstance(n, ast.Return)):
                if r is not defs[h].body[-1]:
                    problems.append(f"{h}: return only as the last statement (line {r.lineno})")
    run_def = defs.get("run")
    runner_ok = set()
    if run_def is not None and run_def.args.args:
        first = run_def.args.args[0].arg
        inner = [n for n in ast.walk(run_def) if isinstance(n, ast.Call) and _dotted(n.func) == "subprocess.run"
                 and n.args and isinstance(n.args[0], ast.Name) and n.args[0].id == first]
        if not inner or not any(isinstance(n, ast.Raise) for n in ast.walk(run_def)):
            problems.append("run must call subprocess.run(<its argv>) and raise on a nonzero exit")
        runner_ok = {id(n) for n in inner}

    # commands: literal allowlisted argv only; stage-upload solely through stage(); `-c` payloads scanned
    stage_def = defs.get("stage")
    ok_stage_uploads = set()
    if stage_def is not None:
        for s in stage_def.body:
            c = _direct_call(s)
            if c is not None and _dotted(c.func) == "run" and _argv_prefix(c) == STAGE_UPLOAD:
                ok_stage_uploads.add(id(c))
    for i, c in calls_all:
        if not _is_runner(c) or id(c) in runner_ok:
            continue
        prefix = _argv_prefix(c)
        if prefix == STAGE_UPLOAD and id(c) not in ok_stage_uploads:
            problems.append(f"cell {i}: stage-upload may only be invoked by stage() (line {c.lineno}); a direct "
                            "call skips stage()'s proof and completeness gates")
            continue
        if prefix == PY_C:
            elts = c.args[0].elts if c.args and isinstance(c.args[0], (ast.List, ast.Tuple)) else []
            payload = elts[2] if len(elts) > 2 else None
            if not (isinstance(payload, ast.Constant) and isinstance(payload.value, str)):
                problems.append(f"cell {i}: a -c payload must be a plain string literal (line {c.lineno}); "
                                "it is arbitrary code the allowlist cannot see")
            elif CODE_ESCAPE_RE.search(payload.value):
                problems.append(f"cell {i}: -c payload may not reference staging or publish (line {c.lineno}): "
                                f"{payload.value[:60]!r}")
            continue
        if prefix is None:
            argv = [_render(e) for e in c.args[0].elts] if c.args and isinstance(c.args[0], (ast.List, ast.Tuple)) else None
            if argv and "publish" in argv:
                problems.append(f"cell {i}: forbidden call scripts.hf_backfill publish: the notebook must not publish")
            else:
                problems.append(f"cell {i}: command is not allowlisted (line {c.lineno}): argv must be a literal "
                                f"list starting with an allowed prefix, got {argv!r}")

    # required steps: unconditional top-level statements, proof before the (guarded) stage() call
    pos: dict[str, tuple[int, int]] = {}
    proof_call: ast.Call | None = None
    for i, tree in trees:
        for st in tree.body:
            call = _direct_call(st)
            if call is not None:
                d = _dotted(call.func)
                if d == "chk.append_only_proof" and proof_call is None:
                    proof_call = call
                    pos.setdefault(d, (i, st.lineno))
                elif d in ("checkout_pinned", "dry_run"):
                    pos.setdefault(d, (i, st.lineno))
            if (isinstance(st, ast.If) and isinstance(st.test, ast.Name) and st.test.id == "CONFIRM_STAGE"
                    and len(st.body) == 1 and isinstance(st.body[0], ast.Expr)
                    and isinstance(st.body[0].value, ast.Call) and _dotted(st.body[0].value.func) == "stage"
                    and not st.body[0].value.args):
                pos.setdefault("stage", (i, st.lineno))
    for name in ("checkout_pinned", "dry_run", "chk.append_only_proof", "stage"):
        if name not in pos:
            problems.append(f"call to {name} not found as an unconditional top-level statement"
                            + (" (stage() must be the body of `if CONFIRM_STAGE:`)" if name == "stage" else ""))
    if sum(1 for _, c in calls_all if _dotted(c.func) == "stage") != 1:
        problems.append("stage() must be called exactly once, as the body of `if CONFIRM_STAGE:`")
    if "stage" in pos and "chk.append_only_proof" in pos and pos["chk.append_only_proof"] >= pos["stage"]:
        problems.append("append_only_proof must run before stage-upload")
    if not _scan_split_complete(trees):
        problems.append("call to chk.split_complete not found (outside any def, try or loop-free dead code)")
    if not ok_stage_uploads:
        problems.append("call to stage-upload not found as an unconditional top-level statement of stage()")

    # the proof may not be self-referential, and the proof hash may not be fabricated
    proven_db: str | None = None
    if proof_call is not None:
        args = proof_call.args
        if len(args) == 2 and all(isinstance(a, ast.Name) for a in args) and args[0].id != args[1].id:
            proven_db = args[1].id
        else:
            problems.append("append_only_proof must compare two different databases, as plain names "
                            "(a self-proof or computed argument proves nothing)")
    reset_before_proof = False
    proof_pos = pos.get("chk.append_only_proof")
    for i, top, value, lineno in _proof_sha_values(trees):
        if isinstance(value, ast.Constant) and value.value is None:
            if proof_pos is not None and top and i == proof_pos[0] and lineno < proof_pos[1]:
                reset_before_proof = True
            continue
        if (proven_db is not None and isinstance(value, ast.Call) and isinstance(value.func, ast.Name)
                and value.func.id == "sha256_file" and len(value.args) == 1
                and isinstance(value.args[0], ast.Name) and value.args[0].id == proven_db
                and not value.keywords):
            continue
        problems.append(f"PROOF_SHA must only be None or sha256_file(<the proven DB>) (cell {i}, line {lineno}); "
                        "any other value is a fabricated proof hash")
    if proof_call is not None and not reset_before_proof:
        problems.append("PROOF_SHA = None must run before append_only_proof in the same cell, so a failed "
                        "re-check cannot leave a stale proof from an earlier run")


def _scan_split_complete(trees) -> bool:
    """chk.split_complete reachable from top-level code through if/for only (not in a def)."""
    def walk(stmts):
        for st in stmts:
            if isinstance(st, (ast.If, ast.For)):
                if walk(st.body) or walk(st.orelse):
                    return True
            else:
                call = _direct_call(st)
                if call is not None and _dotted(call.func) == "chk.split_complete":
                    return True
        return False
    return any(walk(t.body) for _, t in trees)


def check_notebook(path: Path) -> list[str]:
    """Return a list of problems (empty means the notebook is clean)."""
    problems: list[str] = []
    nb = json.loads(Path(path).read_text(encoding="utf-8"))
    if nb.get("nbformat") != 4:
        problems.append(f"nbformat is {nb.get('nbformat')!r}, expected 4")

    code_cells = [c for c in nb.get("cells", []) if c.get("cell_type") == "code"]
    if not code_cells:
        problems.append("no code cells")
    trees: list[tuple[int, ast.AST]] = []  # (cell index, parsed tree) in cell order
    for i, cell in enumerate(nb.get("cells", [])):
        if cell.get("cell_type") != "code":
            continue
        code = _source(cell)
        if cell.get("outputs"):
            problems.append(f"cell {i}: outputs not cleared")
        if cell.get("execution_count") is not None:
            problems.append(f"cell {i}: execution_count not cleared")
        if any(line.lstrip().startswith(("!", "%")) for line in code.splitlines()):
            problems.append(f"cell {i}: shell/cell magics are not allowed"
                            + (" (forbidden call scripts.hf_backfill publish)" if PUBLISH_CMD_RE.search(code) else ""))
        if any(line.lstrip().startswith(("!", "%")) and any(n in line for n in SECRET_NAMES[:3])
               for line in code.splitlines()):
            problems.append(f"cell {i}: shell magic references a secret")
        try:
            tree = ast.parse(_blank_magics(code))
        except SyntaxError as exc:
            problems.append(f"cell {i}: SyntaxError line {exc.lineno}: {exc.msg}")
            continue
        trees.append((i, tree))
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call) and getattr(node.func, "id", "") == "print"
                    and any(_reads_secret(n) for a in node.args for n in ast.walk(a))):
                problems.append(f"cell {i}: print() references a secret variable")

    if trees:
        _check_code(trees, problems)
    for _, tree in trees:
        if _mentions_publish(tree):
            problems.append("forbidden call scripts.hf_backfill publish: the notebook must not publish "
                            "(only a print() of plain string constants may mention it)")
            break

    joined = "\n".join(_source(c) for c in code_cells)
    for flag in FLAGS:
        # Cell order, then position in the cell: the LAST assignment is the value later cells see.
        assigns = [(i, ln, col, v) for i, tree in trees for ln, col, v in _flag_assignments(tree, flag)]
        assigns.sort(key=lambda a: a[:3])
        if not assigns:
            problems.append(f"{flag} = False not found (must be off by default)")
        elif assigns[-1][3] is not False:
            final = assigns[-1][3]
            problems.append(f"{flag} is True" if final is True
                            else f"{flag} final assignment is not a literal False")
    m = re.search(r"^STAGING_REPO\s*=\s*['\"]([^'\"]+)['\"]", joined, re.MULTILINE)
    if not m:
        problems.append("STAGING_REPO literal not found")
    elif m.group(1).strip().lower() == PROD_REPO:
        problems.append("STAGING_REPO is the production dataset")
    c = re.search(r"^REPO_COMMIT\s*=\s*['\"]([^'\"]*)['\"]", joined, re.MULTILINE)
    if not c:
        problems.append("REPO_COMMIT literal not found (the checkout must be pinned to a commit)")
    elif c.group(1) and not re.fullmatch(r"[0-9a-f]{40}", c.group(1)):
        problems.append("REPO_COMMIT must be empty or a full 40-character lowercase sha")
    for name in FORBIDDEN_CALLS:
        if " " not in name and re.search(rf"\b{re.escape(name)}\b", joined):
            problems.append(f"forbidden call {name}: the notebook must not publish")
    # Whole file, markdown cells and metadata included.
    raw = Path(path).read_text(encoding="utf-8")
    if TOKEN_RE.search(raw):
        problems.append("a token-shaped string is present")
    return problems


def main(argv: list[str]) -> int:
    path = Path(argv[1]) if len(argv) > 1 else DEFAULT_NB
    problems = check_notebook(path)
    try:
        import nbformat
        nbformat.validate(nbformat.read(str(path), as_version=4))
        print("nbformat.validate: OK")
    except ImportError:
        print("nbformat not installed; skipped nbformat.validate")
    except Exception as exc:  # nbformat.ValidationError
        problems.append(f"nbformat.validate: {exc}")
    for p in problems:
        print("FAIL:", p)
    if not problems:
        print(f"{path.name}: OK")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
