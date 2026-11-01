"""Testes locais com amostras mínimas, sem downloads nem FiveM real."""
import tempfile
import unittest
from pathlib import Path

from installer import destination_for, install_pack


class InstallationTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.origins = self.base / "originais"
        self.resources = self.base / "servidor" / "resources"
        self.resources.mkdir(parents=True)

    def make_file(self, relative, content="x"):
        path = self.origins / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def make_pack1(self):
        base = "pacote_01/civ-master/PLOKS_CARS"
        self.make_file(base + "/fxmanifest.lua",
                       "fx_version 'cerulean'\ngame 'gta5'\n"
                       "client_scripts {'vehicle_names.lua'}\n"
                       "server_script 'server.lua'\n"
                       "files {'data/**/*.meta'}\n"
                       "data_file 'VEHICLE_METADATA_FILE' 'data/**/vehicles*.meta'\n")
        self.make_file(base + "/server.lua", "print('old')")
        self.make_file(base + "/vehicle_names.lua",
                       "Citizen.CreateThread(function()\n"
                       "AddTextEntry('tltypes', 'Acura Type-S')\n"
                       "AddTextEntry('amdbx', 'Aston Martin DBX')\nend)\n")
        for brand, model in [("ACURA", "tltypes"), ("ASTONMARTIN", "amdbx")]:
            meta = base + f"/data/[{brand}]/{model}/vehicles.meta"
            self.make_file(meta,
                           "<CVehicleModelInfo__InitDataList><InitDatas><Item>"
                           f"<modelName>{model}</modelName><gameName>{model}</gameName>"
                           "</Item></InitDatas></CVehicleModelInfo__InitDataList>")
            self.make_file(base + f"/stream/[{brand}]/{model}/{model}.yft", model)

    def make_pack2(self):
        root = "pacote_02/lore-main"
        prefix = root + "/Lore_Friendly_Car_Pack"
        self.make_file(prefix + "/fxmanifest.lua",
                       "fx_version 'cerulean'\nserver_script 'server.lua'\n"
                       "server_script 'versioncheck.lua'\n")
        self.make_file(prefix + "/server.lua", "print('up')")
        self.make_file(prefix + "/stream/model.yft", "model")
        self.make_file(root + "/Lore Friendly Rim Packs/Lore Friendly Wheels Pack/fxmanifest.lua",
                       "fx_version 'cerulean'\n")
        self.make_file(root + "/Lore Friendly Rim Packs/Lore Friendly Wheels Pack/stream/rim.ytd", "rim")

    def make_pack3(self):
        prefix = "pacote_03/repo-main/LNWK-CARS"
        self.make_file(prefix + "/fxmanifest.lua", "fx_version('bodacious')\n")
        self.make_file(prefix + "/data/Car One/vehicles.meta", "<Vehicle/>")
        self.make_file(prefix + "/stream/Car One/one.yft", "vehicle")
        self.make_file(prefix + "/data/Car One/fxmanifest.lua", "fx_version 'cerulean'")
        self.make_file("pacote_03/repo-main/Diffirent Handling Types/handling.meta", "alternative")

    def make_pack4(self):
        prefix = "pacote_04/repo-tag"
        self.make_file(prefix + "/fxmanifest.lua", "fx_version 'cerulean'\n")
        self.make_file(prefix + "/data/one/handling.meta", "<handling/>")
        self.make_file(prefix + "/stream/one/one.yft", "vehicle")
        self.make_file(prefix + "/[lf-cars-sounds]/arias-sound/fxmanifest.lua",
                       "fx_version 'cerulean'\n")
        self.make_file(prefix + "/[lf-cars-sounds]/arias-sound/sfx/sound.awc", "audio")

    def test_destinations_and_no_category_nesting(self):
        self.assertEqual(destination_for(1, self.resources),
                         (self.resources / "[carros]").resolve())
        own = self.resources / "[carros2]"
        self.assertEqual(destination_for(2, own), own.resolve())
        with self.assertRaises(ValueError):
            destination_for(2, self.resources / "[carros]")
        for n, category in enumerate(["[carros]", "[carros2]", "[carros3]", "[carros4]"], 1):
            self.assertEqual(destination_for(n, self.resources), (self.resources / category).resolve())

    def test_install_four_independent_categories(self):
        self.make_pack1()
        self.make_pack2()
        self.make_pack3()
        self.make_pack4()
        first = self.origins / "pacote_01/civ-master/PLOKS_CARS/stream/[ACURA]/tltypes/tltypes.yft"
        all_names = []
        for idx in range(1, 5):
            target, names = install_pack(self.origins, idx, self.resources)
            self.assertEqual(target, (self.resources / ("[carros]" if idx == 1 else f"[carros{idx}]")).resolve())
            self.assertTrue((target / "INSTRUCOES_FROTALAB.txt").is_file())
            for name in names:
                self.assertTrue((target / name / "fxmanifest.lua").is_file())
            all_names.append(names)
        self.assertEqual(all_names[0], ["CIV_ACURA", "CIV_ASTONMARTIN"])
        self.assertEqual(all_names[1], ["Lore_Friendly_Car_Pack", "LF_RIMS_01"])
        self.assertEqual(all_names[2], ["LNWK-CARS"])
        self.assertEqual(all_names[3], ["LIVID_LF_CARS", "LIVID_arias-sound"])
        self.assertEqual(first.read_text(), "tltypes")
        with self.assertRaises(FileExistsError):
            install_pack(self.origins, 1, self.resources)
        self.assertIn("tltypes",
                      (self.resources / "[carros]/CIV_ACURA/vehicle_names.lua").read_text())
        self.assertNotIn("amdbx",
                         (self.resources / "[carros]/CIV_ACURA/vehicle_names.lua").read_text())
        self.assertNotIn("server_script 'server.lua'",
                         (self.resources / "[carros]/CIV_ACURA/fxmanifest.lua").read_text())
        self.assertNotIn("versioncheck.lua",
                         (self.resources / "[carros2]/Lore_Friendly_Car_Pack/fxmanifest.lua").read_text())
        self.assertFalse((self.resources / "[carros3]/Diffirent Handling Types").exists())

    def test_direct_category_and_original_pack1_preserved(self):
        self.make_pack1()
        own = self.resources / "[carros]"
        own.mkdir()
        target, names = install_pack(
            self.origins, 1, own, split_pack1=False)
        self.assertEqual(target, own.resolve())
        self.assertEqual(names, ["PLOKS_CARS"])
        self.assertTrue((own / "PLOKS_CARS/server.lua").is_file())

    def test_nonempty_target_is_not_overwritten(self):
        self.make_pack3()
        old = self.resources / "[carros3]" / "my_resource"
        old.mkdir(parents=True)
        (old / "fxmanifest.lua").write_text("valuable")
        with self.assertRaises(FileExistsError):
            install_pack(self.origins, 3, self.resources)
        self.assertEqual((old / "fxmanifest.lua").read_text(), "valuable")


if __name__ == "__main__":
    unittest.main()
