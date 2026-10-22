Pink RouteManager (Odoo 19)
===========================

Módulo administrativo para preparar la sincronización RouteManager -> Odoo.
No activa una sincronización automática ni modifica el backend de RouteManager.
No depende de facturación, ventas, RR. HH. o flota.

Alcance
-------

* Empresas clientes y conductores como ``res.partner``.
* Un servicio reutilizable ``Viaje``, con unidad km.
* Un registro ``pink.routemanager.trip`` por viaje, con empresa, conductor,
  fecha UTC, kilómetros y estado final (COMPLETED/CANCELLED).
* ``pasajeroapp`` es únicamente un valor opcional del viaje. No se crean fichas
  ni relaciones con pasajeros individuales, vehículos, rutas o ubicaciones GPS.
* No se crean pedidos, facturas, precios de transporte ni asientos contables.
  El producto está deshabilitado para venta y compra.

Contactos
---------

Los obligatorios siguientes se aplican solo cuando ``pink_role`` tiene un valor.
Los demás contactos Odoo conservan sus requisitos originales.

========================== ======================== =====================================
Dato RouteManager          Campo Odoo               Regla
========================== ======================== =====================================
ID de empresa/conductor    pink_routemanager_id     UUID canónico, único, inmutable al asignar
Tipo de registro           pink_role                company o driver
Nombre                     name                     Obligatorio
Teléfono                   phone                    Obligatorio, al menos siete dígitos
Correo                     email                    Obligatorio y válido
Tipo de documento          pink_document_type       Obligatorio, V/E/J/G/P/C, sin valor supuesto
Número sin prefijo          pink_document_number     Obligatorio, texto, conserva ceros
license del conductor      pink_license             Obligatorio para conductor
companyId del conductor    pink_employer_id         Empresa Pink opcional, no empresa del viaje
Dirección de empresa       street                   Obligatoria para empresa
Responsable de empresa     pink_contact_name        Obligatorio para empresa
Activo/inactivo            active                   Archivo nativo, no eliminación
Compañía interna Odoo      company_id               Obligatoria para contactos Pink
========================== ======================== =====================================

``license`` se conserva como texto: el formulario actual utiliza valores como
``Tipo 3``. No se transforma ese dato en un número de licencia ni se inventan
vencimientos, certificados o datos ausentes.

La cédula actual de RouteManager no tiene selector separado de tipo documental.
El futuro sincronizador debe separar un prefijo explícito (por ejemplo V) del
número, o solicitar el tipo que falta. Nunca debe asumir V/J. El RIF se maneja
de igual forma; no se convierte en número entero ni se pierden ceros iniciales.

Los datos del responsable/correo de empresa se obtienen del contacto asociado
cuando existan. Las empresas que no tengan la información obligatoria quedan
pendientes de corregir, sin documentos ni responsables ficticios. El estado
Verificado/Inactivo se traduce a ``active`` por el sincronizador; no se archiva
un contacto por un estado desconocido.

Los campos históricos ``doc_tipo``/``vat_aux`` de ``base_contable`` no están
registrados en el ORM de la instancia de calidad inspeccionada, aunque exista
metainformación antigua. Este módulo usa el espacio ``pink_`` y no instala ni
altera la localización contable o el campo fiscal nativo ``vat``. Si se recupera
esa localización, habrá que acordar el mapeo documental antes de sincronizarla.

Viajes e identidad
------------------

``routemanager_id`` es el UUID canónico del viaje. ``customer_id`` se resuelve
mediante ``Trip.companyId`` y ``driver_id`` mediante el conductor efectivo del
viaje. No se deduce el cliente a partir de ``pink_employer_id``. Las relaciones
apuntan a contactos de la misma compañía interna Odoo del viaje.

``product_id`` usa el XMLID ``pink_routemanager.product_trip`` y ``uom_id``
permanece en km. ``distance_km`` debe enviarse explícitamente, ser finito y ser
mayor que cero para COMPLETED. CANCELLED permite cero explícito; un kilometraje
ausente nunca se transforma en cero. No se convierten metros, duración ni
estimaciones en kilómetros definitivos.

El futuro sincronizador deberá:

#. Buscar por UUID con ``active_test=False`` para incluir archivados.
#. Crear si no existe, o actualizar el mismo registro si ya existe.
#. Resolver empresa y conductor antes de enviar un viaje.
#. Ante un timeout de escritura, consultar el UUID antes de reintentar.
#. Usar un usuario dedicado con el grupo Pink y compañías Odoo explícitas.

Las restricciones únicas evitan crear dos registros con el mismo UUID, pero
no sustituyen un sincronizador, una cola de errores ni su conciliación.

Instalación y permisos
----------------------

Este addon se versiona exclusivamente en el repositorio Odoo, rama ``calidad``.
Tras desplegar y verificar el build Odoo.sh, actualizar la lista de aplicaciones
e instalar ``Pink RouteManager`` desde Odoo. No se instala directamente por SQL.

Asignar el permiso ``Pink RouteManager / Gestionar empresas, conductores y
viajes`` a los operadores y al usuario de integración. Los administradores base
reciben el grupo al instalar. Los campos Pink de contactos están protegidos por
el grupo a nivel ORM, no solo ocultos en la vista. Los viajes tienen regla global
de compañía y permiten consultar, crear, actualizar y archivar, no eliminar.
Los contactos referenciados por viajes no pueden borrarse ni cambiar su tipo o
compañía, incluso cuando los viajes estén archivados.

Pruebas
-------

``tests/test_structure.py`` comprueba sintaxis, manifiesto y estructura sin Odoo.
``pink_routemanager/tests/test_routemanager.py`` contiene las pruebas nativas de
ORM, validaciones y permisos. GitHub Actions instala el addon en Odoo oficial
19.0 con PostgreSQL desechable mediante ``tests/run_odoo.sh``. No levanta un
servidor local ni toca registros reales. Los logs se conservan como artefacto.

Estas pruebas usan TransactionCase porque validan restricciones y reglas del
ORM, no un flujo web; e2e no sustituye esa comprobación. La revisión visual y la
comprobación API en la base de calidad se realizan después de instalar el módulo.

Referencias consultadas
-----------------------

* Código oficial: https://github.com/odoo/odoo/tree/19.0
* Skill comunitaria: https://github.com/fhidalgodev/odoo-development-skill
* Guías oficiales: https://github.com/odoo/odoo/tree/master/skills

Los ejemplos comunitarios y de master se contrastan con 19.0: no se aplica el
nuevo modelo de permisos ``ir.access`` de versiones posteriores a Odoo 19.
