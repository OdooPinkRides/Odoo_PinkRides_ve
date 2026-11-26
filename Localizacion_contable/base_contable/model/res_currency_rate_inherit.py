# -*- coding: utf-8 -*-

import logging
import re
from datetime import date, datetime

import requests
import urllib3
from bs4 import BeautifulSoup
from pytz import timezone

from odoo import models, fields, api, _
from odoo.exceptions import UserError

try:
    import xlrd
except ImportError:
    xlrd = None

urllib3.disable_warnings()

_logger = logging.getLogger(__name__)


# Moneda..
class CurrencyRate(models.Model):
    _inherit = "res.currency.rate"

    BCV_URL = "https://www.bcv.org.ve/"
    BCV_HISTORY_XLS_TEMPLATE = (
        "https://www.bcv.org.ve/sites/default/files/EstadisticasGeneral/"
        "2_1_2{quarter}{year_short}_smc.xls"
    )
    BCV_REQUEST_TIMEOUT = 30
    BCV_CURRENCY_MAP = {
        'USD': 'dolar',
        'EUR': 'euro',
        'CNY': 'yuan',
        'TRY': 'lira',
        'RUB': 'rublo',
    }

    # _sql_constraints = [('unique_name', 'CHECK(1=1)', 'Only one currency rate per day allowed!')]
    # En Odoo 19 _sql_constraints fue reemplazado por models.Constraint y no debe usarse.
    # currency_id = fields.Many2one('res.currency',readonly=False,copied=False)

    @api.model_create_multi
    def create(self, vals_list):
        """
        Sobreescribe el método create para evitar la creación de tasas con fecha anterior a la actual.
        El campo de fecha en el modelo res.currency.rate se llama 'name'.
        Adaptado a Odoo 19 utilizando vals_list para el manejo multi-registro del ORM.
        """
        if not self.env.context.get('bcv_auto_update'):
            # 1. Iteramos la lista de diccionarios que recibe Odoo 19
            for vals in vals_list:
                # Obtener la fecha de la nueva tasa.
                # En res.currency.rate, el campo fecha se llama 'name' y es un DateField.
                rate_date_str = vals.get('name')

                if rate_date_str:
                    # Odoo puede enviar un objeto date/datetime o un string. Nos aseguramos de procesarlo como Date.
                    if isinstance(rate_date_str, (date, datetime)):
                        rate_date = rate_date_str.date() if isinstance(rate_date_str, datetime) else rate_date_str
                    else:
                        rate_date = fields.Date.from_string(rate_date_str)

                    today = date.today()

                    # 2. Realizar la validación
                    if rate_date < today:
                        # Si la fecha de la tasa es menor que la fecha actual (retroactiva), lanza el error.
                        raise UserError(
                            "❌ ¡Creación de Tasa Rechazada! "
                            "No se permite crear tipos de cambio con fecha anterior a la fecha actual."
                        )

        # 3. Si pasa la validación en todos los registros, llama al método original enviando la lista completa
        return super().create(vals_list)

    # Nuevo método: Evitar modificar a una fecha anterior
    def write(self, vals):
        """
        Sobreescribe el método write para evitar que se cambie la fecha ('name') 
        de un registro a una fecha anterior a la que ya tenía.
        """
        if not self.env.context.get('bcv_auto_update'):
            # Solo necesitamos ejecutar la lógica si se está intentando modificar el campo 'name' (fecha)
            if 'name' in vals:
                if isinstance(vals['name'], (date, datetime)):
                    new_date = vals['name'].date() if isinstance(vals['name'], datetime) else vals['name']
                else:
                    new_date = fields.Date.from_string(vals['name'])

                for record in self:
                    # 1. Obtener la fecha actual del registro
                    old_date = record.name

                    # 2. Realizar la validación
                    # Si la nueva fecha es anterior a la fecha original del registro, se rechaza
                    if old_date and new_date < old_date:
                        raise UserError(
                            "❌ ¡Modificación de Tasa Rechazada! "
                            "No se puede cambiar la fecha de una tasa de cambio a una fecha anterior. "
                        )

            # 2. Validación de inverse_company_rate
            if 'inverse_company_rate' in vals:
                raise UserError(
                    "❌ ¡Modificación de Tasa Rechazada! "
                    "El campo 'Tasa Inversa' no puede ser modificado manualmente. Es un campo calculado."
                )

        # 3. Si pasa la validación (o si el campo 'name' no se modificó), se realiza la escritura
        return super().write(vals)

    def _fetch_bcv_rates(self):
        """Obtiene y parsea las tasas publicadas en el portal del BCV."""
        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; Odoo-BCV-RateUpdater/1.0)",
        }
        try:
            response = requests.get(
                self.BCV_URL,
                headers=headers,
                verify=False,
                timeout=self.BCV_REQUEST_TIMEOUT,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            _logger.warning("BCV rate update: error al consultar %s: %s", self.BCV_URL, exc)
            return {}

        html = BeautifulSoup(response.text, "html.parser")
        parsed_rates = {}
        for currency_code, element_id in self.BCV_CURRENCY_MAP.items():
            container = html.find('div', {'id': element_id})
            strong = container.find('strong') if container else None
            if not strong:
                _logger.warning(
                    "BCV rate update: no se encontró el contenedor '%s' para %s",
                    element_id,
                    currency_code,
                )
                continue
            raw_value = strong.text.strip()
            try:
                rate_value = float(raw_value.replace('.', '').replace(',', '.'))
            except ValueError:
                _logger.warning(
                    "BCV rate update: valor inválido '%s' para %s",
                    raw_value,
                    currency_code,
                )
                continue
            if rate_value > 0:
                parsed_rates[currency_code] = rate_value
        return parsed_rates

    def _upsert_bcv_rates(self, rates_by_date):
        """Crea o actualiza tasas BCV por fecha para todas las compañías VES y monedas activas."""
        if not rates_by_date:
            return 0

        all_codes = set()
        for day_rates in rates_by_date.values():
            all_codes.update(day_rates.keys())

        active_currencies = self.env['res.currency'].sudo().search([
            ('name', 'in', list(all_codes)),
            ('active', '=', True),
        ])
        if not active_currencies:
            _logger.info("BCV rate update: no hay monedas activas coincidentes con el BCV.")
            return 0

        ves_companies = self.env['res.company'].sudo().search([
            ('currency_id.name', '=', 'VES'),
        ])
        if not ves_companies:
            _logger.info("BCV rate update: no hay compañías con moneda base VES.")
            return 0

        rate_env = self.sudo().with_context(bcv_auto_update=True)
        total_changes = 0

        for company in ves_companies:
            company_rate_env = rate_env.with_company(company)
            company_updated = False

            for rate_date in sorted(rates_by_date.keys()):
                day_rates = rates_by_date[rate_date]
                for currency in active_currencies:
                    bcv_value = day_rates.get(currency.name)
                    if not bcv_value or bcv_value <= 0:
                        continue

                    existing = company_rate_env.search([
                        ('currency_id', '=', currency.id),
                        ('name', '=', rate_date),
                        ('company_id', '=', company.id),
                    ], limit=1)
                    if not existing:
                        existing = company_rate_env.search([
                            ('currency_id', '=', currency.id),
                            ('name', '=', rate_date),
                            ('company_id', '=', False),
                        ], limit=1)

                    if existing:
                        needs_update = (
                            existing.company_id != company
                            or abs(existing.inverse_company_rate - bcv_value) > 1e-6
                        )
                        if needs_update:
                            existing.write({
                                'company_id': company.id,
                                'inverse_company_rate': bcv_value,
                            })
                            company_updated = True
                            total_changes += 1
                            _logger.info(
                                "BCV rate update: actualizada %s (%s) para %s = %.6f",
                                currency.name,
                                rate_date,
                                company.name,
                                bcv_value,
                            )
                    else:
                        company_rate_env.create([{
                            'name': rate_date,
                            'currency_id': currency.id,
                            'company_id': company.id,
                            'inverse_company_rate': bcv_value,
                        }])
                        company_updated = True
                        total_changes += 1
                        _logger.info(
                            "BCV rate update: creada %s (%s) para %s = %.6f",
                            currency.name,
                            rate_date,
                            company.name,
                            bcv_value,
                        )

            if company_updated:
                self.with_company(company).funcion_actualiza_coste_precio_venta()

        return total_changes

    def central_bank(self):
        parsed_rates = self._fetch_bcv_rates()
        if not parsed_rates:
            _logger.warning("BCV rate update: no se pudieron obtener tasas válidas del BCV.")
            return False

        rate_date = datetime.now(timezone('America/Caracas')).date()
        changes = self._upsert_bcv_rates({rate_date: parsed_rates})
        if not changes:
            _logger.info(
                "BCV rate update: las tasas del %s ya estaban actualizadas.",
                rate_date,
            )
        return True

    def _bcv_quarter_xls_urls(self, date_from, date_to):
        """Devuelve las URLs trimestrales oficiales del BCV que cubren [date_from, date_to]."""
        quarter_letters = {1: 'a', 2: 'b', 3: 'c', 4: 'd'}
        urls = []
        seen = set()
        year = date_from.year
        month = date_from.month
        while (year, month) <= (date_to.year, date_to.month):
            quarter_idx = ((month - 1) // 3) + 1
            key = (year, quarter_idx)
            if key not in seen:
                seen.add(key)
                urls.append(
                    self.BCV_HISTORY_XLS_TEMPLATE.format(
                        quarter=quarter_letters[quarter_idx],
                        year_short=str(year)[-2:],
                    )
                )
            month += 1
            if month > 12:
                month = 1
                year += 1
        return urls

    @staticmethod
    def _parse_bcv_xls_bytes(xls_bytes):
        """Parsea un archivo XLS oficial del BCV y devuelve {fecha_valor: {ISO: tasa_bs}}."""
        if xlrd is None:
            raise UserError(_("La librería 'xlrd' no está instalada para leer el histórico del BCV."))

        workbook = xlrd.open_workbook(file_contents=xls_bytes)
        rates_by_date = {}
        fecha_pattern = re.compile(r"Fecha\s+Valor\s*:\s*(\d{2}/\d{2}/\d{4})", re.IGNORECASE)

        for sheet in workbook.sheets():
            fecha_valor = None
            day_rates = {}
            for row_idx in range(sheet.nrows):
                row_values = [sheet.cell_value(row_idx, col_idx) for col_idx in range(sheet.ncols)]
                if fecha_valor is None:
                    for val in row_values:
                        match = fecha_pattern.search(str(val))
                        if match:
                            fecha_valor = datetime.strptime(match.group(1), "%d/%m/%Y").date()
                            break
                if len(row_values) > 6:
                    code = str(row_values[1]).strip().upper()
                    if len(code) == 3 and code.isalpha():
                        try:
                            ask_bs = float(row_values[6])
                        except (TypeError, ValueError):
                            ask_bs = 0.0
                        if ask_bs > 0:
                            day_rates[code] = ask_bs
            if fecha_valor and day_rates:
                rates_by_date[fecha_valor] = day_rates

        return rates_by_date

    def sync_bcv_history(self, date_from=None, date_to=None):
        """Sincroniza tasas históricas oficiales del BCV desde date_from hasta date_to."""
        today_ve = datetime.now(timezone('America/Caracas')).date()
        start_date = (
            fields.Date.from_string(date_from)
            if isinstance(date_from, str)
            else (date_from or today_ve.replace(day=1))
        )
        end_date = (
            fields.Date.from_string(date_to)
            if isinstance(date_to, str)
            else (date_to or today_ve)
        )
        if start_date > end_date:
            raise UserError(_("La fecha inicial no puede ser mayor que la fecha final."))

        headers = {"User-Agent": "Mozilla/5.0 (compatible; Odoo-BCV-RateUpdater/1.0)"}
        all_published = {}
        for url in self._bcv_quarter_xls_urls(start_date, end_date):
            try:
                response = requests.get(
                    url,
                    headers=headers,
                    verify=False,
                    timeout=self.BCV_REQUEST_TIMEOUT,
                )
                response.raise_for_status()
            except requests.RequestException as exc:
                _logger.warning("BCV history sync: error al descargar %s: %s", url, exc)
                continue
            all_published.update(self._parse_bcv_xls_bytes(response.content))

        if not all_published:
            _logger.warning("BCV history sync: no se encontraron datos en los archivos del BCV.")
            return 0

        filtered = {
            d: rates for d, rates in all_published.items() if start_date <= d <= end_date
        }
        # Si date_from cae en fin de semana o feriado, sembrar con la última tasa publicada anterior
        if start_date not in filtered:
            prior_dates = [d for d in all_published if d < start_date]
            if prior_dates:
                filtered[start_date] = all_published[max(prior_dates)]

        return self._upsert_bcv_rates(filtered)

    def funcion_actualiza_coste_precio_venta(self):
        lista2 = self.env['product.product'].search([])
        if lista2:
            for item in lista2:
                item.actualiza_coste()
                item.actualiza_precio_venta_bs()

        lista = self.env['product.template'].search([])
        if lista:
            for rec in lista:
                rec.actualiza_coste()
                rec.actualiza_precio_venta_bs()