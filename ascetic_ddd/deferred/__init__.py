"""Deferred pattern for handling asynchronous operations."""
from ascetic_ddd.deferred.deferred import Deferred, noop
from ascetic_ddd.deferred.interfaces import IDeferred, DeferredCallback

__all__ = [
    "IDeferred",
    "DeferredCallback",
    "Deferred",
    "noop",
]
