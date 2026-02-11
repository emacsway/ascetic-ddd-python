import os
import py_compile
import re
import shutil
import tempfile
import unittest

from ascetic_ddd.cli.scaffold.ast_renderer import ast_render_bounded_context
from ascetic_ddd.cli.scaffold.parser import parse_yaml


YAML_PATH = os.path.join(os.path.dirname(__file__), 'domain-model.yaml')


class TestAstRenderer(unittest.TestCase):
    def setUp(self):
        self.output_dir = tempfile.mkdtemp()
        self.model = parse_yaml(YAML_PATH)
        self.files = ast_render_bounded_context(
            self.model, self.output_dir, 'app.jobs',
        )

    def tearDown(self):
        shutil.rmtree(self.output_dir)

    def test_files_generated(self):
        self.assertGreater(len(self.files), 0)

    def test_directory_structure(self):
        resume_dir = os.path.join(self.output_dir, 'domain', 'resume')
        self.assertTrue(os.path.isdir(resume_dir))
        self.assertTrue(os.path.isdir(os.path.join(resume_dir, 'values')))
        self.assertTrue(os.path.isdir(os.path.join(resume_dir, 'events')))

    def test_identity_vo_content(self):
        path = os.path.join(
            self.output_dir, 'domain', 'resume', 'values', 'resume_id.py',
        )
        with open(path) as f:
            content = f.read()
        self.assertIn('class ResumeId(IntIdentity)', content)
        self.assertIn('from ascetic_ddd.seedwork.domain.identity', content)

    def test_string_vo_content(self):
        path = os.path.join(
            self.output_dir, 'domain', 'resume', 'values', 'title.py',
        )
        with open(path) as f:
            content = f.read()
        self.assertIn('class Title:', content)
        self.assertIn('cannot be empty', content)
        self.assertIn('cannot exceed 255 characters', content)
        self.assertIn('value.strip()', content)
        self.assertIn('def export(self, setter', content)
        self.assertIn('def __eq__', content)
        self.assertIn('def __hash__', content)

    def test_enum_vo_content(self):
        path = os.path.join(
            self.output_dir, 'domain', 'resume', 'values',
            'employment_type.py',
        )
        with open(path) as f:
            content = f.read()
        self.assertIn('class EmploymentType(str, Enum)', content)
        self.assertIn("FULL_TIME = 'full_time'", content)
        self.assertIn('def export(self, setter', content)

    def test_composite_vo_content(self):
        path = os.path.join(
            self.output_dir, 'domain', 'resume', 'values', 'rate.py',
        )
        with open(path) as f:
            content = f.read()
        self.assertIn('class Rate:', content)
        self.assertIn('class IRateExporter', content)
        self.assertIn('def export(self, exporter', content)

    def test_aggregate_content(self):
        path = os.path.join(
            self.output_dir, 'domain', 'resume', 'resume.py',
        )
        with open(path) as f:
            content = f.read()
        self.assertIn(
            'class Resume(EventiveEntity[PersistentDomainEvent],'
            ' VersionedAggregate)',
            content,
        )
        self.assertIn('class IResumeExporter', content)
        self.assertIn('class IResumeReconstitutor', content)
        self.assertIn('def export(self, exporter', content)
        self.assertIn('def _import(self, provider', content)
        self.assertIn('def reconstitute(cls', content)

    def test_aggregate_exporter_content(self):
        path = os.path.join(
            self.output_dir, 'domain', 'resume', 'resume_exporter.py',
        )
        with open(path) as f:
            content = f.read()
        self.assertIn(
            'class ResumeExporter(VersionedAggregateExporter,'
            ' IResumeExporter)',
            content,
        )
        self.assertIn('RateExporter', content)
        self.assertIn("self.data['specialization_ids'] = []", content)

    def test_aggregate_reconstitutor_content(self):
        path = os.path.join(
            self.output_dir, 'domain', 'resume',
            'resume_reconstitutor.py',
        )
        with open(path) as f:
            content = f.read()
        self.assertIn(
            'class ResumeReconstitutor(VersionedAggregateReconstitutor,'
            ' IResumeReconstitutor)',
            content,
        )
        self.assertIn('return ResumeId(', content)
        self.assertIn('return Title(', content)

    def test_domain_event_content(self):
        path = os.path.join(
            self.output_dir, 'domain', 'resume', 'events',
            'resume_created.py',
        )
        with open(path) as f:
            content = f.read()
        self.assertIn('@dataclass(frozen=True, kw_only=True)', content)
        self.assertIn('class ResumeCreated(PersistentDomainEvent)', content)
        self.assertIn('class IResumeCreatedExporter', content)

    def test_command_content(self):
        path = os.path.join(
            self.output_dir, 'application', 'commands',
            'create_resume_command.py',
        )
        with open(path) as f:
            content = f.read()
        self.assertIn('@dataclass(frozen=True, kw_only=True)', content)
        self.assertIn('class CreateResumeCommand:', content)
        self.assertIn('user_id: int', content)
        self.assertIn('title: str', content)
        # Must NOT contain domain types
        self.assertNotIn('Title', content)
        self.assertNotIn('ResumeId', content)

    def test_imported_vo_not_generated(self):
        path = os.path.join(
            self.output_dir, 'domain', 'resume', 'values', 'money.py',
        )
        self.assertFalse(os.path.exists(path))

    def test_imported_vo_in_init(self):
        path = os.path.join(
            self.output_dir, 'domain', 'resume', 'values', '__init__.py',
        )
        with open(path) as f:
            content = f.read()
        self.assertIn(
            'from ascetic_ddd.seedwork.domain.values.money import Money',
            content,
        )

    def test_relative_imported_vo_not_generated(self):
        path = os.path.join(
            self.output_dir, 'domain', 'resume', 'values',
            'specialization_id.py',
        )
        self.assertFalse(os.path.exists(path))

    def test_relative_imported_vo_in_init(self):
        path = os.path.join(
            self.output_dir, 'domain', 'resume', 'values', '__init__.py',
        )
        with open(path) as f:
            content = f.read()
        self.assertIn(
            'from app.jobs.domain.specialization.values.specialization_id'
            ' import SpecializationId',
            content,
        )

    def test_skip_existing_files(self):
        """Files that already exist must not be overwritten."""
        path = os.path.join(
            self.output_dir, 'domain', 'resume', 'values', 'title.py',
        )
        original = 'existing content\n'
        with open(path, 'w') as f:
            f.write(original)

        from ascetic_ddd.cli.scaffold.ast_renderer import AstRenderWalker
        walker = AstRenderWalker(self.output_dir, 'app.jobs')
        walker.walk(self.model)

        with open(path) as f:
            content = f.read()
        self.assertEqual(content, original)
        self.assertIn(path, walker.skipped)

    def test_no_fstrings(self):
        """Generated code must not contain f-strings."""
        fstring_pattern = re.compile(r'\bf["\']')
        for fpath in self.files:
            with open(fpath) as f:
                content = f.read()
            match = fstring_pattern.search(content)
            self.assertIsNone(
                match,
                'f-string found in %s' % fpath,
            )

    def test_generated_files_are_valid_python(self):
        """All generated files must pass py_compile."""
        for fpath in self.files:
            try:
                py_compile.compile(fpath, doraise=True)
            except py_compile.PyCompileError:
                self.fail('Invalid Python in %s' % fpath)


if __name__ == '__main__':
    unittest.main()
