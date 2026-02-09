import unittest

from ascetic_ddd.dag_change.change_subject import ChangeSubject
from ascetic_ddd.dag_change.change_observer import ChangeObserver
from ascetic_ddd.dag_change.dag_change_manager import DAGChangeManager
from ascetic_ddd.dag_change.simple_change_manager import SimpleChangeManager
from ascetic_ddd.dag_change.interfaces import IChangeSubject


class RecordingObserver(ChangeObserver):
    """Observer that records update calls for test assertions."""

    def __init__(self, name, cm):
        super().__init__(name, cm)
        self.updates = []

    def update(self, subject: IChangeSubject) -> None:
        self.updates.append(subject.name)


class DiamondDependencyTestCase(unittest.TestCase):
    """
    Test 1: Diamond dependency + DAG propagation.

         [A]
        /   \\
      [B]   [C]
        \\   /
         [D]
          |
         [E]

    D is reachable from A via two paths.
    DAGChangeManager must notify D exactly once.
    """

    def test_each_observer_notified_exactly_once(self):
        cm = DAGChangeManager()

        a = ChangeSubject("A", cm)
        b = RecordingObserver("B", cm)
        c = RecordingObserver("C", cm)
        d = RecordingObserver("D", cm)
        e = RecordingObserver("E", cm)

        cm.register(a, b)
        cm.register(a, c)
        cm.register(b, d)
        cm.register(c, d)  # diamond
        cm.register(d, e)

        a.notify()

        self.assertEqual(len(b.updates), 1)
        self.assertEqual(len(c.updates), 1)
        self.assertEqual(len(d.updates), 1)  # exactly once, not twice
        self.assertEqual(len(e.updates), 1)

    def test_topological_order(self):
        cm = DAGChangeManager()

        a = ChangeSubject("A", cm)
        b = RecordingObserver("B", cm)
        c = RecordingObserver("C", cm)
        d = RecordingObserver("D", cm)
        e = RecordingObserver("E", cm)

        cm.register(a, b)
        cm.register(a, c)
        cm.register(b, d)
        cm.register(c, d)
        cm.register(d, e)

        # Collect notification order via a shared list
        order = []

        class OrderRecordingObserver(ChangeObserver):
            def __init__(self, name_, cm_, order_list):
                super().__init__(name_, cm_)
                self._order_list = order_list

            def update(self, subject):
                self._order_list.append(self.name)

        cm2 = DAGChangeManager()
        a2 = ChangeSubject("A", cm2)
        b2 = OrderRecordingObserver("B", cm2, order)
        c2 = OrderRecordingObserver("C", cm2, order)
        d2 = OrderRecordingObserver("D", cm2, order)
        e2 = OrderRecordingObserver("E", cm2, order)

        cm2.register(a2, b2)
        cm2.register(a2, c2)
        cm2.register(b2, d2)
        cm2.register(c2, d2)
        cm2.register(d2, e2)

        a2.notify()

        # B and C must come before D, D must come before E
        self.assertLess(order.index("B"), order.index("D"))
        self.assertLess(order.index("C"), order.index("D"))
        self.assertLess(order.index("D"), order.index("E"))

    def test_original_subject_passed_to_update(self):
        cm = DAGChangeManager()

        a = ChangeSubject("A", cm)
        b = RecordingObserver("B", cm)
        d = RecordingObserver("D", cm)

        cm.register(a, b)
        cm.register(b, d)

        a.notify()

        # All observers receive the original changed subject name
        self.assertEqual(b.updates, ["A"])
        self.assertEqual(d.updates, ["A"])


