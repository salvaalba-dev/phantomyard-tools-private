# PhantomView

Un observatorio local y privado para recuperar el contexto de una instalación
Phantomyard: organización → departamento → rol → persona → herramientas,
procedimientos y documentos. Versión inicial **0.1.0**.

## Instalar y abrir

Requisitos: Python 3.11 o posterior. Para actualizar el software: Git y una copia
limpia del repositorio privado. Se instala únicamente PyYAML; la interfaz no
necesita Node, compilación ni servicios externos.

Windows, desde `phantomview/`:

```powershell
.\install.ps1
.\run.cmd serve --open
```

Linux / macOS:

```sh
sh install.sh
sh run.sh serve --open
```

El lanzador abre una sesión autenticada con un token temporal generado en memoria.
Escucha únicamente en `127.0.0.1:8765`. No publica el dashboard en Internet.
El token se transfiere al navegador en el fragmento de la URL, se elimina de la
barra de direcciones y permanece en sessionStorage. No se escribe en archivos,
logs ni configuraciones. `PHANTOMVIEW_TOKEN` permite proporcionar una sesión por
entorno desde un gestor de secretos; no lo incluyas en scripts versionados.

La primera apertura muestra **datos de ejemplo sintéticos**, señalados en todas
las vistas. No se usan identidades, documentos ni estadísticas de tu instalación.

## Conectar una instalación nueva o existente

En **Configurar instalación**, selecciona Nueva instalación o Instalación
existente y proporciona rutas absolutas a:

- Uno o varios `org.yaml` de PhantomOrg.
- La carpeta de personas de PhantomBot, si ya existe.
- Uno o varios `manifest.yaml` de PhantomDocs, si están disponibles.
- Un JSON de procedimientos estructurados opcional.
- Un informe JSON exportado de `phantombot doctor --json --no-repair`, opcional.

Una instalación nueva puede empezar sin personas ni documentos. PhantomView no
crea PhantomBot, no aprovisiona roles y no despliega personas: conecta las fuentes
a medida que se crean con las herramientas que las gestionan.

Alternativa por consola, usando el lanzador de tu plataforma:

```sh
sh run.sh setup --mode existing --org /ruta/org.yaml --personas /ruta/personas --docs /ruta/manifest.yaml --interval 300
sh run.sh serve --open
```

La configuración y el índice derivado pertenecen a PhantomView y viven en
`../.phantomview/`; están excluidos de Git. `--config /ruta/config.json` permite
usar una ubicación propia. No elijas una carpeta de persona como destino del
estado de PhantomView.

## Setups separados y perfiles en otras cuentas

Cada observatorio lee únicamente sus fuentes seleccionadas. No deduce la organización
por el dominio del VPS ni incorpora todas las cuentas del servidor. Los manifiestos de
otra organización se rechazan para evitar mezclar sus documentos.

En el asistente, **Rutas por persona** permite distribuir los perfiles entre cuentas,
con un mapa JSON de claves `organizacion:persona` y rutas absolutas. Deja la carpeta
común vacía al usar rutas explícitas. Por ejemplo:

```json
{"mi-organizacion:coordinacion": "/home/cuenta/.local/share/phantombot/personas/coordinacion"}
```

**Personas en otros equipos** declara una ubicación sin acceder al equipo remoto:

```json
{"mi-organizacion:proyectos": "PC local"}
```

La persona conserva su rol, jerarquía y relaciones de la especificación, y su estado
se muestra como **Otro equipo · sin comprobar**. Esta opción no establece una conexión
SSH ni realiza sondas remotas. Una carpeta no puede asignarse simultáneamente a dos
personas o setups. Las rutas deben corresponder al perfil; no uses `/home` como carpeta
común ni cambies los permisos de todas las cuentas para recopilar datos.

## Navegación

- Organización: recuentos derivados, grafo por capas y comprobaciones.
- Departamentos: equipos, política declarada y responsabilidades.
- Personas: ficha con rol, superior, funciones, herramientas y documentos a cargo.
- Herramientas: matriz de capacidades declaradas e integraciones MCP detectadas.
- Documentos: archivo registrado, propietarios, clasificación y ubicación.
- Procedimientos: pasos, responsables, entradas y resultados.
- Cambios: altas, bajas y modificaciones entre lecturas del observatorio.
- Fuentes y setup: procedencia, fechas, cobertura y configuración.

