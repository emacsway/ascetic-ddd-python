import ast

from ascetic_ddd.cli.scaffold.model import DispatchKind, VoKind
from ascetic_ddd.cli.scaffold.renderer import _singularize


# --- Low-level AST helpers ---


def _name(id):
    return ast.Name(id=id)


def _const(value):
    return ast.Constant(value=value)


def _attr(obj, attr_name):
    return ast.Attribute(value=obj, attr=attr_name)


def _self_attr(attr_name):
    return _attr(_name('self'), attr_name)


def _call(func, args=None, keywords=None):
    return ast.Call(func=func, args=args or [], keywords=keywords or [])


def _import(name):
    return ast.Import(names=[ast.alias(name=name)])


def _import_from(module, names):
    return ast.ImportFrom(
        module=module,
        names=[ast.alias(name=n) for n in names],
        level=0,
    )


def _simple_args(names):
    """Build ast.arguments with positional args from name strings."""
    return ast.arguments(
        posonlyargs=[],
        args=[ast.arg(arg=n) for n in names],
        vararg=None,
        kwonlyargs=[],
        kw_defaults=[],
        kwarg=None,
        defaults=[],
    )


def _args_with_kwargs(names):
    """Build ast.arguments with positional args + **kwargs."""
    return ast.arguments(
        posonlyargs=[],
        args=[ast.arg(arg=n) for n in names],
        vararg=None,
        kwonlyargs=[],
        kw_defaults=[],
        kwarg=ast.arg(arg='kwargs'),
        defaults=[],
    )


def _args_with_varargs_kwargs(names):
    """Build ast.arguments with positional args + *args + **kwargs."""
    return ast.arguments(
        posonlyargs=[],
        args=[ast.arg(arg=n) for n in names],
        vararg=ast.arg(arg='args'),
        kwonlyargs=[],
        kw_defaults=[],
        kwarg=ast.arg(arg='kwargs'),
        defaults=[],
    )


def _annotated_arg(name, annotation):
    return ast.arg(arg=name, annotation=annotation)


def _module(body):
    return ast.Module(body=body, type_ignores=[])


def _class(name, bases, body, decorators=None, keywords=None):
    return ast.ClassDef(
        name=name,
        bases=bases,
        keywords=keywords or [],
        body=body,
        decorator_list=decorators or [],
    )


def _func(name, args, body, decorators=None, returns=None):
    return ast.FunctionDef(
        name=name,
        args=args,
        body=body,
        decorator_list=decorators or [],
        returns=returns,
    )


def _async_func(name, args, body, decorators=None, returns=None):
    return ast.AsyncFunctionDef(
        name=name,
        args=args,
        body=body,
        decorator_list=decorators or [],
        returns=returns,
    )


def _assign(target, value):
    return ast.Assign(targets=[target], value=value)


def _ann_assign(target, annotation, value=None):
    node = ast.AnnAssign(
        target=target,
        annotation=annotation,
        simple=1,
    )
    if value is not None:
        node.value = value
    return node


def _super_call(method_name, args=None, keywords=None):
    """Build super().method_name(args, **keywords)."""
    return _call(
        _attr(_call(_name('super')), method_name),
        args=args,
        keywords=keywords,
    )


def _abstract_method(name, params, returns=None):
    """Build @abstractmethod def name(self, params): raise NotImplementedError."""
    return _func(
        name,
        _simple_args(['self'] + params),
        [ast.Raise(exc=_name('NotImplementedError'))],
        decorators=[_name('abstractmethod')],
        returns=returns or _const(None),
    )


def _self_data_subscript(key):
    """Build self.data['key']."""
    return ast.Subscript(
        value=_self_attr('data'),
        slice=_const(key),
    )


def _self_data_key_subscript(key):
    """Build self._data['key']."""
    return ast.Subscript(
        value=_self_attr('_data'),
        slice=_const(key),
    )


def _parse_type(type_str):
    """Parse a type string like 'list[int]' into an AST annotation node."""
    return ast.parse(type_str, mode='eval').body


# --- Import resolution ---


def _resolve_import(import_path, package_prefix):
    """Resolve import path: '.' prefix -> absolute, else as-is."""
    if import_path.startswith('.'):
        domain_pkg = package_prefix.rsplit('.', 1)[0]
        return domain_pkg + import_path
    return import_path


def _build_vo_import_nodes(used_vos, package_prefix, with_exporters=False):
    """Build list of ast.ImportFrom for VO imports."""
    result = []
    for vo in used_vos:
        if vo.import_path:
            resolved = _resolve_import(vo.import_path, package_prefix)
            result.append(_import_from(resolved, [vo.class_name]))
            if with_exporters and vo.kind == VoKind.COMPOSITE:
                result.append(_import_from(
                    '%s_exporter' % resolved,
                    ['%sExporter' % vo.class_name],
                ))
        else:
            names = [vo.class_name]
            if with_exporters and vo.kind == VoKind.COMPOSITE:
                names.append('%sExporter' % vo.class_name)
            result.append(_import_from(
                '%s.values' % package_prefix,
                names,
            ))
    return result


