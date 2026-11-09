# Smart Weather AI

MVP académico de 9.º semestre: una app de clima que combina **clima actual**, **visión del cielo** (clasificación de fotos), **pronóstico a corto plazo** y un **asistente conversacional por voz/texto**. Está pensada para usarse en móvil (Safari iOS) y puede instalarse como PWA.

- **Backend:** Python 3.10+ / FastAPI / Pydantic v2
- **Frontend:** React 18 / Vite 6 / Tailwind CSS 3 / Axios / lucide-react
- **IA:** Google Gemini (con fallback local), heurística de imagen (con soporte opcional para CNN), simulación de LSTM
- **Datos externos:** Open-Meteo, Nominatim (OpenStreetMap), ipapi.co

> Este README es la guía de referencia del proyecto. Describe cómo está compuesto, cómo fluye la información, los contratos de datos y qué partes son reales vs. simuladas. Está hecho para retomar el trabajo en futuras sesiones.

---

## 1. Estructura del repositorio

```
PROJECT-CLIMA/
├── .github/
│   └── workflows/
│       └── ci.yml                     # Backend pytest + frontend build
└── smart-weather-ai/
    ├── backend/
    │   ├── app/
    │   │   ├── main.py                  # App FastAPI, CORS, logging, lifespan/DB
    │   │   ├── config.py                # Settings (pydantic-settings, .env)
    │   │   ├── schemas.py               # Contratos Pydantic (request/response)
    │   │   ├── api/
    │   │   │   └── routes.py            # Endpoints REST (/api/*)
    │   │   ├── routers/
    │   │   │   └── admin.py             # Métricas e historial del panel admin
    │   │   ├── db/
    │   │   │   ├── database.py          # Engine SQLite + sesión
    │   │   │   ├── models.py            # Modelo WeatherLog
    │   │   │   └── crud.py              # log_weather() + cleanup_logs()
    │   │   └── services/
    │   │       ├── weather_service.py   # Open-Meteo + clima simulado
    │   │       ├── location_service.py  # GPS/IP + geocodificación dinámica con sesgo
    │   │       ├── forecast_model.py    # "LSTM" simulada
    │   │       ├── vision_model.py      # Validación de imagen + CNN opcional + heurística
    │   │       └── gemini_agent.py      # Gemini + razonador local de respaldo
    │   ├── scripts/
    │   │   └── cleanup_logs.py         # Depuración manual del historial
    │   ├── tests/                       # pytest + SQLite temporal
    │   ├── smart_weather.db             # Generado en runtime (no versionado)
    │   ├── requirements.txt
    │   └── requirements-dev.txt         # pytest + httpx (solo tests/CI)
    └── frontend/
        ├── src/
        │   ├── App.jsx                  # Orquestador de estado y layout
        │   ├── main.jsx                 # Bootstrap React
        │   ├── index.css                # Tailwind + clases .card/.btn
        │   ├── services/api.js          # Cliente Axios
        │   ├── hooks/
        │   │   ├── useGeolocation.js    # navigator.geolocation
        │   │   └── useSpeech.js         # Web Speech API (STT + TTS) + desbloqueo iOS
        │   └── components/
        │       ├── MainWeatherView.jsx  # Pantalla móvil: clima, visión, texto y voz
        │       ├── AdminModal.jsx       # Acceso protegido por token
        │       └── AdminPanel.jsx       # Métricas e historial (dentro del modal)
        ├── public/                      # manifest.webmanifest, icon.svg
        ├── vite.config.js               # Proxy /api -> :8000
        ├── tailwind.config.js
        └── package.json
```

Archivos generados/no versionados: `node_modules/`, `dist/`, `.venv/`, `__pycache__/`, `.env` (ver `.gitignore` en la raíz).

---

## 2. Cómo funciona de extremo a extremo

### Flujo principal (al abrir la app)

1. `App.jsx` llama `requestLocation()` (`useGeolocation`). Pide permiso de GPS con `enableHighAccuracy`, `timeout=15000`, `maximumAge=60000`.
2. Con coordenadas (o sin ellas), ejecuta en paralelo `GET /api/weather/current` y `GET /api/weather/forecast`.
3. El backend resuelve la ubicación (`location_service`):
   - `lat/lon` presentes → geocodificación inversa con **Nominatim**.
   - sin coordenadas → ubicación aproximada por **IP** (`ipapi.co`).
   - si falla → etiqueta neutra (`default`).
