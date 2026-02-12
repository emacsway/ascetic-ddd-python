# Bounded Context Scaffold

```{index} Scaffold, Code Generation, Bounded Context, Aggregate, Value Object, Domain Event, Command
```


## Overview

The scaffold module (`ascetic_ddd.cli.scaffold`) generates Python code for a
DDD {term}`Bounded Context` from a declarative YAML domain model.

A single YAML file produces a complete directory tree:
{term}`Aggregate` roots with exporter/reconstitutor infrastructure,
{term}`Value Object` classes (identity, string, enum, composite),
{term}`Domain Event` dataclasses with exporters,
and CQRS Command dataclasses with async handler stubs.

Generated code follows the patterns described in
{doc}`/architecture/patterns` — encapsulated aggregates that expose state
through the Mediator (exporter/reconstitutor) pattern, never through getters.


## Why?

Setting up a new aggregate by hand involves creating 10-30 files with a lot
of boilerplate: the aggregate class, its exporter and reconstitutor interfaces,
value object classes with validation, domain events, commands, `__init__.py`
re-exports. Each file follows a strict structural convention.

The scaffold automates this initial setup. You describe the domain model
declaratively — fields, value objects, events — and get a compilable,
structurally correct codebase ready for customization. The generated code is
a starting point, not a framework: you own it and modify it freely.

The YAML schema enforces DDD constraints at definition time:

- Value objects use a class hierarchy (`IdentityVoDef`, `SimpleVoDef`,
  `EnumVoDef`, `CompositeVoDef`), each with its own validation rules and
  generated structure.
- Commands use only primitive types — domain types do not leak into the
  application layer.
- Collection fields generate `add_*` methods on exporters (not `set_*`),
  enforcing the aggregate's control over its internal collections.


## Usage

```bash
python -m ascetic_ddd.cli scaffold \
    -i domain-model.yaml \
    -o ./output \
    -p app.jobs
```

