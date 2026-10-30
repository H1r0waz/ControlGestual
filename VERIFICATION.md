# Verificación — 2026-10-29

## 2026-10-30 — Control Gestual 5.3.0: consola visual Jarvis

- Interfaz oscura con acentos cian, núcleo SVG animado, indicadores de IA/micrófono/cámara/Android y ventana objetivo. Estados derivados de /api/state: espera, inicio, escucha, procesamiento, respuesta, elección/confirmación y pérdida de conexión. Sin telemetría inventada ni recursos web nuevos.
- Navegación Abrir asistente sin encender hardware/modelo. Controles existentes conservados; escritorio lateral, chat diferenciado por rol, herramientas compartidas y diseño adaptable. Movimiento reducido respetado. Título nativo conservado para exclusión del panel.
- Respaldo previo: work/backup-before-v53-20261030-194905. Nueva compilación PyInstaller 6.22.3, acceso directo 5.3 y migración de ajustes/autorización desde 5.2. Versiones anteriores conservadas.
- desktop_browser_check.mjs completo correcto: recorridos de gestos, calibración, segundo plano, minimizar/maximizar, perfiles, voz, conversación/confirmaciones, consulta de una frase y teléfono; cero errores JS y solicitudes externas. Dispositivos/ventanas/modelo simulados.
- frozen_browser_check.mjs correcto con ejecutable 5.3: cámara e inferencia sintéticas, cuatro contactos con pulgar, pausa, conversación, validación de teléfono y salida; acciones nativas bloqueadas y cero errores JS.
- jarvis_ui_check.mjs correcto sobre ejecutable: tres pestañas sin desborde horizontal a 360/390/650/1440px; siete estados visuales; preferencia de movimiento reducido; acceso a conversación sin iniciar micrófono/IA. Cero errores JS. Capturas de escritorio/móvil inspeccionadas visualmente.
- check_frozen.py correcto: ejecutable GUI 5.3.0, recursos locales, bandeja registrada, comprobaciones nativas sobre ventana de prueba y salida limpia; cámara física no abierta.
- No se probó voz/mano física ni teléfono real para este cambio visual. Las mediciones de reconocimiento y latencia de 5.2 siguen siendo antecedentes, no pruebas repetidas de esta versión.

## 2026-10-30 — Control Gestual 5.2.0: corrección de nombres y órdenes de voz

El usuario informó que Chrome/Discord no se reconocían y que 5.0 funcionaba mejor. Se comprobó que 5.1 activaba el reconocedor libre junto con la IA, mientras 5.0 usaba gramática acotada. Los ajustes vigentes solo registraban Chrome, Bloc notas y Codex; Discord estaba abierto pero no registrado. No se abrió el micrófono ni se leyó una grabación del usuario.

La comparación sobre los mismos WAV sintéticos reprodujo Chrome -> crm y Discord -> discordia en modo libre. Tras volver a gramática de comandos y registrar nombres, **11/11 frases** resolvieron la selección directa con confianza >=0,60. El contraste anterior dio 0/11 selecciones directas; ese número incluye alias/frases no registrados y no mide todas las posibles respuestas de Qwen. Evidencia detallada en work/app-voice-comparison.json. No es una medición de la voz real del usuario.

Corrección:

- Activar IA ya no cambia el reconocedor de órdenes. Se conserva la gramática de 5.0, con alias explícitos Control Chrome, Control Discord y seleccionar nombre.
- Migración de catálogo: Discord, Spotify, Steam, WhatsApp, Explorador y Edge; conserva nombres personalizados, limita el total y respeta eliminaciones posteriores mediante versión de catálogo. Frases personalizadas/reservadas mantienen prioridad.
- Dictado libre de una sola consulta: Control pregunta o botón Dictar consulta, con IA/micrófono activos. Vuelve automáticamente a órdenes tras recibir una frase, baja confianza, tiempo de espera de veinte segundos, pausa, parada o fallo de captura. Las acciones dictadas requieren confirmación incluso si coinciden con una orden conocida. No se agregaron coincidencias fonéticas aproximadas ni se bajó el umbral de comandos.
- La prueba guiada cancela una consulta pendiente; el estado distingue órdenes/consulta. El formulario conserva un borrador nuevo si el usuario lo edita mientras llega la respuesta de la consulta anterior.

Verificación ejecutada:

- **82 pruebas Python correctas**: cinco nuevas para consulta explícita de una sola frase, retorno de modo, generación, timeout, baja confianza, parada del micrófono, migración/eliminación de nombres, alias directos y confirmación de una acción dictada. Las demás pruebas de voz/IA/escritorio/teléfono se conservan.
- voice_model_check.py con la gramática de producción: **73/73 muestras** (las 72 anteriores y Control pregunta), confianza >=0,60. check_app_voice.py: **11/11** nombres y variantes correctos. Modelo Vosk real y audio Microsoft Helena Desktop sintético, sin micrófono físico ni acciones durante reconocimiento.
- desktop_browser_check.mjs completo correcto: IA activa conserva órdenes, Dictar consulta cambia a una sola pregunta, respuesta simulada y regreso automático, más recorridos anteriores. Cero errores JavaScript/peticiones externas. Audio, ventanas y Qwen simulados en ese recorrido.
- PyInstaller 6.22.3: compilación correcta de releases/ControlGestual-V5.2/ControlGestual-V5.2.exe y acceso directo ControlGestual 5.2.lnk. Ajustes/autorización de teléfono migrados desde 5.1, sin cambiar la versión abierta del usuario. Respaldo previo en work/backup-before-v52-20261030-192753.
- check_frozen.py correcto: versión, recursos, bandeja, arranque real de Ollama y comprobación de que la voz sigue en modo commands al encender IA. Dictar requiere micrófono activo y se rechaza sin abrirlo. Se apaga solo el motor de prueba. Se conservan pruebas de ventana Tk descartable propia y cierre/confirmación.
- verify_frozen_voice.py correcto: motor/modelo/PortAudio dentro del ejecutable; WAV de minimizar y WAV de Chrome/Discord reconocidos como select_app:chrome.exe/select_app:discord.exe. No ejecuta esas acciones ni abre captura.
- frozen_browser_check.mjs correcto: UI, voz inicialmente apagada, ayuda/reinicio, contactos y cámara sintética, pausa/cierre sin errores JavaScript.

Pendiente: prueba con la voz, micrófono y entorno acústico del usuario. Se resolvieron las causas reproducidas de configuración/modo de reconocimiento; no se afirma que toda dificultad acústica esté resuelta. La inferencia general de Qwen conserva la implementación comprobada en 5.1; esta fase se concentró en reconocimiento y control de modos, sin volver a ejecutar toda la evaluación de conversación real.

## 2026-10-30 — Control Gestual 5.1.0: integración local con Qwen

Se integró el Ollama portable 0.40.13 y qwen3:1.7b preparados en local-ai. La app inicia una instancia propia solo al pulsar Encender IA, con puerto loopback libre, nube desactivada, contexto de 2048 tokens y un modelo/consulta simultáneos. No toca otras instancias ni variables globales. Usa los recursos existentes fuera del ZIP de la aplicación y valida el digest del modelo esperado. Cancelar petición, reinicio y F8 invalidan la respuesta y cierran su conexión; apagar/salir termina únicamente su servidor/runners. Un cierre inesperado del motor restaura el modo de voz anterior.

Las órdenes reconocidas por el intérprete anterior mantienen su comportamiento. Las solicitudes nuevas pasan a Qwen con esquema JSON y validación local independiente: siete acciones, aliases registrados/current y ninguna clave adicional. El modelo nunca recibe acceso a Win32 ni a la API del controlador. Toda propuesta generada por él exige confirmación, con revalidación de identidad, título y exclusiones. Su texto sobre una acción se ignora para el resultado de ejecución; el resultado lo produce el controlador existente. Negaciones, acciones no soportadas y pedidos compuestos tienen límites adicionales y no se ejecutan como planes arbitrarios.

Verificación ejecutada:

