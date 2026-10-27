"""``scripts/openapi_to_pack.py`` — a pack transcribed from a spec, checked on the wire.

The Luma pack is one output of the generator; these tests are about the
generator, on small specs written to exercise one construct each, in the two
OpenAPI dialects it reads natively and the Swagger 2.0 one it converts. Each
generated pack is imported and called against ``respx``, because the claim is
not that the script writes Python but that the Python it writes sends what the
spec describes.

The generated packs are written to a temporary directory added to
``charter.packs.__path__``, so they import under their real module names (the
generated code imports itself absolutely) without touching the source tree.
"""

from __future__ import annotations

import base64
import copy
import importlib
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any, Dict, get_args

import httpx
import pydantic
import pytest
import respx

import charter.packs

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "openapi_to_pack.py"


def _load_script():
    spec = importlib.util.spec_from_file_location("openapi_to_pack", _SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["openapi_to_pack"] = module
    spec.loader.exec_module(module)
    return module


generator = _load_script()


@pytest.fixture
def packs_dir(tmp_path, monkeypatch):
    """A directory ``charter.packs`` also imports from, for the test's packs only."""
    root = tmp_path / "packs"
    root.mkdir()
    monkeypatch.setattr(charter.packs, "__path__", [*charter.packs.__path__, str(root)])
    yield root
    for name in [m for m in sys.modules if m.startswith("charter.packs.gen")]:
        del sys.modules[name]


def _generate(packs_dir: Path, pack: str, spec: Dict[str, Any], *extra: str) -> Any:
    source = packs_dir.parent / f"{pack}.json"
    source.write_text(json.dumps(spec))
    code = generator.main([str(source), "--pack", pack, "--out", str(packs_dir / pack), *extra])
    assert code == 0
    importlib.invalidate_caches()
    return importlib.import_module(f"charter.packs.{pack}")


# -----------------------------------------------------
# OpenAPI 3.0: camelCase, path and header parameters, recursion, OAuth
# -----------------------------------------------------

WIDGETS: Dict[str, Any] = {
    "openapi": "3.0.3",
    "info": {"title": "Widgets", "version": "1"},
    "servers": [{"url": "https://api.widgets.test/v2"}],
    "components": {
        "securitySchemes": {
            "oauth": {
                "type": "oauth2",
                "flows": {
                    "authorizationCode": {
                        "authorizationUrl": "https://widgets.test/authorize",
                        "tokenUrl": "https://widgets.test/token",
                        "scopes": {"widgets.read": "", "widgets.write": ""},
                    }
                },
            }
        },
        "schemas": {
            "Widget": {
                "type": "object",
                "description": "A widget.",
                "required": ["displayName"],
                "properties": {
                    "displayName": {"type": "string", "maxLength": 40, "description": "Shown."},
                    "htmlURL": {"type": "string", "description": "Where it lives."},
                    "from": {"type": "string", "description": "Origin."},
                    "kind": {
                        "type": "string",
                        "nullable": True,
                        "enum": ["round", "square", "oval", None],
                        "description": "Shape.",
                    },
                    "parent": {"$ref": "#/components/schemas/Widget"},
                    "id": {"type": "string", "readOnly": True, "description": "Server-set."},
                    "legacy": {"type": "boolean", "deprecated": True, "description": "Old."},
                    "payload": {"type": "string", "format": "byte", "description": "Bytes."},
                    "count": {
                        "type": "integer",
                        "minimum": 0,
                        "maximum": 10,
                        "default": 1,
                        "description": "How many.",
                    },
                },
            },
            "Shape": {
                "oneOf": [
                    {"$ref": "#/components/schemas/Circle"},
                    {"$ref": "#/components/schemas/Square"},
                ],
                "discriminator": {"propertyName": "shapeType"},
            },
            "Circle": {
                "type": "object",
                "required": ["shapeType", "radius"],
                "properties": {
                    "shapeType": {"type": "string", "enum": ["circle"]},
                    "radius": {"type": "number", "description": "Radius."},
                },
            },
            "Square": {
                "allOf": [
                    {"$ref": "#/components/schemas/Labelled"},
                    {
                        "type": "object",
                        "required": ["shapeType"],
                        "properties": {
                            "shapeType": {"type": "string", "enum": ["square"]},
                            "side": {"type": "number", "description": "Side."},
                        },
                    },
                ]
            },
            "Labelled": {
                "type": "object",
                "properties": {"label": {"type": "string", "description": "Label."}},
            },
        },
    },
    "paths": {
        "/widgets/{widgetId}": {
            "parameters": [
                {
                    "name": "widgetId",
                    "in": "path",
                    "required": True,
                    "schema": {"type": "string"},
                    "description": "The widget.",
                }
            ],
            "get": {
                "operationId": "getWidget",
                "summary": "Get a widget",
                "description": "Fetch one widget.",
                "security": [{"oauth": ["widgets.read"]}, {"oauth": ["widgets.write"]}],
                "parameters": [
                    {
                        "name": "X-Trace",
                        "in": "header",
                        "schema": {"type": "string"},
                        "description": "Trace id.",
                    },
                    {
                        "name": "pageSize",
                        "in": "query",
                        "schema": {"type": "integer"},
                        "description": "Page size.",
                    },
                ],
            },
            "patch": {
                "operationId": "updateWidget",
                "summary": "Update a widget",
                "description": "Change it.",
                "security": [{"oauth": ["widgets.write"]}],
                "requestBody": {
                    "content": {
                        "application/json": {"schema": {"$ref": "#/components/schemas/Widget"}}
                    }
                },
            },
        },
        "/shapes": {
            "post": {
                "operationId": "createShape",
                "summary": "Create a shape",
                "description": "Make one.",
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {"schema": {"$ref": "#/components/schemas/Shape"}}
                    },
                },
            }
        },
        "/tokens": {
            "post": {
                "operationId": "createToken",
                "summary": "Create a token",
                "description": "Form-encoded.",
                "requestBody": {
                    "content": {
                        "application/x-www-form-urlencoded": {
                            "schema": {
                                "type": "object",
                                "required": ["grantType", "scope"],
                                "properties": {
                                    "grantType": {"type": "string", "description": "Grant."},
                                    "scope": {"type": "string", "description": "Scope."},
                                },
                            }
                        }
                    }
                },
            }
        },
    },
}


