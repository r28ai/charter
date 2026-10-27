#!/usr/bin/env python
"""Draft a Charter pack from an OpenAPI document, word for word.

Most of declaring a pack is transcription: every parameter, every body field,
every enum member and every description, copied out of the provider's spec into
``Annotated`` fields. Done by a model it is slow, expensive, and lossy in the
one way that matters — a dropped enum member is a 400 nobody can reproduce. A
spec is already a complete machine-readable list of those facts, so this reads
it and writes them out mechanically, and the reviewer's time goes on what a
spec cannot say.

What it writes, under ``src/charter/packs/<pack>/`` by default:

* ``types/common.py`` — every model a request reaches: the component schemas,
  the inline objects (deduplicated by shape, so an object the spec repeats
  inline is one class), discriminated unions, and the enums worth a name.
* ``types/<tag>.py`` — one ``<Tool>Request`` per operation, grouped by the
  operation's first tag. Parameters and body properties are flattened onto it,
  each marked ``Path``/``Query``/``Header``/``Body``.
* ``__init__.py`` — the credential, ``configure()``, the factory and one tool
  per operation, built from the servers, the security scheme, the casing the
  spec uses and the pagination you name on the command line.

What it decides mechanically, and why each rule is the skill's rule:

* Descriptions are the spec's, verbatim. Nothing of the script's own is mixed
  in; where it adds a sentence (a documented server default), it is a
  ``Gloss``.
* Not required means ``Optional[...] = None``. A documented ``default`` is
  never copied onto the field, because a default on the schema goes out on
  every call.
* ``enum``/``const`` become ``Literal`` with every member. Constraints become
  ``ge``/``le``/``min_length``/``max_length``/``pattern``.
* ``readOnly`` is ``Mode("response_only")``; ``deprecated`` is
  ``Mode("disabled")``; ``format: byte`` is ``Format("base64")``.
* A wire name the casing convention cannot produce gets ``WireName``.

What it does not decide, and lists in the report it prints for the reviewer:
kinds of credential and scopes beyond what the spec's ``security`` names, an
``Envelope`` for an API that answers 200 on failure, cross-field rules written in
prose, fields whose description says to send ``null`` (Charter omits unset
fields and never sends ``null``), undescribed parameters the model would fill
blind, and anything the script could not express. The report is the review
checklist; the skill's steps are the rest of it.

The output is a draft, and the review edits it directly: from then on the pack
is maintained like any other. To see what the vendor has changed since, draft
the spec again into a scratch directory with ``--out`` and diff the two; the
script refuses to write over a pack that is already there.

Supports OpenAPI 3.0 and 3.1, and Swagger 2.0 by converting it to the 3.0 shape
first. Local ``$ref`` only. The output is formatted with ``ruff`` when it is
installed.

Usage::

    uv run python scripts/openapi_to_pack.py https://public-api.luma.com/openapi.json \\
        --pack luma --cursor-param pagination_cursor --cursor-field next_cursor \\
        --more-field has_more \\
        --reference-url 'https://docs.luma.com/reference/{method}_{slug}'
"""

from __future__ import annotations

import argparse
import json
import keyword
import re
import sys
import textwrap
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

METHODS = ("get", "post", "put", "patch", "delete")
_SKIPPED_METHODS = ("head", "options", "trace")

# Names pydantic's BaseModel already uses: a field by one of these shadows it.
_BASEMODEL_NAMES = {
    "construct",
    "copy",
    "dict",
    "fields",
    "json",
    "parse_file",
    "parse_obj",
    "parse_raw",
    "schema",
    "schema_json",
    "update_forward_refs",
    "validate",
}
_RESERVED_CLASS_NAMES = {
    "Annotated",
    "Any",
    "Body",
    "Dict",
    "Field",
    "Format",
    "Gloss",
    "Header",
    "List",
    "Literal",
    "Mode",
    "Optional",
    "PackModel",
    "Path",
    "Query",
    "Union",
    "WireName",
}

_NULL_HINT = re.compile(r"\bnull\b|\bnil\b", re.I)


# --------------------------------------------------------------------------
# Loading and normalising
# --------------------------------------------------------------------------


def load_spec(source: str) -> Dict[str, Any]:
    if re.match(r"https?://", source):
        with urllib.request.urlopen(source, timeout=60) as response:  # noqa: S310
            text = response.read().decode("utf-8")
    else:
        text = Path(source).read_text(encoding="utf-8")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        try:
            import yaml  # type: ignore[import-untyped]
        except ImportError:
            sys.exit("The spec is not JSON, and PyYAML is not installed to read it as YAML.")
        return yaml.safe_load(text)


def swagger2_to_openapi3(spec: Dict[str, Any]) -> Dict[str, Any]:
    """The 3.0 shape of a Swagger 2.0 document, for the parts this script reads."""

    def fix_refs(node: Any) -> Any:
        if isinstance(node, dict):
            out = {}
            for key, value in node.items():
                if key == "$ref" and isinstance(value, str):
                    value = value.replace("#/definitions/", "#/components/schemas/")
                    value = value.replace("#/parameters/", "#/components/parameters/")
                    value = value.replace("#/responses/", "#/components/responses/")
                out[key] = fix_refs(value)
            if out.get("x-nullable") is True:
                out["nullable"] = True
            return out
        if isinstance(node, list):
            return [fix_refs(item) for item in node]
        return node

    spec = fix_refs(spec)
    scheme = (spec.get("schemes") or ["https"])[0]
    servers = []
    if spec.get("host"):
        servers.append({"url": f"{scheme}://{spec['host']}{spec.get('basePath', '')}"})
    consumes = spec.get("consumes") or ["application/json"]

    def convert_params(params: List[Dict[str, Any]], op_consumes: List[str]):
        kept, body, form = [], None, {}
        required_form: List[str] = []
        for param in params:
            if "$ref" in param:
                kept.append(param)
                continue
            where = param.get("in")
            if where == "body":
                body = {
                    "required": param.get("required", False),
                    "content": {op_consumes[0]: {"schema": param.get("schema", {})}},
                }
                if param.get("description"):
                    body["description"] = param["description"]
            elif where == "formData":
                schema = {k: v for k, v in param.items() if k not in ("name", "in", "required")}
                if schema.get("type") == "file":
                    schema = {
                        "type": "string",
                        "format": "binary",
                        **{k: v for k, v in schema.items() if k == "description"},
                    }
                form[param["name"]] = schema
                if param.get("required"):
                    required_form.append(param["name"])
            else:
                schema_keys = (
                    "type",
                    "format",
                    "items",
                    "enum",
                    "default",
                    "minimum",
                    "maximum",
                    "exclusiveMinimum",
                    "exclusiveMaximum",
                    "minLength",
                    "maxLength",
                    "pattern",
                    "minItems",
                    "maxItems",
                    "collectionFormat",
                )
                schema = {k: param[k] for k in schema_keys if k in param}
                converted = {k: v for k, v in param.items() if k not in schema_keys}
                converted["schema"] = schema
                kept.append(converted)
        if form:
            media = next(
                (m for m in op_consumes if "form" in m), "application/x-www-form-urlencoded"
            )
            body = {
                "required": bool(required_form),
                "content": {
                    media: {
                        "schema": {"type": "object", "properties": form, "required": required_form}
                    }
                },
            }
        return kept, body

    paths: Dict[str, Any] = {}
    for path, item in (spec.get("paths") or {}).items():
        new_item: Dict[str, Any] = {}
        shared, _ = convert_params(item.get("parameters", []), consumes)
        if shared:
            new_item["parameters"] = shared
        for method, op in item.items():
            if method not in METHODS + _SKIPPED_METHODS:
                continue
            op = dict(op)
            params, body = convert_params(op.get("parameters", []), op.get("consumes") or consumes)
            op["parameters"] = params
            if body:
                op["requestBody"] = body
            responses = {}
            for status, response in (op.get("responses") or {}).items():
                response = dict(response)
                if "schema" in response:
                    response["content"] = {"application/json": {"schema": response.pop("schema")}}
                responses[status] = response
            op["responses"] = responses
            new_item[method] = op
        paths[path] = new_item

    security_schemes = {}
    for name, scheme_def in (spec.get("securityDefinitions") or {}).items():
        scheme_def = dict(scheme_def)
        if scheme_def.get("type") == "basic":
            scheme_def = {"type": "http", "scheme": "basic"}
        elif scheme_def.get("type") == "oauth2":
            flow = scheme_def.get("flow", "accessCode")
            flow_name = {"accessCode": "authorizationCode", "application": "clientCredentials"}.get(
                flow, flow
            )
            scheme_def = {
                "type": "oauth2",
                "flows": {
                    flow_name: {
                        "authorizationUrl": scheme_def.get("authorizationUrl", ""),
                        "tokenUrl": scheme_def.get("tokenUrl", ""),
                        "scopes": scheme_def.get("scopes", {}),
                    }
                },
            }
        security_schemes[name] = scheme_def

    return {
        "openapi": "3.0.0",
        "info": spec.get("info", {}),
        "servers": servers,
        "paths": paths,
        "security": spec.get("security", []),
        "components": {
            "schemas": spec.get("definitions", {}),
            "parameters": {
                name: convert_params([p], consumes)[0][0]
                for name, p in (spec.get("parameters") or {}).items()
                if p.get("in") not in ("body", "formData")
            },
            "securitySchemes": security_schemes,
        },
    }


