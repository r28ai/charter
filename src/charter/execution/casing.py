"""
Key-case conversion for the wire.

Schemas are written in snake_case; APIs rarely are. ``DictKeyParser`` converts
keys on the way out, honouring the cascade:

    Field ``Case()`` > Schema ``__case__`` > Endpoint override > Factory default

Only *keys* are converted — values are passed through untouched.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, Optional

from charter.types.errors import DeclarationError

__all__ = ["DictKeyParser"]

# Maps KeyCase values to converter functions (snake -> target).
# "snake" is identity (no conversion needed).
_CONVERTERS: Dict[str, Callable[[str], str]] = {}  # populated after class definition


class DictKeyParser:
    """Converts snake_case keys to camel/pascal/kebab, recursively."""

    @staticmethod
    def _snake2camel(snake_str: str) -> str:
        """Convert snake_case string to camelCase."""
        components = snake_str.split("_")
        return components[0] + "".join(x.capitalize() for x in components[1:])

    @staticmethod
    def _snake2pascal(snake_str: str) -> str:
        """Convert snake_case string to PascalCase."""
        return "".join(x.capitalize() for x in snake_str.split("_"))

    @staticmethod
    def _snake2kebab(snake_str: str) -> str:
        """Convert snake_case string to kebab-case."""
        return snake_str.replace("_", "-")

    @classmethod
    def convert_key(cls, key: str, case: str) -> str:
        """Convert a single snake_case key to the target case."""
        if case == "snake":
            return key
        converter = _CONVERTERS.get(case)
        if converter is None:
            raise DeclarationError(
            f"Unknown case: {case!r}", docs="tools/key-case-cascade"
        )
        return converter(key)

    @classmethod
    def convert_keys_recursive(
        cls,
        data: dict,
        case: str,
        *,
        field_cases: Optional[Dict[str, str]] = None,
        schema_case: Optional[str] = None,
        wire_names: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """Convert dictionary keys from snake_case to the target case.

        Supports per-field overrides via ``field_cases`` (field_name -> case) and
        schema-level overrides via ``schema_case``.

        Priority: ``wire_names[key]`` > ``field_cases[key]`` > ``schema_case`` >
        ``case`` (caller default). A wire name is not a convention, so it wins
        over all of them.

        Note that ``field_cases`` and ``schema_case`` apply at the top level only;
        nested dicts recurse with the plain ``case``. Field-level markers name a
        field on *this* schema, so they would be meaningless keyed against a
        nested object's field names.
        """
        if case == "snake" and not field_cases and not schema_case and not wire_names:
            return data

        effective_default = schema_case or case

        new_dict = {}
        for key, value in data.items():
            # Determine effective case for this key
            verbatim = (wire_names or {}).get(key)
            if verbatim is not None:
                new_key = verbatim
            else:
                effective_case = (field_cases or {}).get(key) or effective_default
                new_key = cls.convert_key(key, effective_case)
            if isinstance(value, dict):
                value = cls.convert_keys_recursive(value, case)
            elif isinstance(value, list):
                value = [
                    cls.convert_keys_recursive(item, case) if isinstance(item, dict) else item
                    for item in value
                ]
            new_dict[new_key] = value
        return new_dict


_CONVERTERS.update(
    {
        "camel": DictKeyParser._snake2camel,
        "pascal": DictKeyParser._snake2pascal,
        "kebab": DictKeyParser._snake2kebab,
    }
)
