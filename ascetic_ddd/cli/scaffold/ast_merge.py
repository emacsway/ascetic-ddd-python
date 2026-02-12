"""Additive AST merge: add missing elements from generated module to existing.

Never removes or modifies existing code — only adds missing imports,
classes, class members, and __init__ parameters.
"""
import ast


def merge_modules(existing, generated):
    """Merge generated module into existing (in-place, additive only).

    Returns existing module with missing elements added.
    """
    _add_missing_imports(existing, generated)
    _add_missing_definitions(existing, generated)
    return existing


# --- Imports ---


def _get_imported_names(module):
    """Return set of (module_name, imported_name) tuples.

    For ``import X``, module_name is None.
    """
    result = set()
    for node in module.body:
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                result.add((node.module, alias.name))
        elif isinstance(node, ast.Import):
            for alias in node.names:
                result.add((None, alias.name))
    return result


def _find_import_from(module, mod_name):
    """Find first ImportFrom node for the given module."""
    for node in module.body:
        if isinstance(node, ast.ImportFrom) and node.module == mod_name:
            return node
    return None


def _last_import_index(module):
    """Return index of last import statement, or -1."""
    idx = -1
    for i, node in enumerate(module.body):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            idx = i
    return idx


def _add_missing_imports(existing, generated):
    """Add imports from generated that don't exist in existing."""
    existing_set = _get_imported_names(existing)
    insert_idx = _last_import_index(existing) + 1

    for node in generated.body:
        if isinstance(node, ast.ImportFrom):
            missing = [
                alias for alias in node.names
                if (node.module, alias.name) not in existing_set
            ]
            if not missing:
                continue
            # Try to extend existing import from same module
            existing_node = _find_import_from(existing, node.module)
            if existing_node:
                for alias in missing:
                    existing_node.names.append(ast.alias(name=alias.name))
                    existing_set.add((node.module, alias.name))
            else:
                new_import = ast.ImportFrom(
                    module=node.module,
                    names=[ast.alias(name=a.name) for a in missing],
                    level=0,
                )
                existing.body.insert(insert_idx, new_import)
                insert_idx += 1
                for alias in missing:
                    existing_set.add((node.module, alias.name))

        elif isinstance(node, ast.Import):
            for alias in node.names:
                if (None, alias.name) not in existing_set:
                    existing.body.insert(
                        insert_idx,
                        ast.Import(names=[ast.alias(name=alias.name)]),
                    )
                    insert_idx += 1
                    existing_set.add((None, alias.name))


# --- Top-level definitions ---


def _add_missing_definitions(existing, generated):
    """Add missing classes and merge existing ones."""
    existing_classes = {
        node.name: node for node in existing.body
        if isinstance(node, ast.ClassDef)
    }

    for node in generated.body:
        if isinstance(node, ast.ClassDef):
            if node.name in existing_classes:
                _merge_class(existing_classes[node.name], node)
            else:
                existing.body.append(node)
        elif isinstance(node, ast.Assign):
            name = _assign_target_name(node)
            if name == '__all__':
                existing_node = _find_assign(existing, '__all__')
                if existing_node:
                    _merge_all_list(existing_node, node)
                else:
                    existing.body.append(node)


# --- Class merging ---


def _merge_class(existing_cls, generated_cls):
    """Add missing members from generated class to existing."""
    existing_methods = {
        node.name for node in existing_cls.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    existing_annotations = {
        node.target.id for node in existing_cls.body
        if isinstance(node, ast.AnnAssign)
        and isinstance(node.target, ast.Name)
    }

    # Insert point for annotations: before first method
    ann_insert_idx = 0
    for i, node in enumerate(existing_cls.body):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            ann_insert_idx = i
            break
    else:
        ann_insert_idx = len(existing_cls.body)

    added = 0
    for node in generated_cls.body:
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if node.target.id not in existing_annotations:
                existing_cls.body.insert(ann_insert_idx + added, node)
                added += 1
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name not in existing_methods:
                existing_cls.body.append(node)
            elif node.name == '__init__':
                existing_init = _find_method(existing_cls, '__init__')
                if existing_init:
                    _merge_init(existing_init, node)

    # Remove lone ``pass`` if real members were added
    _strip_pass(existing_cls)


def _merge_init(existing_init, generated_init):
    """Add missing parameters and self.X = X assignments to __init__."""
    existing_params = {arg.arg for arg in existing_init.args.args}

    # Insert new params before *args / **kwargs, or at end of args list
    insert_idx = len(existing_init.args.args)

    for arg in generated_init.args.args:
        if arg.arg not in existing_params and arg.arg != 'self':
            existing_init.args.args.insert(insert_idx, arg)
            insert_idx += 1

    # Add missing self._x = x assignments
    existing_self_attrs = _collect_self_assigns(existing_init)
    for stmt in generated_init.body:
        if isinstance(stmt, ast.Assign) and stmt.targets:
            target = stmt.targets[0]
            if (isinstance(target, ast.Attribute)
                    and isinstance(target.value, ast.Name)
                    and target.value.id == 'self'
                    and target.attr not in existing_self_attrs):
                existing_init.body.append(stmt)


def _collect_self_assigns(func):
    """Collect set of self.X attribute names from assignments in func body."""
    result = set()
    for stmt in func.body:
        if isinstance(stmt, ast.Assign):
            for target in stmt.targets:
                if (isinstance(target, ast.Attribute)
                        and isinstance(target.value, ast.Name)
                        and target.value.id == 'self'):
                    result.add(target.attr)
    return result


def _strip_pass(cls):
    """Remove ``pass`` statement if class has other members."""
    if len(cls.body) > 1:
        cls.body = [
            node for node in cls.body
            if not isinstance(node, ast.Pass)
        ]


# --- Helpers ---


def _find_method(cls, name):
    for node in cls.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name == name:
                return node
    return None


def _assign_target_name(node):
    if isinstance(node, ast.Assign) and node.targets:
        target = node.targets[0]
        if isinstance(target, ast.Name):
            return target.id
    return None


def _find_assign(module, name):
    for node in module.body:
        if _assign_target_name(node) == name:
            return node
    return None


def _merge_all_list(existing_node, generated_node):
    """Add missing names to __all__ list."""
    if not isinstance(existing_node.value, ast.List):
        return
    if not isinstance(generated_node.value, ast.List):
        return

    existing_names = set()
    for elt in existing_node.value.elts:
        if isinstance(elt, ast.Constant):
            existing_names.add(elt.value)

    for elt in generated_node.value.elts:
        if isinstance(elt, ast.Constant) and elt.value not in existing_names:
            existing_node.value.elts.append(elt)
            existing_names.add(elt.value)