# --- Exporter dispatch helpers ---


def _build_exporter_set_method(field):
    """Build a set_X method for exporter class based on dispatch_kind."""
    method_name = 'set_%s' % field.param_name

    if field.dispatch_kind == DispatchKind.PRIMITIVE:
        # self.data['x'] = value
        body = [_assign(
            _self_data_subscript(field.param_name),
            _name('value'),
        )]
    elif field.dispatch_kind == DispatchKind.COMPOSITE_VO:
        # exporter = XExporter()
        # value.export(exporter)
        # self.data['x'] = exporter.data
        exporter_name = '%sExporter' % field.type_name
        body = [
            _assign(_name('exporter'), _call(_name(exporter_name))),
            ast.Expr(value=_call(
                _attr(_name('value'), 'export'),
                [_name('exporter')],
            )),
            _assign(
                _self_data_subscript(field.param_name),
                _attr(_name('exporter'), 'data'),
            ),
        ]
    else:
        # value.export(lambda val: self.data.update({'x': val}))
        body = [ast.Expr(value=_call(
            _attr(_name('value'), 'export'),
            [ast.Lambda(
                args=_simple_args(['val']),
                body=_call(
                    _attr(_self_attr('data'), 'update'),
                    [ast.Dict(
                        keys=[_const(field.param_name)],
                        values=[_name('val')],
                    )],
                ),
            )],
        ))]

    return _func(method_name, _simple_args(['self', 'value']), body,
                 returns=_const(None))


def _build_exporter_add_method(field):
    """Build an add_X method for exporter class (collection fields)."""
    method_name = 'add_%s' % _singularize(field.param_name)

    if field.dispatch_kind == DispatchKind.COLLECTION_COMPOSITE_VO:
        # exporter = XExporter()
        # value.export(exporter)
        # self.data['x'].append(exporter.data)
        exporter_name = '%sExporter' % field.inner_type
        body = [
            _assign(_name('exporter'), _call(_name(exporter_name))),
            ast.Expr(value=_call(
                _attr(_name('value'), 'export'),
                [_name('exporter')],
            )),
            ast.Expr(value=_call(
                _attr(_self_data_subscript(field.param_name), 'append'),
                [_attr(_name('exporter'), 'data')],
            )),
        ]
    else:
        # value.export(lambda val: self.data['x'].append(val))
        body = [ast.Expr(value=_call(
            _attr(_name('value'), 'export'),
            [ast.Lambda(
                args=_simple_args(['val']),
                body=_call(
                    _attr(_self_data_subscript(field.param_name), 'append'),
                    [_name('val')],
                ),
            )],
        ))]

    return _func(method_name, _simple_args(['self', 'value']), body,
                 returns=_const(None))


def _build_exporter_method(field):
    """Build the appropriate exporter method (set_ or add_) for a field."""
    if field.is_collection:
        return _build_exporter_add_method(field)
    return _build_exporter_set_method(field)


# --- Reconstitutor dispatch helpers ---


def _build_reconstitutor_method(field):
    """Build a property accessor method for reconstitutor class."""
    if field.dispatch_kind == DispatchKind.PRIMITIVE:
        # return self._data['x']
        body = [ast.Return(value=_self_data_key_subscript(field.param_name))]
    elif field.dispatch_kind == DispatchKind.SIMPLE_VO:
        # return X(self._data['x'])
        body = [ast.Return(value=_call(
            _name(field.type_name),
            [_self_data_key_subscript(field.param_name)],
        ))]
    elif field.dispatch_kind == DispatchKind.COMPOSITE_VO:
        # data = self._data['x']
        # return X(**data)
        body = [
            _assign(_name('data'), _self_data_key_subscript(field.param_name)),
            ast.Return(value=_call(
                _name(field.type_name),
                keywords=[ast.keyword(arg=None, value=_name('data'))],
            )),
        ]
    elif field.dispatch_kind == DispatchKind.COLLECTION_SIMPLE_VO:
        # return [X(i) for i in self._data['x']]
        body = [ast.Return(value=ast.ListComp(
            elt=_call(_name(field.inner_type), [_name('i')]),
            generators=[ast.comprehension(
                target=_name('i'),
                iter=_self_data_key_subscript(field.param_name),
                ifs=[],
                is_async=0,
            )],
        ))]
    elif field.dispatch_kind == DispatchKind.COLLECTION_COMPOSITE_VO:
        # return [X(**i) for i in self._data['x']]
        body = [ast.Return(value=ast.ListComp(
            elt=_call(
                _name(field.inner_type),
                keywords=[ast.keyword(arg=None, value=_name('i'))],
            ),
            generators=[ast.comprehension(
                target=_name('i'),
                iter=_self_data_key_subscript(field.param_name),
                ifs=[],
                is_async=0,
            )],
        ))]
    else:
        body = [ast.Return(value=_self_data_key_subscript(field.param_name))]

    return _func(field.param_name, _simple_args(['self']), body)


