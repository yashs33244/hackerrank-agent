"""Backwards-compatibility shim — all types now live in domain/types.py.

Importing from state.py still works for existing tests.
"""
from domain.types import Chunk, TicketState  # noqa: F401
