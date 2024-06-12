import builtins
from types import ModuleType
from typing import Mapping, Optional, Sequence

_builtin_import = builtins.__import__


def _import(
    name: str,
    globals: Optional[Mapping[str, object]] = None,
    locals: Optional[Mapping[str, object]] = None,
    fromlist: Sequence[str] = (),
    level: int = 0,
) -> ModuleType:
    if name == "searx.network":
        mod = ModuleType("searx.network")
        mod.get = lambda *args, **kwargs: None  # type: ignore[attr-defined]
        return mod

    return _builtin_import(name, globals, locals, fromlist, level)


builtins.__import__ = _import
