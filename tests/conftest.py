"""Fixtures required for testing."""

import importlib.abc
import importlib.machinery
import sys
from collections import defaultdict

import pytest


class _uwsgi:
    def __init__(self):
        self._caches = defaultdict(lambda: {})

    @staticmethod
    def lock(_):
        pass

    @staticmethod
    def unlock(_):
        pass

    def cache_exists(self, key, cache):
        return key in self._caches[cache]

    def cache_update(self, key, value, _, cache):
        self._caches[cache][key] = value.encode()

    def cache_get(self, key, cache):
        return self._caches[cache][key]


class _Loader(importlib.abc.Loader):
    def __init__(self):
        self._uwsgi = _uwsgi()

    def create_module(self, spec):
        return self._uwsgi

    def exec_module(self, module):
        pass


class _Finder(importlib.abc.MetaPathFinder):
    def __init__(self, loader):
        self._loader = loader

    def find_spec(self, fullname, path, target):
        if fullname == "uwsgi":
            return importlib.machinery.ModuleSpec(fullname, self._loader)


@pytest.fixture(autouse=True)
def searchengine_import():
    """Edit the meta path to import custom uwsgi module."""
    loader = _Loader()
    finder = _Finder(loader)
    sys.meta_path.append(finder)  # type: ignore

    yield

    sys.meta_path.remove(finder)  # type: ignore
