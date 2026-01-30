# -*- coding: utf-8 -*-

import logging
from lxml import etree
from odoo import models, api, _
import sys

# Asegúrate de que tu módulo pueda importar esto si es una dependencia externa
# Si no está instalado como paquete Python del sistema, es posible que necesites ajustar el path
try:
    from facturacion_electronica import facturacion_electronica as fe
except ImportError:
    _logger = logging.getLogger(__name__)
    _logger.warning("No se pudo importar facturacion_electronica como fe. El módulo puede no funcionar.")

_logger = logging.getLogger(__name__)


class SIIUploadXMLWizardInherit(models.TransientModel):
    _inherit = "sii.dte.upload_xml.wizard"

    def do_receipt_deliver(self):
        # --- INICIO DEL MÉTODO HEREDADO Y MODIFICADO ---
        self.ensure_one()
        
        # 1. Leer el XML
        envio = self._read_xml("etree")
        if envio.find("SetDTE") is None or envio.find("SetDTE/Caratula") is None:
            return True
        
        # 2. Obtener el RUT del Receptor desde el XML
        rut_node = envio.find("SetDTE/Caratula/RutReceptor")
        if rut_node is None or not rut_node.text:
            return True
            
        rut_xml = rut_node.text
        
        # --- BLOQUE DE BÚSQUEDA INTELIGENTE (FIX) ---
        # Normalizamos el RUT quitando puntos, guiones y CL para dejar solo el número limpio
        rut_clean = rut_xml.replace(".", "").replace("-", "").replace("CL", "").upper().strip()
        
        if len(rut_clean) >= 9:
            # Separamos el número del dígito verificador
            rut_num = rut_clean[:-1]
            rut_dv = rut_clean[-1]
            
            # Generamos los posibles formatos en los que podría estar guardado en la BD
            vat_candidates = [
                "CL" + rut_num + "-" + rut_dv,  # CL77334434-4 (Estándar Odoo l10n_cl)
                rut_num + "-" + rut_dv,         # 77334434-4 (Formato común)
                "CL" + rut_clean,               # CL77334434 (Formato de tu función format_rut)
                rut_clean                       # 77334434 (Solo números)
            ]

            company_id = False
            for vat in vat_candidates:
                company_id = self.env["res.company"].search([("vat", "=", vat)], limit=1)
                if company_id:
                    _logger.info("Compañía encontrada usando formato: %s -> %s", vat, company_id.name)
                    break
            
            # Si con coincidencia exacta no funcionó, intentamos búsqueda parcial (LIKE) como último recurso
            # Esto ayuda si hay formatos con puntos (ej: 77.334.434-4)
            if not company_id:
                company_id = self.env["res.company"].search([("vat", "like", rut_clean)], limit=1)
                if company_id:
                    _logger.warning("Compañía encontrada por búsqueda parcial (LIKE). VAT en BD: %s", company_id.vat)
        else:
            company_id = False
        --- FIN BLOQUE DE BÚSQUEDA INTELIGENTE ---

        # Si no encontramos compañía, salimos (aqui es donde antes daba False)
        if not company_id:
            _logger.warning("No se pudo encontrar compañía para el RUT: %s", rut_xml)
            return True

        # --- CONTINUACIÓN DEL CÓDIGO ORIGINAL ---
        # Ahora que tenemos company_id, el resto del flujo es igual
        
        # Obtener ID de respuesta
        IdRespuesta = self.env.ref("l10n_cl_fe.response_sequence").next_by_id()
        
        # Obtener datos de empresa y firma (Ahora usará la compañía correcta)
        vals = self._get_datos_empresa(company_id)
        vals.update(
            {
                "Recepciones": [
                    {
                        "IdRespuesta": IdRespuesta,
                        "RutResponde": company_id.partner_id.rut(),
                        "NmbContacto": self.env.user.partner_id.name,
                        "FonoContacto": self.env.user.partner_id.phone,
                        "MailContacto": self.env.user.partner_id.email,
                        "xml_nombre": self._get_xml_name(),
                        "xml_envio": self._get_xml(),
                    }
                ]
            }
        )
        
        # Generar la respuesta usando la librería externa
        respuesta = fe.recepcion_xml(vals)
        
        # Manejo de errores
        if type(respuesta) is dict:
            if self.dte_id:
                self.dte_id.message_post(body=respuesta['error'])
            else:
                from odoo.exceptions import UserError
                raise UserError(respuesta['error'])
                
        # Si todo está bien, procesar las respuestas y enviar correos
        if self.dte_id:
            for r in respuesta:
                att = self._create_attachment(r["respuesta_xml"], r["nombre_xml"], self.dte_id.id, "mail.message.dte")
                dte_email_id = self.dte_id.company_id.dte_email_id or self.env.user.company_id.dte_email_id
                email_to = self.sudo().dte_id.mail_id.email_from
                
                if envio is not None:
                    RUT = envio.find("SetDTE/Caratula/RutEmisor").text
                    partner_id = self.env["res.partner"].search(
                        [("active", "=", True), ("parent_id", "=", False), ("vat", "=", self.format_rut(RUT))]
                    )
                    if partner_id.dte_email:
                        email_to = partner_id.dte_email
                
                values = {
                    "res_id": self.dte_id.id,
                    "email_from": dte_email_id.name_get()[0][1],
                    "email_to": email_to,
                    "auto_delete": False,
                    "model": "mail.message.dte",
                    "body": "XML de Respuesta Envío, Estado: %s , Glosa: %s "
                    % (r["EstadoRecepEnv"], r["RecepEnvGlosa"]),
                    "subject": "XML de Respuesta Envío",
                    "attachment_ids": [[6, 0, att.ids]],
                }
                send_mail = self.env["mail.mail"].sudo().create(values)
                send_mail.send()