Los filtros de organización y departamento se conservan entre vistas. Los
perfiles distinguen especificación, instalación y evidencia; una herramienta
declarada no se presenta como disponible y una configuración MCP no acredita
permisos efectivos. Los diagnósticos importados son informes, no sondas en vivo.

## Sincronización manual y automática

**Actualizar ahora** vuelve a leer las fuentes configuradas. Puede configurarse
un intervalo de 30 segundos a 24 horas, o modo manual. La sincronización automática
se ejecuta mientras el servidor está en marcha, aunque el navegador esté cerrado.
Para ejecutarlo tras un reinicio, registra el lanzador `serve` con el gestor de
servicios de tu sistema; esta versión no instala servicios del sistema.

Se registran diferencias estructurales y se conservan las últimas 50 lecturas
con cambios. Una lectura idéntica no genera otro evento. Los fallos de lectura
conservan la última lectura válida y muestran un aviso; nunca se convierten en un
estado verde. Al cambiar la configuración se limpia el índice anterior para no
mezclar organizaciones.

## Actualización del software y vuelta atrás

```sh
sh run.sh update --tag v0.1.0 --check
sh run.sh update --tag v0.1.0
sh run.sh rollback
```

La implementación admite únicamente tags `vX.Y.Z` **firmados**, desde el origen
privado autorizado. `git verify-tag` debe verificar la firma con las claves de
release aprobadas por el operador. Rechaza copias con cambios locales, valida la
versión en una copia temporal y ejecuta sus pruebas antes de activarla. Conserva
el commit anterior como punto de retorno, y no modifica la configuración ni el
índice. La actualización manual requiere reiniciar el servidor.

En el setup puede seleccionarse una versión firmada explícita y un intervalo:
el servidor comprobará y aplicará únicamente esa versión, y se reiniciará tras
activarla conservando la sesión. No sigue ramas móviles ni instala versiones no
firmadas. **Todavía no hay una release firmada publicada**, por lo que la primera
distribución y el flujo de firmas deben completarse antes de activar esta opción.
La actualización por Git es inicial: no constituye un despliegue atómico entre
varias máquinas y debe ensayarse en un entorno de pruebas antes de producción.

## Alcance y pendientes

Implementado y probado localmente:

- Lectura de YAML/JSON de PhantomOrg; referencias, duplicados y ciclos.
- Detección de carpetas de personas y archivos de perfil ausentes.
- Lectura selectiva de metadatos de `mcp.json` y nombres de notas KB.
- Comparación de `role_id` en `.phantomorg.yaml` con el rol declarado.
- Lectura de manifiestos documentales con filtrado por `currentVersions`.
- Procedimientos mediante un archivo estructurado y diagnóstico mediante exportación.
- Sesión autenticada, rechazo de origen externo y de Host no autorizado.
- Sincronización manual, periódica, persistencia del índice e historial.
- Actualizador restringido a tags firmados y punto de retorno.

Pendiente de integración y de datos de la instalación:

- Google Drive: árbol completo, enlaces, permisos reales y cambios incrementales.
- PhantomBridge/PhantomMeet: estado y actividad en vivo de salas y grabaciones.
- Tareas y actividad de PhantomBot: historial, tiempos y cobertura de auditoría.
- Comprobación de integridad con PhantomDocs y ACL efectivas por usuario.
- Extracción revisable de procedimientos desde texto y enlaces entre notas KB.
- Agregación de múltiples equipos, instalación como servicio y autenticación para
  acceso remoto. No exponer este servidor directamente a Internet.
- Sincronización de bloques de perfil completos con el resultado del compilador.
- Firmas, releases y prueba end-to-end de actualización y rollback.

## Privacidad y propiedad de los datos

No lee `identity.json`, `vault.sqlite`, conversaciones ni contenidos de las notas
KB. No cambia configuración, confianza, memoria ni tareas de ninguna persona.
Los archivos de perfil se comprueban por existencia; el registro MCP se reduce a
nombre y transporte. La información privada permanece en el host.

