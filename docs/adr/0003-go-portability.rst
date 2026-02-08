ADR-0003: Go Portability Considerations
=======================================

.. index:: ADR; Go portability, portability

Status
------
Accepted

Context
-------
The project may be ported to Go in the future. Certain Python idioms and
patterns do not translate well to Go's type system and concurrency model.

Decision
--------
Adopt design choices that facilitate a potential Go port:

1. **C-style formatting** (see :doc:`0001-c-style-string-formatting`)
2. **Interface-based design**: Define explicit interfaces (ABCs) that map to
   Go interfaces
3. **Composition over inheritance**: Prefer composition patterns that translate
   to Go's embedding
4. **Explicit error handling**: Prefer natural exceptions (``IndexError``,
   ``KeyError``) over custom exception hierarchies — these map to Go's
   explicit error returns
5. **No metaclass magic**: Avoid Python-specific metaclass tricks that have
   no Go equivalent

Consequences
------------
- Code structure maps more naturally to Go's type system
- Some Pythonic patterns (decorators, metaclasses, dynamic dispatch) are
  avoided even when they might be more concise
- Interface definitions serve as clear contracts for both Python and Go
  implementations
- The codebase may feel less "Pythonic" but gains cross-language clarity