- Suite completa final de **77 pruebas Python** correcta; las **10 pruebas focalizadas de integración/protocolo/recuperación** también pasaron tras añadir restauración de voz cuando el motor se detiene. Cubren JSON inconsistente, acciones/objetivos/campos extra, respuesta truncada, cancelación, falta de recursos sin arranque, cambio de modo ASR, confianza de frase con activación débil/directa, confirmación obligatoria, selección ambigua antes de confirmar y descarte tras reset.
- check_local_model.py: **7/7 casos del recorrido de interpretación** correctos. Cuatro usaron inferencia real (conversación, maximizar, minimizar, explicación con negación); tres se resolvieron con controles previos (abrir app no soportado, varias acciones y pedido de comandos/borrado). No se ejecutaron acciones en esa prueba. La primera consulta tardó unos 49 s y las siguientes entre 1 y 3 s, según la muestra.
- check_integrated_ai.py sobre fuente: app HTTP autenticada -> Qwen real -> propuesta sin cambiar la ventana -> confirmación -> maximización de una ventana Tk descartable propia. Mantiene PID original. Consulta en curso cancelada antes de cualquier acción; apagar IA restaura modo de voz y detiene el motor. No se actuó sobre ventanas del usuario.
- check_integrated_ai.py --frozen: mismo recorrido sobre ControlGestual-V5.1.exe, con conversación real, propuesta, confirmación, efecto nativo sobre su propia ventana, cancelación y apagado. La primera consulta del ejecutable tardó 55,63 s. Reportes en work/ai-end-to-end-check.json y work/ai-end-to-end-frozen-check.json. No se abrió micrófono físico.
- desktop_browser_check.mjs completo correcto: alta/baja de IA simulada, pregunta, propuesta, confirmación, conversación y funciones anteriores. Cero errores JavaScript/peticiones externas. Backend Win32, voz y respuestas del modelo simulados en ese recorrido; la inferencia y Win32 reales se probaron por separado como se indica arriba.
- Voz fija: **72/72 muestras Vosk** correctas, manteniendo el umbral anterior. Reconocimiento libre real: tres muestras con Control aptas para consulta/propuesta, y una muestra con Jarvis mal reconocido rechazada. Se mantuvo el rechazo de activaciones poco claras. El mínimo por palabra era inadecuado para frases largas con un artículo incierto: para consultas/propuestas sin ejecución directa se usa mínimo entre confianza de activación y promedio de frase, con umbral 0,80. Las órdenes directas conservan mínimo por palabra 0,60. Se verificó esta distinción con regresiones. Evidencia en work/free-voice-check.json. Audio español sintético; no se validó micrófono físico.
- PyInstaller 6.22.3: compilación correcta de la versión 5.1; acceso directo y ajustes/estado del teléfono migrados desde 5.0, con versiones anteriores conservadas. Copia previa de fuentes en work/backup-before-v51-20261030-182117. local-ai se agregó a .gitignore para no incorporar pesos, binarios, logs o estado privado.
- check_frozen.py, verify_frozen_voice.py y frozen_browser_check.mjs correctos: versión, Windows GUI, recursos, bandeja, motor de voz, ayuda, reinicio, UI, cámara sintética y pausa/cierre. Las acciones de ventanas se bloquearon en el recorrido de cámara; la prueba de IA real solo usó su ventana Tk.

Una corrida de la suite simultánea con la carga de Qwen no alcanzó a ocultar el overlay en la espera de dos segundos. Repetida sin esa carga, la suite completa pasó; no se modificó el overlay. La relación con carga/temporización es una observación del ensayo, no una causa demostrada.

Límites: modelo pequeño con posibles errores de interpretación/contenido, sin datos en vivo, apertura de apps, lectura de pantalla, acciones arbitrarias o planes de varias acciones. La primera consulta puede tardar cerca de un minuto. El micrófono y altavoces reales quedan pendientes. La voz libre debe activarse con Control; Jarvis permanece como nombre/prefijo escrito y en el modo de órdenes anterior.

## 2026-10-30 — Control Gestual 5.0.0: asistente local Jarvis

Se implementó un intérprete local acotado de frases para mover, maximizar, minimizar, restaurar, seleccionar y cerrar ventanas abiertas. Tiene entrada de texto en Micrófono y activación Jarvis por voz; los comandos Control existentes se conservan. Mantiene contexto HWND/PID en memoria, pregunta ante varias ventanas de una aplicación y espera elección por voz o botón durante treinta segundos. El cierre por Jarvis exige una segunda confirmación, sin cambiar el cierre directo anterior. Revalida identidad y título, rechaza repeticiones, cambios de objetivo, vencimiento y cancelación. No se agregó un modelo de conversación general ni servicios externos.

Se añadió síntesis española local de Windows mediante System.Speech, habilitada por preferencia explícita. El texto viaja como JSON por stdin y nunca como código/argumento de shell. Se descarta audio durante la respuesta y 700 ms después; se reinicia el reconocedor al cambiar el estado de salida. F8, bandeja, apagar micrófono y cierre del controlador detienen su propio proceso de voz. La conversación tiene hasta veinte mensajes en memoria; Reiniciar conversación borra mensajes, objetivo y elecciones. Se añadió un botón de micrófono en la tarjeta, se limitó la altura del historial y se corrigió el aviso global que cubría contenido al desplazarse.

Verificación ejecutada:

- **67 pruebas Python correctas**. Diez pruebas del asistente/salida cubren variantes, rechazo de solicitudes fuera de catálogo, negación y varias acciones juntas, selección ambigua, continuidad de objetivo pese a otra ventana activa, HWND/PID cambiado, título cambiado antes de confirmar, exclusiones, vencimiento, reinicio, cierre con confirmación de un solo uso, pausa, supresión de reconocimiento mientras habla y texto por stdin. Incluyen renderizado español real a WAV sin altavoces. Se conservan las pruebas anteriores de Windows, teléfono y productividad.
- **72/72 muestras Vosk correctas** con confianza mínima >=0,60: las 61 anteriores y once frases de Jarvis (movimiento, cortesía, maximizar, minimizar, elección, estado, cancelar, confirmar, ayuda, selección y navegador grande). Audio sintético Microsoft Helena Desktop, sin micrófono físico ni acciones durante decodificación. Todas las palabras de la gramática nueva se comprobaron contra el vocabulario del modelo. Los pronombres verbales que no están en ese vocabulario se admiten por texto; la guía distingue ejemplos de voz comprobados.
- desktop_browser_check.mjs completo correcto tras la pasada final: texto con cortesía, opciones entre dos ventanas, contexto de seguimiento, cierre con confirmación y cancelación, botón de micrófono junto a la conversación, voz simulada, preferencia de salida, rechazo de borrado de archivos y reinicio. Backend Win32 y TTS simulados en ese recorrido; cero errores JavaScript y peticiones externas observadas. Se conservan contactos, calibración, segundo plano, distribuciones y teléfono.
- PyInstaller 6.22.3: compilación correcta de releases/ControlGestual-V5.0/ControlGestual-V5.0.exe y acceso directo ControlGestual 5.0.lnk. Ajustes migrados desde 4.2 y claves locales del teléfono preservadas si existían; versiones anteriores conservadas. Respaldo previo de fuentes en work/backup-before-v50-20261030-155213. No hay raíz Git en este directorio: no se atribuyen cambios a un commit.
- check_frozen.py correcto sobre la compilación final: Windows GUI, versión, recursos, bandeja, ayuda del asistente y salida hablada inicialmente apagada. Una ventana Tk descartable propia fue minimizada por solicitud natural, maximizada por una continuación sobre el mismo objetivo y cerrada únicamente tras la confirmación de Jarvis. El proceso terminó con código 0. Se retiró solo el historial del servidor de prueba antes de comprobar que el cierre no añade Deshacer. No se actuó sobre ventanas del usuario.
- verify_frozen_voice.py correcto: modelo y PortAudio cargados dentro del ejecutable, reconocimiento real de muestra WAV. El motor de síntesis se probó generando work/assistant-tts-check.wav; no se reprodujo voz en altavoces físicos.
- frozen_browser_check.mjs correcto: paquete final, ayuda, rechazo de solicitudes fuera de catálogo, reinicio que elimina mensajes, salida inicialmente apagada, contactos, modelo de mano y worker, pausa y cierre. Captura de la tarjeta Jarvis inspeccionada: título visible y aviso sin cubrir controles. Audio/cámara sintéticos y acciones nativas bloqueadas en ese recorrido.

La pasada final añadió una regresión para conservar el objetivo no disponible tras un cierre/cambio de identidad. Repetir una orden de seguimiento no captura otra ventana activa; se exige nombrar otra app, cambiar selección o reiniciar. Se repitieron las diez pruebas focalizadas del asistente después del ajuste y se incorporó el caso al control del ejecutable.

