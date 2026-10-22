import re
from uuid import UUID

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError
from odoo.tools import email_normalize


PINK_GROUP = "pink_routemanager.group_pink_routemanager"


class ResPartner(models.Model):
    _inherit = "res.partner"

    pink_role = fields.Selection(
        [("company", "Empresa RouteManager"), ("driver", "Conductor")],
        string="Tipo de contacto Pink",
        copy=False,
        groups=PINK_GROUP,
    )
    pink_routemanager_id = fields.Char(
        string="ID RouteManager", copy=False, groups=PINK_GROUP
    )
    # The accounting fields doc_tipo/vat_aux are absent from the current registry.
    pink_document_type = fields.Selection(
        [(value, value) for value in ("V", "E", "J", "G", "P", "C")],
        string="Tipo de documento Pink",
        groups=PINK_GROUP,
    )
    pink_document_number = fields.Char(
        string="Número de documento Pink", groups=PINK_GROUP
    )
    pink_license = fields.Char(
        string="Licencia (RouteManager)",
        groups=PINK_GROUP,
        help="Valor original de license, por ejemplo Tipo 3. No se inventa un número de licencia.",
    )
    pink_contact_name = fields.Char(
        string="Responsable de la empresa", groups=PINK_GROUP
    )
    pink_employer_id = fields.Many2one(
        "res.partner",
        string="Empresa del conductor",
        check_company=True,
        ondelete="restrict",
        groups=PINK_GROUP,
        domain="[('pink_role', '=', 'company')]",
    )

    _pink_routemanager_id_unique = models.Constraint(
        "UNIQUE(pink_routemanager_id)",
        "El ID de RouteManager ya está vinculado a otro contacto.",
    )

    @api.constrains(
        "pink_role",
        "pink_routemanager_id",
        "pink_document_type",
        "pink_document_number",
        "pink_license",
        "pink_contact_name",
        "pink_employer_id",
        "name",
        "phone",
        "email",
        "street",
        "is_company",
        "company_id",
    )
    def _check_pink_contact(self):
        # Validate protected fields internally without exposing them to ordinary contact users.
        for partner in self.sudo():
            if not partner.pink_role:
                if partner.pink_routemanager_id:
                    raise ValidationError(
                        _("Un contacto de RouteManager debe indicar su tipo Pink.")
                    )
                continue
            required = [
                "name",
                "phone",
                "email",
                "pink_document_type",
                "pink_document_number",
                "company_id",
            ]
            required += (
                ["street", "pink_contact_name"]
                if partner.pink_role == "company"
                else ["pink_license"]
            )
            if any(
                not partner[field]
                or (isinstance(partner[field], str) and not partner[field].strip())
                for field in required
            ):
                raise ValidationError(
                    _(
                        "Complete los datos obligatorios del contacto Pink, incluido su documento."
                    )
                )
            if partner.is_company != (partner.pink_role == "company"):
                raise ValidationError(
                    _(
                        "Una empresa Pink debe ser compañía y un conductor debe ser persona."
                    )
                )
            if (
                not email_normalize(partner.email)
                or len(re.sub(r"\D", "", partner.phone)) < 7
            ):
                raise ValidationError(
                    _(
                        "Indique un correo válido y un teléfono con al menos siete dígitos."
                    )
                )
            if not re.fullmatch(
                r"[A-Za-z0-9]+(?:-[A-Za-z0-9]+)*", partner.pink_document_number
            ):
                raise ValidationError(
                    _(
                        "El número de documento debe contener letras, números o guiones, sin prefijo de tipo."
                    )
                )
            if partner.pink_routemanager_id:
                try:
                    if (
                        str(UUID(partner.pink_routemanager_id))
                        != partner.pink_routemanager_id
                    ):
                        raise ValueError("Non-canonical UUID")
                except ValueError as error:
                    raise ValidationError(
                        _("El ID de RouteManager debe ser un UUID válido.")
                    ) from error
            employer = partner.pink_employer_id
            if employer and (
                partner.pink_role != "driver"
                or employer.pink_role != "company"
                or employer.company_id != partner.company_id
            ):
                raise ValidationError(
                    _(
                        "La empresa del conductor debe ser una empresa Pink de la misma compañía Odoo."
                    )
                )

    def write(self, vals):
        self.check_access("write")
        affected_ids = []
        # Sudo reads only these contacts and fixed existence checks, including archived references.
        for partner in self.sudo():
            if (
                partner.pink_routemanager_id
                and "pink_routemanager_id" in vals
                and vals["pink_routemanager_id"] != partner.pink_routemanager_id
            ):
                raise ValidationError(
                    _(
                        "No se puede cambiar el ID de un contacto ya vinculado a RouteManager."
                    )
                )
            changed = any(
                field in vals and vals[field] != partner[field]
                for field in ("pink_role", "is_company")
            )
            moved = "company_id" in vals and vals["company_id"] != partner.company_id.id
            if changed or moved:
                affected_ids.append(partner.id)
        if affected_ids:
            trips = (
                self.env["pink.routemanager.trip"]
                .sudo()
                .with_context(active_test=False)
            )
            employers = self.sudo().with_context(active_test=False)
            if trips.search_count(
                [
                    "|",
                    ("customer_id", "in", affected_ids),
                    ("driver_id", "in", affected_ids),
                ],
                limit=1,
            ) or employers.search_count(
                [("pink_employer_id", "in", affected_ids)], limit=1
            ):
                raise ValidationError(
                    _(
                        "No se puede cambiar el tipo o compañía de un contacto con viajes o conductores vinculados."
                    )
                )
        return super().write(vals)
