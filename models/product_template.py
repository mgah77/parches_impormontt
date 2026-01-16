from odoo import models, fields, api

class ProductDepartment(models.Model):
    _inherit = 'product.template'  # Reemplaza 'your.model' por el nombre del modelo que deseas modificar


    margenes = fields.Float(string='Margen', compute='_compute_margenes')

    @api.depends('standard_price', 'list_price')
    def _compute_margenes(self):
        for product in self:
            if product.standard_price > 0 and product.list_price > 0:
                # Fórmula: ((Precio venta - Precio costo) / Precio costo) * 100
                product.margenes = ((product.list_price - product.standard_price) / product.standard_price)
            else:
                product.margenes = 0.0

    is_admin_user = fields.Boolean(string="list_price", compute="_compute_is_admin_user", store=False)

    @api.depends_context('uid')
    def _compute_is_admin_user(self):
        for rec in self:
            rec.is_admin_user = self.env.user.has_group('parches_impormontt.group_list_price')

