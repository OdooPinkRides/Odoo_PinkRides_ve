# -*- coding: utf-8 -*-
from odoo import fields, models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    codigo_conductora = fields.Char(
        string='Código',
        help='Código identificador asignado al contacto (cliente o conductora).',
        index=True,
    )