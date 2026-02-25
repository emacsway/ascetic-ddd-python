import typing

from ascetic_ddd.dag_change_typed.interfaces import IChangeManager, IChangeSubject, IChangeObserver


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


def _cleanup_empty(
        deps: dict[IChangeSubject, list[IChangeObserver]],
        reverse_deps: dict[IChangeObserver, list[IChangeSubject]],
        subject: IChangeSubject,
        observer: IChangeObserver,
) -> None:
    if subject in deps and len(deps[subject]) == 0:
        del deps[subject]
    if observer in reverse_deps and len(reverse_deps[observer]) == 0:
        del reverse_deps[observer]


class DAGChangeManager(IChangeManager):
    """
    Hybrid instance-based + type-based DAG Change Manager.

    Type-based subscriptions act as edge factories:
      - register_by_type("Sensor", aggregator) — declaration of intent
      - When a concrete Sensor1 appears (add_subject), the manager
        automatically calls register(sensor1, aggregator) — creates
        a real edge in the graph
      - Topo sort, diamond detection — all work on concrete edges

    This is analogous to auto-wiring in DI containers: you declare
    a dependency on a type, the container resolves it to an instance.
    """

    def __init__(self) -> None:
        # Instance-based edges
        self._deps: dict[IChangeSubject, list[IChangeObserver]] = {}
        self._reverse_deps: dict[IChangeObserver, list[IChangeSubject]] = {}

        # Type-based registry
        self._type_bindings: list[tuple[str, IChangeObserver]] = []
        self._subjects: dict[str, list[IChangeSubject]] = {}
        self._auto_edges: dict[IChangeSubject, dict[IChangeObserver, bool]] = {}

    # --- Instance-based registration ---

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
        _cleanup_empty(self._deps, self._reverse_deps, subject, observer)

    # --- Type-based registration ---

    def register_by_type(self, subject_type: str, observer: IChangeObserver) -> None:
        """
        Observer wants to observe all Subjects with the given subject_type.

        For already known subjects of this type, edges are created immediately.
        """
        self._type_bindings.append((subject_type, observer))

        for subject in self._subjects.get(subject_type, []):
            if not self._has_edge(subject, observer):
                self.register(subject, observer)
                self._mark_auto_edge(subject, observer)

    def unregister_by_type(self, subject_type: str, observer: IChangeObserver) -> None:
        # Remove binding
        for i, (typ, obs) in enumerate(self._type_bindings):
            if typ == subject_type and obs is observer:
                del self._type_bindings[i]
                break

        # Remove auto-edges
        for subject in self._subjects.get(subject_type, []):
            if self._is_auto_edge(subject, observer):
                self.unregister(subject, observer)
                del self._auto_edges[subject][observer]

    # --- Lifecycle ---

    def add_subject(self, subject: IChangeSubject) -> None:
        """
        Subject announces its appearance.

        The manager checks type-based bindings and creates edges
        for matching observers.
        """
        typ = subject.subject_type
        if typ not in self._subjects:
            self._subjects[typ] = []
        self._subjects[typ].append(subject)

        for binding_type, observer in self._type_bindings:
            if binding_type == typ:
                # Don't subscribe observer to itself
                if subject is observer:  # type: ignore[comparison-overlap]
                    continue
                if not self._has_edge(subject, observer):
                    self.register(subject, observer)
                    self._mark_auto_edge(subject, observer)

    def remove_subject(self, subject: IChangeSubject) -> None:
        # Remove all edges from this subject
        for observer in self._deps.get(subject, []):
            _remove_subject(self._reverse_deps, observer, subject)
            if observer in self._reverse_deps and len(self._reverse_deps[observer]) == 0:
                del self._reverse_deps[observer]
        if subject in self._deps:
            del self._deps[subject]
        if subject in self._auto_edges:
            del self._auto_edges[subject]

        # Remove from subject registry
        typ = subject.subject_type
        subjects = self._subjects.get(typ, [])
        for i, s in enumerate(subjects):
            if s is subject:
                del subjects[i]
                break

    # --- Introspection ---

    def observers_of(self, subject: IChangeSubject) -> typing.List[IChangeObserver]:
        return self._deps.get(subject, [])

    def subjects_of(self, observer: IChangeObserver) -> typing.List[IChangeSubject]:
        return self._reverse_deps.get(observer, [])

    # --- Notify with DAG topo sort ---

    def notify(self, changed: IChangeSubject) -> None:
        affected: dict[IChangeObserver, bool] = {}
        self._collect_affected(changed, affected)

        if not affected:
            return

        sorted_ = self._topo_sort(affected)

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

    # --- Internal helpers ---

    def _has_edge(self, subject: IChangeSubject, observer: IChangeObserver) -> bool:
        for o in self._deps.get(subject, []):
            if o is observer:
                return True
        return False

    def _mark_auto_edge(self, subject: IChangeSubject, observer: IChangeObserver) -> None:
        if subject not in self._auto_edges:
            self._auto_edges[subject] = {}
        self._auto_edges[subject][observer] = True

    def _is_auto_edge(self, subject: IChangeSubject, observer: IChangeObserver) -> bool:
        return subject in self._auto_edges and observer in self._auto_edges[subject]
