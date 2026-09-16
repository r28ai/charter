"""
Factories: bind the per-API constants once, declare endpoints against them.

Every tool for one API shares a base URL, an auth method, and a casing
convention. A factory captures those, and returns a callable that turns a schema
plus a URL template into a :class:`~charter.tool.Tool`.

Two auth shapes are covered:

- :func:`api_key_tool_factory` — static header auth (``x-api-key``, a bearer
  token you already hold, whatever the API wants).
- :func:`oauth_tool_factory` — a bearer token fetched per call from a
  :class:`~charter.auth.CredentialProvider` you supply.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, Iterable, Optional, Sequence, Type

from pydantic import BaseModel

from charter.auth import CredentialProvider
from charter.execution.executor import ApiKeyHeaders, ResponseHandler
from charter.execution.http import BaseUrl, BodyFormat, HTTPMethod, QueryFormat
from charter.execution.schema import SchemaStore
from charter.observability import CallSink
from charter.tool import Tool
from charter.types.envelope import Envelope
from charter.types.errors import DeclarationError
from charter.types.markers import KeyCase, TransportOverride
from charter.types.pagination import Pagination

__all__ = ["api_key_tool_factory", "oauth_tool_factory"]

ToolBuilder = Callable[..., Tool]


def _validate_api_key_headers(headers: ApiKeyHeaders, where: str) -> None:
    """Fail at build time on an empty credential rather than on the first 401.

    A callable is resolved per request, so it cannot be checked here — the
    executor validates whatever it returns, on every call.
    """
    if callable(headers):
        return
    for key, value in headers.items():
        if not value:
            # No `docs`: the message already states the fix. The class says
            # when this was raised, which is a separate question from whether
            # there is a page worth sending anyone to.
            raise DeclarationError(
                f"API key header {key!r} has an empty value ({where}). "
                "Provide a valid credential or remove the header."
            )


def api_key_tool_factory(
    base_url: BaseUrl,
    api_key_headers: Optional[ApiKeyHeaders] = None,
    *,
    pack: Optional[str] = None,
    body_case: KeyCase = "camel",
    query_case: KeyCase = "snake",
    path_case: KeyCase = "snake",
    timeout: int = 20,
    quota_doc_url: Optional[str] = None,
    envelope: Optional[Envelope] = None,
    pagination: Optional[Pagination] = None,
    body_format: BodyFormat = "json",
    query_format: QueryFormat = "repeat",
    static_query: Optional[Dict[str, Any]] = None,
    static_headers: Optional[Dict[str, str]] = None,
    on_call: Optional[CallSink] = None,
    credential_statuses: Optional[Iterable[int]] = None,
    follow_redirects: bool = False,
) -> ToolBuilder:
    """Build tools for an API that authenticates with static headers.

    Works for anything header-based: ``x-api-key``, ``Authorization: Bearer ...``,
    several headers at once.

    Args:
        base_url: Base URL for the API, e.g. ``"https://api.example.com/"``.
        api_key_headers: Headers injected on every request. May be omitted here
            and supplied per tool via ``api_key_headers_override``.
        body_case: Case convention for body keys ("camel", "snake", "pascal", "kebab").
        query_case: Case convention for query keys.
        path_case: Case convention for path keys.
        timeout: Request timeout in seconds.
        quota_doc_url: Link to the API's own rate-limit documentation.
        envelope: How this API reports failure inside a 200 response. Declared
            once here, enforced on every tool the factory builds.
        pagination: Where this API keeps its cursor.
        body_format: ``"json"`` (default) or ``"form"`` for form-encoded APIs
            such as Stripe and Twilio.
        query_format: ``"repeat"`` (default) or ``"bracket"`` for APIs expecting
            ``expand[0]=x`` in the query string.
        static_query: Query parameters sent verbatim on every request.
        static_headers: Headers sent verbatim on every request — an Azure
            ``api-version``, a ``Notion-Version``.
        follow_redirects: Whether a 3xx is followed, for the whole factory.
            ``False`` by default: on a JSON API a redirect is usually a wrong
            URL, and following it quietly hides that. Set it per tool with
            ``follow_redirects_override`` on the endpoints whose answer *is* a
            redirect — GitHub serves Actions logs and artifacts as a 302 to a
            short-lived signed URL. The bearer token does not travel with it:
            httpx drops ``Authorization`` when a redirect leaves the origin.
        on_call: Receives a :class:`~charter.observability.ToolCall` after every
            invocation of every tool this factory builds — timings by stage,
            payload versus context size, and the outcome. Declared here because
            observability belongs to the deployment, not to one endpoint.

    Per-tool, ``static_body`` declares constant *body* keys for one endpoint —
    the GraphQL query document being the case that motivated it. It is per-tool
    rather than per-factory because the constant belongs to the operation, not
    the API.

    Returns:
        A callable that builds :class:`~charter.tool.Tool` instances with these defaults.

    Example::

        weather = api_key_tool_factory(
            base_url="https://api.openweathermap.org/",
            api_key_headers={"x-api-key": os.environ["OPENWEATHER_API_KEY"]},
        )

        get_current = weather(
            name="get_current_weather",
            args_schema=GetWeather,
            method="GET",
            url_template="data/2.5/weather/{city}",
            description="Get current weather for a city.",
        )
    """
    if api_key_headers:
        _validate_api_key_headers(api_key_headers, "factory")

    # One store per factory, shared by every tool it builds. Tools in a pack reach
    # the same types constantly - Linear's filters are referenced by most of its
    # 128 tools - and without this each tool rebuilds the whole graph for itself.
    #
    # A `SchemaStore` rather than a dict because the readers are threads. The view
    # is derived on first use, so whoever reaches a tool first builds it, and a
    # pack's tools are process-wide objects that several requests reach at once.
    _llm_cache = SchemaStore()

    def create_tool(
        name: str,
        args_schema: Type[BaseModel],
        method: HTTPMethod,
        url_template: str,
        description: Optional[str] = None,
        action_label: Optional[str] = None,
        body_case_override: Optional[KeyCase] = None,
        query_case_override: Optional[KeyCase] = None,
        path_case_override: Optional[KeyCase] = None,
        timeout_override: Optional[int] = None,
        mode: Optional[str] = None,
        response_handler: Optional[ResponseHandler] = None,
        api_key_headers_override: Optional[ApiKeyHeaders] = None,
        build_request: Optional[Callable[[BaseModel], TransportOverride]] = None,
        quota_cost: Optional[int] = None,
        envelope_override: Optional[Envelope] = None,
        pagination_override: Optional[Pagination] = None,
        body_format_override: Optional[BodyFormat] = None,
        static_body: Optional[Dict[str, Any]] = None,
        on_call_override: Optional[CallSink] = None,
        follow_redirects_override: Optional[bool] = None,
    ) -> Tool:
        """Build one API-key tool with the factory's defaults."""
        actual_headers = (
            api_key_headers_override if api_key_headers_override is not None else api_key_headers
        )

        if not actual_headers:
            raise DeclarationError(
                f"API key headers must be provided either on the factory or on the "
                f"create_tool call for tool {name!r}",
                docs="auth/api-key-tool-factory",
            )
        _validate_api_key_headers(actual_headers, f"tool {name!r}")

        return Tool(
            name=name,
            description=description or "",
            args_schema=args_schema,
            method=method,
            url_template=url_template,
            base_url=base_url,
            pack=pack,
            body_case=body_case_override if body_case_override is not None else body_case,
            query_case=query_case_override if query_case_override is not None else query_case,
            path_case=path_case_override if path_case_override is not None else path_case,
            timeout=timeout_override if timeout_override is not None else timeout,
            mode=mode,
            action_label=action_label,
            quota_cost=quota_cost,
            quota_doc_url=quota_doc_url,
            api_key_headers=actual_headers,
            build_request=build_request,
            response_handler=response_handler,
            envelope=envelope_override if envelope_override is not None else envelope,
            pagination=pagination_override if pagination_override is not None else pagination,
            body_format=body_format_override if body_format_override is not None else body_format,
            query_format=query_format,
            static_query=static_query,
            static_headers=static_headers,
            static_body=static_body,
            on_call=on_call_override if on_call_override is not None else on_call,
            follow_redirects=(
                follow_redirects_override
                if follow_redirects_override is not None
                else follow_redirects
            ),
            credential_statuses=credential_statuses,
            llm_cache=_llm_cache,
        )

    return create_tool


