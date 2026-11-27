# -*- coding: utf-8 -*-
import json
import logging
import requests
from odoo import api, fields, models, _

_logger = logging.getLogger(__name__)


class AccountMoveSend(models.AbstractModel):
    _inherit = 'account.move.send'

    def _prepare_invoice_pdf_report(self, invoices_data, **kwargs):
        """
        Descarga el PDF directamente desde la URL de Unidigital (reutilizando el adjunto
        si ya fue descargado previamente en el wizard) y lo adjunta al envío de correo,
        omitiendo el PDF nativo de Odoo.
        """
        invoices_digital = self.env['account.move']
        Attachment = self.env['ir.attachment']

        for invoice, invoice_data in invoices_data.items():
            if not invoice.company_id.usar_fact_digi or not invoice.result:
                continue

            # 1. Extraer el UUID limpio de result (igual que en print_digital)
            raw_res = invoice.result
            clean_result = ""
            try:
                parsed_res = json.loads(raw_res)
                if isinstance(parsed_res, dict):
                    clean_result = str(parsed_res.get('id') or parsed_res.get('documentId') or '')
                else:
                    clean_result = str(parsed_res)
            except Exception:
                clean_result = str(raw_res)

            clean_result = clean_result.strip('"\'').strip()
            if not clean_result:
                continue

            file_name = f"{invoice.name.replace('/', '_')}_fiscal.pdf"

            # 2. Reutilizar adjunto si ya fue descargado al abrir el wizard (evita duplicados)
            attachment = Attachment.search([
                ('res_model', '=', 'account.move'),
                ('res_id', '=', invoice.id),
                ('name', '=', file_name),
            ], limit=1)

            pdf_raw = attachment.raw if attachment and attachment.raw else None

            if not pdf_raw:
                base_url = (invoice.company_id.url or '').strip().rstrip('/')
                endpoint = (invoice.company_id.endpoint_pdf_doc or '').strip().strip('/')
                pdf_url = f"{base_url}/{endpoint}/{clean_result}"

                try:
                    _logger.info("Unidigital: Descargando PDF fiscal para correo desde: %s", pdf_url)
                    headers = {
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
                        "Accept": "application/pdf, application/json, */*"
                    }
                    if invoice.company_id.unidg_jwt_token:
                        headers["Authorization"] = f"Bearer {invoice.company_id.unidg_jwt_token}"

                    response = requests.get(pdf_url, headers=headers, timeout=25)
                    if response.status_code == 200 and response.content:
                        pdf_raw = response.content
                        attachment = Attachment.create({
                            'name': file_name,
                            'raw': pdf_raw,
                            'mimetype': 'application/pdf',
                            'res_model': 'account.move',
                            'res_id': invoice.id,
                            'type': 'binary',
                        })
                    else:
                        _logger.warning("Unidigital: Código %s al descargar PDF desde %s", response.status_code, pdf_url)
                except Exception as e:
                    _logger.error("Unidigital: Error descargando PDF de Unidigital: %s", str(e))

            if pdf_raw and attachment:
                invoice_data['pdf_attachment_values'] = {
                    'name': file_name,
                    'raw': pdf_raw,
                    'mimetype': 'application/pdf',
                    'res_model': 'account.move',
                    'res_id': invoice.id,
                }
                if 'attachment_ids' in invoice_data:
                    invoice_data['attachment_ids'] = list(set(invoice_data['attachment_ids'] + [attachment.id]))
                else:
                    invoice_data['attachment_ids'] = [attachment.id]

                invoices_digital |= invoice
                _logger.info("Unidigital: PDF fiscal adjuntado con éxito a la factura %s", invoice.name)

        # Para las facturas que no son de Unidigital, se ejecuta el flujo estándar de Odoo
        remaining_invoices_data = {
            inv: data for inv, data in invoices_data.items() if inv not in invoices_digital
        }

        if remaining_invoices_data:
            return super()._prepare_invoice_pdf_report(remaining_invoices_data, **kwargs)

        return invoices_data


class AccountMoveSendWizard(models.TransientModel):
    _inherit = 'account.move.send.wizard'

    @api.depends('move_id')
    def _compute_mail_attachments_widget(self):
        """
        Al abrir la ventana emergente de envío, descarga el PDF de Unidigital
        si aún no existe y reemplaza el adjunto nativo de Odoo en la vista previa.
        """
        super()._compute_mail_attachments_widget()

        Attachment = self.env['ir.attachment']

        for wizard in self:
            move = wizard.move_id
            if not move or not move.company_id.usar_fact_digi or not move.result:
                continue

            raw_res = move.result
            clean_result = ""
            try:
                parsed_res = json.loads(raw_res)
                if isinstance(parsed_res, dict):
                    clean_result = str(parsed_res.get('id') or parsed_res.get('documentId') or '')
                else:
                    clean_result = str(parsed_res)
            except Exception:
                clean_result = str(raw_res)

            clean_result = clean_result.strip('"\'').strip()
            if not clean_result:
                continue

            file_name = f"{move.name.replace('/', '_')}_fiscal.pdf"

            attachment = Attachment.search([
                ('res_model', '=', 'account.move'),
                ('res_id', '=', move.id),
                ('name', '=', file_name),
            ], limit=1)

            if not attachment:
                base_url = (move.company_id.url or '').strip().rstrip('/')
                endpoint = (move.company_id.endpoint_pdf_doc or '').strip().strip('/')
                pdf_url = f"{base_url}/{endpoint}/{clean_result}"

                try:
                    headers = {
                        "User-Agent": "Mozilla/5.0",
                        "Accept": "application/pdf, application/json, */*"
                    }
                    if move.company_id.unidg_jwt_token:
                        headers["Authorization"] = f"Bearer {move.company_id.unidg_jwt_token}"

                    res = requests.get(pdf_url, headers=headers, timeout=20)
                    if res.status_code == 200 and res.content:
                        attachment = Attachment.create({
                            'name': file_name,
                            'raw': res.content,
                            'mimetype': 'application/pdf',
                            'res_model': 'account.move',
                            'res_id': move.id,
                            'type': 'binary',
                        })
                        _logger.info("Unidigital: PDF descargado y guardado para el wizard: %s", file_name)
                except Exception as e:
                    _logger.error("Unidigital: Error descargando PDF para el wizard de %s: %s", move.name, str(e))

            if attachment:
                wizard.mail_attachments_widget = [{
                    'id': attachment.id,
                    'name': attachment.name,
                    'mimetype': attachment.mimetype,
                    'placeholder': False,
                    'protect_from_deletion': True,
                }]
