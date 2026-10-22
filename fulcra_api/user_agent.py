"""User-Agent header for the requests the library makes.

Every request names the library and its version, so Fulcra can tell the
library, the `fulcra` CLI and the tools built on them (such as the MCP server)
apart from other HTTP clients. Callers add their own product token after it,
e.g. `fulcra-api/0.1.55 python/3.12 fulcra-cli/0.1.55`. Nothing identifying the
user or the machine goes in it.
"""

import re
import sys

from . import __version__

# Product tokens and comments: printable ASCII without control characters,
# so a caller's string can't break or add to the header.
_EXTRA = re.compile(r"[\x20-\x7e]+")


def default_user_agent() -> str:
    """The library's own product tokens, e.g. `fulcra-api/0.1.55 python/3.12`."""
    major, minor = sys.version_info[:2]
    return f"fulcra-api/{__version__} python/{major}.{minor}"


def build_user_agent(extra: str | None = None) -> str:
    """The library's User-Agent, followed by the caller's product tokens, if any.

    Raises ValueError if `extra` is empty or has characters outside printable
    ASCII.
    """
    if extra is None:
        return default_user_agent()
    extra = extra.strip()
    if not extra or not _EXTRA.fullmatch(extra):
        raise ValueError(
            "user_agent_extra must be non-empty printable ASCII, e.g. 'my-tool/1.0'"
        )
    return f"{default_user_agent()} {extra}"
