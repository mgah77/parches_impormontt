from lxml.builder import E
from markupsafe import Markup

from odoo import api, models, tools, _


class BaseModel(models.AbstractModel):
    _inherit = 'base'

    def _notify_get_reply_to(self, default=None):
        _records = self
        model = _records._name if _records and _records._name != 'mail.thread' else False
        res_ids = _records.ids if _records and model else []
        _res_ids = res_ids or [False]  # default value

        alias_domain = self.env['ir.config_parameter'].sudo().get_param("mail.catchall.domain")
        result = dict.fromkeys(_res_ids, False)
        result_email = dict()
        doc_names = dict()

        if alias_domain and model and res_ids:
            if not doc_names:
                doc_names = dict((rec.id, rec.display_name) for rec in _records)

            # 1. Buscar alias específicos
            mail_aliases = self.env['mail.alias'].sudo().search([
                ('alias_parent_model_id.model', '=', model),
                ('alias_parent_thread_id', 'in', res_ids),
                ('alias_name', '!=', False)])
            for alias in mail_aliases:
                result_email.setdefault(alias.alias_parent_thread_id, '%s@%s' % (alias.alias_name, alias_domain))

        # 2. Usar team_id o user_id antes del catchall
        left_ids = set(_res_ids) - set(result_email)
        for record in self:
            if record.id in left_ids:
                email = False
                if hasattr(record, 'team_id') and record.team_id and record.team_id.mail_team:
                    email = record.team_id.mail_team
                elif hasattr(record, 'user_id') and record.user_id and record.user_id.email:
                    email = record.user_id.email

                if email:
                    result_email[record.id] = email

        # 3. Asignar catchall solo a los que no tienen nada aún
        left_ids = set(_res_ids) - set(result_email)
        if alias_domain and left_ids:
            catchall = self.env['ir.config_parameter'].sudo().get_param("mail.catchall.alias")
            if catchall:
                for rid in left_ids:
                    result_email[rid] = '%s@%s' % (catchall, alias_domain)

        # 4. Formatear todos los correos
        for res_id in result_email:
            result[res_id] = self._notify_get_reply_to_formatted_email(
                result_email[res_id],
                doc_names.get(res_id) or '',
            )

        # 5. Finalmente, usar el valor por defecto si aún quedan sin asignar
        left_ids = set(_res_ids) - set(result)
        if left_ids:
            result.update(dict((res_id, default) for res_id in left_ids))

        return result
