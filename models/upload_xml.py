# -*- coding: utf-8 -*-

import logging
from lxml import etree
from odoo import models, api, _

try:
    from facturacion_electronica import facturacion_electronica as fe
except ImportError:
    _logger = logging.getLogger(__name__)
    _logger.warning("No se pudo importar facturacion_electronica como fe.")

_logger = logging.getLogger(__name__)


class SIIUploadXMLWizardInherit(models.TransientModel):
    _inherit = "sii.dte.upload_xml.wizard"

    def _search_company_smart(self, rut_xml):
        """
        Busca una compañía en res.company probando diferentes formatos de RUT.
        Retorna el recordset de la compañía o False.
        """
        # Normalizar RUT del XML
        rut_clean = rut_xml.replace(".", "").replace("-", "").replace("CL", "").upper().strip()
        company_id = False

        if len(rut_clean) >= 9:
            rut_num = rut_clean[:-1]
            rut_dv = rut_clean[-1]
            
            # Candidatos de formato
            vat_candidates = [
                "CL" + rut_num + "-" + rut_dv,
                rut_num + "-" + rut_dv,
                "CL" + rut_clean,
                rut_clean
            ]

            # Búsqueda exacta
            for vat in vat_candidates:
                company_id = self.env["res.company"].search([("vat", "=", vat)], limit=1)
                if company_id:
                    _logger.info("Compañía encontrada para %s usando formato: %s", rut_xml, vat)
                    break
            
            # Búsqueda parcial (LIKE) como último recurso
            if not company_id:
                company_id = self.env["res.company"].search([("vat", "like", rut_clean)], limit=1)
                if company_id:
                    _logger.warning("Compañía encontrada por búsqueda parcial (LIKE) para %s. VAT BD: %s", rut_xml, company_id.vat)
        
        if not company_id:
            _logger.warning("No se pudo encontrar compañía para el RUT: %s", rut_xml)
            
        return company_id

    def do_receipt_deliver(self):
        self.ensure_one()
        
        envio = self._read_xml("etree")
        if envio.find("SetDTE") is None or envio.find("SetDTE/Caratula") is None:
            return True
        
        rut_node = envio.find("SetDTE/Caratula/RutReceptor")
        if rut_node is None or not rut_node.text:
            return True
            
        rut_xml = rut_node.text
        
        # USAR MÉTODO DE BÚSQUEDA INTELIGENTE
        company_id = self._search_company_smart(rut_xml)
        
        if not company_id:
            return True

        IdRespuesta = self.env.ref("l10n_cl_fe.response_sequence").next_by_id()
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
        respuesta = fe.recepcion_xml(vals)
        if type(respuesta) is dict:
            if self.dte_id:
                self.dte_id.message_post(body=respuesta['error'])
            else:
                from odoo.exceptions import UserError
                raise UserError(respuesta['error'])
                
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

    def do_create_pre(self):
        # Heredado para usar búsqueda inteligente de compañía
        created = []
        self.do_receipt_deliver()
        dtes = self._get_dtes()
        for dte in dtes:
            try:
                documento = dte.find("Documento")
                
                # --- FIX: BÚSQUEDA INTELIGENTE ---
                rut_receptor = documento.find("Encabezado/Receptor/RUTRecep").text
                company_id = self._search_company_smart(rut_receptor)
                # ----------------------------------
                
                if not company_id:
                    _logger.warning("No existe compañia para %s", rut_receptor)
                    continue
                
                pre = self._create_pre(documento, company_id,)
                if pre:
                    inv = self._inv_exist(documento)
                    pre.write(
                        {"id_dte": documento.get("ID"), "move_id": inv.id,}
                    )
                    created.append(pre.id)
            except Exception as e:
                msg = "Error en 1 pre con error:  %s" % str(e)
                _logger.warning(msg, exc_info=True)
                if self.dte_id:
                    self.dte_id.message_post(body=msg)
        return created

    def do_create_inv(self):
        # Revertido a lógica original pero con búsqueda inteligente
        created = []
        dtes = self._get_dtes()
        for dte in dtes:
            try:
                to_post = self.type == "ventas" or self.option == "accept"
                company_id = self.document_id.company_id
                documento = dte.find("Documento")
                path_rut = "Encabezado/Receptor/RUTRecep"
                if self.type == "ventas":
                    path_rut = "Encabezado/Emisor/RUTEmisor"
                rut = documento.find(path_rut).text
                
                # --- FIX: BÚSQUEDA INTELIGENTE ---
                company_id = self._search_company_smart(rut)
                # ---------------------------------

                if not company_id:
                    raise UserError(_(f"No existe compañia para el rut {rut}"))
                
                # Se llama al original _get_data (que contiene la lógica de totales y SQL)
                data = self._get_data(documento, company_id)
                inv = self._create_inv(documento, company_id,)
                if self.document_id:
                    self.document_id.move_id = inv.id
                if inv:
                    created.append(inv.id)
                if not inv:
                    raise UserError(
                        "El archivo XML no contiene documentos para alguna empresa registrada en Odoo, o ya ha sido procesado anteriormente "
                    )
                if to_post and inv.state=="draft":
                    inv._onchange_partner_id()
                    inv._onchange_invoice_line_ids()
                    inv.with_context(
                        purchase_to_done=self.purchase_to_done.id,
                        check_move_validity=False,
                        recompute=False,
                    )._post()

            except Exception as e:
                msg = "Error en crear 1 factura con error:  %s" % str(e)
                _logger.warning(msg, exc_info=True)
                _logger.warning(etree.tostring(dte))
                if self.document_id:
                    self.document_id.message_post(body=msg)

        if created and self.option not in [False, "upload"] and self.type == "compras" and not self._context.get('create_only', False):
            datos = {
                "move_ids": [(6, 0, created)],
                "action": "ambas",
                "claim": "ACD",
                "estado_dte": "0",
                "tipo": "account.move",
            }
            wiz_accept = self.env["sii.dte.validar.wizard"].create(datos)
            wiz_accept.confirm()
        return created

    def do_create_po(self):
        created = []
        dtes = self._get_dtes()
        for dte in dtes:
            documento = dte.find("Documento")
            path_rut = "Encabezado/Receptor/RUTRecep"
            
            # --- FIX: BÚSQUEDA INTELIGENTE EN do_create_po ---
            rut = documento.find(path_rut).text
            company = self._search_company_smart(rut)
            # ----------------------------------------------

            if not company:
                _logger.warning("No se encontró compañía para el RUT %s en do_create_po. Saltando.", rut)
                continue

            path_tpo_doc = "Encabezado/IdDoc/TipoDTE"
            dc_id = self.env["sii.document_class"].search([("sii_code", "=", documento.find(path_tpo_doc).text)])
            if dc_id.es_factura() or dc_id.es_nd() or dc_id.es_guia() or dc_id.es_boleta_afecta():
                try:
                    po = self._create_po(documento, dc_id, company)
                    created.append(po.id)
                    if self.document_id:
                        self.document_id.purchase_to_done = po
                        self.document_id.auto_map_po_lines()
                except Exception as e:
                    msg = "Error en procesar PO: %s" % str(e)
                    _logger.warning(msg, exc_info=True)
                    if self.document_id:
                        self.document_id.message_post(body=msg)
                    continue
                if self.action == "both" and not dc_id.es_guia():
                    self.purchase_to_done = po
                    self.crear_po = False
        return created