"""Unit tests for SCC (Strongly Connected Components) detection module."""

import unittest

from ..scc import (
    find_circular_sccs,
    strongly_connected_components,
)


def _to_sorted_result(sccs):
    """Convert SCCs to sorted nested lists for deterministic comparison."""
    return [sorted(scc) for scc in sccs]


class TestStronglyConnectedComponents(unittest.TestCase):

    def test_empty_graph(self):
        """Empty graph."""
        graph = {}
        self.assertEqual(_to_sorted_result(strongly_connected_components(graph)), [])

    def test_single_node_without_edges(self):
        """Graph: a (isolated)."""
        graph = {("a",): set()}
        self.assertEqual(
            _to_sorted_result(strongly_connected_components(graph)),
            [[("a",)]],
        )

    def test_single_node_with_self_loop(self):
        """Graph: a -> a."""
        graph = {("a",): {("a",)}}
        self.assertEqual(
            _to_sorted_result(strongly_connected_components(graph)),
            [[("a",)]],
        )

    def test_bidirectional_edge_pair(self):
        """Graph: a <-> b."""
        graph = {
            ("a",): {("b",)},
            ("b",): {("a",)},
        }
        self.assertEqual(
            _to_sorted_result(strongly_connected_components(graph)),
            [[("a",), ("b",)]],
        )

    def test_triangular_cycle(self):
        """Graph: a -> b -> c -> a."""
        graph = {
            ("a",): {("b",)},
            ("b",): {("c",)},
            ("c",): {("a",)},
        }
        self.assertEqual(
            _to_sorted_result(strongly_connected_components(graph)),
            [[("a",), ("b",), ("c",)]],
        )

    def test_linear_chain(self):
        """Graph: a -> b -> c (acyclic)."""
        graph = {
            ("a",): {("b",)},
            ("b",): {("c",)},
            ("c",): set(),
        }
        self.assertEqual(
            _to_sorted_result(strongly_connected_components(graph)),
            [[("c",)], [("b",)], [("a",)]],
        )

    def test_two_independent_cycles(self):
        """Graph: a <-> b / x <-> y (disconnected)."""
        graph = {
            ("a",): {("b",)},
            ("b",): {("a",)},
            ("x",): {("y",)},
            ("y",): {("x",)},
        }
        self.assertEqual(
            _to_sorted_result(strongly_connected_components(graph)),
            [[("a",), ("b",)], [("x",), ("y",)]],
        )

    def test_edge_only_node(self):
        """Graph: a -> b (b only referenced as edge target)."""
        graph = {
            ("a",): {("b",)},
        }
        self.assertEqual(
            _to_sorted_result(strongly_connected_components(graph)),
            [[("b",)], [("a",)]],
        )

    def test_nested_cycle(self):
        """Graph: a -> b,d / b <-> c / d (isolated)."""
        graph = {
            ("a",): {("b",), ("d",)},
            ("b",): {("c",)},
            ("c",): {("b",)},
            ("d",): set(),
        }
        self.assertEqual(
            _to_sorted_result(strongly_connected_components(graph)),
            [[("b",), ("c",)], [("d",)], [("a",)]],
        )

    def test_deterministic_results(self):
        """Graph: z <-> y / a <-> b (verify determinism across 5 runs)."""
        graph = {
            ("z",): {("y",)},
            ("y",): {("z",)},
            ("a",): {("b",)},
            ("b",): {("a",)},
        }
        results = [
            _to_sorted_result(strongly_connected_components(graph))
            for _ in range(5)
        ]
        for i in range(1, 5):
            self.assertEqual(results[i], results[0])

    def test_multiple_unvisited_neighbors(self):
        """Graph: a -> b,c,d / b -> a / c -> a / d (isolated)."""
        graph = {
            ("a",): {("b",), ("c",), ("d",)},
            ("b",): {("a",)},
            ("c",): {("a",)},
            ("d",): set(),
        }
        self.assertEqual(
            _to_sorted_result(strongly_connected_components(graph)),
            [[("d",)], [("a",), ("b",), ("c",)]],
        )

    def test_on_stack_neighbor(self):
        """Graph: a -> b -> c,d / c -> a / d -> b."""
        graph = {
            ("a",): {("b",)},
            ("b",): {("c",), ("d",)},
            ("c",): {("a",)},
            ("d",): {("b",)},
        }
        self.assertEqual(
            _to_sorted_result(strongly_connected_components(graph)),
            [[("a",), ("b",), ("c",), ("d",)]],
        )

    def test_deep_graph_iterative(self):
        """100-node chain with terminal cycle n98 <-> n99."""
        graph = {}
        for i in range(99):
            graph[("n%s" % i,)] = {("n%s" % (i + 1),)}
        graph[("n99",)] = {("n98",)}

        result = strongly_connected_components(graph)
        multi_node_sccs = [scc for scc in result if len(scc) > 1]
        self.assertEqual(
            _to_sorted_result(multi_node_sccs),
            [[("n98",), ("n99",)]],
        )

    def test_realistic_module_path_tuples(self):
        """Graph: (pkg, __init__) <-> (pkg, issuing)."""
        graph = {
            ("pkg", "__init__"): {("pkg", "issuing")},
            ("pkg", "issuing"): {("pkg", "__init__")},
        }
        self.assertEqual(
            _to_sorted_result(strongly_connected_components(graph)),
            [[("pkg", "__init__"), ("pkg", "issuing")]],
        )

    def test_skips_indexed_neighbors(self):
        """Graph: a -> b,c / b -> c / c (isolated)."""
        graph = {
            ("a",): {("b",), ("c",)},
            ("b",): {("c",)},
            ("c",): set(),
        }
        self.assertEqual(
            _to_sorted_result(strongly_connected_components(graph)),
            [[("c",)], [("b",)], [("a",)]],
        )

    def test_scc_root_detection(self):
        """Graph: a -> b,c / b -> d / c -> d / d -> a."""
        graph = {
            ("a",): {("b",), ("c",)},
            ("b",): {("d",)},
            ("c",): {("d",)},
            ("d",): {("a",)},
        }
        self.assertEqual(
            _to_sorted_result(strongly_connected_components(graph)),
            [[("a",), ("b",), ("c",), ("d",)]],
        )

    def test_later_on_stack_neighbor(self):
        """Graph: a -> b,c,d / b -> c / c -> a / d (isolated)."""
        graph = {
            ("a",): {("b",), ("c",), ("d",)},
            ("b",): {("c",)},
            ("c",): {("a",)},
            ("d",): set(),
        }
        self.assertEqual(
            _to_sorted_result(strongly_connected_components(graph)),
            [[("d",)], [("a",), ("b",), ("c",)]],
        )

    def test_visited_not_on_stack_neighbor(self):
        """Graph: a -> x / b -> a,x / x (isolated)."""
        graph = {
            ("a",): {("x",)},
            ("b",): {("a",), ("x",)},
            ("x",): set(),
        }
        self.assertEqual(
            _to_sorted_result(strongly_connected_components(graph)),
            [[("x",)], [("a",)], [("b",)]],
        )

    def test_exhausts_neighbors_finds_root(self):
        """Graph: a -> b / b (isolated)."""
        graph = {
            ("a",): {("b",)},
            ("b",): set(),
        }
        self.assertEqual(
            _to_sorted_result(strongly_connected_components(graph)),
            [[("b",)], [("a",)]],
        )

    def test_multi_node_scc_pops_all_members(self):
        """Graph: a -> b -> c -> d -> a (4-node cycle)."""
        graph = {
            ("a",): {("b",)},
            ("b",): {("c",)},
            ("c",): {("d",)},
            ("d",): {("a",)},
        }
        self.assertEqual(
            _to_sorted_result(strongly_connected_components(graph)),
            [[("a",), ("b",), ("c",), ("d",)]],
        )

    def test_extraction_with_multiple_pops(self):
        """Graph: a -> b -> c -> d -> e -> a (5-node cycle)."""
        graph = {
            ("a",): {("b",)},
            ("b",): {("c",)},
            ("c",): {("d",)},
            ("d",): {("e",)},
            ("e",): {("a",)},
        }
        self.assertEqual(
            _to_sorted_result(strongly_connected_components(graph)),
            [[("a",), ("b",), ("c",), ("d",), ("e",)]],
        )

    def test_multiple_returns_in_call_stack(self):
        """Graph: a -> b,c / b -> d / c -> d / d -> e / e -> a."""
        graph = {
            ("a",): {("b",), ("c",)},
            ("b",): {("d",)},
            ("c",): {("d",)},
            ("d",): {("e",)},
            ("e",): {("a",)},
        }
        self.assertEqual(
            _to_sorted_result(strongly_connected_components(graph)),
            [[("a",), ("b",), ("c",), ("d",), ("e",)]],
        )