# ========================================================================
# Per-file builders
# ========================================================================


def build_empty_init():
    """Build an empty __init__.py module."""
    return _module([])


# --- Value Objects ---


def build_identity_vo(vo):
    """Build ast.Module for identity value object."""
    imports = [
        _import_from(
            'ascetic_ddd.seedwork.domain.identity',
            [vo.identity_base_class],
        ),
    ]

    if vo.constraints.required:
        init_body = [
            ast.If(
                test=ast.Compare(
                    left=_name('value'),
                    ops=[ast.Is()],
                    comparators=[_const(None)],
                ),
                body=[ast.Raise(exc=_call(_name('ValueError'), [
                    _const('Type of %s value should not be empty'
                           % vo.identity_base_class),
                ]))],
                orelse=[],
            ),
            ast.Expr(value=_super_call('__init__', [_name('value')])),
        ]
        class_body = [_func(
            '__init__',
            _simple_args(['self', 'value']),
            init_body,
        )]
    else:
        class_body = [ast.Pass()]

    cls = _class(vo.class_name, [_name(vo.identity_base_class)], class_body)
    return _module(imports + [cls])


def build_string_vo(vo):
    """Build ast.Module for string value object."""
    imports = [_import('typing')]

    # __init__ body
    init_body = []
    if not vo.constraints.blank:
        # if not value or not value.strip():
        #     raise ValueError("X cannot be empty")
        init_body.append(ast.If(
            test=ast.BoolOp(
                op=ast.Or(),
                values=[
                    ast.UnaryOp(op=ast.Not(), operand=_name('value')),
                    ast.UnaryOp(
                        op=ast.Not(),
                        operand=_call(_attr(_name('value'), 'strip')),
                    ),
                ],
            ),
            body=[ast.Raise(exc=_call(_name('ValueError'), [
                _const('%s cannot be empty' % vo.class_name),
            ]))],
            orelse=[],
        ))

    if vo.constraints.max_length:
        # if len(value) > max_length:
        #     raise ValueError("X cannot exceed N characters")
        init_body.append(ast.If(
            test=ast.Compare(
                left=_call(_name('len'), [_name('value')]),
                ops=[ast.Gt()],
                comparators=[_const(vo.constraints.max_length)],
            ),
            body=[ast.Raise(exc=_call(_name('ValueError'), [
                _const('%s cannot exceed %d characters'
                       % (vo.class_name, vo.constraints.max_length)),
            ]))],
            orelse=[],
        ))

    if 'strip' in vo.maps:
        # self._value = value.strip()
        init_body.append(_assign(
            _self_attr('_value'),
            _call(_attr(_name('value'), 'strip')),
        ))
    else:
        # self._value = value
        init_body.append(_assign(_self_attr('_value'), _name('value')))

    # typing.Callable[[str], None]
    callable_annotation = ast.Subscript(
        value=_attr(_name('typing'), 'Callable'),
        slice=ast.Tuple(elts=[
            ast.List(elts=[_name('str')]),
            _const(None),
        ]),
    )

    class_body = [
        # _value: str
        _ann_assign(_name('_value'), _name('str')),

        # def __init__(self, value: str) -> None:
        _func(
            '__init__',
            ast.arguments(
                posonlyargs=[],
                args=[
                    ast.arg(arg='self'),
                    _annotated_arg('value', _name('str')),
                ],
                vararg=None,
                kwonlyargs=[],
                kw_defaults=[],
                kwarg=None,
                defaults=[],
            ),
            init_body,
            returns=_const(None),
        ),

        # @property
        # def value(self) -> str:
        _func(
            'value',
            _simple_args(['self']),
            [ast.Return(value=_self_attr('_value'))],
            decorators=[_name('property')],
            returns=_name('str'),
        ),

        # def __str__(self) -> str:
        _func(
            '__str__',
            _simple_args(['self']),
            [ast.Return(value=_self_attr('_value'))],
            returns=_name('str'),
        ),

        # def __repr__(self) -> str:
        #     return "%s(%r)" % ("ClassName", self._value)
        _func(
            '__repr__',
            _simple_args(['self']),
            [ast.Return(value=ast.BinOp(
                left=_const('%s(%r)'),
                op=ast.Mod(),
                right=ast.Tuple(elts=[
                    _const(vo.class_name),
                    _self_attr('_value'),
                ]),
            ))],
            returns=_name('str'),
        ),

        # def __eq__(self, other: object) -> bool:
        _func(
            '__eq__',
            ast.arguments(
                posonlyargs=[],
                args=[
                    ast.arg(arg='self'),
                    _annotated_arg('other', _name('object')),
                ],
                vararg=None,
                kwonlyargs=[],
                kw_defaults=[],
                kwarg=None,
                defaults=[],
            ),
            [
                ast.If(
                    test=ast.UnaryOp(
                        op=ast.Not(),
                        operand=_call(
                            _name('isinstance'),
                            [_name('other'), _name(vo.class_name)],
                        ),
                    ),
                    body=[ast.Return(value=_name('NotImplemented'))],
                    orelse=[],
                ),
                ast.Return(value=ast.Compare(
                    left=_self_attr('_value'),
                    ops=[ast.Eq()],
                    comparators=[_attr(_name('other'), '_value')],
                )),
            ],
            returns=_name('bool'),
        ),

        # def __hash__(self) -> int:
        _func(
            '__hash__',
            _simple_args(['self']),
            [ast.Return(value=_call(_name('hash'), [_self_attr('_value')]))],
            returns=_name('int'),
        ),

        # def export(self, setter: typing.Callable[[str], None]) -> None:
        _func(
            'export',
            ast.arguments(
                posonlyargs=[],
                args=[
                    ast.arg(arg='self'),
                    _annotated_arg('setter', callable_annotation),
                ],
                vararg=None,
                kwonlyargs=[],
                kw_defaults=[],
                kwarg=None,
                defaults=[],
            ),
            [ast.Expr(value=_call(
                _name('setter'),
                [_self_attr('_value')],
            ))],
            returns=_const(None),
        ),
    ]

    cls = _class(vo.class_name, [], class_body)
    return _module(imports + [cls])


