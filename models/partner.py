from odoo import models, fields, api

class res_partner_customer_provider(models.Model):
    _inherit = 'res.partner'

    is_customer = fields.Boolean(string ='Cliente',default=False)
    is_provider = fields.Boolean(string ='Proveedor',default=False)
    time_limit = fields.Integer(string='Tiempo para pago en dias')
    