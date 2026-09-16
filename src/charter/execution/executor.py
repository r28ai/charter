"""
The execution pipeline: transform → auth → call → handle.

``ToolExecutor`` is framework-free and holds no ambient state. Credentials
arrive through an injected :class:`~charter.auth.CredentialProvider`; there is
no permission store, no context variable, and no re-auth interrupt. An expired
or rejected token raises :class:`~charter.types.errors.CredentialError` and the host
application decides what to do about it.
"""

from __future__ import annotations

import inspect
import logging
from time import perf_counter
from typing import (
    Any,
    Awaitable,
    Callable,
    Dict,
    Iterable,
    Mapping,
    Optional,
    Type,
    Union,
    get_args,
    get_origin,
)

import httpx
from pydantic import BaseModel

from charter.auth import CredentialProvider
from charter.execution.http import (
    BaseUrl,
    BodyFormat,
    HTTPMethod,
    QueryFormat,
    call_api,
    unwraps_body,
)
from charter.observability import CallProbe
from charter.transforms import apply_transform
from charter.types.envelope import Envelope
from charter.types.errors import CredentialError, DeclarationError, TransformError
from charter.types.markers import Body, Format, KeyCase, Path, Query, TransportOverride

__all__ = ["ToolExecutor", "ResponseHandler", "ApiKeyHeaders"]

logger = logging.getLogger("charter")


# -----------------------------------------------------
# Response Handler Type
# -----------------------------------------------------

ApiKeyHeaders = Union[Dict[str, str], Callable[[], Dict[str, str]]]
"""Static auth headers, or a callable resolving them at request time.

The callable form is what lets a credential arrive after the tools are built —
and, unlike a check the tool author has to remember to add, it is applied by the
runtime on every call.
"""

ResponseHandler = Callable[[Any], Awaitable[Any]]
"""An async callable that trims or reshapes a raw API response.

This is the context-economy hook: an API that returns 40KB of envelope for one
useful string costs the model its window on every call. A handler runs after the
request and returns whatever the model should actually see.
"""


# -----------------------------------------------------
# Transform Helpers
# -----------------------------------------------------


def _dump_like_json(value: Any) -> Any:
    """Recursively dump BaseModel instances to dict, including in lists and dicts."""
    if isinstance(value, BaseModel):
        return value.model_dump(exclude_none=True, mode="json")
    elif isinstance(value, list):
        return [_dump_like_json(item) for item in value]
    elif isinstance(value, dict):
        return {k: _dump_like_json(v) for k, v in value.items()}
    return value


def _unwrap_optional(field_type: Any) -> Any:
    """``Optional[X]`` -> ``X``; anything else unchanged."""
    if get_origin(field_type) is Union:
        args = get_args(field_type)
        non_none = [a for a in args if a is not type(None)]
        if non_none:
            return non_none[0]
    return field_type


def _apply_nested_transforms(schema: Type[BaseModel], data: dict) -> bool:
    """Recursively apply ``Format`` transforms in-place on matching fields.

    Returns True if any transforms were applied at any depth.
    """
    any_transformed = False

    for field_name, field_info in schema.model_fields.items():
        if field_name not in data or data[field_name] is None:
            continue

        format_marker = None
        for metadata in field_info.metadata:
            if isinstance(metadata, Format):
                format_marker = metadata
                break

        if format_marker:
            original_value = data[field_name]
            try:
                transformed_value = apply_transform(format_marker.transform, original_value)
            except TransformError as exc:
                # Name the field: the registry only knows the transform.
                exc.field = exc.field or field_name
                raise
            if transformed_value != original_value:
                data[field_name] = transformed_value
                any_transformed = True
        else:
            field_type = _unwrap_optional(field_info.annotation)

            if isinstance(field_type, type) and issubclass(field_type, BaseModel):
                if isinstance(data[field_name], dict):
                    if _apply_nested_transforms(field_type, data[field_name]):
                        any_transformed = True

            elif get_origin(field_type) is list:
                list_args = get_args(field_type)
                if list_args:
                    item_type = list_args[0]
                    if isinstance(item_type, type) and issubclass(item_type, BaseModel):
                        if isinstance(data[field_name], list):
                            for item in data[field_name]:
                                if isinstance(item, dict):
                                    if _apply_nested_transforms(item_type, item):
                                        any_transformed = True

    return any_transformed


