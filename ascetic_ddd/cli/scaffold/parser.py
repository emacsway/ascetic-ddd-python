import yaml

from ascetic_ddd.cli.scaffold.naming import (
    camel_to_snake,
    strip_underscore_prefix,
    is_collection_type,
    extract_inner_type,
    collection_kind,
    is_primitive_type,
)
from ascetic_ddd.cli.scaffold.model import (
    AggregateDef,
    BoundedContextModel,
    CollectionKind,
    CommandDef,
    ConstraintsDef,
    DispatchKind,
    DomainEventDef,
    FieldDef,
    MapDef,
    ValueObjectDef,
    VoKind,
)


def vo_primitive_type(vo):
    """Return the primitive type string for a VO.

    Pure utility — used by both ModelParser and RenderWalker.
    """
    if vo.kind == VoKind.IDENTITY:
        return vo.base_type
    if vo.kind == VoKind.ENUM:
        return 'str'
    if vo.kind == VoKind.COMPOSITE:
        return 'dict'
    if vo.base_type and is_primitive_type(vo.base_type):
        return vo.base_type
    return 'str'


class ModelParser:
    """Parses domain-model YAML into BoundedContextModel."""

    _IDENTITY_BASE_CLASS_MAP = {
        'int': 'IntIdentity',
        'str': 'StrIdentity',
        'uuid': 'UuidIdentity',
    }

    _VALID_TOP_LEVEL_KEYS = frozenset({'aggregates', 'external_references'})
    _VALID_AGGREGATE_KEYS = frozenset({'fields', 'value_objects', 'domain_events'})
    _VALID_VO_KEYS = frozenset({
        'type', 'identity', 'fields', 'values', 'constraints', 'map', 'reference',
    })

    def __init__(self):
        self._vo_map = {}

    def parse(self, file_path):
        """Parse YAML file and return BoundedContextModel."""
        with open(file_path, 'r') as f:
            raw = yaml.safe_load(f)

        self._validate_top_level(raw)

        external_vos = self._parse_external_references(
            raw.get('external_references', {}),
        )
        aggregates = []
        for agg_name, agg_data in raw.get('aggregates', {}).items():
            self._validate_aggregate(agg_name, agg_data)
            aggregates.append(self._parse_aggregate(agg_name, agg_data))

        return BoundedContextModel(
            aggregates=aggregates,
            external_value_objects=external_vos,
        )

    # --- validation ---

    def _validate_top_level(self, raw):
        if not isinstance(raw, dict):
            raise ValueError('YAML root must be a mapping')
        unknown = set(raw.keys()) - self._VALID_TOP_LEVEL_KEYS
        if unknown:
            raise ValueError(
                'Unknown top-level keys: %s' % ', '.join(sorted(unknown))
            )
        if 'aggregates' not in raw:
            raise ValueError("Missing required key 'aggregates'")

    def _validate_aggregate(self, agg_name, agg_data):
        if not isinstance(agg_data, dict):
            raise ValueError('Aggregate %s must be a mapping' % agg_name)
        unknown = set(agg_data.keys()) - self._VALID_AGGREGATE_KEYS
        if unknown:
            raise ValueError(
                'Unknown keys in aggregate %s: %s'
                % (agg_name, ', '.join(sorted(unknown)))
            )

    def _validate_vo(self, vo_name, vo_data):
        if not isinstance(vo_data, dict):
            raise ValueError('Value object %s must be a mapping' % vo_name)
        unknown = set(vo_data.keys()) - self._VALID_VO_KEYS
        if unknown:
            raise ValueError(
                'Unknown keys in VO %s: %s'
                % (vo_name, ', '.join(sorted(unknown)))
            )

    # --- parsing ---

    def _parse_external_references(self, ext_data):
        result = []
        # External VOs have no aggregate context
        saved = self._vo_map
        self._vo_map = {}
        for vo_name, vo_data in ext_data.get('value_objects', {}).items():
            vo = self._parse_value_object(vo_name, vo_data)
            vo.is_external_ref = True
            result.append(vo)
        self._vo_map = saved
        return result

    def _parse_aggregate(self, agg_name, agg_data):
        self._vo_map = {}
        vos = []
        for vo_name, vo_data in agg_data.get('value_objects', {}).items():
            vo = self._parse_value_object(vo_name, vo_data)
            vos.append(vo)
            self._vo_map[vo_name] = vo

        fields = self._parse_fields(agg_data.get('fields', {}))

        events = []
        for ev_name, ev_data in agg_data.get('domain_events', {}).items():
            events.append(self._parse_domain_event(ev_name, ev_data))

        commands = self._derive_commands(events)

        return AggregateDef(
            class_name=agg_name,
            snake_name=camel_to_snake(agg_name),
            fields=fields,
            value_objects=vos,
            domain_events=events,
            commands=commands,
        )

    def _parse_value_object(self, vo_name, vo_data):
        self._validate_vo(vo_name, vo_data)
        kind = self._classify_vo(vo_data)
        base_type = vo_data.get('type', '')

        identity_mode = ''
        identity_base_class = ''
        if kind == VoKind.IDENTITY:
            identity_mode = vo_data.get('identity', 'transient')
            identity_base_class = self._IDENTITY_BASE_CLASS_MAP.get(
                base_type, 'IntIdentity',
            )

        constraints = self._parse_constraints(vo_data.get('constraints', {}))
        map_def = self._parse_map(vo_data.get('map', {}))

        vo_fields = []
        if kind == VoKind.COMPOSITE:
            # Composite VO fields don't reference aggregate VOs
            saved = self._vo_map
            self._vo_map = {}
            vo_fields = self._parse_fields(vo_data.get('fields', {}))
            self._vo_map = saved

        enum_values = {}
        if kind == VoKind.ENUM:
            enum_values = vo_data.get('values', {})

        reference = vo_data.get('reference', '')

        return ValueObjectDef(
            class_name=vo_name,
            snake_name=camel_to_snake(vo_name),
            kind=kind,
            base_type=base_type,
            identity_mode=identity_mode,
            identity_base_class=identity_base_class,
            constraints=constraints,
            map_def=map_def,
            fields=vo_fields,
            enum_values=enum_values,
            reference=reference,
        )

    def _parse_domain_event(self, ev_name, ev_data):
        raw_fields = ev_data.get('fields', {})
        event_version = raw_fields.get('event_version', 1)
        # Filter out metadata keys before parsing as domain fields
        fields_data = {
            k: v for k, v in raw_fields.items() if k != 'event_version'
        }
        fields = self._parse_fields(fields_data)
        return DomainEventDef(
            class_name=ev_name,
            snake_name=camel_to_snake(ev_name),
            fields=fields,
            event_version=event_version,
        )

    def _parse_fields(self, fields_data):
        result = []
        for field_name, field_type in fields_data.items():
            field_type_str = str(field_type)
            param = strip_underscore_prefix(field_name)
            is_coll = is_collection_type(field_type_str)

            inner = ''
            coll_kind = CollectionKind.NONE
            if is_coll:
                inner = extract_inner_type(field_type_str)
                coll_kind = collection_kind(field_type_str)

            # Determine the effective type for dispatch
            effective_type = inner if is_coll else field_type_str
            is_prim = is_primitive_type(effective_type)

            dispatch = self._compute_dispatch_kind(
                effective_type, is_coll, is_prim,
            )

            result.append(FieldDef(
                name=field_name,
                param_name=param,
                type_name=field_type_str,
                is_collection=is_coll,
                collection_kind=coll_kind,
                inner_type=inner,
                is_primitive=is_prim,
                dispatch_kind=dispatch,
            ))
        return result

    def _parse_constraints(self, data):
        if not data:
            return ConstraintsDef()
        return ConstraintsDef(
            required=data.get('required', False),
            blank=data.get('blank', True),
            max_length=data.get('max_length', 0),
        )

    def _parse_map(self, data):
        if not data:
            return MapDef()
        return MapDef(
            strip=data.get('strip', False),
        )

    # --- semantic analysis ---

    def _classify_vo(self, vo_data):
        if 'identity' in vo_data:
            return VoKind.IDENTITY
        type_str = vo_data.get('type', '')
        if type_str.startswith('Enum['):
            return VoKind.ENUM
        if 'fields' in vo_data:
            return VoKind.COMPOSITE
        # Default: string-like VO
        return VoKind.STRING

    def _compute_dispatch_kind(self, effective_type, is_collection, is_primitive):
        if is_primitive:
            return DispatchKind.PRIMITIVE

        vo = self._vo_map.get(effective_type)
        is_composite = vo and vo.kind == VoKind.COMPOSITE

        if is_collection:
            if is_composite:
                return DispatchKind.COLLECTION_COMPOSITE_VO
            return DispatchKind.COLLECTION_SIMPLE_VO

        if is_composite:
            return DispatchKind.COMPOSITE_VO
        return DispatchKind.SIMPLE_VO

    def _derive_commands(self, events):
        commands = []
        for event in events:
            # Derive a "Create" command from "XCreated" event
            cmd_name = event.class_name
            if cmd_name.endswith('Created'):
                cmd_name = 'Create' + cmd_name[:-len('Created')]
            elif cmd_name.endswith('Updated'):
                cmd_name = 'Update' + cmd_name[:-len('Updated')]
            elif cmd_name.endswith('Deleted'):
                cmd_name = 'Delete' + cmd_name[:-len('Deleted')]

            cmd_fields = []
            for ef in event.fields:
                prim_type = self._field_to_primitive(ef)
                cmd_fields.append(FieldDef(
                    name=ef.param_name,
                    param_name=ef.param_name,
                    type_name=prim_type,
                    is_collection=ef.is_collection,
                    collection_kind=ef.collection_kind,
                    inner_type=self._primitive_inner_type(ef) if ef.is_collection else '',
                    is_primitive=True,
                    dispatch_kind=DispatchKind.PRIMITIVE,
                ))

            commands.append(CommandDef(
                class_name=cmd_name,
                snake_name=camel_to_snake(cmd_name),
                fields=cmd_fields,
                command_version=event.event_version,
            ))
        return commands

    def _field_to_primitive(self, field_def):
        """Map a VO field type to its primitive equivalent for commands."""
        if field_def.is_primitive:
            return field_def.type_name

        effective = field_def.inner_type if field_def.is_collection else field_def.type_name
        vo = self._vo_map.get(effective)
        prim = vo_primitive_type(vo) if vo else 'str'

        if field_def.is_collection:
            return '%s[%s]' % (field_def.collection_kind.value, prim)
        return prim

    def _primitive_inner_type(self, field_def):
        vo = self._vo_map.get(field_def.inner_type)
        if vo:
            return vo_primitive_type(vo)
        return 'str'


# --- Public facade ---


def parse_yaml(file_path):
    return ModelParser().parse(file_path)
