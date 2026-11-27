# -*- coding: utf-8 -*-
import logging
from odoo import api, fields, models, _

_logger = logging.getLogger(__name__)


class AccountMoveMassConfirm(models.TransientModel):
    _name = 'account.move.mass.confirm'
    _description = 'Confirmación Masiva de Facturas'

    date_from = fields.Date(string='Fecha desde')
    date_to = fields.Date(string='Fecha hasta')
    partner_id = fields.Many2one('res.partner', string='Cliente')
    company_id = fields.Many2one(
        'res.company',
        string='Compañía',
        default=lambda self: self.env.company,
    )

    def action_confirm_invoices(self):
        self.ensure_one()

        domain = [
            ('state', '=', 'draft'),
            ('move_type', 'in', ('out_invoice', 'out_refund')),
            ('company_id', '=', self.company_id.id),
        ]

        active_ids = (
            self.env.context.get('active_ids')
            if self.env.context.get('active_model') == 'account.move'
            else None
        )
        if active_ids and not (self.date_from or self.date_to or self.partner_id):
            domain.append(('id', 'in', active_ids))
        else:
            if self.date_from:
                domain.append(('invoice_date', '>=', self.date_from))
            if self.date_to:
                domain.append(('invoice_date', '<=', self.date_to))
            if self.partner_id:
                domain.append(('partner_id', '=', self.partner_id.id))

        invoices = self.env['account.move'].search(
            domain, order='invoice_date asc, id asc'
        )

        if not invoices:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Sin facturas'),
                    'message': _('No se encontraron facturas en estado borrador para los filtros seleccionados.'),
                    'type': 'warning',
                    'sticky': False,
                },
            }

        # Guardamos los IDs y etiquetas antes de iterar para soportar commit/rollback por factura
        invoice_items = [
            (inv.id, inv.partner_id.display_name or _('Sin cliente'), bool(inv.company_id.usar_fact_digi))
            for inv in invoices
        ]

        confirmed_count = 0
        failed_details = []

        for inv_id, partner_name, use_digital in invoice_items:
            inv = self.env['account.move'].browse(inv_id)
            if not inv.exists() or inv.state != 'draft':
                continue
            try:
                if use_digital:
                    inv.confirmar2()
                    if inv.state == 'posted':
                        confirmed_count += 1
                    else:
                        reason = inv.errorMessage or inv.information or _('Rechazada por Unidigital')
                        failed_details.append(f"ID {inv_id} ({partner_name}): {reason}")
                    # Persistimos inmediatamente cada factura procesada contra Unidigital
                    # para que un error posterior nunca revierta documentos ya emitidos fiscalmente.
                    self.env.cr.commit()
                else:
                    with self.env.cr.savepoint():
                        inv.action_post()
                    confirmed_count += 1
                    self.env.cr.commit()
            except Exception as err:
                self.env.cr.rollback()
                _logger.warning(
                    "Confirmación masiva: error en factura ID %s (%s): %s",
                    inv_id, partner_name, err,
                )
                failed_details.append(f"ID {inv_id} ({partner_name}): {err}")

        if failed_details:
            preview_errors = '\n'.join(failed_details[:5])
            extra = (
                f"\n... y {len(failed_details) - 5} error(es) más (ver log del servidor)."
                if len(failed_details) > 5
                else ''
            )
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Confirmación masiva con observaciones'),
                    'message': _(
                        'Confirmadas: %(ok)s | Con error: %(err)s.\n%(details)s%(extra)s',
                        ok=confirmed_count,
                        err=len(failed_details),
                        details=preview_errors,
                        extra=extra,
                    ),
                    'type': 'warning',
                    'sticky': True,
                },
            }

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Éxito'),
                'message': _('Se confirmaron y enviaron %s facturas correctamente.') % confirmed_count,
                'type': 'success',
                'sticky': False,
            },
        }