def _create_auto_transformer(
    original_schema: Type[BaseModel],
) -> Callable[[BaseModel], TransportOverride]:
    """Build a transformer from the ``Format`` markers in a schema.

    The returned function takes the LLM-provided input (semantic types),
    recursively applies every ``Format`` transform at any nesting depth, and
    returns a ``TransportOverride`` carrying only the transformed fields, each
    routed to its HTTP location.
    """

    def auto_transform(input_model: BaseModel) -> TransportOverride:
        data = input_model.model_dump(exclude_none=True, mode="json")
        transformed_fields: Dict[str, Any] = {}

        for field_name, field_info in original_schema.model_fields.items():
            if field_name not in data or data[field_name] is None:
                continue

            format_marker = None
            for metadata in field_info.metadata:
                if isinstance(metadata, Format):
                    format_marker = metadata
                    break

            if format_marker:
                original_value = data[field_name]
                try:
                    transformed_value = apply_transform(
                        format_marker.transform, original_value
                    )
                except TransformError as exc:
                    exc.field = exc.field or field_name
                    raise
                if transformed_value != original_value:
                    transformed_fields[field_name] = transformed_value
            else:
                field_type = _unwrap_optional(field_info.annotation)
                field_value = data[field_name]
                nested_transformed = False

                if isinstance(field_type, type) and issubclass(field_type, BaseModel):
                    if isinstance(field_value, dict):
                        if _apply_nested_transforms(field_type, field_value):
                            nested_transformed = True

                elif get_origin(field_type) is list:
                    list_args = get_args(field_type)
                    if list_args:
                        item_type = list_args[0]
                        if isinstance(item_type, type) and issubclass(item_type, BaseModel):
                            if isinstance(field_value, list):
                                for item in field_value:
                                    if isinstance(item, dict):
                                        if _apply_nested_transforms(item_type, item):
                                            nested_transformed = True

                if nested_transformed:
                    transformed_fields[field_name] = field_value

        if not transformed_fields:
            return {}

        # A single Body() field that unwraps *is* the body, so its transformed
        # value replaces the body outright — that is how `raw` becomes Gmail's
        # whole request. With several Body() fields, or with one whose value is a
        # scalar, the body is a mapping and replacing it with one field's value
        # silently drops the rest. `unwraps_body` is the one place that decides;
        # `call_api` asks it too, and the two have to agree or a transform changes
        # where every other field goes.
        declared_body_fields = sum(
            1
            for f in original_schema.model_fields.values()
            if not any(isinstance(m, (Path, Query)) for m in f.metadata)
        )

        # Route transformed fields to their HTTP locations
        result: TransportOverride = {}
        path_overrides: Dict[str, Any] = {}
        query_overrides: Dict[str, Any] = {}
        body_override = None

        for field_name, transformed_value in transformed_fields.items():
            field_info = original_schema.model_fields[field_name]

            location = None
            for metadata in field_info.metadata:
                if isinstance(metadata, (Path, Query, Body)):
                    location = metadata
                    break

            transformed_value = _dump_like_json(transformed_value)

            if isinstance(location, Path):
                path_overrides[field_name] = transformed_value
            elif isinstance(location, Query):
                query_overrides[field_name] = transformed_value
            elif isinstance(location, Body):
                if unwraps_body(declared_body_fields, location, transformed_value):
                    body_override = transformed_value
                else:
                    if body_override is None:
                        body_override = {}
                    if isinstance(body_override, dict):
                        body_override[field_name] = transformed_value
            else:
                body_override = transformed_value

        if path_overrides:
            result["path"] = path_overrides
        if query_overrides:
            result["query"] = query_overrides
        if body_override is not None:
            result["body"] = body_override

        return result

    return auto_transform


# -----------------------------------------------------
# ToolExecutor
# -----------------------------------------------------