| Flag | Description |
|------|-------------|
| `-i, --input` | Path to domain-model YAML file (required) |
| `-o, --output` | Output directory for generated code (required) |
| `-p, --package` | Base package name for imports, e.g. `app.jobs` (optional) |
| `-t, --templates` | Custom templates directory (optional, see [Custom templates](#custom-templates)) |

Programmatic usage:

```python
from ascetic_ddd.cli.scaffold import scaffold

scaffold("domain-model.yaml", "./output", "app.jobs")
```


## Complete YAML Example

```yaml
aggregates:
  Resume:
    fields:
      _id: ResumeId
      _user_id: UserId
      _title: Title
      _description: Description
      _specialization_ids: list[.specialization.values.SpecializationId]
      _rate: Rate
      _employment_types: list[EmploymentType]
      _work_formats: list[WorkFormat]
      _show_reputation: bool
      _created_at: datetime
      _updated_at: datetime
      _is_active: bool
      _experience: list[Experience]      # collection entity

    entities:
      Experience:
        fields:
          resume_id: .resume.values.ResumeId
          company_name: CompanyName
          date_range: TimeRange
        value_objects:
          CompanyName:
            type: str
            constraints:
              blank: false
              max_length: 255
            map:
              - strip
          TimeRange:
            import: ascetic_ddd.seedwork.domain.values.TimeRange

    value_objects:
      ResumeId:                          # identity VO
        type: int
        identity: transient

      UserId:                            # string VO with external reference
        type: int
        reference: external
        constraints:
          required: true

      Title:                             # string VO with validation + strip
        type: str
        constraints:
          blank: false
          max_length: 255
        map:
          - strip

      Description:                       # string VO with validation
        type: str
        constraints:
          blank: false
        map:
          - strip

      Rate:                              # composite VO
        fields:
          _rate_period: PaymentPeriod
          _rate: ascetic_ddd.seedwork.domain.values.Money
        constraints:
          required: true

      EmploymentType:                    # enum VO
        type: Enum[str]
        values:
          FULL_TIME: "full_time"
          PART_TIME: "part_time"
          ONE_TIME: "one_time"
          CONSULTING: "consulting"
          MENTORING: "mentoring"

      PaymentPeriod:                     # enum VO (used inside composite Rate)
        type: Enum[str]
        values:
          HOURLY: "hourly"
          MONTHLY: "monthly"
          YEARLY: "yearly"
          ONE_TIME: "one_time"

      WorkFormat:                        # enum VO
        type: Enum[str]
        values:
          OFFICE: "office"
          HYBRID: "hybrid"
          REMOTE: "remote"

    domain_events:
      ResumeCreated:                     # -> derives CreateResumeCommand
        fields:
          aggregate_id: ResumeId
          user_id: UserId
          title: Title
          description: Description
          specialization_ids: tuple[.specialization.values.SpecializationId, ...]
          rate: Rate
          employment_types: tuple[EmploymentType, ...]
          work_formats: tuple[WorkFormat, ...]
          show_reputation: bool
          created_at: datetime
          is_active: bool
          event_version: 1               # metadata, not a domain field

  Specialization:
    fields:
      _id: SpecializationId
      _profile: SpecializationProfile    # single entity

    entities:
      SpecializationProfile:
        fields:
          bio: str
          level: str

    value_objects:
      SpecializationId:
        type: int
        identity: transient

external_references:                     # VOs from other bounded contexts
  value_objects:
    UserId:
      type: int
      reference: User
      constraints:
        required: true
```

This model generates files across two aggregates, including value objects
of all four kinds (identity, string, enum, composite), entities (collection
and single), a domain event with exporter, and a derived command with handler.


## YAML Schema

### Top-level structure

```yaml
aggregates:               # required, at least one
  AggregateName:
    fields: { ... }
    value_objects: { ... }
    entities: { ... }
    domain_events: { ... }

external_references:      # optional
  value_objects:
    TypeName:
      type: int
      reference: ExternalContext
```

Allowed top-level keys: `aggregates`, `external_references`.
Unknown keys raise `ValueError`.


### Fields

Fields describe the internal state of an aggregate, an entity, a composite
VO, or a domain event. Declared as `name: type` pairs.

```yaml
fields:
  _id: ResumeId                                               # VO reference
  _title: Title                                               # VO reference
  _specialization_ids: list[.specialization.values.SpecializationId]  # dotted path in collection
  _rate: Rate                                                 # composite VO
  _employment_types: list[EmploymentType]
  _experience: list[Experience]                               # entity collection
  _show_reputation: bool                                      # primitive
  _created_at: datetime                                       # primitive
```

Underscore prefix (`_id`) denotes private aggregate state.
The prefix is stripped for parameter names in constructors and exporters
(`_id` -> `id`, `_specialization_ids` -> `specialization_ids`).

Primitive types: `bool`, `int`, `str`, `float`, `datetime`, `Decimal`.

Collection types: `list[T]`, `tuple[T, ...]`.
Collections generate `add_*` (singular form) methods on exporter interfaces
instead of `set_*`.

**Inline dotted paths.** A field type can be a dotted path referencing a VO
from another aggregate or an external package. The parser creates a synthetic
VO definition from the path — no explicit VO declaration is needed:

```yaml
# Relative path (resolves within current bounded context's domain package)
_specialization_ids: list[.specialization.values.SpecializationId]

# Absolute path (external package)
_rate: ascetic_ddd.seedwork.domain.values.Money
```

The class name is extracted from the last segment; the module path is derived
by converting the class name to snake_case:
`.specialization.values.SpecializationId` → import from
`.specialization.values.specialization_id`.


### Value Objects

A VO kind is determined by which keys are present in its definition.
Allowed keys: `type`, `identity`, `fields`, `values`, `constraints`, `map`,
`reference`, `import`. Unknown keys raise `ValueError`.


#### Identity VO

```yaml
ResumeId:
  type: int               # int | str | uuid
  identity: transient     # transient | persistent
```

Discriminator: presence of the `identity` key.

Generated class extends `IntIdentity`, `StrIdentity`, or `UuidIdentity`
from `ascetic_ddd.seedwork.domain.identity`.

```python
from ascetic_ddd.seedwork.domain.identity import IntIdentity

class ResumeId(IntIdentity):
    pass
```


#### String VO

```yaml
Title:
  type: str
  constraints:
    blank: false          # reject empty / whitespace-only (default: true)
    max_length: 255       # reject strings over N chars (default: no limit)
  map:
    - strip               # strip whitespace on init
```

Discriminator: no `identity`, no `fields`, no `values`.

Generated class validates constraints in `__init__`, exposes a `value`
property, implements `__eq__`, `__hash__`, and `export(setter)`:

```python
class Title:
    def __init__(self, value: str) -> None:
        if not value or not value.strip():
            raise ValueError("Title cannot be empty")
        if len(value) > 255:
            raise ValueError("Title cannot exceed 255 characters")
        self._value = value.strip()

    def export(self, setter: typing.Callable[[str], None]) -> None:
        setter(self._value)
```


#### Enum VO

```yaml
EmploymentType:
  type: Enum[str]
  values:
    FULL_TIME: "full_time"
    PART_TIME: "part_time"
    ONE_TIME: "one_time"
```

Discriminator: `type` value starts with `Enum[`.

Generated class extends `str, Enum`:

```python
class EmploymentType(str, Enum):
    FULL_TIME = "full_time"
    PART_TIME = "part_time"
    ONE_TIME = "one_time"

    def export(self, setter: typing.Callable[[str], None]) -> None:
        setter(self.value)
```


#### Composite VO

```yaml
Rate:
  fields:
    _rate_period: PaymentPeriod
    _rate: ascetic_ddd.seedwork.domain.values.Money
  constraints:
    required: true
```

Discriminator: presence of the `fields` key (without `identity`).

Generated as a class with an exporter interface and a separate exporter module:

```python
class IRateExporter(metaclass=ABCMeta):
    @abstractmethod
    def set_rate_period(self, value) -> None: ...

    @abstractmethod
    def set_rate(self, value) -> None: ...

class Rate:
    def export(self, exporter: "IRateExporter") -> None:
        self._rate_period.export(exporter.set_rate_period)
        self._rate.export(exporter.set_rate)
```

Composite VO fields can reference aggregate-level VOs, primitives, and
inline dotted paths (e.g. `ascetic_ddd.seedwork.domain.values.Money`).
When multiple composite VOs depend on each other, the parser uses
topological sorting (Kahn's algorithm) to determine parse order.


#### Reference marker

Any VO can carry a `reference` key to document cross-aggregate or external
dependencies:

```yaml
SpecializationId:
  type: int
  reference: Specialization     # another aggregate in this context

UserId:
  type: int
  reference: external           # external bounded context
```

The `reference` value is stored as metadata; the scaffold does not follow it.


(imported-vo)=
#### Imported VO

There are two ways to reference VOs from external packages or other
aggregates:

**1. Inline dotted path in fields (preferred).** Use a dotted path directly
as the field type — no VO declaration needed:

```yaml
fields:
  _rate: ascetic_ddd.seedwork.domain.values.Money      # absolute
  _specialization_ids: list[.specialization.values.SpecializationId]  # relative
```

The class name is the last path segment. The import module is derived by
converting the class name to snake_case. With `--package app.jobs`, the
relative path generates:

```python
from app.jobs.domain.specialization.values.specialization_id import SpecializationId
```

**2. Explicit `import` key on VO declaration.** Use the `import` key with
`package.ClassName` format:

```yaml
TimeRange:
  import: ascetic_ddd.seedwork.domain.values.TimeRange
```

When `import` is specified, the scaffold does not generate a file for this VO.
The module path is derived from the class name:
`ascetic_ddd.seedwork.domain.values.TimeRange` →
`from ascetic_ddd.seedwork.domain.values.time_range import TimeRange`.

**Relative imports.** A `.` prefix resolves relative to the `domain` package
(i.e. `{package_name}.domain`). This works both in inline dotted paths and
in the `import` key.

The `import` key can be combined with other keys. For instance, a composite
imported VO (`import` + `fields`) will also import its exporter interface
and exporter class from the external package, following the same naming
convention as locally generated composite VOs.


### Constraints reference

| Key | Applies to | Default | Description |
|-----|------------|---------|-------------|
| `required` | any VO | `false` | Value must not be null |
| `blank` | string VO | `true` | Empty / whitespace-only is allowed |
| `max_length` | string VO | `0` (no limit) | Maximum string length |

### Maps reference

The `map` key accepts a list of mapping names applied to the value on init:

| Map | Applies to | Description |
|-----|------------|-------------|
| `strip` | string VO | Strip leading/trailing whitespace |


### Entities

Entities are child objects owned by an aggregate. They can hold their own
value objects, fields, and even nested entities (recursive):

```yaml
entities:
  Experience:
    fields:
      resume_id: .resume.values.ResumeId
      company_name: CompanyName
      date_range: TimeRange
    value_objects:
      CompanyName:
        type: str
        constraints:
          blank: false
          max_length: 255
      TimeRange:
        import: ascetic_ddd.seedwork.domain.values.TimeRange
```

**Collection entities** are referenced from aggregate fields via `list[EntityName]`.
They generate `add_*` methods on the aggregate exporter, an `_experience = []`
initialization in `_make_empty`, and list iteration in `export`:

```yaml
fields:
  _experience: list[Experience]
```

**Single entities** are referenced directly by name. They generate `set_*`
methods (not `add_*`), `None` initialization, and direct assignment:

```yaml
fields:
  _profile: SpecializationProfile
```

Entity fields can reference VOs from the parent aggregate scope via inline
dotted paths (e.g. `.resume.values.ResumeId`). Each entity generates its
own directory with the entity class, exporter, reconstitutor, and a
`values/` subdirectory.


### Domain Events

```yaml
domain_events:
  ResumeCreated:
    fields:
      aggregate_id: ResumeId
      user_id: UserId
      title: Title
      event_version: 1           # metadata (default: 1), not a domain field
```

Generated as frozen dataclasses extending `PersistentDomainEvent`.
Each event gets an exporter interface and a separate exporter module.

The special key `event_version` inside `fields` is extracted as metadata and
excluded from the domain fields list.


### Command derivation

Commands are derived automatically from domain events by suffix:

| Event class name | Derived command |
|---|---|
| `ResumeCreated` | `CreateResume` |
| `ResumeUpdated` | `UpdateResume` |
| `ResumeDeleted` | `DeleteResume` |

Command fields are the same as the event fields, but all VO types are mapped
to their primitive equivalents. Domain types do not leak into the application
layer:

```python
@dataclass(frozen=True, kw_only=True)
class CreateResumeCommand:
    aggregate_id: int         # not ResumeId
    user_id: int              # not UserId
    title: str                # not Title
    command_version: int = 1
```

Primitive mapping rules:

| VO kind | Primitive type |
|---|---|
| Identity | base type (`int`, `str`, `uuid`) |
| String | `str` |
| Enum | `str` |
| Composite | `dict` |


## Generated Structure

For a model with aggregates `Resume` and `Specialization`, package `app.jobs`:

```
output/
  domain/
    resume/
      __init__.py
      resume.py                          # aggregate root
      resume_exporter.py                 # IResumeExporter implementation
      resume_reconstitutor.py            # IResumeReconstitutor implementation
      values/
        __init__.py                      # re-exports all VOs
        resume_id.py                     # identity VO
        title.py                         # string VO with validation
        rate.py                          # composite VO
        rate_exporter.py                 # composite VO exporter
        employment_type.py               # enum VO
        ...
      events/
        __init__.py
        resume_created.py                # frozen dataclass
        resume_created_exporter.py       # event exporter
      experience/                        # collection entity
        __init__.py
        experience.py
        experience_exporter.py
        experience_reconstitutor.py
        values/
          __init__.py
          company_name.py
    specialization/
      __init__.py
      specialization.py
      specialization_exporter.py
      specialization_reconstitutor.py
      values/
        ...
      specialization_profile/            # single entity
        __init__.py
        specialization_profile.py
        specialization_profile_exporter.py
        specialization_profile_reconstitutor.py
        values/
          __init__.py
  application/
    __init__.py
    commands/
      __init__.py                        # re-exports all commands
      create_resume_command.py           # frozen dataclass
      create_resume_command_handler.py   # async handler stub
```


## Generated Code Patterns

### Aggregate root

The aggregate extends `EventiveEntity[PersistentDomainEvent]` and
`VersionedAggregate`. It exposes its state exclusively through the
exporter/reconstitutor interfaces — no getters:

```python
class Resume(EventiveEntity[PersistentDomainEvent], VersionedAggregate):

    def export(self, exporter: "IResumeExporter") -> None:
        super().export(exporter)
        exporter.set_title(self._title)
        for item in self._specialization_ids:
            exporter.add_specialization_id(item)

    def _import(self, provider: "IResumeReconstitutor") -> None:
        super()._import(provider)
        self._title = provider.title()
        self._specialization_ids = list(provider.specialization_ids())

    @classmethod
    def reconstitute(cls, reconstitutor) -> typing.Self:
        return super().reconstitute(reconstitutor)
```


### Exporter interface

Scalar fields get `set_*` methods. Collection fields get `add_*` methods
with the field name singularized (`specialization_ids` -> `add_specialization_id`):

```python
class IResumeExporter(IVersionedAggregateExporter, metaclass=ABCMeta):

    @abstractmethod
    def set_title(self, value) -> None:
        raise NotImplementedError

    @abstractmethod
    def add_specialization_id(self, value) -> None:
        raise NotImplementedError
```

### Reconstitutor interface

```python
class IResumeReconstitutor(IVersionedAggregateReconstitutor, metaclass=ABCMeta):

    @abstractmethod
    def title(self):
        raise NotImplementedError

    @abstractmethod
    def specialization_ids(self):
        raise NotImplementedError
```


### Value Object export

Single-field VOs use a setter callback — the VO controls what gets exported:

```python
class Title:
    def export(self, setter: typing.Callable[[str], None]) -> None:
        setter(self._value)
```

Composite VOs use an exporter interface with one method per field:

```python
class Rate:
    def export(self, exporter: "IRateExporter") -> None:
        self._rate_period.export(exporter.set_rate_period)
        self._rate.export(exporter.set_rate)
```


### Command handler

Generated as an async stub raising `NotImplementedError`:

```python
class CreateResumeCommandHandler:
    async def __call__(self, command: CreateResumeCommand) -> typing.Any:
        raise NotImplementedError
```


## Architecture

```
YAML file
    │
    ▼
ModelParser              parser.py      YAML → BoundedContextModel
    │
    ▼
BoundedContextModel      model.py       dataclasses (TypeRef hierarchy)
    │
    ▼
RenderWalker             renderer.py    walks model, renders Jinja2 templates
    │
    ▼
*.py files               templates/     22 Jinja2 templates
```


### Model (`model.py`)

**TypeRef hierarchy** — every field type is represented by a `TypeRef`
subclass, enabling polymorphic dispatch without enums:

```
TypeRef (base)
├── PrimitiveType(name)         # bool, int, str, datetime, ...
├── VoRef(vo)                   # reference to ValueObjectDef
├── EntityRef(entity)           # reference to EntityDef
└── CollectionType(kind, element: TypeRef)  # list[T], tuple[T, ...]
```

**ValueObjectDef hierarchy** — VO kind is determined by class type,
not by an enum:

```
ValueObjectDef (base)
├── SimpleVoDef           # string-like VO with constraints
├── IdentityVoDef         # identity VO (IntIdentity, StrIdentity, ...)
├── EnumVoDef             # enum VO (str, Enum)
└── CompositeVoDef        # composite VO with inner fields
```

Jinja2 templates dispatch on VO type via custom tests:
`vo is composite_vo`, `vo is enum_vo`.

The renderer dispatches template selection via `VO_TEMPLATE_MAP[type(vo)]`.

**CollectionKind** — `list`, `tuple` (enum with `str` mixin).

Core dataclasses form a tree:

```
BoundedContextModel
├── external_value_objects: list[ValueObjectDef]
└── aggregates: list[AggregateDef]
    ├── fields: list[FieldDef]
    │   └── type_ref: TypeRef
    ├── value_objects: list[ValueObjectDef]  (subclass per kind)
    ├── entities: list[EntityDef]
    │   ├── fields: list[FieldDef]
    │   ├── value_objects: list[ValueObjectDef]
    │   └── entities: list[EntityDef]        (recursive)
    ├── domain_events: list[DomainEventDef]
    │   └── fields: list[FieldDef]
    └── commands: list[CommandDef]           (derived from events)
        └── fields: list[FieldDef]
```


### Parser (`parser.py`)

`ModelParser` class with `_vo_map` and `_entity_map` as instance state —
maps class names to their definitions within the current scope.

**Scope isolation** (push/pop pattern):

- Composite VO fields — `_vo_map` is shallow-copied so inner fields can
  reference aggregate-level VOs but additions don't leak outward.
- Entity parsing — `_vo_map` and `_entity_map` are shallow-copied; entity
  VOs are added to the copy.
- External references — parsed with a separate empty `_vo_map`.

**Two-pass VO parsing with topological sort:**

1. Non-composite VOs are parsed first (identity, simple, enum).
2. Composite VOs are topologically sorted by field dependencies (Kahn's
   algorithm) and parsed in dependency order. Circular dependencies raise
   `ValueError`.

This ensures composite VOs can reference other composite VOs regardless of
declaration order in YAML.

**Type resolution** (`_resolve_type` / `_resolve_element_type`):

- Primitives → `PrimitiveType`
- Dotted paths (contain `.`) → `_resolve_import_ref` creates or updates
  a synthetic VO, returns `VoRef`
- Entity names → `EntityRef`
- Known VO names → `VoRef`
- Collection wrappers (`list[T]`, `tuple[T, ...]`) → `CollectionType`
  wrapping the resolved element type

**VO classification** follows a priority chain:

1. Has `identity` key → `IdentityVoDef`
2. `type` starts with `Enum[` → `EnumVoDef`
3. Has `fields` key → `CompositeVoDef`
4. Otherwise → `SimpleVoDef`

YAML validation checks allowed keys at four levels (top-level, aggregate,
entity, value object) and raises `ValueError` with the offending key names.

Public facade:

```python
from ascetic_ddd.cli.scaffold.parser import parse_yaml

model = parse_yaml("domain-model.yaml")
```


### Renderer (`renderer.py`)

`RenderWalker` class with `_visit_X` methods, modeled after `EvaluateVisitor`
from `ascetic_ddd.faker.domain.query`. Per-aggregate state is captured in an
`_AggregateContext` dataclass (package path, directories, used VOs, field
lists).

All VO import paths (relative `.` prefixes) are resolved to absolute paths
by `_resolve_vo_imports` before template rendering — for aggregate `used_vos`,
`value_objects`, and domain event `used_vos` alike. Templates receive
pre-resolved absolute paths and use them directly.

Walk order:

```
BoundedContextModel
└── AggregateDef                _visit_aggregate()
    ├── ValueObjectDef          _visit_value_objects()
    │   └── [composite]         + exporter module
    ├── values/__init__
    ├── EntityDef               _visit_entities() → _visit_entity()
    │   ├── entity VOs          _visit_value_object()
    │   ├── values/__init__
    │   ├── {entity}.py
    │   ├── {entity}_exporter.py
    │   ├── {entity}_reconstitutor.py
    │   ├── __init__.py
    │   └── [nested entities]   (recursive)
    ├── _visit_aggregate_module()
    │   ├── {agg}.py
    │   ├── {agg}_exporter.py
    │   ├── {agg}_reconstitutor.py
    │   └── __init__.py
    ├── DomainEventDef          _visit_domain_event()
    │   ├── {event}.py
    │   └── {event}_exporter.py
    ├── events/__init__
    └── CommandDef              _visit_command()
        ├── {cmd}_command.py
        └── {cmd}_command_handler.py
```

All rendering goes through `_render_template(tpl_name, path, **kwargs)` —
a single method that loads the Jinja2 template, renders, writes the file,
and appends the path to the generated files list.

Public facade:

```python
from ascetic_ddd.cli.scaffold.renderer import render_bounded_context

files = render_bounded_context(model, "./output", "app.jobs")
```


### Naming (`naming.py`)

Pure functions for name transformations:

| Function | Example |
|---|---|
| `camel_to_snake` | `ResumeCreated` -> `resume_created` |
| `strip_underscore_prefix` | `_id` -> `id` |
| `is_collection_type` | `list[X]` -> `True` |
| `extract_inner_type` | `list[SpecializationId]` -> `SpecializationId`, `list[.pkg.Cls]` -> `.pkg.Cls` |
| `collection_kind` | `tuple[X, ...]` -> `CollectionKind.TUPLE` |
| `is_primitive_type` | `datetime` -> `True`, `ResumeId` -> `False` |


(templates)=
### Templates

22 Jinja2 templates under `ascetic_ddd/cli/scaffold/templates/`:

| Path | Generates |
|------|-----------|
| `_macros.j2` | Shared macro: `vo_imports` |
| `_field_macros.j2` | Shared macros: `exporter_method`, `reconstitutor_method`, `export_field`, `import_field` |
| `domain/aggregate.py.j2` | Aggregate root + interfaces |
| `domain/aggregate_exporter.py.j2` | Aggregate exporter |
| `domain/aggregate_reconstitutor.py.j2` | Aggregate reconstitutor |
| `domain/__init__.py.j2` | Aggregate / entity package |
| `domain/values/identity_vo.py.j2` | Identity VO (extends `*Identity` base) |
| `domain/values/simple_vo.py.j2` | String VO with validation |
| `domain/values/enum_vo.py.j2` | Enum VO (extends `str, Enum`) |
| `domain/values/composite_vo.py.j2` | Composite VO with exporter interface |
| `domain/values/composite_vo_exporter.py.j2` | Composite VO exporter |
| `domain/values/__init__.py.j2` | Values package re-exports |
| `domain/entity/entity.py.j2` | Entity class + interfaces |
| `domain/entity/entity_exporter.py.j2` | Entity exporter |
| `domain/entity/entity_reconstitutor.py.j2` | Entity reconstitutor |
| `domain/events/domain_event.py.j2` | Domain event + exporter interface |
| `domain/events/domain_event_exporter.py.j2` | Event exporter |
| `domain/events/__init__.py.j2` | Events package |
| `application/commands/command.py.j2` | Command dataclass |
| `application/commands/command_handler.py.j2` | Async handler stub |
| `application/commands/__init__.py.j2` | Commands package re-exports |
| `application/__init__.py.j2` | Application package |

Jinja2 environment settings: `trim_blocks`, `lstrip_blocks`,
`keep_trailing_newline`. Custom filters: `singularize` (plural -> singular),
`pluralize` (singular -> plural), `snake` (CamelCase -> snake_case).
Custom tests: `composite_vo`, `enum_vo` (for VO type dispatch in templates).


(custom-templates)=
## Custom templates

The `-t` / `--templates` flag specifies a directory with custom Jinja2
templates. Templates found in this directory take priority over the built-in
ones; any template not present falls back to the default.

```bash
python -m ascetic_ddd.cli scaffold \
    -i domain-model.yaml \
    -o ./output \
    -p app.jobs \
    -t ./my-templates
```

To override a single template, create a file at the same relative path.
For example, to customize string VO generation:

```
my-templates/
  domain/
    values/
      string_vo.py.j2
```

The custom template receives the same context variables as the original
(see [Templates](#templates) for the full list). All other templates
continue to use the built-in versions.

Programmatic usage:

```python
from ascetic_ddd.cli.scaffold import scaffold

scaffold("domain-model.yaml", "./output", "app.jobs",
         templates_dir="./my-templates")
```


## Limitations

- **Cross-aggregate VO sharing.** Each aggregate defines its own VOs.
  When two aggregates share a type (e.g. `SpecializationId`), use an inline
  dotted path in the field type:
  `_specialization_ids: list[.specialization.values.SpecializationId]`
  or an explicit `import` key on the VO definition
  (see [Imported VO](#imported-vo)).

- **No cyclic composite VO references.** Composite VOs are topologically
  sorted within each aggregate. Circular dependencies among composite VOs
  raise `ValueError`.

- **Command derivation is suffix-based.** Only `Created`, `Updated`,
  `Deleted` event suffixes are recognized. Events with other suffixes
  produce commands with the event name unchanged.

- **Composite VO reconstruction is partial.** The generated reconstitutor
  includes TODOs for composite VO fields that must be filled in manually.


## Tests

```bash
python -m unittest discover -s ascetic_ddd/cli/scaffold/tests -p "test_*.py" -v
```

| Module | What it covers |
|---|---|
| `test_naming.py` | CamelCase conversion, collection detection, primitive classification |
| `test_parser.py` | YAML parsing, VO classification, type resolution, inline dotted paths, entity parsing, command derivation, validation errors |
| `test_renderer.py` | Generated file contents, directory structure, entity rendering, custom templates, no f-strings in output |
| `test_scaffold.py` | End-to-end: YAML -> compilable Python files |
