"""Overwrite import of searx.network to avoid spawning of threads."""

import builtins
from collections.abc import Mapping, Sequence
from types import ModuleType
from typing import Optional

_builtin_import = builtins.__import__


def _import(
    name: str,
    globals: Optional[Mapping[str, object]] = None,  # noqa: A002
    locals: Optional[Mapping[str, object]] = None,  # noqa: A002
    fromlist: Sequence[str] = (),
    level: int = 0,
) -> ModuleType:
    if name == "searx.network":
        mod = ModuleType("searx.network")
        mod.get = lambda *_, **__: None  # type: ignore[attr-defined]
        mod.raise_for_httperror = lambda _: None  # type: ignore[attr-defined]
        return mod

    return _builtin_import(name, globals, locals, fromlist, level)


builtins.__import__ = _import
