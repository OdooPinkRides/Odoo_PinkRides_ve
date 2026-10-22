{
    "name": "Pink RouteManager",
    "version": "19.0.1.0.0",
    "summary": "Empresas, conductores y viajes por kilometraje de RouteManager",
    "category": "Services",
    "license": "LGPL-3",
    "depends": ["contacts", "product", "uom"],
    "data": [
        "security/pink_security.xml",
        "security/ir.model.access.csv",
        "data/trip_product.xml",
        "views/res_partner_views.xml",
        "views/trip_views.xml",
    ],
    "application": True,
    "installable": True,
}