El dashboard muestra metadatos documentales de las fuentes seleccionadas a su
operador autenticado. No es un portal de autoservicio para múltiples usuarios ni
aplica las ACL de cada persona al operador. Su cache debe protegerse con los
permisos del sistema operativo. No se sirve ningún archivo local arbitrario:
solo los cuatro recursos estáticos y dos endpoints autenticados.

El historial es un índice de observación regenerable; no sustituye la memoria de
PhantomBot ni su auditoría. La configuración es la fuente para recolectar; los
modelos organizativos originales mantienen la autoridad.

## Marca

Logo oficial tomado de `https://phantombot.bot/assets/img/logo.png`. Interfaz basada
en el negro, blanco, grises y verde `#3fb950` de PhantomBot, con detalle azul en el
símbolo. Familias Inter / JetBrains Mono con fallback a fuentes del sistema; no
hay solicitudes a Google Fonts ni dependencias de CDN. El logo se usa localmente
como identificación del ecosistema; no implica una publicación oficial.

## Pruebas

```sh
python -m pip install -r phantomview/requirements.txt
python -m unittest discover -s phantomview -p 'test_*.py'
```

Las pruebas verifican acceso autenticado, rechazo de origen/Host externo, rutas,
referencias, ciclos, secreto no recolectado, estado de persona intacto, historia
sin duplicados, recuperación de una lectura fallida y selección documental de
versiones actuales. CI preparada para Python 3.11/3.12 en Linux y Windows.

## Desarrollo

Repositorio privado: `salvaalba-dev/phantomyard-tools-private`. Este módulo es
independiente y consume los formatos del ecosistema; no contiene una copia de las
otras herramientas. Los ejemplos son sintéticos. No subir configuración,
identidades, caches, tokens ni documentos de una instalación real.

## Acceso delegado mediante PhantomBlog

La modalidad de servidor reutiliza `phantomblog.access` de la instalación existente:
petición Nostr/NIP-98 firmada, clave pública del emisor en una lista explícita,
protección contra repetición y enlace de cinco minutos, de un solo uso. PhantomView
no implementa otro firmante ni lee identidades privadas. El firmante existente de
PhantomBlog opera dentro de la cuenta de la persona responsable.

El código llega en `/#c=...`, se borra de la dirección y se canjea por una cookie
HttpOnly/SameSite=Strict/Secure. PhantomView limita además la sesión a 30 minutos,
guarda solo su hash en memoria y permite cerrar y revocar la sesión. El proceso
web sirve exclusivamente un índice exportado: no puede cambiar las fuentes,
recoger nuevos archivos ni actualizar software mediante la sesión humana.

La persona emisora debe ser asignada expresamente. Que un rol tenga funciones de
coordinación lo convierte en candidato, pero no asigna por sí mismo la herramienta.
El alta inicial comprueba que la persona y su rol coincidan con `org.yaml`; un cambio
posterior de custodio requiere revisar la política de acceso y reiniciar el visor.

`deploy_au.py` prepara el piloto AU con destinos propios y se niega a sobrescribir
una instalación existente. Crea un recolector separado, un temporizador de cinco
minutos y un visor sin privilegios de administrador. Usa Python, YAML y PhantomBlog
ya instalados. Antes de activar el proxy privado HTTPS, revisar su origen exacto,
la persona emisora y la disponibilidad de los puertos. Requiere aprobación humana
para la instalación; el parámetro `--apply` es el paso que escribe y activa servicios.

Para emitir una URL, la persona utiliza el firmante existente con el puerto del visor:

```sh
PYTHONPATH=/opt/phantomblog-tool python3 -m phantomblog access-link \
  --persona PERSONA_RESPONSABLE --persona-dir RUTA_A_SU_ALMACEN_DE_PERSONAS \
  --port 8789 --public-origin https://HOST_PRIVADO:8790
```

No ejecutar el firmante desde una cuenta humana para hacerse pasar por la persona.
La petición humana debe llegar a la persona por su canal habitual, y la ejecución
pertenece a su cuenta. La integración de esta petición en su catálogo de herramientas
debe verificarse en el despliegue; el instalador del visor no modifica sus perfiles.

Las 32 pruebas locales incluyen el adaptador de acceso, límites de sesión, cierre,
canje único, aislamiento de origen y bloqueo de administración por navegador. Usan
un doble del verificador de PhantomBlog; la firma real debe verificarse también en
la prueba de integración con el runtime instalado.
