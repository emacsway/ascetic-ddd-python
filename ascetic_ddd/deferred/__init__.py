"""Deferred pattern for handling asynchronous operations."""
from ascetic_ddd.deferred.deferred import Deferred, noop
from ascetic_ddd.deferred.interfaces import IDeferred

__all__ = [
    "IDeferred",
    "Deferred",
    "noop",
]
