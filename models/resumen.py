from odoo import models, fields, api

class Resumen(models.Model):
    
    _inherit = 'account.move'

    lineas_por_pagar = fields.Integer(compute='_compute_lineas_por_pagar', store=False)

    @api.depends('payment_state', 'move_type')
    def _compute_lineas_por_pagar(self):
        for record in self:
            por_pagar_count = self.search_count([
                ('payment_state', '=', 'not_paid'),
                ('move_type', '=', 'in_invoice')
            ])
            record.lineas_por_pagar = por_pagar_count