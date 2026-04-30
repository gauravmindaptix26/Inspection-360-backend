"""
Minimal `cgi` module for Python 3.13+ compatibility.

Python 3.13 removed the stdlib `cgi` module. Django 4.0.x still imports
`cgi.parse_header` (used to parse the Content-Type header). This project is on
`Django==4.0.2`, so on Python 3.13+ we provide the small subset Django needs.

If you later move this project to an older Python version that still includes
stdlib `cgi`, this local module will still work for Django's use.
"""

from __future__ import annotations


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
    Parse a Content-type like header value.

    Returns (main_value, params_dict).
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

