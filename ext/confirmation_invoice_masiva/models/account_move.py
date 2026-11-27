# -*- coding: utf-8 -*-
from odoo import models


class AccountMove(models.Model):
    _inherit = 'account.move'

    def _notify_get_recipients_groups(self, message, model_description, msg_vals=None):
        """Oculta el botón 'View Invoice' / 'Ver Factura' en los correos salientes
        de facturas cuando la compañía usa Facturación Digital (Unidigital).
        De esta forma el cliente recibe únicamente el PDF fiscal adjunto y no un
        botón con enlace externo/portal que arroje error 404.
        """
        groups = super()._notify_get_recipients_groups(
            message, model_description, msg_vals=msg_vals
        )
        if len(self) == 1 and self.company_id.usar_fact_digi and self.is_invoice(include_receipts=True):
            for _group_name, _group_func, group_data in groups:
                group_data['has_button_access'] = False
                group_data.pop('button_access', None)
        return groups