@pytest.fixture
def widgets(packs_dir):
    pack = _generate(packs_dir, "genwidgets", WIDGETS)
    pack.configure(api_key="token-1")
    return pack


def test_operations_become_tools_named_after_their_operation_ids(widgets):
    assert [t.name for t in widgets.TOOLS] == [
        "get_widget",
        "update_widget",
        "create_shape",
        "create_token",
    ]
    assert widgets.get_widget.url_template == "widgets/{widget_id}"
    assert widgets.BASE_URL == "https://api.widgets.test/v2/"
    assert widgets.get_widget.body_case == "camel"


@respx.mock
async def test_a_path_a_header_and_a_query_parameter_land_where_the_spec_puts_them(widgets):
    route = respx.get(url__startswith="https://api.widgets.test/v2/widgets/w-1").mock(
        return_value=httpx.Response(200, json={})
    )
    await widgets.get_widget.ainvoke(widget_id="w-1", x_trace="t-9", page_size=5)
    request = route.calls[0].request
    assert request.url.path == "/v2/widgets/w-1"
    assert dict(request.url.params) == {"pageSize": "5"}
    assert request.headers["x-trace"] == "t-9"
    assert request.headers["authorization"] == "Bearer token-1"


@respx.mock
async def test_a_name_no_convention_reaches_keeps_its_spelling_on_the_wire(widgets):
    """`htmlURL` is not what camelCase makes of `html_url`, and `from` is a keyword."""
    route = respx.patch("https://api.widgets.test/v2/widgets/w-1").mock(
        return_value=httpx.Response(200, json={})
    )
    await widgets.update_widget.ainvoke(
        widget_id="w-1",
        display_name="Gear",
        html_url="https://widgets.test/w-1",
        from_="factory",
        payload="hello",
    )
    assert json.loads(route.calls[0].request.content) == {
        "displayName": "Gear",
        "htmlURL": "https://widgets.test/w-1",
        "from": "factory",
        "payload": base64.b64encode(b"hello").decode(),
    }


def test_a_patch_body_mandates_nothing_whatever_the_resource_requires(widgets):
    required = [
        name
        for name, field in widgets.update_widget.llm_schema().model_fields.items()
        if field.is_required()
    ]
    assert required == ["widget_id"]


