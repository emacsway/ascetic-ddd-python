__all__ = ('empty', 'Empty', )


class Empty:

    def __bool__(self):
        return False


empty = Empty()
