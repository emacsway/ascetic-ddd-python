from __future__ import annotations

from dataclasses import dataclass, field

from ascetic_ddd.cli.scaffold.naming import CollectionKind, PRIMITIVE_TYPES


# --- Type system ---


@dataclass
class TypeRef:
    """Base for all type references in the model."""

    @property
    def class_name(self):
        raise NotImplementedError

    @property
    def primitive_type(self):
        raise NotImplementedError


@dataclass
class PrimitiveType(TypeRef):
    name: str

    @property
    def class_name(self):
        return self.name

    @property
    def primitive_type(self):
        return self.name


# --- Domain model definitions ---


@dataclass
class ConstraintsDef:
    required: bool = False
    blank: bool = True  # True means blank is allowed
    max_length: int = 0  # 0 means no limit


@dataclass
class ValueObjectDef:
    """Base for all value object definitions."""
    class_name: str
    snake_name: str
    import_path: str = ''
    reference: str = ''
    is_external_ref: bool = False

    @property
    def primitive_type(self):
        raise NotImplementedError


@dataclass
class SimpleVoDef(ValueObjectDef):
    base_type: str = ''
    constraints: ConstraintsDef = field(default_factory=ConstraintsDef)
    maps: tuple = ()

    @property
    def primitive_type(self):
        if self.base_type and self.base_type in PRIMITIVE_TYPES:
            return self.base_type
        return 'str'


@dataclass
class IdentityVoDef(ValueObjectDef):
    base_type: str = ''
    constraints: ConstraintsDef = field(default_factory=ConstraintsDef)
    identity_mode: str = ''
    identity_base_class: str = ''

    @property
    def primitive_type(self):
        return self.base_type


@dataclass
class EnumVoDef(ValueObjectDef):
    enum_values: dict[str, str] = field(default_factory=dict)

    @property
    def primitive_type(self):
        return 'str'


@dataclass
class CompositeVoDef(ValueObjectDef):
    fields: list[FieldDef] = field(default_factory=list)

    @property
    def primitive_type(self):
        return 'dict'


@dataclass
class VoRef(TypeRef):
    vo: ValueObjectDef

    @property
    def class_name(self):
        return self.vo.class_name

    @property
    def primitive_type(self):
        return self.vo.primitive_type


@dataclass
class FieldDef:
    name: str           # e.g. "_id", "_title"
    param_name: str     # e.g. "id", "title" (without _ prefix)
    type_ref: TypeRef

    @property
    def type_name(self):
        return self.type_ref.class_name

    @property
    def is_collection(self):
        return isinstance(self.type_ref, CollectionType)

    @property
    def collection_kind(self):
        if isinstance(self.type_ref, CollectionType):
            return self.type_ref.kind
        return CollectionKind.NONE

    @property
    def inner_type(self):
        if isinstance(self.type_ref, CollectionType):
            return self.type_ref.element.class_name
        return ''

    @property
    def is_primitive(self):
        effective = self.type_ref
        if isinstance(effective, CollectionType):
            effective = effective.element
        return isinstance(effective, PrimitiveType)

    @property
    def is_entity(self):
        effective = self.type_ref
        if isinstance(effective, CollectionType):
            effective = effective.element
        return isinstance(effective, EntityRef)

    @property
    def is_composite_vo(self):
        effective = self.type_ref
        if isinstance(effective, CollectionType):
            effective = effective.element
        return isinstance(effective, VoRef) and isinstance(effective.vo, CompositeVoDef)


@dataclass
class DomainEventDef:
    class_name: str
    snake_name: str
    fields: list[FieldDef] = field(default_factory=list)
    event_version: int = 1


@dataclass
class CommandDef:
    class_name: str
    snake_name: str
    fields: list[FieldDef] = field(default_factory=list)
    command_version: int = 1


@dataclass
class EntityDef:
    class_name: str
    snake_name: str
    fields: list[FieldDef] = field(default_factory=list)
    value_objects: list[ValueObjectDef] = field(default_factory=list)
    entities: list[EntityDef] = field(default_factory=list)


@dataclass
class EntityRef(TypeRef):
    entity: EntityDef

    @property
    def class_name(self):
        return self.entity.class_name

    @property
    def primitive_type(self):
        return 'dict'


@dataclass
class CollectionType(TypeRef):
    kind: CollectionKind
    element: TypeRef

    @property
    def class_name(self):
        return '%s[%s]' % (self.kind.value, self.element.class_name)

    @property
    def primitive_type(self):
        return '%s[%s]' % (self.kind.value, self.element.primitive_type)


@dataclass
class AggregateDef:
    class_name: str
    snake_name: str
    fields: list[FieldDef] = field(default_factory=list)
    value_objects: list[ValueObjectDef] = field(default_factory=list)
    domain_events: list[DomainEventDef] = field(default_factory=list)
    commands: list[CommandDef] = field(default_factory=list)
    entities: list[EntityDef] = field(default_factory=list)


@dataclass
class BoundedContextModel:
    aggregates: list[AggregateDef] = field(default_factory=list)
    external_value_objects: list[ValueObjectDef] = field(default_factory=list)
