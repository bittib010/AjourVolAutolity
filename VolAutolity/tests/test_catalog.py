"""The catalog must match the installed Volatility: names exist, no deprecated aliases, no unmet required options.

This is what catches plugin renames when requirements.txt bumps Volatility.
"""

import importlib.util
import unittest

from volautolity.catalog import PluginCatalog, PluginKind
from volautolity.models import OsFamily

HAVE_VOLATILITY = importlib.util.find_spec("volatility3") is not None

# Options the pipeline supplies itself for a given kind.
SUPPLIED = {PluginKind.STRINGS: {"strings_file"}, PluginKind.HIVELIST: {"dump"}, PluginKind.YARA: {"yara_file"}}


class CatalogShapeTests(unittest.TestCase):
    def test_tables_are_unique_per_os(self):
        catalog = PluginCatalog()
        for os_family in OsFamily:
            tables = [catalog.bootstrap(os_family).table] + [s.table for s in catalog.plugins(os_family)]
            self.assertEqual(len(tables), len(set(tables)), f"duplicate table names for {os_family.value}")


@unittest.skipUnless(HAVE_VOLATILITY, "volatility3 not installed (pip install -r requirements.txt)")
class CatalogMatchesVolatilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import volatility3.plugins
        from volatility3 import framework
        from volatility3.framework import deprecation

        framework.require_interface_version(2, 0, 0)
        failures = framework.import_files(volatility3.plugins, True)
        cls.plugins = framework.list_plugins()
        cls.import_failures = failures
        cls.rename_class = deprecation.PluginRenameClass

    def _all_specs(self):
        catalog = PluginCatalog()
        for os_family in OsFamily:
            yield catalog.bootstrap(os_family)
            yield from catalog.plugins(os_family)
        yield catalog.diagnostics()

    def test_every_plugin_exists_and_is_current(self):
        for spec in self._all_specs():
            with self.subTest(plugin=spec.name):
                self.assertIn(spec.name, self.plugins, f"not found (import failures: {self.import_failures})")
                self.assertFalse(issubclass(self.plugins[spec.name], self.rename_class), "deprecated alias")

    def test_required_options_are_supplied(self):
        from volatility3.framework.configuration import requirements as req
        from volatility3.framework.interfaces.configuration import SimpleTypeRequirement

        simple = (SimpleTypeRequirement, req.ListRequirement, req.ChoiceRequirement, req.URIRequirement)
        for spec in self._all_specs():
            supplied = {a.lstrip("-").replace("-", "_") for a in spec.args if a.startswith("--")} | SUPPLIED.get(spec.kind, set())
            for requirement in self.plugins[spec.name].get_requirements():
                if isinstance(requirement, simple) and not requirement.optional and requirement.default is None:
                    with self.subTest(plugin=spec.name, option=requirement.name):
                        self.assertIn(requirement.name, supplied)


if __name__ == "__main__":
    unittest.main()
