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

- Value objects are classified by kind (identity, string, enum, composite),
  each with its own validation rules and generated structure.
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
      _specialization_ids: list[SpecializationId]
      _rate: Rate
      _employment_types: list[EmploymentType]
      _work_formats: list[WorkFormat]
      _show_reputation: bool
      _created_at: datetime
      _updated_at: datetime
      _is_active: bool

    value_objects:
      ResumeId:                          # identity VO
        type: int
        identity: transient

      UserId:                            # string VO with external reference
        type: int
        reference: external
        constraints:
          required: true

      SpecializationId:                  # string VO with cross-aggregate reference
        type: int
        reference: Specialization
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
          _rate: Money
        constraints:
          required: true

      Money:                             # imported VO (no file generated)
        import: ascetic_ddd.seedwork.domain.values.money

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
          specialization_ids: tuple[SpecializationId, ...]
          rate: Rate
          employment_types: tuple[EmploymentType, ...]
          work_formats: tuple[WorkFormat, ...]
          show_reputation: bool
          created_at: datetime
          is_active: bool
          event_version: 1               # metadata, not a domain field

  Specialization:                        # minimal aggregate — only identity
    fields:
      _id: SpecializationId

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

This model generates 29 files across two aggregates, including value objects
of all four kinds (identity, string, enum, composite), a domain event with
exporter, and a derived command with handler.


## YAML Schema

### Top-level structure

```yaml
aggregates:               # required, at least one
  AggregateName:
    fields: { ... }
    value_objects: { ... }
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

Fields describe the internal state of an aggregate, a composite VO, or a
domain event. Declared as `name: type` pairs.

```yaml
fields:
  _id: ResumeId                              # VO reference
  _title: Title                              # VO reference
  _specialization_ids: list[SpecializationId] # collection of VOs
  _employment_types: list[EmploymentType]
  _show_reputation: bool                     # primitive
  _created_at: datetime                      # primitive
```

Underscore prefix (`_id`) denotes private aggregate state.
The prefix is stripped for parameter names in constructors and exporters
(`_id` -> `id`, `_specialization_ids` -> `specialization_ids`).

Primitive types: `bool`, `int`, `str`, `float`, `datetime`, `Decimal`.

Collection types: `list[T]`, `tuple[T, ...]`.
Collections generate `add_*` (singular form) methods on exporter interfaces
instead of `set_*`.


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
    _rate: Money
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

Composite VO fields are isolated from the aggregate's VO scope — they can
only reference primitives or types defined within the composite itself.


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

```yaml
Money:
  import: ascetic_ddd.seedwork.domain.values.money
```

Discriminator: presence of the `import` key.

When `import` is specified, the scaffold does not generate a file for this VO.
Instead, it uses the given module path in import statements:

```python
from ascetic_ddd.seedwork.domain.values.money import Money
```

This is useful for value objects that already exist in a shared library
(e.g. seedwork) and should not be re-generated.

The `import` key can be combined with other keys. For instance, a composite
imported VO (`import` + `fields`) will also import its exporter interface
and exporter class from the external package, following the same naming
convention as locally generated composite VOs:

```yaml
Money:
  import: ascetic_ddd.seedwork.domain.values.money
  fields:
    _amount: Decimal
    _currency: str
```

Generates:

```python
from ascetic_ddd.seedwork.domain.values.money import Money, IMoneyExporter
from ascetic_ddd.seedwork.domain.values.money_exporter import MoneyExporter
```


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
    specialization/
      ...                                # same structure
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
BoundedContextModel      model.py       dataclasses + enums
    │
    ▼
RenderWalker             renderer.py    walks model, renders Jinja2 templates
    │
    ▼
*.py files               templates/     17 Jinja2 templates
```


### Model (`model.py`)

Enums use `(str, Enum)` mixin so Jinja2 templates can compare them
with plain strings:

- `VoKind` — `identity`, `string`, `composite`, `enum`
- `DispatchKind` — `primitive`, `simple_vo`, `composite_vo`,
  `collection_simple_vo`, `collection_composite_vo`
- `CollectionKind` — `list`, `tuple`

Core dataclasses form a tree:

```
BoundedContextModel
├── external_value_objects: list[ValueObjectDef]
└── aggregates: list[AggregateDef]
    ├── fields: list[FieldDef]
    ├── value_objects: list[ValueObjectDef]
    │   ├── constraints: ConstraintsDef
    │   ├── map_def: MapDef
    │   ├── fields: list[FieldDef]       (composite only)
    │   └── enum_values: dict[str, str]  (enum only)
    ├── domain_events: list[DomainEventDef]
    │   └── fields: list[FieldDef]
    └── commands: list[CommandDef]        (derived from events)
        └── fields: list[FieldDef]
```


