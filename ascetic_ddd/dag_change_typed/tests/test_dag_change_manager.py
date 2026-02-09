import unittest

from ascetic_ddd.dag_change_typed.change_subject import ChangeSubject
from ascetic_ddd.dag_change_typed.change_observer import ChangeObserver
from ascetic_ddd.dag_change_typed.dag_change_manager import DAGChangeManager
from ascetic_ddd.dag_change_typed.interfaces import IChangeSubject


class RecordingObserver(ChangeObserver):
    """Observer that records update calls for test assertions."""

    def __init__(self, name, subject_type, cm):
        super().__init__(name, subject_type, cm)
        self.updates = []

    def update(self, subject: IChangeSubject) -> None:
        self.updates.append((subject.name, subject.subject_type))


class PureRecordingObserver:
    """Pure observer (not a Subject) that records updates."""

    def __init__(self, name):
        self._name = name
        self.updates = []

    @property
    def name(self) -> str:
        return self._name

    def update(self, subject: IChangeSubject) -> None:
        self.updates.append((subject.name, subject.subject_type))


class RegisterByTypeBeforeSubjectsTestCase(unittest.TestCase):
    """
    Scenario 1: register_by_type BEFORE subjects are created.

    Observer subscribes to type "DataSource".
    Then concrete DataSource subjects appear — edges are created automatically.
    """

    def test_auto_wiring_on_add_subject(self):
        cm = DAGChangeManager()
        cell = PureRecordingObserver("TotalCell")

        cm.register_by_type("DataSource", cell)

        price = ChangeSubject("Price", "DataSource", cm)
        tax = ChangeSubject("Tax", "DataSource", cm)
        shipping = ChangeSubject("Shipping", "DataSource", cm)

        # TotalCell should observe all three DataSource subjects
        subjects = cm.subjects_of(cell)
        subject_names = [s.name for s in subjects]
        self.assertEqual(sorted(subject_names), ["Price", "Shipping", "Tax"])

    def test_no_wiring_for_unrelated_type(self):
        cm = DAGChangeManager()
        cell = PureRecordingObserver("TotalCell")

        cm.register_by_type("DataSource", cell)
        ChangeSubject("Config", "Settings", cm)

        # TotalCell should NOT observe Config (different type)
        self.assertEqual(len(cm.subjects_of(cell)), 0)

    def test_notify_reaches_type_subscribed_observer(self):
        cm = DAGChangeManager()
        cell = PureRecordingObserver("TotalCell")

        cm.register_by_type("DataSource", cell)
        price = ChangeSubject("Price", "DataSource", cm)

        price.notify()

        self.assertEqual(cell.updates, [("Price", "DataSource")])

    def test_notify_preserves_source_subject(self):
        cm = DAGChangeManager()
        cell = PureRecordingObserver("TotalCell")

        cm.register_by_type("DataSource", cell)
        price = ChangeSubject("Price", "DataSource", cm)
        tax = ChangeSubject("Tax", "DataSource", cm)

        price.notify()
        tax.notify()

        self.assertEqual(cell.updates, [
            ("Price", "DataSource"),
            ("Tax", "DataSource"),
        ])


class RegisterByTypeAfterSubjectsTestCase(unittest.TestCase):
    """
    Scenario 2: register_by_type AFTER subjects already exist.

    Edges are created immediately for existing subjects.
    """

    def test_wiring_to_existing_subjects(self):
        cm = DAGChangeManager()

        price = ChangeSubject("Price", "DataSource", cm)
        tax = ChangeSubject("Tax", "DataSource", cm)

        audit = PureRecordingObserver("AuditLog")
        cm.register_by_type("DataSource", audit)

        # AuditLog should already be wired to Price and Tax
        subjects = cm.subjects_of(audit)
        subject_names = [s.name for s in subjects]
        self.assertEqual(sorted(subject_names), ["Price", "Tax"])

    def test_notify_after_late_subscription(self):
        cm = DAGChangeManager()

        shipping = ChangeSubject("Shipping", "DataSource", cm)

        cell = PureRecordingObserver("TotalCell")
        cm.register_by_type("DataSource", cell)

        audit = PureRecordingObserver("AuditLog")
        cm.register_by_type("DataSource", audit)

        shipping.notify()

        self.assertEqual(cell.updates, [("Shipping", "DataSource")])
        self.assertEqual(audit.updates, [("Shipping", "DataSource")])


