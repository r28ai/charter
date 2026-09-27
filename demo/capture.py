"""Phase 1 — run the demo beats for real, record exactly what came back.

Runs under the PROJECT venv (charter importable). Emits demo/transcript.json,
which demo/render.py turns into frames. Nothing here is simulated: every
output string is what the interpreter actually produced.
"""
import ast, asyncio, contextlib, inspect, io, json, os, pathlib, sys, traceback

BEATS = [
    # ---- declare the tool, then watch what it puts on the wire ----------
    ("# declare a tool once. no glue code, no vendor SDK", None),
    ("from typing import Annotated", None),
    ("from pydantic import BaseModel", None),
    ("from charter import Body, EmailContent, Format, Path, oauth_tool_factory", None),
    ("from charter.auth import EnvTokenProvider", None),
    ("", None),
    ("# input schema", None),
    ("class SendMessage(BaseModel):\n"
     "    user_id: Annotated[str, Path()] = 'me'\n"
     "    raw: Annotated[EmailContent, Body(envelop=True), Format('rfc822_base64')]", 1.4),
    ("", None),
    ("# api config", None),
    ("gmail = oauth_tool_factory(pack='mygmail', provider='google',\n"
     "    base_url='https://gmail.googleapis.com/',\n"
     "    credential_provider=EnvTokenProvider('GOOGLE_ACCESS_TOKEN'))", None),
    ("", None),
    ("# the tool", None),
    ("send = gmail(name='messages_send', method='POST',\n"
     "    url_template='gmail/v1/users/{user_id}/messages/send',\n"
     "    args_schema=SendMessage)", 1.2),
    ("__scroll__", None),

    ("# call the tool", None),
    ("await send.ainvoke({'raw': {'to': 'nqmug1@gmail.com',\n"
     "                           'subject': 'Sent by Charter',\n"
     "                           'body': 'Hello from a declared tool.'}})", 8.0),
    ("__clear__", None),

    # ---- see what a tool costs you before the model reads the task ------
    ("# finetune your agent's context", None),
    ("from charter import schema_tokens, format_path_costs, format_egress_map", None),
    ("from charter.packs import linear, gmail as gmail_pack", None),
    ("schema_tokens(linear.issues_list_full)", 0.3),
    ("__spotlight__ 45072 | one tool", 1.5),

    ("# audit the schema. what's eating it?", None),
    ("print(format_path_costs(\n"
     "    linear.issues_list_full.paths(under='variables', by_cost=True)))", 3.0),
    ("__scroll__", None),

    ("# keep only what your agent needs", None),
    ("F = 'variables.filter.'", None),
    ("triage = linear.issues_list_full.derived(name='issues_list_triage',\n"
     "    keep={F+'id', F+'number', F+'title', F+'priority', F+'state.type',\n"
     "          F+'assignee.email', F+'team.key', F+'labels.name'})", None),
    ("schema_tokens(triage)", 0.3),
    ("__spotlight__ 2267 | 20x smaller, same job", 1.9),
    ("__clear__", None),

    # ---- policy that lives on the declaration ---------------------------
    ("# define a policy the model can't touch", None),
    ("invoices = gmail_pack.messages_list.derived(name='search_invoices',\n"
     "    pin={'q': 'label:invoices'})", None),
    # the closing frame, so it holds longer than a mid-demo beat would
    ("print(format_egress_map([invoices]))", 4.0),
]


async def run(beats):
    import warnings; warnings.filterwarnings("ignore")
    g = {"__name__": "__main__"}
    out = []
    for src, hold in beats:
        if src.startswith(("__clear__", "__scroll__", "__spotlight__")):
            # markers carry their own dwell; do not flatten it
            out.append({"in": src, "out": "", "hold": hold or 0.3}); continue
        if not src.strip() or src.lstrip().startswith("#"):
            out.append({"in": src, "out": "", "hold": hold or 0.8}); continue
        buf = io.StringIO(); result = ""
        try:
            with contextlib.redirect_stdout(buf):
                flags = ast.PyCF_ALLOW_TOP_LEVEL_AWAIT
                try:
                    val = eval(compile(src, "<demo>", "eval", flags), g)
                    if inspect.isawaitable(val):
                        val = await val
                    if val is not None:
                        result = repr(val)
                except SyntaxError:
                    code = compile(src, "<demo>", "exec", flags)
                    val = eval(code, g)
                    if inspect.isawaitable(val):
                        await val
        except Exception:
            result = traceback.format_exc(limit=1).strip().splitlines()[-1]
        printed = buf.getvalue().rstrip("\n")
        text = "\n".join(x for x in (printed, result) if x)
        out.append({"in": src, "out": text, "hold": hold or 1.0})
    return out

