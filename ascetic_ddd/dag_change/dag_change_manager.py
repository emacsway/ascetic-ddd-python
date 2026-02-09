import typing

from ascetic_ddd.dag_change.interfaces import IChangeManager, IChangeSubject, IChangeObserver


__all__ = ('DAGChangeManager',)


def _remove_observer(
        deps: dict[IChangeSubject, list[IChangeObserver]],
        subject: IChangeSubject,
        observer: IChangeObserver,
) -> None:
    observers = deps.get(subject)
    if observers is None:
        return
    for i, o in enumerate(observers):
        if o is observer:
            del observers[i]
            return


def _remove_subject(
        reverse_deps: dict[IChangeObserver, list[IChangeSubject]],
        observer: IChangeObserver,
        subject: IChangeSubject,
) -> None:
    subjects = reverse_deps.get(observer)
    if subjects is None:
        return
    for i, s in enumerate(subjects):
        if s is subject:
            del subjects[i]
            return


class DAGChangeManager(IChangeManager):
    """
    Mediator for propagation of changes through a DAG of dependencies.

    GoF point 1: Associative look-up (dict[Subject, list[Observer]])
      - Subjects without observers do NOT create entries in the dict
      - On unregister_all/unregister, empty entries are deleted
      - Trade-off: O(1) amortized lookup vs inline list in Subject

    GoF point 2: Multi-subject observer support
      - reverse_deps[Observer, list[Subject]] stores all sources of an observer
      - update(subject) allows the observer to distinguish notification sources
      - subjects_of(o) gives the observer its full dependency list

    Guarantees:
      1. Each observer is notified EXACTLY ONCE
      2. Notifications follow topological order of the DAG
      3. No duplication in diamond dependencies
    """

    def __init__(self):
        # GoF point 1: associative look-up instead of storing in Subject.
        # If a subject has no observers, there is simply no entry — zero overhead.
        self._deps: dict[IChangeSubject, list[IChangeObserver]] = {}

        # GoF point 2: reverse mapping observer -> subjects.
        # Enables: (a) topo sort, (b) observer can query its dependencies,
        # (c) correct cleanup on unregister.
        self._reverse_deps: dict[IChangeObserver, list[IChangeSubject]] = {}

    def register(self, subject: IChangeSubject, observer: IChangeObserver) -> None:
        if subject not in self._deps:
            self._deps[subject] = []
        self._deps[subject].append(observer)

        if observer not in self._reverse_deps:
            self._reverse_deps[observer] = []
        self._reverse_deps[observer].append(subject)

    def unregister(self, subject: IChangeSubject, observer: IChangeObserver) -> None:
        _remove_observer(self._deps, subject, observer)
        _remove_subject(self._reverse_deps, observer, subject)

        # GoF point 1: if the subject has no more observers — delete the entry,
        # so we don't waste memory on empty lists.
        if subject in self._deps and len(self._deps[subject]) == 0:
            del self._deps[subject]
        if observer in self._reverse_deps and len(self._reverse_deps[observer]) == 0:
            del self._reverse_deps[observer]

    def unregister_all(self, subject: IChangeSubject) -> None:
        for observer in self._deps.get(subject, []):
            _remove_subject(self._reverse_deps, observer, subject)
            if observer in self._reverse_deps and len(self._reverse_deps[observer]) == 0:
                del self._reverse_deps[observer]
        if subject in self._deps:
            del self._deps[subject]

    def observers_of(self, subject: IChangeSubject) -> typing.List[IChangeObserver]:
        return self._deps.get(subject, [])

    def subjects_of(self, observer: IChangeObserver) -> typing.List[IChangeSubject]:
        return self._reverse_deps.get(observer, [])

    def notify(self, changed: IChangeSubject) -> None:
        """Propagate change from subject through the DAG in topological order."""
        affected: dict[IChangeObserver, bool] = {}
        self._collect_affected(changed, affected)

        if not affected:
            return

        sorted_ = self._topo_sort(affected)

        # GoF point 2: pass changed (the original subject) into update(),
        # so multi-subject observers know who initiated the cascade.
        for observer in sorted_:
            observer.update(changed)

    def _collect_affected(
            self,
            subject: IChangeSubject,
            visited: dict[IChangeObserver, bool],
    ) -> None:
        for observer in self._deps.get(subject, []):
            if observer not in visited:
                visited[observer] = True
                if isinstance(observer, IChangeSubject):
                    self._collect_affected(observer, visited)

    def _topo_sort(
            self,
            affected: dict[IChangeObserver, bool],
    ) -> typing.List[IChangeObserver]:
        in_degree: dict[IChangeObserver, int] = {}
        for observer in affected:
            in_degree[observer] = 0

        for observer in affected:
            for dep in self._reverse_deps.get(observer, []):
                if isinstance(dep, IChangeObserver) and dep in affected:
                    in_degree[observer] += 1

        queue: list[IChangeObserver] = []
        for observer, deg in in_degree.items():
            if deg == 0:
                queue.append(observer)

        sorted_: list[IChangeObserver] = []
        while queue:
            node = queue.pop(0)
            sorted_.append(node)

            if isinstance(node, IChangeSubject):
                for observer in self._deps.get(node, []):
                    if observer in affected:
                        in_degree[observer] -= 1
                        if in_degree[observer] == 0:
                            queue.append(observer)

        return sorted_
