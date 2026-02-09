from ascetic_ddd.dag_change.interfaces import IChangeObserver, IChangeSubject, IChangeManager
from ascetic_ddd.dag_change.change_subject import ChangeSubject


__all__ = ('ChangeObserver',)


class ChangeObserver(IChangeObserver, IChangeSubject):
    """
    Observer that is also a Subject (dual role node in DAG).

    Uses composition with ChangeSubject for Go portability
    (maps to Go's struct embedding).

    GoF point 2: Update receives the source Subject so that
    multi-subject observers can distinguish notification sources.
    """

    def __init__(self, name: str, cm: IChangeManager):
        self._subject = ChangeSubject(name, cm)

    # IChangeObserver

    @property
    def name(self) -> str:
        return self._subject.name

    def update(self, subject: IChangeSubject) -> None:
        pass

    # IChangeSubject — delegated to composed ChangeSubject

    def set_change_manager(self, cm: IChangeManager) -> None:
        self._subject.set_change_manager(cm)

    def get_change_manager(self) -> IChangeManager:
        return self._subject.get_change_manager()

    def notify(self) -> None:
        self._subject.notify()