class AssociativeLookupTestCase(unittest.TestCase):
    """
    Test 2: GoF point 1 — Associative look-up, zero storage overhead.

    Subjects without observers should not create entries in the deps dict.
    """

    def test_zero_overhead_for_subjects_without_observers(self):
        cm = DAGChangeManager()

        lonely1 = ChangeSubject("Lonely1", cm)
        lonely2 = ChangeSubject("Lonely2", cm)
        popular = ChangeSubject("Popular", cm)
        obs1 = RecordingObserver("Obs1", cm)
        obs2 = RecordingObserver("Obs2", cm)

        cm.register(popular, obs1)
        cm.register(popular, obs2)

        # Only Popular has an entry in deps
        self.assertEqual(len(cm._deps), 1)
        self.assertEqual(len(cm.observers_of(popular)), 2)
        self.assertEqual(len(cm.observers_of(lonely1)), 0)
        self.assertEqual(len(cm.observers_of(lonely2)), 0)

    def test_notify_subject_without_observers(self):
        cm = DAGChangeManager()
        lonely = ChangeSubject("Lonely", cm)

        # Should not raise
        lonely.notify()

    def test_unregister_all_removes_entry(self):
        cm = DAGChangeManager()

        popular = ChangeSubject("Popular", cm)
        obs1 = RecordingObserver("Obs1", cm)
        obs2 = RecordingObserver("Obs2", cm)

        cm.register(popular, obs1)
        cm.register(popular, obs2)
        self.assertEqual(len(cm._deps), 1)

        cm.unregister_all(popular)
        self.assertEqual(len(cm._deps), 0)

    def test_unregister_removes_empty_entries(self):
        cm = DAGChangeManager()

        s = ChangeSubject("S", cm)
        o = RecordingObserver("O", cm)

        cm.register(s, o)
        self.assertIn(s, cm._deps)
        self.assertIn(o, cm._reverse_deps)

        cm.unregister(s, o)
        self.assertNotIn(s, cm._deps)
        self.assertNotIn(o, cm._reverse_deps)


class MultiSubjectObserverTestCase(unittest.TestCase):
    """
    Test 3: GoF point 2 — Observer depending on multiple subjects.

      [Price]  [Tax]  [Shipping]
         \\       |       /
          [ TotalCell ]
    """

    def test_subjects_of_returns_all_dependencies(self):
        cm = DAGChangeManager()

        price = ChangeSubject("Price", cm)
        tax = ChangeSubject("Tax", cm)
        shipping = ChangeSubject("Shipping", cm)
        total = RecordingObserver("TotalCell", cm)

        cm.register(price, total)
        cm.register(tax, total)
        cm.register(shipping, total)

        subjects = cm.subjects_of(total)
        subject_names = [s.name for s in subjects]
        self.assertEqual(subject_names, ["Price", "Tax", "Shipping"])

    def test_update_receives_correct_source(self):
        cm = DAGChangeManager()

        price = ChangeSubject("Price", cm)
        tax = ChangeSubject("Tax", cm)
        total = RecordingObserver("TotalCell", cm)

        cm.register(price, total)
        cm.register(tax, total)

        price.notify()
        self.assertEqual(total.updates, ["Price"])

        total.updates.clear()
        tax.notify()
        self.assertEqual(total.updates, ["Tax"])


class ComplexDAGTestCase(unittest.TestCase):
    """
    Test 4: Multi-subject + Diamond + DAG.

      [Src1]    [Src2]
        |  \\    /  |
        |  [Mid1]  |
        |  /    \\  |
      [Mid2]  [Mid3]
         \\      /
          [Sink]
    """

    def test_complex_dag_each_notified_once(self):
        cm = DAGChangeManager()

        src1 = ChangeSubject("Src1", cm)
        src2 = ChangeSubject("Src2", cm)
        mid1 = RecordingObserver("Mid1", cm)
        mid2 = RecordingObserver("Mid2", cm)
        mid3 = RecordingObserver("Mid3", cm)
        sink = RecordingObserver("Sink", cm)

        cm.register(src1, mid1)
        cm.register(src2, mid1)    # Mid1 observes Src1 and Src2 (multi-subject)
        cm.register(src1, mid2)
        cm.register(mid1, mid2)    # Mid2 observes Src1 and Mid1
        cm.register(mid1, mid3)
        cm.register(src2, mid3)    # Mid3 observes Mid1 and Src2
        cm.register(mid2, sink)
        cm.register(mid3, sink)    # Sink observes Mid2 and Mid3 (diamond)

        src1.notify()

        self.assertEqual(len(mid1.updates), 1)
        self.assertEqual(len(mid2.updates), 1)
        self.assertEqual(len(sink.updates), 1)  # diamond: notified exactly once

    def test_complex_dag_topological_order(self):
        order = []

        class OrderObserver(ChangeObserver):
            def __init__(self, name_, cm_, order_list):
                super().__init__(name_, cm_)
                self._order_list = order_list

            def update(self, subject):
                self._order_list.append(self.name)

        cm = DAGChangeManager()

        src1 = ChangeSubject("Src1", cm)
        src2 = ChangeSubject("Src2", cm)
        mid1 = OrderObserver("Mid1", cm, order)
        mid2 = OrderObserver("Mid2", cm, order)
        mid3 = OrderObserver("Mid3", cm, order)
        sink = OrderObserver("Sink", cm, order)

        cm.register(src1, mid1)
        cm.register(src2, mid1)
        cm.register(src1, mid2)
        cm.register(mid1, mid2)
        cm.register(mid1, mid3)
        cm.register(src2, mid3)
        cm.register(mid2, sink)
        cm.register(mid3, sink)

        src1.notify()

        # Mid1 before Mid2 (Mid2 depends on Mid1)
        self.assertLess(order.index("Mid1"), order.index("Mid2"))
        # Mid1 before Mid3 (Mid3 depends on Mid1)
        # Mid3 may or may not be in affected set depending on reachability from Src1
        # Mid3 IS reachable: Src1 -> Mid1 -> Mid3
        self.assertIn("Mid3", order)
        self.assertLess(order.index("Mid1"), order.index("Mid3"))
        # Mid2 and Mid3 before Sink
        self.assertLess(order.index("Mid2"), order.index("Sink"))
        self.assertLess(order.index("Mid3"), order.index("Sink"))

    def test_multi_subject_introspection(self):
        cm = DAGChangeManager()

        src1 = ChangeSubject("Src1", cm)
        src2 = ChangeSubject("Src2", cm)
        mid1 = RecordingObserver("Mid1", cm)

        cm.register(src1, mid1)
        cm.register(src2, mid1)

        subject_names = [s.name for s in cm.subjects_of(mid1)]
        self.assertEqual(subject_names, ["Src1", "Src2"])


