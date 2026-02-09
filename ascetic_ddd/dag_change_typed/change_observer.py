from ascetic_ddd.dag_change_typed.interfaces import IChangeObserver, IChangeSubject, IChangeManager
from ascetic_ddd.dag_change_typed.change_subject import ChangeSubject


__all__ = ('ChangeObserver',)


class ChangeObserver(IChangeObserver, IChangeSubject):
    """
    Observer that is also a Subject (dual role node in DAG).

    Uses composition with ChangeSubject for Go portability
    (maps to Go's struct embedding).
    """

    def __init__(self, name: str, subject_type: str, cm: IChangeManager):
        self._subject = ChangeSubject(name, subject_type, cm)

    # IChangeObserver

    @property
    def name(self) -> str:
        return self._subject.name

    def update(self, subject: IChangeSubject) -> None:
        pass

    # IChangeSubject — delegated to composed ChangeSubject

    @property
    def subject_type(self) -> str:
        return self._subject.subject_type

    def notify(self) -> None:
        self._subject.notify()
