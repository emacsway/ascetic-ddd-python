Signals
=======

.. index:: signals, signal pattern, typed observer

The signals module provides the typed Signal pattern implementation —
a composition-based alternative to the classic Observer pattern.

Each event aspect is a separate typed signal attribute (``ISyncSignal[EventT]``
or ``IAsyncSignal[EventT]``) instead of string-based aspects with ``*args, **kwargs``.

Overview
--------

The classic Observer pattern uses a single ``attach(aspect, observer)``
method where ``aspect`` is a string key. This couples observers to
string-based dispatch and loses type information.

The Signal pattern replaces string-based aspects with typed attributes:

.. code-block:: python

   # Classic Observer (string-based)
   session.attach("on_started", handler)

   # Signal pattern (typed)
   session.on_started.attach(handler)

Each signal is a standalone object that manages its own list of observers,
typed to the specific event it emits.

Interfaces
----------

.. code-block:: python

   class ISyncSignal(typing.Generic[EventT], metaclass=ABCMeta):
       def attach(self, observer, observer_id=None) -> IDisposable: ...
       def detach(self, observer, observer_id=None): ...
       def notify(self, event: EventT): ...

   class IAsyncSignal(typing.Generic[EventT], metaclass=ABCMeta):
       def attach(self, observer, observer_id=None) -> IDisposable: ...
       def detach(self, observer, observer_id=None): ...
       async def notify(self, event: EventT): ...

``attach(observer, observer_id=None)``
    Registers an observer. Returns an ``IDisposable`` — calling
    ``await disposable.dispose()`` detaches the observer.
    If an observer with the same identity is already attached,
    the call is idempotent (no duplicate registration).

``detach(observer, observer_id=None)``
    Removes the observer. Raises ``KeyError`` if not found.

``notify(event)``
    Calls all registered observers with the event, in registration order.
    ``AsyncSignal`` awaits each observer sequentially.

``observer_id``
    Optional explicit identity for the observer. If omitted, the signal
    computes identity automatically: ``id(func)`` for functions,
    ``(id(self), id(method))`` for bound methods.

Implementations
---------------

SyncSignal / AsyncSignal
^^^^^^^^^^^^^^^^^^^^^^^^

Primary signal implementations. Each maintains an ``OrderedDict``
of observers, preserving insertion order.

.. code-block:: python

   from ascetic_ddd.signals.signal import SyncSignal, AsyncSignal

   sync_signal = SyncSignal[MyEvent]()
   async_signal = AsyncSignal[MyEvent]()

SyncCompositeSignal / AsyncCompositeSignal
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Composite signals that delegate ``attach``, ``detach``, and ``notify``
to multiple underlying signals. Useful when a composite object aggregates
signals from several delegates.

.. code-block:: python

   from ascetic_ddd.signals.composite_signal import AsyncCompositeSignal

   composite = AsyncCompositeSignal(signal_a, signal_b)
   composite.attach(observer, observer_id="obs")  # attaches to both

   await composite.notify(event)  # notifies both

``attach`` returns a single ``IDisposable`` that detaches the observer
from all delegates at once.

Usage
-----

Declaring signals on a class
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Expose signals as typed attributes on your class interface:

.. code-block:: python

   from dataclasses import dataclass
   from ascetic_ddd.signals.interfaces import IAsyncSignal
   from ascetic_ddd.signals.signal import AsyncSignal

   @dataclass(frozen=True)
   class SessionStartedEvent:
       session: object

   @dataclass(frozen=True)
   class SessionEndedEvent:
       session: object

   class MySession:
       _on_started: IAsyncSignal[SessionStartedEvent]
       _on_ended: IAsyncSignal[SessionEndedEvent]

       def __init__(self):
           self._on_started = AsyncSignal[SessionStartedEvent]()
           self._on_ended = AsyncSignal[SessionEndedEvent]()

       @property
       def on_started(self) -> IAsyncSignal[SessionStartedEvent]:
           return self._on_started

       @property
       def on_ended(self) -> IAsyncSignal[SessionEndedEvent]:
           return self._on_ended

Subscribing and unsubscribing
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: python

   async def on_session_started(event: SessionStartedEvent):
       print("Session started")

   # Subscribe — returns IDisposable
   disposable = session.on_started.attach(on_session_started)

   # Notify all observers
   await session.on_started.notify(SessionStartedEvent(session=session))

   # Unsubscribe via disposable
   await disposable.dispose()

   # Or unsubscribe directly
   session.on_started.detach(on_session_started)

Composite signals
^^^^^^^^^^^^^^^^^

``CompositeSession`` uses ``AsyncCompositeSignal`` to aggregate signals from
multiple delegate sessions, so a single ``attach`` subscribes to all:

.. code-block:: python

   from ascetic_ddd.signals.composite_signal import AsyncCompositeSignal

   class CompositeSessionPool:
       def __init__(self, *delegates):
           self._delegates = delegates

       @property
       def on_session_started(self):
           return AsyncCompositeSignal(
               *(d.on_session_started for d in self._delegates)
           )

Copy semantics
^^^^^^^^^^^^^^

All signal classes support ``copy.copy()``. A shallow copy creates a new
signal with an empty observer list, ensuring that copied objects do not
share observers with the original.

See the :doc:`/api/index` for auto-generated API documentation.
