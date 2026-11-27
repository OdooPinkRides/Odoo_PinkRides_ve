# -*- coding: utf-8 -*-
from odoo import fields, models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    codigo_conductora = fields.Char(
        string='Código de Conductora',
        help='Código identificador asignado a la conductora.',
        index=True,
    )
