# -*- coding: utf-8 -*-

import logging
from odoo import api, models

_logger = logging.getLogger(__name__)


class IrAttachmentInherit(models.Model):
    _inherit = 'ir.attachment'

    @api.model_create_multi
    def create(self, vals_list):
        new_vals_list = []
        
        for vals in vals_list:
            # Usar 'datas' en lugar de 'raw'
            if 'datas' in vals and vals['datas']:
                # Verificar si es XML (puede ser base64 o bytes)
                data = vals['datas']
                
                # Si está en base64, decodificar temporalmente
                if isinstance(data, str):
                    try:
                        import base64
                        decoded = base64.b64decode(data)
                        if b'<?xml' in decoded and b'standalone="no"' in decoded:
                            # Reemplazar standalone="no"
                            modified = decoded.replace(b' standalone="no"', b'')
                            # Volver a codificar a base64
                            vals['datas'] = base64.b64encode(modified)
                            _logger.info("Bytes 'standalone' eliminados en attachment: %s", 
                                        vals.get('name'))
                    except Exception:
                        pass
                
                # Sincronizar con db_datas si existe
                if 'db_datas' in vals:
                    vals['db_datas'] = vals['datas']
            
            new_vals_list.append(vals)
        
        return super(IrAttachmentInherit, self).create(new_vals_list)