from uuid import uuid4

from psycopg2 import IntegrityError

from odoo import Command
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import TransactionCase, tagged
from odoo.tests.common import new_test_user
from odoo.tools import mute_logger


@tagged("post_install", "-at_install")
class TestPinkRouteManager(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner = cls.env["res.partner"]
        cls.trip = cls.env["pink.routemanager.trip"]
        cls.customer = cls.partner.create(cls._contact_values("company"))
        cls.driver = cls.partner.create(cls._contact_values("driver"))

    @classmethod
    def _contact_values(cls, role):
        return {
            "name": f"Pink test {role}",
            "is_company": role == "company",
            "company_id": cls.env.company.id,
            "pink_role": role,
            "pink_routemanager_id": str(uuid4()),
            "phone": "+584121234567",
            "email": f"{role}@example.test",
            "street": "Dirección de prueba",
            "pink_document_type": "J" if role == "company" else "V",
            "pink_document_number": "00123456-9",
            "pink_license": "Tipo 3",
            "pink_contact_name": "Responsable de prueba",
        }

    def _trip_values(self, **overrides):
        return {
            "routemanager_id": str(uuid4()),
            "company_id": self.env.company.id,
            "customer_id": self.customer.id,
            "driver_id": self.driver.id,
            "date": "2026-10-01 12:00:00",
            "distance_km": 12.5,
            **overrides,
        }

    def test_driver_license_and_document_are_preserved(self):
        self.assertEqual(self.driver.pink_license, "Tipo 3")
        self.assertEqual(self.driver.pink_document_number, "00123456-9")
        self.assertEqual(self.driver.pink_document_type, "V")

    def test_required_contact_fields_only_apply_to_pink(self):
        self.partner.create({"name": "Contacto normal sin datos Pink"})
        for role, field in (
            ("driver", "pink_license"),
            ("driver", "pink_document_type"),
            ("driver", "pink_document_number"),
            ("driver", "email"),
            ("driver", "phone"),
            ("company", "street"),
            ("company", "pink_contact_name"),
        ):
            with (
                self.subTest(role=role, field=field),
                self.assertRaises(ValidationError),
                self.cr.savepoint(),
            ):
                self.partner.create({**self._contact_values(role), field: False})

    def test_invalid_email_phone_document_and_identity(self):
        for field, value in (
            ("email", "invalid"),
            ("phone", "123"),
            ("pink_document_number", "  "),
            ("pink_routemanager_id", "not-a-uuid"),
            ("is_company", True),
        ):
            with (
                self.subTest(field=field),
                self.assertRaises(ValidationError),
                self.cr.savepoint(),
            ):
                self.partner.create({**self._contact_values("driver"), field: value})

    @mute_logger("odoo.sql_db")
    def test_duplicate_contact_external_id_is_rejected(self):
        with self.assertRaises(IntegrityError), self.cr.savepoint():
            self.partner.create(
                {
                    **self._contact_values("driver"),
                    "pink_routemanager_id": self.driver.pink_routemanager_id,
                }
            )
            self.partner.flush_model()

    def test_trip_uses_one_service_in_km(self):
        trip = self.trip.create(self._trip_values(passenger_type="pasajeroapp"))
        self.assertEqual(
            trip.product_id, self.env.ref("pink_routemanager.product_trip")
        )
        self.assertEqual(trip.product_id.type, "service")
        self.assertEqual(trip.uom_id, self.env.ref("uom.product_uom_km"))
        self.assertEqual(trip.distance_km, 12.5)
        self.assertEqual(trip.customer_id, self.customer)
        self.assertEqual(trip.passenger_type, "pasajeroapp")
        self.assertNotIn("passenger_id", self.trip._fields)
        self.assertNotIn("vehicle_id", self.trip._fields)

    def test_trip_company_does_not_come_from_driver_employer(self):
        another_customer = self.partner.create(self._contact_values("company"))
        self.driver.pink_employer_id = another_customer
        trip = self.trip.create(self._trip_values())
        self.assertEqual(trip.customer_id, self.customer)
        self.assertNotEqual(trip.customer_id, trip.driver_id.pink_employer_id)

    @mute_logger("odoo.sql_db")
    def test_invalid_trip_kilometers_and_identity_are_rejected(self):
        for overrides in (
            {"distance_km": 0},
            {"distance_km": -1},
            {"distance_km": float("inf")},
            {"distance_km": float("nan")},
            {"routemanager_id": "not-a-uuid"},
            {"customer_id": self.driver.id},
            {"driver_id": self.customer.id},
        ):
            with (
                self.subTest(overrides=overrides),
                self.assertRaises(ValidationError),
                self.cr.savepoint(),
            ):
                self.trip.create(self._trip_values(**overrides))

    def test_unknown_distance_is_not_zero_even_for_cancelled_trips(self):
        for distance in (None, False):
            with (
                self.subTest(distance=distance),
                self.assertRaises(ValidationError),
                self.cr.savepoint(),
            ):
                self.trip.create(
                    self._trip_values(state="CANCELLED", distance_km=distance)
                )
        values = self._trip_values(state="CANCELLED")
        del values["distance_km"]
        with self.assertRaises(ValidationError), self.cr.savepoint():
            self.trip.create(values)
        trip = self.trip.create(self._trip_values(state="CANCELLED"))
        with self.assertRaises(ValidationError), self.cr.savepoint():
            trip.write({"distance_km": False})

    def test_foreign_service_or_unit_is_rejected(self):
        other_product = self.env["product.product"].create(
            {"name": "Otro servicio", "type": "service"}
        )
        for overrides in (
            {"product_id": other_product.id},
            {"uom_id": self.env.ref("uom.product_uom_meter").id},
        ):
            with (
                self.subTest(overrides=overrides),
                self.assertRaises(ValidationError),
                self.cr.savepoint(),
            ):
                self.trip.create(self._trip_values(**overrides))

    def test_cancelled_trip_allows_zero_distance(self):
        trip = self.trip.create(self._trip_values(state="CANCELLED", distance_km=0))
        self.assertEqual(trip.state, "CANCELLED")

    @mute_logger("odoo.sql_db")
    def test_trip_external_id_is_unique_and_immutable(self):
        trip = self.trip.create(self._trip_values())
        with self.assertRaises(IntegrityError), self.cr.savepoint():
            self.trip.create(self._trip_values(routemanager_id=trip.routemanager_id))
            self.trip.flush_model()
        with self.assertRaises(ValidationError), self.cr.savepoint():
            trip.routemanager_id = str(uuid4())
        with self.assertRaises(ValidationError), self.cr.savepoint():
            self.driver.pink_routemanager_id = str(uuid4())

    def test_trip_can_be_updated_without_creating_another(self):
        trip = self.trip.create(self._trip_values())
        trip.write({"distance_km": 15.75})
        self.assertEqual(
            self.trip.search_count([("routemanager_id", "=", trip.routemanager_id)]), 1
        )
        self.assertEqual(trip.distance_km, 15.75)

    def test_partner_role_cannot_break_existing_trips(self):
        trip = self.trip.create(self._trip_values())
        trip.active = False
        with self.assertRaises(ValidationError), self.cr.savepoint():
            self.driver.write({"pink_role": False})

    def test_employer_role_cannot_break_driver_affiliation(self):
        self.driver.pink_employer_id = self.customer
        with self.assertRaises(ValidationError), self.cr.savepoint():
            self.customer.pink_role = False

    def test_driver_sensitive_fields_require_pink_group(self):
        outsider = new_test_user(
            self.env,
            login="pink_contact_outsider",
            groups="base.group_user,base.group_partner_manager",
        )
        with self.assertRaises(AccessError), self.cr.savepoint():
            self.driver.with_user(outsider).read(
                ["pink_license", "pink_document_number"]
            )
        with self.assertRaises(AccessError), self.cr.savepoint():
            self.driver.with_user(outsider).write({"pink_license": "Tipo 4"})
        self.driver.with_user(outsider).write({"name": "Nombre corregido"})
        self.assertEqual(self.driver.name, "Nombre corregido")

    def test_cross_company_trip_is_rejected(self):
        other_company = self.env["res.company"].create(
            {"name": "Otra compañía de prueba"}
        )
        with self.assertRaises(UserError), self.cr.savepoint():
            self.trip.create(self._trip_values(company_id=other_company.id))

    def test_access_group_and_company_isolation(self):
        trip = self.trip.create(self._trip_values())
        user = new_test_user(
            self.env,
            login="pink_integration_test",
            groups="pink_routemanager.group_pink_routemanager",
        )
        user.write(
            {
                "company_id": self.env.company.id,
                "company_ids": [Command.set([self.env.company.id])],
            }
        )
        self.assertEqual(trip.with_user(user).distance_km, 12.5)
        with self.assertRaises(AccessError), self.cr.savepoint():
            trip.with_user(user).unlink()
        outsider = new_test_user(
            self.env, login="pink_outsider_test", groups="base.group_user"
        )
        with self.assertRaises(AccessError), self.cr.savepoint():
            self.trip.with_user(outsider).search_read([], ["distance_km"])
        other_company = self.env["res.company"].create(
            {"name": "Otra compañía aislada"}
        )
        other_customer = self.partner.create(
            {**self._contact_values("company"), "company_id": other_company.id}
        )
        other_driver = self.partner.create(
            {**self._contact_values("driver"), "company_id": other_company.id}
        )
        other_trip = self.trip.create(
            self._trip_values(
                company_id=other_company.id,
                customer_id=other_customer.id,
                driver_id=other_driver.id,
            )
        )
        with self.assertRaises(AccessError), self.cr.savepoint():
            other_trip.with_user(user).read(["distance_km"])
