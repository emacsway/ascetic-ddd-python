import ast
import unittest

from ascetic_ddd.cli.scaffold.ast_merge import merge_modules


class TestMergeModules(unittest.TestCase):
    """Tests for ast_merge.merge_modules."""

    def _merge(self, existing_src, generated_src):
        existing = ast.parse(existing_src)
        generated = ast.parse(generated_src)
        merge_modules(existing, generated)
        ast.fix_missing_locations(existing)
        return ast.unparse(existing)

    def test_add_missing_import(self):
        existing = 'from foo import Bar'
        generated = 'from foo import Bar, Baz'
        result = self._merge(existing, generated)
        self.assertIn('Bar', result)
        self.assertIn('Baz', result)

    def test_add_new_import_module(self):
        existing = 'from foo import Bar'
        generated = 'from baz import Qux'
        result = self._merge(existing, generated)
        self.assertIn('from foo import Bar', result)
        self.assertIn('from baz import Qux', result)

    def test_add_missing_class(self):
        existing = 'class Foo:\n    pass'
        generated = 'class Bar:\n    pass'
        result = self._merge(existing, generated)
        self.assertIn('class Foo:', result)
        self.assertIn('class Bar:', result)

    def test_add_missing_method(self):
        existing = (
            'class Foo:\n'
            '    def bar(self):\n'
            '        return 1'
        )
        generated = (
            'class Foo:\n'
            '    def bar(self):\n'
            '        return 2\n'
            '    def baz(self):\n'
            '        return 3'
        )
        result = self._merge(existing, generated)
        self.assertIn('def bar(self)', result)
        self.assertIn('def baz(self)', result)
        # Existing body preserved (return 1, not return 2)
        self.assertIn('return 1', result)

    def test_add_missing_annotation(self):
        existing = (
            'class Foo:\n'
            '    x: int\n'
            '    def __init__(self):\n'
            '        pass'
        )
        generated = (
            'class Foo:\n'
            '    x: int\n'
            '    y: str\n'
            '    def __init__(self):\n'
            '        pass'
        )
        result = self._merge(existing, generated)
        self.assertIn('x: int', result)
        self.assertIn('y: str', result)

    def test_merge_init_params(self):
        existing = (
            'class Foo:\n'
            '    def __init__(self, x):\n'
            '        self._x = x'
        )
        generated = (
            'class Foo:\n'
            '    def __init__(self, x, y):\n'
            '        self._x = x\n'
            '        self._y = y'
        )
        result = self._merge(existing, generated)
        self.assertIn('self, x, y', result)
        self.assertIn('self._y = y', result)

    def test_preserve_user_method(self):
        existing = (
            'class Foo:\n'
            '    def user_logic(self):\n'
            '        return "custom"'
        )
        generated = (
            'class Foo:\n'
            '    def generated(self):\n'
            '        pass'
        )
        result = self._merge(existing, generated)
        self.assertIn('def user_logic(self)', result)
        self.assertIn('custom', result)
        self.assertIn('def generated(self)', result)

    def test_merge_all_list(self):
        existing = "__all__ = ['Foo', 'Bar']"
        generated = "__all__ = ['Foo', 'Baz']"
        result = self._merge(existing, generated)
        self.assertIn("'Foo'", result)
        self.assertIn("'Bar'", result)
        self.assertIn("'Baz'", result)

    def test_strip_pass_when_members_added(self):
        existing = 'class Foo:\n    pass'
        generated = (
            'class Foo:\n'
            '    def bar(self):\n'
            '        return 1'
        )
        result = self._merge(existing, generated)
        self.assertIn('def bar(self)', result)
        # pass should be removed since class now has real members
        self.assertNotIn('pass', result)

    def test_no_duplicate_imports(self):
        existing = 'from foo import Bar'
        generated = 'from foo import Bar'
        result = self._merge(existing, generated)
        # Should not duplicate
        self.assertEqual(result.count('Bar'), 1)

    def test_no_duplicate_methods(self):
        existing = (
            'class Foo:\n'
            '    def bar(self):\n'
            '        return 1'
        )
        generated = (
            'class Foo:\n'
            '    def bar(self):\n'
            '        return 2'
        )
        result = self._merge(existing, generated)
        # Should only have one bar, with existing body
        self.assertEqual(result.count('def bar'), 1)
        self.assertIn('return 1', result)


if __name__ == '__main__':
    unittest.main()
