"""Static checks for notebooks/colab_backfill.ipynb (no Colab, GPU or network needed).

    uv run python scripts/check_colab_notebook.py [notebook.ipynb]
    uv run --with nbformat python scripts/check_colab_notebook.py   # also nbformat.validate

Checks: valid JSON; every code cell parses with ast (shell/cell magics are blanked
first); outputs and execution counts are cleared; embedding and staging are disabled by
default (the LAST assignment of each flag, in cell order, must be a literal False); the repo
checkout is pinned to a full commit sha; the notebook can only write to a staging repo that is not
production (no upload, commit or Space-restart call against the dataset, and no executable
`scripts.hf_backfill publish` command); the required steps are real calls, in order (the append-only
proof before stage-upload), not marker text; no hardcoded token; no cell prints or echoes a secret
(including `os.environ["HF_TOKEN"]` / `userdata.get("HF_TOKEN")` read by key).
"""
import ast
import json
import re
import sys
from pathlib import Path

DEFAULT_NB = Path(__file__).resolve().parent.parent / "notebooks" / "colab_backfill.ipynb"
SECRET_NAMES = ("HF_TOKEN", "GH_TOKEN", "EDGAR_USER_AGENT", "auth")
PROD_REPO = "egoh33/rag-workbench"
# The notebook may only stage through `scripts.hf_backfill stage-upload`; publishing is out of scope.
# A name containing a space is a shell command, matched only in executable code (a print() that
# tells the user how to publish from a checkout is allowed).
FORBIDDEN_CALLS = ("create_commit", "upload_file", "upload_folder", "CommitOperationAdd",
                   "CommitOperationDelete", "delete_file", "delete_repo", "restart_space",
                   "scripts.hf_backfill publish")
PUBLISH_CMD_RE = re.compile(r"hf_backfill(?:\.py)?\s+publish\b")
FLAGS = ("CONFIRM_EXECUTE", "CONFIRM_STAGE")
# Steps that must be real calls: (call name, label). stage-upload is matched as a command argument.
REQUIRED_CALLS = ("checkout_pinned", "dry_run", "split_complete", "append_only_proof")
TOKEN_RE = re.compile(r"\b(hf_[A-Za-z0-9]{20,}|ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})")


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
    elif (isinstance(node, ast.Call) and getattr(node.func, "id", "") == "getenv" and node.args):
        key = node.args[0]
    return isinstance(key, ast.Constant) and key.value in SECRET_NAMES


def _callee(node: ast.Call) -> str:
    f = node.func
    return f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else ""


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


_NOT_LITERAL = object()


def _is_info_print(node: ast.AST) -> bool:
    """A print() whose arguments are plain strings (constants or call-free f-strings): purely informational."""
    if not (isinstance(node, ast.Call) and _callee(node) == "print"):
        return False
    parts = list(node.args) + [k.value for k in node.keywords]
    return not any(isinstance(x, ast.Call) for p in parts for x in ast.walk(p))


def _publishes(tree: ast.AST) -> bool:
    """True when code holds a `hf_backfill publish` command. Only an informational print() is exempt;
    print(subprocess.run([... 'publish'])) is still executable and is inspected."""
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
        if PUBLISH_CMD_RE.search(text):
            return True
    return False


_RUNNERS = ("run", "check_call", "check_output", "call", "Popen")


def _static_truth(test: ast.AST):
    """True/False for a literal condition, None when it is only known at run time."""
    try:
        return bool(ast.literal_eval(test))
    except (ValueError, TypeError, SyntaxError):
        pass
    if isinstance(test, ast.UnaryOp) and isinstance(test.op, ast.Not):
        inner = _static_truth(test.operand)
        return None if inner is None else not inner
    return None


def _stmt_calls(stmt: ast.stmt):
    """Calls evaluated by one simple statement (not inside a lambda or a print())."""
    out = []

    def visit(n):
        if isinstance(n, ast.Lambda) or (isinstance(n, ast.Call) and _callee(n) == "print"):
            return
        if isinstance(n, ast.Call):
            out.append(n)
        for c in ast.iter_child_nodes(n):
            visit(c)
    visit(stmt)
    return out