def _decoded(value, max_lines=9):
    """A base64url wire body, read back as the document it encodes.

    The request really does carry base64; showing what it decodes to is how a
    pretty-printing logger handles an encoded payload, and it is the whole
    point of the beat — three fields in, an RFC 2822 document out.
    """
    if not isinstance(value, str) or len(value) < 40:
        return []
    try:
        from charter import decode_base64url
        text = decode_base64url(value)
    except Exception:
        return []
    if isinstance(text, bytes):
        text = text.decode("utf-8", "replace")
    if not text.isprintable() and "\n" not in text:
        return []
    # The MIME body carries its own Content-Transfer-Encoding, so the payload
    # is base64 inside the base64. Render it as the text it encodes; the
    # header above stays, so the frame still says how it was encoded.
    try:
        import email
        msg = email.message_from_string(text)
        if not msg.is_multipart():
            payload = msg.get_payload(decode=True)
            if payload:
                head = text.split("\n\n", 1)[0]
                text = head + "\n\n" + payload.decode("utf-8", "replace")
    except Exception:
        pass
    # Two lines that prove Charter built and encoded a document, then the
    # two the viewer just typed. MIME-Version is true and nobody cares.
    keep = ("Content-Type:", "Content-Transfer-Encoding:", "To:", "Subject:")
    out = [l.rstrip() for l in text.splitlines() if l.startswith(keep)]
    return out + ["\u2026"]


def enable_http_logging():
    """Log every outgoing request, the way an app would in development.

    Harness configuration, not part of the demo. The beats above are exactly
    the code a user writes; with logging on, those same lines emit the request
    Charter built — URL, injected credential, wire body — as a side effect.
    """
    import httpx, logging

    log = logging.getLogger("charter.http")
    log.setLevel(logging.INFO)
    if not log.handlers:
        class _Stdout(logging.Handler):
            # print() resolves sys.stdout at emit time, so this lands in the
            # per-beat buffer that redirect_stdout installs.
            def emit(self, record):
                print(self.format(record))
        h = _Stdout(); h.setFormatter(logging.Formatter("%(message)s"))
        log.addHandler(h); log.propagate = False

    if getattr(httpx.AsyncClient, "_charter_logged", False):
        return
    original = httpx.AsyncClient.send
    skip = ("host", "accept", "accept-encoding", "connection", "user-agent",
            "content-length")

    async def send(self, request, *a, **kw):
        response = await original(self, request, *a, **kw)
        lines = [f"{request.method} {request.url}"]
        for k, v in request.headers.items():
            k = k.lower()
            if k in skip:
                continue
            if k == "authorization":              # prefix only; not usable
                scheme, _, tok = v.partition(" ")
                v = f"{scheme} {tok[:14]}\u2026"
            lines.append(f"{k}: {v}")
        raw = request.content or b""
        if raw:
            try:
                doc = json.loads(raw)
                key, val = next(iter(doc.items()))
                shown = val if isinstance(val, str) else json.dumps(val)
                lines.append(f'{{"{key}": "{shown[:52]}\u2026"}}'
                             if len(shown) > 52 else f'{{"{key}": "{shown}"}}')
                body = _decoded(val)
                if body:
                    lines.append("    \u21b3 decoded")
                    lines += [f"      {b}" for b in body]
            except Exception:
                lines.append(raw[:52].decode("utf-8", "replace") + "\u2026")
        lines.append(f"HTTP/1.1 {response.status_code} {response.reason_phrase}")
        log.info("\n".join(lines))
        return response

    httpx.AsyncClient.send = send
    httpx.AsyncClient._charter_logged = True


def load_env(path):
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


if __name__ == "__main__":
    load_env(pathlib.Path(__file__).resolve().parents[1] / ".env")
    enable_http_logging()
    beats = list(BEATS)
    dest = pathlib.Path(__file__).parent / "transcript.json"
    dest.write_text(json.dumps(asyncio.run(run(beats)), indent=1))
    steps = sum(1 for b in beats if b[0].strip())
    print(f"captured {steps} executed steps -> {dest}")
