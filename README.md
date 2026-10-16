# SmartGuard

Seguridad para condominios a partir de las cámaras que ya tiene el conjunto:

- **Control de acceso por placa** (formato Ecuador). Lee la placa en la garita, la busca en el registro de residentes y muestra en grande **AUTORIZADO**, **BLOQUEADO** o **NO REGISTRADO**, con los datos del propietario. Cada acceso queda guardado con foto.
- **Varias cámaras** a la vez: IP por RTSP/HTTP (Hikvision, Dahua…), USB/integradas o archivos de video.
- **Conteo** de autos, motos, buses, camiones, bicicletas, personas y animales, por día y por hora. Se puede contar todo lo que aparece, lo que cruza una línea (con dirección entrada/salida) o lo que entra en una zona.
- **Foto de cada vehículo** que pasa, consultable en una galería por fecha.
- **Alertas de armas** de fuego y blancas: una franja roja con sonido en toda la app y la foto como evidencia, para que el guardia confirme la amenaza o la marque como falsa alarma.
- **Estadísticas** con gráficos y exportación a CSV.

## Instalación

Requiere [uv](https://docs.astral.sh/uv/) (instala Python 3.13 por su cuenta si hace falta).

```bash
uv sync
uv run smartguard
```

La primera vez se descargan los modelos (unos 30 MB). Después la app funciona sin internet.

Al abrirla por primera vez muestra un video de demostración (`samples/demo.mp4`). Para usar las cámaras del condominio, entre en **Configuración → Cámaras del condominio**, agregue cada cámara con su URL y pulse **Probar conexión**.

| Marca | URL RTSP habitual |
|---|---|
| Hikvision | `rtsp://usuario:clave@192.168.1.64:554/Streaming/Channels/101` |
| Dahua | `rtsp://usuario:clave@192.168.1.108:554/cam/realmonitor?channel=1&subtype=0` |

Para leer placas conviene una cámara dedicada a la entrada, a 3–6 m del vehículo, que capture la placa con al menos 100 px de ancho.

## Uso

| Página | Para qué sirve |
|---|---|
| **Acceso** | Video de la garita, resultado de la última placa, historial y consulta manual. Desde la tarjeta se registra un vehículo nuevo. |
| **Alertas** | Alertas de armas con foto, pendientes de revisión: «Amenaza confirmada» o «Falsa alarma». |
| **Cámaras** | Mosaico con todas las cámaras en vivo. |
| **Registro** | Vehículos de residentes: propietario, cédula (validada), casa, estado autorizado/bloqueado. Exporta a CSV. |
| **Conteo** | Elegir qué contar por cámara y dibujar la línea o zona sobre el video. |
| **Estadísticas** | Conteos y accesos por día y hora, fotos de vehículos y exportación CSV. |
| **Configuración** | Cámaras, modelos, umbrales y carpeta de capturas. |

Los datos (base SQLite, capturas, modelos, `settings.json` y `smartguard.log`) se guardan en la carpeta de datos del usuario. En macOS es `~/Library/Application Support/SmartGuard`. La variable `SMARTGUARD_HOME` permite cambiarla.

## Cómo funciona

| Etapa | Tecnología |
|---|---|
| Seguimiento de personas, vehículos y animales | **YOLO26** (Ultralytics) + ByteTrack |
| Detección de placas | **YOLOv9** de `open-image-models` (ONNX) |
| Lectura de placas | **fast-plate-ocr** `cct-s-v2-global-model` (ONNX) |
| Validación | formato ecuatoriano y provincia, con corrección de confusiones típicas del OCR (0/O, 8/B, 5/S…) |
| Confirmación | la misma placa debe leerse 3 veces en 4 s; no se repite durante 60 s |

En las capturas del proyecto anterior, el OCR nuevo leyó bien todas las placas (PBZ-5579, PCX-7679). El sistema antiguo había confundido la mitad.

Cada cámara corre en su propio hilo, así que la interfaz no se congela. En un Mac con Apple Silicon, una cámara 720p se procesa a unos 9–10 fps con lectura de placas.

### Detección de armas

SmartGuard incluye su propio modelo, `smartguard-armas-v1`: YOLO26-S ajustado con unas 6.400 imágenes de Open Images. Contiene pistolas, rifles, escopetas, cuchillos, dagas y espadas, más 4.000 fotos de personas sin armas (con celulares, paraguas, linternas o herramientas) para que aprenda a no confundirlas.

Se evaluó con 1.251 imágenes que el modelo no vio al entrenar. Los resultados son por imagen, con umbral 0,5:

| Modelo | Armas de fuego detectadas | Armas blancas detectadas | Falsas alarmas |
|---|---|---|---|
| **smartguard-armas-v1** | **83 %** | **89 %** | 2,6 % |
| YOLO26-M Objects365 (el mejor modelo genérico), umbral 0,1 | 44 % | 48 % | 2,2 % |
| YOLOE-26-M por texto, umbral 0,6 | 26 % | 58 % | 2,8 % |

En la app, una alerta exige además dos condiciones:
- Que el arma se vea 3 veces en 2 segundos.
- Que esté junto a una persona que la cámara sigue. Así se descartan carteles, pantallas y vitrinas.

En un video de prueba alertó en 6 de 6 escenas con persona armada y en 0 de 6 escenas de personas con celulares, paraguas o herramientas. El video de demostración de la garita da 0 alertas.

**Limitaciones:**
- Las fotos de entrenamiento no son de cámaras de seguridad: confirme la precisión con grabaciones reales de sus cámaras.
- Un arma pequeña, oculta o a más de unos 10 m puede pasar inadvertida.
- A veces confunde el tipo de arma, por ejemplo un cuchillo grande con un arma de fuego.
- Toda alerta debe revisarla una persona antes de actuar. Las marcadas como «Falsa alarma» quedan guardadas para un próximo reentrenamiento.

Para medir la precisión con grabaciones reales de sus cámaras, sin abrir la interfaz:

```bash
uv run python -m smartguard.tools.process_video grabacion.mp4 --line 100,400,1200,400
```

## Desarrollo

```bash
uv run pytest        # pruebas (la interfaz se prueba con QT_QPA_PLATFORM=offscreen)
uv run ruff check
```

```
smartguard/
  core/       configuración, base de datos, fuentes de video, hilo por cámara
  vision/     seguimiento, placas, reglas de Ecuador, votación, conteo, fotos
  features/   una carpeta por página de la interfaz
  ui/         ventana principal, iconos y widgets compartidos
  tools/      procesamiento de video por línea de comandos
```

## Privacidad y licencias

- La app guarda fotos de vehículos y datos personales de residentes. Informe a los residentes y defina por cuánto tiempo se conservan, según la Ley Orgánica de Protección de Datos Personales de Ecuador.
- `ultralytics` (YOLO26) se distribuye bajo **AGPL-3.0**: si SmartGuard se distribuye o se ofrece como servicio, debe cumplir esa licencia o adquirir la licencia comercial de Ultralytics. `open-image-models` y `fast-plate-ocr` son MIT.
- El modelo `smartguard-armas-v1` deriva de pesos de Ultralytics (AGPL-3.0) y se entrenó con [Open Images V7](https://storage.googleapis.com/openimages/web/index.html): anotaciones CC BY 4.0 de Google y fotos CC BY 2.0 de sus autores.