### Parser (`parser.py`)

`ModelParser` class with `_vo_map` as instance state — maps VO class names to
their definitions within the current aggregate scope.

The push/pop pattern isolates VO resolution scope:

- Composite VO fields — `_vo_map` is temporarily emptied so inner fields
  cannot reference aggregate-level VOs.
- External references — parsed with a separate empty `_vo_map`.

VO classification follows a priority chain:

1. Has `identity` key → `VoKind.IDENTITY`
2. `type` starts with `Enum[` → `VoKind.ENUM`
3. Has `fields` key → `VoKind.COMPOSITE`
4. Otherwise → `VoKind.STRING`

YAML validation checks allowed keys at three levels (top-level, aggregate,
value object) and raises `ValueError` with the offending key names.

Public facade:

```python
from ascetic_ddd.cli.scaffold.parser import parse_yaml

model = parse_yaml("domain-model.yaml")
```


### Renderer (`renderer.py`)

`RenderWalker` class with `_visit_X` methods, modeled after `EvaluateVisitor`
from `ascetic_ddd.faker.domain.query`. Per-aggregate state is captured in an
`_AggregateContext` dataclass (package path, directories, VO map, imports,
field lists).

Walk order:

```
BoundedContextModel
└── AggregateDef              _visit_aggregate()
    ├── ValueObjectDef        _visit_value_object()
    │   └── [composite]       _visit_composite_vo_exporter()
    ├── values/__init__
    ├── aggregate module      _visit_aggregate_module()
    │   ├── aggregate.py
    │   ├── exporter.py
    │   ├── reconstitutor.py
    │   └── __init__.py
    ├── DomainEventDef        _visit_domain_event()
    │   ├── event.py
    │   └── event_exporter.py
    ├── events/__init__
    └── CommandDef            _visit_command()
        ├── command.py
        └── command_handler.py
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
| `extract_inner_type` | `list[SpecializationId]` -> `SpecializationId` |
| `collection_kind` | `tuple[X, ...]` -> `CollectionKind.TUPLE` |
| `is_primitive_type` | `datetime` -> `True`, `ResumeId` -> `False` |


### Templates

17 Jinja2 templates under `ascetic_ddd/cli/scaffold/templates/`:

| Path | Generates |
|------|-----------|
| `domain/values/identity_vo.py.j2` | Identity VO (extends `*Identity` base) |
| `domain/values/string_vo.py.j2` | String VO with validation |
| `domain/values/enum_vo.py.j2` | Enum VO (extends `str, Enum`) |
| `domain/values/composite_vo.py.j2` | Composite VO with exporter interface |
| `domain/values/composite_vo_exporter.py.j2` | Composite VO exporter |
| `domain/values/__init__.py.j2` | Values package re-exports |
| `domain/aggregate/aggregate.py.j2` | Aggregate root + interfaces |
| `domain/aggregate/aggregate_exporter.py.j2` | Aggregate exporter |
| `domain/aggregate/aggregate_reconstitutor.py.j2` | Aggregate reconstitutor |
| `domain/aggregate/__init__.py.j2` | Aggregate package |
| `domain/events/domain_event.py.j2` | Domain event + exporter interface |
| `domain/events/domain_event_exporter.py.j2` | Event exporter |
| `domain/events/__init__.py.j2` | Events package |
| `application/commands/command.py.j2` | Command dataclass |
| `application/commands/command_handler.py.j2` | Async handler stub |
| `application/commands/__init__.py.j2` | Commands package re-exports |
| `application/__init__.py.j2` | Application package |

Jinja2 environment settings: `trim_blocks`, `lstrip_blocks`,
`keep_trailing_newline`. Custom filters: `singularize` (naive plural -> singular),
`snake` (CamelCase -> snake_case).


## Limitations

- **No cross-aggregate VO sharing.** Each aggregate defines its own VOs.
  Shared types (e.g. `SpecializationId` used by both `Resume` and
  `Specialization`) must be duplicated in each aggregate's `value_objects`.
  The `reference` key documents the relationship but is not followed.
  External VOs from shared libraries can be referenced via `import` key
  (see [Imported VO](#imported-vo)).

- **No cyclic references.** The YAML schema is a tree. If cross-aggregate
  VO references are needed in the future, topological sorting (e.g.
  Tarjan's SCC from `ascetic_ddd.graph.scc`) would be required to detect
  cycles and determine render order.

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
| `test_parser.py` | YAML parsing, VO classification, command derivation, validation errors |
| `test_renderer.py` | Generated file contents, directory structure, no f-strings in output |
| `test_scaffold.py` | End-to-end: YAML -> compilable Python files |
