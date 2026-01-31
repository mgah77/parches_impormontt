# -*- coding: utf-8 -*-

import re
import logging
from base64 import b64decode
from lxml import etree
from odoo import models

_logger = logging.getLogger(__name__)


class MailMessageInherit(models.Model):
    _inherit = "mail.message"

    def _parse_xml(self, string_xml):
        try:
            string_xml = b64decode(string_xml).decode("ISO-8859-1")
        except Exception as e:
            _logger.warning("Error decoding string_xml: %s", e)
            return False

        # --- FIX PARA XML CON standalone="no" ---
        # Usamos regex para eliminar CUALQUIER declaración XML (<?xml ...?>)
        # Esto soluciona: Unicode strings with encoding declaration are not supported
        string_xml = re.sub(r'<\?xml[^>]*\?>', '', string_xml)
        # -------------------------------------------

        # Mantenemos el resto de la lógica de limpieza original
        xml = string_xml.replace('<DscItem />', "")
        xml = xml.replace(' xmlns="http://www.sii.cl/SiiDte"', "")
        parser = etree.XMLParser(remove_blank_text=True)
        return etree.fromstring(xml, parser=parser)