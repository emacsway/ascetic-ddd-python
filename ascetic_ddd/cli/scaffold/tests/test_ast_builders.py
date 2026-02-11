import ast
import unittest

from ascetic_ddd.cli.scaffold.ast_builders import (
    build_command,
    build_command_handler,
    build_composite_vo,
    build_composite_vo_exporter,
    build_empty_init,
    build_enum_vo,
    build_identity_vo,
    build_string_vo,
    build_values_init,
)
from ascetic_ddd.cli.scaffold.model import (
    ConstraintsDef,
    DispatchKind,
    FieldDef,
    ValueObjectDef,
    VoKind,
    CommandDef,
)


def _unparse(module):
    ast.fix_missing_locations(module)
    return ast.unparse(module)


class TestBuildEmptyInit(unittest.TestCase):
    def test_empty_module(self):
        module = build_empty_init()
        source = _unparse(module)
        self.assertEqual(source, '')


class TestBuildIdentityVo(unittest.TestCase):
    def test_basic_identity(self):
        vo = ValueObjectDef(
            class_name='ResumeId', snake_name='resume_id',
            kind=VoKind.IDENTITY, base_type='int',
            identity_base_class='IntIdentity',
        )
        source = _unparse(build_identity_vo(vo))
        self.assertIn('class ResumeId(IntIdentity)', source)
        self.assertIn('pass', source)
        self.assertNotIn('ValueError', source)

    def test_required_identity(self):
        vo = ValueObjectDef(
            class_name='UserId', snake_name='user_id',
            kind=VoKind.IDENTITY, base_type='int',
            identity_base_class='IntIdentity',
            constraints=ConstraintsDef(required=True),
        )
        source = _unparse(build_identity_vo(vo))
        self.assertIn('if value is None', source)
        self.assertIn('ValueError', source)
        self.assertIn('IntIdentity', source)


class TestBuildStringVo(unittest.TestCase):
    def test_basic_string(self):
        vo = ValueObjectDef(
            class_name='Title', snake_name='title',
            kind=VoKind.STRING, base_type='str',
        )
        source = _unparse(build_string_vo(vo))
        self.assertIn('class Title:', source)
        self.assertIn('def __eq__', source)
        self.assertIn('def __hash__', source)
        self.assertIn('def export', source)
        self.assertIn("'%s(%r)'", source)

    def test_blank_constraint(self):
        vo = ValueObjectDef(
            class_name='Title', snake_name='title',
            kind=VoKind.STRING, base_type='str',
            constraints=ConstraintsDef(blank=False),
        )
        source = _unparse(build_string_vo(vo))
        self.assertIn('cannot be empty', source)

    def test_max_length_constraint(self):
        vo = ValueObjectDef(
            class_name='Title', snake_name='title',
            kind=VoKind.STRING, base_type='str',
            constraints=ConstraintsDef(max_length=255),
        )
        source = _unparse(build_string_vo(vo))
        self.assertIn('cannot exceed 255 characters', source)

    def test_strip_map(self):
        vo = ValueObjectDef(
            class_name='Title', snake_name='title',
            kind=VoKind.STRING, base_type='str',
            maps=('strip',),
        )
        source = _unparse(build_string_vo(vo))
        self.assertIn('value.strip()', source)


class TestBuildEnumVo(unittest.TestCase):
    def test_enum(self):
        vo = ValueObjectDef(
            class_name='Status', snake_name='status',
            kind=VoKind.ENUM,
            enum_values={'ACTIVE': 'active', 'DRAFT': 'draft'},
        )
        source = _unparse(build_enum_vo(vo))
        self.assertIn('class Status(str, Enum)', source)
        self.assertIn("ACTIVE = 'active'", source)
        self.assertIn("DRAFT = 'draft'", source)
        self.assertIn('def export', source)


class TestBuildCompositeVo(unittest.TestCase):
    def test_composite(self):
        fields = [
            FieldDef(
                name='_amount', param_name='amount',
                type_name='int', is_primitive=True,
                dispatch_kind=DispatchKind.PRIMITIVE,
            ),
            FieldDef(
                name='_currency', param_name='currency',
                type_name='str', is_primitive=True,
                dispatch_kind=DispatchKind.PRIMITIVE,
            ),
        ]
        vo = ValueObjectDef(
            class_name='Money', snake_name='money',
            kind=VoKind.COMPOSITE, fields=fields,
        )
        source = _unparse(build_composite_vo(vo))
        self.assertIn('class IMoneyExporter', source)
        self.assertIn('class Money:', source)
        self.assertIn('self._amount = amount', source)
        self.assertIn('self._currency = currency', source)
        self.assertIn('def export(self, exporter', source)

    def test_composite_exporter(self):
        fields = [
            FieldDef(
                name='_amount', param_name='amount',
                type_name='int', is_primitive=True,
                dispatch_kind=DispatchKind.PRIMITIVE,
            ),
        ]
        vo = ValueObjectDef(
            class_name='Money', snake_name='money',
            kind=VoKind.COMPOSITE, fields=fields,
        )
        source = _unparse(build_composite_vo_exporter(vo, 'app.domain.agg'))
        self.assertIn('class MoneyExporter(IMoneyExporter)', source)
        self.assertIn("self.data['amount'] = value", source)


class TestBuildValuesInit(unittest.TestCase):
    def test_simple_vos(self):
        vos = [
            ValueObjectDef(
                class_name='Title', snake_name='title',
                kind=VoKind.STRING,
            ),
            ValueObjectDef(
                class_name='ResumeId', snake_name='resume_id',
                kind=VoKind.IDENTITY,
            ),
        ]
        source = _unparse(build_values_init(vos, 'app.domain.resume'))
        self.assertIn('from app.domain.resume.values.title import Title',
                       source)
        self.assertIn(
            'from app.domain.resume.values.resume_id import ResumeId',
            source,
        )
        self.assertIn('__all__', source)

    def test_imported_vo(self):
        vos = [
            ValueObjectDef(
                class_name='Money', snake_name='money',
                kind=VoKind.STRING,
                import_path='ascetic_ddd.seedwork.domain.values.money',
            ),
        ]
        source = _unparse(build_values_init(vos, 'app.domain.resume'))
        self.assertIn(
            'from ascetic_ddd.seedwork.domain.values.money import Money',
            source,
        )


class TestBuildCommand(unittest.TestCase):
    def test_command(self):
        cmd = CommandDef(
            class_name='CreateResume', snake_name='create_resume',
            fields=[
                FieldDef(
                    name='title', param_name='title',
                    type_name='str', is_primitive=True,
                ),
                FieldDef(
                    name='user_id', param_name='user_id',
                    type_name='int', is_primitive=True,
                ),
            ],
            command_version=1,
        )
        source = _unparse(build_command(
            cmd, needs_datetime=False, needs_decimal=False,
        ))
        self.assertIn('class CreateResumeCommand:', source)
        self.assertIn('title: str', source)
        self.assertIn('user_id: int', source)
        self.assertIn('command_version: int = 1', source)

    def test_command_handler(self):
        cmd = CommandDef(
            class_name='CreateResume', snake_name='create_resume',
        )
        source = _unparse(build_command_handler(cmd, 'app.commands'))
        self.assertIn('class CreateResumeCommandHandler:', source)
        self.assertIn('async def __call__', source)
        self.assertIn('CreateResumeCommand', source)


class TestMergeModules(unittest.TestCase):
    """Tests for ast_merge.merge_modules."""

    def _merge(self, existing_src, generated_src):
        from ascetic_ddd.cli.scaffold.ast_merge import merge_modules
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
