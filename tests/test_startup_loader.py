"""Testes do iniciador escalonado sem servidor FiveM real."""
import tempfile
import unittest
from pathlib import Path

from startup_loader import create_loader, discover_brands, make_config


class StartupLoaderTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.resources = self.root / "resources"
        self.group = self.resources / "[carros]"
        self.group.mkdir(parents=True)

    def add(self, name, manifest=True):
        dest = self.group / name
        dest.mkdir()
        if manifest:
            (dest / "fxmanifest.lua").write_text("fx_version 'cerulean'\n")
        return dest

    def test_generates_launcher_in_resources_and_does_not_edit_cars(self):
        acura = self.add("CIV_ACURA")
        aston = self.add("CIV_ASTONMARTIN")
        audi = self.add("CIV_AUDI")
        self.add("PLOKS_CARS")
        original = (acura / "fxmanifest.lua").read_text()
        folder, names = create_loader(self.resources)
        self.assertEqual(names, ["CIV_ACURA", "CIV_ASTONMARTIN", "CIV_AUDI"])
        self.assertEqual(folder, (self.resources / "frotalab_loader").resolve())
        self.assertEqual((acura / "fxmanifest.lua").read_text(), original)
        self.assertTrue((folder / "fxmanifest.lua").is_file())
        self.assertTrue((folder / "server.lua").is_file())
        config = (folder / "config.lua").read_text(encoding="utf-8")
        self.assertIn("Config.StartAll = false", config)
        self.assertIn("Config.IntervalMs = 15000", config)
        self.assertIn('"CIV_ACURA"', config)
        self.assertIn('"CIV_ASTONMARTIN"', config)
        self.assertIn('"CIV_AUDI"', config)
        self.assertNotIn('"PLOKS_CARS"', config)
        lua = (folder / "server.lua").read_text(encoding="utf-8")
        self.assertIn('GetResourceState(name)', lua)
        self.assertIn('StartResource(name)', lua)
        self.assertIn('if state == "started" then', lua)
        self.assertIn('pause(Config.IntervalMs)', lua)
        self.assertNotIn('ExecuteCommand("ensure', lua)
        self.assertFalse((self.root / "server.cfg").exists())
        self.assertEqual((audi / "fxmanifest.lua").read_text(), original)
        with self.assertRaises(FileExistsError):
            create_loader(self.resources)

    def test_select_category_directly_and_opt_in_to_all(self):
        self.add("CIV_ACURA")
        self.add("CIV_ASTONMARTIN")
        folder, names = create_loader(self.group, start_all=True, interval_seconds=20)
        self.assertEqual(len(names), 2)
        conf = (folder / "config.lua").read_text()
        self.assertIn("Config.StartAll = true", conf)
        self.assertIn("Config.IntervalMs = 20000", conf)
        self.assertEqual(folder.parent, self.resources.resolve())

    def test_refuse_missing_category(self):
        with self.assertRaises(ValueError):
            discover_brands(self.root)
        with self.assertRaises(ValueError):
            create_loader(self.resources)

    def test_refuse_missing_resource_manifest(self):
        self.add("CIV_ACURA", manifest=False)
        with self.assertRaises(ValueError):
            create_loader(self.resources)
        self.assertFalse((self.resources / "frotalab_loader").exists())

    def test_refuse_invalid_delay(self):
        with self.assertRaises(ValueError):
            make_config(["CIV_ACURA"], interval_seconds=0)
        with self.assertRaises(ValueError):
            make_config(["CIV_ACURA"], interval_seconds=61)
        with self.assertRaises(ValueError):
            make_config(["CIV_ACURA", "CIV_ACURA"])
        with self.assertRaises(ValueError):
            make_config(["CIV_ACURA", "CIV_]"], interval_seconds=10)


if __name__ == "__main__":
    unittest.main()
