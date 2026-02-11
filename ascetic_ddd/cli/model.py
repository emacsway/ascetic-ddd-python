from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


# str mixin so Jinja2 template comparisons like
# ``f.dispatch_kind == 'primitive'`` keep working.


class VoKind(str, Enum):
    IDENTITY = 'identity'
    STRING = 'string'
    COMPOSITE = 'composite'
    ENUM = 'enum'


class DispatchKind(str, Enum):
    PRIMITIVE = 'primitive'
    SIMPLE_VO = 'simple_vo'
    COMPOSITE_VO = 'composite_vo'
    COLLECTION_SIMPLE_VO = 'collection_simple_vo'
    COLLECTION_COMPOSITE_VO = 'collection_composite_vo'


class CollectionKind(str, Enum):
    NONE = ''
    LIST = 'list'
    TUPLE = 'tuple'


@dataclass
class ConstraintsDef:
    required: bool = False
    blank: bool = True  # True means blank is allowed
    max_length: int = 0  # 0 means no limit


@dataclass
class MapDef:
    strip: bool = False


@dataclass
class FieldDef:
    name: str                   # e.g. "_id", "_title"
    param_name: str             # e.g. "id", "title" (without _ prefix)
    type_name: str              # e.g. "ResumeId", "Title", "bool", "datetime"
    is_collection: bool = False
    collection_kind: CollectionKind = CollectionKind.NONE
    inner_type: str = ''        # for collections, the element type
    is_primitive: bool = False
    dispatch_kind: DispatchKind = DispatchKind.PRIMITIVE


@dataclass
class ValueObjectDef:
    class_name: str
    snake_name: str
    kind: VoKind
    base_type: str = ''
    identity_mode: str = ''
    identity_base_class: str = ''
    constraints: ConstraintsDef = field(default_factory=ConstraintsDef)
    map_def: MapDef = field(default_factory=MapDef)
    fields: list[FieldDef] = field(default_factory=list)
    enum_values: dict[str, str] = field(default_factory=dict)
    is_external_ref: bool = False
    reference: str = ''


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
class AggregateDef:
    class_name: str
    snake_name: str
    fields: list[FieldDef] = field(default_factory=list)
    value_objects: list[ValueObjectDef] = field(default_factory=list)
    domain_events: list[DomainEventDef] = field(default_factory=list)
    commands: list[CommandDef] = field(default_factory=list)


@dataclass
class BoundedContextModel:
    aggregates: list[AggregateDef] = field(default_factory=list)
    external_value_objects: list[ValueObjectDef] = field(default_factory=list)
