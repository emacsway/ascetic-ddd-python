from ascetic_ddd.dag_change_typed.interfaces import IChangeSubject, IChangeManager


__all__ = ('ChangeSubject',)


class ChangeSubject(IChangeSubject):
    """
    Lightweight subject with type-based matching support.

    Does NOT store observers — this is delegated to ChangeManager.
    Auto-registers itself via cm.add_subject() on construction,
    which triggers type-based wiring for matching bindings.
    """

    def __init__(self, name: str, subject_type: str, cm: IChangeManager):
        self._name = name
        self._subject_type = subject_type
        self._cm = cm
        cm.add_subject(self)

    @property
    def name(self) -> str:
        return self._name

    @property
    def subject_type(self) -> str:
        return self._subject_type

    def notify(self) -> None:
        self._cm.notify(self)
