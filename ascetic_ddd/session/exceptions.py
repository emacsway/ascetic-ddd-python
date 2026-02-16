__all__ = (
    "ObjectNotFound",
    "ConcurrentUpdate",
)


class ObjectNotFound(Exception):
    pass


class ConcurrentUpdate(Exception):
    pass
