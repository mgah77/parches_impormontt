# -*- coding: utf-8 -*-

{
    'name': 'Insumar_parches',
    'version': '4.01',
    'category': 'General',
    'summary': '',
    'description': """
    Parches Insumar

       """,
    'author' : 'M.Gah',
    'website': '',
    'depends': ['account'],
    'data': [
            "security/groups.xml",
            "views/configuration_menu.xml",
            "views/product_template.xml"
    ],
    'assets': {
        'web.report_assets_common': [
            'parches_insumar/static/src/css/styles_pdf_layout.css',
        ],
    },            
    'installable': True,
    'auto_install': False,
    'application': True,
}
