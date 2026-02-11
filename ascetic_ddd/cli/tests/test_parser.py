import os
import unittest

from ascetic_ddd.cli.model import CollectionKind, DispatchKind, VoKind
from ascetic_ddd.cli.parser import parse_yaml


YAML_PATH = os.path.join(
    os.path.dirname(__file__),
    '..', '..', '..', 'domain-model.yaml',
)


class TestParseYaml(unittest.TestCase):
    def setUp(self):
        self.model = parse_yaml(YAML_PATH)

    def test_aggregates_count(self):
        self.assertEqual(len(self.model.aggregates), 2)

    def test_resume_aggregate(self):
        resume = self.model.aggregates[0]
        self.assertEqual(resume.class_name, 'Resume')
        self.assertEqual(resume.snake_name, 'resume')

    def test_resume_fields_count(self):
        resume = self.model.aggregates[0]
        self.assertEqual(len(resume.fields), 12)

    def test_resume_value_objects(self):
        resume = self.model.aggregates[0]
        vo_names = [vo.class_name for vo in resume.value_objects]
        self.assertIn('ResumeId', vo_names)
        self.assertIn('Title', vo_names)
        self.assertIn('Description', vo_names)
        self.assertIn('Rate', vo_names)
        self.assertIn('EmploymentType', vo_names)
        self.assertIn('WorkFormat', vo_names)
        self.assertIn('PaymentPeriod', vo_names)

    def test_identity_vo(self):
        resume = self.model.aggregates[0]
        resume_id = next(
            vo for vo in resume.value_objects if vo.class_name == 'ResumeId'
        )
        self.assertEqual(resume_id.kind, VoKind.IDENTITY)
        self.assertEqual(resume_id.identity_mode, 'transient')
        self.assertEqual(resume_id.identity_base_class, 'IntIdentity')

    def test_string_vo(self):
        resume = self.model.aggregates[0]
        title = next(
            vo for vo in resume.value_objects if vo.class_name == 'Title'
        )
        self.assertEqual(title.kind, VoKind.STRING)
        self.assertFalse(title.constraints.blank)
        self.assertEqual(title.constraints.max_length, 255)
        self.assertTrue(title.map_def.strip)

    def test_enum_vo(self):
        resume = self.model.aggregates[0]
        et = next(
            vo for vo in resume.value_objects
            if vo.class_name == 'EmploymentType'
        )
        self.assertEqual(et.kind, VoKind.ENUM)
        self.assertIn('FULL_TIME', et.enum_values)
        self.assertEqual(et.enum_values['FULL_TIME'], 'full_time')

    def test_composite_vo(self):
        resume = self.model.aggregates[0]
        rate = next(
            vo for vo in resume.value_objects if vo.class_name == 'Rate'
        )
        self.assertEqual(rate.kind, VoKind.COMPOSITE)
        self.assertEqual(len(rate.fields), 2)

    def test_domain_events(self):
        resume = self.model.aggregates[0]
        self.assertEqual(len(resume.domain_events), 1)
        ev = resume.domain_events[0]
        self.assertEqual(ev.class_name, 'ResumeCreated')
        self.assertEqual(ev.snake_name, 'resume_created')

    def test_commands_derived(self):
        resume = self.model.aggregates[0]
        self.assertEqual(len(resume.commands), 1)
        cmd = resume.commands[0]
        self.assertEqual(cmd.class_name, 'CreateResume')
        self.assertEqual(cmd.snake_name, 'create_resume')

    def test_command_fields_are_primitives(self):
        resume = self.model.aggregates[0]
        cmd = resume.commands[0]
        for f in cmd.fields:
            self.assertTrue(f.is_primitive, '%s should be primitive' % f.param_name)

    def test_external_references(self):
        self.assertEqual(len(self.model.external_value_objects), 1)
        ext = self.model.external_value_objects[0]
        self.assertEqual(ext.class_name, 'UserId')
        self.assertTrue(ext.is_external_ref)

    def test_specialization_aggregate(self):
        spec = self.model.aggregates[1]
        self.assertEqual(spec.class_name, 'Specialization')
        self.assertEqual(len(spec.fields), 1)

    def test_collection_field_dispatch(self):
        resume = self.model.aggregates[0]
        spec_ids = next(
            f for f in resume.fields if f.param_name == 'specialization_ids'
        )
        self.assertTrue(spec_ids.is_collection)
        self.assertEqual(spec_ids.collection_kind, CollectionKind.LIST)
        self.assertEqual(spec_ids.inner_type, 'SpecializationId')
        self.assertEqual(spec_ids.dispatch_kind, DispatchKind.COLLECTION_SIMPLE_VO)

    def test_no_event_version_mutation(self):
        """Parsing the same YAML twice must produce identical results."""
        model2 = parse_yaml(YAML_PATH)
        ev1 = self.model.aggregates[0].domain_events[0]
        ev2 = model2.aggregates[0].domain_events[0]
        self.assertEqual(len(ev1.fields), len(ev2.fields))
        self.assertEqual(ev1.event_version, ev2.event_version)


class TestYamlValidation(unittest.TestCase):
    def _write_yaml(self, content):
        import tempfile
        f = tempfile.NamedTemporaryFile(
            mode='w', suffix='.yaml', delete=False,
        )
        f.write(content)
        f.close()
        return f.name

    def _cleanup(self, path):
        os.unlink(path)

    def test_missing_aggregates(self):
        path = self._write_yaml('external_references: {}')
        try:
            with self.assertRaises(ValueError):
                parse_yaml(path)
        finally:
            self._cleanup(path)

    def test_unknown_top_level_key(self):
        path = self._write_yaml('aggregates: {}\nbogus: 1')
        try:
            with self.assertRaises(ValueError):
                parse_yaml(path)
        finally:
            self._cleanup(path)

    def test_unknown_aggregate_key(self):
        path = self._write_yaml(
            'aggregates:\n  Foo:\n    fields: {}\n    bogus: 1'
        )
        try:
            with self.assertRaises(ValueError):
                parse_yaml(path)
        finally:
            self._cleanup(path)

    def test_unknown_vo_key(self):
        path = self._write_yaml(
            'aggregates:\n  Foo:\n    value_objects:\n'
            '      Bar:\n        type: str\n        bogus: 1'
        )
        try:
            with self.assertRaises(ValueError):
                parse_yaml(path)
        finally:
            self._cleanup(path)


if __name__ == '__main__':
    unittest.main()
