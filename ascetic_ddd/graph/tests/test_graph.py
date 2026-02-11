"""Unit tests for stable_toposort graph utility."""

import unittest

from ..graph import stable_toposort


class TestStableToposortBasic(unittest.TestCase):

    def test_empty_graph(self):
        result = stable_toposort([], {}, key=lambda n: 0)
        self.assertEqual(result, [])

    def test_single_node_no_edges(self):
        result = stable_toposort(['a'], {}, key=lambda n: 0)
        self.assertEqual(result, ['a'])

    def test_two_nodes_one_edge(self):
        """a -> b means a before b."""
        result = stable_toposort(
            ['a', 'b'], {'a': {'b'}}, key=lambda n: 0,
        )
        self.assertEqual(result, ['a', 'b'])

    def test_two_nodes_reverse_input_order(self):
        """b -> a, nodes listed as [a, b]."""
        result = stable_toposort(
            ['a', 'b'], {'b': {'a'}}, key=lambda n: 0,
        )
        self.assertEqual(result, ['b', 'a'])

    def test_linear_chain(self):
        """a -> b -> c."""
        result = stable_toposort(
            ['a', 'b', 'c'],
            {'a': {'b'}, 'b': {'c'}},
            key=lambda n: 0,
        )
        self.assertEqual(result, ['a', 'b', 'c'])

    def test_linear_chain_reversed_input(self):
        """a -> b -> c, nodes given as [c, b, a]."""
        result = stable_toposort(
            ['c', 'b', 'a'],
            {'a': {'b'}, 'b': {'c'}},
            key=lambda n: 0,
        )
        self.assertEqual(result, ['a', 'b', 'c'])


class TestStableToposortDiamond(unittest.TestCase):

    def test_diamond_dependency(self):
        """a -> b,c / b -> d / c -> d."""
        result = stable_toposort(
            ['a', 'b', 'c', 'd'],
            {'a': {'b', 'c'}, 'b': {'d'}, 'c': {'d'}},
            key=lambda n: 0,
        )
        self.assertEqual(result[0], 'a')
        self.assertEqual(result[-1], 'd')
        # b before c because order_index(b)=1 < order_index(c)=2
        self.assertEqual(result, ['a', 'b', 'c', 'd'])

    def test_diamond_key_overrides_input_order(self):
        """a -> b,c / b -> d / c -> d.  key puts c before b."""
        priorities = {'a': 0, 'b': 2, 'c': 1, 'd': 3}
        result = stable_toposort(
            ['a', 'b', 'c', 'd'],
            {'a': {'b', 'c'}, 'b': {'d'}, 'c': {'d'}},
            key=lambda n: priorities[n],
        )
        self.assertEqual(result, ['a', 'c', 'b', 'd'])


class TestStableToposortKeyTieBreaking(unittest.TestCase):

    def test_key_determines_order_no_edges(self):
        """No edges — key alone determines output order."""
        priorities = {'c': 0, 'a': 1, 'b': 2}
        result = stable_toposort(
            ['a', 'b', 'c'], {}, key=lambda n: priorities[n],
        )
        self.assertEqual(result, ['c', 'a', 'b'])

    def test_key_breaks_tie_among_ready_nodes(self):
        """a -> c, b -> c.  Both a,b ready; key(b) < key(a)."""
        priorities = {'a': 2, 'b': 1, 'c': 0}
        result = stable_toposort(
            ['a', 'b', 'c'],
            {'a': {'c'}, 'b': {'c'}},
            key=lambda n: priorities[n],
        )
        self.assertEqual(result, ['b', 'a', 'c'])


class TestStableToposortStability(unittest.TestCase):

    def test_same_key_preserves_input_order(self):
        """Equal keys — original list order is kept."""
        result = stable_toposort(
            ['x', 'y', 'z'], {}, key=lambda n: 0,
        )
        self.assertEqual(result, ['x', 'y', 'z'])

    def test_same_key_preserves_reversed_input_order(self):
        result = stable_toposort(
            ['z', 'y', 'x'], {}, key=lambda n: 0,
        )
        self.assertEqual(result, ['z', 'y', 'x'])

    def test_deterministic_over_multiple_runs(self):
        nodes = ['d', 'c', 'b', 'a']
        edges = {'a': {'b'}, 'c': {'d'}}
        priorities = {'a': 1, 'b': 2, 'c': 1, 'd': 2}
        results = [
            stable_toposort(nodes, edges, key=lambda n: priorities[n])
            for _ in range(10)
        ]
        for i in range(1, 10):
            self.assertEqual(results[i], results[0])


