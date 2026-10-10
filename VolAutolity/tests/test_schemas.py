import unittest

from volautolity.catalog import PluginCatalog
from volautolity.csvnorm import ColumnType
from volautolity.models import OsFamily
from volautolity.schemas import TableSchemas


class SchemaTests(unittest.TestCase):
    def setUp(self):
        self.schemas = TableSchemas()

    def test_every_catalog_table_has_a_declared_schema(self):
        catalog = PluginCatalog()
        for os_family in OsFamily:
            tables = self.schemas.for_os(os_family)
            for spec in [catalog.bootstrap(os_family), *catalog.plugins(os_family)]:
                with self.subTest(os=os_family.value, table=spec.table):
                    self.assertIn(spec.table, tables)
                    self.assertEqual(tables[spec.table][-1].name, "VolRow")

    def test_common_tables_and_patterns(self):
        tables = self.schemas.for_os(OsFamily.WINDOWS)
        self.assertIn("volautolity_runs", tables)
        printkey = TableSchemas.lookup(tables, "printkey_ntuser2")
        self.assertEqual([c.name for c in printkey][:3], ["TreeDepth", "LastWriteTime", "HiveOffset"])
        self.assertEqual(printkey[1].type, ColumnType.DATETIME)
        self.assertIsNone(TableSchemas.lookup(tables, "nonexistent"))

    def test_unknown_os_only_gets_diagnostics(self):
        tables = self.schemas.for_os(None)
        self.assertEqual(set(tables), {"volautolity_runs", "volautolity_image", "banners"})


if __name__ == "__main__":
    unittest.main()
