Installation
============

.. index:: installation, pip, Poetry

Requirements
------------

- Python >= 3.11
- PostgreSQL (for persistence layer)

Install from PyPI
-----------------

.. code-block:: bash

   pip install ascetic-ddd

Install with Poetry
-------------------

.. code-block:: bash

   poetry add ascetic-ddd

Development Installation
------------------------

Clone the repository and install with development dependencies:

.. code-block:: bash

   git clone https://github.com/krew-solutions/ascetic-ddd-python.git
   cd ascetic-ddd-python
   poetry install --with dev

Building Documentation
----------------------

To build the documentation locally:

.. code-block:: bash

   poetry install --with docs
   cd docs
   make html

The output will be in ``docs/_build/html/``.
