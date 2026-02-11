import os
from dataclasses import dataclass

from jinja2 import ChoiceLoader, Environment, FileSystemLoader

from ascetic_ddd.cli.scaffold.model import FieldDef, VoKind
from ascetic_ddd.cli.scaffold.naming import camel_to_snake, is_primitive_type
from ascetic_ddd.cli.scaffold.parser import vo_primitive_type


TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), 'templates')

VO_TEMPLATE_MAP = {
    VoKind.IDENTITY: 'domain/values/identity_vo.py.j2',
    VoKind.STRING: 'domain/values/string_vo.py.j2',
    VoKind.ENUM: 'domain/values/enum_vo.py.j2',
    VoKind.COMPOSITE: 'domain/values/composite_vo.py.j2',
}


def _singularize(name):
    """Naive singularization: remove trailing 's' or 'es'."""
    if name.endswith('_ids'):
        return name[:-1]  # specialization_ids -> specialization_id
    if name.endswith('_types'):
        return name[:-1]  # employment_types -> employment_type
    if name.endswith('_formats'):
        return name[:-1]  # work_formats -> work_format
    if name.endswith('s'):
        return name[:-1]
    return name


def _make_env(templates_dir=None):
    if templates_dir:
        loader = ChoiceLoader([
            FileSystemLoader(templates_dir),
            FileSystemLoader(TEMPLATES_DIR),
        ])
    else:
        loader = FileSystemLoader(TEMPLATES_DIR)
    env = Environment(
        loader=loader,
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
    )
    env.filters['singularize'] = _singularize
    env.filters['snake'] = camel_to_snake
    return env


@dataclass
class _AggregateContext:
    """Per-aggregate state, analogous to EvaluateVisitor's push/pop context."""
    agg: object
    pkg: str
    agg_dir: str
    values_dir: str
    events_dir: str
    vo_map: dict
    used_vos: list
    fields: list
    collection_fields: list
    needs_datetime: bool


