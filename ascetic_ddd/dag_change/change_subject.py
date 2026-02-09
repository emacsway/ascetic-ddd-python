from ascetic_ddd.dag_change.interfaces import IChangeSubject, IChangeManager


__all__ = ('ChangeSubject',)


class ChangeSubject(IChangeSubject):
    """
    Lightweight subject that delegates notify() to its ChangeManager.

    Does NOT store observers — this is delegated to ChangeManager
    (GoF point 1: "Associative look-up"). Storage overhead is zero
    for subjects without observers.
    """

    def __init__(self, name: str, cm: IChangeManager):
        self._name = name
        self._cm = cm

    @property
    def name(self) -> str:
        return self._name

    def set_change_manager(self, cm: IChangeManager) -> None:
        self._cm = cm

    def get_change_manager(self) -> IChangeManager:
        return self._cm

    def notify(self) -> None:
        self._cm.notify(self)
