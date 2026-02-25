import typing

from ascetic_ddd.dag_change.interfaces import IChangeManager, IChangeSubject, IChangeObserver


__all__ = ('SimpleChangeManager',)


class SimpleChangeManager(IChangeManager):
    """
    Naive change manager without topological sort.

    Notifies observers in registration order without deduplication.
    Useful for comparison and for cases where DAG ordering is not needed.
    """

    def __init__(self) -> None:
        self._deps: dict[IChangeSubject, list[IChangeObserver]] = {}
        self._reverse_deps: dict[IChangeObserver, list[IChangeSubject]] = {}

    def register(self, subject: IChangeSubject, observer: IChangeObserver) -> None:
        if subject not in self._deps:
            self._deps[subject] = []
        self._deps[subject].append(observer)

        if observer not in self._reverse_deps:
            self._reverse_deps[observer] = []
        self._reverse_deps[observer].append(subject)

    def unregister(self, subject: IChangeSubject, observer: IChangeObserver) -> None:
        observers = self._deps.get(subject)
        if observers is not None:
            for i, o in enumerate(observers):
                if o is observer:
                    del observers[i]
                    break
            if len(observers) == 0:
                del self._deps[subject]

        subjects = self._reverse_deps.get(observer)
        if subjects is not None:
            for i, s in enumerate(subjects):
                if s is subject:
                    del subjects[i]
                    break
            if len(subjects) == 0:
                del self._reverse_deps[observer]

    def unregister_all(self, subject: IChangeSubject) -> None:
        for observer in self._deps.get(subject, []):
            subjects = self._reverse_deps.get(observer)
            if subjects is not None:
                for i, s in enumerate(subjects):
                    if s is subject:
                        del subjects[i]
                        break
                if len(subjects) == 0:
                    del self._reverse_deps[observer]
        if subject in self._deps:
            del self._deps[subject]

    def notify(self, subject: IChangeSubject) -> None:
        for observer in self._deps.get(subject, []):
            observer.update(subject)

    def observers_of(self, subject: IChangeSubject) -> typing.List[IChangeObserver]:
        return self._deps.get(subject, [])

    def subjects_of(self, observer: IChangeObserver) -> typing.List[IChangeSubject]:
        return self._reverse_deps.get(observer, [])