def _executable_calls(trees, defs, seen=()):
    """Calls that run when the cells run top to bottom, as (cell, line, col, Call): not inside an
    uncalled def, a dead branch or code after a raise, nor in print() arguments. A call to a function
    defined in the notebook is expanded at its call site (position = the call site)."""
    out = []

    def block(stmts, cell, anchor, stack):
        for st in stmts:
            if isinstance(st, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue
            if isinstance(st, ast.If):
                t = _static_truth(st.test)
                out.extend((cell, *pos(st.test, anchor), c) for c in _stmt_calls(ast.Expr(st.test)))
                if t is not False:
                    block(st.body, cell, anchor, stack)
                if t is not True:
                    block(st.orelse, cell, anchor, stack)
                continue
            if isinstance(st, ast.While) and _static_truth(st.test) is False:
                block(st.orelse, cell, anchor, stack)
                continue
            if isinstance(st, (ast.For, ast.AsyncFor, ast.While, ast.With, ast.AsyncWith, ast.Try)):
                head = [x for x in ast.iter_child_nodes(st) if isinstance(x, ast.expr) or isinstance(x, ast.withitem)]
                for h in head:
                    out.extend((cell, *pos(c, anchor), c) for c in _stmt_calls(ast.Expr(h if isinstance(h, ast.expr) else h.context_expr)))
                for field in ("body", "handlers", "orelse", "finalbody"):
                    for sub in getattr(st, field, []):
                        block(sub.body if isinstance(sub, ast.ExceptHandler) else [sub], cell, anchor, stack)
                continue
            for c in _stmt_calls(st):
                out.append((cell, *pos(c, anchor), c))
                name = c.func.id if isinstance(c.func, ast.Name) else None
                if name in defs and name not in stack:
                    expand(name, cell, anchor or (c.lineno, c.col_offset), stack + (name,))
            if isinstance(st, ast.Raise):
                return

    def pos(n, anchor):
        return anchor if anchor else (n.lineno, n.col_offset)

    def expand(name, cell, anchor, stack):
        block(defs[name].body, cell, anchor, stack)

    for cell, tree in trees:
        block(tree.body, cell, None, seen)
    return sorted(out, key=lambda t: t[:3])


def _is_stage_upload(call: ast.Call) -> bool:
    """The real invocation: a runner called with an argv list holding scripts.hf_backfill then stage-upload."""
    if _callee(call) not in _RUNNERS or not call.args or not isinstance(call.args[0], (ast.List, ast.Tuple)):
        return False
    argv = [e.value for e in call.args[0].elts if isinstance(e, ast.Constant) and isinstance(e.value, str)]
    return ("scripts.hf_backfill" in argv and "stage-upload" in argv
            and argv.index("scripts.hf_backfill") < argv.index("stage-upload"))


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
    # The required steps must be executed calls (top-level code, or a notebook function called from it),
    # not marker text, uncalled defs, dead branches or print() arguments; and the proof comes first.
    defs = {n.name: n for _, t in trees for n in t.body if isinstance(n, ast.FunctionDef)}
    first_call: dict[str, tuple[int, int, int]] = {}
    for cell, ln, col, call in _executable_calls(trees, defs):
        names = [_callee(call)]
        if _is_stage_upload(call):
            names.append("stage-upload")
        for name in names:
            if name in REQUIRED_CALLS + ("stage-upload",) and name not in first_call:
                first_call[name] = (cell, ln, col)  # list is position-sorted: the first is the earliest
    for name in REQUIRED_CALLS + ("stage-upload",):
        if name not in first_call:
            problems.append(f"call to {name} not found (a marker string, an uncalled def or a dead branch does not count)")
    if "stage-upload" in first_call and "append_only_proof" in first_call \
            and first_call["append_only_proof"] >= first_call["stage-upload"]:
        problems.append("append_only_proof must run before stage-upload")
    publishes = any(_publishes(tree) for _, tree in trees) or any(
        PUBLISH_CMD_RE.search(line) for c in code_cells for line in _source(c).splitlines()
        if line.lstrip().startswith(("!", "%")))
    for name in FORBIDDEN_CALLS:
        hit = publishes if " " in name else re.search(rf"\b{re.escape(name)}\b", joined)
        if hit:
            problems.append(f"forbidden call {name}: the notebook must not publish")
    # Whole file, markdown cells and metadata included.
    raw = Path(path).read_text(encoding="utf-8")
    if TOKEN_RE.search(raw):
        problems.append("a token-shaped string is present")
    for i, cell in enumerate(nb.get("cells", [])):
        if cell.get("cell_type") != "code":
            continue
        for line in _source(cell).splitlines():
            if line.lstrip().startswith(("!", "%")) and any(n in line for n in SECRET_NAMES[:3]):
                problems.append(f"cell {i}: shell magic references a secret")
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
