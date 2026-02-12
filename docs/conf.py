# Configuration file for the Sphinx documentation builder.
#
# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

import os
import sys

# -- Path setup --------------------------------------------------------------
sys.path.insert(0, os.path.abspath('..'))

# -- Project information -----------------------------------------------------
project = 'ascetic-ddd'
copyright = '2026, Ivan Zakrevsky'
author = 'Ivan Zakrevsky'
release = '0.1.5'

# -- General configuration ---------------------------------------------------
extensions = [
    'sphinx.ext.autodoc',
    'sphinx.ext.autosummary',
    'sphinx.ext.intersphinx',
    'sphinx.ext.viewcode',
    'sphinx.ext.todo',
    'sphinx.ext.napoleon',
    'sphinx.ext.inheritance_diagram',
    'sphinx_immaterial',
    'sphinx_autodoc_typehints',

    'myst_parser',
    'sphinxcontrib.mermaid',
]

templates_path = ['_templates']
exclude_patterns = ['_build', 'Thumbs.db', '.DS_Store']

# -- Options for autodoc -----------------------------------------------------
autodoc_default_options = {
    'members': True,
    'undoc-members': True,
    'show-inheritance': True,
}
autodoc_member_order = 'bysource'
autodoc_typehints = 'description'
autosummary_generate = True

# Mock imports for packages that may not be installed during doc build
autodoc_mock_imports = [
    'psycopg',
    'psycopg_pool',
    'tortoise',
    'jsonpath2',
    'jsonpath_rfc9535',
    'hypothesis',
    'aiohttp',
    'dotenv',
    'dateutil',
    'requests',
    'scipy',
    'mimesis',
    'faker',
    'pydash',
    'sqlalchemy',
]

# -- Options for Napoleon (Google/NumPy docstrings) --------------------------
napoleon_google_docstring = True
napoleon_numpy_docstring = False

# -- Options for intersphinx -------------------------------------------------
intersphinx_mapping = {
    'python': ('https://docs.python.org/3', None),
}

# -- Options for MyST parser -------------------------------------------------
# Allows including .md files from the source tree
myst_enable_extensions = [
    'colon_fence',
    'deflist',
]

# -- Options for HTML output -------------------------------------------------
html_theme = 'sphinx_immaterial'
html_static_path = ['_static']
html_css_files = ['custom.css']
html_title = 'ascetic-ddd'

html_theme_options = {
    'icon': {
        'repo': 'fontawesome/brands/github',
    },
    'site_url': 'https://krew-solutions.github.io/ascetic-ddd-python/',
    'repo_url': 'https://github.com/krew-solutions/ascetic-ddd-python',
    'repo_name': 'ascetic-ddd-python',
    'social': [
        {
            'icon': 'fontawesome/brands/github',
            'link': 'https://github.com/krew-solutions/ascetic-ddd-python',
        },
        {
            'icon': 'fontawesome/brands/python',
            'link': 'https://pypi.org/project/ascetic-ddd/',
        },
    ],
    'edit_uri': 'blob/main/docs',
    'globaltoc_collapse': True,
    'features': [
        'navigation.expand',
        'navigation.sections',
        'navigation.top',
        'search.highlight',
        'search.share',
        'toc.follow',
        'toc.sticky',
        'content.code.copy',
    ],
    'palette': [
        {
            'media': '(prefers-color-scheme: light)',
            'scheme': 'default',
            'primary': 'indigo',
            'accent': 'light-blue',
            'toggle': {
                'icon': 'material/weather-night',
                'name': 'Switch to dark mode',
            },
        },
        {
            'media': '(prefers-color-scheme: dark)',
            'scheme': 'slate',
            'primary': 'indigo',
            'accent': 'light-blue',
            'toggle': {
                'icon': 'material/weather-sunny',
                'name': 'Switch to light mode',
            },
        },
    ],
    'toc_title_is_page_title': True,
}

# -- Suppress unresolvable TypeVar cross-reference warnings ------------------
suppress_warnings = ['ref.param']

# -- Options for todo extension ----------------------------------------------
todo_include_todos = True