# --------------------------------------------------------------------------
# Names
# --------------------------------------------------------------------------


def snake(name: str) -> str:
    """``eventId``/``EventID``/``event-id``/``$event.id`` -> ``event_id``."""
    name = re.sub(r"[^0-9A-Za-z]+", "_", name)
    name = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", name)
    name = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", name)
    name = re.sub(r"_+", "_", name).strip("_").lower()
    return name or "field"


def pascal(name: str) -> str:
    parts = [p for p in re.split(r"[^0-9A-Za-z]+", name) if p]
    out = "".join(p[0].upper() + p[1:] for p in parts)
    if not out:
        return "Model"
    if out[0].isdigit():
        out = "N" + out
    return out


def singular(name: str) -> str:
    if name.endswith("ies") and len(name) > 4:
        return name[:-3] + "y"
    if name.endswith(("ses", "xes", "ches", "shes")):
        return name[:-2]
    if name.endswith("s") and not name.endswith("ss") and len(name) > 3:
        return name[:-1]
    return name + "Item"


def to_camel(snake_name: str) -> str:
    """The runtime's snake -> camel conversion, so a WireName is added exactly when needed."""
    parts = snake_name.split("_")
    return parts[0] + "".join(p.capitalize() for p in parts[1:])


def wire_case(names: Iterable[str]) -> str:
    """The convention most of these wire names follow: ``snake`` or ``camel``."""
    camel = sum(1 for n in names if re.search(r"[a-z][A-Z]", n))
    snake_count = sum(1 for n in names if "_" in n)
    return "camel" if camel > snake_count else "snake"


def python_name(wire: str, case: str) -> Tuple[str, Optional[str]]:
    """The field name for a wire name, and the ``WireName`` it needs, if any."""
    name = snake(wire)
    if keyword.iskeyword(name) or name in _BASEMODEL_NAMES or name.startswith("model_"):
        name += "_"
    produced = name if case == "snake" else to_camel(name)
    return name, (None if produced == wire else wire)


# --------------------------------------------------------------------------
# Source text
# --------------------------------------------------------------------------


def py_str(text: str, indent: int = 0, width: int = 88) -> str:
    """A string literal, split into implicitly concatenated pieces when long."""
    text = text.strip()
    if len(text) + indent < width - 4 and "\n" not in text:
        return json.dumps(text, ensure_ascii=False)
    pieces: List[str] = []
    for i, line in enumerate(text.split("\n")):
        last = i == len(text.split("\n")) - 1
        suffix = "" if last else "\n"
        wrapped = textwrap.wrap(
            line,
            width=max(30, width - indent - 6),
            drop_whitespace=False,
            replace_whitespace=False,
            break_long_words=False,
            break_on_hyphens=False,
            expand_tabs=False,
        ) or [""]
        for j, chunk in enumerate(wrapped):
            pieces.append(chunk + (suffix if j == len(wrapped) - 1 else ""))
    pad = " " * (indent + 4)
    body = "\n".join(pad + json.dumps(p, ensure_ascii=False) for p in pieces if p != "")
    return "(\n" + body + "\n" + " " * indent + ")"


def call(name: str, text: str, indent: int = 8) -> str:
    """``Name("text")``, the literal's own parentheses dropped when it has some."""
    literal = py_str(text, indent=indent)
    if literal.startswith("(\n"):
        literal = literal[1:-1].rstrip() + "\n" + " " * indent
    return f"{name}({literal})"


def docstring(text: str, indent: int = 4) -> str:
    text = text.strip().replace("\\", "\\\\").replace('"""', '\\"\\"\\"')
    pad = " " * indent
    lines = text.split("\n")
    if len(lines) == 1 and len(lines[0]) + indent + 6 <= 100:
        return f'{pad}"""{lines[0]}"""\n'
    out = [f'{pad}"""{lines[0]}']
    for line in lines[1:]:
        if not line.strip():
            out.append("")
            continue
        lead = re.match(r"\s*(?:[-*] |\d+\. )?", line).group(0)  # type: ignore[union-attr]
        out += textwrap.wrap(
            line,
            width=96 - indent,
            initial_indent=pad,
            subsequent_indent=pad + " " * len(lead),
            break_long_words=False,
            break_on_hyphens=False,
        ) or [pad + line]
    out.append(f'{pad}"""')
    return "\n".join(out) + "\n"


# --------------------------------------------------------------------------
# The schema graph
# --------------------------------------------------------------------------


@dataclass
class FieldDef:
    name: str
    annotation: str
    required: bool
    description: Optional[str]
    constraints: Dict[str, Any] = field(default_factory=dict)
    markers: List[str] = field(default_factory=list)


@dataclass
class ModelDef:
    name: str
    doc: str
    fields: List[FieldDef]
    module: str
    deps: Set[str] = field(default_factory=set)


@dataclass
class AliasDef:
    """A module-level ``Name = <annotation>``: a named enum or a discriminated union."""

    name: str
    source: str
    module: str
    deps: Set[str] = field(default_factory=set)


@dataclass
class ToolDef:
    name: str
    request: str
    module: str
    method: str
    url: str
    description: str
    action_label: str
    paginated: bool
    body_format: Optional[str]
    scopes: Optional[List[List[str]]]
    reference: str