def build_enum_vo(vo):
    """Build ast.Module for enum value object."""
    imports = [
        _import('typing'),
        _import_from('enum', ['Enum']),
    ]

    # typing.Callable[[str], None]
    callable_annotation = ast.Subscript(
        value=_attr(_name('typing'), 'Callable'),
        slice=ast.Tuple(elts=[
            ast.List(elts=[_name('str')]),
            _const(None),
        ]),
    )

    class_body = []
    # Enum members
    for member_name, member_value in vo.enum_values.items():
        class_body.append(_assign(_name(member_name), _const(member_value)))

    # def export(self, setter: typing.Callable[[str], None]) -> None:
    class_body.append(_func(
        'export',
        ast.arguments(
            posonlyargs=[],
            args=[
                ast.arg(arg='self'),
                _annotated_arg('setter', callable_annotation),
            ],
            vararg=None,
            kwonlyargs=[],
            kw_defaults=[],
            kwarg=None,
            defaults=[],
        ),
        [ast.Expr(value=_call(
            _name('setter'),
            [_attr(_name('self'), 'value')],
        ))],
        returns=_const(None),
    ))

    cls = _class(
        vo.class_name,
        [_name('str'), _name('Enum')],
        class_body,
    )
    return _module(imports + [cls])


def build_composite_vo(vo):
    """Build ast.Module for composite value object."""
    imports = [
        _import_from('abc', ['ABCMeta', 'abstractmethod']),
    ]

    # IXExporter interface
    exporter_body = []
    for f in vo.fields:
        exporter_body.append(_abstract_method(
            'set_%s' % f.param_name, ['value'],
        ))

    exporter_cls = _class(
        'I%sExporter' % vo.class_name,
        [],
        exporter_body,
        keywords=[ast.keyword(arg='metaclass', value=_name('ABCMeta'))],
    )

    # X class
    # __init__(self, param1, param2, ...) -> None
    param_names = [f.param_name for f in vo.fields]
    init_body = []
    for f in vo.fields:
        init_body.append(_assign(_self_attr(f.name), _name(f.param_name)))

    # export(self, exporter: "IXExporter") -> None
    export_body = []
    for f in vo.fields:
        export_body.append(ast.Expr(value=_call(
            _attr(_name('exporter'), 'set_%s' % f.param_name),
            [_self_attr(f.name)],
        )))

    class_body = [
        _func(
            '__init__',
            _simple_args(['self'] + param_names),
            init_body,
            returns=_const(None),
        ),
        _func(
            'export',
            ast.arguments(
                posonlyargs=[],
                args=[
                    ast.arg(arg='self'),
                    _annotated_arg(
                        'exporter',
                        _const('I%sExporter' % vo.class_name),
                    ),
                ],
                vararg=None,
                kwonlyargs=[],
                kw_defaults=[],
                kwarg=None,
                defaults=[],
            ),
            export_body,
            returns=_const(None),
        ),
    ]

    vo_cls = _class(vo.class_name, [], class_body)
    return _module(imports + [exporter_cls, vo_cls])