**Pendiente con el usuario:** escucha con su micrófono, iluminación/cámara real, salida de altavoces y comportamiento acústico de la supresión de eco en su habitación. La lógica de descarte se verificó con estados simulados y síntesis a archivo, no con un bucle de audio físico. Se conserva la limitación de vinculación/control real de Android documentada en 4.1. Esta entrega no incluye comprensión general de preguntas ni lectura de pantalla.

## 2026-10-30 — Control Gestual 4.2.0: cierre normal en Windows

Se agregó Cerrar ventana al catálogo, botón compartido y voz (Control cerrar, Control cerrar ventana, Control cerrar aplicación). Puede asignarse a los gestos existentes; no se cambia ninguna asignación predeterminada. Actúa sobre el HWND/PID seleccionado, con validación de identidad, exclusiones, época de emergencia y generación de voz. PostMessageW/WM_CLOSE solicita el cierre normal; nunca termina un proceso. La aplicación puede pedir guardar, rechazar o ignorar la solicitud. El resultado informa Cierre solicitado, no asegura que la ventana haya cerrado. No añade un Deshacer ficticio y conserva el historial anterior.

Verificación ejecutada:

- **57 pruebas Python correctas**. Tres pruebas nuevas cubren mensaje dirigido, objetivo inválido/cambiado, aplicación colgada, selección, exclusiones, pausa de gestos, voz apagada y conservación del historial. Una ventana Tk descartable propia rechazó el primer WM_CLOSE y siguió abierta; aceptó el segundo y terminó con código 0. Se actualizó el mock del catálogo completo de voz para que la prueba no envíe mensajes a HWND ficticios.
- **61/61 muestras Vosk correctas** con confianza mínima >=0,60 y audio sintético Microsoft Helena Desktop. Incluyen las tres frases de cerrar y las anteriores. Se corrigió la grafía de aplicación en la gramática sin modificar aplicaciones. Se repitieron las 10 pruebas de voz tras ese ajuste. No se abrió micrófono físico.
- desktop_browser_check.mjs completo correcto: botón de cierre, catálogo de gestos y voz sobre backend simulado; no aumenta el historial. Mantiene recorridos anteriores de contactos, calibración, segundo plano, distribuciones y teléfono. Cero errores JavaScript y peticiones externas observadas.
- Compilación PyInstaller 6.22.3 correcta: releases/ControlGestual-V4.2/ControlGestual-V4.2.exe y acceso directo ControlGestual 4.2.lnk. Versiones anteriores conservadas, ajustes migrados desde 4.1 y claves del teléfono copiadas localmente si existían. Respaldo previo de fuentes en work/backup-before-v42-20261030-153923.
- check_frozen.py correcto: Windows GUI, versión, recursos y bandeja; además, solicitud de cierre por API real del ejecutable a una ventana Tk descartable propia, que terminó con código 0. Resultado sin entrada en Deshacer. verify_frozen_voice.py correcto: modelo, PortAudio y reconocimiento real dentro del paquete.
- frozen_browser_check.mjs correcto: UI compilada, contactos, modelo y worker incluidos, pausa y cierre del controlador; cámara sintética y acciones de ventanas bloqueadas durante ese recorrido. ZIP verificado por CRC y hashes de UI, modelo y herramientas portables, excluyendo settings.json y phone-private.

Límites: no se cerraron ventanas del usuario ni se verificaron diálogos concretos de Word/Chrome u otras aplicaciones. Una ventana de navegador puede contener varias pestañas: el cierre se aplica a esa ventana completa. Android mantiene sus acciones anteriores y no recibe la acción nueva.

## 2026-10-30 — Control Gestual 4.1.0: Android por Wi-Fi

Se agregó la pestaña Teléfono con vinculación por código local, conexión por puerto independiente, consulta de estado, desconexión, pausa, ventana scrcpy y acciones acotadas. Se incorporaron 14 órdenes de voz y destino explícito de gestos del puño para volver, recientes y desplazamiento vertical. Los comandos de escritorio se conservan.

La distribución portable oficial scrcpy 5.0.1 se descargó desde Genymobile y se comprobó contra el SHA-256 publicado. PHONE_ASSETS.json registra procedencia y los 16 archivos. ADB 37.0.1 y scrcpy 5.0.1 respondieron a sus consultas de versión. El ejecutable de ADB incluido generó correctamente un par de claves descartables en work/phone-key-smoke; esa prueba no inició servidor ni vinculó dispositivos. El programa inicia su servidor ADB únicamente al pedir vincular/conectar, con puerto e identidad locales propios. El código viaja por stdin y se borra del formulario; las claves persistentes no se incluyen en el ZIP.

Verificación ejecutada:

- Suite Python: **54 pruebas correctas**; incluye validación de IP/puerto y comandos, código fuera de argv/estado, entorno aislado, selección explícita del dispositivo, pausa, swipe, rechazo de componentes no válidos, opciones de scrcpy, autenticación HTTP y cancelación de gestos. Las operaciones del teléfono fueron simuladas.
- Suite JavaScript: **21 pruebas correctas**, reconocimiento de gestos y extensión.
- Reconocimiento Vosk real: **58/58 muestras** con audio español sintético; incluye los 14 comandos del teléfono. Sin micrófono físico ni ejecución de órdenes durante decodificación.
- PyInstaller 6.22.3: compilación Windows GUI correcta de ControlGestual-V4.1.exe. Se conservaron versiones anteriores y ajustes. Respaldo previo de fuentes en work/backup-before-v41-20261030-144202.
- check_frozen.py, verify_frozen_voice.py y frozen_browser_check.mjs: correctos. Se comprobó motor/modelo/PortAudio dentro del ejecutable, UI, cámara sintética, gestos, pausa y cierre. El formulario rechaza puerto inválido y borra el código antes de iniciar ADB.
- Recorrido específico de teléfono en navegador limpio: vincular/conectar simulados, botón Inicio, gesto de recientes con landmarks sintéticos, cambio de pestaña por clic con cámara activa, orden de voz y pausa que apaga cámara y desmarca el destino. Sin errores JavaScript ni peticiones externas. El modo raw CDP/noDefaults del test de segundo plano descartaba eventos de entrada después de otra sesión de cámara; la misma secuencia pasó con el controlador normal de Playwright. Se aislaron los recorridos para conservar la prueba real de visibilidad sin usar ese modo para el recorrido telefónico.
- desktop_browser_check.mjs completo: correcto tras separar las sesiones; conserva segundo plano, calibración, contactos, distribuciones, voz y recorrido telefónico. ZIP comprobado con testzip y hashes del modelo, UI y 16 herramientas portables; se excluyen settings.json y cualquier carpeta phone-private.

**Pendiente con el usuario:** vinculación Wi-Fi real, permisos específicos del Redmi, imagen scrcpy y recepción de entradas en Android. No se abrió cámara ni micrófono físico, no se introdujeron credenciales reales, no se cambió la configuración global ni se probó desbloqueo del dispositivo. Los swipes automáticos se calculan para orientación vertical.

## 2026-10-30 — Control Gestual 4.0.0: herramientas 1 a 7

Se implementaron los siete puntos pedidos:

1. Prueba guiada del micrófono: dos segundos de silencio para estimar nivel de fondo y tres frases con coincidencia, confianza, volumen máximo y saturación. Se pausan los gestos; las frases de práctica no ejecutan acciones. Al completar/cancelar/agotar tiempo, la voz queda pausada hasta Control continuar.
2. Confirmación previa y final en panel e indicador flotante; sonido opcional al finalizar, deshabilitado por defecto. El sonido se comprobó con winsound simulado; no se reprodujo sonido físico durante los tests.
3. Frases propias persistentes, por ejemplo Control grande, con lista, eliminación, acciones acotadas, protección de frases reservadas y validación de palabras presentes en el modelo. Se actualiza la gramática sin reiniciar micrófono. Se muestran etiquetas explícitas para maximizar/restaurar y controles de voz.
4. Selección de aplicación abierta por nombre: Chrome, Bloc notas y Codex por defecto y nombres configurables para ejecutables detectados. Se respeta exclusión; ventanas ambiguas requieren selección previa. No se inicia software cerrado.
5. Scroll por voz, botones y acciones asignables a gestos; botón para asignar arriba/abajo a pulgar + meñique conservando laterales. Tres pasos de rueda, dirigidos al centro de la ventana seleccionada, con comprobación de foco/ventana bajo puntero y retorno del cursor si el usuario no lo movió.
6. Volumen del sistema, silencio, reproducir/pausar y pistas con teclas multimedia estándar de Windows. Acciones disponibles en voz, botones y asignaciones. Envío acotado de pulsación/liberación y reintento de liberación si la primera operación fue parcial. No se inventa historial de Deshacer para scroll/multimedia.
7. Distribuciones favoritas de una a ocho ventanas: elección explícita, guardado por nombre sin sobrescribir accidentalmente, aplicar por botón o Control modo trabajo, eliminar y Deshacer del grupo. Se guarda ejecutable/título/pantalla y geometría relativa, no IDs persistentes. Comprobación previa de ventanas, pantallas y exclusiones; rollback ante error. Recuperación fallida informa estado parcial y conserva entrada para reintentar.