class TestStableToposortCycles(unittest.TestCase):

    def test_self_loop_appended_as_remaining(self):
        """a -> a.  indegree never reaches 0; appended as remaining."""
        result = stable_toposort(
            ['a'], {'a': {'a'}}, key=lambda n: 0,
        )
        self.assertEqual(result, ['a'])

    def test_two_node_cycle(self):
        """a <-> b.  Both stuck in cycle, appended by key then input order."""
        result = stable_toposort(
            ['a', 'b'],
            {'a': {'b'}, 'b': {'a'}},
            key=lambda n: 0,
        )
        self.assertEqual(result, ['a', 'b'])

    def test_cycle_remaining_ordered_by_key(self):
        """a <-> b.  key(b) < key(a) — b comes first in remaining."""
        priorities = {'a': 2, 'b': 1}
        result = stable_toposort(
            ['a', 'b'],
            {'a': {'b'}, 'b': {'a'}},
            key=lambda n: priorities[n],
        )
        self.assertEqual(result, ['b', 'a'])

    def test_cycle_with_acyclic_prefix(self):
        """a -> b -> c -> b.  a is processed normally; b,c form a cycle."""
        result = stable_toposort(
            ['a', 'b', 'c'],
            {'a': {'b'}, 'b': {'c'}, 'c': {'b'}},
            key=lambda n: 0,
        )
        self.assertEqual(result[0], 'a')
        self.assertEqual(set(result), {'a', 'b', 'c'})

    def test_triangular_cycle(self):
        """a -> b -> c -> a."""
        result = stable_toposort(
            ['a', 'b', 'c'],
            {'a': {'b'}, 'b': {'c'}, 'c': {'a'}},
            key=lambda n: 0,
        )
        self.assertEqual(len(result), 3)
        self.assertEqual(set(result), {'a', 'b', 'c'})

    def test_cycle_mixed_with_free_nodes(self):
        """x (free) / a <-> b (cycle) / y (free)."""
        result = stable_toposort(
            ['x', 'a', 'b', 'y'],
            {'a': {'b'}, 'b': {'a'}},
            key=lambda n: 0,
        )
        # x and y processed normally (indegree 0), a and b appended
        self.assertEqual(result[:2], ['x', 'y'])
        self.assertEqual(set(result[2:]), {'a', 'b'})


class TestStableToposortEdgeCases(unittest.TestCase):

    def test_edges_to_unknown_nodes_ignored(self):
        """Edge a -> z, but z not in nodes."""
        result = stable_toposort(
            ['a', 'b'], {'a': {'z', 'b'}}, key=lambda n: 0,
        )
        self.assertEqual(result, ['a', 'b'])

    def test_edges_from_unknown_source_ignored(self):
        """Edge z -> a, but z not in nodes."""
        result = stable_toposort(
            ['a', 'b'], {'z': {'a'}}, key=lambda n: 0,
        )
        self.assertEqual(result, ['a', 'b'])

    def test_integer_nodes(self):
        result = stable_toposort(
            [3, 1, 2], {1: {2}, 2: {3}}, key=lambda n: n,
        )
        self.assertEqual(result, [1, 2, 3])

    def test_all_nodes_independent(self):
        """Five independent nodes — sorted by key then input order."""
        result = stable_toposort(
            ['e', 'd', 'c', 'b', 'a'],
            {},
            key=lambda n: 0,
        )
        self.assertEqual(result, ['e', 'd', 'c', 'b', 'a'])

    def test_complex_graph(self):
        """a -> b,c / b -> d / c -> d / d -> e / f (independent)."""
        result = stable_toposort(
            ['f', 'a', 'b', 'c', 'd', 'e'],
            {'a': {'b', 'c'}, 'b': {'d'}, 'c': {'d'}, 'd': {'e'}},
            key=lambda n: 0,
        )
        # f and a both have indegree 0; f has lower order_index
        self.assertEqual(result[0], 'f')
        self.assertEqual(result[1], 'a')
        self.assertEqual(result[-1], 'e')
        # All dependency constraints satisfied
        for src, dests in {'a': {'b', 'c'}, 'b': {'d'}, 'c': {'d'}, 'd': {'e'}}.items():
            for dst in dests:
                self.assertLess(
                    result.index(src), result.index(dst),
                    '%s should come before %s' % (src, dst),
                )


if __name__ == '__main__':
    unittest.main()
