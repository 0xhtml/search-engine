"""Module to store metrics about engines."""

import contextlib
import sqlite3
from typing import NamedTuple

from .engines import Engine, EngineResults
from .templates import pretty_exc


class EngineError(NamedTuple):
    """Class to store engine errors."""

    engine: Engine
    error: BaseException

    def __eq__(self, other: object) -> bool:
        """Check if two engine errors are equal."""
        if not isinstance(other, EngineError):
            return NotImplemented
        if str(self.engine) != str(other.engine):
            return False
        return pretty_exc(self.error) == pretty_exc(other.error)

    def __hash__(self) -> int:
        """Hash the engine error."""
        return hash((str(self.engine), pretty_exc(self.error)))


def _create_tables(con: sqlite3.Connection) -> None:
    con.execute("""
        CREATE TABLE IF NOT EXISTS success (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            engine TEXT NOT NULL,
            result_count INTEGER NOT NULL,
            time REAL NOT NULL
        );
    """)
    con.execute("""
        CREATE TABLE IF NOT EXISTS error (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            engine TEXT NOT NULL,
            error TEXT NOT NULL
        );
    """)


def metric_success(engine_results: EngineResults) -> None:
    """Store success metrics in database."""
    with contextlib.closing(sqlite3.connect("metrics.db")) as con, con:
        _create_tables(con)
        con.execute(
            "INSERT INTO success (engine, result_count, time) VALUES (?, ?, ?)",
            (
                str(engine_results.engine),
                len(engine_results.results),
                engine_results.elapsed,
            ),
        )


def metric_errors(errors: set[EngineError]) -> None:
    """Store engine error metrics in database."""
    with contextlib.closing(sqlite3.connect("metrics.db")) as con, con:
        _create_tables(con)
        con.executemany(
            "INSERT INTO error (engine, error) VALUES (?, ?)",
            [(str(engine), pretty_exc(exc)) for engine, exc in errors],
        )
