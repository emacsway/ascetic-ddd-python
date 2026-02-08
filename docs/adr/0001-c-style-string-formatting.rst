ADR-0001: C-Style String Formatting
====================================

.. index:: ADR; string formatting, string formatting

Status
------
Accepted

Context
-------
Python offers multiple string formatting approaches: C-style (``%s``, ``%d``),
``.format()``, and f-strings. The project aims for potential portability to Go,
which uses ``fmt.Sprintf`` with C-style verbs (``%s``, ``%d``, ``%v``).

F-strings are Python-specific syntax with no equivalent in Go or most other
languages. ``.format()`` is also Python-specific.

Decision
--------
Use C-style string formatting exclusively throughout the codebase:

.. code-block:: python

   # Correct
   message = "Provider '%s' has no output." % self.provider_name
   log.info("Processing %d items for %s", count, name)

   # Incorrect — do not use
   message = f"Provider '{self.provider_name}' has no output."
   message = "Provider '{}' has no output.".format(self.provider_name)

Consequences
------------
- Formatting style maps directly to Go's ``fmt.Sprintf`` verbs
- Consistent with C, Go, and most compiled languages
- Slightly less readable than f-strings for complex expressions, but this
  encourages extracting expressions into named variables
- Logging calls benefit from lazy formatting (arguments are only formatted
  if the log level is enabled)
