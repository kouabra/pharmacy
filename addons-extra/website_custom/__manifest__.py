# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
{
    'name' : 'Website custom',
    'version': '1.8',
    'category': 'Website/base',
    'sequence': 15,
    'summary': 'Website',
    'description': """
Website
====================

 """,
    'website': 'http://www.veone.net',
    'depends': ['base', 'mail', 'sale_management', 'website',
                'base_geolocalize', 'web','website_sale', 'sale', 'board'],
    'data': [
        'views/website_custom_view.xml',
        'views/payment_view.xml',


    ],
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
}
