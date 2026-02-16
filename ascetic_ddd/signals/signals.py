from weakref import WeakKeyDictionary, WeakValueDictionary

__all__ = ('Signal',)


class UndefinedSender:
    pass


undefined_sender = UndefinedSender()


class Signal:

    def __init__(self):
        self._flush()

    def _flush(self):
        self._receivers = WeakKeyDictionary()
        self._weak_cache = set()

    def connect(self, receiver, sender_type=None, weak=True, receiver_id=None):
        if sender_type is None:
            sender_type = undefined_sender
        if not weak:
            self._weak_cache.add(receiver)
        if receiver_id is None:
            receiver_id = self._make_id(receiver)
        if sender_type not in self._receivers:
            self._receivers[sender_type] = WeakValueDictionary()
        self._receivers[sender_type][receiver_id] = receiver

    @staticmethod
    def _make_id(target):
        if hasattr(target, '__func__'):
            return (type(target), id(target.__self__), id(target.__func__))
        return (type(target), id(target))

    def disconnect(self, receiver=None, sender_type=None, receiver_id=None):
        if sender_type is None:
            sender_type = undefined_sender
        if receiver_id is None:
            receiver_id = self._make_id(receiver)
        if receiver_id:
            try:
                self._weak_cache.discard(receiver or self._receivers[sender_type][receiver_id])
                del self._receivers[sender_type][receiver_id]
                if not self._receivers[sender_type]:
                    del self._receivers[sender_type]
            except KeyError:
                pass
        else:
            raise ValueError('a receiver or a receiver_id must be provided')

    def send(self, sender, *args, **kwargs):
        if sender is None:
            sender = undefined_sender
        responses = []
        sender_type = type(sender)
        if sender_type in self._receivers:
            for receiver in self._receivers[sender_type].values():
                responses.append((receiver, receiver(sender_type, *args, **kwargs)))
        if sender_type is not undefined_sender:
            responses += self.send(undefined_sender, *args, **kwargs)
        return responses

    async def asend(self, sender, *args, **kwargs):
        if sender is None:
            sender = undefined_sender
        responses = []
        sender_type = type(sender)
        if sender_type in self._receivers:
            for receiver in self._receivers[sender_type].values():
                responses.append((receiver, await receiver(sender_type, *args, **kwargs)))
        if sender_type is not undefined_sender:
            responses += await self.asend(undefined_sender, *args, **kwargs)
        return responses


def connect(signal, sender=None, weak=True, receiver_id=None):
    def decorator(fn):
        signal.connect(fn, sender, weak, receiver_id)
        return fn
    return decorator
