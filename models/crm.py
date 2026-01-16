from odoo import models, fields, api

class Crm_team_mail(models.Model):

    _inherit = 'crm.team'

    mail_team = fields.Char(string ="Team e-mail")