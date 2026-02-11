from dataclasses import replace as dataclass_replace

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
    CollectionType,
    CommandDef,
    ConstraintsDef,
    DomainEventDef,
    EntityDef,
    EntityRef,
    FieldDef,
    PrimitiveType,
    ValueObjectDef,
    VoKind,
    VoRef,
)


class ModelParser:
    """Parses domain-model YAML into BoundedContextModel."""

    _IDENTITY_BASE_CLASS_MAP = {
        'int': 'IntIdentity',
        'str': 'StrIdentity',
        'uuid': 'UuidIdentity',
    }

    _VALID_TOP_LEVEL_KEYS = frozenset({'aggregates', 'external_references'})
    _VALID_AGGREGATE_KEYS = frozenset({
        'fields', 'value_objects', 'domain_events', 'entities',
    })
    _VALID_ENTITY_KEYS = frozenset({'fields', 'value_objects', 'entities'})
    _VALID_VO_KEYS = frozenset({
        'type', 'identity', 'fields', 'values', 'constraints', 'map', 'reference',
        'import',
    })

    def __init__(self):
        self._vo_map = {}
        self._entity_map = {}

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
        self._entity_map = {}
        vos = []
        for vo_name, vo_data in agg_data.get('value_objects', {}).items():
            vo = self._parse_value_object(vo_name, vo_data)
            vos.append(vo)
            self._vo_map[vo_name] = vo

        entities = []
        for ent_name, ent_data in agg_data.get('entities', {}).items():
            entity = self._parse_entity(ent_name, ent_data)
            entities.append(entity)
            self._entity_map[ent_name] = entity

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
            entities=entities,
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
        maps = self._parse_maps(vo_data.get('map', ()))

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
        import_path = vo_data.get('import', '')

        return ValueObjectDef(
            class_name=vo_name,
            snake_name=camel_to_snake(vo_name),
            kind=kind,
            base_type=base_type,
            identity_mode=identity_mode,
            identity_base_class=identity_base_class,
            constraints=constraints,
            maps=maps,
            fields=vo_fields,
            enum_values=enum_values,
            reference=reference,
            import_path=import_path,
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

    def _validate_entity(self, ent_name, ent_data):
        if not isinstance(ent_data, dict):
            raise ValueError('Entity %s must be a mapping' % ent_name)
        unknown = set(ent_data.keys()) - self._VALID_ENTITY_KEYS
        if unknown:
            raise ValueError(
                'Unknown keys in entity %s: %s'
                % (ent_name, ', '.join(sorted(unknown)))
            )

    def _parse_entity(self, ent_name, ent_data):
        self._validate_entity(ent_name, ent_data)

        # Save parent vo_map and entity_map; entity inherits parent VOs
        saved_vo_map = self._vo_map
        saved_entity_map = self._entity_map
        self._entity_map = {}

        # Entity VOs: parsed in context of parent vo_map
        entity_vos = []
        for vo_name, vo_data in ent_data.get('value_objects', {}).items():
            vo = self._parse_value_object(vo_name, vo_data)
            entity_vos.append(vo)
            self._vo_map[vo_name] = vo

        # Entity fields: may contain import path references
        fields, referenced_vos = self._parse_entity_fields(
            ent_data.get('fields', {}),
        )

        # Nested entities (recursive)
        nested_entities = []
        for nested_name, nested_data in ent_data.get('entities', {}).items():
            nested = self._parse_entity(nested_name, nested_data)
            nested_entities.append(nested)
            self._entity_map[nested_name] = nested

        # Restore parent maps
        self._vo_map = saved_vo_map
        self._entity_map = saved_entity_map

        return EntityDef(
            class_name=ent_name,
            snake_name=camel_to_snake(ent_name),
            fields=fields,
            value_objects=entity_vos,
            entities=nested_entities,
            referenced_vos=referenced_vos,
        )

    def _parse_entity_fields(self, fields_data):
        """Parse entity fields. Handles import path references in types.

        Returns (fields, referenced_vos) where referenced_vos are
        parent VO copies with import_path set.
        """
        result = []
        referenced_vos = []
        for field_name, field_type in fields_data.items():
            field_type_str = str(field_type)
            param = strip_underscore_prefix(field_name)

            # Check for import path reference: .resume.values.ResumeId
            if '.' in field_type_str:
                class_name = field_type_str.rsplit('.', 1)[1]
                pkg_path = field_type_str.rsplit('.', 1)[0]
                import_path = '%s.%s' % (pkg_path, camel_to_snake(class_name))
                if class_name not in self._vo_map:
                    # Unknown VO — register as synthetic imported VO
                    vo = ValueObjectDef(
                        class_name=class_name,
                        snake_name=camel_to_snake(class_name),
                        kind=VoKind.SIMPLE,
                        import_path=import_path,
                    )
                    self._vo_map[class_name] = vo
                else:
                    # Known parent VO — create copy with import_path
                    existing = self._vo_map[class_name]
                    referenced_vos.append(dataclass_replace(
                        existing, import_path=import_path,
                    ))
                field_type_str = class_name

            type_ref = self._resolve_type(field_type_str)
            result.append(FieldDef(
                name=field_name,
                param_name=param,
                type_ref=type_ref,
            ))
        return result, referenced_vos

    def _parse_fields(self, fields_data):
        result = []
        for field_name, field_type in fields_data.items():
            field_type_str = str(field_type)
            param = strip_underscore_prefix(field_name)
            type_ref = self._resolve_type(field_type_str)
            result.append(FieldDef(
                name=field_name,
                param_name=param,
                type_ref=type_ref,
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

    def _parse_maps(self, data):
        if not data:
            return ()
        return tuple(data)

    # --- type resolution ---

    def _resolve_type(self, type_str):
        """Resolve a type string to a TypeRef."""
        if is_collection_type(type_str):
            inner_str = extract_inner_type(type_str)
            kind = collection_kind(type_str)
            element = self._resolve_element_type(inner_str)
            return CollectionType(kind=kind, element=element)
        return self._resolve_element_type(type_str)

    def _resolve_element_type(self, type_str):
        """Resolve a non-collection type string to a TypeRef."""
        if is_primitive_type(type_str):
            return PrimitiveType(name=type_str)
        entity = self._entity_map.get(type_str)
        if entity:
            return EntityRef(entity=entity)
        vo = self._vo_map.get(type_str)
        if vo:
            return VoRef(vo=vo)
        # Unknown type — treat as primitive
        return PrimitiveType(name=type_str)

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
        return VoKind.SIMPLE

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
                cmd_type = PrimitiveType(name=ef.type_ref.primitive_type)
                cmd_fields.append(FieldDef(
                    name=ef.param_name,
                    param_name=ef.param_name,
                    type_ref=cmd_type,
                ))

            commands.append(CommandDef(
                class_name=cmd_name,
                snake_name=camel_to_snake(cmd_name),
                fields=cmd_fields,
                command_version=event.event_version,
            ))
        return commands


# --- Public facade ---


def parse_yaml(file_path):
    return ModelParser().parse(file_path)