Verificación ejecutada:

- python -m unittest discover -s tests -p "test*.py" -q: **48 pruebas correctas**. Incluyen validación/migración, frases propias y nombres, reserva de comandos, wizard sin efectos, timeout, entradas multimedia/liberación, feedback previsto/completado/sonido simulado, scroll sin undo ficticio, exclusiones y modos con preflight, fallo en segunda ventana, rollback y recuperación parcial.
- node --test tests/*.test.mjs: **21 pruebas correctas**.
- tests/test_productivity_real.py: prueba real sobre dos ventanas Tk descartables propias. El widget de texto recibió scroll real y cambió su posición; se guardaron posiciones, se acomodaron en mitades, se aplicó el modo y se deshizo el grupo, comprobando geometría. La prueba inicial encontró verificación prematura de SetWindowPos asíncrono; se añadió espera acotada de confirmación como en el acomodo anterior. La regresión pasó después del cambio y en la suite final. El estado del test de scroll se reinicia para evitar evidencia de ejecuciones previas.
- scripts/voice_model_check.py: **44/44 muestras** con modelo y gramática reales, confianza mínima por palabra >=0,60. Incluyen las 37 intenciones estáticas, dos frases antiguas de mover, los tres nombres de aplicaciones predeterminados, Control grande y Control modo trabajo. Audio español sintético de Microsoft Helena Desktop, sin micrófono físico ni ejecución de acciones durante decodificación.
- scripts/desktop_browser_check.mjs: recorrido de las siete funciones con ventanas/audio simulados. Alias grande, aplicación por nombre, prueba guiada y comprobación de que no cambia el contador de acciones, preset de scroll, botones scroll/multimedia, guardar/aplicar modo y deshacer como grupo. Se mantienen pestañas, contactos, calibración, segundo plano, pausa y cierre; sin errores JavaScript ni peticiones externas observadas. Captura de Micrófono inspeccionada visualmente.
- PyInstaller 6.22.3: compilación correcta en releases/ControlGestual-V4.0/ControlGestual-V4.0.exe, acceso directo ControlGestual 4.0.lnk, ajustes copiados desde 3.2 y versiones anteriores conservadas. Copia de código previa en work/backup-before-v40-20261030-134940.
- scripts/check_frozen.py: versión 4.0.0, Windows GUI, recursos, bandeja y cierre correctos.
- scripts/verify_frozen_voice.py: motor, modelo y PortAudio cargados en el ejecutable, WAV sintético reconocido como minimizar. winsound.pyd presente en distribución.
- scripts/frozen_browser_check.mjs: UI y contactos reales del paquete con cámara sintética, alta de alias con validador Vosk real, catálogo actualizado y prueba guiada deshabilitada sin micrófono activo. Se conservan diagnósticos de audio con estado inyectado, selección de dispositivo y cierre; sin errores JavaScript, acciones nativas interceptadas.
- node --check desktop/app.js correcto. Después del recorrido se corrigió únicamente la etiqueta de alias para distinguir Maximizar de alternar; se sincronizó el recurso externo del paquete con el código fuente.

Límites: micrófono/cámara físicos, acento/ruido reales y respuesta de reproductores multimedia requieren prueba manual. El volumen y las teclas multimedia se probaron con envío simulado; no se modificó el volumen ni la reproducción del usuario. Scroll y distribuciones sí se probaron en nuestras ventanas descartables, no en las aplicaciones de trabajo del usuario ni en sus dos monitores físicos. Los tamaños mínimos, permisos elevados o cambios de pantallas pueden impedir aplicar una distribución; el error no se presenta como éxito. No se agregó inicio con Windows (punto 8 no solicitado), no hubo publicación ni se cerraron versiones anteriores del usuario.

## 2026-10-30 — Control Gestual 3.2.0: órdenes breves y claridad de entrada

Se simplificó la lista recomendada: Control mover izquierda/derecha, siguiente/anterior, mitad arriba/abajo, pantalla uno/dos/tres/cuatro, automático y descartar. Se mantienen las frases anteriores como alias. Control mover sin dirección se rechaza y muestra ejemplos. La evidencia del código previo fue que una frase no coincidente se descartaba sin feedback; ahora se muestra la última frase y el motivo de rechazo. No se afirma que esto resuelva errores acústicos reales del usuario.

Se agrega selección de dispositivo de entrada antes de iniciar, transcripción provisional, nivel RMS en escala visual de 0 a 100, advertencia de señal baja/silencio y saturación. No se agregó amplificación ni reducción de ruido, ni se cambió el modelo acústico. La lista de dispositivos usa la API de sounddevice; no abre un flujo al enumerar. Las hipótesis parciales solo se muestran. El reconocedor devuelve palabras con confianza y se rechazan órdenes con alguna palabra por debajo de 0,60; esta puntuación no garantiza exactitud. Se conserva la palabra Control, la ejecución por frase completa, exclusiones y cancelación de audio de un objetivo anterior.

Verificación ejecutada:

- python -m unittest discover -s tests -p "test*.py" -q: **38 pruebas correctas**. Nuevas regresiones para comandos breves y aliases, mover ambiguo, rechazo de baja confianza, nivel/saturación, confianza inválida y selección/listado de micrófonos. Se conserva el resto de las regresiones de voz/ventanas.
- scripts/voice_model_check.py: **31/31 muestras** reconocidas con confianza mínima por palabra >=0,60: las 29 intenciones recomendadas y las dos frases antiguas de mover. WAV sintéticos PCM españoles generados con Microsoft Helena Desktop; Vosk y gramática reales. El micrófono físico no se abrió y no se ejecutaron acciones al decodificar.
- scripts/desktop_browser_check.mjs: búsqueda/selección del micrófono de prueba, encendido, órdenes, pestañas, pausa y apagado con backend simulado. Se mantienen recorrido de gestos, calibración, ciclos, exclusiones, historial y segundo plano. Sin errores JavaScript ni solicitudes externas observadas. Captura de Micrófono inspeccionada visualmente.
- Compilación PyInstaller 6.22.3 correcta en releases/ControlGestual-V3.2/ControlGestual-V3.2.exe, acceso directo ControlGestual 3.2.lnk. Distribuciones previas conservadas; ajustes copiados desde 3.1. Copia de código anterior: work/backup-before-v32-20261030-133051.
- scripts/check_frozen.py: versión 3.2.0, Windows GUI, recursos, bandeja y cierre correctos.
- scripts/verify_frozen_voice.py: modelo y PortAudio cargados; WAV sintético reconocido como minimizar, sin acceso al micrófono.
- scripts/frozen_browser_check.mjs: recorrido de cámara/contactos/pestañas y pruebas de UI de voz con estado inyectado (nivel 65, transcripción, confianza 94%, selector bloqueado mientras escucha y selección de dispositivo al detener). Sin errores JavaScript; acciones nativas interceptadas. La etiqueta estática del resultado final se ajustó a Última frase después del recorrido y se sincronizó con el recurso externo del paquete.

Pendiente: precisión real con micrófono, acento, distancia y ruido del usuario, y selección/desconexión de sus dispositivos físicos. El 31/31 con síntesis no es una medición de su ambiente ni prueba una mejora de precisión acústica. Las suites JavaScript de lógica de mano no se repitieron porque esa lógica no cambió; el recorrido de integración sí se ejecutó. No se abrió ningún micrófono físico ni se cerraron las versiones anteriores del usuario.

## 2026-10-30 — Control Gestual 3.1.0: pestañas Gestos y Micrófono

Se separó la interfaz en dos paneles con pestañas accesibles. Gestos reúne cámara, contactos, asignaciones, perfil del puño, sensibilidad y calibración. Micrófono reúne encendido/apagado, estado, última orden y catálogo de comandos. Selección de ventana/pantalla, controles manuales, exclusiones, historial, bandeja y cierre permanecen compartidos. Indicadores en las pestañas muestran controles activos aunque su panel esté oculto. Cambiar de pestaña solo cambia visibilidad: no recrea componentes, no reinicia captura ni modifica el objetivo. Se admite clic, flechas, Inicio y Fin con foco y estado ARIA coherentes.

Verificación ejecutada:

- scripts/desktop_browser_check.mjs: Gestos predeterminada; Micrófono oculta Gestos y expone sus botones; volver con flechas/Inicio/Fin conserva los tracks de cámara vivos y el mismo trabajador. Con Micrófono simulado activo, pasar a Gestos permite completar una orden de minimizar y volver a Micrófono para comprobar el resultado. Se mantienen contactos, calibración, voz, pantalla destino, ciclo de aplicaciones, exclusiones, historial y segundo plano con inferencia lenta simulada; sin errores JavaScript ni solicitudes externas observadas.
- Se inspeccionaron visualmente capturas de ambas pestañas, generadas por el recorrido anterior.
- Compilación PyInstaller 6.22.3 correcta: releases/ControlGestual-V3.1/ControlGestual-V3.1.exe y acceso directo ControlGestual 3.1.lnk. Ajustes copiados desde 3.0; distribución anterior conservada. Copia previa en work/backup-before-v31-20261030-025651.
- scripts/check_frozen.py: versión 3.1.0, subsistema Windows GUI, recursos locales, bandeja y cierre correctos.
- scripts/verify_frozen_voice.py: bibliotecas de voz incluidas y cargadas, modelo listo, WAV sintético reconocido como minimizar. Sin acceso al micrófono físico.
- scripts/frozen_browser_check.mjs: pestañas comprobadas en el ejecutable, cámara sintética viva al cambiar de panel, cuatro contactos, pausa y cierre correctos; sin errores JavaScript. Operaciones nativas interceptadas.

No se repitieron las suites unitarias ni las 29 muestras de voz de 3.0, porque el cambio es de presentación y las comprobaciones de integración anteriores cubren la modificación. Las validaciones históricas se conservan abajo. Pendiente: interacción con cámara/micrófono físicos y sesiones largas. No se abrieron dispositivos físicos ni se cerraron las versiones anteriores del usuario.

## 2026-10-30 — Control Gestual 3.0.0: voz local

Se agregó control por micrófono con Vosk 0.3.45, sounddevice 0.5.5 y el modelo español local vosk-model-small-es-0.42. Descarga oficial y hashes en VOICE_ASSETS.json. Se instalaron dependencias únicamente en work/build-env; la distribución incluye motor, bibliotecas y modelo. Micrófono apagado al iniciar; no se guarda audio ni se envía al servidor HTTP. La captura y el reconocimiento ocurren en un hilo nativo, independiente de visibilidad o cámara del panel.

29 intenciones diferentes (31 frases con alias) requieren Control y una frase completa: todas las acciones de ventanas, maximizar/restaurar explícitos, alternancia, deshacer, descartar registro, pausa/continuación de voz, apagado de micrófono, detener todo, mostrar/ocultar panel, destino automático y cuatro destinos de pantalla. Los ajustes/calibración se manejan desde sus controles existentes. El selector de ventana/monitor se sincroniza con la voz; cambiar de objetivo invalida audio pendiente. Cola de audio acotada, reinicio ante desbordamiento, descarte de hipótesis parciales y limitación de repeticiones inmediatas.

Control pausar deja el micrófono escuchando Control continuar. Control apagar micrófono detiene la captura. Control detener todo, F8 y Pausar en bandeja detienen micrófono y gestos; Escape hace lo mismo con el panel enfocado. Cerrar el panel solicita detener ambos dispositivos; ocultarlo conserva los activos. Los comandos de ventanas comparten exclusiones, comprobación de identidad, bloqueo de acciones y Deshacer.

Evidencia ejecutada:

- node --test tests/*.test.mjs: **21 pruebas correctas**.
- python -m unittest discover -s tests -p "test*.py" -q: **35 pruebas correctas**. Nuevas pruebas de cobertura de acciones, frase exacta/palabra de activación, pausa/continuación, repetición, audio obsoleto, validación de selección, modelo ausente, cierre de flujo por orden hablada y micrófono desconectado usando una fuente simulada. Se verifican controles HTTP autenticados, destino, deshacer y exclusiones. Sobre ventanas Tk descartables se comprobaron maximización idempotente y restauración normal desde minimizada.
- scripts/voice_model_check.py: **29/29 intenciones reconocidas** con el modelo real y WAV españoles generados mediante Microsoft Helena Desktop de Windows, PCM mono 16 kHz/16 bits. No se abrió el micrófono ni se ejecutaron acciones al decodificar. Se ajustaron las frases de cuadrantes/mitades a palabras presentes en el vocabulario del modelo; no se ignoraron advertencias de palabras faltantes.
- scripts/desktop_browser_check.mjs: controles de voz reales en el panel/HTTP con captura y operaciones nativas simuladas: encender, minimizar, restaurar, mostrar texto entendido, pausar/continuar y apagar. Se conservaron las cuatro familias de contactos, ciclo de aplicaciones, segundo plano con inferencia lenta simulada, calibración, exclusiones, historial y cierre; sin errores JavaScript ni solicitudes externas observadas. Captura del panel revisada visualmente.
- PyInstaller 6.22.3: compilación correcta en releases/ControlGestual-V3.0/ControlGestual-V3.0.exe y acceso directo ControlGestual 3.0.lnk. Se conservaron distribuciones anteriores y ajustes. Copia previa del código: work/backup-before-v30-20261030-023710.
- scripts/check_frozen.py: versión 3.0.0, Windows GUI sin consola, recursos, bandeja y cierre correctos.
- scripts/verify_frozen_voice.py: modelo, DLL de Vosk y PortAudio incluidos y cargados desde el ejecutable. WAV sintético Control minimizar decodificado a minimize; micrófono físico no abierto.
- scripts/frozen_browser_check.mjs: UI, trabajador/modelo de mano, cuatro contactos, pausa y cierre correctos desde la distribución; sin errores JavaScript. Cámara sintética y acciones nativas bloqueadas.

Límites: no se abrió ni probó el micrófono físico, sus permisos de Windows, ruido ambiente o la voz/acento del usuario. La síntesis demuestra integración y decodificación, no precisión en el ambiente real. No hay identificación de hablante: una grabación o voz de fondo podría activar una orden completa. Las sesiones largas, desconexiones reales de dispositivo y los dos monitores físicos requieren prueba manual. No se dejó la versión nueva escuchando ni se cerraron procesos anteriores del usuario.

## 2026-10-30 — Control Gestual 2.3.0: pulgar + meñique

Se agrega el cuarto contacto, pulgar + meñique: izquierda activa la aplicación anterior y derecha la siguiente. Arriba/abajo quedan desactivados por defecto y se pueden reasignar desde el panel. Se conservan los otros contactos y el puño. Los ajustes 2.1/2.2 reciben solo la nueva familia; las asignaciones existentes se conservan sin mutar el objeto de entrada.

El servidor devuelve la ventana activada al cambiar de aplicación. La selección manual del panel sigue a esa ventana si el usuario no eligió otro objetivo durante la operación, de modo que repetir el gesto permite recorrer las aplicaciones. La selección automática permanece automática. Se mantienen exclusiones, pausa, validación de identidad y manejo de fallos de Windows.

Verificación ejecutada:

- `node --test tests/*.test.mjs`: **21 pruebas correctas**; se extendieron reconocimiento y liberación al meñique, en ambos sentidos laterales.
- `python -m unittest discover -s tests -p "test*.py" -q`: **28 pruebas correctas**. Nuevas regresiones de migración desde tres familias, conservación de asignaciones, selección devuelta por el servidor, cambio anterior/siguiente, exclusiones, pausa y vertical desactivada para el meñique.
- `scripts/desktop_browser_check.mjs`: las cuatro familias recorren trabajador → UI → servidor con cámara sintética y operaciones nativas simuladas. Se comprueba que el meñique cambia de aplicación y que la selección manual sigue a la ventana activada. Dos cambios siguientes recorren las dos ventanas de prueba en ciclo. Se conservan calibración, segundo plano con inferencia lenta simulada, minimizar/maximizar, exclusiones, historial, pausa y cierre; sin errores JavaScript ni peticiones externas observadas.
- Compilación PyInstaller 6.22.3: `releases/ControlGestual-V2.3/ControlGestual-V2.3.exe`. Acceso directo `ControlGestual 2.3.lnk`; versiones anteriores conservadas; ajustes copiados desde 2.2 con alternativas anteriores si falta ese archivo. Copia previa de código en `work/backup-before-v23-20261030-022902`.
- `scripts/check_frozen.py`: versión 2.3.0, subsistema Windows GUI, recursos locales, bandeja y cierre correctos.
- `scripts/frozen_browser_check.mjs`: cuatro contactos (incluido meñique) y liberación sin abrir toda la mano desde el ejecutable real, con cámara sintética y operaciones nativas bloqueadas; pausa y cierre correctos, sin errores JavaScript.

Pendiente: precisión del contacto con meñique usando webcam física y sesiones prolongadas; las pruebas con puntos sintéticos no acreditan precisión con manos reales. La cámara detecta cercanía en la imagen, no presión. No se modificaron ventanas de trabajo del usuario ni se cerraron sus versiones anteriores.

## 2026-10-30 — Control Gestual 2.2.0: contactos con el pulgar

Se reemplaza la selección por dedos extendidos por contactos: pulgar + índice (mitades), pulgar + medio (aplicaciones/maximizar/minimizar) y pulgar + anular (cuadrantes). Las asignaciones de las tres familias se conservan con sus identificadores anteriores; no se modifica el esquema de ajustes ni el perfil del puño. El puño conserva activación y apertura para confirmar. Los contactos se confirman separando el dedo del pulgar; no exigen abrir toda la mano.

Se usa distancia entre puntas normalizada por ancho de palma: contacto hasta 0,28 palmas, separación desde 0,45, estabilidad de captura 350 ms y de liberación 120 ms. Se requieren al menos dos dedos extendidos. Contactos múltiples y cambio de dedo durante el recorrido cancelan el contacto capturado. El meñique no tiene acciones asignadas y se distingue para no interpretarlo como otro contacto. Un puño con pulgar cerca de las puntas sigue siendo puño. Se actualizan instrucciones, etiquetas y resaltado de las puntas en la cámara. Se reconoce cercanía, no presión física.

Evidencia ejecutada:

- `node --test tests/*.test.mjs`: **21 pruebas correctas**, incluyendo contactos individuales, distancia normalizada por escala, umbrales separados, separación estable sin abrir toda la mano, cambio de contacto, ambigüedad, meñique ignorado y conservación del puño.
- `python -m unittest discover -s tests -p "test*.py" -q`: **26 pruebas correctas**; se mantienen migración, validación, permisos de acciones, pausa, exclusiones, historial y ventanas nativas descartables.
- `scripts/desktop_browser_check.mjs`: contacto de cada familia en trabajador → UI → HTTP, soltando el pulgar sin abrir toda la mano; etiquetas, marcador de pose y personalización comprobados. Se mantienen segundo plano/inferencia lenta simulada, minimizar/maximizar, calibración, pausa y cierre. Operaciones nativas simuladas; sin errores JavaScript ni peticiones externas observadas. Panel revisado visualmente.
- Compilación nueva en `releases/ControlGestual-V2.2/ControlGestual-V2.2.exe`, con acceso directo `ControlGestual 2.2.lnk`. Se conserva la distribución anterior y se copian sus ajustes a la nueva sin modificarla. Copia previa del código: `work/backup-before-v22-20261030-021625`.
- `scripts/check_frozen.py`: versión 2.2.0, subsistema Windows GUI, recursos, bandeja y cierre correctos.
- `scripts/frozen_browser_check.mjs`: ejecutable compilado y trabajador/modelo reales; tres contactos inyectados y liberados separando el pulgar, sin apertura completa. Se verificaron las direcciones y familias enviadas. Capturas, previsualizaciones y acciones nativas interceptadas para no modificar ventanas del usuario; cámara sintética. Pausa/cierre correctos, sin errores JavaScript.

Pendiente: comprobar precisión con webcam física y dedos del usuario. La cámara estima cercanía en la imagen y puede confundir superposiciones; no mide presión. No se verificaron sesiones prolongadas ni el traslado entre sus dos monitores físicos. Los procesos anteriores del usuario se conservaron; salir de ellos desde la bandeja antes de abrir la 2.2.

## 2026-10-30 — Control Gestual 2.1.0: combinaciones de dedos

Cambios: índice para mitades; índice y medio para aplicaciones/maximizar/minimizar; índice, medio y anular para diagonales de cuadrantes. El puño conserva su perfil. Se pueden personalizar o desactivar las 12 combinaciones nuevas sin cambiar el perfil del puño. Se añade guía visible, nombre de combinación, configuración validada en el servidor y migración de ajustes previos. Pulgar independiente; posturas exactas de los otros cuatro dedos, estabilidad de 350 ms y confirmación al abrir durante 120 ms. La extensión conserva la activación por puño.

Verificación ejecutada:

- `node --test tests/*.test.mjs`: **18 pruebas correctas**. Se agregan identificación exacta, independencia de pulgar/calibración, preparación, estabilidad, confirmación, espera, cancelación, posturas desconocidas y cuatro diagonales.
- `python -m unittest discover -s tests -p "test*.py" -q`: **26 pruebas correctas**. Incluyen migración independiente de perfiles, asignaciones del servidor, dirección/postura inválida, exclusiones, pausa y desactivación de gestos. Se mantienen las pruebas nativas sobre ventanas descartables.
- `scripts/desktop_browser_check.mjs`: las tres familias nuevas recorren trabajador → UI → HTTP con puntos sintéticos y operaciones nativas simuladas; se probó después de calibrar. Personalizar/desactivar un gesto de dedos conserva las asignaciones del puño. Se conservan regresiones de segundo plano con inferencia lenta simulada, minimizar/maximizar, pausa, cancelación y cierre. Sin errores JavaScript ni peticiones externas observadas. Captura del panel revisada visualmente.
- Compilación PyInstaller 6.22.3 correcta en `releases/ControlGestual-V2.1/ControlGestual-V2.1.exe`, acceso directo `ControlGestual 2.1.lnk`. `Iniciar.cmd` apunta a la versión nueva.
- `scripts/check_frozen.py`: versión 2.1.0, subsistema Windows GUI, recursos, bandeja y cierre correctos.
- `scripts/frozen_browser_check.mjs`: panel, trabajador/modelo, cámara sintética, pausa y cierre correctos desde el ejecutable; sin errores JavaScript. Acciones nativas bloqueadas durante esta prueba del paquete.

La primera compilación intentó usar el directorio anterior, cuyos archivos estaban abiertos por la versión 2.0 del usuario. Se detuvo al encontrar una DLL bloqueada; se restauraron 984 archivos faltantes desde `work/release-backup-20261030-020833`, sin sobrescribir archivos existentes. Los archivos de la versión anterior se compararon por SHA-256 con la copia: sin diferencias, excluyendo ajustes mutables. La 2.1 se compiló en una carpeta separada. Se añadió una comprobación previa al script para rechazar recompilar la 2.1 si está ejecutándose desde ese destino. No se terminaron los procesos 2.0 del usuario.

Copia del código anterior: `work/backup-before-v21-20261030-020531`. Ajustes previos de distribución copiados para la nueva instalación; el ZIP portable excluye `settings.json` y empieza con valores predeterminados. La lista `MEJORAS-PROPUESTAS.md` contiene propuestas, no funciones ya implementadas.

Pendiente: webcam física, precisión con dedos reales, sesiones largas y traslado entre los dos monitores del usuario. Los puntos sintéticos prueban la lógica y su integración, no la precisión del reconocimiento físico. La versión 2.0 del usuario sigue abierta; salir desde su bandeja antes de iniciar la 2.1.

## 2026-10-30 — Control Gestual 2.0.0

Se preparó la versión 2 con distribuciones de mitades/cuadrantes, destino de monitor, cambio de aplicación, perfiles y asignaciones de gestos, exclusiones por ejecutable, historial de 20 acciones y ejecutable Windows sin consola. La copia previa está en `work/backup-before-v2-20261030-013122`.

Evidencia ejecutada:

- `node --test tests/*.test.mjs`: **14 pruebas correctas**.
- `python -m unittest discover -s tests -p "test*.py" -v`: **24 pruebas correctas**. Incluyen migración de ajustes sin perder calibración, partición de pantallas con tamaños impares y coordenadas negativas, exclusiones en controles manuales y cambio de aplicación, perfiles personalizados/desactivados, destino explícito, historial multinivel y descarte de registros.
- Ventanas Tk descartables reales: acomodo en mitad y cuarto, recuperación de posición y cambio de foco entre dos ventanas. Se corrigió el cambio de foco mediante asociación temporal de ambas colas de entrada, desasociadas siempre al terminar. No se inyectaron teclas ni se modificaron ventanas de trabajo del usuario.
- `scripts/desktop_browser_check.mjs`: recorrido real de UI/HTTP con operaciones nativas simuladas: selector de monitor, distribución, cambio de aplicación, perfil predefinido y personalizado, exclusión de aplicación elegida, rechazo de una operación excluida y deshacer dos pasos. Se conservaron cámara/trabajador, calibración, pausa, cancelación y gestos con panel oculto e inferencia lenta simulada. Sin errores JavaScript ni peticiones externas de la página observadas.
- `scripts/check_frozen.py`: ejecutable compilado iniciado y cerrado correctamente; subsistema Windows GUI comprobado en su cabecera PE; versión 2.0.0; recursos locales presentes; proceso Tk/bandeja incluido y operativo. No se abrió la cámara física.
- `scripts/frozen_browser_check.mjs`: UI y detector ejecutados desde los recursos del paquete compilado, con cámara sintética. Las acciones nativas se bloquearon expresamente en esta prueba para proteger las ventanas del usuario. Inicio, pausa y cierre correctos, sin errores JavaScript.
- Construcción con PyInstaller 6.22.3 en `work/build-env`, con Python 3.14.4. Ejecutable en `releases/ControlGestual-V2`, acceso directo `ControlGestual 2.lnk`, ajustes de distribución conservados al recompilar. Dependencias de construcción registradas en `scripts/requirements-build.txt`.
- Se corrigió un cierre prematuro de conexiones al rechazar POST no autorizados en Windows: se consume el cuerpo pequeño y acotado antes de responder 403. La prueba de Host/origen volvió a pasar en la suite final.

Límites: la webcam física, los gestos personalizados con la mano del usuario, el traslado entre sus monitores físicos y las restricciones particulares de cada aplicación requieren prueba manual. Windows puede rechazar cambios de foco o tamaño en aplicaciones protegidas o que no respondan. No se probó suspensión del equipo ni sesiones largas. No se dejó la versión nueva ejecutando; se debe salir de la versión anterior antes de abrir la nueva.

Las secciones siguientes conservan la evidencia histórica.

## 2026-10-30 — Corrección de gestos en segundo plano y minimizar → maximizar

El usuario informó reconocimiento incorrecto en segundo plano y que no podía maximizar después de minimizar. Se reprodujeron tres defectos mediante regresiones que fallaron antes del cambio: rechazo explícito de una ventana minimizada, cambio automático de objetivo por el foco que Windows entrega a la ventana de atrás, y pérdida del agarre con detecciones separadas 500 ms.

Cambios: maximización directa desde estado minimizado; conservación del objetivo minimizado ante el cambio de foco pasivo, con liberación al activar una ventana distinta; reconocimiento completo del gesto dentro del trabajador y tolerancia de 1,2 segundos entre detecciones. Las cancelaciones y cambios de ajustes usan un identificador de seguimiento para descartar mensajes antiguos.

Verificación:

- **14 pruebas JavaScript** y **18 pruebas Python**, incluidas las regresiones indicadas. Las pausas prolongadas siguen cancelando el gesto.
- Ventana Tk descartable real: minimizar → maximizar directamente, comprobar que deja de estar minimizada y queda maximizada; Deshacer recupera el estado minimizado anterior. No se operó sobre ventanas de trabajo del usuario.
- Navegador aislado, panel oculto y minimizado: se añadieron **350 ms de demora a cada inferencia simulada** y puntos de mano inyectados; se completaron minimizar → maximizar y deshacer. Modelo y trabajador reales, operaciones nativas simuladas en este recorrido. Calibración, pausa y liberación de cámara siguen pasando.

La demora reproducida muestra un defecto real de tolerancia; no constituye una medición del rendimiento de la webcam del usuario. El reconocimiento con su cámara y una sesión prolongada en segundo plano siguen pendientes de comprobación manual después de reiniciar la aplicación. No se cambiaron sus ajustes guardados.

## 2026-10-30 — Maximizar/restaurar hacia arriba y minimizar hacia abajo

El usuario informó que probó la versión anterior. Se añadió el gesto hacia arriba para alternar maximización y tamaño normal, manteniendo el gesto hacia abajo para minimizar. Las acciones verticales pertenecen al control del escritorio; la extensión conserva su comportamiento anterior.

- `node --test tests/*.test.mjs`: **13 pruebas correctas**. Se verifica gesto hacia arriba habilitado/deshabilitado, rechazo de diagonales y conservación de minimizar/laterales.
- `python -m unittest discover -s tests -p test_desktop.py -v`: **16 pruebas correctas**. Se verifica alternancia maximizar/restaurar, rechazo de ventanas sin soporte de maximización, endpoint autenticado, bloqueo con gestos pausados y disponibilidad de Deshacer.
- Sobre una ventana Tk descartable real, el nuevo controlador maximizó y restauró el tamaño normal; se comprobó `IsZoomed`, se conservó la prueba de minimizar y se recuperó el estado anterior con Deshacer.
- Recorrido de navegador con trabajador/modelo reales y cámara sintética: botón Maximizar / Restaurar, puntos de mano inyectados para gesto hacia arriba, flecha ↑, confirmación al abrir y deshacer. Las operaciones nativas de ese recorrido están simuladas; la validación Win32 real se realiza por separado sobre la ventana descartable. Se mantuvieron calibración, minimizar en segundo plano y liberación de cámara.

Pendiente: probar el nuevo gesto hacia arriba con la webcam física y las aplicaciones del usuario. No se movieron ventanas de trabajo ni se dejó la aplicación nueva ejecutando.

## 2026-10-30 — Calibración, sensibilidad, minimizar y segundo plano

- `node --test tests/*.test.mjs`: **12 pruebas correctas**. Incluyen calibración válida, rechazo de capturas insuficientes o indistinguibles, sensibilidad, minimizar hacia abajo y cancelación de diagonales. La extensión mantiene minimizar por gestos desactivado.
- `python -m unittest discover -s tests -p test_desktop.py -v`: **14 pruebas correctas**. Incluyen minimizar y deshacer, rechazo de gestos pausados, validación de ajustes, guardado y recarga de `settings.json` en una carpeta temporal del proyecto, y controles de bandeja que utilizan el mismo estado de pausa/deshacer.
- Sobre una ventana Tk descartable real: minimización verificada mediante `IsIconic`, recuperación de su maximización anterior y conservación del resto de comprobaciones de posición. No se movieron ventanas de trabajo del usuario.
- Proceso de indicador/bandeja real: `Shell_NotifyIcon` aceptó el registro del icono. Se comprobó que comunica si el atajo global se registró; un mensaje de prueba enviado exclusivamente a su ventana produjo la acción de deshacer. No se presionó un atajo físico en aplicaciones del usuario. La prueba conserva la comprobación de no activación del indicador y cierre limpio al terminar la tubería.
- Recorrido de navegador: modelo y trabajador reales con cámara sintética; puntos de mano inyectados para calibración guiada abierta/puño, cambio de sensibilidad, gesto lateral y gesto de minimizar, y deshacer. Se comprobó **`document.hidden === true` y estado de ventana `minimized`** mientras el trabajador continuaba entregando detecciones y el gesto hacia abajo llegaba al endpoint simulado de minimizar. La operación nativa del recorrido de navegador está simulada; la minimización Win32 real se verifica por separado en la ventana descartable.
- La primera comprobación de ocultación falló porque Playwright aplica emulación de foco que mantiene la página visible. Se repitió con Chromium aislado iniciado externamente y conexión CDP `noDefaults`, sin modificar el perfil habitual del usuario ni forzar un valor falso de visibilidad. La repetición pasó.
- Pausa por cambio de estado equivalente a F8/bandeja, finalización de pistas, cancelación durante el inicio y cierre del servidor pasaron. Sin errores JavaScript ni peticiones externas de la página observadas.

Pendiente: calibrar con la **webcam física del usuario**, verificar el atajo físico y la comodidad del gesto de minimizar, probar el menú de bandeja en su sesión y validar sesiones largas con el panel oculto. La comprobación de segundo plano es breve, no una prueba de suspensión, bloqueo de sesión o descarte de página. No se dejó la aplicación nueva ejecutando al terminar las comprobaciones.

Las secciones siguientes conservan la evidencia de versiones anteriores.

## Actualización: puño, mano dibujada y transición de movimiento

- Nuevo gesto común para escritorio y extensión: mano abierta prepara, puño estable selecciona, desplazamiento de palma fija dirección, apertura estable confirma. Se conserva cancelación por pérdida de seguimiento, recorrido mínimo, tiempo máximo y descanso.
- `node --test tests/*.test.mjs`: **10 pruebas correctas**, actualizadas para puño/apertura, postura intermedia, rechazo de cierres o aperturas breves, cancelación y movimiento animado por pasos en Chrome.
- `python -m unittest discover -s tests -p test_desktop.py -v`: **11 pruebas correctas**. Se verifica la secuencia de interpolación Win32 y la recuperación de la posición original ante fallo de un paso de animación. Se animó exclusivamente una ventana de prueba descartable dentro de la pantalla visible; se mantuvieron las comprobaciones reales de deshacer y maximización.
- Ambos recorridos de navegador pasaron. El de escritorio usa modelo real con cámara sintética para inicialización y **puntos de mano inyectados** para probar el gesto. Comprueba además que el canvas tiene píxeles del esqueleto, identifica el puño y se borra al perder la mano. La extensión utiliza APIs reales de Chrome para separar la pestaña y desplazar su ventana por pasos, con pantallas simuladas.
- La cámara física y la fluidez del traslado entre los monitores del usuario continúan pendientes de validación manual. No se grabaron imágenes ni se movieron ventanas de trabajo del usuario.

Las secciones siguientes documentan versiones anteriores del gesto.

## Actualización: índice y medio, selección automática, indicador y deshacer

El usuario informó que probó la versión anterior y funciona. No precisó todas las aplicaciones o recorridos probados; ese reporte se conserva separado de las comprobaciones siguientes.

Ejecutado en esta actualización:

- `node --test tests/*.test.mjs`: **10 pruebas correctas**. Incluyen el nuevo gesto con índice y medio, ambos sentidos, rechazo del antiguo gesto con el pulgar, cancelación al doblar cualquiera de los dos dedos, pérdida de seguimiento y descanso entre movimientos.
- `python -m unittest discover -s tests -p test_desktop.py -v`: **10 pruebas correctas**. Incluyen estado de deshacer, conservación del registro ante un movimiento fallido, selección activa y validación de identidad para el indicador.
- Sobre una ventana Tk descartable: captura real de `WINDOWPLACEMENT`, cambio de posición y tamaño, recuperación verificada de la geometría anterior; captura y recuperación del estado maximizado. No se movieron ventanas del usuario.
- Proceso de indicador real: muestra y ocultación verificadas mediante Win32, estilo de no activación y conservación de la ventana en primer plano. El proceso termina al cerrar la tubería.
- `scripts/desktop_browser_check.mjs`: panel y servidor local reales, selección automática predeterminada y recorrido completo **con puntos de mano inyectados**: separar → juntar índice/medio → nombre de ventana y flecha → movimiento simulado → deshacer. Por separado se inicializó el modelo real con cámara sintética, se verificó pausa, liberación de captura al cancelar el inicio y cierre. Sin errores JavaScript ni peticiones externas observadas.
- `scripts/browser_check.mjs`: prueba de la extensión conservada correcta con el detector actualizado. Geometría de pantallas y cámara siguen simuladas en esa comprobación.
- Sintaxis Python/JavaScript e inspección visual del panel y del estado de selección comprobadas.

Pendiente: probar el **nuevo gesto** con la webcam real, ajustar umbrales si es necesario y comprobar el indicador/deshacer al pasar entre las dos pantallas del usuario. El entorno de Codex continúa separado de esa prueba manual. No se implementaron todavía procesamiento de cámara con el panel oculto, calibración interactiva ni empaquetado como ejecutable.

Las secciones siguientes conservan la evidencia de las versiones anteriores.

## Ampliación: ventanas de aplicaciones del escritorio

Ejecutado después de la ampliación:

- `python -m unittest discover -s tests -p test_desktop.py -v`: **7 pruebas correctas**. Cubren selección del monitor, ajuste al vertical y conservación de maximización mediante Win32 simulado; rechazo de ventanas cerradas/minimizadas; autenticación local, Host y origen, límite de archivos, pausa y rechazo de una sesión de gestos antigua.
- Prueba Win32 real sobre **una ventana Tk creada expresamente en un proceso hijo**: enumeración y lectura de geometría, cambio de posición dentro del único monitor visible y rechazo de un traslado sin monitor de destino. Solo se movió esa ventana descartable; se terminó su proceso al finalizar.
- Lectura actual de `EnumDisplayMonitors`: **1 monitor, 3840 × 2160, área útil 3840 × 2088**. Esta observación no representa la distribución de dos pantallas que mostró el usuario.
- `scripts/desktop_browser_check.mjs`: panel local real con servidor Python, detector y modelo MediaPipe reales, cámara sintética y operaciones nativas simuladas. Verificó botón de movimiento, pausa mediante cambio simulado de estado de F8, finalización de pistas de cámara, cancelación durante el inicio de cámara y cierre del servidor. No se inyectó una tecla F8 real ni se movieron ventanas del usuario. Sin peticiones externas de la página ni errores JavaScript observados.
- Se ejecutaron nuevamente las **8 pruebas de JavaScript** y `scripts/browser_check.mjs` de la extensión conservada: correctas.
- Se corrigió además la limpieza de captura al cancelar el inicio de cámara, tanto en el panel nuevo como en la extensión original.

Pendiente: ejecutar `Iniciar.cmd` en la sesión del usuario, confirmar ambos monitores, probar aplicaciones reales normales y maximizadas, comprobar F8 físico y calibrar los gestos con la webcam real. El movimiento entre monitores físicos y la compatibilidad con cada aplicación siguen **NO VERIFICADOS**. El componente de escritorio no se dejó ejecutando después de las pruebas.

## Evidencia del prototipo original para Chrome

## Ejecutado

- `node --test tests/*.test.mjs`: ocho pruebas de lógica y adaptador con APIs simuladas. Verifican geometría horizontal/vertical y coordenadas negativas, límites del escritorio, separación de pestañas por ID, ventanas de una pestaña, maximización, cambio de pestaña durante el gesto, pérdida de seguimiento, duración mínima y descanso entre gestos.
- `node --check` en `core.js`, `background.js` y `panel.js`: sin errores de sintaxis.
- Lectura del manifest y comparación SHA-256 de los ocho recursos con `ASSETS.json`: correctas. El script de preparación también verificó SHA-512 del paquete contra la integridad publicada en npm.
- Prueba de extensión en Chromium aislado ya disponible, con Playwright ya disponible, perfil temporal, sin usar el perfil habitual del usuario. Panel a 580 px, separación real de una pestaña mediante la API de Chrome manteniendo su ID, selección de la nueva ventana, movimiento de esa ventana de vuelta a la izquierda, carga del modelo y procesamiento de cámara sintética. Al pausar, las pistas de captura terminan. Sin errores JavaScript de página ni peticiones HTTP/HTTPS de la página observadas durante esa prueba.
- Inspección visual de la captura `work/panel-check.png`.

## Límites

El Chromium headless disponible se cierra al ejecutar `chrome.system.display.getInfo()`, reproducido también sin abrir el panel. La comprobación de navegador sustituye **solo esa API** por dos áreas simuladas dentro de la pantalla virtual. Esto no demuestra detección de monitores físicos, posiciones en el escritorio real ni compatibilidad con el Chrome habitual del usuario. La cámara es sintética y no contiene una mano real.

No se instaló la extensión en el perfil habitual, no se cambió su modo de desarrollador, no se accedió a la webcam física y no se movieron ventanas del usuario. No se instalaron paquetes globales, servicios ni versiones adicionales de Python.

## Prueba manual pendiente

1. Cargar `extension` siguiendo `README.md` y abrir el panel desde el icono de la extensión.
2. Comprobar que aparecen ambas pantallas y elegir una ventana con dos pestañas sin trabajo importante.
3. Probar ventana a derecha y a izquierda; repetir estando maximizada.
4. Probar pestaña activa en ambas direcciones y confirmar que conserva su contenido y que la otra pestaña permanece en origen.
5. Encender cámara, conceder permiso y ajustar posición/iluminación. Probar el gesto hacia ambos lados y, si hace falta, invertir la dirección.
6. Probar mano fuera de cuadro, movimiento corto, repeticiones y cambio de modo durante el agarre. No deben activar movimientos accidentales.
7. Verificar Apagar/Pausar, Escape en el panel y Alt+Shift+P dentro de Chrome; comprobar que se apaga el indicador de cámara.

El prototipo está preparado para esta validación; la experiencia con hardware real sigue **NO VERIFICADA**.
