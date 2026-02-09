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
    Subject in a DAG dependency graph with type-based matching.

    Does NOT store observers — this is delegated to ChangeManager
    (GoF point 1: "Associative look-up").

    subject_type enables type-based subscriptions: observers can subscribe
    to all subjects of a given type via register_by_type().
    """

    @property
    @abstractmethod
    def name(self) -> str:
        raise NotImplementedError

    @property
    @abstractmethod
    def subject_type(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def notify(self) -> None:
        raise NotImplementedError


class IChangeManager(metaclass=ABCMeta):
    """
    Mediator that owns the associative mapping subject -> observers.

    Supports both instance-based and type-based subscriptions.
    Type-based subscriptions act as edge factories: when a subject
    with a matching type appears, instance-based edges are created
    automatically (auto-wiring, analogous to DI container resolution).
    """

    # Instance-based registration

    @abstractmethod
    def register(self, subject: IChangeSubject, observer: IChangeObserver) -> None:
        raise NotImplementedError

    @abstractmethod
    def unregister(self, subject: IChangeSubject, observer: IChangeObserver) -> None:
        raise NotImplementedError

    @abstractmethod
    def notify(self, subject: IChangeSubject) -> None:
        raise NotImplementedError

    # Type-based registration

    @abstractmethod
    def register_by_type(self, subject_type: str, observer: IChangeObserver) -> None:
        raise NotImplementedError

    @abstractmethod
    def unregister_by_type(self, subject_type: str, observer: IChangeObserver) -> None:
        raise NotImplementedError

    # Lifecycle: subject announces its appearance/removal

    @abstractmethod
    def add_subject(self, subject: IChangeSubject) -> None:
        raise NotImplementedError

    @abstractmethod
    def remove_subject(self, subject: IChangeSubject) -> None:
        raise NotImplementedError

    # Introspection

    @abstractmethod
    def observers_of(self, subject: IChangeSubject) -> typing.List[IChangeObserver]:
        raise NotImplementedError

    @abstractmethod
    def subjects_of(self, observer: IChangeObserver) -> typing.List[IChangeSubject]:
        raise NotImplementedError
