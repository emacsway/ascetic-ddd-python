import os
import py_compile
import shutil
import tempfile
import unittest

from ascetic_ddd.cli.scaffold import scaffold


YAML_PATH = os.path.join(os.path.dirname(__file__), 'domain-model.yaml')


class TestScaffoldEndToEnd(unittest.TestCase):
    def setUp(self):
        self.output_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.output_dir)

    def test_scaffold_generates_files(self):
        scaffold(YAML_PATH, self.output_dir, 'app.jobs')
        # Check key files exist
        self.assertTrue(os.path.exists(
            os.path.join(self.output_dir, 'domain', 'resume', 'resume.py'),
        ))
        self.assertTrue(os.path.exists(
            os.path.join(
                self.output_dir, 'application', 'commands',
                'create_resume_command.py',
            ),
        ))

    def test_generated_files_are_valid_python(self):
        scaffold(YAML_PATH, self.output_dir, 'app.jobs')
        errors = []
        for root, dirs, files in os.walk(self.output_dir):
            for name in files:
                if name.endswith('.py'):
                    path = os.path.join(root, name)
                    try:
                        py_compile.compile(path, doraise=True)
                    except py_compile.PyCompileError as e:
                        errors.append('%s: %s' % (path, e))
        self.assertEqual(errors, [], 'Compilation errors:\n' + '\n'.join(errors))


if __name__ == '__main__':
    unittest.main()
