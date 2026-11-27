{
    'name': 'Confirmation Invoice Masiva',
    'version': '19.0.0.11.0',
    'summary': 'Aprobacion de facturas Masivas',
    'description': """
        Aprobacion de facturas Masivas, adjunto PDF fiscal Unidigital sin botón View Invoice,
        y campo Código en la ficha de contactos.
    """,
    'category': 'Account',
    'author': 'Silicon Valley Latam coladorador:Ing.Marilynmillan',
    'depends': ['account', 'contacts', 'factura_digital_unidigital'],
    'data': [
        'security/ir.model.access.csv',
        'views/res_partner_views.xml',
        'wizard/account_move_mass_confirm_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}