def build_composite_vo_exporter(vo, package_prefix):
    """Build ast.Module for composite VO exporter."""
    imports = [
        _import_from(
            '%s.values.%s' % (package_prefix, vo.snake_name),
            ['I%sExporter' % vo.class_name],
        ),
    ]

    # __init__
    init_body = [
        ast.Expr(value=_super_call('__init__')),
        _assign(_self_attr('data'), ast.Dict(keys=[], values=[])),
    ]

    # dispatch methods
    methods = [_func(
        '__init__',
        _simple_args(['self']),
        init_body,
    )]
    for f in vo.fields:
        methods.append(_build_exporter_method(f))

    cls = _class(
        '%sExporter' % vo.class_name,
        [_name('I%sExporter' % vo.class_name)],
        methods,
    )
    return _module(imports + [cls])


def build_values_init(value_objects, package_prefix):
    """Build ast.Module for values/__init__.py with re-exports."""
    body = []

    for vo in value_objects:
        if vo.import_path:
            resolved = _resolve_import(vo.import_path, package_prefix)
            if vo.kind == VoKind.COMPOSITE:
                body.append(_import_from(
                    resolved,
                    [vo.class_name, 'I%sExporter' % vo.class_name],
                ))
                body.append(_import_from(
                    '%s_exporter' % resolved,
                    ['%sExporter' % vo.class_name],
                ))
            else:
                body.append(_import_from(resolved, [vo.class_name]))
        elif vo.kind == VoKind.COMPOSITE:
            body.append(_import_from(
                '%s.values.%s' % (package_prefix, vo.snake_name),
                [vo.class_name, 'I%sExporter' % vo.class_name],
            ))
            body.append(_import_from(
                '%s.values.%s_exporter' % (package_prefix, vo.snake_name),
                ['%sExporter' % vo.class_name],
            ))
        else:
            body.append(_import_from(
                '%s.values.%s' % (package_prefix, vo.snake_name),
                [vo.class_name],
            ))

    # __all__
    all_names = []
    for vo in sorted(value_objects, key=lambda v: v.class_name):
        all_names.append(_const(vo.class_name))
        if vo.kind == VoKind.COMPOSITE:
            all_names.append(_const('I%sExporter' % vo.class_name))
            all_names.append(_const('%sExporter' % vo.class_name))

    body.append(_assign(_name('__all__'), ast.List(elts=all_names)))
    return _module(body)


# --- Aggregate ---


