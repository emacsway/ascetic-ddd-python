Architecture Decisions
======================

.. index:: architecture decision records, ADR

Key architecture decisions are documented as Architecture Decision Records (ADRs).

See the full :doc:`/adr/index` section for all recorded decisions.

Summary of Key Decisions
------------------------

- :doc:`/adr/0001-c-style-string-formatting` — Use C-style ``%s``/``%d`` formatting
  exclusively, no f-strings or ``.format()``
- :doc:`/adr/0002-sociable-unit-tests` — Test with real collaborators, mocks only
  for external dependencies
- :doc:`/adr/0003-go-portability` — Design choices that enable potential Go port
- :doc:`/adr/0004-diamond-problem-in-provider-topology` — Handling diamond
  dependencies in faker provider topology
- :doc:`/adr/0005-dag-change-manager-for-provider-populate-topology` — DAG
  Change Manager (Mediator) for controlling provider populate order
