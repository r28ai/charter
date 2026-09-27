"""Executing a documentation code block the way a reader would.

The docs are written to be pasted into the file their title names, which means a
block that makes a call drives it itself — ``asyncio.run(main())`` — rather than
leaving a bare ``await`` at module level for the reader to discover is a
``SyntaxError``. That shape cannot be ``eval``'d here directly: these tests are
async, so a loop is already running on this thread and ``asyncio.run`` refuses.

So a self-driving block runs on a worker thread, which has no loop of its own.
``respx`` patches httpx's transport classes process-wide, so the mock installed
by the caller still applies there, and the namespace is the caller's dict, so
blocks that chain still see what earlier ones defined.

The older shape — top-level ``await``, no driver — is still supported, because
not every block is a whole program: an excerpt from a request handler has no
business calling ``asyncio.run``.
"""

from __future__ import annotations

import ast
import asyncio
import inspect
import re

_DRIVES_ITSELF = re.compile(r"^asyncio\.run\(", re.M)


def drives_itself(source: str) -> bool:
    """True when the block runs its own event loop at module level."""
    return bool(_DRIVES_ITSELF.search(source))


async def run_doc_block(source: str, namespace: dict, origin: str) -> None:
    """Execute one block, whichever of the two shapes it is.

    ``dont_inherit``, or the calling module's ``from __future__ import
    annotations`` would follow the snippet in and stringify every annotation —
    which a reader pasting the block into their own file would not get.
    """
    code = compile(
        source,
        origin,
        "exec",
        flags=ast.PyCF_ALLOW_TOP_LEVEL_AWAIT,
        dont_inherit=True,
    )
    if drives_itself(source):
        # No loop on that thread, so the block's own asyncio.run works.
        await asyncio.to_thread(eval, code, namespace)  # noqa: S307 — this repo's docs
        return
    result = eval(code, namespace)  # noqa: S307 — this repo's docs
    if inspect.iscoroutine(result):
        await result
