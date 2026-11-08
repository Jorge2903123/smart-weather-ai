# Smart Weather AI

**Smart Weather AI** es una Progressive Web App (PWA) de monitoreo meteorológico predictivo y asistencia multimodal. Integra redes neuronales convolucionales (CNN) para clasificación del cielo, pronóstico horario mediante telemetría satelital (LSTM / Open-Meteo), un asistente conversacional con síntesis y reconocimiento de voz orquestado por Google Gemini, y un panel administrativo para auditoría y métricas de uso continuo.

---

## 🚀 Características Principales

- **Diagnóstico visual del cielo (CNN):** clasificación de fotos en tiempo real (cielo despejado, nubosidad dispersa, tormenta) con filtro espectral y de varianza para rechazar imágenes no válidas o tomadas en interiores (techos, muros, oscuridad).
- **Asistente conversacional multimodal:** interacción por voz y texto vía Google Gemini, capaz de procesar lenguaje natural, entender jergas coloquiales locales y formular recomendaciones prácticas ("Qué hacer").
- **Geocodificación dinámica por sesgo espacial:** resolución de destinos mediante Nominatim / Photon API con ponderación geográfica (*Spatial Bounding Box*), permitiendo consultar rutas y puntos de interés sin depender de coordenadas estáticas.
- **Diseño mobile-first (iOS Safari):** adaptación completa a viewports dinámicos (`100dvh`), soporte para áreas seguras (`safe-area-inset` para Notch/Dynamic Island), acceso dual a cámara y galería, y persistencia de voz vía Web Speech API.
- **Panel administrativo y persistencia (SQLite):** registro de consultas y diagnósticos en base de datos relacional para consultar métricas agrupadas día con día (temperaturas promedio, volumen de uso y tendencias de lluvia).

---

## 🛠️ Stack Tecnológico

### Frontend

- **Framework:** React 18 + Vite
- **Estilos:** Tailwind CSS
- **Iconografía:** Lucide React
- **Audio y sensores:** Web Speech API (TTS y SpeechRecognition), Geolocation API, HTML5 Media Capture

### Backend

- **Framework:** FastAPI (Python 3.10+)
- **Servidor ASGI:** Uvicorn
- **Inteligencia artificial:**
  - Google Gemini API (`gemini-2.5-flash`, orquestación y Function Calling)
  - PyTorch / TensorFlow (CNN para análisis del cielo)
- **Persistencia:** SQLite + SQLAlchemy
- **Geolocalización y telemetría:** Open-Meteo API, Nominatim / Photon (OpenStreetMap)

---

## 📁 Estructura del Proyecto

```text
smart-weather-ai/
├── backend/
│   ├── app/
│   │   ├── db/
│   │   │   ├── database.py          # Conexión SQLite y sesión SQLAlchemy
│   │   │   └── models.py            # Modelo WeatherLog
│   │   ├── routers/
│   │   │   ├── admin.py             # Endpoints de métricas y auditoría
│   │   │   ├── assistant.py         # Orquestador conversacional Gemini
│   │   │   ├── vision.py            # Clasificación del cielo e inferencia CNN
│   │   │   └── weather.py           # Telemetría meteorológica y rutas
│   │   ├── services/
│   │   │   ├── location_service.py  # Geocodificación dinámica y sesgo espacial
│   │   │   ├── vision_service.py    # Filtro espectral (HSV) e inferencia
│   │   │   └── weather_service.py   # Integración con Open-Meteo
│   │   └── main.py                  # Punto de entrada FastAPI y middlewares CORS
│   ├── requirements.txt
│   └── smart_weather.db             # Base de datos SQLite
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   ├── AdminDashboard.jsx   # Métricas acumuladas y logs
│   │   │   └── MainWeatherView.jsx  # Vista principal móvil adaptada a iOS
│   │   ├── App.jsx                  # Estado global, orquestación y modales
│   │   └── main.jsx
│   ├── package.json
│   └── tailwind.config.js
└── README.md
```

---

## ⚙️ Instalación y Ejecución Local

### 1. Clonar el repositorio

```bash
git clone https://github.com/tu-usuario/smart-weather-ai.git
cd smart-weather-ai
```

### 2. Configurar el backend

```bash
cd backend

# Crear y activar entorno virtual
python -m venv venv
source venv/Scripts/activate   # Windows (Git Bash)
# source venv/bin/activate     # Linux / macOS

# Instalar dependencias
pip install -r requirements.txt
```

Crea un archivo `.env` dentro de `backend/` con tu clave de Gemini:

```env
GEMINI_API_KEY=tu_api_key_aqui
```

Inicia el servidor:

```bash
uvicorn app.main:app --reload --port 8000
```

### 3. Configurar el frontend

En una segunda terminal:

```bash
cd frontend

# Instalar paquetes
npm install

# Iniciar servidor de desarrollo
npm run dev
```

### 4. Conexión móvil con sensores (iPhone / HTTPS)

Para probar geolocalización precisa, cámara y micrófono en un dispositivo móvil bajo HTTPS:

```bash
npx cloudflared tunnel --url http://localhost:5173
```

Abre en Safari el enlace temporal generado (`*.trycloudflare.com`).

---

## 🔒 Acceso Administrativo

El panel de administración está separado de la vista del usuario final.

- **Acceso:** ícono de candado en el header superior (abre un modal).
- **Provee visualización de:**
  - Registro de auditoría de inferencias (visión vs. clima).
  - Detección de fotos válidas vs. fotos rechazadas o de interiores.
  - Métricas agregadas día con día (total de interacciones y temperaturas promedio).

---

## 📄 Licencia

Proyecto desarrollado con fines académicos y de investigación en sistemas inteligentes.
