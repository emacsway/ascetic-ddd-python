import typing
from abc import ABCMeta, abstractmethod


__all__ = (
    'IChangeObserver',
    'IChangeSubject',
    'IChangeManager',
)


class IChangeObserver(metaclass=ABCMeta):
    """
    Observer in a DAG dependency graph.

    Update receives the source Subject so that multi-subject observers
    can distinguish which source triggered the notification
    (GoF point 2: "Observing more than one subject").
    """

    @property
    @abstractmethod
    def name(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def update(self, subject: 'IChangeSubject') -> None:
        raise NotImplementedError


class IChangeSubject(metaclass=ABCMeta):
    """
    Subject in a DAG dependency graph.

    Does NOT store observers — this is delegated to ChangeManager
    (GoF point 1: "Associative look-up").
    """

    @property
    @abstractmethod
    def name(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def set_change_manager(self, cm: 'IChangeManager') -> None:
        raise NotImplementedError

    @abstractmethod
    def get_change_manager(self) -> 'IChangeManager':
        raise NotImplementedError

    @abstractmethod
    def notify(self) -> None:
        raise NotImplementedError


class IChangeManager(metaclass=ABCMeta):
    """
    Mediator that owns the associative mapping subject -> observers.

    GoF point 1: Associative look-up instead of storing observers in Subject.
    GoF point 2: Reverse mapping observer -> subjects for multi-subject support.
    """

    @abstractmethod
    def register(self, subject: IChangeSubject, observer: IChangeObserver) -> None:
        raise NotImplementedError

    @abstractmethod
    def unregister(self, subject: IChangeSubject, observer: IChangeObserver) -> None:
        raise NotImplementedError

    @abstractmethod
    def unregister_all(self, subject: IChangeSubject) -> None:
        raise NotImplementedError

    @abstractmethod
    def notify(self, subject: IChangeSubject) -> None:
        raise NotImplementedError

    @abstractmethod
    def observers_of(self, subject: IChangeSubject) -> typing.List[IChangeObserver]:
        raise NotImplementedError

    @abstractmethod
    def subjects_of(self, observer: IChangeObserver) -> typing.List[IChangeSubject]:
        raise NotImplementedError
