from odoo import models, fields, api ,_
from collections import defaultdict
from odoo.exceptions import UserError
from odoo.tools import (
    date_utils,
    email_re,
    email_split,
    float_compare,
    float_is_zero,
    float_repr,
    format_amount,
    format_date,
    formatLang,
    frozendict,
    get_lang,
    is_html_empty,
    sql
)

class AccountMove(models.Model):
    _inherit = 'account.move'

    glosa = fields.Char(string="Glosa")
    document_number = fields.Char(related='partner_id.document_number', string="RUT", store=False)

    @api.model
    def search(self, domain, offset=0, limit=None, order=None, count=False):
        # Agregar filtro por equipo del usuario
        user_team_id = self.env.user.team_id
        if user_team_id:
            domain = domain + [('team_id', '=', user_team_id.id)]
        # Si no tiene equipo, no filtrar (ver todo)
        return super().search(domain, offset=offset, limit=limit, order=order, count=count)


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    glosa = fields.Char(string="Glosa", index=True)

    @api.depends('product_id')
    def _compute_name(self):
        for line in self:
            if line.display_type == 'payment_term':
                if line.move_id.payment_reference:
                    line.name = line.move_id.payment_reference
                elif not line.name:
                    line.name = ''
                continue
            if not line.product_id or line.display_type in ('line_section', 'line_note'):
                continue
            if line.partner_id.lang:
                product = line.product_id.with_context(lang=line.partner_id.lang)
            else:
                product = line.product_id

            values = []
            # Eliminamos la línea que agrega product.partner_ref (código interno)
            if line.journal_id.type == 'sale':
                if product.description_sale:
                    values.append(product.description_sale)
            elif line.journal_id.type == 'purchase':
                if product.description_purchase:
                    values.append(product.description_purchase)
            # Si no hay descripción específica, usar el nombre del producto
            if not values:
                values.append(product.name)
            line.name = '\n'.join(values)

class AccountPayment(models.Model):
    _inherit = 'account.payment'

    serie_cheque = fields.Char(string="Serie del cheque")
    banco_cheque_id = fields.Many2one('res.bank', string="Banco del cheque")
    fecha_cobro = fields.Date(string="Fecha de cobro del cheque")
 
    partner_vat = fields.Char(string="RUT", related='partner_id.document_number', store=False)

    estado_cheque = fields.Selection([
        ('no_cobrado', 'No Cobrado'),
        ('cobrado', 'Cobrado'),
    ], string="Estado del Cheque", default='no_cobrado')

    factura_name = fields.Char(related='move_id.ref', string='Factura', store=False, readonly=True)

    def action_toggle_estado_cheque(self):
        for record in self:
            record.estado_cheque = 'cobrado' if record.estado_cheque == 'no_cobrado' else 'no_cobrado'    

    sucursal_nombre = fields.Char(string="Sucursal", compute="_compute_sucursal_nombre", store=False)

    def _compute_sucursal_nombre(self):
        for rec in self:
            team_id = rec.move_id.team_id.id if rec.move_id and rec.move_id.team_id else False
            if team_id == 1:
                rec.sucursal_nombre = "ParVial"
            elif team_id == 5:
                rec.sucursal_nombre = "Ñuble"
            else:
                rec.sucursal_nombre = ""

class AccountPaymentRegister(models.TransientModel):
    _inherit = 'account.payment.register'

    serie_cheque = fields.Char(string="Serie del cheque")
    banco_cheque_id = fields.Many2one('res.bank', string="Banco del cheque")
    fecha_cobro = fields.Date(string="Fecha de cobro del cheque")

    def _create_payments(self):
        """Crea los pagos y les pasa los datos del cheque."""
        payments = super()._create_payments()
        for wiz in self:
            payments.write({
                'serie_cheque': wiz.serie_cheque,
                'banco_cheque_id': wiz.banco_cheque_id.id if wiz.banco_cheque_id else False,
                'fecha_cobro': wiz.fecha_cobro,
            })
        return payments

class AccountPartialReconcile(models.Model):
    _inherit = 'account.partial.reconcile'

    def unlink(self):
            moves = (self.debit_move_id.move_id | self.credit_move_id.move_id)
            res = super().unlink()

            # Fuerza el estado "not_paid" en todas las facturas o notas asociadas
            for move in moves:
                if move.move_type in ('out_invoice', 'in_invoice', 'out_refund', 'in_refund'):
                    move.payment_state = 'not_paid'

            return res