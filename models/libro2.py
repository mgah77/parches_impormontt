from datetime import datetime

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models
from odoo.exceptions import UserError

class Librodos(models.Model):
    _name = "account.move.libro2"
    _description = "Libro de Compra / Venta DTE"

    name = fields.Char(string="Libro", required=True, readonly=True, default="Compra Venta")    
    detalles = fields.Char(default="Documentos")
    periodo_tributario = fields.Char(
        string="Periodo Tributario",
        required=True,
        default=lambda *a: datetime.now().strftime("%Y-%m"),
    )
    date = fields.Date(
        string="Fecha",
        required=True,
        readonly=True,
        default=lambda self: fields.Date.context_today(self),
    ) 
    company_id = fields.Many2one(
        "res.company",
        string="Compañía",
        required=True,
        default=lambda self: self.env.user.company_id.id,
        readonly=True,
    )
    currency_id = fields.Many2one(
        "res.currency",
        string="Moneda",
        default=lambda self: self.env.user.company_id.currency_id,
        required=True,
        track_visibility="always",
    )
    ventas_neto = fields.Monetary(string="Total Neto", readonly=True, )
    ventas_iva = fields.Monetary(string="Total IVA", readonly=True, )
    total_debito = fields.Monetary(string="Total Debito", readonly=True, )
    compras_neto = fields.Monetary(string="Total Neto", readonly=True, )
    compras_iva = fields.Monetary(string="IVA Recuperable", readonly=True, )
    total_compras = fields.Monetary(string="Total", readonly=True, )
    total_credito = fields.Monetary(string="Total Credito", readonly=True, )
    total_ventas = fields.Monetary(string="Total", readonly=True, )
    total_otros_imps = fields.Monetary(
        string="Total Otros Impuestos", readonly=True, )
    total = fields.Monetary(string="Total Otros Impuestos", readonly=True, )
    impuestos = fields.Many2many("account.invoice", readonly=True, string="Impuestos", )
    compras_ids = fields.Many2many("account.move", readonly=True, )
    ventas_ids = fields.Many2many("account.move", readonly=True, )

    @api.onchange("periodo_tributario")           
    def set_movimientos(self):
        if not self.periodo_tributario:
            return
        current = datetime.strptime(self.periodo_tributario + "-01", "%Y-%m-%d")
        next_month = current + relativedelta(months=1)    
        query_compra = [
            ("company_id", "=", self.company_id.id),
            ("date", "<", next_month.strftime("%Y-%m-%d")),
            ("date", ">=", current.strftime("%Y-%m-%d")),
            ("journal_id.type", "=", "purchase")
        ]
        self.compras_ids = self.env["account.move"].search(query_compra)    
        query_venta = [
            ("company_id", "=", self.company_id.id),
            ("date", "<", next_month.strftime("%Y-%m-%d")),
            ("date", ">=", current.strftime("%Y-%m-%d")),
            ("journal_id.type", "=", "sale")
        ]
        self.ventas_ids = self.env["account.move"].search(query_venta)  
        query_imp = [
            ("company_id", "=", self.company_id.id),
            ("date", "<", next_month.strftime("%Y-%m-%d")),
            ("date", ">=", current.strftime("%Y-%m-%d")),
            ("type", "=", "out_invoice")
        ]
        self.impuestos = self.env["account.invoice"].search(query_imp)
        neto = 0
        iva = 0
        venta = 0
        for line in self.impuestos:
            neto += line.amount_untaxed
            iva += line.amount_tax
            venta += line.amount_total
        query_compra_undo = [
            ("company_id", "=", self.company_id.id),
            ("date", "<", next_month.strftime("%Y-%m-%d")),
            ("date", ">=", current.strftime("%Y-%m-%d")),
            ("type", "=", "in_refund")
        ]  
        self.impuestos = self.env["account.invoice"].search(query_compra_undo)
        for line in self.impuestos:
            neto += line.amount_untaxed
            iva += line.amount_tax
            venta += line.amount_total  
        self.ventas_neto = neto
        self.ventas_iva = iva
        self.total_ventas = venta
        query_imp_compra = [
            ("company_id", "=", self.company_id.id),
            ("date", "<", next_month.strftime("%Y-%m-%d")),
            ("date", ">=", current.strftime("%Y-%m-%d")),
            ("type", "=", "in_invoice")
        ]
        self.impuestos = self.env["account.invoice"].search(query_imp_compra)
        neto = 0
        iva = 0
        venta = 0
        for line in self.impuestos:
            neto += line.amount_untaxed
            iva += line.amount_tax
            venta += line.amount_total
        query_venta_undo = [
            ("company_id", "=", self.company_id.id),
            ("date", "<", next_month.strftime("%Y-%m-%d")),
            ("date", ">=", current.strftime("%Y-%m-%d")),
            ("type", "=", "out_refund")
        ]  
        self.impuestos = self.env["account.invoice"].search(query_venta_undo)
        for line in self.impuestos:
            neto += line.amount_untaxed
            iva += line.amount_tax
            venta += line.amount_total  
        self.compras_neto = neto
        self.compras_iva = iva
        self.total_compras = venta

        

class ImpuestosLibrodos(models.Model):
    _name = "account.move.libro2.tax"
    _description = "línea de impuesto Libro CV"

    tax_id = fields.Many2one("account.tax", string="Impuesto")
    credit = fields.Monetary(string="Créditos", default=0.00)
    debit = fields.Monetary(string="Débitos", default=0.00)
    amount = fields.Monetary(string="Monto", default=0.00)
    currency_id = fields.Many2one(
        "res.currency",
        string="Moneda",
        default=lambda self: self.env.user.company_id.currency_id,
        required=True,
        track_visibility="always",
    )
    book_id = fields.Many2one("account.move.libro2", string="Libro")