def test_server_set_and_deprecated_fields_never_reach_the_model(widgets):
    fields = widgets.update_widget.llm_schema().model_fields
    assert "id" not in fields
    assert "legacy" not in fields
    assert "display_name" in fields


def test_a_default_is_told_to_the_model_and_never_sent(widgets):
    schema = json.dumps(widgets.update_widget.to_json_schema())
    assert "Defaults to `1` when omitted." in schema
    assert widgets.update_widget.args_schema.model_fields["count"].default is None


def test_constraints_and_every_enum_member_are_carried(widgets):
    from charter.packs.genwidgets.types import Kind

    assert set(get_args(Kind)) == {"round", "square", "oval"}
    llm = widgets.update_widget.llm_schema()
    with pytest.raises(pydantic.ValidationError):
        llm(widget_id="w-1", count=11)
    with pytest.raises(pydantic.ValidationError):
        llm(widget_id="w-1", display_name="x" * 41)


def test_a_recursive_model_resolves(widgets):
    llm = widgets.update_widget.llm_schema()
    llm(widget_id="w-1", parent={"displayName": "outer", "parent": {"displayName": "inner"}})


@respx.mock
async def test_a_tagged_union_body_sends_the_member_its_tag_names(widgets):
    """`Square` is an `allOf` of a base and its own fields; both reach the wire."""
    route = respx.post("https://api.widgets.test/v2/shapes").mock(
        return_value=httpx.Response(200, json={})
    )
    await widgets.create_shape.ainvoke(body={"shapeType": "square", "side": 2, "label": "a"})
    assert json.loads(route.calls[0].request.content) == {
        "shapeType": "square",
        "side": 2,
        "label": "a",
    }
    with pytest.raises(pydantic.ValidationError):
        widgets.create_shape.llm_schema()(body={"shapeType": "circle", "side": 2})


@respx.mock
async def test_a_form_body_is_form_encoded(widgets):
    route = respx.post("https://api.widgets.test/v2/tokens").mock(
        return_value=httpx.Response(200, json={})
    )
    await widgets.create_token.ainvoke(grant_type="client_credentials", scope="widgets.read")
    request = route.calls[0].request
    assert request.headers["content-type"].startswith("application/x-www-form-urlencoded")
    assert request.content == b"grantType=client_credentials&scope=widgets.read"


def test_oauth_scopes_come_from_each_operation(widgets):
    """Two security requirements of one scope each are alternatives: `AnyOf`."""
    from charter.auth import scopes_for

    source = Path(widgets.__file__).read_text()
    assert 'scopes_override=[AnyOf("widgets.read", "widgets.write")]' in source
    assert 'scopes_override=["widgets.write"]' in source
    assert set(scopes_for([widgets.update_widget])) == {"widgets.write"}


# -----------------------------------------------------
# Swagger 2.0, converted first
# -----------------------------------------------------

PETS: Dict[str, Any] = {
    "swagger": "2.0",
    "info": {"title": "Pets", "version": "1"},
    "host": "pets.test",
    "basePath": "/api",
    "schemes": ["https"],
    "securityDefinitions": {"key": {"type": "apiKey", "in": "header", "name": "X-Api-Key"}},
    "definitions": {
        "Pet": {
            "type": "object",
            "required": ["name"],
            "properties": {
                "name": {"type": "string", "description": "Name."},
                "tag": {"type": "string", "x-nullable": True, "description": "Tag."},
            },
        }
    },
    "paths": {
        "/pets": {
            "get": {
                "operationId": "listPets",
                "summary": "List pets",
                "parameters": [
                    {
                        "name": "limit",
                        "in": "query",
                        "type": "integer",
                        "maximum": 100,
                        "description": "At most this many.",
                    }
                ],
            },
            "post": {
                "operationId": "addPet",
                "summary": "Add a pet",
                "parameters": [
                    {
                        "name": "body",
                        "in": "body",
                        "required": True,
                        "schema": {"$ref": "#/definitions/Pet"},
                    }
                ],
            },
        }
    },
}


