"""Dependency-free source checks; runtime invariants are tested by Odoo in CI."""

import ast
import csv
import unittest
from pathlib import Path
from xml.etree import ElementTree


ROOT = Path(__file__).resolve().parents[1]
ADDON = ROOT / "pink_routemanager"


class TestModuleStructure(unittest.TestCase):
    def test_python_and_xml_parse(self):
        for path in ADDON.rglob("*.py"):
            with self.subTest(path=path):
                ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for path in ADDON.rglob("*.xml"):
            with self.subTest(path=path):
                self.assertEqual(ElementTree.parse(path).getroot().tag, "odoo")

    def test_manifest_files_exist_without_out_of_scope_dependencies(self):
        manifest = ast.literal_eval(
            (ADDON / "__manifest__.py").read_text(encoding="utf-8")
        )
        self.assertTrue(manifest["version"].startswith("19.0."))
        self.assertEqual(set(manifest["depends"]), {"contacts", "product", "uom"})
        for path in manifest["data"]:
            self.assertTrue((ADDON / path).is_file(), path)
        self.assertIn(
            "test_routemanager",
            (ADDON / "tests/__init__.py").read_text(encoding="utf-8"),
        )

    def test_quality_keeps_existing_purchase_field_provider(self):
        # The quality database still uses views from the original custom addons.
        baseline = ROOT / "Localizacion_contable/base_contable"
        self.assertTrue((baseline / "__manifest__.py").is_file())
        self.assertTrue(
            (ROOT / "Facturacion Digital/factura_digital_unidigital/__manifest__.py").is_file()
        )
        self.assertIn(
            "from . import model", (baseline / "__init__.py").read_text(encoding="utf-8")
        )
        self.assertIn(
            "from . import sale_purchase_order",
            (baseline / "model/__init__.py").read_text(encoding="utf-8"),
        )
        model = ast.parse(
            (baseline / "model/sale_purchase_order.py").read_text(encoding="utf-8")
        )
        purchase = next(node for node in model.body if isinstance(node, ast.ClassDef)
                        and node.name == "PurchaseOrder")
        assignments = {node.targets[0].id: node.value for node in purchase.body
                       if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name)}
        self.assertEqual(ast.literal_eval(assignments["_inherit"]), "purchase.order")
        self.assertEqual(assignments["x_tasa"].func.attr, "Float")
        view = ElementTree.parse(baseline / "vista/purchase_inherit.xml")
        self.assertIsNotNone(view.find(".//field[@name='x_tasa']"))

    def test_trip_access_requires_group_and_has_no_delete(self):
        with (ADDON / "security/ir.model.access.csv").open(
            encoding="utf-8", newline=""
        ) as source:
            rows = list(csv.DictReader(source))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["group_id:id"], "group_pink_routemanager")
        self.assertEqual(rows[0]["perm_unlink"], "0")
        rules = ElementTree.parse(ADDON / "security/pink_security.xml")
        rule = rules.find(".//record[@id='trip_company_rule']")
        self.assertIsNotNone(rule)
        self.assertIsNone(rule.find("field[@name='groups']"))
        self.assertEqual(
            rule.find("field[@name='domain_force']").text,
            "[('company_id', 'in', company_ids)]",
        )

    def test_product_is_service_in_km_not_a_sellable_invoice_item(self):
        product = ElementTree.parse(ADDON / "data/trip_product.xml").find(
            ".//record[@id='product_trip']"
        )
        self.assertEqual(product.find("field[@name='type']").text, "service")
        self.assertEqual(
            product.find("field[@name='uom_id']").attrib["ref"], "uom.product_uom_km"
        )
        self.assertEqual(product.find("field[@name='sale_ok']").attrib["eval"], "False")


if __name__ == "__main__":
    unittest.main(verbosity=2)