class Generator:
    def __init__(self, spec: Dict[str, Any], args: argparse.Namespace) -> None:
        self.spec = spec
        self.args = args
        self.components: Dict[str, Any] = (spec.get("components") or {}).get("schemas") or {}
        self.models: Dict[str, ModelDef] = {}
        self.aliases: Dict[str, AliasDef] = {}
        self.by_shape: Dict[str, str] = {}  # canonical schema -> class or alias name
        self.component_names: Dict[str, str] = {}  # component key -> class/alias name
        self.taken: Set[str] = set(_RESERVED_CLASS_NAMES)
        # A spec's component names mean those components to anyone reading its
        # docs, so an inline object never takes one, even if the component itself
        # is response-only and never generated.
        self.spec_names: Set[str] = {pascal(k) for k in self.components}
        self.own_name: Optional[str] = None  # the component being named, which may take its name
        self.tools: List[ToolDef] = []
        self.report: Dict[str, List[str]] = {}
        self.case = "snake"
        self.query_case = "snake"
        self.current_deps: Optional[Set[str]] = None

    # ----- reporting -----

    def note(self, section: str, line: str) -> None:
        entries = self.report.setdefault(section, [])
        if line not in entries:
            entries.append(line)

    # ----- refs -----

    def deref(self, node: Dict[str, Any], seen: Optional[Set[str]] = None) -> Dict[str, Any]:
        """Follow ``$ref`` until a concrete node; sibling keys override (3.1 semantics)."""
        seen = seen or set()
        while isinstance(node, dict) and "$ref" in node:
            ref = node["$ref"]
            if not ref.startswith("#/"):
                self.note("Not expressed", f"external $ref {ref!r} is not followed; typed Any")
                return {}
            if ref in seen:
                return {}
            seen.add(ref)
            target: Any = self.spec
            for part in ref[2:].split("/"):
                target = target[part.replace("~1", "/").replace("~0", "~")]
            siblings = {k: v for k, v in node.items() if k != "$ref"}
            node = {**target, **siblings} if siblings else target
        return node

    @staticmethod
    def component_key(node: Dict[str, Any]) -> Optional[str]:
        ref = node.get("$ref", "")
        prefix = "#/components/schemas/"
        if not ref.startswith(prefix) or "/" in ref[len(prefix) :]:
            return None
        return ref[len(prefix) :].replace("~1", "/").replace("~0", "~")

    # ----- casing -----

    def survey_case(self) -> None:
        body_names: List[str] = []
        query_names: List[str] = []

        def walk(node: Any, seen: Set[int]) -> None:
            if isinstance(node, dict):
                if id(node) in seen:
                    return
                seen.add(id(node))
                for key in node.get("properties") or {}:
                    body_names.append(key)
                for value in node.values():
                    walk(value, seen)
            elif isinstance(node, list):
                for item in node:
                    walk(item, seen)

        walk(self.components, set())
        for item in (self.spec.get("paths") or {}).values():
            for method, op in item.items():
                if method not in METHODS:
                    continue
                body = (op.get("requestBody") or {}).get("content") or {}
                walk(body, set())
                for param in op.get("parameters", []) + item.get("parameters", []):
                    param = self.deref(param)
                    if param.get("in") == "query":
                        query_names.append(param.get("name", ""))
        self.case = wire_case(body_names)
        self.query_case = wire_case(query_names) if query_names else "snake"

    # ----- names -----

    def claim(self, *candidates: str) -> str:
        for candidate in candidates:
            if candidate not in self.taken:
                self.taken.add(candidate)
                return candidate
        base = candidates[-1]
        n = 2
        while f"{base}{n}" in self.taken:
            n += 1
        self.taken.add(f"{base}{n}")
        return f"{base}{n}"

    # ----- types -----

    def annotation(
        self,
        node: Dict[str, Any],
        hint: str,
        parent: str,
        module: str,
        depth: int = 0,
    ) -> Tuple[str, bool, Dict[str, Any]]:
        """``(annotation, nullable, constraints)`` for one schema.

        Constraints are returned rather than applied when they belong to the
        node itself, so the caller can put them on the field's ``Field()``; a
        nested node gets them inline as ``Annotated[..., Field(...)]``.
        """
        if not isinstance(node, dict) or not node:
            return "Any", False, {}

        key = self.component_key(node)
        if key is not None:
            name = self.component(key)
            resolved = self.deref(node)
            nullable = any(bool(n.get("nullable")) or _type_has_null(n) for n in (node, resolved))
            return name, nullable, {}

        node = self.deref(node)

        nullable = bool(node.get("nullable"))
        types = node.get("type")
        if isinstance(types, list):
            if "null" in types:
                nullable = True
            types = [t for t in types if t != "null"]
            if len(types) == 1:
                types = types[0]
            elif not types:
                return "None", True, {}
        if types == "null":
            return "None", True, {}

        if "const" in node:
            return f"Literal[{_literal(node['const'])}]", nullable, {}
        if "enum" in node:
            values = [v for v in node["enum"] if v is not None]
            if len(values) < len(node["enum"]):
                nullable = True
            if not values:
                return "None", True, {}
            return self.enum(values, hint, parent), nullable, {}

        if "allOf" in node:
            members = node["allOf"]
            if len(members) == 1 and self.component_key(members[0]) is not None:
                siblings = {k: v for k, v in node.items() if k != "allOf"}
                return self.annotation({**siblings, **members[0]}, hint, parent, module, depth)
            merged = self.merge_all_of(node)
            if merged is not None:
                return self.annotation(merged, hint, parent, module, depth)
            self.note("Not expressed", f"{parent}.{hint}: allOf of non-objects, typed Any")
            return "Any", False, {}

        for combinator in ("oneOf", "anyOf"):
            if combinator in node:
                members = node[combinator]
                concrete = [m for m in members if not _is_null(self.deref(m))]
                if len(concrete) < len(members):
                    nullable = True
                if not concrete:
                    return "None", True, {}
                if len(concrete) == 1:
                    inner, inner_null, constraints = self.annotation(
                        concrete[0], hint, parent, module, depth
                    )
                    return inner, nullable or inner_null, constraints
                return self.union(node, concrete, hint, parent, module, depth), nullable, {}

        if isinstance(types, list):  # several non-null primitive types
            parts = [
                self.annotation({**node, "type": t}, hint, parent, module, depth + 1)[0]
                for t in types
            ]
            return f"Union[{', '.join(dict.fromkeys(parts))}]", nullable, {}

        if types == "array" or "items" in node:
            item_node = node.get("items") or {}
            item, item_null, item_constraints = self.annotation(
                item_node, singular(hint), parent, module, depth + 1
            )
            if item_constraints:
                item = f"Annotated[{item}, Field({_kwargs(item_constraints)})]"
            if item_null:
                item = f"Optional[{item}]"
            constraints = _constraints(node, "array")
            return f"List[{item}]", nullable, constraints

        if types == "object" or "properties" in node or "additionalProperties" in node:
            properties = node.get("properties") or {}
            if properties:
                return self.inline_model(node, hint, parent, module), nullable, {}
            extra = node.get("additionalProperties")
            if isinstance(extra, dict) and extra:
                value, value_null, value_constraints = self.annotation(
                    extra, singular(hint), parent, module, depth + 1
                )
                if value_constraints:
                    value = f"Annotated[{value}, Field({_kwargs(value_constraints)})]"
                if value_null:
                    value = f"Optional[{value}]"
                return f"Dict[str, {value}]", nullable, {}
            self.note(
                "Free-form objects (typed Dict[str, Any]; check the docs for a shape)",
                f"{parent}.{hint}",
            )
            return "Dict[str, Any]", nullable, {}

        if types == "string":
            if node.get("format") == "binary":
                self.note("Not expressed", f"{parent}.{hint}: binary upload, typed str")
            return "str", nullable, _constraints(node, "string")
        if types == "integer":
            return "int", nullable, _constraints(node, "number")
        if types == "number":
            return "float", nullable, _constraints(node, "number")
        if types == "boolean":
            return "bool", nullable, {}
        return "Any", nullable, {}

    def merge_all_of(self, node: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """``allOf`` of objects as one object; ``None`` if a member is not an object."""
        merged: Dict[str, Any] = {"type": "object", "properties": {}, "required": []}
        members = node["allOf"]
        for member in members:
            member = self.deref(member)
            if "allOf" in member:
                member = self.merge_all_of(member)
                if member is None:
                    return None
            if member.get("type") not in (None, "object") or any(
                k in member for k in ("oneOf", "anyOf", "enum", "const", "items")
            ):
                if len(members) == 1:
                    return {**member, **{k: v for k, v in node.items() if k != "allOf"}}
                return None
            merged["properties"].update(member.get("properties") or {})
            merged["required"] += [
                r for r in member.get("required", []) if r not in merged["required"]
            ]
            for key in ("description", "title", "additionalProperties"):
                if key in member and key not in merged:
                    merged[key] = member[key]
        outer = {k: v for k, v in node.items() if k != "allOf"}
        merged["properties"].update(outer.pop("properties", None) or {})
        merged["required"] += [r for r in outer.pop("required", []) if r not in merged["required"]]
        merged.update(outer)
        return merged

    def enum(self, values: List[Any], hint: str, parent: str) -> str:
        literal = f"Literal[{', '.join(_literal(v) for v in values)}]"
        if len(values) < 3:
            return literal
        shape = "enum:" + json.dumps(values)
        if shape in self.by_shape:
            name = self.by_shape[shape]
        else:
            name = self.claim(*self.candidates(hint, parent))
            self.by_shape[shape] = name
            self.aliases[name] = AliasDef(name, literal, "common")
        self.depend(name)
        return name

    def candidates(self, hint: str, parent: str) -> List[str]:
        """Names for something declared inline: its own, then qualified by its parent."""
        base = re.sub(r"Request$", "", pascal(parent))
        own = pascal(hint)
        qualified = own if own.startswith(base) else base + own
        names = [own, qualified]
        allowed = [n for n in names if n not in self.spec_names or n == self.own_name]
        return allowed or [qualified + "Inline"]

    def depend(self, name: str) -> None:
        if self.current_deps is not None:
            self.current_deps.add(name)

    def union(
        self,
        node: Dict[str, Any],
        members: List[Dict[str, Any]],
        hint: str,
        parent: str,
        module: str,
        depth: int,
    ) -> str:
        resolved = [self.deref(m) for m in members]
        resolved = [self.merge_all_of(m) or m if "allOf" in m else m for m in resolved]
        constants = [
            m.get("enum", [m.get("const")]) for m in resolved if "const" in m or "enum" in m
        ]
        if len(constants) == len(resolved):
            values = list(dict.fromkeys(v for group in constants for v in group if v is not None))
            return self.enum(values, hint, parent)
        tag = self.discriminator(node, resolved)
        if tag is None:
            parts = []
            labels = _labels(resolved)
            for i, (member, concrete) in enumerate(zip(members, resolved, strict=True)):
                label = labels[i] if labels else str(i + 1)
                if self.component_key(member) is None and concrete.get("properties"):
                    named = f"{hint}_{label}" if labels else hint
                    part = self.inline_model(
                        concrete,
                        named,
                        parent,
                        module,
                        preferred=None if labels else self.candidates(hint, parent)[-1],
                    )
                    part_null, constraints = False, {}
                else:
                    part, part_null, constraints = self.annotation(
                        member, hint, parent, module, depth + 1
                    )
                if constraints:
                    part = f"Annotated[{part}, Field({_kwargs(constraints)})]"
                parts.append(part)
            parts = list(dict.fromkeys(parts))
            # A constrained member beside the bare type it narrows adds nothing the
            # bare one does not already accept: `date-time | date` is a `str`.
            parts = [
                p
                for p in parts
                if not (
                    p.startswith("Annotated[") and p[len("Annotated[") :].split(",")[0] in parts
                )
            ]
            return parts[0] if len(parts) == 1 else f"Union[{', '.join(parts)}]"

        shape = "union:" + _canonical(node)
        if shape in self.by_shape:
            name = self.by_shape[shape]
            self.depend(name)
            return name
        name = self.claim(*self.candidates(hint, parent))
        self.by_shape[shape] = name
        variant_names = []
        outer = self.current_deps
        alias_deps: Set[str] = set()
        self.current_deps = alias_deps
        for member, concrete in zip(members, resolved, strict=True):
            value = (concrete.get("properties") or {}).get(tag, {})
            value = self.deref(value)
            label = value.get("const", (value.get("enum") or [""])[0])
            key = self.component_key(member)
            if key is not None:
                variant_names.append(self.component(key))
            else:
                variant_names.append(
                    self.inline_model(
                        concrete,
                        f"{hint}_{label}",
                        parent,
                        module,
                        preferred=name + pascal(str(label)),
                    )
                )
        self.current_deps = outer
        # A plain Union, not Field(discriminator=...): the LLM view accepts each
        # field under its camel, Pascal and snake spellings, and pydantic refuses
        # a discriminator over aliased fields. Every variant pins the tag to its
        # own Literal, so validation still selects exactly one.
        source = f"Union[{', '.join(variant_names)}]"
        self.aliases[name] = AliasDef(name, source, "common", alias_deps | set(variant_names))
        self.depend(name)
        return name

    def discriminator(self, node: Dict[str, Any], members: List[Dict[str, Any]]) -> Optional[str]:
        declared = (node.get("discriminator") or {}).get("propertyName")
        candidates = [declared] if declared else []
        if not candidates and members:
            first = members[0].get("properties") or {}
            candidates = list(first)
        for prop in candidates:
            values = []
            for member in members:
                if member.get("type") not in (None, "object") or "properties" not in member:
                    return None
                schema = self.deref((member.get("properties") or {}).get(prop, {}))
                if prop not in member.get("required", []):
                    break
                if "const" in schema:
                    values.append(schema["const"])
                elif len(schema.get("enum") or []) == 1:
                    values.append(schema["enum"][0])
                else:
                    break
            else:
                if len(set(map(str, values))) == len(values):
                    return prop
        return None

    def component(self, key: str) -> str:
        """The class or alias for ``#/components/schemas/<key>``, generated on first use."""
        if key in self.component_names:
            name = self.component_names[key]
            self.depend(name)
            return name
        node = self.components.get(key, {})
        name = self.claim(pascal(key), pascal(key) + "Model")
        self.component_names[key] = name
        resolved = node
        if "allOf" in node:
            resolved = self.merge_all_of(node) or node
        for combinator in ("anyOf", "oneOf"):
            concrete = [m for m in node.get(combinator, []) if not _is_null(self.deref(m))]
            if len(concrete) == 1 and len(node[combinator]) > 1:
                only = self.deref(concrete[0])
                if only.get("properties") and self.component_key(concrete[0]) is None:
                    resolved = {
                        **only,
                        "description": node.get("description") or only.get("description"),
                    }
        is_object = (resolved.get("properties") is not None) and not any(
            c in resolved for c in ("oneOf", "anyOf")
        )
        outer = self.current_deps
        if is_object:
            self.build_model(name, resolved, "common", key)
        else:
            # Not an object: an enum, a union or a primitive, named for the reader.
            # The name is released so an enum or a union built below takes it
            # as its own, rather than claiming a second one beside it.
            deps: Set[str] = set()
            self.current_deps = deps
            self.taken.discard(name)
            self.own_name = name
            source, nullable, constraints = self.annotation(
                {k: v for k, v in node.items()}, key, key, "common"
            )
            self.own_name = None
            if source == name:
                # A discriminated union already claimed this name as its alias.
                self.current_deps = outer
                self.depend(name)
                return name
            self.taken.add(name)
            if constraints:
                source = f"Annotated[{source}, Field({_kwargs(constraints)})]"
            if nullable:
                source = f"Optional[{source}]"
            self.aliases[name] = AliasDef(name, source, "common", deps)
        self.current_deps = outer
        self.depend(name)
        return name

    def inline_model(
        self,
        node: Dict[str, Any],
        hint: str,
        parent: str,
        module: str,
        preferred: Optional[str] = None,
    ) -> str:
        shape = "model:" + _canonical(node)
        if shape in self.by_shape:
            name = self.by_shape[shape]
            self.depend(name)
            return name
        candidates = [c for c in (preferred,) if c and c not in self.spec_names]
        name = self.claim(*candidates, *self.candidates(hint, parent))
        self.by_shape[shape] = name
        self.build_model(name, node, "common", None, origin=f"{parent}.{hint}")
        self.depend(name)
        return name

    def build_model(
        self,
        name: str,
        node: Dict[str, Any],
        module: str,
        component: Optional[str],
        origin: str = "",
    ) -> None:
        placeholder = ModelDef(name, "", [], module)
        self.models[name] = placeholder
        outer = self.current_deps
        deps: Set[str] = set()
        self.current_deps = deps
        required = set(node.get("required") or [])
        fields = []
        for wire, prop in (node.get("properties") or {}).items():
            fdef = self.field(wire, prop, wire in required, name, module, location=None)
            fields.append(_unique(fdef, fields, wire))
        self.current_deps = outer
        doc = (node.get("description") or node.get("title") or "").strip()
        if component:
            doc = doc or f"``{component}`` in the spec."
        placeholder.doc = doc or f"Declared inline in the spec: ``{origin}``."
        placeholder.fields = fields
        placeholder.deps = deps

    def field(
        self,
        wire: str,
        prop: Dict[str, Any],
        required: bool,
        parent: str,
        module: str,
        location: Optional[str],
        header: Optional[str] = None,
        description: Optional[str] = None,
    ) -> FieldDef:
        case = self.query_case if location == "Query" else self.case
        name, wire_name = python_name(wire, case)
        if location in ("Path", "Header"):
            wire_name = None  # the URL template and Header() carry those names
        resolved = self.deref(prop) if isinstance(prop, dict) else {}
        desc = description or _description(prop) or _description(resolved)
        annotation, nullable, constraints = self.annotation(prop, wire, parent, module)
        markers: List[str] = []
        deprecated = bool(prop.get("deprecated") or resolved.get("deprecated"))
        if prop.get("readOnly") or resolved.get("readOnly"):
            markers.append('Mode("response_only")')
            required = False
        if deprecated:
            markers.append('Mode("disabled")')
            required = False
            self.note('Deprecated (withheld with Mode("disabled"))', f"{parent}.{wire}")
        if resolved.get("format") == "byte" and annotation == "str":
            markers.append('Format("base64")')
            self.note('Base64 fields (Format("base64"): the model sends text)', f"{parent}.{wire}")
        if location:
            markers.append(f'Header("{header}")' if location == "Header" else f"{location}()")
        if wire_name:
            markers.append(f'WireName("{wire_name}")')
        # The spec's default, told to the model rather than sent: a Gloss, so the
        # description stays the spec's own words.
        default = prop.get("default", resolved.get("default"))
        if default is not None and not required and not (desc and "default" in desc.lower()):
            rendered = default if isinstance(default, str) else json.dumps(default)
            markers.append(call("Gloss", f"Defaults to `{rendered}` when omitted."))
        if nullable and desc and _NULL_HINT.search(desc) and not required:
            self.note(
                "Says to send null, which Charter never sends (unset fields are omitted)",
                f"{parent}.{wire}",
            )
        if nullable and required:
            self.note("Required but nullable (sent as required, never null)", f"{parent}.{wire}")
        if location and not (desc or "").strip() and "$ref" not in prop:
            self.note(
                "Undescribed parameters (the model fills these blind; add a Gloss)",
                f"{parent}.{wire}",
            )
        if desc and re.search(
            r"\bnot be (used|combined) with\b|can't be combined|"
            r"cannot be used with|mutually exclusive|only one of",
            desc,
            re.I,
        ):
            self.note(
                "Cross-field rules in prose (ConflictsWith or a validator)",
                f"{parent}.{wire}: {desc[:110]}",
            )
        if not required and annotation != "None":
            annotation = f"Optional[{annotation}]"
        return FieldDef(name, annotation, required, desc, constraints, markers)

    # ----- operations -----

    def operations(self) -> Iterable[Tuple[str, str, Dict[str, Any], Dict[str, Any]]]:
        for path, item in (self.spec.get("paths") or {}).items():
            for method, op in item.items():
                if method in _SKIPPED_METHODS:
                    self.note("Not expressed", f"{method.upper()} {path}: Charter has no {method}")
                if method in METHODS:
                    yield path, method, op, item

    def tool_name(self, path: str, method: str, op: Dict[str, Any]) -> str:
        if op.get("operationId") and not self.args.names_from_paths:
            return snake(op["operationId"])
        trimmed = re.sub(self.args.strip_prefix, "/", path)
        segments = [s for s in trimmed.split("/") if s and not s.startswith("{")]
        return snake("_".join(segments)) or "root"

    def build_tools(self) -> None:
        names: Dict[str, Tuple[str, str]] = {}
        planned = []
        for path, method, op, item in self.operations():
            name = self.tool_name(path, method, op)
            if name in names:
                other_path, other_method = names[name]
                name = (
                    f"{name}_{method}"
                    if other_method != method
                    else snake(f"{name}_{path.strip('/').split('/')[0]}")
                )
                self.note("Renamed to avoid a clash", f"{method.upper()} {path} -> {name}")
            if not re.match(r"[a-z_][a-z0-9_]*$", name) or keyword.iskeyword(name):
                name = f"op_{name}" if not name[0].isalpha() else f"{name}_"
            names[name] = (path, method)
            planned.append((name, path, method, op, item))

        for name, path, method, op, item in planned:
            self.build_tool(name, path, method, op, item)

    def build_tool(
        self, name: str, path: str, method: str, op: Dict[str, Any], item: Dict[str, Any]
    ) -> None:
        # Untagged, an operation is filed under its first segment past the version.
        trimmed = re.sub(self.args.strip_prefix, "/", path)
        segments = [p for p in trimmed.split("/") if p and not p.startswith("{")]
        tag = ((op.get("tags") or [None])[0]) or (segments[0] if segments else "operations")
        module = snake(tag)
        if module in ("common", "types"):
            module += "_ops"
        request = self.claim(pascal(name) + "Request")
        summary = (op.get("summary") or "").strip()
        description = (op.get("description") or "").strip()
        reference = self.reference(path, method)

        fields: List[FieldDef] = []
        deps: Set[str] = set()
        self.current_deps = deps
        params: Dict[Tuple[str, str], Dict[str, Any]] = {}
        for param in list(item.get("parameters", [])) + list(op.get("parameters", [])):
            param = self.deref(param)
            params[(param.get("in", ""), param.get("name", ""))] = param
        url = path
        for (where, wire), param in params.items():
            schema = param.get("schema") or {}
            if where == "cookie":
                self.note("Not expressed", f"{name}: cookie parameter {wire!r} is not sent")
                continue
            location = {"path": "Path", "query": "Query", "header": "Header"}.get(where)
            if location is None:
                continue
            if where == "header" and wire.lower() in ("authorization", "content-type", "accept"):
                continue
            if param.get("deprecated"):
                schema = {**schema, "deprecated": True}
            if where == "query" and (
                param.get("style") not in (None, "form") or param.get("explode") is False
            ):
                self.note(
                    "Query serialisation to check (style/explode)",
                    f"{name}.{wire}: style={param.get('style')} explode={param.get('explode')}",
                )
            if where == "query" and self.deref(schema).get("type") == "array":
                self.note(
                    "Array query parameters (check repeat vs bracket on the wire)", f"{name}.{wire}"
                )
            fdef = self.field(
                wire,
                schema,
                bool(param.get("required")) or where == "path",
                request,
                module,
                location,
                header=wire if where == "header" else None,
                description=param.get("description") or schema.get("description"),
            )
            fdef = _unique(fdef, fields, wire)
            if where == "path":
                url = url.replace("{" + wire + "}", "{" + fdef.name + "}")
            fields.append(fdef)

        body_format = None
        body = self.deref(op.get("requestBody") or {})
        content = body.get("content") or {}
        if content:
            media, media_def = _pick_media(content)
            if len(content) > 1:
                self.note(
                    "Several body media types (the first JSON/form one is declared)",
                    f"{name}: {', '.join(content)} -> {media}",
                )
            schema = media_def.get("schema") or {}
            if "form-urlencoded" in media:
                body_format = "form"
            elif "multipart" in media:
                self.note("Not expressed", f"{name}: multipart body declared as JSON fields")
            body_required = bool(body.get("required"))
            resolved = self.deref(schema)
            if "allOf" in resolved:
                resolved = self.merge_all_of(resolved) or resolved
            is_json = "json" in media or "form" in media
            if (
                is_json
                and resolved.get("properties")
                and not any(c in resolved for c in ("oneOf", "anyOf"))
            ):
                required = set(resolved.get("required") or [])
                if method == "patch" and required:
                    # A PATCH merges, so its body mandates nothing — the resource's
                    # required list is about creating it, not about changing it.
                    self.note(
                        "PATCH body fields made optional (a patch mandates nothing)",
                        f"{name}: {', '.join(sorted(required))}",
                    )
                    required = set()
                for wire, prop in resolved["properties"].items():
                    fdef = self.field(wire, prop, wire in required, request, module, "Body")
                    fields.append(_unique(fdef, fields, wire))
                # A lone Body() field whose value is a list or an object *becomes*
                # the body. These are named properties of an object, so the one
                # that stands alone keeps its key: {"emails": [...]}, not [...].
                lone = [f for f in fields if "Body()" in f.markers]
                if len(lone) == 1:
                    lone[0].markers[lone[0].markers.index("Body()")] = "Body(envelop=True)"
            elif is_json:
                hint = "body"
                annotation, nullable, constraints = self.annotation(
                    schema, hint, pascal(name), module
                )
                marker = "Body()"
                markers = [marker]
                fields.append(
                    FieldDef(
                        "body",
                        annotation if body_required else f"Optional[{annotation}]",
                        body_required,
                        body.get("description") or resolved.get("description"),
                        constraints,
                        markers,
                    )
                )
                described = body.get("description") or resolved.get("description")
                if not described:
                    self.note(
                        "Undescribed parameters (the model fills these blind; add a Gloss)",
                        f"{request}.body",
                    )
            else:
                fields.append(
                    FieldDef(
                        "body",
                        "str" if body_required else "Optional[str]",
                        body_required,
                        body.get("description") or resolved.get("description"),
                        {},
                        [f'Body(media_type="{media}")'],
                    )
                )
                self.note(
                    "Raw bodies (Body(media_type=...); check what the model should send)",
                    f"{name}: {media}",
                )
        self.current_deps = None

        doc_lines = [summary or name]
        if description and description != summary:
            doc_lines += ["", description]
        doc_lines += ["", f"API Reference: {reference}"]
        self.models[request] = ModelDef(request, "\n".join(doc_lines), fields, module, deps)

        paginated = self.paginates(op, fields)
        tool_description = description or summary or name
        if not description:
            self.note("Operations with only a summary to describe them", name)
        self.tools.append(
            ToolDef(
                name=name,
                request=request,
                module=module,
                method=method.upper(),
                url=url.lstrip("/"),
                description=tool_description,
                action_label=summary or name.replace("_", " ").capitalize(),
                paginated=paginated,
                body_format=body_format,
                scopes=self.scopes(op),
                reference=reference,
            )
        )

    def reference(self, path: str, method: str) -> str:
        template = self.args.reference_url
        if not template:
            return self.args.source
        slug = path.strip("/").replace("/", "-").replace("{", "").replace("}", "")
        return template.format(method=method, path=path, slug=slug)

    def paginates(self, op: Dict[str, Any], fields: List[FieldDef]) -> bool:
        if not self.args.cursor_param:
            return False
        if not any(f.name == snake(self.args.cursor_param) for f in fields):
            return False
        response = self.deref((op.get("responses") or {}).get("200") or {})
        content = response.get("content") or {}
        if not content:
            return False
        _, media_def = _pick_media(content)
        schema = self.deref(media_def.get("schema") or {})
        if "allOf" in schema:
            schema = self.merge_all_of(schema) or schema
        top = self.args.cursor_field.split(".")[0]
        return top in (schema.get("properties") or {})

    def scopes(self, op: Dict[str, Any]) -> Optional[List[List[str]]]:
        requirements = op.get("security", self.spec.get("security"))
        if not requirements:
            return None
        schemes = (self.spec.get("components") or {}).get("securitySchemes") or {}
        alternatives: List[List[str]] = []
        for requirement in requirements:
            for scheme_name, scope_list in requirement.items():
                if (schemes.get(scheme_name) or {}).get("type") in ("oauth2", "openIdConnect"):
                    alternatives.append(list(scope_list))
        return alternatives or None


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------


def _is_null(node: Dict[str, Any]) -> bool:
    return node.get("type") == "null" or node.get("enum") == [None]


def _type_has_null(node: Dict[str, Any]) -> bool:
    types = node.get("type")
    return isinstance(types, list) and "null" in types


def _description(node: Any) -> Optional[str]:
    """A node's description, or its lone non-null member's (``anyOf: [X, null]``)."""
    if not isinstance(node, dict):
        return None
    if node.get("description"):
        return node["description"]
    for combinator in ("anyOf", "oneOf"):
        concrete = [m for m in node.get(combinator, []) if not _is_null(m)]
        texts = [_description(m) for m in concrete]
        # Every member described, and none of them objects (whose descriptions
        # are their own classes' docstrings): the members' texts, one per line.
        if concrete and all(texts) and not any(m.get("properties") for m in concrete):
            return "\n".join(dict.fromkeys(t for t in texts if t))
    return None


def _unique(fdef: FieldDef, fields: List[FieldDef], wire: str) -> FieldDef:
    """Two wire names that snake to one field name: the second keeps its spelling."""
    taken = {f.name for f in fields}
    if fdef.name not in taken:
        return fdef
    n = 2
    while f"{fdef.name}_{n}" in taken:
        n += 1
    fdef.name = f"{fdef.name}_{n}"
    if not any(m.startswith("WireName(") for m in fdef.markers):
        fdef.markers.append(f'WireName("{wire}")')
    return fdef


def _labels(members: List[Dict[str, Any]]) -> Optional[List[str]]:
    """A name for each member of an undiscriminated union, from a constant it carries.

    The first property every member pins to a constant; two members pinned to
    the same value are numbered. ``None`` when no property does.
    """
    first = members[0].get("properties") or {}
    for prop in first:
        labels = []
        for member in members:
            schema = (member.get("properties") or {}).get(prop) or {}
            options = schema.get("anyOf") or schema.get("oneOf") or [schema]
            pinned = [o.get("const", (o.get("enum") or [None])[0]) for o in options]
            value = pinned[0] if all(v is not None for v in pinned) else None
            if value is None:
                break
            labels.append(str(value))
        else:
            seen: Dict[str, int] = {}
            out = []
            for label in labels:
                seen[label] = seen.get(label, 0) + 1
                out.append(label if seen[label] == 1 else f"{label}_{seen[label]}")
            return out
    return None


def _literal(value: Any) -> str:
    if isinstance(value, bool):
        return "True" if value else "False"
    if isinstance(value, (int, float)):
        return repr(value)
    return json.dumps(str(value), ensure_ascii=False)


def _canonical(node: Any) -> str:
    return json.dumps(node, sort_keys=True, ensure_ascii=False)


def _constraints(node: Dict[str, Any], kind: str) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    if kind == "string":
        if "minLength" in node:
            out["min_length"] = node["minLength"]
        if "maxLength" in node:
            out["max_length"] = node["maxLength"]
        if "pattern" in node:
            out["pattern"] = node["pattern"]
    elif kind == "array":
        if "minItems" in node:
            out["min_length"] = node["minItems"]
        if "maxItems" in node:
            out["max_length"] = node["maxItems"]
    elif kind == "number":
        for spec_key, py_key in (("minimum", "ge"), ("maximum", "le")):
            if spec_key in node and not isinstance(node[spec_key], bool):
                out[py_key] = node[spec_key]
        # 3.0 spells an exclusive bound as a boolean beside minimum/maximum.
        if node.get("exclusiveMinimum") is True and "ge" in out:
            out["gt"] = out.pop("ge")
        elif isinstance(node.get("exclusiveMinimum"), (int, float)) and not isinstance(
            node.get("exclusiveMinimum"), bool
        ):
            out["gt"] = node["exclusiveMinimum"]
        if node.get("exclusiveMaximum") is True and "le" in out:
            out["lt"] = out.pop("le")
        elif isinstance(node.get("exclusiveMaximum"), (int, float)) and not isinstance(
            node.get("exclusiveMaximum"), bool
        ):
            out["lt"] = node["exclusiveMaximum"]
    return out


def _kwargs(constraints: Dict[str, Any]) -> str:
    parts = []
    for key, value in constraints.items():
        if key == "pattern":
            parts.append(f"pattern={_raw(value)}")
        else:
            parts.append(f"{key}={value!r}")
    return ", ".join(parts)


def _raw(pattern: str) -> str:
    if '"' not in pattern and not pattern.endswith("\\"):
        return f'r"{pattern}"'
    return json.dumps(pattern)


def _pick_media(content: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
    for preferred in ("application/json", "json", "form-urlencoded", "multipart"):
        for media, media_def in content.items():
            if preferred in media:
                return media, media_def or {}
    media = next(iter(content))
    return media, content[media] or {}


# --------------------------------------------------------------------------
# Rendering
# --------------------------------------------------------------------------

HEADER = "# SPDX-FileCopyrightText: 2026 R28 AI, Inc.\n# SPDX-License-Identifier: Apache-2.0\n"


def render_field(f: FieldDef) -> str:
    default = "..." if f.required else "None"
    kwargs = [default]
    if f.constraints:
        kwargs.append(_kwargs(f.constraints))
    if f.description:
        kwargs.append(f"description={py_str(f.description, indent=12)}")
    field_call = f"Field({', '.join(kwargs)})"
    parts = [f.annotation, field_call] + f.markers
    inner = ",\n".join("        " + p for p in parts)
    return f"    {f.name}: Annotated[\n{inner},\n    ]\n"


def render_model(model: ModelDef) -> str:
    out = f"\n\nclass {model.name}(PackModel):\n"
    out += docstring(model.doc)
    if model.fields:
        out += "\n" + "".join(render_field(f) for f in model.fields)
    return out


def _used(text: str, names: Iterable[str]) -> List[str]:
    return [n for n in names if re.search(rf"\b{re.escape(n)}\b", text)]


def _imports(text: str, local: Set[str]) -> str:
    typing_names = [
        n
        for n in ("Annotated", "Any", "Dict", "List", "Literal", "Optional", "Union")
        if re.search(rf"\b{n}\[|\b{n}\b(?=[,\]])", text)
    ]
    marker_names = [
        n
        for n in (
            "Body",
            "ConflictsWith",
            "Format",
            "Gloss",
            "Header",
            "Mode",
            "Path",
            "Query",
            "WireName",
        )
        if re.search(rf"\b{n}\(", text)
    ]
    lines = ["from __future__ import annotations", ""]
    if typing_names:
        lines.append(f"from typing import {', '.join(typing_names)}")
        lines.append("")
    lines.append("from pydantic import Field")
    lines.append("")
    if marker_names:
        lines.append(f"from charter.types import {', '.join(marker_names)}")
    lines.append(
        "from charter.types.model import PackModel"
        + (", resolve_forward_refs" if "resolve_forward_refs(" in text else "")
    )
    return "\n".join(lines) + "\n"


def order(models: Dict[str, ModelDef], aliases: Dict[str, AliasDef]) -> List[str]:
    """Dependencies first; cycles broken in declaration order."""
    deps = {n: set(m.deps) for n, m in models.items()}
    deps.update({n: set(a.deps) for n, a in aliases.items()})
    done: List[str] = []
    state: Dict[str, int] = {}

    def visit(name: str) -> None:
        if state.get(name) == 2 or name not in deps:
            return
        if state.get(name) == 1:
            return
        state[name] = 1
        for dep in sorted(deps[name]):
            if dep != name:
                visit(dep)
        state[name] = 2
        done.append(name)

    for name in deps:
        visit(name)
    return done


def write_pack(gen: Generator, out: Path, args: argparse.Namespace) -> List[Path]:
    written: List[Path] = []
    types_dir = out / "types"
    types_dir.mkdir(parents=True, exist_ok=True)

    common_models = {n: m for n, m in gen.models.items() if m.module == "common"}
    request_models = {n: m for n, m in gen.models.items() if m.module != "common"}
    sequence = order(common_models, gen.aliases)

    body = ""
    defined: Set[str] = set()
    forward: List[str] = []
    for name in sequence:
        if name in gen.aliases:
            alias = gen.aliases[name]
            source = alias.source
            # An alias is evaluated when the module runs, so a class it names that
            # is not defined yet (a recursive union) has to be a string.
            for dep in alias.deps - defined - {name}:
                source = re.sub(rf'(?<!["\w]){re.escape(dep)}(?![\w"])', f'"{dep}"', source)
            body += f"\n\n{name} = {source}\n"
        else:
            model = common_models[name]
            if any(d not in defined and d != name for d in model.deps) or name in model.deps:
                forward.append(name)
            body += render_model(model)
        defined.add(name)
    if forward:
        body += "\n\nresolve_forward_refs(" + ", ".join(forward) + ")\n"

    source_line = f"Drafted from {args.source} by scripts/openapi_to_pack.py."
    common_doc = (
        f'"""\nModels shared by the {args.pack} requests: the spec\'s component schemas and the\n'
        f'objects it declares inline, one class per shape.\n\n{source_line}\n"""\n'
    )
    exported = [n for n in sequence]
    common_text = HEADER + "\n" + common_doc + "\n" + _imports(body, set())
    common_text += "\n__all__ = [\n" + "".join(f'    "{n}",\n' for n in exported) + "]\n" + body
    (types_dir / "common.py").write_text(common_text)
    written.append(types_dir / "common.py")

    modules: Dict[str, List[ModelDef]] = {}
    for model in request_models.values():
        modules.setdefault(model.module, []).append(model)
    for module, models in modules.items():
        body = "".join(render_model(m) for m in models)
        shared = sorted(set().union(*(m.deps for m in models)) & set(sequence))
        shared = [n for n in shared if re.search(rf"\b{re.escape(n)}\b", body)]
        text = (
            HEADER
            + "\n"
            + (
                f'"""\nRequest schemas for the {args.pack} {module.replace("_", " ")} operations.\n\n'
                f'{source_line}\n"""\n\n'
            )
            + _imports(body, set())
        )
        if shared:
            text += (
                f"\nfrom charter.packs.{args.pack}.types.common import "
                + (
                    ", ".join(shared)
                    if len(shared) < 4
                    else "(\n" + "".join(f"    {n},\n" for n in shared) + ")"
                )
                + "\n"
            )
        text += "\n__all__ = [\n" + "".join(f'    "{m.name}",\n' for m in models) + "]\n" + body
        (types_dir / f"{module}.py").write_text(text)
        written.append(types_dir / f"{module}.py")

    init = HEADER + "\n" + f'"""Request schemas and shared models for the {args.pack} pack."""\n\n'
    init += "from .common import *\n"
    for module in sorted(modules):
        init += f"from .{module} import *\n"
    (types_dir / "__init__.py").write_text(init)
    written.append(types_dir / "__init__.py")

    (out / "__init__.py").write_text(render_init(gen, args))
    written.append(out / "__init__.py")
    return written


def _draft_docstring(
    gen: Generator, args: argparse.Namespace, title: str, env_var: str
) -> List[str]:
    """The pack docstring before review: an example the conformance suite can check."""
    example_tool = next((t for t in gen.tools if t.method == "GET"), gen.tools[0])
    example_args = ", ".join(
        f"{f.name}=..." for f in gen.models[example_tool.request].fields if f.required
    )
    return [
        f"{title} — {len(gen.tools)} tools, generated from the provider's OpenAPI document.",
        "",
        f"    from charter.packs import {args.pack}",
        "",
        f'    {args.pack}.configure(api_key="...")',
        f"    result = await {args.pack}.{example_tool.name}.ainvoke({example_args})",
        "",
        f"``configure()`` is optional if ``${env_var}`` is set.",
        "",
        f"Source: {args.source}",
        "",
        "DRAFT: written by scripts/openapi_to_pack.py and not yet reviewed. Replace this",
        "docstring with what the review found about the API.",
        '"""',
    ]


def render_init(gen: Generator, args: argparse.Namespace) -> str:
    spec = gen.spec
    info = spec.get("info") or {}
    title = info.get("title") or args.pack
    servers = spec.get("servers") or [{"url": ""}]
    base_url = servers[0].get("url", "").rstrip("/") + "/"
    if not base_url.startswith("http"):
        gen.note("Review", f"servers[0].url is {base_url!r}; set BASE_URL by hand")
    schemes = (spec.get("components") or {}).get("securitySchemes") or {}
    token_header = None
    for scheme in schemes.values():
        kind = scheme.get("type")
        if kind == "apiKey" and scheme.get("in") == "header":
            token_header = scheme.get("name")
        elif kind == "apiKey":
            gen.note(
                "Not expressed",
                f"API key sent in {scheme.get('in')!r}; Charter sends credentials in a header",
            )
        elif kind == "http" and scheme.get("scheme", "").lower() == "basic":
            gen.note("Not expressed", "HTTP basic auth; Charter sends a bearer or a named header")
    env_var = args.env_var or f"{args.pack.upper()}_API_KEY"

    paginated = [t for t in gen.tools if t.paginated]

    lines = [HEADER.rstrip("\n"), '"""']
    lines += _draft_docstring(gen, args, title, env_var)
    lines.append("")
    lines.append("from __future__ import annotations")
    lines.append("")
    lines.append("from typing import Optional")
    lines.append("")
    auth_imports = ["CredentialProvider"]
    if any(t.scopes for t in gen.tools):
        auth_imports.append("AnyOf")
    lines.append(f"from charter.auth import {', '.join(sorted(auth_imports))}")
    lines.append("from charter.factories import oauth_tool_factory")
    lines.append(
        "from charter.packs._config import DeferredCredentialProvider, configure_key_or_provider"
    )
    requests = sorted(t.request for t in gen.tools)
    lines.append(f"from charter.packs.{args.pack}.types import (")
    lines += [f"    {r}," for r in requests]
    lines.append(")")
    lines.append("from charter.tool import Tool")
    if paginated:
        lines.append("from charter.types.pagination import Pagination")
    lines.append("")
    lines.append(f'BASE_URL = "{base_url}"')
    lines.append("")
    if paginated:
        more = f', more_field="{args.more_field}"' if args.more_field else ""
        lines.append(f"{args.pack.upper()}_PAGINATION = Pagination(")
        lines.append(f'    cursor_field="{args.cursor_field}",')
        lines.append(f'    cursor_param="{snake(args.cursor_param)}"{more},')
        lines.append(")")
        lines.append("")
    lines.append(f'_credentials = DeferredCredentialProvider("{args.pack}", env_var="{env_var}")')
    lines.append("")
    lines.append("")
    lines.append("def configure(")
    lines.append("    api_key: Optional[str] = None,")
    lines.append("    *,")
    lines.append("    credential_provider: Optional[CredentialProvider] = None,")
    lines.append(") -> None:")
    lines.append(
        f'    """Supply the {title} credential for this pack\'s tools, or a provider of one '
        'per call."""'
    )
    lines.append("    configure_key_or_provider(_credentials, api_key, credential_provider)")
    lines.append("")
    lines.append("")
    factory = f"_{args.pack}"
    lines.append(f"{factory} = oauth_tool_factory(")
    lines.append(f'    pack="{args.pack}",')
    lines.append("    base_url=BASE_URL,")
    lines.append(f'    provider="{args.pack}",')
    lines.append("    credential_provider=_credentials,")
    lines.append(f'    body_case="{gen.case}",')
    lines.append(f'    query_case="{gen.query_case}",')
    lines.append('    path_case="snake",')
    if token_header:
        lines.append(f'    token_header="{token_header}",')
    lines.append(")")

    for tool in gen.tools:
        lines.append("")
        lines.append(f"{tool.name} = {factory}(")
        lines.append(f'    name="{tool.name}",')
        lines.append(f"    args_schema={tool.request},")
        lines.append(f'    method="{tool.method}",')
        lines.append(f'    url_template="{tool.url}",')
        lines.append(f"    description={py_str(tool.description, indent=4)},")
        lines.append(f"    action_label={py_str(tool.action_label, indent=4)},")
        if tool.paginated:
            lines.append(f"    pagination_override={args.pack.upper()}_PAGINATION,")
        if tool.body_format:
            lines.append(f'    body_format_override="{tool.body_format}",')
        if tool.scopes:
            if len(tool.scopes) == 1:
                rendered = json.dumps(tool.scopes[0])
            elif all(len(s) == 1 for s in tool.scopes):
                rendered = "[AnyOf(" + ", ".join(json.dumps(s[0]) for s in tool.scopes) + ")]"
            else:
                rendered = json.dumps(tool.scopes[0])
                gen.note("Scopes to settle by hand", f"{tool.name}: alternatives {tool.scopes}")
            lines.append(f"    scopes_override={rendered},")
        lines.append(")")
    lines.append("")
    lines.append("TOOLS: list[Tool] = [")
    lines += [f"    {t.name}," for t in gen.tools]
    lines.append("]")
    lines.append("")
    lines.append("__all__ = [")
    names = ["TOOLS", "configure", "BASE_URL"]
    if paginated:
        names.append(f"{args.pack.upper()}_PAGINATION")
    names += [t.name for t in gen.tools]
    lines += [f'    "{n}",' for n in names]
    lines.append("]")
    return "\n".join(lines) + "\n"


def format_output(paths: List[Path]) -> None:
    """``ruff format`` and import sorting, so the draft reads like the code beside it."""
    import subprocess

    names = [str(p) for p in paths]
    for command in (
        [sys.executable, "-m", "ruff", "check", "--quiet", "--fix", "--select", "I,F401", *names],
        [sys.executable, "-m", "ruff", "format", "--quiet", *names],
    ):
        try:
            subprocess.run(command, check=False, capture_output=True)
        except OSError:
            print("ruff is not installed: the output is valid but unformatted.", file=sys.stderr)
            return


def generate(args: argparse.Namespace, out: Path) -> Generator:
    spec = load_spec(args.source)
    if str(spec.get("swagger", "")).startswith("2"):
        spec = swagger2_to_openapi3(spec)
    elif not str(spec.get("openapi", "")).startswith("3"):
        sys.exit("Not an OpenAPI 3.x or Swagger 2.0 document.")
    gen = Generator(spec, args)
    gen.survey_case()
    gen.build_tools()
    if not gen.tools:
        sys.exit("The document declares no operations.")
    format_output(write_pack(gen, out, args))
    return gen


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    parser.add_argument("source", help="Path or URL of the OpenAPI document.")
    parser.add_argument("--pack", required=True, help="The pack's name, e.g. luma.")
    parser.add_argument("--out", help="Output directory (default src/charter/packs/<pack>).")
    parser.add_argument("--env-var", help="Credential variable (default <PACK>_API_KEY).")
    parser.add_argument(
        "--strip-prefix",
        default=r"^/v\d+(\.\d+)?/",
        help="Regex removed from a path before it becomes a tool name.",
    )
    parser.add_argument(
        "--names-from-paths",
        action="store_true",
        help="Name tools from paths even where an operationId exists.",
    )
    parser.add_argument("--cursor-param", help="The request field that takes a cursor.")
    parser.add_argument("--cursor-field", help="The response field that holds the next cursor.")
    parser.add_argument("--more-field", help="The response field that says another page exists.")
    parser.add_argument(
        "--reference-url", help="Per-operation docs URL, with {method}, {path} and {slug}."
    )
    parser.add_argument("--force", action="store_true", help="Overwrite an existing pack.")
    args = parser.parse_args(argv)
    if bool(args.cursor_param) != bool(args.cursor_field):
        parser.error("--cursor-param and --cursor-field go together")
    if not re.match(r"[a-z][a-z0-9]*$", args.pack):
        # A module name, and a tool-name prefix: `_` is what separates a pack from
        # its tools, so it cannot appear inside one.
        parser.error("--pack must be lowercase letters and digits, e.g. luma")

    out = Path(args.out or f"src/charter/packs/{args.pack}")
    # Once drafted, a pack is reviewed by editing it, so a second draft over the
    # top would erase the review. Draft into a scratch directory and diff instead.
    if (out / "__init__.py").exists() and not args.force:
        sys.exit(
            f"{out} already holds a pack. To see what the spec changed, draft into "
            "another directory with --out and diff; --force overwrites it."
        )

    gen = generate(args, out)
    print(
        f"Wrote {len(gen.tools)} tools and {len(gen.models) - len(gen.tools)} shared models "
        f"to {out}"
    )
    print(f"Casing: body_case={gen.case!r} query_case={gen.query_case!r}")
    print("\nFor review (the generator does not decide these):")
    for section, entries in gen.report.items():
        print(f"\n  {section} ({len(entries)}):")
        for entry in entries:
            print(f"    - {entry}")
    print(
        "\n  Always: does the API answer 200 on failure (Envelope)? Kinds of credential?"
        "\n  Make the review's changes in the pack itself, add it to PACK_NAMES,"
        "\n  and write its tests."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
