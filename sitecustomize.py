"""
Compatibility shim for running this Django 4.0.x project on newer Python.

Python 3.13+ removed the stdlib `cgi` module, but Django 4.0.x still imports
`cgi.parse_header`. Python automatically imports `sitecustomize` (if present on
sys.path) during startup, so we register a minimal replacement module only when
`cgi` is missing.
"""

from __future__ import annotations

import sys
import types


def _install_cgi_stub() -> None:
    if "cgi" in sys.modules:
        return

    try:
        import cgi as _cgi  # noqa: F401

        return
    except ModuleNotFoundError:
        pass

    cgi_stub = types.ModuleType("cgi")

    def _parseparam(s: str):
        while s[:1] == ";":
            s = s[1:]
            end = s.find(";")
            while end > 0 and s.count('"', 0, end) % 2:
                end = s.find(";", end + 1)
            if end < 0:
                end = len(s)
            f = s[:end].strip()
            yield f
            s = s[end:]

    def parse_header(line: str):
        """
        Parse a Content-type like header.

        Returns (main_value, params_dict). This is a small subset of the Python
        3.12 stdlib `cgi.parse_header` behavior, sufficient for Django 4.0.x.
        """

        parts = _parseparam(";" + (line or ""))
        key = next(parts, "")
        pdict: dict[str, str] = {}
        for p in parts:
            i = p.find("=")
            if i < 0:
                continue
            name = p[:i].strip().lower()
            value = p[i + 1 :].strip()
            if len(value) >= 2 and value[0] == value[-1] == '"':
                value = value[1:-1].replace("\\\\", "\\").replace('\\"', '"')
            pdict[name] = value
        return key, pdict

    cgi_stub.parse_header = parse_header  # type: ignore[attr-defined]
    sys.modules["cgi"] = cgi_stub


_install_cgi_stub()

