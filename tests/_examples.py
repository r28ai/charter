"""Checking a code example a reader will copy, without running it.

``_doc_blocks.py`` runs the documentation blocks that can run. The examples here
cannot: a pack's docstring calls a live API with a token only the reader holds,
and a tool page leaves its required arguments as ``...``. Nothing looked at
them, and three kinds of bug reached readers through them at once. Every pack
docstring imported ``StaticTokenProvider`` from ``charter``, which has not
exported it since credentials moved to ``charter.auth``. The paging examples on
the GitHub and Linear pages raised ``UnboundLocalError`` before their first
request. Four tool pages showed ``ainvoke({})`` for a tool that refuses an empty
call.

All three are decidable from the source, which is what this does:

* the block parses, and every name it imports from ``charter`` exists;
* every attribute read off an imported name exists;
* every keyword passed to something ``charter`` exports is one of its
  parameters;
* every tool call's arguments pass that tool's own validation, with ``...``,
  and any value that is not a literal, standing for what the reader fills in;
* no function reads a module-level name before assigning it, which makes the
  name local to the function and the first read an ``UnboundLocalError``.
"""

from __future__ import annotations

import ast
import importlib
import inspect
from typing import Any, Dict, Iterator, List, Optional, Set, Tuple

from pydantic.alias_generators import to_snake

from charter.execution.validation import validate_input
from charter.tool import Tool
from charter.types.errors import ToolValidationError

_MISSING = object()
_UNKNOWN = object()

# Keywords `ainvoke` takes for itself rather than passing to the tool.
_CALL_OPTIONS = {"headers", "client"}

# Each of these is a scope of its own, so a name inside one is not the
# enclosing function's.
_SCOPES = (
    ast.FunctionDef,
    ast.AsyncFunctionDef,
    ast.ClassDef,
    ast.Lambda,
    ast.ListComp,
    ast.SetComp,
    ast.DictComp,
    ast.GeneratorExp,
)


def example_problems(source: str, namespace: Optional[Dict[str, Any]] = None) -> List[str]:
    """Everything wrong with one example, as sentences; empty when nothing is.

    ``namespace`` carries what earlier blocks on the same page imported, since a
    page's blocks are read in order, and receives what this one imports.
    """
    namespace = {} if namespace is None else namespace
    try:
        tree = compile(
            source, "<example>", "exec", ast.PyCF_ONLY_AST | ast.PyCF_ALLOW_TOP_LEVEL_AWAIT
        )
    except SyntaxError as exc:
        return [f"does not parse: {exc.msg} (line {exc.lineno})"]

    problems = _imports(tree, namespace)
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and isinstance(node.ctx, ast.Load):
            problems += _resolve(node, namespace)[1]
        elif isinstance(node, ast.Call):
            problems += _call(node, namespace)
    problems += _unbound_locals(tree)
    return list(dict.fromkeys(problems))


def _imports(tree: ast.AST, namespace: Dict[str, Any]) -> List[str]:
    problems = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and (node.module or "").split(".")[0] == "charter":
            assert node.module is not None
            try:
                module = importlib.import_module(node.module)
            except ImportError:
                problems.append(f"`from {node.module} import ...`: there is no `{node.module}`")
                continue
            for alias in node.names:
                if alias.name == "*":
                    continue
                bound = getattr(module, alias.name, _MISSING)
                if bound is _MISSING:
                    try:
                        bound = importlib.import_module(f"{node.module}.{alias.name}")
                    except ImportError:
                        problems.append(
                            f"`from {node.module} import {alias.name}`: "
                            f"`{node.module}` has no `{alias.name}`"
                        )
                        continue
                namespace[alias.asname or alias.name] = bound
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] != "charter":
                    continue
                try:
                    module = importlib.import_module(alias.name)
                except ImportError:
                    problems.append(f"`import {alias.name}`: there is no such module")
                    continue
                if alias.asname:
                    namespace[alias.asname] = module
                else:
                    namespace["charter"] = importlib.import_module("charter")
    return problems


def _resolve(expr: ast.expr, namespace: Dict[str, Any]) -> Tuple[Any, List[str]]:
    """What an attribute chain rooted at an imported name refers to.

    ``_UNKNOWN`` when the chain starts at a name the example made itself — a
    variable, a stdlib module — which there is nothing to check against.
    """
    chain = []
    while isinstance(expr, ast.Attribute):
        chain.append(expr.attr)
        expr = expr.value
    if not isinstance(expr, ast.Name) or expr.id not in namespace:
        return _UNKNOWN, []
    obj, spelled = namespace[expr.id], expr.id
    for attr in reversed(chain):
        spelled += f".{attr}"
        found = getattr(obj, attr, _MISSING)
        if found is _MISSING and inspect.ismodule(obj):
            try:
                found = importlib.import_module(f"{obj.__name__}.{attr}")
            except ImportError:
                pass
        if found is _MISSING:
            # A field of a pydantic class is an attribute of its instances only.
            if attr in (getattr(obj, "model_fields", None) or {}):
                return _UNKNOWN, []
            return _UNKNOWN, [f"`{spelled}` does not exist"]
        obj = found
    return obj, []


