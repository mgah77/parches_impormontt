# -*- coding: utf-8 -*-

{
    'name': 'Parches Impormontt',
    'version': '16',
    'category': 'General',
    'summary': '',
    'description': """
    Parches Impormontt

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