class ToolExecutor:
    """Runs one endpoint: transform → auth → call_api → response_handler."""

    def __init__(
        self,
        *,
        method: HTTPMethod,
        url_template: str,
        base_url: BaseUrl,
        original_schema: Type[BaseModel],
        body_case: KeyCase = "camel",
        query_case: KeyCase = "snake",
        path_case: KeyCase = "snake",
        timeout: int = 20,
        credential_provider: Optional[CredentialProvider] = None,
        provider: str = "",
        api_key_headers: Optional[ApiKeyHeaders] = None,
        build_request: Optional[Callable[[BaseModel], TransportOverride]] = None,
        response_handler: Optional[ResponseHandler] = None,
        envelope: Optional[Envelope] = None,
        body_format: BodyFormat = "json",
        query_format: QueryFormat = "repeat",
        static_query: Optional[Dict[str, Any]] = None,
        static_headers: Optional[Dict[str, str]] = None,
        static_body: Optional[Dict[str, Any]] = None,
        expiry_leeway_seconds: int = 10,
        credential_statuses: Optional[Iterable[int]] = None,
        follow_redirects: bool = False,
    ) -> None:
        has_oauth = credential_provider is not None
        # A callable resolves later, so it counts as configured auth; a literal
        # mapping still has to be non-empty here.
        has_api_key = api_key_headers is not None and (
            callable(api_key_headers) or len(api_key_headers) > 0
        )

        if not has_oauth and not has_api_key:
            raise DeclarationError(
                "Must provide either a credential_provider (bearer auth) "
                "or api_key_headers (header auth)",
                docs="reference/factories",
            )

        if has_oauth and has_api_key:
            raise DeclarationError(
                "Cannot use both a credential_provider and api_key_headers. "
                "Choose one authentication method.",
                docs="reference/factories",
            )

        # The Literal types are written out rather than inferred. Assigning a
        # Literal-typed parameter to a bare attribute widens it to str, and
        # these go straight back into call_api, which declares the Literals.
        self._method: HTTPMethod = method
        self._url_template = url_template
        self._base_url = base_url
        self._original_schema = original_schema
        self._body_case: KeyCase = body_case
        self._query_case: KeyCase = query_case
        self._path_case: KeyCase = path_case
        self._timeout = timeout
        self._credential_provider = credential_provider
        self._provider = provider
        self._api_key_headers = api_key_headers
        self._envelope = envelope
        self._body_format: BodyFormat = body_format
        self._query_format: QueryFormat = query_format
        self._static_query = static_query
        self._static_headers = static_headers
        self._static_body = static_body
        self._expiry_leeway_seconds = expiry_leeway_seconds
        self._credential_statuses = credential_statuses
        self._follow_redirects = follow_redirects

        # Auto-generate build_request if not provided
        if build_request is None:
            self._build_request = _create_auto_transformer(original_schema)
        else:
            self._build_request = build_request

        # Validate response_handler is async if provided
        if response_handler is not None and not inspect.iscoroutinefunction(response_handler):
            handler_name = getattr(response_handler, "__name__", str(response_handler))
            raise DeclarationError(
                f"response_handler must be an async function (defined with 'async def'). "
                f"Got non-async function: '{handler_name}'",
                docs="reference/response-handling",
            )
        self._response_handler = response_handler

    async def execute(
        self,
        tool_input: BaseModel,
        *,
        tool_name: Optional[str] = None,
        headers: Optional[Mapping[str, str]] = None,
        client: Optional[httpx.AsyncClient] = None,
        probe: Optional[CallProbe] = None,
    ) -> Any:
        """Execute the tool against ``tool_input`` (already validated).

        ``headers`` are supplied by the host application for this one call — an
        idempotency key, a tenant selector — and never come from tool input.

        ``probe`` collects the per-stage timings. Each stage is timed separately
        because they have different owners: a slow credential provider and a slow
        API are the same number to a caller who only measured the total.
        """
        if logger.isEnabledFor(logging.DEBUG) and tool_name:
            logger.debug(
                "Tool call: %s",
                tool_name,
                extra={"charter_input": tool_input.model_dump(exclude_none=True, mode="json")},
            )

        # 1. Apply build_request (format transforms) → TransportOverride
        started = perf_counter()
        try:
            transport_override = self._build_request(tool_input) if self._build_request else None
        finally:
            if probe is not None:
                probe.transform_ms = (perf_counter() - started) * 1000

        # 2. Auth + call_api
        if self._api_key_headers:
            response = await self._execute_api_key(
                tool_input, transport_override, headers, client, probe
            )
        else:
            response = await self._execute_bearer(
                tool_input, transport_override, headers, client, probe
            )

        # 3. Apply response handler if provided. Failures — HTTP or envelope —
        # have already raised, so a handler only ever sees a successful payload.
        if self._response_handler:
            started = perf_counter()
            try:
                response = await self._response_handler(response)
            finally:
                if probe is not None:
                    probe.handler_ms = (perf_counter() - started) * 1000

        return response

    async def _execute_api_key(
        self,
        tool_input: BaseModel,
        transport_override: Optional[TransportOverride],
        request_headers: Optional[Mapping[str, str]],
        client: Optional[httpx.AsyncClient],
        probe: Optional[CallProbe] = None,
    ) -> Any:
        """API-key mode — inject headers, no bearer credentials."""
        assert self._api_key_headers is not None
        started = perf_counter()
        try:
            auth_headers = self._resolve_api_key_headers()
        finally:
            if probe is not None:
                probe.credential_ms = (perf_counter() - started) * 1000

        if transport_override and "headers" in transport_override:
            auth_headers.update(transport_override["headers"])

        if transport_override is None:
            transport_override = {}
        transport_override["headers"] = auth_headers

        return await call_api(
            method=self._method,
            url_template=self._url_template,
            tool_input=tool_input,
            credentials=None,
            base_url=self._base_url,
            body_case=self._body_case,
            query_case=self._query_case,
            path_case=self._path_case,
            timeout=self._timeout,
            transport_override=transport_override,
            provider=self._provider or None,
            envelope=self._envelope,
            request_headers=request_headers,
            body_format=self._body_format,
            query_format=self._query_format,
            static_query=self._static_query,
            static_headers=self._static_headers,
            static_body=self._static_body,
            client=client,
            probe=probe,
            credential_statuses=self._credential_statuses,
            follow_redirects=self._follow_redirects,
        )

    def _resolve_api_key_headers(self) -> Dict[str, str]:
        """Resolve auth headers for this request.

        A callable is invoked per call, so a pack configured after its tools were
        built is picked up, and an unconfigured one fails here — locally, before
        anything reaches the network.
        """
        source = self._api_key_headers
        if source is None:  # pragma: no cover - guarded in __init__
            raise CredentialError(
                "No API key headers are configured for this tool.",
                docs="auth/api-key-tool-factory",
            )
        resolved: Dict[str, str] = source() if callable(source) else source
        headers: Dict[str, str] = dict(resolved)

        if not headers:
            raise CredentialError(
                "No API key headers were resolved for this request.",
                provider=self._provider or None,
                docs="auth/api-key-tool-factory",
            )
        empty = [k for k, v in headers.items() if not v]
        if empty:
            raise CredentialError(
                f"API key header(s) {', '.join(sorted(empty))} resolved to an empty "
                "value; the credential is missing.",
                provider=self._provider or None,
                docs="auth/api-key-tool-factory",
            )
        return headers

    async def _execute_bearer(
        self,
        tool_input: BaseModel,
        transport_override: Optional[TransportOverride],
        request_headers: Optional[Mapping[str, str]],
        client: Optional[httpx.AsyncClient],
        probe: Optional[CallProbe] = None,
    ) -> Any:
        """Bearer mode — pull credentials from the provider, then call."""
        assert self._credential_provider is not None

        # The provider is the host's code and may go to a vault or a database,
        # so its time is recorded separately rather than folded into the request.
        started = perf_counter()
        try:
            credentials = await self._credential_provider.get_credentials(self._provider)
        finally:
            if probe is not None:
                probe.credential_ms = (perf_counter() - started) * 1000

        if credentials.is_expired(self._expiry_leeway_seconds):
            raise CredentialError(
                "Credentials have expired. Refresh them and retry.",
                provider=self._provider or None,
                docs="auth/oauth-flow",
            )

        return await call_api(
            method=self._method,
            url_template=self._url_template,
            tool_input=tool_input,
            credentials=credentials,
            base_url=self._base_url,
            body_case=self._body_case,
            query_case=self._query_case,
            path_case=self._path_case,
            timeout=self._timeout,
            transport_override=transport_override,
            provider=self._provider or None,
            envelope=self._envelope,
            request_headers=request_headers,
            body_format=self._body_format,
            query_format=self._query_format,
            static_query=self._static_query,
            static_headers=self._static_headers,
            static_body=self._static_body,
            client=client,
            probe=probe,
            credential_statuses=self._credential_statuses,
            follow_redirects=self._follow_redirects,
        )
