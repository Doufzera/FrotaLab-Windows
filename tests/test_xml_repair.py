"""Regressão para reparo de XML e instalação do Bugatti do Pack 1."""
import tempfile
import unittest
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

from installer import install_pack
from metadata_repair import parse_vehicle_meta
from frotalab import split_pack1_by_brand


BAD_XML = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<CVehicleModelInfo__InitDataList>\n'
    '  <InitDatas><Item><modelName>bolide</modelName>'
    '<gameName>bolide</gameName></Item></InitDatas>\n'
    '  <!------------------------------------------------------------------------------------------------------------------->\n'
    '  <txdRelationships><Item><parent>example</parent>'
    '<child>bolide</child></Item></txdRelationships>\n'
    '</CVehicleModelInfo__InitDataList>\n'
)


class MetadataRepairTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def write(self, path, contents):
        p = self.root / path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(contents, encoding="utf-8")
        return p

    def test_repairs_only_copy_of_invalid_separator(self):
        meta = self.write("vehicles.meta", BAD_XML)
        with self.assertRaises(ET.ParseError):
            ET.parse(meta)
        xml, repaired, count = parse_vehicle_meta(meta)
        self.assertEqual(count, 1)
        self.assertIn(b"<!-- separador -->", repaired)
        self.assertEqual(xml.findtext(".//modelName"), "bolide")
        self.assertEqual(meta.read_text(encoding="utf-8"), BAD_XML)
        ET.fromstring(repaired)

    def test_valid_xml_remains_unchanged(self):
        meta = self.write("vehicles.meta", "<Root><Item>ok</Item></Root>")
        _, repaired, count = parse_vehicle_meta(meta)
        self.assertIsNone(repaired)
        self.assertEqual(count, 0)

    def test_other_xml_errors_do_not_get_auto_modified(self):
        malformed = "<Root><Item></Root>"
        meta = self.write("vehicles.meta", malformed)
        with self.assertRaises(ValueError):
            parse_vehicle_meta(meta)
        self.assertEqual(meta.read_text(encoding="utf-8"), malformed)

    def test_repairs_bugatti_when_installing_and_exporting(self):
        root = "originais/pacote_01/FiveM-Civ-Car-Pack-master/PLOKS_CARS"
        self.write(root + "/fxmanifest.lua", "fx_version 'cerulean'\ngame 'gta5'\n")
        self.write(root + "/server.lua", "print('server')\n")
        self.write(root + "/vehicle_names.lua",
                   "CreateThread(function()\n"
                   "AddTextEntry('bolide', 'Bugatti Bolide')\n"
                   "AddTextEntry('tltypes', 'Acura TL')\nend)\n")
        self.write(root + "/data/[BUGATTI]/bolide/vehicles.meta", BAD_XML)
        self.write(root + "/stream/[BUGATTI]/bolide/bolide.yft", "YFT")
        self.write(root + "/stream/[BUGATTI]/bolide/bolide.ytd", "YTD")
        self.write(root + "/data/[ACURA]/tltypes/vehicles.meta",
                   "<Root><InitDatas><Item><modelName>tltypes</modelName>"
                   "</Item></InitDatas></Root>")
        self.write(root + "/stream/[ACURA]/tltypes/tltypes.yft", "YFT")
        self.write(root + "/stream/[ACURA]/tltypes/tltypes.ytd", "YTD")
        resources = self.root / "server" / "resources"
        resources.mkdir(parents=True)
        installed, names = install_pack(self.root / "originais", 1, resources)
        self.assertEqual(names, ["CIV_ACURA", "CIV_BUGATTI"])
        repaired = installed / "CIV_BUGATTI/data/[BUGATTI]/bolide/vehicles.meta"
        ET.parse(repaired)
        self.assertTrue((installed / "CIV_BUGATTI/CORRECOES_META.txt").is_file())
        original = self.root / root / "data/[BUGATTI]/bolide/vehicles.meta"
        with self.assertRaises(ET.ParseError):
            ET.parse(original)

        exported = self.root / "export"
        result = split_pack1_by_brand(self.root / "originais", exported)
        self.assertEqual(result, ["CIV_ACURA.zip", "CIV_BUGATTI.zip"])
        with zipfile.ZipFile(exported / "CIV_BUGATTI.zip") as z:
            self.assertIsNone(z.testzip())
            archive_meta = z.read(
                "CIV_BUGATTI/data/[BUGATTI]/bolide/vehicles.meta")
            ET.fromstring(archive_meta)
            self.assertIn("CIV_BUGATTI/CORRECOES_META.txt", z.namelist())
        with self.assertRaises(ET.ParseError):
            ET.parse(original)

    def test_repairs_bugatti_in_unsplit_pack_without_touching_original(self):
        root = "originais/pacote_01/FiveM-Civ-Car-Pack-master/PLOKS_CARS"
        self.write(root + "/fxmanifest.lua", "fx_version 'cerulean'\n")
        self.write(root + "/server.lua", "print('server')\n")
        self.write(root + "/data/[BUGATTI]/bolide/vehicles.meta", BAD_XML)
        self.write(root + "/stream/[BUGATTI]/bolide/bolide.yft", "YFT")
        resources = self.root / "server" / "resources"
        resources.mkdir(parents=True)
        installed, names = install_pack(
            self.root / "originais", 1, resources, split_pack1=False)
        self.assertEqual(names, ["PLOKS_CARS"])
        installed_meta = installed / "PLOKS_CARS/data/[BUGATTI]/bolide/vehicles.meta"
        ET.parse(installed_meta)
        self.assertTrue((installed / "PLOKS_CARS/CORRECOES_META.txt").is_file())
        with self.assertRaises(ET.ParseError):
            ET.parse(self.root / root / "data/[BUGATTI]/bolide/vehicles.meta")


if __name__ == "__main__":
    unittest.main()
