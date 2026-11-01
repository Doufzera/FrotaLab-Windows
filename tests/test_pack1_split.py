import tempfile
import unittest
import zipfile
from pathlib import Path
from frotalab import split_pack1_by_brand


class Pack1SplitTest(unittest.TestCase):
    def test_exports_each_brand_as_standalone_resource_without_mutation(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            src = root / "originais" / "pacote_01" / "FiveM-Civ-Car-Pack-master" / "PLOKS_CARS"
            (src / "fxmanifest.lua").parent.mkdir(parents=True)
            (src / "fxmanifest.lua").write_text("fx_version 'cerulean'\n")
            (src / "vehicle_names.lua").write_text(
                "Citizen.CreateThread(function()\n"
                "AddTextEntry('tltypes','Acura TL Type-S')\n"
                "AddTextEntry('amdbx','Aston Martin DBX')\nend)\n")
            for group, model in [("[ACURA]", "tltypes"), ("[ASTONMARTIN]", "amdbx")]:
                d = src / "data" / group / model
                stream = src / "stream" / group / model
                d.mkdir(parents=True)
                stream.mkdir(parents=True)
                (d / "vehicles.meta").write_text(
                    "<?xml version='1.0'?><CVehicleModelInfo__InitDataList>"
                    "<InitDatas><Item><modelName>" + model + "</modelName>"
                    "<gameName>" + model + "</gameName></Item></InitDatas>"
                    "</CVehicleModelInfo__InitDataList>")
                (d / "handling.meta").write_text("<CHandlingDataMgr/>")
                (stream / f"{model}.yft").write_bytes(b"YFT_SAMPLE")
                (stream / f"{model}.ytd").write_bytes(b"YTD_SAMPLE")
            out = root / "saida"
            names = split_pack1_by_brand(root / "originais", out)
            self.assertEqual(names, ["CIV_ACURA.zip", "CIV_ASTONMARTIN.zip"])
            for brand, group, model in [
                ("ACURA", "[ACURA]", "tltypes"),
                ("ASTONMARTIN", "[ASTONMARTIN]", "amdbx")
            ]:
                with zipfile.ZipFile(out / f"CIV_{brand}.zip") as z:
                    self.assertIsNone(z.testzip())
                    prefix = f"CIV_{brand}"
                    self.assertIn(f"{prefix}/fxmanifest.lua", z.namelist())
                    self.assertIn(f"{prefix}/data/{group}/{model}/vehicles.meta", z.namelist())
                    self.assertIn(f"{prefix}/stream/{group}/{model}/{model}.yft", z.namelist())
                    self.assertIn(f"{prefix}/stream/{group}/{model}/{model}.ytd", z.namelist())
                    self.assertIn(model, z.read(f"{prefix}/vehicle_names.lua").decode())
                    self.assertNotIn("server_script", z.read(f"{prefix}/fxmanifest.lua").decode())
            self.assertEqual((src / "stream" / "[ACURA]" / "tltypes" / "tltypes.yft").read_bytes(), b"YFT_SAMPLE")
            self.assertTrue((out / "INSTRUCOES_PACK1.txt").is_file())
            self.assertTrue((out / "relatorio_marcas.json").is_file())


if __name__ == "__main__":
    unittest.main()