@respx.mock
async def test_swagger_2_reads_like_openapi_3(packs_dir):
    pets = _generate(packs_dir, "genpets", PETS)
    pets.configure(api_key="k-1")
    assert pets.BASE_URL == "https://pets.test/api/"

    listed = respx.get(url__startswith="https://pets.test/api/pets").mock(
        return_value=httpx.Response(200, json=[])
    )
    await pets.list_pets.ainvoke(limit=3)
    assert dict(listed.calls[0].request.url.params) == {"limit": "3"}
    assert listed.calls[0].request.headers["x-api-key"] == "k-1"
    with pytest.raises(pydantic.ValidationError):
        pets.list_pets.llm_schema()(limit=101)

    added = respx.post("https://pets.test/api/pets").mock(return_value=httpx.Response(200, json={}))
    await pets.add_pet.ainvoke(name="Rex")
    assert json.loads(added.calls[0].request.content) == {"name": "Rex"}


# -----------------------------------------------------
# OpenAPI 3.1, and drafting next to a pack that exists
# -----------------------------------------------------

NOTES: Dict[str, Any] = {
    "openapi": "3.1.0",
    "info": {"title": "Notes", "version": "1"},
    "servers": [{"url": "https://notes.test"}],
    "components": {
        "securitySchemes": {"key": {"type": "apiKey", "in": "header", "name": "x-notes-key"}}
    },
    "paths": {
        "/v1/notes/create": {
            "post": {
                "summary": "Create Note",
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {
                                "type": "object",
                                "required": ["title"],
                                "properties": {
                                    "title": {"type": "string"},
                                    "body": {"type": ["string", "null"], "description": "Text."},
                                    "pinned": {"type": "boolean", "description": "Pin it."},
                                    "archived": {
                                        "type": "boolean",
                                        "default": False,
                                        "description": "Archive it.",
                                    },
                                },
                            }
                        }
                    },
                },
            }
        },
        "/v1/notes/tags/add": {
            "post": {
                "summary": "Add Tags",
                "description": "Tag notes.",
                "requestBody": {
                    "content": {
                        "application/json": {
                            "schema": {
                                "type": "object",
                                "required": ["tags"],
                                "properties": {
                                    "tags": {
                                        "type": "array",
                                        "items": {"type": "string"},
                                        "description": "Tags.",
                                    }
                                },
                            }
                        }
                    }
                },
            }
        },
    },
}


@respx.mock
async def test_openapi_3_1_type_arrays_and_a_lone_array_keeps_its_key(packs_dir):
    notes = _generate(packs_dir, "gennotes", NOTES)
    notes.configure(api_key="n-1")

    fields = notes.notes_create.args_schema.model_fields
    assert not fields["body"].is_required()
    assert "Defaults to `false` when omitted." in json.dumps(notes.notes_create.to_json_schema())

    # One property that is an array would unwrap to a bare array; it must not.
    route = respx.post("https://notes.test/v1/notes/tags/add").mock(
        return_value=httpx.Response(200, json={})
    )
    await notes.notes_tags_add.ainvoke(tags=["a", "b"])
    assert json.loads(route.calls[0].request.content) == {"tags": ["a", "b"]}
    assert route.calls[0].request.headers["x-notes-key"] == "n-1"


def test_a_reviewed_pack_is_never_drafted_over(packs_dir):
    """The review edits the draft, so a second draft on top would erase it."""
    _generate(packs_dir, "gennotes", NOTES)
    source = packs_dir.parent / "gennotes.json"
    out = str(packs_dir / "gennotes")
    with pytest.raises(SystemExit, match="draft into another directory"):
        generator.main([str(source), "--pack", "gennotes", "--out", out])
    assert generator.main([str(source), "--pack", "gennotes", "--out", out, "--force"]) == 0


def test_drift_is_a_second_draft_beside_the_first(packs_dir, tmp_path):
    """What the vendor changed is what differs between two drafts of the spec."""
    _generate(packs_dir, "gennotes", NOTES)
    moved = copy.deepcopy(NOTES)
    create = moved["paths"]["/v1/notes/create"]["post"]
    props = create["requestBody"]["content"]["application/json"]["schema"]["properties"]
    props["color"] = {"type": "string", "enum": ["red", "blue"], "description": "Color."}
    source = tmp_path / "moved.json"
    source.write_text(json.dumps(moved))
    scratch = tmp_path / "scratch" / "gennotes"
    assert generator.main([str(source), "--pack", "gennotes", "--out", str(scratch)]) == 0

    before = (packs_dir / "gennotes" / "types" / "notes.py").read_text()
    after = (scratch / "types" / "notes.py").read_text()
    assert "color" not in before and "color" in after
