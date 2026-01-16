# -*- coding: utf-8 -*-
from odoo import api, fields, models

class PriceCheckWizard(models.TransientModel):
    _name = "price.check.wizard"
    _description = "Consulta de Precios"

    search_text = fields.Char(string="Buscar producto")

    result_ids = fields.One2many(
        "price.check.wizard.line", "wizard_id", string="Resultados"
    )

    @api.onchange("search_text")
    def _onchange_search_text(self):
        """Busca productos cuando se escribe y se confirma (Enter)."""
        if not self.search_text:
            self.result_ids = [(5, 0, 0)]
            return

        domain = [
            ("sale_ok", "=", True),
            "|",
            ("name", "ilike", self.search_text),
            ("default_code", "ilike", self.search_text),
        ]
        products = self.env["product.product"].search(domain, limit=50)

        lines = []
        for prod in products:
            neto = prod.product_tmpl_id.list_price
            lines.append((0, 0, {
                "product_id": prod.id,
                "price_net": neto,
                "price_gross": neto * 1.19,
            }))

        self.result_ids = [(5, 0, 0)] + lines


class PriceCheckWizardLine(models.TransientModel):
    _name = "price.check.wizard.line"
    _description = "Resultados de Consulta de Precios"

    wizard_id = fields.Many2one("price.check.wizard", ondelete="cascade")
    product_id = fields.Many2one("product.product", string="Producto", readonly=True)
    price_net = fields.Float(string="Precio Neto", readonly=True, digits=(16, 0))
    price_gross = fields.Float(string="Precio + IVA (19%)", readonly=True, digits=(16, 0))