4. Con las coordenadas resueltas, `weather_service` consulta **Open-Meteo**. Si falla o no hay coordenadas, devuelve **clima simulado determinista**.
5. `forecast_model` genera 6 horas de pronóstico simulado a partir del clima actual.
6. `MainWeatherView` pinta el hero del clima, la recomendación y el pronóstico desde `App.viewData`. La recomendación inmediata se calcula en el cliente; si luego el asistente responde, se usa la del asistente.

### Flujo de visión

La sección de visión de `MainWeatherView` → `POST /api/vision/analyze` (multipart `image` + `location` opcional) → `vision_model.analyze_sky_image`:

- Valida que sea imagen y ≤ 10 MB.
- **Control de calidad:** calcula brillo medio y varianza en escala de grises. Si el brillo es `< 25` o la varianza `< 12` (foto negra, lente tapado o color plano), devuelve `status="invalid_image"`, una descripción guía y `rain_probability=0.0`, sin clasificar.
- **Filtro de cielo abierto:** analiza color HSV (azul atmosférico/sesgo frío), proporción de tonos cálidos y neutros, dispersión de gradientes, densidad de bordes y delta vertical. Rechaza techos, paredes e interiores con `status="invalid_image"`, `is_valid=false` y `sky_label="Interior o superficie plana detectada"`; tampoco los registra en la base de datos.
- Preprocesa a 224×224 RGB normalizado con media/std de ImageNet.
- Si `VISION_MODEL_PATH` apunta a un modelo PyTorch válido → inferencia CNN (5 clases).
- Si no → **clasificador heurístico** (brillo, dominancia de azul, contraste).
- El resultado incluye `label`, `confidence`, `state`, `status`, `description`, `rain_probability`, y el contrato de rechazo `has_image`, `is_valid`, `sky_label`, `message`.

El resultado se guarda en `App.analysis` y se envía como contexto al asistente.

### Flujo de persistencia y admin

La base SQLite (`backend/smart_weather.db`) guarda **solo consultas deliberadas**:

| Acción | `query_type` |
| --- | --- |
| Análisis de foto (`/api/vision/analyze`) | `vision` |
| Pregunta al asistente (`/api/assistant/ask`) | `assistant_query` |

Las cargas pasivas de clima (`/api/weather/current`, `/api/weather/forecast`) **ya no se registran**, y los análisis de imagen inválidos (`status="invalid_image"`) se descartan sin tocar la base. Los tipos `weather_check` y `destination_query` quedaron como legados y se eliminan con la depuración.

La escritura nunca bloquea la respuesta principal: si la DB falla, solo se registra un warning. El panel admin se abre desde el candado de `MainWeatherView`, pide un PIN/token en el modal y lo envía como header `X-Admin-Token` a `/api/admin/summary`, `/api/admin/history` y `POST /api/admin/cleanup`. El backend valida el token contra `ADMIN_TOKEN` (`401` si falta, `403` si es incorrecto); si `ADMIN_TOKEN` está vacío, el panel queda deshabilitado. La limpieza borra legados y duplicados exactos conservando el registro más antiguo de cada grupo; también puede ejecutarse con `python scripts/cleanup_logs.py` desde `backend/`.

### Flujo del asistente

El dock de texto/voz de `MainWeatherView` → `App.handleAsk` → `POST /api/assistant/ask` con `{ prompt, current_context }` → `gemini_agent.generate_weather_response`:

