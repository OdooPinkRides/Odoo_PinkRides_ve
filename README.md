# Odoo_PinkRides_ve
Empresa de Movilidad en Venezuela

## Base de la rama calidad

`calidad` conserva los addons originales de `main` en `Localizacion_contable/` y `Facturacion Digital/`, sin modificar su implementación. La base de calidad contiene vistas de esos addons; omitir su código deja referencias a campos ausentes, como `purchase.order.x_tasa`. El módulo operativo del Rutero se añade sobre esa base y no incorpora dependencias ni procesos contables. `tests/test_structure.py` comprueba que se conserve el proveedor original del campo.

## Pink RouteManager (Odoo 19)

El addon [`pink_routemanager`](pink_routemanager/README.rst) incorpora empresas y conductores como contactos, documentación y licencia, y viajes con su empresa, conductor y kilómetros.

Sin facturación, vehículos ni fichas de pasajeros. El módulo prepara el destino Odoo; la sincronización automática del backend todavía no está implementada.

La rama `calidad` se verifica con GitHub Actions sobre Odoo oficial 19.0 y una base desechable. La instalación del addon en la instancia de calidad es un paso posterior al despliegue.
