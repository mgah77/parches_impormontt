from odoo import models, fields, api, _

class AccountPaymentRegisterCustom(models.TransientModel):
    _inherit = 'account.payment.register'

    amount_total = fields.Monetary(currency_field='currency_id', store=True, readonly=False)

    @api.depends('line_ids')
    def _compute_amount(self):
        for wizard in self:
            move = None
            if wizard.env.context.get('active_model') == 'account.move':
                move_ids = wizard.env.context.get('active_ids')
                if move_ids:
                    move = wizard.env['account.move'].browse(move_ids[0])
            elif wizard.line_ids:
                move = wizard.line_ids[0].move_id

            wizard.amount = abs(move.amount_residual) if move else 0.0
            wizard.amount_total = abs(move.amount_total) if move else 0.0 
            wizard.write({'amount_total': move.amount_total})

    
    @api.depends('can_edit_wizard', 'amount')
    def _compute_payment_difference(self):
        for wizard in self:
            move = None
            if wizard.env.context.get('active_model') == 'account.move':
                move_ids = wizard.env.context.get('active_ids')
                if move_ids:
                    move = wizard.env['account.move'].browse(move_ids[0])
            elif wizard.line_ids:
                move = wizard.line_ids[0].move_id

            if move:
                expected = abs(move.amount_residual)
                wizard.payment_difference = expected - wizard.amount
            else:
                wizard.payment_difference = 0.0


        # 🔧 Escritura SQL DESPUÉS de que todo Odoo haya terminado sus cálculos
    def action_create_payments(self):
        payments = self._create_payments()

        # ⏬ Forzar valores al final del proceso

        for wizard in self:
            if wizard.env.context.get('active_model') == 'account.move':
                move_ids = wizard.env.context.get('active_ids', [])                
                pagado = wizard.amount

                for move_id in move_ids:
                    move = wizard.env['account.move'].browse(move_id)
                    total = move.amount_residual
                    nuevo_residual = int(round(total - pagado))
                    estado = 'paid' if nuevo_residual == 0 else 'partial'

                    # Actualizar el encabezado de factura
                    wizard.env.cr.execute("""
                        UPDATE account_move
                        SET amount_residual = %s,
                            payment_state = %s
                        WHERE id = %s
                    """, (nuevo_residual, estado, move_id))

                    # Solo si se paga completamente, marcar líneas como conciliadas
                    if nuevo_residual == 0:
                        wizard.env.cr.execute("""
                            UPDATE account_move_line
                            SET amount_residual = 0,
                                amount_residual_currency = 0,
                                reconciled = true
                            WHERE move_id = %s
                            AND display_type = 'payment_term'
                            AND account_id IN (
                                SELECT id FROM account_account WHERE reconcile = true
                            )
                        """, (move_id,))

        if self._context.get('dont_redirect_to_payments'):
            return True

        # Redirección estándar
        action = {
            'name': _('Payments'),
            'type': 'ir.actions.act_window',
            'res_model': 'account.payment',
            'context': {'create': False},
        }
        if len(payments) == 1:
            action.update({
                'view_mode': 'form',
                'res_id': payments.id,
            })
        else:
            action.update({
                'view_mode': 'tree,form',
                'domain': [('id', 'in', payments.ids)],
            })
        return action