class TypeBasedPlusInstanceBasedDAGTestCase(unittest.TestCase):
    """
    Scenario 3: Type-based + Instance-based + DAG.

      [Sensor1]  [Sensor2]   <- type "Sensor", appear dynamically
          \\        /
        [Aggregator]          <- register_by_type("Sensor")
             |
        [Dashboard]           <- register(Aggregator, Dashboard)
    """

    def test_dag_cascade(self):
        cm = DAGChangeManager()

        agg = RecordingObserver("Aggregator", "Aggregator", cm)
        dash = RecordingObserver("Dashboard", "Dashboard", cm)

        cm.register_by_type("Sensor", agg)
        cm.register(agg, dash)

        s1 = ChangeSubject("Sensor1", "Sensor", cm)
        s1.notify()

        # Both Aggregator and Dashboard should be notified
        self.assertEqual(len(agg.updates), 1)
        self.assertEqual(len(dash.updates), 1)
        # Both receive the original source
        self.assertEqual(agg.updates[0], ("Sensor1", "Sensor"))
        self.assertEqual(dash.updates[0], ("Sensor1", "Sensor"))

    def test_topological_order_in_dag(self):
        order = []

        class OrderObserver(ChangeObserver):
            def __init__(self, name_, subject_type, cm_, order_list):
                super().__init__(name_, subject_type, cm_)
                self._order_list = order_list

            def update(self, subject):
                self._order_list.append(self.name)

        cm = DAGChangeManager()
        agg = OrderObserver("Aggregator", "Aggregator", cm, order)
        dash = OrderObserver("Dashboard", "Dashboard", cm, order)

        cm.register_by_type("Sensor", agg)
        cm.register(agg, dash)

        ChangeSubject("Sensor1", "Sensor", cm)
        ChangeSubject("Sensor2", "Sensor", cm)

        # Notify from Sensor1 — Aggregator before Dashboard
        ChangeSubject.__dict__  # force nothing
        cm.notify(cm._subjects["Sensor"][0])
        self.assertLess(order.index("Aggregator"), order.index("Dashboard"))

    def test_new_sensor_auto_wired(self):
        cm = DAGChangeManager()
        agg = RecordingObserver("Aggregator", "Aggregator", cm)

        cm.register_by_type("Sensor", agg)

        s1 = ChangeSubject("Sensor1", "Sensor", cm)
        s2 = ChangeSubject("Sensor2", "Sensor", cm)

        # Aggregator should observe both sensors
        subjects = cm.subjects_of(agg)
        subject_names = [s.name for s in subjects]
        self.assertIn("Sensor1", subject_names)
        self.assertIn("Sensor2", subject_names)


class RemoveSubjectTestCase(unittest.TestCase):
    """Scenario 4: remove_subject — auto-cleanup of edges."""

    def test_remove_subject_cleans_edges(self):
        cm = DAGChangeManager()
        agg = RecordingObserver("Aggregator", "Aggregator", cm)

        cm.register_by_type("Sensor", agg)

        s1 = ChangeSubject("Sensor1", "Sensor", cm)
        s2 = ChangeSubject("Sensor2", "Sensor", cm)

        self.assertEqual(len(cm.observers_of(s1)), 1)

        cm.remove_subject(s1)

        self.assertEqual(len(cm.observers_of(s1)), 0)
        # s2 still has its edge
        self.assertEqual(len(cm.observers_of(s2)), 1)

    def test_notify_after_remove(self):
        cm = DAGChangeManager()
        agg = RecordingObserver("Aggregator", "Aggregator", cm)

        cm.register_by_type("Sensor", agg)

        s1 = ChangeSubject("Sensor1", "Sensor", cm)
        s2 = ChangeSubject("Sensor2", "Sensor", cm)

        cm.remove_subject(s1)

        s2.notify()
        self.assertEqual(len(agg.updates), 1)
        self.assertEqual(agg.updates[0], ("Sensor2", "Sensor"))


