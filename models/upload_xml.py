# -*- coding: utf-8 -*-

import logging
from lxml import etree
from odoo import models, api, fields, _
from datetime import timedelta

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

    def _get_data(self, documento, company_id, ignore_journal=False):
        # 1. Ejecutar lógica original
        data = super(SIIUploadXMLWizardInherit, self)._get_data(documento, company_id, ignore_journal)
        
        # 2. Si ignore_journal es True (POs) o ya tiene journal, no hacer nada.
        if ignore_journal or data.get('journal_id'):
            return data
            
        # 3. Si no tiene journal (porque la compañía nueva no tiene), buscar uno genérico.
        _logger.warning("DEBUG: _get_data sin journal_id. Buscando fallback para compañía %s...", company_id.name)
        
        # Buscar Tipo de DTE en el XML
        encabezado = documento.find("Encabezado")
        IdDoc = encabezado.find("IdDoc") if encabezado is not None else None
        sii_code = IdDoc.find("TipoDTE").text if IdDoc is not None else False
        
        if sii_code:
            dc_id = self.env["sii.document_class"].search([("sii_code", "=", sii_code)])
            type = "purchase"
            # Buscar en cualquier compañía del usuario (FALLBACK GENÉRICO)
            query = [("company_id", "in", self.env.user.company_ids.ids)]
            if self.type == "ventas":
                type = "sale"
                query.append(("journal_document_class_ids.sii_document_class_id", "=", dc_id.id))
            else:
                query.append(("document_class_ids", "=", dc_id.id))
            query.append(("type", "=", type))
            
            journal_id = self.env["account.journal"].search(query, limit=1)
            
            if journal_id:
                _logger.warning("DEBUG: Encontrado diario genérico: %s. Asignando.", journal_id.name)
                data['journal_id'] = journal_id.id
            else:
                _logger.warning("DEBUG: NO se encontró diario ni siquiera genérico.")
        
        return data

    def do_create_inv(self):
        # Lógica modificada para crear la factura en dos pasos (Cabecera -> Líneas)
        # Y manejo de errores de publicación para dejar la factura en borrador si fallan validaciones de campos faltantes.
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
                
                # Obtenemos todos los datos (incluyendo líneas)
                data = self._get_data(documento, company_id)
                
                # --- NUEVA LÓGICA DE CREACIÓN EN DOS PASOS ---
                lines = data.get('invoice_line_ids', [])
                
                header_data = data.copy()
                header_data.pop('invoice_line_ids', None)
                header_data.pop('line_ids', None)
                
                inv = self.env["account.move"].create(header_data)
                
                if self.document_id:
                    self.document_id.move_id = inv.id
                if inv:
                    created.append(inv.id)
                
                # Agregar líneas
                if lines:
                    inv.write({'invoice_line_ids': lines})
                # ----------------------------------------------

                if not inv:
                    raise UserError(
                        "El archivo XML no contiene documentos para alguna empresa registrada en Odoo, o ya ha sido procesado anteriormente "
                    )
                
                # --- INTENTO DE PUBLICACIÓN CON MANEJO DE ERRORES ---
                try:
                    if to_post and inv.state=="draft":
                        inv._onchange_partner_id()
                        inv._onchange_invoice_line_ids()
                        inv.with_context(
                            purchase_to_done=self.purchase_to_done.id,
                            check_move_validity=False,
                            recompute=False,
                        )._post()
                except Exception as e:
                    # Si falla por falta de datos de contribuyente u otros validaciones de l10n_cl,
                    # dejamos la factura en borrador pero continuamos para actualizar totales.
                    if "tipo de contribuyente" in str(e) or "Tax payer type" in str(e):
                        _logger.warning("Fallo la publicación de la factura (Error de tipo de contribuyente). La factura se mantiene en borrador y se actualizarán totales. Error: %s", str(e))
                        # No hacemos 'raise', permitimos continuar al bloque SQL
                    else:
                        # Si es otro error (ej: balance), si lanzamos
                        raise
                # -------------------------------------------------------

                # --- BLOQUE SQL ORIGINAL PARA TOTALES ---
                # Este bloque se ejecutará tanto si se publicó bien como si falló el paso anterior (quedando en borrador)
                if not self.crear_po:
                    encabezado = documento.find("Encabezado")
                    if encabezado is None: continue
                    totales = encabezado.find("Totales")
                    if totales is None: continue

                    vlr_pagar = totales.find("VlrPagar")
                    if vlr_pagar is not None and vlr_pagar.text:
                        valor_vlrpagar = int(vlr_pagar.text or 0)
                        if valor_vlrpagar != 0:
                            mnt_total = valor_vlrpagar
                        else:
                            mnt_total = int(totales.find("MntTotal").text or 0)
                    else:
                        mnt_total = int(totales.find("MntTotal").text or 0)

                    mnt_neto = int(totales.find("MntNeto").text or 0) if totales.find("MntNeto") is not None else 0
                    mnt_exe = int(totales.find("MntExe").text or 0) if totales.find("MntExe") is not None else 0              
                    iva = int(totales.find("IVA").text or 0) if totales.find("IVA") is not None else 0
                    neto_total = mnt_neto + mnt_exe
                    signo = -1 if inv.move_type == 'in_invoice' else 1
                    total_signed = mnt_total * signo
                    untaxed_signed = (mnt_neto + mnt_exe) * signo
                    tax_signed = iva * signo
                    residual = mnt_total
                    residual_signed = total_signed
                    currency_total_signed = total_signed
                    if inv.currency_id != inv.company_id.currency_id:
                        currency_total_signed = inv.currency_id._convert(
                            mnt_total,
                            inv.currency_id,
                            inv.company_id,
                            inv.date or fields.Date.context_today(self)
                        ) * signo

                    _logger.warning("Actualizando Totales SQL - Neto: %s, IVA: %s, Total: %s", neto_total, iva, mnt_total)

                    self.env.cr.execute("""
                        UPDATE account_move
                        SET amount_untaxed = %s,
                            amount_tax = %s,
                            amount_total = %s,
                            amount_untaxed_signed = %s,
                            amount_tax_signed = %s,
                            amount_total_signed = %s,
                            amount_total_in_currency_signed = %s,
                            amount_residual = %s,
                            amount_residual_signed = %s
                        WHERE id = %s
                    """, (
                        neto_total,
                        iva,
                        mnt_total,
                        untaxed_signed,
                        tax_signed,
                        total_signed,
                        currency_total_signed,
                        residual,
                        residual_signed,
                        inv.id
                    ))

                    fch_emis = encabezado.find("IdDoc/FchEmis").text
                    fch_venc_node = encabezado.find("IdDoc/FchVenc")
                    if fch_venc_node is not None and fch_venc_node.text:
                        fecha_vencimiento = fch_venc_node.text
                    else:
                        fecha_emision = fields.Date.from_string(fch_emis)
                        fecha_vencimiento = fields.Date.to_string(fecha_emision + timedelta(days=30))

                    self.env.cr.execute("""
                        UPDATE account_move
                        SET invoice_date_due = %s
                        WHERE id = %s
                    """, (fecha_vencimiento, inv.id))

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
                raise UserError(_(f"No existe compañia para el rut {rut}"))

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