1. **Detecta y normaliza el destino** con Gemini: entiende jerga y abreviaciones (“huixqui” → “Huixquilucan”, “el tec” → “Tecnológico de Monterrey Campus Santa Fe”). El regex en español queda solo como respaldo sin clave/modelo, y se descartan destinos que el modelo invente y no aparezcan en la pregunta.
2. Si hay destino, lo **geocodifica dinámicamente con sesgo espacial** de ±1.2° (~120 km) hacia la ubicación del usuario: Nominatim → Photon → ambos sin sesgo restringidos a México (`countrycodes=mx`) → Open-Meteo Geocoding. No hay listas fijas de lugares.
3. Construye un contexto JSON legible (ciudad, métricas, visión CNN, lluvia máxima del pronóstico, destino).
4. Llama a **Gemini** pidiendo **JSON estricto** (`answer`, `need_umbrella`, `need_jacket`, `need_sunscreen`, `summary`).
5. Si Gemini falla (sin clave, cuota, modelo retirado, JSON inválido) → **razonador local** con plantillas variadas. La demo nunca se queda sin respuesta.
6. El frontend muestra la respuesta y actualiza la recomendación. La síntesis de voz se reproduce bajo demanda con `useSpeech`; en iOS el motor se desbloquea dentro del gesto de usuario (tocar micrófono o escuchar).

---

## 3. Backend

### Configuración (`app/config.py`)

Variables leídas de `.env` o del entorno. Todas tienen valores por defecto seguros:

| Variable | Default | Uso |
| --- | --- | --- |
| `GEMINI_API_KEY` | `None` | Clave de Google AI Studio. Opcional. |
| `GEMINI_MODEL` | `gemini-1.5-flash` | Modelo preferido (se autocorrige si no existe). |
| `HOST` | `0.0.0.0` | Escucha en toda la red local. |
| `PORT` | `8000` | Puerto del servidor. |
| `APP_NAME` / `APP_VERSION` | `Smart Weather AI` / `0.1.0` | Metadatos. |
| `CORS_ORIGINS` | `["http://localhost:5173"]` | Allowlist JSON de orígenes permitidos. Para LAN/túnel se amplía explícitamente. |
| `ADMIN_TOKEN` | vacío | Token obligatorio para `/api/admin/*`. Vacío deshabilita el panel. Genéralo con `openssl rand -hex 32`. |
| `VISION_MODEL_PATH` | `None` | Ruta opcional a pesos `.pt`. |
| `DATABASE_URL` | `sqlite:///backend/smart_weather.db` | Override de la base de datos. |

`get_settings()` está cacheado con `lru_cache`.

### Servicios (resumen y estado real)

| Servicio | Qué hace | Estado |
| --- | --- | --- |
| `weather_service.py` | Clima actual vía Open-Meteo; fallback simulado determinista (semilla `ciudad+hora+coords`). Mapea códigos WMO a condición/emoji. Cachea por coordenada redondeada + hora. | **Real** con fallback |
| `location_service.py` | Resolución GPS/IP y geocodificación dinámica con sesgo de proximidad, abreviaturas de estados de México, cachés (`lru_cache`) y locks para no duplicar llamadas. | **Real** con fallback |
| `forecast_model.py` | Simula salida de LSTM: curva diurna + lluvia derivada de humedad/condición, con ruido acotado y semilla por día/hora. | **Simulado** |
| `vision_model.py` | Validación de calidad + carga opcional de CNN PyTorch; si no existe, heurística de color/brillo. | **Heurística** (CNN preparada) |
| `gemini_agent.py` | Agente Gemini con selección dinámica de modelo, extracción de destinos, prompt estricto JSON y razonador local. | **Real** con fallback |
| `db/` | Persistencia SQLAlchemy/SQLite del historial de consultas. | **Real** |

Detalles clave:

- **Selección de modelo Gemini:** `_list_generate_models()` lista los modelos disponibles y `_candidate_model_names()` ordena candidatos (configurado → flash preferidos → flash más recientes). Si el modelo falla en runtime, `_advance_model()` prueba el siguiente. Esto cubre la retirada de `gemini-1.5-flash`.
- **Recomendaciones (regla compartida):**
  - paraguas si `lluvia ≥ 40%` o humedad ≥ 80% o condición/visión indican lluvia;
  - chamarra si `temp ≤ 18°C` o viento ≥ 25 km/h;
  - protector solar si `temp ≥ 26°C` y `lluvia < 30%` y sin señales de lluvia.
