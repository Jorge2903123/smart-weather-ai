# Smart Weather AI — MVP

MVP funcional para el proyecto de 9.º semestre: clima actual, visión del cielo,
pronóstico a corto plazo y asistente de voz con Gemini. Backend en **FastAPI**,
frontend en **React + Vite + Tailwind CSS**, pensado mobile-first para Safari iOS.

## Arquitectura

```text
smart-weather-ai/
├── backend/
│   ├── app/
│   │   ├── main.py                  # FastAPI + CORS
│   │   ├── config.py                # Variables de entorno
│   │   ├── schemas.py               # Modelos Pydantic
│   │   ├── api/routes.py            # Endpoints REST
│   │   └── services/
│   │       ├── gemini_agent.py      # Gemini + razonador de respaldo
│   │       ├── vision_model.py      # CNN + fallback heurístico
│   │       ├── forecast_model.py    # Simulación de LSTM
│   │       ├── location_service.py  # GPS, destinos y fallback por IP
│   │       └── weather_service.py   # Open-Meteo + fallback simulado
│   ├── requirements.txt
│   └── .env.example
└── frontend/
    ├── src/
    │   ├── App.jsx
    │   ├── services/api.js
    │   ├── hooks/useSpeech.js
    │   ├── hooks/useGeolocation.js
    │   └── components/...
    ├── public/manifest.webmanifest   # PWA-ready
    ├── package.json
    ├── vite.config.js
    └── tailwind.config.js
```

## 1. Backend

Requisitos: Python 3.10+.

### Windows (PowerShell / CMD)

```bash
cd smart-weather-ai/backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

### macOS / Linux

```bash
cd smart-weather-ai/backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Edita `.env` y coloca tu clave de Google AI Studio:

```env
GEMINI_API_KEY=tu_clave_aqui
GEMINI_MODEL=gemini-1.5-flash
HOST=0.0.0.0
PORT=8000
```

> `gemini-1.5-flash` ya no está disponible para claves nuevas. El backend detecta
> los modelos vigentes con `list_models()` y cambia automáticamente a un Flash
> compatible (por ejemplo `gemini-3.5-flash-lite`), registrando el cambio en
> consola. Si no hay clave o la cuota falla, responde con un razonador local
> variado. La demo nunca se queda sin respuesta.

Ejecuta el servidor escuchando en toda la red local:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

- API: http://localhost:8000
- Swagger: http://localhost:8000/docs
- Salud: http://localhost:8000/api/health

### Endpoints

| Método | Ruta                     | Descripción                                      |
| ------ | ------------------------ | ------------------------------------------------ |
| GET    | `/api/weather/current`   | Clima actual (`?lat=...&lon=...` opcional)       |
| GET    | `/api/weather/forecast`  | Pronóstico 6 h (`?lat=...&lon=...&hours=6`)      |
| POST   | `/api/vision/analyze`    | FormData `image` → etiqueta + confianza          |
| POST   | `/api/assistant/ask`     | `{prompt, current_context}` → respuesta + destino |
| GET    | `/api/health`            | Estado del servicio                              |

La ubicación se resuelve en este orden:

1. `lat`/`lon` del GPS → geocodificación inversa con Nominatim.
2. Sin coordenadas → `ipapi.co` (IP pública).
3. Si ambos fallan → etiqueta neutra; la app sigue operativa.

El frontend pide permiso de ubicación al iniciar con `enableHighAccuracy: true`,
`timeout: 15000` y `maximumAge: 60000`. Si el usuario lo deniega, hace la petición
sin parámetros y el backend aplica el fallback por IP. En ese caso el Header muestra
un botón `GPS` para volver a solicitar la ubicación precisa y recargar clima +
pronóstico; también aparece un aviso con instrucciones para habilitar la ubicación
en Safari.

El asistente también detecta destinos en la pregunta (por ejemplo “Polanco”,
“Santa Fe”, “Condesa”, “Interlomas” o “Toluca”). La geocodificación usa tres
niveles: hotspots locales con coordenadas fijas para colonias y zonas conurbadas,
Nominatim restringido a México (`countrycodes=mx`) y Open-Meteo Geocoding como
respaldo. Después consulta su clima con Open-Meteo y compara el destino contra la
ubicación actual. El clima actual usa Open-Meteo cuando hay coordenadas y cae a
datos simulados si la API externa no responde.

## 2. Frontend

Requisitos: Node.js 18+.

```bash
cd smart-weather-ai/frontend
npm install
cp .env.example .env      # en Windows: copy .env.example .env
npm run dev
```

Abre http://localhost:5173.

`.env`:

