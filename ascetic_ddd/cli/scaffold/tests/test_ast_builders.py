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


if __name__ == '__main__':
    unittest.main()
