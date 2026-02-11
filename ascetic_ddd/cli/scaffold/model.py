from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from ascetic_ddd.cli.scaffold.naming import CollectionKind, PRIMITIVE_TYPES


# str mixin so Jinja2 template comparisons like
# ``vo.kind == 'identity'`` keep working.


class VoKind(str, Enum):
    IDENTITY = 'identity'
    SIMPLE = 'simple'
    COMPOSITE = 'composite'
    ENUM = 'enum'


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
    class_name: str
    snake_name: str
    kind: VoKind
    base_type: str = ''
    identity_mode: str = ''
    identity_base_class: str = ''
    constraints: ConstraintsDef = field(default_factory=ConstraintsDef)
    maps: tuple = ()
    fields: list[FieldDef] = field(default_factory=list)
    enum_values: dict[str, str] = field(default_factory=dict)
    is_external_ref: bool = False
    reference: str = ''
    import_path: str = ''

    @property
    def primitive_type(self):
        if self.kind == VoKind.IDENTITY:
            return self.base_type
        if self.kind == VoKind.ENUM:
            return 'str'
        if self.kind == VoKind.COMPOSITE:
            return 'dict'
        if self.base_type and self.base_type in PRIMITIVE_TYPES:
            return self.base_type
        return 'str'


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
        return isinstance(effective, VoRef) and effective.vo.kind == VoKind.COMPOSITE


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
