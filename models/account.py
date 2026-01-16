from odoo import models, fields, api ,_

class AccountMove(models.Model):
    _inherit = 'account.move'

    glosa = fields.Char(string="Glosa")