```env
# En la computadora
VITE_API_URL=http://localhost:8000
```

El cliente normaliza la URL y agrega `/api` automáticamente.

## 3. Probar desde un iPhone en la misma red

1. Obtén la IP LAN de tu computadora:
   - Windows: `ipconfig` → “Dirección IPv4” (ej. `192.168.1.50`)
   - macOS: `ipconfig getifaddr en0`
2. Backend ya escucha en `0.0.0.0:8000`. Si el firewall lo bloquea, permite
   Python/uvicorn en la red privada.
3. En `frontend/.env`:
   ```env
   VITE_API_URL=http://192.168.1.50:8000
   ```
4. Reinicia Vite (`npm run dev`) y en Safari abre:
   `http://192.168.1.50:5173`

> **Micrófono y GPS en iOS:** Safari solo habilita `geolocation`,
> `SpeechRecognition` y `getUserMedia` en **HTTPS** (o localhost). Por HTTP en
> LAN el botón de voz y el GPS no funcionarán; en ese caso el backend usa el
> fallback por IP para la ubicación y el resto de la app sigue operativa.

### Túnel HTTPS (recomendado para voz y GPS)

Usa Cloudflare Tunnel o Ngrok para exponer ambos servicios con HTTPS.

Con Cloudflare (`cloudflared` instalado):

```bash
# Terminal 1: backend
cloudflared tunnel --url http://localhost:8000

# Terminal 2: frontend
cloudflared tunnel --url http://localhost:5173
```

Cada comando imprime una URL `https://...trycloudflare.com`.

1. Copia la URL HTTPS del **backend** en `frontend/.env`:
   ```env
   VITE_API_URL=https://backend-xxxx.trycloudflare.com
   ```
2. Reinicia Vite.
3. Abre en el iPhone la URL HTTPS del **frontend**.
4. Acepta el permiso de micrófono. El CORS del backend ya permite `*`.

Con Ngrok el equivalente es `ngrok http 8000` y `ngrok http 5173`.

## 4. PWA en iOS

La app incluye `manifest.webmanifest`, `theme-color` y metadatos
`apple-mobile-web-app-*`. En Safari:

1. Abre la URL de la app.
2. Toca **Compartir → Añadir a pantalla de inicio**.
3. Se abrirá en modo standalone (sin barra de Safari).

Los iconos actuales son SVG; para producción conviene generar PNG 192/512 y
actualizar el manifest.

## 5. Conectar los modelos reales

- **CNN de visión:** guarda los pesos (`.pt`) y define `VISION_MODEL_PATH` en
  `.env`. Ajusta `_load_model` e `_infer_with_model` en
  `backend/app/services/vision_model.py` a la arquitectura entrenada. Mientras
  no exista el archivo, se usa el clasificador heurístico (brillo, dominancia de
  azul y contraste) que devuelve etiquetas realistas.
- **LSTM de pronóstico:** reemplaza `_predict` en
  `backend/app/services/forecast_model.py` por la inferencia del modelo,
  manteniendo el formato `{time, temperature, rain_probability}`.
- **Clima real:** `weather_service.py` ya consulta Open-Meteo cuando recibe
  coordenadas. Si quieres otro proveedor, conserva el mismo contrato de salida
  (`temperature`, `humidity`, `condition`, `rain_probability`, etc.).

## 6. Verificación rápida

```bash
# Backend
cd smart-weather-ai/backend
.venv\Scripts\activate
uvicorn app.main:app --host 0.0.0.0 --port 8000

# Frontend (otra terminal)
cd smart-weather-ai/frontend
npm run build
npm run dev
```

Prueba manual:

1. Al abrir, el navegador solicita permiso de ubicación y el Header muestra la
   ciudad/municipio real devuelto por el backend.
2. Si se deniega el permiso, el Header indica “Usando ubicación aproximada por IP”
   y aparece el botón `GPS` para reintentar con alta precisión.
3. La temperatura y la carita cargan al abrir.
4. “Ver detalles” muestra humedad, viento y pronóstico por hora.
5. “Tomar o subir foto del cielo” devuelve etiqueta y confianza.
6. Pregunta “¿Qué clima hace en Santa Fe?” o “¿Lloverá en Toluca?”: el asistente
   debe geocodificar el destino y comparar su clima con el actual.
7. El botón de micrófono transcribe y envía la pregunta; la respuesta se lee en
   voz alta.
8. Repite una pregunta similar: Gemini debe cambiar la redacción manteniendo
   las recomendaciones coherentes.
9. La recomendación (paraguas/chamarra/protector solar) se actualiza tras la
   respuesta del asistente.
