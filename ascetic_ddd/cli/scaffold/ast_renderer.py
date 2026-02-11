import ast
import os
import re

from ascetic_ddd.cli.scaffold import ast_builders as builders
from ascetic_ddd.cli.scaffold.model import VoKind
from ascetic_ddd.cli.scaffold.renderer import (
    _AggregateContext,
    _build_reconstitutor_params,
    _collect_used_vos,
    _needs_datetime,
)


class AstRenderWalker:
    """Walks BoundedContextModel and generates files via ast module.

    Only generates files that do not already exist.
    """

    def __init__(self, output_dir, package_name=None):
        self._output_dir = output_dir
        self._package_name = package_name
        self._generated = []
        self._skipped = []

    def walk(self, model):
        """Walk the entire model and return list of generated file paths."""
        for agg in model.aggregates:
            self._visit_aggregate(agg, model)
        return self._generated

    @property
    def skipped(self):
        return list(self._skipped)

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

        self._write_module(
            builders.build_values_init(ctx.agg.value_objects, ctx.pkg),
            os.path.join(ctx.values_dir, '__init__.py'),
        )

    def _visit_value_object(self, vo, ctx):
        vo_builder_map = {
            VoKind.IDENTITY: builders.build_identity_vo,
            VoKind.STRING: builders.build_string_vo,
            VoKind.ENUM: builders.build_enum_vo,
            VoKind.COMPOSITE: builders.build_composite_vo,
        }
        builder = vo_builder_map[vo.kind]
        self._write_module(
            builder(vo),
            os.path.join(ctx.values_dir, '%s.py' % vo.snake_name),
        )

        if vo.kind == VoKind.COMPOSITE:
            self._write_module(
                builders.build_composite_vo_exporter(vo, ctx.pkg),
                os.path.join(
                    ctx.values_dir, '%s_exporter.py' % vo.snake_name,
                ),
            )

    def _visit_aggregate_module(self, ctx):
        agg = ctx.agg

        self._write_module(
            builders.build_aggregate(
                agg, ctx.fields, ctx.collection_fields,
                ctx.used_vos, ctx.pkg, ctx.needs_datetime,
            ),
            os.path.join(ctx.agg_dir, '%s.py' % agg.snake_name),
        )

        self._write_module(
            builders.build_aggregate_exporter(
                agg, ctx.fields, ctx.collection_fields,
                ctx.used_vos, ctx.pkg,
            ),
            os.path.join(ctx.agg_dir, '%s_exporter.py' % agg.snake_name),
        )

        reconstitutor_params = _build_reconstitutor_params(
            ctx.fields, agg.value_objects,
        )
        self._write_module(
            builders.build_aggregate_reconstitutor(
                agg, ctx.fields, reconstitutor_params,
                ctx.used_vos, ctx.pkg, ctx.needs_datetime,
            ),
            os.path.join(
                ctx.agg_dir, '%s_reconstitutor.py' % agg.snake_name,
            ),
        )

        self._write_module(
            builders.build_empty_init(),
            os.path.join(ctx.agg_dir, '__init__.py'),
        )

    def _visit_domain_events(self, ctx):
        for event in ctx.agg.domain_events:
            self._visit_domain_event(event, ctx)

        self._write_module(
            builders.build_empty_init(),
            os.path.join(ctx.events_dir, '__init__.py'),
        )

    def _visit_domain_event(self, event, ctx):
        ev_used_vos = _collect_used_vos(event.fields, ctx.vo_map)
        ev_collection_fields = [f for f in event.fields if f.is_collection]

        self._write_module(
            builders.build_domain_event(
                event, ev_used_vos, ctx.pkg,
                _needs_datetime(event.fields),
            ),
            os.path.join(ctx.events_dir, '%s.py' % event.snake_name),
        )

        self._write_module(
            builders.build_domain_event_exporter(
                event, ev_collection_fields, ev_used_vos, ctx.pkg,
            ),
            os.path.join(
                ctx.events_dir, '%s_exporter.py' % event.snake_name,
            ),
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
        self._write_module(
            builders.build_commands_init(all_commands, cmds_pkg),
            os.path.join(cmds_dir, '__init__.py'),
        )

        # application/__init__.py
        self._write_module(
            builders.build_empty_init(),
            os.path.join(app_dir, '__init__.py'),
        )

    def _visit_command(self, cmd, cmds_dir, cmds_pkg):
        self._write_module(
            builders.build_command(
                cmd,
                needs_datetime=any(
                    'datetime' in f.type_name for f in cmd.fields
                ),
                needs_decimal=any(
                    'Decimal' in f.type_name for f in cmd.fields
                ),
            ),
            os.path.join(cmds_dir, '%s_command.py' % cmd.snake_name),
        )

        self._write_module(
            builders.build_command_handler(cmd, cmds_pkg),
            os.path.join(
                cmds_dir, '%s_command_handler.py' % cmd.snake_name,
            ),
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

    def _write_module(self, module, path):
        """Unparse AST module and write to file, skipping existing files."""
        if os.path.exists(path):
            self._skipped.append(path)
            return
        ast.fix_missing_locations(module)
        source = ast.unparse(module)
        source = _postformat(source)
        source = source.rstrip('\n') + '\n'
        with open(path, 'w') as f:
            f.write(source)
        self._generated.append(path)


# --- Public facade ---


def ast_render_bounded_context(model, output_dir, package_name=None):
    walker = AstRenderWalker(output_dir, package_name)
    return walker.walk(model)


# --- Post-formatting ---


_IMPORT_RE = re.compile(r'^(from \S+ import )(.+)$')


def _postformat(source):
    """Post-process ast.unparse output for readability.

    1. Ensure 2 blank lines before top-level class/function/decorator.
    2. Wrap long import lines into parenthesized form.
    3. Inject TODO comments for NotImplementedError stubs.
    """
    if not source.strip():
        return source

    lines = source.split('\n')

    # Pass 1: add double blank lines before top-level definitions
    result = []
    for i, line in enumerate(lines):
        if i > 0 and _is_toplevel_def(line):
            # Don't add blank lines if previous non-blank line is a decorator
            prev_nonblank = ''
            for j in range(len(result) - 1, -1, -1):
                if result[j].strip():
                    prev_nonblank = result[j].strip()
                    break
            if prev_nonblank.startswith('@'):
                # Decorator before class/def — no extra spacing
                result.append(line)
                continue
            # Ensure exactly 2 blank lines before top-level def
            if result and result[-1].strip() != '':
                result.append('')
                result.append('')
            elif result and result[-1].strip() == '':
                if len(result) < 2 or result[-2].strip() != '':
                    result.append('')
        result.append(line)

    source = '\n'.join(result)

    # Pass 2: wrap long imports
    source = _wrap_long_imports(source)

    # Pass 3: inject TODO comments
    source = _inject_todo_comments(source)

    return source


def _is_toplevel_def(line):
    """Check if line starts a top-level class, function, or decorator."""
    if not line or line[0] == ' ':
        return False
    return (line.startswith('class ')
            or line.startswith('def ')
            or line.startswith('async def ')
            or line.startswith('@'))


def _wrap_long_imports(source, max_line=99):
    """Wrap 'from X import A, B, C, ...' lines that exceed max_line."""
    lines = source.split('\n')
    result = []
    for line in lines:
        if len(line) > max_line:
            m = _IMPORT_RE.match(line)
            if m:
                prefix = m.group(1)
                names = [n.strip() for n in m.group(2).split(',')]
                result.append('%s(' % prefix)
                for name in names:
                    result.append('    %s,' % name)
                result.append(')')
                continue
        result.append(line)
    return '\n'.join(result)


def _inject_todo_comments(source):
    """Inject TODO comments for NotImplementedError not preceded by @abstractmethod."""
    lines = source.split('\n')
    result = []
    for i, line in enumerate(lines):
        stripped = line.lstrip()
        if stripped == 'raise NotImplementedError':
            # Search backwards for @abstractmethod before the enclosing def
            is_abstract = False
            for j in range(i - 1, -1, -1):
                prev_stripped = lines[j].strip()
                if not prev_stripped:
                    continue
                if prev_stripped.startswith('@abstractmethod'):
                    is_abstract = True
                    break
                if prev_stripped.startswith('def '):
                    # Found the def, keep looking for decorator
                    continue
                if prev_stripped.startswith('async def '):
                    continue
                # Hit something else (class, assignment, etc.)
                break
            if not is_abstract:
                line = '%s  # TODO: implement' % line
        result.append(line)
    return '\n'.join(result)