def build_aggregate(agg, fields, collection_fields, used_vos,
                    package_prefix, needs_datetime):
    """Build ast.Module for aggregate root (3 classes)."""
    imports = [
        _import('dataclasses'),
        _import('typing'),
    ]
    if needs_datetime:
        imports.append(_import_from('datetime', ['datetime']))
    imports.append(_import_from('abc', ['ABCMeta', 'abstractmethod']))
    imports.append(_import_from(
        'ascetic_ddd.seedwork.domain.aggregate',
        [
            'EventiveEntity',
            'PersistentDomainEvent',
            'VersionedAggregate',
            'IVersionedAggregateExporter',
            'IVersionedAggregateReconstitutor',
        ],
    ))
    imports.extend(_build_vo_import_nodes(used_vos, package_prefix))

    # IXExporter interface
    exporter_body = []
    for f in fields:
        if f.is_collection:
            exporter_body.append(_abstract_method(
                'add_%s' % _singularize(f.param_name), ['value'],
            ))
        else:
            exporter_body.append(_abstract_method(
                'set_%s' % f.param_name, ['value'],
            ))

    exporter_cls = _class(
        'I%sExporter' % agg.class_name,
        [_name('IVersionedAggregateExporter')],
        exporter_body,
        keywords=[ast.keyword(arg='metaclass', value=_name('ABCMeta'))],
    )

    # IXReconstitutor interface
    reconstitutor_body = []
    for f in fields:
        reconstitutor_body.append(_abstract_method(
            f.param_name, [],
        ))

    reconstitutor_cls = _class(
        'I%sReconstitutor' % agg.class_name,
        [_name('IVersionedAggregateReconstitutor')],
        reconstitutor_body,
        keywords=[ast.keyword(arg='metaclass', value=_name('ABCMeta'))],
    )

    # Aggregate class
    agg_body = []

    # Field annotations
    for f in fields:
        agg_body.append(_ann_assign(_name(f.name), _parse_type(f.type_name)))

    # __init__
    param_names = [f.param_name for f in fields]
    init_body = []
    for f in fields:
        if f.param_name == 'id':
            type_name = f.inner_type if f.is_collection else f.type_name
            init_body.append(ast.Assert(
                test=_call(
                    _name('isinstance'),
                    [_name(f.param_name), _name(type_name)],
                ),
            ))
    init_body.append(ast.Expr(value=_super_call(
        '__init__',
        keywords=[ast.keyword(arg=None, value=_name('kwargs'))],
    )))
    for f in fields:
        init_body.append(_assign(_self_attr(f.name), _name(f.param_name)))

    agg_body.append(_func(
        '__init__',
        _args_with_kwargs(['self'] + param_names),
        init_body,
        returns=_const(None),
    ))

    # _add_domain_event
    agg_body.append(_func(
        '_add_domain_event',
        ast.arguments(
            posonlyargs=[],
            args=[
                ast.arg(arg='self'),
                _annotated_arg('event', _name('PersistentDomainEvent')),
            ],
            vararg=None,
            kwonlyargs=[],
            kw_defaults=[],
            kwarg=None,
            defaults=[],
        ),
        [
            _assign(
                _name('event'),
                _call(
                    _attr(_name('dataclasses'), 'replace'),
                    [_name('event')],
                    [ast.keyword(
                        arg='aggregate_version',
                        value=_call(_attr(_name('self'), 'next_version')),
                    )],
                ),
            ),
            ast.Expr(value=_super_call(
                '_add_domain_event', [_name('event')],
            )),
        ],
        returns=_const(None),
    ))

    # export
    export_body = [ast.Expr(value=_super_call(
        'export', [_name('exporter')],
    ))]
    for f in fields:
        if f.is_collection:
            export_body.append(ast.For(
                target=_name('item'),
                iter=_self_attr(f.name),
                body=[ast.Expr(value=_call(
                    _attr(
                        _name('exporter'),
                        'add_%s' % _singularize(f.param_name),
                    ),
                    [_name('item')],
                ))],
                orelse=[],
            ))
        else:
            export_body.append(ast.Expr(value=_call(
                _attr(_name('exporter'), 'set_%s' % f.param_name),
                [_self_attr(f.name)],
            )))

    agg_body.append(_func(
        'export',
        ast.arguments(
            posonlyargs=[],
            args=[
                ast.arg(arg='self'),
                _annotated_arg(
                    'exporter',
                    _const('I%sExporter' % agg.class_name),
                ),
            ],
            vararg=None,
            kwonlyargs=[],
            kw_defaults=[],
            kwarg=None,
            defaults=[],
        ),
        export_body,
        returns=_const(None),
    ))

    # _import
    import_body = [ast.Expr(value=_super_call(
        '_import', [_name('provider')],
    ))]
    for f in fields:
        if f.is_collection:
            import_body.append(_assign(
                _self_attr(f.name),
                _call(
                    _name(f.collection_kind.value),
                    [_call(_attr(_name('provider'), f.param_name))],
                ),
            ))
        else:
            import_body.append(_assign(
                _self_attr(f.name),
                _call(_attr(_name('provider'), f.param_name)),
            ))

    agg_body.append(_func(
        '_import',
        ast.arguments(
            posonlyargs=[],
            args=[
                ast.arg(arg='self'),
                _annotated_arg(
                    'provider',
                    _const('I%sReconstitutor' % agg.class_name),
                ),
            ],
            vararg=None,
            kwonlyargs=[],
            kw_defaults=[],
            kwarg=None,
            defaults=[],
        ),
        import_body,
        returns=_const(None),
    ))

    # reconstitute classmethod
    agg_body.append(_func(
        'reconstitute',
        ast.arguments(
            posonlyargs=[],
            args=[
                ast.arg(arg='cls'),
                _annotated_arg(
                    'reconstitutor',
                    _const('I%sReconstitutor' % agg.class_name),
                ),
            ],
            vararg=None,
            kwonlyargs=[],
            kw_defaults=[],
            kwarg=None,
            defaults=[],
        ),
        [ast.Return(value=_super_call(
            'reconstitute', [_name('reconstitutor')],
        ))],
        decorators=[_name('classmethod')],
        returns=_attr(_name('typing'), 'Self'),
    ))

    agg_cls = _class(
        agg.class_name,
        [
            ast.Subscript(
                value=_name('EventiveEntity'),
                slice=_name('PersistentDomainEvent'),
            ),
            _name('VersionedAggregate'),
        ],
        agg_body,
    )

    return _module(imports + [exporter_cls, reconstitutor_cls, agg_cls])