class TestFindCircularSccs(unittest.TestCase):

    def test_empty_graph(self):
        """Empty graph."""
        graph = {}
        self.assertEqual(_to_sorted_result(find_circular_sccs(graph)), [])

    def test_acyclic_graph(self):
        """Graph: a -> b -> c (acyclic)."""
        graph = {
            ("a",): {("b",)},
            ("b",): {("c",)},
            ("c",): set(),
        }
        self.assertEqual(_to_sorted_result(find_circular_sccs(graph)), [])

    def test_self_loop_detected(self):
        """Graph: a -> a."""
        graph = {("a",): {("a",)}}
        self.assertEqual(
            _to_sorted_result(find_circular_sccs(graph)),
            [[("a",)]],
        )

    def test_single_node_without_self_loop(self):
        """Graph: a (isolated)."""
        graph = {("a",): set()}
        self.assertEqual(_to_sorted_result(find_circular_sccs(graph)), [])

    def test_bidirectional_pair_detected(self):
        """Graph: a <-> b."""
        graph = {
            ("a",): {("b",)},
            ("b",): {("a",)},
        }
        self.assertEqual(
            _to_sorted_result(find_circular_sccs(graph)),
            [[("a",), ("b",)]],
        )

    def test_multiple_independent_cycles_detected(self):
        """Graph: a <-> b / x <-> y (disconnected)."""
        graph = {
            ("a",): {("b",)},
            ("b",): {("a",)},
            ("x",): {("y",)},
            ("y",): {("x",)},
        }
        self.assertEqual(
            _to_sorted_result(find_circular_sccs(graph)),
            [[("a",), ("b",)], [("x",), ("y",)]],
        )

    def test_results_sorted_by_minimum_element(self):
        """Graph: z <-> y / a <-> b (verify sorted by min element)."""
        graph = {
            ("z",): {("y",)},
            ("y",): {("z",)},
            ("a",): {("b",)},
            ("b",): {("a",)},
        }
        result = find_circular_sccs(graph)
        self.assertLess(min(result[0]), min(result[1]))
        self.assertEqual(
            _to_sorted_result(result),
            [[("a",), ("b",)], [("y",), ("z",)]],
        )

    def test_filters_acyclic_sccs(self):
        """Graph: a <-> b / c -> d (mixed cyclic and acyclic)."""
        graph = {
            ("a",): {("b",)},
            ("b",): {("a",)},
            ("c",): {("d",)},
            ("d",): set(),
        }
        self.assertEqual(
            _to_sorted_result(find_circular_sccs(graph)),
            [[("a",), ("b",)]],
        )

    def test_edge_only_node_not_circular(self):
        """Graph: a -> b (b only referenced as edge)."""
        graph = {
            ("a",): {("b",)},
        }
        self.assertEqual(_to_sorted_result(find_circular_sccs(graph)), [])

    def test_stripe_api_like_pattern(self):
        """Graph: () <-> (issuing,)."""
        graph = {
            (): {("issuing",)},
            ("issuing",): {()},
        }
        self.assertEqual(
            _to_sorted_result(find_circular_sccs(graph)),
            [[(), ("issuing",)]],
        )

    def test_triangular_cycle_with_external_edge(self):
        """Graph: a -> b,x / b -> c / c -> a / x (isolated)."""
        graph = {
            ("a",): {("b",), ("x",)},
            ("b",): {("c",)},
            ("c",): {("a",)},
            ("x",): set(),
        }
        self.assertEqual(
            _to_sorted_result(find_circular_sccs(graph)),
            [[("a",), ("b",), ("c",)]],
        )

    def test_iteration_over_multiple_sccs(self):
        """Graph: a <-> b / c (isolated) / d -> d / e -> f -> g -> e."""
        graph = {
            ("a",): {("b",)},
            ("b",): {("a",)},
            ("c",): set(),
            ("d",): {("d",)},
            ("e",): {("f",)},
            ("f",): {("g",)},
            ("g",): {("e",)},
        }
        result = find_circular_sccs(graph)
        sizes = sorted([len(scc) for scc in result])
        self.assertEqual(sizes, [1, 2, 3])
        self.assertEqual(
            _to_sorted_result(result),
            [[("a",), ("b",)], [("d",)], [("e",), ("f",), ("g",)]],
        )

    def test_many_single_node_sccs_with_self_loops(self):
        """Graph: a -> a / b -> b / c -> c / d -> d."""
        graph = {
            ("a",): {("a",)},
            ("b",): {("b",)},
            ("c",): {("c",)},
            ("d",): {("d",)},
        }
        result = find_circular_sccs(graph)
        self.assertEqual(len(result), 4)
        self.assertEqual(
            _to_sorted_result(result),
            [[("a",)], [("b",)], [("c",)], [("d",)]],
        )

    def test_mixed_scc_sizes_iteration(self):
        """Graph: a (isolated) / b -> b / c <-> d / e -> f -> g -> h -> e."""
        graph = {
            ("a",): set(),
            ("b",): {("b",)},
            ("c",): {("d",)},
            ("d",): {("c",)},
            ("e",): {("f",)},
            ("f",): {("g",)},
            ("g",): {("h",)},
            ("h",): {("e",)},
        }
        result = find_circular_sccs(graph)
        self.assertEqual(len(result), 3)
        sizes = sorted([len(scc) for scc in result])
        self.assertEqual(sizes, [1, 2, 4])


if __name__ == '__main__':
    unittest.main()