- **Geocodificación dinámica (sin hotspots):** `dynamic_geocode()` prueba Nominatim con `viewbox` de ±1.2° alrededor del usuario, Photon con el mismo sesgo, luego ambos sin sesgo con `countrycodes=mx` y, por último, Open-Meteo Geocoding. Los resultados se cachean con `lru_cache`.

### Endpoints (`app/api/routes.py`, prefijo `/api`)

| Método | Ruta | Entrada | Salida |
| --- | --- | --- | --- |
| GET | `/api/health` | — | `{status, service, version}` |
| GET | `/api/weather/current` | `?lat&lon` (opcional, ambos o ninguno) | `CurrentWeather` |
| GET | `/api/weather/forecast` | `?lat&lon&hours` (1–24, default 6) | `ForecastResponse` |
| POST | `/api/vision/analyze` | FormData `image` (+ `location` opcional), ≤10 MB | `SkyAnalysis` |
| POST | `/api/assistant/ask` | `{prompt (1–1000), current_context}` | `AssistantResponse` |
| GET | `/api/admin/summary` | Header `X-Admin-Token` | Métricas por día + días más lluviosos |
| GET | `/api/admin/history` | Header `X-Admin-Token`, `?limit` (1–500, default 50) | Historial reciente |
| POST | `/api/admin/cleanup` | Header `X-Admin-Token`, `?delete_legacy&dedupe` (default `true`) | Conteo de registros eliminados |
| GET | `/` | — | Metadatos + links a docs/health |

Errores: `400` coordenadas incompletas o imagen inválida, `401`/`403` token de admin ausente o incorrecto, `413` imagen > 10 MB, `415` tipo no imagen, `422` payload inválido (incluido `current_context` > 8 KB).

### Contratos de datos (`app/schemas.py`)

```text
CurrentWeather: location, temperature, feels_like, humidity, wind_kph,
                uv_index, condition, sky_state, emoji, rain_probability,
                latitude, longitude, country, country_code,
                location_source ("gps"|"ip"|"default"|"geocoded"),
                data_source ("open-meteo"|"simulated"), updated_at

ForecastResponse: location, source ("lstm"|"simulated"),
                  points[{ time, temperature, rain_probability }]

SkyAnalysis: label, confidence (0–1), state,
              source ("cnn"|"heuristic"),
              status ("ok"|"invalid_image"), description,
              rain_probability (0–100),
              has_image, is_valid, sky_label, message

AssistantResponse: answer, recommendations{need_umbrella, need_jacket,
                   need_sunscreen, summary}, source ("gemini"|"fallback"),
                   destination (query, resolved, location, current, forecast | null)

WeatherLog (tabla weather_logs): id, created_at (America/Mexico_City), date,
  location, temperature, rain_probability, sky_condition, query_type
  ("assistant_query"|"vision"|"weather_check"|"destination_query")
```

> `weather_check` y `destination_query` son tipos legados de solo lectura; las consultas nuevas se registran como `assistant_query` o `vision`.

---

## 4. Frontend

### Estado y componentes

`App.jsx` es el contenedor de estado:

- `weather`, `forecast`, `analysis`, `assistant` → datos de las APIs.
- `loadingWeather`, `loadingAssistant`, `error`, `online` → UI feedback.
- `useGeolocation()` → coordenadas + estado del permiso.
- `recommendations` (`useMemo`): usa las del asistente si existen; si no, calcula localmente desde clima + pronóstico + visión.

| Componente | Responsabilidad |
| --- | --- |
| `App` | Contenedor de estado: clima, pronóstico, análisis, asistente, admin, errores y adaptación de datos a `MainWeatherView`. |
| `MainWeatherView` | Pantalla móvil completa: ubicación, estado En vivo/Simulado, hero del clima, métricas, consejo con TTS, pronóstico, visión con cámara/galería y dock de texto/micrófono. Usa `useSpeech`. |
| `AdminModal` | Modal que pide el token y aísla el panel administrativo de la pantalla principal. |
| `AdminPanel` | Totales, tabla día con día, historial reciente y botón de limpieza. |

### Simulado vs En vivo