def build_aggregate_exporter(agg, fields, collection_fields, used_vos,
                             package_prefix):
    """Build ast.Module for aggregate exporter."""
    imports = [
        _import_from(
            'ascetic_ddd.seedwork.domain.aggregate',
            ['VersionedAggregateExporter'],
        ),
    ]
    imports.extend(_build_vo_import_nodes(
        used_vos, package_prefix, with_exporters=True,
    ))
    imports.append(_import_from(
        '%s.%s' % (package_prefix, agg.snake_name),
        ['I%sExporter' % agg.class_name],
    ))

    # __init__
    init_body = [ast.Expr(value=_super_call('__init__'))]
    for f in collection_fields:
        init_body.append(_assign(
            _self_data_subscript(f.param_name),
            ast.List(elts=[]),
        ))

    methods = [_func(
        '__init__',
        _simple_args(['self']),
        init_body,
        returns=_const(None),
    )]

    for f in fields:
        methods.append(_build_exporter_method(f))

    cls = _class(
        '%sExporter' % agg.class_name,
        [
            _name('VersionedAggregateExporter'),
            _name('I%sExporter' % agg.class_name),
        ],
        methods,
    )
    return _module(imports + [cls])


def build_aggregate_reconstitutor(agg, fields, reconstitutor_params,
                                  used_vos, package_prefix, needs_datetime):
    """Build ast.Module for aggregate reconstitutor."""
    imports = []
    if needs_datetime:
        imports.append(_import_from('datetime', ['datetime']))
    imports.append(_import_from(
        'ascetic_ddd.seedwork.domain.aggregate',
        ['VersionedAggregateReconstitutor'],
    ))
    imports.extend(_build_vo_import_nodes(used_vos, package_prefix))
    imports.append(_import_from(
        '%s.%s' % (package_prefix, agg.snake_name),
        ['I%sReconstitutor' % agg.class_name],
    ))

    # __init__(self, param1, param2, ..., *args, **kwargs)
    param_names = [f.param_name for f in reconstitutor_params]
    init_body = [
        ast.Expr(value=_super_call(
            '__init__',
            [_name('args')],
            [ast.keyword(arg=None, value=_name('kwargs'))],
        )),
        ast.Expr(value=_call(
            _attr(_self_attr('_data'), 'update'),
            [ast.Dict(
                keys=[_const(f.param_name) for f in reconstitutor_params],
                values=[_name(f.param_name) for f in reconstitutor_params],
            )],
        )),
    ]

    # Fix: super().__init__(*args, **kwargs) needs starred args
    init_body[0] = ast.Expr(value=_call(
        _attr(_call(_name('super')), '__init__'),
        [ast.Starred(value=_name('args'))],
        [ast.keyword(arg=None, value=_name('kwargs'))],
    ))

    methods = [_func(
        '__init__',
        _args_with_varargs_kwargs(['self'] + param_names),
        init_body,
        returns=_const(None),
    )]

    for f in fields:
        methods.append(_build_reconstitutor_method(f))

    cls = _class(
        '%sReconstitutor' % agg.class_name,
        [
            _name('VersionedAggregateReconstitutor'),
            _name('I%sReconstitutor' % agg.class_name),
        ],
        methods,
    )
    return _module(imports + [cls])


# --- Domain Events ---


def build_domain_event(event, used_vos, package_prefix, needs_datetime):
    """Build ast.Module for domain event."""
    imports = [
        _import_from('dataclasses', ['dataclass']),
    ]
    if needs_datetime:
        imports.append(_import_from('datetime', ['datetime']))
    imports.append(_import_from('abc', ['ABCMeta', 'abstractmethod']))
    imports.append(_import_from(
        'ascetic_ddd.seedwork.domain.aggregate',
        ['PersistentDomainEvent', 'IPersistentDomainEventExporter'],
    ))
    imports.extend(_build_vo_import_nodes(used_vos, package_prefix))

    # IXExporter interface
    exporter_body = []
    for f in event.fields:
        if f.is_collection:
            exporter_body.append(_abstract_method(
                'add_%s' % _singularize(f.param_name), ['value'],
            ))
        else:
            exporter_body.append(_abstract_method(
                'set_%s' % f.param_name, ['value'],
            ))

    exporter_cls = _class(
        'I%sExporter' % event.class_name,
        [_name('IPersistentDomainEventExporter')],
        exporter_body,
        keywords=[ast.keyword(arg='metaclass', value=_name('ABCMeta'))],
    )

    # Event dataclass
    event_body = []
    for f in event.fields:
        event_body.append(_ann_assign(
            _name(f.param_name),
            _parse_type(f.type_name),
        ))
    event_body.append(_ann_assign(
        _name('event_version'),
        _name('int'),
        _const(event.event_version),
    ))

    # export method
    export_body = [ast.Expr(value=_super_call(
        'export', [_name('exporter')],
    ))]
    for f in event.fields:
        if f.is_collection:
            export_body.append(ast.For(
                target=_name('item'),
                iter=_attr(_name('self'), f.param_name),
                body=[ast.Expr(value=_call(
                    _attr(
                        _name('exporter'),
                        'add_%s' % _singularize(f.param_name),
                    ),
                    [_name('item')],
                ))],
                orelse=[],
            ))
        else:
            export_body.append(ast.Expr(value=_call(
                _attr(_name('exporter'), 'set_%s' % f.param_name),
                [_attr(_name('self'), f.param_name)],
            )))

    event_body.append(_func(
        'export',
        ast.arguments(
            posonlyargs=[],
            args=[
                ast.arg(arg='self'),
                _annotated_arg(
                    'exporter',
                    _const('I%sExporter' % event.class_name),
                ),
            ],
            vararg=None,
            kwonlyargs=[],
            kw_defaults=[],
            kwarg=None,
            defaults=[],
        ),
        export_body,
        returns=_const(None),
    ))

    event_cls = _class(
        event.class_name,
        [_name('PersistentDomainEvent')],
        event_body,
        decorators=[_call(
            _name('dataclass'),
            keywords=[
                ast.keyword(arg='frozen', value=_const(True)),
                ast.keyword(arg='kw_only', value=_const(True)),
            ],
        )],
    )

    return _module(imports + [exporter_cls, event_cls])