class UnregisterByTypeTestCase(unittest.TestCase):
    """Scenario 5: unregister_by_type — removes type binding and auto-edges."""

    def test_unregister_by_type_removes_auto_edges(self):
        cm = DAGChangeManager()
        agg = RecordingObserver("Aggregator", "Aggregator", cm)

        cm.register_by_type("Sensor", agg)

        s1 = ChangeSubject("Sensor1", "Sensor", cm)
        s2 = ChangeSubject("Sensor2", "Sensor", cm)

        self.assertEqual(len(cm.observers_of(s1)), 1)
        self.assertEqual(len(cm.observers_of(s2)), 1)

        cm.unregister_by_type("Sensor", agg)

        self.assertEqual(len(cm.observers_of(s1)), 0)
        self.assertEqual(len(cm.observers_of(s2)), 0)

    def test_unregister_by_type_does_not_affect_instance_edges(self):
        cm = DAGChangeManager()
        agg = RecordingObserver("Aggregator", "Aggregator", cm)
        dash = RecordingObserver("Dashboard", "Dashboard", cm)

        cm.register_by_type("Sensor", agg)
        cm.register(agg, dash)  # instance-based edge

        ChangeSubject("Sensor1", "Sensor", cm)

        cm.unregister_by_type("Sensor", agg)

        # Instance edge Aggregator -> Dashboard should still exist
        self.assertEqual(len(cm.observers_of(agg)), 1)
        self.assertIs(cm.observers_of(agg)[0], dash)

    def test_no_auto_wiring_after_unregister(self):
        cm = DAGChangeManager()
        agg = RecordingObserver("Aggregator", "Aggregator", cm)

        cm.register_by_type("Sensor", agg)
        cm.unregister_by_type("Sensor", agg)

        # New sensor should NOT be wired to Aggregator
        s = ChangeSubject("NewSensor", "Sensor", cm)
        self.assertEqual(len(cm.observers_of(s)), 0)


class SelfSubscriptionPreventionTestCase(unittest.TestCase):
    """Observer should not be subscribed to itself via type-based wiring."""

    def test_no_self_subscription(self):
        cm = DAGChangeManager()

        # Aggregator is both a Subject (type "Sensor") and wants to observe "Sensor"
        agg = RecordingObserver("Aggregator", "Sensor", cm)
        cm.register_by_type("Sensor", agg)

        # Aggregator should NOT observe itself
        subjects = cm.subjects_of(agg)
        for s in subjects:
            self.assertIsNot(s, agg)


class MixedEdgesTestCase(unittest.TestCase):
    """Instance-based and type-based edges coexist correctly."""

    def test_mixed_edges_in_topo_sort(self):
        order = []

        class OrderObserver(ChangeObserver):
            def __init__(self, name_, subject_type, cm_, order_list):
                super().__init__(name_, subject_type, cm_)
                self._order_list = order_list

            def update(self, subject):
                self._order_list.append(self.name)

        cm = DAGChangeManager()
        agg = OrderObserver("Aggregator", "Aggregator", cm, order)
        dash = OrderObserver("Dashboard", "Dashboard", cm, order)

        # Type-based: Aggregator observes all Sensors
        cm.register_by_type("Sensor", agg)
        # Instance-based: Dashboard observes Aggregator
        cm.register(agg, dash)

        s1 = ChangeSubject("Sensor1", "Sensor", cm)

        s1.notify()

        # Aggregator before Dashboard
        self.assertEqual(order, ["Aggregator", "Dashboard"])


if __name__ == '__main__':
    unittest.main()
