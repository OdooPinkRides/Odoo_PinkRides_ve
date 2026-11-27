{
    'name': 'Confirmation Invoice Masiva',
    'version': '19.0.0.8.0',
    'summary': 'Aprobacion de facturas Masivas',
    'description': """
        Aprobacion de facturas Masivas
    """,
    'category': 'Account',
    'author': 'Silicon Valley Latam coladorador:Ing.Marilynmillan',
    'depends': ['account','contacts','factura_digital_unidigital',],
    'data': [
        'security/ir.model.access.csv',
        'wizard/account_move_mass_confirm_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}
