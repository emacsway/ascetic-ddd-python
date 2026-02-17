import copy
import collections

from collections.abc import Callable, Hashable

from ascetic_ddd.disposable import IDisposable
from ascetic_ddd.disposable.disposable import Disposable
from ascetic_ddd.observable.interfaces import IObservable


class Observable(IObservable):

    def __init__(self):
        self._observers = collections.defaultdict(collections.OrderedDict)
        super().__init__()

    def attach(self, aspect: Hashable, observer: Callable, observer_id: Hashable | None = None) -> IDisposable:
        observer_id = observer_id or self._make_id(observer)
        if observer_id not in self._observers[aspect]:
            self._observers[aspect][observer_id] = observer

        async def detach():
            self.detach(aspect, observer, observer_id)

        return Disposable(detach)

    def detach(self, aspect: Hashable, observer: Callable, observer_id: Hashable | None = None):
        observer_id = observer_id or self._make_id(observer)
        del self._observers[aspect][observer_id]

    def notify(self, aspect: Hashable, *args, **kwargs):
        observers = collections.OrderedDict()
        observers.update(self._observers[None])
        observers.update(self._observers[aspect])
        for observer in observers.values():
            observer(aspect, *args, **kwargs)

    async def anotify(self, aspect: Hashable, *args, **kwargs):
        observers = collections.OrderedDict()
        observers.update(self._observers[None])
        observers.update(self._observers[aspect])
        for observer in observers.values():
            await observer(aspect, *args, **kwargs)

    @staticmethod
    def _make_id(target) -> Hashable:
        if hasattr(target, "__func__"):
            return (id(target.__self__), id(target.__func__))
        return id(target)

    def __copy__(self):
        c = copy.copy(super())
        c._observers = collections.defaultdict(collections.OrderedDict)
        return c
