import math
from uuid import UUID

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class RouteManagerTrip(models.Model):
    _name = "pink.routemanager.trip"
    _description = "Viaje de RouteManager"
    _rec_name = "routemanager_id"
    _order = "date desc, id desc"
    _check_company_auto = True

    routemanager_id = fields.Char(
        string="ID de viaje RouteManager", required=True, index=True, copy=False
    )
    company_id = fields.Many2one(
        "res.company",
        string="Compañía Odoo",
        required=True,
        default=lambda self: self.env.company,
        index=True,
        ondelete="restrict",
    )
    customer_id = fields.Many2one(
        "res.partner",
        string="Empresa del viaje",
        required=True,
        check_company=True,
        domain="[('pink_role', '=', 'company')]",
        ondelete="restrict",
        index=True,
    )
    driver_id = fields.Many2one(
        "res.partner",
        string="Conductor",
        required=True,
        check_company=True,
        domain="[('pink_role', '=', 'driver')]",
        ondelete="restrict",
        index=True,
    )
    date = fields.Datetime(string="Fecha del viaje (UTC)", required=True, index=True)
    product_id = fields.Many2one(
        "product.product",
        string="Servicio",
        required=True,
        check_company=True,
        default=lambda self: self.env.ref("pink_routemanager.product_trip"),
        ondelete="restrict",
    )
    distance_km = fields.Float(string="Kilómetros", required=True, digits=(16, 3))
    uom_id = fields.Many2one(
        "uom.uom",
        string="Unidad",
        required=True,
        readonly=True,
        default=lambda self: self.env.ref("uom.product_uom_km"),
        ondelete="restrict",
    )
    state = fields.Selection(
        [("COMPLETED", "Completado"), ("CANCELLED", "Cancelado")],
        string="Estado",
        required=True,
        default="COMPLETED",
    )
    passenger_type = fields.Selection(
        [("pasajeroapp", "pasajeroapp")], string="Tipo de pasajero"
    )
    active = fields.Boolean(default=True)

    _routemanager_id_unique = models.Constraint(
        "UNIQUE(routemanager_id)",
        "Este viaje de RouteManager ya está registrado en Odoo.",
    )
    _distance_nonnegative = models.Constraint(
        "CHECK(distance_km >= 0)",
        "El kilometraje no puede ser negativo.",
    )

    @api.constrains(
        "routemanager_id",
        "distance_km",
        "state",
        "customer_id",
        "driver_id",
        "product_id",
        "uom_id",
        "company_id",
    )
    def _check_trip(self):
        product = self.env.ref("pink_routemanager.product_trip")
        km = self.env.ref("uom.product_uom_km")
        for trip in self:
            try:
                if str(UUID(trip.routemanager_id)) != trip.routemanager_id:
                    raise ValueError("Non-canonical UUID")
            except (ValueError, TypeError, AttributeError) as error:
                raise ValidationError(
                    _("El ID del viaje debe ser un UUID de RouteManager válido.")
                ) from error
            if (
                not math.isfinite(trip.distance_km)
                or trip.distance_km < 0
                or (trip.state == "COMPLETED" and trip.distance_km <= 0)
            ):
                raise ValidationError(
                    _(
                        "Un viaje completado necesita kilómetros definitivos mayores que cero."
                    )
                )
            if (
                trip.customer_id.pink_role != "company"
                or trip.driver_id.pink_role != "driver"
            ):
                raise ValidationError(
                    _("El viaje debe vincular una empresa Pink y un conductor.")
                )
            if (
                trip.customer_id.company_id != trip.company_id
                or trip.driver_id.company_id != trip.company_id
            ):
                raise ValidationError(
                    _(
                        "La empresa y el conductor deben pertenecer a la compañía Odoo del viaje."
                    )
                )
            if (
                trip.product_id != product
                or product.type != "service"
                or product.uom_id != km
                or trip.uom_id != km
            ):
                raise ValidationError(
                    _(
                        "Use el producto Viaje de Pink RouteManager, de tipo servicio y medido en km."
                    )
                )

    @api.model
    def _check_distance_value(self, value):
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            or value < 0
        ):
            raise ValidationError(
                self.env._(
                    "Envíe kilómetros numéricos, finitos y no negativos; un dato desconocido no equivale a cero."
                )
            )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            self._check_distance_value(vals.get("distance_km"))
        return super().create(vals_list)

    def write(self, vals):
        self.check_access("write")
        if "distance_km" in vals:
            self._check_distance_value(vals["distance_km"])
        if "routemanager_id" in vals and any(
            trip.routemanager_id != vals["routemanager_id"] for trip in self
        ):
            raise ValidationError(
                _("No se puede cambiar el ID de un viaje ya vinculado a RouteManager.")
            )
        return super().write(vals)