class RenderWalker:
    """Walks BoundedContextModel and renders files via Jinja2 templates."""

    def __init__(self, output_dir, package_name=None, templates_dir=None):
        self._env = _make_env(templates_dir)
        self._output_dir = output_dir
        self._package_name = package_name
        self._generated = []

    def walk(self, model):
        """Walk the entire model and return list of generated file paths."""
        for agg in model.aggregates:
            self._visit_aggregate(agg, model)
        return self._generated

    # --- visit methods ---

    def _visit_aggregate(self, agg, model):
        ctx = self._make_aggregate_context(agg)
        self._visit_value_objects(ctx)
        self._visit_aggregate_module(ctx)
        self._visit_domain_events(ctx)
        self._visit_commands(ctx, model)

    def _visit_value_objects(self, ctx):
        for vo in ctx.agg.value_objects:
            if not vo.import_path:
                self._visit_value_object(vo, ctx)

        self._render_template(
            'domain/values/__init__.py.j2',
            os.path.join(ctx.values_dir, '__init__.py'),
            value_objects=ctx.agg.value_objects,
            package_prefix=ctx.pkg,
        )

    def _visit_value_object(self, vo, ctx):
        self._render_template(
            VO_TEMPLATE_MAP[vo.kind],
            os.path.join(ctx.values_dir, '%s.py' % vo.snake_name),
            vo=vo,
        )

        if vo.kind == VoKind.COMPOSITE:
            self._visit_composite_vo_exporter(vo, ctx)

    def _visit_composite_vo_exporter(self, vo, ctx):
        self._render_template(
            'domain/values/composite_vo_exporter.py.j2',
            os.path.join(ctx.values_dir, '%s_exporter.py' % vo.snake_name),
            vo=vo,
            package_prefix=ctx.pkg,
        )

    def _visit_aggregate_module(self, ctx):
        agg = ctx.agg

        # aggregate.py
        self._render_template(
            'domain/aggregate.py.j2',
            os.path.join(ctx.agg_dir, '%s.py' % agg.snake_name),
            agg=agg,
            fields=ctx.fields,
            collection_fields=ctx.collection_fields,
            used_vos=ctx.used_vos,
            package_prefix=ctx.pkg,
            needs_datetime=ctx.needs_datetime,
        )

        # aggregate_exporter.py
        self._render_template(
            'domain/aggregate_exporter.py.j2',
            os.path.join(ctx.agg_dir, '%s_exporter.py' % agg.snake_name),
            agg=agg,
            fields=ctx.fields,
            collection_fields=ctx.collection_fields,
            used_vos=ctx.used_vos,
            package_prefix=ctx.pkg,
        )

        # aggregate_reconstitutor.py
        reconstitutor_params = _build_reconstitutor_params(
            ctx.fields, agg.value_objects,
        )
        self._render_template(
            'domain/aggregate_reconstitutor.py.j2',
            os.path.join(ctx.agg_dir, '%s_reconstitutor.py' % agg.snake_name),
            agg=agg,
            fields=ctx.fields,
            reconstitutor_params=reconstitutor_params,
            used_vos=ctx.used_vos,
            package_prefix=ctx.pkg,
            needs_datetime=ctx.needs_datetime,
        )

        # __init__.py
        self._render_template(
            'domain/__init__.py.j2',
            os.path.join(ctx.agg_dir, '__init__.py'),
        )

    def _visit_domain_events(self, ctx):
        for event in ctx.agg.domain_events:
            self._visit_domain_event(event, ctx)

        self._render_template(
            'domain/events/__init__.py.j2',
            os.path.join(ctx.events_dir, '__init__.py'),
        )

    def _visit_domain_event(self, event, ctx):
        ev_used_vos = _collect_used_vos(event.fields, ctx.vo_map)
        ev_collection_fields = [f for f in event.fields if f.is_collection]

        self._render_template(
            'domain/events/domain_event.py.j2',
            os.path.join(ctx.events_dir, '%s.py' % event.snake_name),
            event=event,
            used_vos=ev_used_vos,
            package_prefix=ctx.pkg,
            needs_datetime=_needs_datetime(event.fields),
        )

        self._render_template(
            'domain/events/domain_event_exporter.py.j2',
            os.path.join(ctx.events_dir, '%s_exporter.py' % event.snake_name),
            event=event,
            collection_fields=ev_collection_fields,
            used_vos=ev_used_vos,
            package_prefix=ctx.pkg,
        )

    def _visit_commands(self, ctx, model):
        if not ctx.agg.commands:
            return

        if self._package_name:
            app_pkg = '%s.application' % self._package_name
        else:
            app_pkg = 'application'
        cmds_pkg = '%s.commands' % app_pkg
        cmds_dir = os.path.join(self._output_dir, 'application', 'commands')
        app_dir = os.path.join(self._output_dir, 'application')
        os.makedirs(cmds_dir, exist_ok=True)

        for cmd in ctx.agg.commands:
            self._visit_command(cmd, cmds_dir, cmds_pkg)

        # commands/__init__.py (shared across all aggregates)
        all_commands = []
        for a in model.aggregates:
            all_commands.extend(a.commands)
        self._render_template(
            'application/commands/__init__.py.j2',
            os.path.join(cmds_dir, '__init__.py'),
            commands=all_commands,
            commands_package=cmds_pkg,
        )

        # application/__init__.py
        self._render_template(
            'application/__init__.py.j2',
            os.path.join(app_dir, '__init__.py'),
        )

    def _visit_command(self, cmd, cmds_dir, cmds_pkg):
        self._render_template(
            'application/commands/command.py.j2',
            os.path.join(cmds_dir, '%s_command.py' % cmd.snake_name),
            cmd=cmd,
            needs_datetime=any(
                'datetime' in f.type_name for f in cmd.fields
            ),
            needs_decimal=any(
                'Decimal' in f.type_name for f in cmd.fields
            ),
        )

        self._render_template(
            'application/commands/command_handler.py.j2',
            os.path.join(cmds_dir, '%s_command_handler.py' % cmd.snake_name),
            cmd=cmd,
            commands_package=cmds_pkg,
        )

    # --- helpers ---

    def _make_aggregate_context(self, agg):
        agg_dir = os.path.join(self._output_dir, 'domain', agg.snake_name)
        values_dir = os.path.join(agg_dir, 'values')
        events_dir = os.path.join(agg_dir, 'events')

        for d in (agg_dir, values_dir, events_dir):
            os.makedirs(d, exist_ok=True)

        if self._package_name:
            pkg = '%s.domain.%s' % (self._package_name, agg.snake_name)
        else:
            pkg = 'domain.%s' % agg.snake_name

        vo_map = {vo.class_name: vo for vo in agg.value_objects}
        fields = agg.fields

        return _AggregateContext(
            agg=agg,
            pkg=pkg,
            agg_dir=agg_dir,
            values_dir=values_dir,
            events_dir=events_dir,
            vo_map=vo_map,
            used_vos=_collect_used_vos(fields, vo_map),
            fields=fields,
            collection_fields=[f for f in fields if f.is_collection],
            needs_datetime=_needs_datetime(fields),
        )

    def _render_template(self, tpl_name, path, **kwargs):
        tpl = self._env.get_template(tpl_name)
        content = tpl.render(**kwargs)
        content = content.rstrip('\n') + '\n'
        with open(path, 'w') as f:
            f.write(content)
        self._generated.append(path)


# --- Public facade ---


def render_bounded_context(model, output_dir, package_name=None,
                           templates_dir=None):
    walker = RenderWalker(output_dir, package_name, templates_dir)
    return walker.walk(model)


# --- Shared helpers ---


def _collect_used_vos(fields, vo_map):
    """Return deduplicated, sorted list of VOs referenced by fields."""
    seen = set()
    result = []
    for f in fields:
        effective = f.inner_type if f.is_collection else f.type_name
        if not is_primitive_type(effective) and effective not in seen:
            seen.add(effective)
            vo = vo_map.get(effective)
            if vo:
                result.append(vo)
    return sorted(result, key=lambda vo: vo.class_name)


def _needs_datetime(fields):
    for f in fields:
        if 'datetime' in f.type_name:
            return True
    return False


def _build_reconstitutor_params(fields, value_objects):
    """Build parameter list for reconstitutor __init__ with primitive types."""
    vo_map = {vo.class_name: vo for vo in value_objects}
    params = []
    for f in fields:
        prim_type = _field_to_primitive(f, vo_map)
        params.append(FieldDef(
            name=f.param_name,
            param_name=f.param_name,
            type_name=prim_type,
            is_primitive=True,
        ))
    return params


def _field_to_primitive(field_def, vo_map):
    """Map field type to primitive for reconstitutor constructor."""
    if field_def.is_primitive:
        return field_def.type_name

    effective = field_def.inner_type if field_def.is_collection else field_def.type_name
    vo = vo_map.get(effective)
    prim = vo_primitive_type(vo) if vo else 'str'

    if field_def.is_collection:
        return '%s[%s]' % (field_def.collection_kind.value, prim)
    return prim