def _call(node: ast.Call, namespace: Dict[str, Any]) -> List[str]:
    func = node.func
    if isinstance(func, ast.Attribute) and func.attr in ("invoke", "ainvoke"):
        tool, _ = _resolve(func.value, namespace)
        if isinstance(tool, Tool):
            return _tool_call(tool, node)

    target, _ = _resolve(func, namespace)
    if target is _UNKNOWN or not callable(target):
        return []
    try:
        parameters = inspect.signature(target).parameters
    except (TypeError, ValueError):
        return []
    if any(p.kind is p.VAR_KEYWORD for p in parameters.values()):
        return []
    name = getattr(target, "__qualname__", repr(target))
    return [
        f"`{name}()` takes no `{keyword.arg}`"
        for keyword in node.keywords
        if keyword.arg and keyword.arg not in parameters
    ]


def _tool_call(tool: Tool, node: ast.Call) -> List[str]:
    """Validate a call's arguments the way ``ainvoke`` will, leaving the reader's own open."""
    pairs: List[Tuple[Optional[ast.expr], ast.expr]] = []
    if node.args:
        first = node.args[0]
        if not isinstance(first, ast.Dict):
            return []  # built somewhere else: nothing here to read
        pairs += list(zip(first.keys, first.values, strict=True))
    pairs += [
        (ast.Constant(keyword.arg) if keyword.arg else None, keyword.value)
        for keyword in node.keywords
        if keyword.arg not in _CALL_OPTIONS
    ]

    args: Dict[str, Any] = {}
    left_open: Set[str] = set()
    for key, value in pairs:
        if not (isinstance(key, ast.Constant) and isinstance(key.value, str)):
            return []  # a `**spread` or a computed key: the arguments are not all here
        try:
            literal = ast.literal_eval(value)
        except (ValueError, TypeError, SyntaxError):
            literal = ...
        if _holds_a_placeholder(literal):
            left_open.add(to_snake(key.value))
        args[key.value] = literal

    try:
        validate_input(tool.llm_schema(), args, tool_name=tool.name)
    except ToolValidationError as exc:
        return [
            f"`{tool.name}` refuses the example: "
            f"{'.'.join(str(part) for part in error['loc']) or '(input)'}: {error['msg']}"
            for error in exc.errors
            if not _left_to_the_reader(error, left_open)
        ]
    return []


def _holds_a_placeholder(value: Any) -> bool:
    if value is ...:
        return True
    if isinstance(value, dict):
        return any(_holds_a_placeholder(v) for v in value.values())
    if isinstance(value, (list, tuple, set)):
        return any(_holds_a_placeholder(v) for v in value)
    return False


def _left_to_the_reader(error: Dict[str, Any], left_open: Set[str]) -> bool:
    """An error under an argument the reader fills in, other than its name being wrong."""
    loc = error.get("loc") or ()
    return (
        bool(loc) and error.get("type") != "extra_forbidden" and to_snake(str(loc[0])) in left_open
    )


def _own_scope(node: ast.AST) -> Iterator[ast.AST]:
    """The nodes under ``node`` that belong to its scope, not to one nested in it."""
    for child in ast.iter_child_nodes(node):
        if isinstance(child, _SCOPES):
            continue
        yield child
        yield from _own_scope(child)


def _unbound_locals(tree: ast.Module) -> List[str]:
    module_level: Set[str] = set()
    for statement in tree.body:
        if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            module_level.add(statement.name)
            continue
        for node in [statement, *_own_scope(statement)]:
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
                module_level.add(node.id)
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                module_level.update((a.asname or a.name).split(".")[0] for a in node.names)

    problems = []
    for function in ast.walk(tree):
        if not isinstance(function, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        parameters = {a.arg for a in ast.walk(function.args) if isinstance(a, ast.arg)}
        declared: Set[str] = set()
        first_store: Dict[str, Tuple[int, int]] = {}
        first_load: Dict[str, Tuple[int, int]] = {}
        for statement in function.body:
            if isinstance(statement, _SCOPES):
                continue
            for node in [statement, *_own_scope(statement)]:
                if isinstance(node, (ast.Global, ast.Nonlocal)):
                    declared.update(node.names)
                elif isinstance(node, ast.Name):
                    book = first_store if isinstance(node.ctx, ast.Store) else first_load
                    position = (node.lineno, node.col_offset)
                    if node.id not in book or position < book[node.id]:
                        book[node.id] = position
        for name, stored in first_store.items():
            if (
                name in module_level
                and name not in declared | parameters
                and name in first_load
                and first_load[name] < stored
            ):
                problems.append(
                    f"`{function.name}()` assigns `{name}`, which makes it local, and reads it "
                    f"before that on line {first_load[name][0]}: UnboundLocalError"
                )
    return problems
