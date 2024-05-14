import builtins
from types import ModuleType

_builtin_import = builtins.__import__


def _import(name, globals=None, locals=None, fromlist=(), level=0) -> object:
    if name == "searx.network":
        mod = ModuleType("searx.network")
        mod.get = lambda *args, **kwargs: None
        return mod

    return _builtin_import(name, globals, locals, fromlist, level)


builtins.__import__ = _import