- `data_sources.weather` refleja `CurrentWeather.data_source` (`open-meteo` o `simulated`).
- `data_sources.forecast` refleja `ForecastResponse.source` (`lstm` o `simulated`).
- La UI muestra “En vivo” solo si el clima actual es de Open-Meteo y el pronóstico no es `simulated`; en cualquier otro caso muestra “Simulado”.
- La miniatura de visión usa “Foto + pronóstico real” solo en modo live; con pronóstico simulado usa “Foto + pronóstico”. El badge de lluvia prioriza `rain_probability` del análisis de la foto y deja el pico horario como dato secundario.

### Hooks

- `useGeolocation`: envuelve `navigator.geolocation.getCurrentPosition`, deduplica prompts con `pendingRef`, devuelve `{coords, status, error, requestLocation}`. Nunca lanza; resuelve `null` si falla para que el backend use IP.
- `useSpeech`: Web Speech API, usado por `MainWeatherView`. `start/stop` para reconocimiento (`es-MX`), `speak/cancelSpeech` para síntesis y `unlockAudio` para desbloquear el TTS de Safari iOS dentro de un gesto del usuario. Detecta soporte, maneja errores comunes (`not-allowed`, `no-speech`) y cancela la síntesis al desmontar.

### Cliente HTTP (`services/api.js`)

- Axios con `baseURL = "/api"`, `timeout = 30000`.
- En desarrollo la URL real la resuelve el **proxy de Vite** (`vite.config.js` → `http://127.0.0.1:8000`). Por eso `VITE_API_URL` no se usa actualmente en el código del cliente (se importa `rawBase` pero no se aplica). Para apuntar a otro backend hoy hay que ajustar el proxy o el `baseURL`.
- `toFriendlyError` traduce timeouts y errores de red a mensajes en español.

### Estilos y PWA

- Tailwind con clases reutilizables `.card`, `.card-title`, `.btn`, `.btn-primary`, `.safe-bottom`.
- Mobile-first, `min-h-dvh`, safe areas de iOS.
- PWA: `public/manifest.webmanifest`, `apple-mobile-web-app-*`, `theme-color`. Icono SVG (para producción conviene generar PNG 192/512).

---

## 5. Puesta en marcha

### Backend

```bash
cd smart-weather-ai/backend
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
# Solo para tests/CI (incluye -r requirements.txt):
pip install -r requirements-dev.txt
# crea backend/.env con GEMINI_API_KEY=...
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

- API: http://localhost:8000
- Swagger: http://localhost:8000/docs
- Salud: http://localhost:8000/api/health

`backend/.env`:

```env
GEMINI_API_KEY=tu_clave_aqui
GEMINI_MODEL=gemini-1.5-flash
HOST=0.0.0.0
PORT=8000
# VISION_MODEL_PATH=./models/vision.pt
```

### Frontend

```bash
cd smart-weather-ai/frontend
npm install
npm run dev        # http://localhost:5173
npm run build      # genera dist/
npm run preview
```

`frontend/.env`:

```env
VITE_API_URL=http://localhost:8000
```

> El PIN/token de administración ya no se configura ni se compara en el frontend. Se escribe en el modal y el backend lo valida contra `ADMIN_TOKEN`; el valor nunca se incluye en el bundle.

### Probar en iPhone en la misma red

1. Averigua la IPv4 LAN del equipo (`ipconfig` / `ipconfig getifaddr en0`).
2. Backend escucha en `0.0.0.0:8000`; permite Python/uvicorn en el firewall privado.
3. Abre `http://<IP-LAN>:5173` en Safari.

> **iOS y HTTPS:** `geolocation`, `SpeechRecognition` y `getUserMedia` solo funcionan en **HTTPS** o `localhost`. Para probar voz y GPS reales usa un túnel (Cloudflare Tunnel o Ngrok) y ajusta el proxy/`baseURL` al backend HTTPS.

```bash
cloudflared tunnel --url http://localhost:8000   # backend
cloudflared tunnel --url http://localhost:5173   # frontend
```

---

## 6. Verificación manual (smoke test)