class LinearChainTestCase(unittest.TestCase):
    """A -> B -> C: simple chain, order preserved."""

    def test_linear_chain_order(self):
        order = []

        class OrderObserver(ChangeObserver):
            def __init__(self, name_, cm_, order_list):
                super().__init__(name_, cm_)
                self._order_list = order_list

            def update(self, subject):
                self._order_list.append(self.name)

        cm = DAGChangeManager()

        a = ChangeSubject("A", cm)
        b = OrderObserver("B", cm, order)
        c = OrderObserver("C", cm, order)

        cm.register(a, b)
        cm.register(b, c)

        a.notify()

        self.assertEqual(order, ["B", "C"])


class SingleObserverTestCase(unittest.TestCase):
    """Trivial case: one subject, one observer."""

    def test_single_observer(self):
        cm = DAGChangeManager()

        s = ChangeSubject("S", cm)
        o = RecordingObserver("O", cm)

        cm.register(s, o)
        s.notify()

        self.assertEqual(len(o.updates), 1)
        self.assertEqual(o.updates[0], "S")


class SimpleChangeManagerComparisonTestCase(unittest.TestCase):
    """
    SimpleChangeManager does NOT deduplicate diamond notifications.
    This test documents the difference.
    """

    def test_simple_manager_notifies_per_edge(self):
        cm = SimpleChangeManager()

        a = ChangeSubject("A", cm)
        b = RecordingObserver("B", cm)
        c = RecordingObserver("C", cm)
        d = RecordingObserver("D", cm)

        cm.register(a, b)
        cm.register(a, c)
        # SimpleChangeManager only notifies direct observers
        # It does not traverse the DAG
        a.notify()

        self.assertEqual(len(b.updates), 1)
        self.assertEqual(len(c.updates), 1)
        # D was not registered directly on A
        self.assertEqual(len(d.updates), 0)

    def test_simple_manager_observers_of(self):
        cm = SimpleChangeManager()

        s = ChangeSubject("S", cm)
        o1 = RecordingObserver("O1", cm)
        o2 = RecordingObserver("O2", cm)

        cm.register(s, o1)
        cm.register(s, o2)

        observer_names = [o.name for o in cm.observers_of(s)]
        self.assertEqual(observer_names, ["O1", "O2"])

    def test_simple_manager_subjects_of(self):
        cm = SimpleChangeManager()

        s1 = ChangeSubject("S1", cm)
        s2 = ChangeSubject("S2", cm)
        o = RecordingObserver("O", cm)

        cm.register(s1, o)
        cm.register(s2, o)

        subject_names = [s.name for s in cm.subjects_of(o)]
        self.assertEqual(subject_names, ["S1", "S2"])


if __name__ == '__main__':
    unittest.main()
