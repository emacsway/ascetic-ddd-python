import unittest

from ascetic_ddd.cli.scaffold.model import CollectionKind
from ascetic_ddd.cli.scaffold.naming import (
    camel_to_snake,
    strip_underscore_prefix,
    is_collection_type,
    extract_inner_type,
    collection_kind,
    is_primitive_type,
)


class TestCamelToSnake(unittest.TestCase):
    def test_simple(self):
        self.assertEqual(camel_to_snake('Resume'), 'resume')

    def test_two_words(self):
        self.assertEqual(camel_to_snake('ResumeId'), 'resume_id')

    def test_three_words(self):
        self.assertEqual(camel_to_snake('ResumeCreated'), 'resume_created')

    def test_employment_type(self):
        self.assertEqual(camel_to_snake('EmploymentType'), 'employment_type')

    def test_payment_period(self):
        self.assertEqual(camel_to_snake('PaymentPeriod'), 'payment_period')

    def test_user_id(self):
        self.assertEqual(camel_to_snake('UserId'), 'user_id')

    def test_create_resume(self):
        self.assertEqual(camel_to_snake('CreateResume'), 'create_resume')

    def test_single_word(self):
        self.assertEqual(camel_to_snake('Rate'), 'rate')


class TestStripUnderscorePrefix(unittest.TestCase):
    def test_with_prefix(self):
        self.assertEqual(strip_underscore_prefix('_id'), 'id')

    def test_without_prefix(self):
        self.assertEqual(strip_underscore_prefix('name'), 'name')

    def test_double_prefix(self):
        self.assertEqual(strip_underscore_prefix('__version'), '_version')


class TestCollectionType(unittest.TestCase):
    def test_list(self):
        self.assertTrue(is_collection_type('list[SpecializationId]'))

    def test_tuple(self):
        self.assertTrue(is_collection_type('tuple[EmploymentType, ...]'))

    def test_not_collection(self):
        self.assertFalse(is_collection_type('ResumeId'))

    def test_primitive(self):
        self.assertFalse(is_collection_type('str'))


class TestExtractInnerType(unittest.TestCase):
    def test_list(self):
        self.assertEqual(
            extract_inner_type('list[SpecializationId]'),
            'SpecializationId',
        )

    def test_tuple(self):
        self.assertEqual(
            extract_inner_type('tuple[EmploymentType, ...]'),
            'EmploymentType',
        )

    def test_not_collection(self):
        self.assertEqual(extract_inner_type('ResumeId'), 'ResumeId')


class TestCollectionKind(unittest.TestCase):
    def test_list(self):
        self.assertEqual(collection_kind('list[X]'), CollectionKind.LIST)

    def test_tuple(self):
        self.assertEqual(collection_kind('tuple[X, ...]'), CollectionKind.TUPLE)

    def test_none(self):
        self.assertEqual(collection_kind('str'), CollectionKind.NONE)


class TestIsPrimitiveType(unittest.TestCase):
    def test_primitives(self):
        for t in ('bool', 'int', 'str', 'float', 'datetime', 'Decimal'):
            self.assertTrue(is_primitive_type(t), t)

    def test_non_primitives(self):
        for t in ('ResumeId', 'Title', 'Rate', 'list[int]'):
            self.assertFalse(is_primitive_type(t), t)


if __name__ == '__main__':
    unittest.main()