def build_domain_event_exporter(event, collection_fields, used_vos,
                                package_prefix):
    """Build ast.Module for domain event exporter."""
    imports = [
        _import_from(
            'ascetic_ddd.seedwork.domain.aggregate',
            ['PersistentDomainEventExporter'],
        ),
    ]
    imports.extend(_build_vo_import_nodes(
        used_vos, package_prefix, with_exporters=True,
    ))
    imports.append(_import_from(
        '%s.events.%s' % (package_prefix, event.snake_name),
        ['I%sExporter' % event.class_name],
    ))

    # __init__
    init_body = [ast.Expr(value=_super_call('__init__'))]
    for f in collection_fields:
        init_body.append(_assign(
            _self_data_subscript(f.param_name),
            ast.List(elts=[]),
        ))

    methods = [_func(
        '__init__',
        _simple_args(['self']),
        init_body,
        returns=_const(None),
    )]

    for f in event.fields:
        methods.append(_build_exporter_method(f))

    cls = _class(
        '%sExporter' % event.class_name,
        [
            _name('PersistentDomainEventExporter'),
            _name('I%sExporter' % event.class_name),
        ],
        methods,
    )
    return _module(imports + [cls])


# --- Commands ---


def build_command(cmd, needs_datetime, needs_decimal):
    """Build ast.Module for command dataclass."""
    imports = [
        _import_from('dataclasses', ['dataclass']),
    ]
    if needs_datetime:
        imports.append(_import_from('datetime', ['datetime']))
    if needs_decimal:
        imports.append(_import_from('decimal', ['Decimal']))

    class_body = []
    for f in cmd.fields:
        class_body.append(_ann_assign(
            _name(f.param_name),
            _parse_type(f.type_name),
        ))
    class_body.append(_ann_assign(
        _name('command_version'),
        _name('int'),
        _const(cmd.command_version),
    ))

    cls = _class(
        '%sCommand' % cmd.class_name,
        [],
        class_body,
        decorators=[_call(
            _name('dataclass'),
            keywords=[
                ast.keyword(arg='frozen', value=_const(True)),
                ast.keyword(arg='kw_only', value=_const(True)),
            ],
        )],
    )
    return _module(imports + [cls])


def build_command_handler(cmd, commands_package):
    """Build ast.Module for command handler."""
    imports = [
        _import('typing'),
        _import_from(
            '%s.%s_command' % (commands_package, cmd.snake_name),
            ['%sCommand' % cmd.class_name],
        ),
    ]

    call_method = _async_func(
        '__call__',
        ast.arguments(
            posonlyargs=[],
            args=[
                ast.arg(arg='self'),
                _annotated_arg(
                    'command',
                    _name('%sCommand' % cmd.class_name),
                ),
            ],
            vararg=None,
            kwonlyargs=[],
            kw_defaults=[],
            kwarg=None,
            defaults=[],
        ),
        [ast.Raise(exc=_name('NotImplementedError'))],
        returns=_attr(_name('typing'), 'Any'),
    )

    cls = _class(
        '%sCommandHandler' % cmd.class_name,
        [],
        [call_method],
    )
    return _module(imports + [cls])


def build_commands_init(commands, commands_package):
    """Build ast.Module for commands/__init__.py with re-exports."""
    body = []
    for cmd in commands:
        body.append(_import_from(
            '%s.%s_command' % (commands_package, cmd.snake_name),
            ['%sCommand' % cmd.class_name],
        ))
        body.append(_import_from(
            '%s.%s_command_handler' % (commands_package, cmd.snake_name),
            ['%sCommandHandler' % cmd.class_name],
        ))
    return _module(body)
