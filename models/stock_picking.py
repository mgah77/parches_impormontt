from odoo import api, fields, models

class stock_picking_custom_kanban(models.Model):
    _inherit = 'stock.picking.type'

    user_warehouse = fields.Integer('Current User', compute="_compute_user")

    def _compute_user(self):
        for record in self:
            record['user_warehouse']=self.env.user.property_warehouse_id
            return


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    user_stock_location_id = fields.Many2one(
        'stock.location',
        compute='_compute_user_stock_location',
        store=False
    )


    @api.depends('picking_type_id')
    def _compute_user_stock_location(self):
        for record in self:
            warehouse = self.env.user.property_warehouse_id
            if warehouse:
                record.user_stock_location_id = warehouse.lot_stock_id
            else:
                record.user_stock_location_id = False
    
    @api.model
    def _get_warehouse_from_location(self, location):
        # Busca el warehouse donde la ubicación de stock principal coincide
        return self.env['stock.warehouse'].search([
            ('lot_stock_id', '=', location.id)
        ], limit=1)

    def button_validate(self):
        # Procesamos solo transferencias internas
        internos = self.filtered(lambda p: p.picking_type_id.code == 'internal')
        otros = self - internos

        for picking in internos:

            origen = picking.location_id
            destino_logico = picking.location_dest_id
            lineas = picking.move_ids_without_package

            # Encontrar bodega destino desde location_dest_id
            wh_dest = self._get_warehouse_from_location(destino_logico)
            if not wh_dest:
                raise Exception("No se pudo determinar la bodega destino desde la ubicación destino.")

            # Buscar tipo Recepciones de esa bodega
            tipo_recep = self.env['stock.picking.type'].search([
                ('code', '=', 'incoming'),
                ('name', '=', 'Recepciones'),
                ('warehouse_id', '=', wh_dest.id),
            ], limit=1)

            if not tipo_recep:
                raise Exception("No existe tipo de operación 'Recepciones' para la bodega destino.")

            # ubicación origen de la recepción (debe ser proveedores)
            ubicacion_proveedor = self.env.ref('stock.stock_location_suppliers')

            # crear la recepción en estado confirmado
            recepcion = self.env['stock.picking'].create({
                'picking_type_id': tipo_recep.id,
                'location_id': ubicacion_proveedor.id,   # origen de la recepción
                'location_dest_id': tipo_recep.default_location_dest_id.id,
                'state': 'confirmed',
                'origin': picking.name,
                'company_id': picking.company_id.id,
                'partner_id': picking.partner_id.id,
            })

            # crear las líneas de la recepción con cantidad y quantity_done
            for mov in lineas:
                self.env['stock.move'].create({
                    'picking_id': recepcion.id,
                    'product_id': mov.product_id.id,
                    'name': mov.name,
                    'product_uom': mov.product_uom.id,
                    'product_uom_qty': mov.product_uom_qty,
                    'quantity_done': mov.product_uom_qty,
                    'location_id': ubicacion_proveedor.id,              # origen
                    'location_dest_id': tipo_recep.default_location_dest_id.id,  # destino
                    'company_id': picking.company_id.id,
                    'state': 'confirmed',
                })

            # Rebaja manual de stock en origen
            Quant = self.env['stock.quant']
            for mov in lineas:
                quant = Quant.search([
                    ('product_id', '=', mov.product_id.id),
                    ('location_id', '=', origen.id),
                    ('company_id', '=', picking.company_id.id),
                ], limit=1)

                if quant:
                    quant.quantity -= mov.product_uom_qty
                else:
                    Quant.create({
                        'product_id': mov.product_id.id,
                        'location_id': origen.id,
                        'quantity': -mov.product_uom_qty,
                        'company_id': picking.company_id.id,
                    })
            # Cancelar movimientos internos para permitir borrado
            (picking.move_ids_without_package | picking.move_ids).write({'state': 'cancel'})

            # NO los borres, solo déjalos cancelados

            # marcar el picking interno como realizado
            picking.state = 'done'

        # Validación normal para los pickings que no son internos
        if otros:
            return super(StockPicking, otros).button_validate()

        return True

    #partner_id se llena automáticamente con company_id.partner_id

    @api.onchange('picking_type_id')
    def _onchange_picking_type_set_partner(self):
        if self.picking_type_id and self.picking_type_id.code == 'internal':
            self.partner_id = self.company_id.partner_id.id