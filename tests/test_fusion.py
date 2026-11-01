"""Testes do FrotaFusion com quatro packs artificiais (sem download gigante)."""
import tempfile
import unittest
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

from fusion_core import build_fusion, scan_pack, select_bundles, unpack_zip


XML_PATTERN = (
    "<?xml version='1.0' encoding='utf-8'?>\n"
    "<CVehicleModelInfo__InitDataList><InitDatas><Item>"
    "<modelName>{model}</modelName></Item></InitDatas>"
    "\n{sep}\n</CVehicleModelInfo__InitDataList>"
)


class FusionTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.res = self.base / "server" / "resources"
        self.res.mkdir(parents=True)
        self.inputs = [self.base / f"source{i}" for i in range(1, 5)]

    def write(self, root, rel, data):
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(data, bytes):
            p.write_bytes(data)
        else:
            p.write_text(data, encoding="utf-8")
        return p

    def model(self, pack, folder, model, texture_bytes=100, invalid_xml=False):
        if pack == 1:
            root = "PLOKS_CARS"
            parent = "[ACURA]/" + folder
        elif pack == 2:
            root = "Lore_Friendly_Car_Pack"
            parent = "[6STR]/" + folder
        elif pack == 3:
            root = "LNWK-CARS"
            parent = folder
        else:
            root = "Lorefriendly-Cars-test"
            parent = folder
        base = self.inputs[pack - 1]
        self.write(base, root + "/fxmanifest.lua",
                   "fx_version 'cerulean'\ngame 'gta5'\n"
                   "files {'data/**/*.meta'}\n"
                   "data_file 'VEHICLE_METADATA_FILE' 'data/**/vehicles.meta'\n")
        sep = "<!----------------------------------------------------->" if invalid_xml else ""
        xml = XML_PATTERN.format(model=model, sep=sep)
        meta = self.write(base, root + "/data/" + parent + "/vehicles.meta", xml)
        self.write(base, root + "/data/" + parent + "/handling.meta", "handling\n")
        self.write(base, root + "/data/" + parent + "/carvariations.meta", "variations\n")
        self.write(base, root + "/stream/" + parent + f"/{model}.yft", b"mesh")
        self.write(base, root + "/stream/" + parent + f"/{model}.ytd", b"t" * texture_bytes)
        return meta

    def test_dedup_keeps_smaller_complete_model(self):
        self.model(1, "first", "unique1")
        self.model(2, "second", "same", 300)
        self.model(3, "third", "same", 50)
        self.model(4, "fourth", "unique4")
        self.write(self.inputs[1], "Lore_Friendly_Car_Pack/audio/audioconfig/sounds.dat151.rel", b"sound")
        self.write(self.inputs[1], "Lore Friendly Rim Packs/Rims A/fxmanifest.lua",
                   "fx_version 'cerulean'")
        self.write(self.inputs[1], "Lore Friendly Rim Packs/Rims A/stream/wheel.ytd", b"w")
        self.write(self.inputs[3], "Lorefriendly-Cars-test/[lf-cars-sounds]/arias-sound/fxmanifest.lua",
                   "fx_version 'cerulean'")
        self.write(self.inputs[3], "Lorefriendly-Cars-test/[lf-cars-sounds]/arias-sound/sfx/aria.awc",
                   b"sound")
        folder, report = build_fusion(self.inputs, self.res)
        self.assertEqual(folder, (self.res / "[carros]").resolve())
        self.assertEqual(report["resumo"]["spawns_incluidos"], 3)
        self.assertEqual(len(report["conflitos_de_spawn"]), 1)
        self.assertEqual(report["conflitos_de_spawn"][0]["spawn"], "same")
        self.assertTrue(report["conflitos_de_spawn"][0]["mantido"].startswith("P3:"))
        self.assertTrue((folder / "LNWK-CARS/stream/third/same.yft").is_file())
        self.assertFalse((folder / "Lore_Friendly_Car_Pack/stream/[6STR]/second/same.yft").exists())
        self.assertTrue((folder / "PLOKS_CARS/stream/[ACURA]/first/unique1.yft").is_file())
        self.assertTrue((folder / "LIVID_LF_CARS/stream/fourth/unique4.yft").is_file())
        self.assertTrue((folder / "Lore_Friendly_Car_Pack/audio/audioconfig/sounds.dat151.rel").is_file())
        self.assertTrue((folder / "FROTA_RODAS_01/fxmanifest.lua").is_file())
        self.assertTrue((folder / "FROTA_SOM_arias-sound/fxmanifest.lua").is_file())
        self.assertTrue((folder / "RELATORIO_FROTAFUSION.json").is_file())
        self.assertTrue((self.inputs[1] / "Lore_Friendly_Car_Pack/stream/[6STR]/second/same.yft").is_file())
        with self.assertRaises(FileExistsError):
            build_fusion(self.inputs, self.res)

    def test_invalid_bolide_metadata_repaired_only_in_output(self):
        original = self.model(1, "bolide", "bolide", 30, invalid_xml=True)
        self.model(2, "a", "spirit")
        self.model(3, "b", "third")
        self.model(4, "c", "fourth")
        with self.assertRaises(ET.ParseError):
            ET.parse(original)
        out, _ = build_fusion(self.inputs, self.res)
        copied = out / "PLOKS_CARS/data/[ACURA]/bolide/vehicles.meta"
        ET.parse(copied)
        with self.assertRaises(ET.ParseError):
            ET.parse(original)

    def test_missing_yft_is_flagged_and_not_counted_as_running_vehicle(self):
        self.model(1, "a", "broken")
        self.model(2, "b", "good2")
        self.model(3, "c", "good3")
        self.model(4, "d", "good4")
        (self.inputs[0] / "PLOKS_CARS/stream/[ACURA]/a/broken.yft").unlink()
        output, report = build_fusion(self.inputs, self.res)
        self.assertIn("broken", report["resumo"]["spawns_sem_selecao"])
        self.assertEqual(report["resumo"]["spawns_incluidos"], 3)
        self.assertFalse((output / "PLOKS_CARS/data/[ACURA]/a/vehicles.meta").exists())

    def test_zip_sources_and_guard_traversal(self):
        self.model(1, "a", "a")
        self.model(2, "b", "b")
        self.model(3, "c", "c")
        self.model(4, "d", "d")
        files = []
        for i, root in enumerate(self.inputs, 1):
            target = self.base / f"{i}.zip"
            with zipfile.ZipFile(target, "w") as z:
                for p in root.rglob("*"):
                    if p.is_file():
                        z.write(p, f"root_archive_{i}/" + p.relative_to(root).as_posix())
            files.append(target)
        output, report = build_fusion(files, self.res)
        self.assertEqual(report["resumo"]["spawns_incluidos"], 4)
        self.assertTrue((output / "LNWK-CARS/fxmanifest.lua").exists())
        evil = self.base / "evil.zip"
        with zipfile.ZipFile(evil, "w") as z:
            z.writestr("../../no.txt", b"oops")
        with self.assertRaises(ValueError):
            unpack_zip(evil, self.base / "other")
        self.assertFalse((self.base / "no.txt").exists())


if __name__ == "__main__":
    unittest.main()