def oauth_tool_factory(
    base_url: BaseUrl,
    provider: str,
    credential_provider: CredentialProvider,
    scopes: Optional[Sequence[str]] = None,
    *,
    pack: Optional[str] = None,
    body_case: KeyCase = "camel",
    query_case: KeyCase = "snake",
    path_case: KeyCase = "snake",
    timeout: int = 20,
    quota_doc_url: Optional[str] = None,
    envelope: Optional[Envelope] = None,
    pagination: Optional[Pagination] = None,
    body_format: BodyFormat = "json",
    query_format: QueryFormat = "repeat",
    static_query: Optional[Dict[str, Any]] = None,
    static_headers: Optional[Dict[str, str]] = None,
    on_call: Optional[CallSink] = None,
    expiry_leeway_seconds: int = 10,
    credential_statuses: Optional[Iterable[int]] = None,
    follow_redirects: bool = False,
) -> ToolBuilder:
    """Build tools for an API that authenticates with a bearer token.

    The token is fetched from ``credential_provider`` on every call, so a
    provider that refreshes is picked up without rebuilding the tools. Charter never
    runs the OAuth flow itself: if the token is missing, expired, or rejected,
    a :class:`~charter.types.errors.CredentialError` is raised for the host app.

    Args:
        base_url: Base URL for the API, e.g. ``"https://gmail.googleapis.com/"``.
        provider: Provider identifier passed to ``get_credentials``, e.g. ``"google"``.
        credential_provider: Supplies the bearer token.
        scopes: The scopes these tools need. Carried as metadata for consent
            screens and approval UIs; Charter does not request them itself.
        body_case: Case convention for body keys.
        query_case: Case convention for query keys.
        path_case: Case convention for path keys.
        timeout: Request timeout in seconds.
        on_call: Receives a :class:`~charter.observability.ToolCall` after every
            invocation of every tool this factory builds. The credential
            provider's own time is reported separately from the API's, so a slow
            vault does not read as a slow provider.
        expiry_leeway_seconds: How dead a token must be before the runtime
            refuses to send it. A guard against sending something already
            expired, not a refresh policy — see
            :class:`~charter.auth.OAuth2Client` for that.
        follow_redirects: Whether a 3xx is followed, for the whole factory.
            ``False`` by default: on a JSON API a redirect is usually a wrong
            URL, and following it quietly hides that. Set it per tool with
            ``follow_redirects_override`` on the endpoints whose answer *is* a
            redirect — GitHub serves Actions logs and artifacts as a 302 to a
            short-lived signed URL. The bearer token does not travel with it:
            httpx drops ``Authorization`` when a redirect leaves the origin.

    Returns:
        A callable that builds :class:`~charter.tool.Tool` instances with these defaults.

    Example::

        gmail = oauth_tool_factory(
            base_url="https://gmail.googleapis.com/",
            provider="google",
            credential_provider=StaticTokenProvider(access_token),
            scopes=["https://www.googleapis.com/auth/gmail.modify"],
        )

        send = gmail(
            name="messages_send",
            args_schema=MessagesSend,
            method="POST",
            url_template="gmail/v1/users/{user_id}/messages/send",
            action_label="Send an email",
        )
    """

    # One store per factory, shared by every tool it builds. Tools in a pack reach
    # the same types constantly - Linear's filters are referenced by most of its
    # 128 tools - and without this each tool rebuilds the whole graph for itself.
    #
    # A `SchemaStore` rather than a dict because the readers are threads. The view
    # is derived on first use, so whoever reaches a tool first builds it, and a
    # pack's tools are process-wide objects that several requests reach at once.
    _llm_cache = SchemaStore()

    def create_tool(
        name: str,
        args_schema: Type[BaseModel],
        method: HTTPMethod,
        url_template: str,
        description: Optional[str] = None,
        action_label: Optional[str] = None,
        body_case_override: Optional[KeyCase] = None,
        query_case_override: Optional[KeyCase] = None,
        path_case_override: Optional[KeyCase] = None,
        timeout_override: Optional[int] = None,
        mode: Optional[str] = None,
        response_handler: Optional[ResponseHandler] = None,
        build_request: Optional[Callable[[BaseModel], TransportOverride]] = None,
        scopes_override: Optional[Sequence[str]] = None,
        quota_cost: Optional[int] = None,
        envelope_override: Optional[Envelope] = None,
        pagination_override: Optional[Pagination] = None,
        body_format_override: Optional[BodyFormat] = None,
        static_body: Optional[Dict[str, Any]] = None,
        on_call_override: Optional[CallSink] = None,
        follow_redirects_override: Optional[bool] = None,
    ) -> Tool:
        """Build one OAuth tool with the factory's defaults."""
        return Tool(
            name=name,
            description=description or "",
            args_schema=args_schema,
            method=method,
            url_template=url_template,
            base_url=base_url,
            pack=pack,
            body_case=body_case_override if body_case_override is not None else body_case,
            query_case=query_case_override if query_case_override is not None else query_case,
            path_case=path_case_override if path_case_override is not None else path_case,
            timeout=timeout_override if timeout_override is not None else timeout,
            mode=mode,
            action_label=action_label,
            provider=provider,
            scopes=scopes_override if scopes_override is not None else scopes,
            quota_cost=quota_cost,
            quota_doc_url=quota_doc_url,
            credential_provider=credential_provider,
            build_request=build_request,
            response_handler=response_handler,
            envelope=envelope_override if envelope_override is not None else envelope,
            pagination=pagination_override if pagination_override is not None else pagination,
            body_format=body_format_override if body_format_override is not None else body_format,
            query_format=query_format,
            static_query=static_query,
            static_headers=static_headers,
            static_body=static_body,
            on_call=on_call_override if on_call_override is not None else on_call,
            follow_redirects=(
                follow_redirects_override
                if follow_redirects_override is not None
                else follow_redirects
            ),
            expiry_leeway_seconds=expiry_leeway_seconds,
            credential_statuses=credential_statuses,
            llm_cache=_llm_cache,
        )

    return create_tool
