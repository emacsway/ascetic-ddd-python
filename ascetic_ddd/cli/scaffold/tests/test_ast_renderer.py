import os
import shutil
import tempfile
import unittest

from ascetic_ddd.cli.scaffold.parser import parse_yaml
from ascetic_ddd.cli.scaffold.renderer import (
    ast_render_bounded_context,
    render_bounded_context,
)


YAML_PATH = os.path.join(os.path.dirname(__file__), 'domain-model.yaml')


class TestAstRenderer(unittest.TestCase):
    """Tests for merge mode (ast_render_bounded_context)."""

    def setUp(self):
        self.output_dir = tempfile.mkdtemp()
        self.model = parse_yaml(YAML_PATH)

    def tearDown(self):
        shutil.rmtree(self.output_dir)

    def _read(self, *parts):
        path = os.path.join(self.output_dir, *parts)
        with open(path, 'r') as f:
            return f.read()

    def _write(self, content, *parts):
        path = os.path.join(self.output_dir, *parts)
        with open(path, 'w') as f:
            f.write(content)

    # --- first run (no existing files) ---

    def test_first_run_generates_files(self):
        """First run with merge=True must generate files normally."""
        files = ast_render_bounded_context(
            self.model, self.output_dir, 'app.jobs',
        )
        self.assertGreater(len(files), 0)
        content = self._read('domain', 'resume', 'values', 'title.py')
        self.assertIn('class Title', content)

    def test_first_run_matches_normal_render(self):
        """With no existing files, merge mode produces same file set."""
        normal_dir = tempfile.mkdtemp()
        try:
            normal_files = render_bounded_context(
                self.model, normal_dir, 'app.jobs',
            )
            merge_files = ast_render_bounded_context(
                self.model, self.output_dir, 'app.jobs',
            )
            # Same number of files generated
            self.assertEqual(len(normal_files), len(merge_files))
        finally:
            shutil.rmtree(normal_dir)

    # --- merge preserves user code ---

    def test_merge_preserves_user_method(self):
        """User-added methods must survive re-generation with merge."""
        # First run: generate files
        ast_render_bounded_context(
            self.model, self.output_dir, 'app.jobs',
        )

        # User adds a custom method to Resume aggregate
        path = os.path.join(
            self.output_dir, 'domain', 'resume', 'resume.py',
        )
        content = self._read('domain', 'resume', 'resume.py')
        # Insert a user method into the Resume class
        content = content.replace(
            'class Resume(',
            'class Resume(\n'
            '    def custom_business_logic(self):\n'
            '        return "user code"\n\n    # original\nclass Resume(',
        )
        # Simpler approach: just append to file via AST
        import ast
        tree = ast.parse(self._read('domain', 'resume', 'resume.py'))
        for node in tree.body:
            if isinstance(node, ast.ClassDef) and node.name == 'Resume':
                user_method = ast.parse(
                    'class _T:\n'
                    '    def custom_business_logic(self):\n'
                    '        return "user code"'
                ).body[0].body[0]
                node.body.append(user_method)
        ast.fix_missing_locations(tree)
        self._write(
            ast.unparse(tree) + '\n',
            'domain', 'resume', 'resume.py',
        )

        # Second run: merge
        ast_render_bounded_context(
            self.model, self.output_dir, 'app.jobs',
        )

        merged = self._read('domain', 'resume', 'resume.py')
        self.assertIn('custom_business_logic', merged)
        self.assertIn('user code', merged)
        # Original generated methods still present
        self.assertIn('def export(self', merged)

    def test_merge_preserves_user_method_body(self):
        """Existing method bodies must not be overwritten by generated code."""
        # First run
        ast_render_bounded_context(
            self.model, self.output_dir, 'app.jobs',
        )

        # User modifies export method body in Title VO
        import ast
        path_parts = ('domain', 'resume', 'values', 'title.py')
        tree = ast.parse(self._read(*path_parts))
        for node in tree.body:
            if isinstance(node, ast.ClassDef) and node.name == 'Title':
                for member in node.body:
                    if (isinstance(member, ast.FunctionDef)
                            and member.name == 'export'):
                        # Replace body with user's custom logic
                        member.body = ast.parse(
                            'logger.info("exporting")\nsetter(self._value)'
                        ).body
        ast.fix_missing_locations(tree)
        self._write(ast.unparse(tree) + '\n', *path_parts)

        # Second run: merge
        ast_render_bounded_context(
            self.model, self.output_dir, 'app.jobs',
        )

        merged = self._read(*path_parts)
        # User's modified body preserved (not overwritten)
        self.assertIn('logger.info', merged)

    # --- merge adds missing elements ---

    def test_merge_adds_missing_import(self):
        """New imports from re-generated code must be added."""
        # First run
        ast_render_bounded_context(
            self.model, self.output_dir, 'app.jobs',
        )

        # User removes an import from resume.py
        import ast
        path_parts = ('domain', 'resume', 'resume.py')
        tree = ast.parse(self._read(*path_parts))
        # Remove first ImportFrom node
        original_imports = [
            n for n in tree.body if isinstance(n, ast.ImportFrom)
        ]
        if original_imports:
            tree.body.remove(original_imports[0])
        ast.fix_missing_locations(tree)
        removed_module = original_imports[0].module if original_imports else ''
        self._write(ast.unparse(tree) + '\n', *path_parts)

        # Second run: merge — must restore missing import
        ast_render_bounded_context(
            self.model, self.output_dir, 'app.jobs',
        )

        merged = self._read(*path_parts)
        if removed_module:
            self.assertIn(removed_module, merged)

    def test_merge_adds_missing_class(self):
        """If user deletes a class, merge adds it back."""
        # First run
        ast_render_bounded_context(
            self.model, self.output_dir, 'app.jobs',
        )

        # Read exporter, remove the class, write back
        import ast
        path_parts = ('domain', 'resume', 'resume_exporter.py')
        tree = ast.parse(self._read(*path_parts))
        classes = [n for n in tree.body if isinstance(n, ast.ClassDef)]
        class_name = classes[0].name if classes else ''
        if classes:
            tree.body.remove(classes[0])
        ast.fix_missing_locations(tree)
        self._write(ast.unparse(tree) + '\n', *path_parts)

        # Second run: merge
        ast_render_bounded_context(
            self.model, self.output_dir, 'app.jobs',
        )

        merged = self._read(*path_parts)
        if class_name:
            self.assertIn(class_name, merged)

    # --- skip-unchanged optimization ---

    def test_non_existing_file_created(self):
        """Merge mode creates files that don't exist yet."""
        files = ast_render_bounded_context(
            self.model, self.output_dir, 'app.jobs',
        )
        for f in files:
            self.assertTrue(
                os.path.exists(f), 'File not created: %s' % f,
            )


class TestAstScaffold(unittest.TestCase):
    """Test the ast_scaffold public facade."""

    def test_ast_scaffold_runs(self):
        output_dir = tempfile.mkdtemp()
        try:
            from ascetic_ddd.cli.scaffold import ast_scaffold
            ast_scaffold(YAML_PATH, output_dir, 'app.jobs')
            # Verify at least one file exists
            resume_py = os.path.join(
                output_dir, 'domain', 'resume', 'resume.py',
            )
            self.assertTrue(os.path.exists(resume_py))
        finally:
            shutil.rmtree(output_dir)


if __name__ == '__main__':
    unittest.main()
