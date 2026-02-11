import os
import shutil
import tempfile
import unittest

from ascetic_ddd.cli.scaffold.parser import parse_yaml
from ascetic_ddd.cli.scaffold.renderer import render_bounded_context


YAML_PATH = os.path.join(os.path.dirname(__file__), 'domain-model.yaml')


class TestRenderer(unittest.TestCase):
    def setUp(self):
        self.output_dir = tempfile.mkdtemp()
        self.model = parse_yaml(YAML_PATH)
        self.files = render_bounded_context(
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
        self.assertIn('FULL_TIME = "full_time"', content)
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
        self.assertIn('class Resume(EventiveEntity[PersistentDomainEvent], VersionedAggregate)', content)
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
        self.assertIn('class ResumeExporter(VersionedAggregateExporter, IResumeExporter)', content)
        self.assertIn('RateExporter', content)
        self.assertIn("self.data['specialization_ids'] = []", content)

    def test_aggregate_reconstitutor_content(self):
        path = os.path.join(
            self.output_dir, 'domain', 'resume', 'resume_reconstitutor.py',
        )
        with open(path) as f:
            content = f.read()
        self.assertIn('class ResumeReconstitutor(VersionedAggregateReconstitutor, IResumeReconstitutor)', content)
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

    # --- Collection entity (Resume.Experience) ---

    def test_entity_directory_structure(self):
        exp_dir = os.path.join(
            self.output_dir, 'domain', 'resume', 'experience',
        )
        self.assertTrue(os.path.isdir(exp_dir))
        self.assertTrue(os.path.isdir(os.path.join(exp_dir, 'values')))

    def test_entity_class_content(self):
        path = os.path.join(
            self.output_dir, 'domain', 'resume', 'experience',
            'experience.py',
        )
        with open(path) as f:
            content = f.read()
        self.assertIn('class Experience:', content)
        self.assertIn('class IExperienceExporter', content)
        self.assertIn('class IExperienceReconstitutor', content)
        self.assertIn('def export(self, exporter', content)
        self.assertIn('def _import(self, provider', content)
        self.assertIn('def reconstitute(cls', content)
        self.assertIn('def _make_empty(cls)', content)

    def test_entity_class_imports_aggregate_vo(self):
        path = os.path.join(
            self.output_dir, 'domain', 'resume', 'experience',
            'experience.py',
        )
        with open(path) as f:
            content = f.read()
        # ResumeId should import from aggregate's values, not entity's
        self.assertIn(
            'from app.jobs.domain.resume.values.resume_id import ResumeId',
            content,
        )

    def test_entity_exporter_content(self):
        path = os.path.join(
            self.output_dir, 'domain', 'resume', 'experience',
            'experience_exporter.py',
        )
        with open(path) as f:
            content = f.read()
        self.assertIn(
            'class ExperienceExporter(IExperienceExporter)',
            content,
        )
        self.assertIn('self.data = {}', content)
        self.assertIn('def set_resume_id', content)

    def test_entity_reconstitutor_content(self):
        path = os.path.join(
            self.output_dir, 'domain', 'resume', 'experience',
            'experience_reconstitutor.py',
        )
        with open(path) as f:
            content = f.read()
        self.assertIn(
            'class ExperienceReconstitutor(IExperienceReconstitutor)',
            content,
        )
        self.assertIn('self._data =', content)
        self.assertIn('def resume_id(self)', content)

    def test_entity_vo_content(self):
        path = os.path.join(
            self.output_dir, 'domain', 'resume', 'experience', 'values',
            'company_name.py',
        )
        with open(path) as f:
            content = f.read()
        self.assertIn('class CompanyName:', content)
        self.assertIn('cannot be empty', content)
        self.assertIn('cannot exceed 255 characters', content)

    def test_entity_imported_vo_not_generated(self):
        path = os.path.join(
            self.output_dir, 'domain', 'resume', 'experience', 'values',
            'time_range.py',
        )
        self.assertFalse(os.path.exists(path))

    def test_aggregate_with_entity_make_empty(self):
        path = os.path.join(
            self.output_dir, 'domain', 'resume', 'resume.py',
        )
        with open(path) as f:
            content = f.read()
        self.assertIn('def _make_empty(cls)', content)
        self.assertIn('agg._experience = []', content)

    def test_aggregate_with_entity_export(self):
        path = os.path.join(
            self.output_dir, 'domain', 'resume', 'resume.py',
        )
        with open(path) as f:
            content = f.read()
        self.assertIn('exporter.add_experience(item)', content)

    def test_aggregate_exporter_with_entity(self):
        path = os.path.join(
            self.output_dir, 'domain', 'resume', 'resume_exporter.py',
        )
        with open(path) as f:
            content = f.read()
        self.assertIn('ExperienceExporter', content)
        self.assertIn('def add_experience(self, value)', content)
        self.assertIn("self.data['experience'] = []", content)

    def test_aggregate_reconstitutor_with_entity(self):
        path = os.path.join(
            self.output_dir, 'domain', 'resume',
            'resume_reconstitutor.py',
        )
        with open(path) as f:
            content = f.read()
        self.assertIn('ExperienceReconstitutor', content)
        self.assertIn('def experience(self)', content)
        self.assertIn('ExperienceReconstitutor(**d)', content)

    # --- Single entity (Specialization.SpecializationProfile) ---

    def test_single_entity_directory(self):
        ent_dir = os.path.join(
            self.output_dir, 'domain', 'specialization',
            'specialization_profile',
        )
        self.assertTrue(os.path.isdir(ent_dir))

    def test_single_entity_class_content(self):
        path = os.path.join(
            self.output_dir, 'domain', 'specialization',
            'specialization_profile', 'specialization_profile.py',
        )
        with open(path) as f:
            content = f.read()
        self.assertIn('class SpecializationProfile:', content)
        self.assertIn('class ISpecializationProfileExporter', content)

    def test_single_entity_aggregate_set(self):
        """Single entity field must use set_X, not add_X."""
        path = os.path.join(
            self.output_dir, 'domain', 'specialization',
            'specialization.py',
        )
        with open(path) as f:
            content = f.read()
        self.assertIn('def set_profile(self, value)', content)
        self.assertNotIn('add_profile', content)

    def test_single_entity_init_none(self):
        path = os.path.join(
            self.output_dir, 'domain', 'specialization',
            'specialization.py',
        )
        with open(path) as f:
            content = f.read()
        self.assertIn('self._profile = None', content)

    def test_single_entity_make_empty_none(self):
        path = os.path.join(
            self.output_dir, 'domain', 'specialization',
            'specialization.py',
        )
        with open(path) as f:
            content = f.read()
        self.assertIn('agg._profile = None', content)

    def test_single_entity_export_set(self):
        path = os.path.join(
            self.output_dir, 'domain', 'specialization',
            'specialization.py',
        )
        with open(path) as f:
            content = f.read()
        self.assertIn('exporter.set_profile(self._profile)', content)

    def test_single_entity_exporter_set(self):
        path = os.path.join(
            self.output_dir, 'domain', 'specialization',
            'specialization_exporter.py',
        )
        with open(path) as f:
            content = f.read()
        self.assertIn('def set_profile(self, value)', content)
        self.assertNotIn('add_profile', content)
        self.assertIn("self.data['profile'] = exporter.data", content)

    def test_single_entity_reconstitutor(self):
        path = os.path.join(
            self.output_dir, 'domain', 'specialization',
            'specialization_reconstitutor.py',
        )
        with open(path) as f:
            content = f.read()
        self.assertIn('SpecializationProfileReconstitutor', content)
        self.assertIn('def profile(self)', content)
        # Single entity — direct call, not list comprehension
        self.assertNotIn('for d in', content)

    def test_no_fstrings(self):
        """Generated code must not contain f-strings."""
        for fpath in self.files:
            with open(fpath) as f:
                content = f.read()
            # Check for f-string patterns like f" or f'
            import re
            fstring_pattern = re.compile(r'\bf["\']')
            match = fstring_pattern.search(content)
            self.assertIsNone(
                match,
                'f-string found in %s' % fpath,
            )


class TestCustomTemplates(unittest.TestCase):
    def setUp(self):
        self.output_dir = tempfile.mkdtemp()
        self.templates_dir = tempfile.mkdtemp()
        self.model = parse_yaml(YAML_PATH)

    def tearDown(self):
        shutil.rmtree(self.output_dir)
        shutil.rmtree(self.templates_dir)

    def test_custom_template_overrides_default(self):
        tpl_dir = os.path.join(
            self.templates_dir, 'domain', 'values',
        )
        os.makedirs(tpl_dir)
        with open(os.path.join(tpl_dir, 'simple_vo.py.j2'), 'w') as f:
            f.write('# custom {{ vo.class_name }}\n')

        render_bounded_context(
            self.model, self.output_dir, 'app.jobs',
            self.templates_dir,
        )

        path = os.path.join(
            self.output_dir, 'domain', 'resume', 'values', 'title.py',
        )
        with open(path) as f:
            content = f.read()
        self.assertEqual(content, '# custom Title\n')

    def test_non_overridden_templates_use_default(self):
        render_bounded_context(
            self.model, self.output_dir, 'app.jobs',
            self.templates_dir,
        )

        path = os.path.join(
            self.output_dir, 'domain', 'resume', 'values', 'resume_id.py',
        )
        with open(path) as f:
            content = f.read()
        self.assertIn('class ResumeId(IntIdentity)', content)


if __name__ == '__main__':
    unittest.main()
