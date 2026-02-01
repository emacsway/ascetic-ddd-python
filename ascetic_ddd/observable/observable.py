import copy
import collections

from collections.abc import Callable, Hashable

from ascetic_ddd.disposable import IDisposable
from ascetic_ddd.disposable.disposable import Disposable
from ascetic_ddd.observable.interfaces import IObservable


class Observable(IObservable):

    def __init__(self):
        self._observers = collections.defaultdict(collections.OrderedDict)

    def attach(self, aspect: Hashable, observer: Callable, id_: Hashable | None = None) -> IDisposable:
        id_ = id_ or id(observer)
        if id_ not in self._observers[aspect]:
            self._observers[aspect][id_] = observer

        async def detach():
            self.detach(aspect, observer, id_)

        return Disposable(detach)

    def detach(self, aspect: Hashable, observer: Callable, id_: Hashable | None = None):
        id_ = id_ or id(observer)
        del self._observers[aspect][id_]

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

    def __copy__(self):
        c = copy.copy(super())
        c._observers = collections.defaultdict(collections.OrderedDict)
        return c
