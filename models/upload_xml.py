    def do_create_inv(self):
        created = []
        dtes = self._get_dtes()
        for dte in dtes:
            try:
                # Aseguramos que procesamos como factura, no PO, para ejecutar el bloque de totales
                self.crear_po = False 
                
                to_post = self.type == "ventas" or self.option == "accept"
                company_id = self.document_id.company_id
                documento = dte.find("Documento")
                path_rut = "Encabezado/Receptor/RUTRecep"
                if self.type == "ventas":
                    path_rut = "Encabezado/Emisor/RUTEmisor"
                rut = documento.find(path_rut).text
                
                # --- BÚSQUEDA INTELIGENTE ---
                company_id = self._search_company_smart(rut)
                # ---------------------------------

                if not company_id:
                    raise UserError(_(f"No existe compañia para el rut {rut}"))
                
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
                    
                # --- Lógica de Totales y SQL ---
                encabezado = documento.find("Encabezado")
                if encabezado is None:
                    _logger.warning("Encabezado no encontrado en el XML. No se actualizaron totales.")
                    continue

                totales = encabezado.find("Totales")
                if totales is None:
                    _logger.warning("Totales no encontrado en el XML. No se actualizaron totales.")
                    continue

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
                
                _logger.info("Actualizando Totales SQL - Neto: %s, IVA: %s, Total: %s", neto_total, iva, mnt_total)

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

                lines = data.get("invoice_line_ids", [])
                for i, line in enumerate(inv.invoice_line_ids.filtered(lambda l: not l.display_type and not l.tax_line_id)):
                    if i < len(lines):
                        subtotal = lines[i][2].get("price_subtotal")
                        if subtotal is not None:
                            self.env.cr.execute("""
                                UPDATE account_move_line
                                SET price_subtotal = %s 
                                WHERE id = %s
                            """, (subtotal, line.id))

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