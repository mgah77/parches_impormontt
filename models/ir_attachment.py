# -*- coding: utf-8 -*-

import base64
from odoo import api, models

class IrAttachmentInherit(models.Model):
    _inherit = 'ir.attachment'

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if 'datas' in vals and vals['datas']:
                try:
                    # Decodificar base64 a bytes
                    data_bytes = base64.b64decode(vals['datas'])
                    
                    # Reemplazar EXACTAMENTE lo que pediste: standalone="no" (con esas comillas)
                    if b'standalone="no"' in data_bytes:
                        data_bytes = data_bytes.replace(b' standalone="no"', b'')
                        
                        # Codificar de nuevo a base64
                        vals['datas'] = base64.b64encode(data_bytes)
                        
                        # Si existe db_datas, actualizarlo también
                        if 'db_datas' in vals:
                            vals['db_datas'] = vals['datas']
                            
                except Exception:
                    # Si hay error, continuar sin modificar
                    continue
        
        return super().create(vals_list)