1. Al abrir, el navegador pide ubicación; la cabecera de `MainWeatherView` muestra ciudad/municipio.
2. Si se deniega, aparece “Usando ubicación aproximada por IP”, aviso y botón `GPS`.
3. Cargan temperatura, condición y métricas (humedad, viento, UV); el pronóstico de las próximas 6 horas se desliza en horizontal.
4. “Tomar foto o elegir de la galería” abre el selector nativo; una foto negra o plana devuelve `invalid_image` con 0% de lluvia.
5. “¿Qué clima hace en Santa Fe?” / “¿Lloverá en Toluca?” detecta, normaliza y geocodifica el destino con sesgo de proximidad.
6. El micrófono transcribe y envía; el botón de voz lee la respuesta en voz alta también en Safari iOS.
7. Repetir una pregunta similar produce redacción distinta (Gemini temperature 0.8).
8. La recomendación se actualiza tras la respuesta del asistente.
9. El candado de `MainWeatherView` abre el modal, pide el PIN/token y muestra el acumulado por día y el historial.
10. Una consulta pasiva de clima **no** añade registros; solo el asistente y la visión persisten. El botón “Limpiar” del admin elimina legados y duplicados.
11. `backend/smart_weather.db` se crea solo al arrancar; puedes borrarlo para reiniciar métricas o ejecutar `python scripts/cleanup_logs.py`.

---

## 7. Tests automatizados

### Backend (pytest)

```bash
cd smart-weather-ai/backend
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements-dev.txt
python -m pytest -q
```

- **19 tests** medidos localmente (sin porcentaje de cobertura; no se inventan métricas).
- `tests/conftest.py` usa una **SQLite temporal** en el directorio temporal del sistema, nunca `backend/smart_weather.db`, y un `ADMIN_TOKEN` de prueba (aleatorio o el del job de CI).
- Los tests no llaman a Open-Meteo, Gemini, Nominatim, Photon ni ipapi: esos servicios se mockean.
- Cobertura actual:
  - visión: foto negra y superficie plana se rechazan con `is_valid=false` y `rain_probability=0.0`; cielo sintético con textura/gradiente es válido;
  - admin: `401` sin token, `403` con token incorrecto, `200` con token válido; `cleanup` sin token no borra nada;
  - persistencia: `GET /weather/current` pasivo no inserta; visión válida y `POST /assistant/ask` insertan exactamente 1 registro;
  - pronóstico: `source="simulated"` y 6 puntos con hora, temperatura y lluvia 0–100;
  - asistente: contexto >32 claves o >8 KB responde `422`; contexto normal responde `200` con Gemini mockeado;
  - ubicación: Nominatim/Photon mockeados con sesgo de proximidad resuelven destinos sin red;
  - CORS: acepta `http://localhost:5173` y rechaza orígenes no listados.
- **No cubierto todavía:** CNN real con pesos PyTorch, LSTM real, llamadas reales a servicios externos, flujos E2E/navegador, geolocalización, voz y pruebas unitarias de componentes React.
- **Frontend:** el CI valida `npm run build`. No se agregó test unitario para `conditionKey`/`forecastIcon` porque implicaría extraer lógica de `App.jsx`; queda como pendiente para una iteración específica.
- La matriz de la **Etapa 6** no existe en este repositorio; no se actualiza ni se inventan porcentajes.

### CI (GitHub Actions)

`.github/workflows/ci.yml` corre en cada push y pull request:

- **Python 3.10:** instala `requirements-dev.txt`, ejecuta `compileall` y `python -m pytest -q` desde `backend/`.
- **Node 20:** ejecuta `npm ci` y `npm run build` desde `frontend/`.
- El job falla si un test o el build falla. No hay pasos de deploy ni secretos reales (solo un `ADMIN_TOKEN` de prueba en variables del job).

---

## 8. Decisiones de diseño y notas para futuras sesiones

- **La demo nunca falla por dependencias externas.** Cada servicio externo (Open-Meteo, Nominatim, ipapi.co, Gemini, SQLite) tiene un fallback local. Esto es intencional para presentaciones.
- **Visión con control de calidad:** antes de clasificar se valida brillo/varianza para evitar falsos positivos de lluvia con fotos negras o sin textura. Los umbrales viven en `vision_model.py` (`MIN_BRIGHTNESS=25`, `MIN_VARIANCE=12`) y son ajustables.
- **Persistencia desacoplada y deliberada:** `log_weather()` captura cualquier error y no interrumpe la respuesta. Solo se guardan consultas al asistente y análisis de visión; el clima pasivo no contamina las métricas. El resumen del admin se calcula con `GROUP BY date` en SQLite.
- **Privacidad:** solo se guarda ubicación, métricas y tipo de consulta; no se almacenan imágenes ni transcripciones de voz.
- **Geocodificación sin listas fijas:** la resolución de destinos es 100% dinámica con sesgo espacial de ±1.2° y fallback a México. Si se cambia la cobertura geográfica, ajustar `SEARCH_VIEWBOX_SPAN` y los `countrycodes`.
- **Admin autenticado:** el panel vive en un modal; el PIN/token se envía como `X-Admin-Token` y el backend lo valida con `ADMIN_TOKEN`. Sin token responde `401`, con token incorrecto `403`; el valor no se hardcodea ni viaja en el bundle. La limpieza (`cleanup_logs`) borra tipos legados y duplicados exactos; está disponible por endpoint y por script.
- **Audio iOS:** `unlockAudio()` se ejecuta al tocar el micrófono o el botón de escuchar para que `speechSynthesis` no quede bloqueado en Safari.
- **Pronóstico y visión son simulados por ahora.** `forecast_model._predict` debe reemplazarse por inferencia LSTM real manteniendo `{time, temperature, rain_probability}`. `vision_model._load_model`/`_infer_with_model` deben adaptarse a la arquitectura de la CNN y a `CLASS_LABELS`.
- **`gemini-1.5-flash` ya no está disponible para claves nuevas.** El agente resuelve el modelo vigente automáticamente; no lo fijes en código.
- **Punto a revisar:** `VITE_API_URL` se lee pero no se aplica en `api.js`; hoy todo depende del proxy de Vite. Si se despliega el frontend separado del backend, hay que usar `rawBase` como `baseURL` (por ejemplo `${rawBase}/api`) y ajustar CORS.
- **Cachés y límites:** `lru_cache` en Open-Meteo y geocodificación; TTL de 10 min para IP; lock para no duplicar llamadas simultáneas clima + pronóstico. Imagen limitada a 10 MB.
- **CORS con allowlist:** por defecto solo `http://localhost:5173`. Para probar desde una IP LAN o túnel se agrega el origen exacto en `CORS_ORIGINS` (lista JSON); no se usa `*` como default.
- **Fuentes honestas:** el pronóstico es simulado por ahora; la UI lo etiqueta como “Simulado” y evita mostrar temperaturas/métricas inventadas mientras carga.
- **Tests automatizados mínimos:** backend con pytest + SQLite temporal y CI con build del frontend (sección 7). La verificación manual de la sección 6 sigue siendo necesaria para GPS, voz, cámara y UI real.
- **Sin linter/formatter configurado** en el repo. El estilo actual es consistente (2 espacios, comillas dobles en JSX/JS, docstrings en Python).

### Ideas de siguiente iteración

- Conectar CNN y LSTM reales (pesos + entrenamiento).
- Ampliar tests de regresión de `gemini_agent` con respuestas Gemini simuladas.
- Extraer `conditionKey`/`forecastIcon` a un módulo puro y probarlo con `node:test`.
- Restringir CORS y mover la URL del backend a configuración de build.
- Iconos PNG de PWA 192/512 y service worker para offline real.
- Historial de conversación en el asistente y geolocalización inversa más robusta.

---

## 9. Variables de entorno — referencia rápida

| Dónde | Archivo | Claves |
| --- | --- | --- |
| Backend | `backend/.env` | `GEMINI_API_KEY`, `GEMINI_MODEL`, `HOST`, `PORT`, `CORS_ORIGINS`, `ADMIN_TOKEN`, `VISION_MODEL_PATH`, `DATABASE_URL` |
| Frontend | `frontend/.env` | `VITE_API_URL` (hoy solo documental; el proxy de Vite manda) |

Nunca se commitean claves: `.env` está en `.gitignore` (el `frontend/.env` versionado no contiene secretos).
