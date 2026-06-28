# Bot TL - Backend de búsqueda de desaparecidos

Backend en Python para un bot de Telegram que permite buscar personas en listas públicas de desaparecidos.

## Stack

- Python 3.11+
- FastAPI
- SQLAlchemy + Alembic
- PostgreSQL (Postgres.app recomendado en macOS)
- python-telegram-bot
- BeautifulSoup, httpx, rapidfuzz

## Requisitos previos

- Python 3.11 o superior
- PostgreSQL en ejecución (Postgres.app puerto **5435** en este entorno)

## Instalación local

```bash
cd bot-tl

python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

pip install -r requirements-dev.txt
cp .env.example .env
```

## PostgreSQL local

Este proyecto usa **Postgres.app** en el puerto **5435**:

| Campo | Valor |
|-------|-------|
| Host | `localhost` |
| Puerto | `5435` |
| Usuario | `bot_tl` |
| Contraseña | `bot_tl_dev` |
| Base de datos | `missing_people_bot` |

Ejemplo de `.env`:

```env
DATABASE_URL=postgresql+psycopg2://bot_tl:bot_tl_dev@localhost:5435/missing_people_bot
TELEGRAM_BOT_TOKEN=tu_token_aqui
APP_ENV=local
```

Alembic lee `DATABASE_URL` desde `app/config.py`.

## Migraciones Alembic

```bash
alembic upgrade head
```

Para regenerar cambios en modelos:

```bash
alembic revision --autogenerate -m "descripcion del cambio"
alembic upgrade head
```

## Cargar / sincronizar datos

Scraper estático de prueba:

```bash
python -m app.scrapers.example_static_scraper
```

Scraper HTML de ejemplo (BeautifulSoup):

```bash
python -m app.scrapers.example_html_scraper
```

Ejecutar **todos** los scrapers:

```bash
python -m app.scrapers.sync
```

## Ejecutar la API

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Verificar salud:

```bash
curl http://localhost:8000/health
# {"status":"ok","database":"connected"}
```

Buscar por nombre o cédula:

```bash
curl "http://localhost:8000/search?q=Juan"
curl "http://localhost:8000/search?q=12345678"
curl "http://localhost:8000/search?q=Mar%C3%ADa"
```

Documentación interactiva: http://localhost:8000/docs

## Ejecutar el bot de Telegram

Configura `TELEGRAM_BOT_TOKEN` en `.env`, luego:

```bash
python -m app.bot.telegram_bot
```

El bot responde a `/start` y a cualquier mensaje de texto con un nombre o cédula.

## Seguridad de datos

La cédula **nunca** se almacena ni retorna en texto plano. El sistema guarda:

- `document_id_hash`: SHA-256 del número normalizado (solo dígitos)
- `document_id_last4`: últimos 4 dígitos para referencia parcial
- `raw_data`: se sanitiza al persistir; no incluye la cédula completa

## Prueba end-to-end local

Ejecuta estos pasos en orden para validar todo el flujo:

```bash
source .venv/bin/activate

# 1. Migraciones
alembic upgrade head

# 2. Cargar datos de prueba (ejecutar dos veces: no debe duplicar personas)
python -m app.scrapers.example_static_scraper
python -m app.scrapers.example_static_scraper

# 3. Levantar API
uvicorn app.main:app --reload
```

En otra terminal:

```bash
# 4. Health check
curl http://localhost:8000/health
# → {"status":"ok","database":"connected"}

# 5. Búsqueda por nombre
curl "http://localhost:8000/search?q=Juan"
# → matches[0].full_name = "Juan Carlos Pérez"

# 6. Búsqueda por cédula (hash interno, respuesta enmascarada)
curl "http://localhost:8000/search?q=12345678"
# → query = "***5678", matches[0].document_id_last4 = "5678"
# → nunca aparece "12345678" en la respuesta

# 7. Bot Telegram (misma lógica SearchService que la API)
python -m app.bot.telegram_bot
# En Telegram escribe: Juan  o  12345678
```

**Resultados esperados:**

| Paso | Verificación |
|------|--------------|
| Alembic | Tablas `persons`, `sources`, `appearances` creadas |
| Scraper x2 | 1 sola fila para Juan Carlos Pérez (sin duplicados) |
| `/search?q=Juan` | Retorna Juan Carlos Pérez con fuentes |
| `/search?q=12345678` | Match exacto por hash, query enmascarada |
| Bot | Mismos resultados que la API, cédula como `***5678` |

## Criterios de normalización y confianza (Fase 6.5)

### Documentos aceptados

Formatos soportados en búsqueda y scrapers:

- `12345678`
- `V12345678` / `V-12345678`
- `12.345.678`
- `C.I. 12345678`

Se extraen solo dígitos para el hash SHA-256. En respuestas y `raw_data` solo se expone `document_id_last4`.

### Nombres

- Se conserva `full_name` original en resultados.
- `normalized_name` quita acentos, convierte `ñ → n`, colapsa espacios y elimina caracteres raros.

### Confidence score

| Tipo de match | Score |
|---------------|-------|
| Cédula exacta (hash) | 100 |
| Nombre exacto normalizado | 95 |
| Nombre parcial (substring) | 80 |
| Fuzzy ≥ 90 | score del fuzzy |
| Fuzzy < 80 | no se muestra |

La API retorna hasta **10** resultados; el bot muestra máximo **5**, ordenados por `confidence_score` descendente.

### Status en Appearance

Valores permitidos: `missing`, `found`, `hospital`, `shelter`, `unknown`  
(alias en español se normalizan automáticamente, ej. `desaparecido` → `missing`).

### Tests

```bash
pip install -r requirements-dev.txt
pytest tests/ -v
```

## Estructura del proyecto

```
app/
  main.py              # FastAPI: /health, /search
  config.py            # Settings desde .env
  database.py          # Engine y sesión SQLAlchemy
  models/              # Person, Source, Appearance
  schemas/             # DTOs de búsqueda
  services/            # Lógica de búsqueda y normalización
  scrapers/            # BaseScraper, HttpScraper, scrapers concretos
  bot/                 # Bot de Telegram
alembic/               # Migraciones
```

## Relaciones

- `Person` → muchas `Appearance`
- `Source` → muchas `Appearance`
- `Appearance` → pertenece a `Person` y `Source`

## Próximos pasos

- Programar `python -m app.scrapers.sync` con cron o scheduler
- Ampliar `REDAYUDA_MAX_RECORDS` para sincronizar más registros (~117k disponibles)

## Fuentes externas Supabase (Fase 7)

Las fuentes públicas se consultan **en vivo** como proveedores de búsqueda.  
No se enumera la base completa ni se usa `service_role`.

| Fuente | Página | Mecanismo |
|--------|--------|-----------|
| [Red Ayuda Venezuela](https://redayudavenezuela.com/buscar) | `/buscar` | RPC `search_people` con `{"q": "..."}` |
| [Emergencia Joch.dev](https://emergencia.joch.dev/) | portal | Filtros PostgREST `ilike` acotados |
| [Localizados Venezuela](https://localizadosvenezuela.com) | portal | `GET /api/v1/localizados?q=...&page=1&limit=10` |
| [Desaparecidos Terremoto Venezuela](https://desaparecidosterremotovenezuela.com/) | portal | `GET /api/personas?page=1&pageSize=10&q=...` |
| [Venezuela Te Busca](https://venezuelatebusca.com) | portal | `GET /_root.data?query=...` |

**Localizados Venezuela** registra personas **ya localizadas** (status `found`), no desaparecidas.  
**Desaparecidos Terremoto Venezuela** consulta personas reportadas en el terremoto; búsqueda acotada por query (solo page=1, sin dump masivo).  
**Venezuela Te Busca** usa un endpoint interno de datos del frontend, por lo que puede cambiar. Se consulta solo por búsqueda del usuario y no se recorre masivamente.

Solo búsqueda acotada por query; no usa rutas `_rsc` ni scraping HTML.

### Obtener anon key (Network tab)

1. Abre la página en Chrome/Firefox → DevTools → **Network**.
2. Busca una persona de prueba.
3. Localiza la petición a `*.supabase.co`.
4. Copia:
   - URL base (`https://xxxx.supabase.co`)
   - Header `apikey` (solo clave **anon/publishable** del frontend)
5. **Nunca** uses `service_role` ni endpoints admin.

### Configuración `.env`

```env
ENABLE_EXTERNAL_SOURCES=true
ENABLE_RED_AYUDA_VENEZUELA=true
ENABLE_EMERGENCIA_JOCH=true
RED_AYUDA_SUPABASE_URL=https://cpavwkdonvkvrwygfzfo.supabase.co
RED_AYUDA_SUPABASE_ANON_KEY=tu_anon_key
EMERGENCIA_JOCH_SUPABASE_URL=https://pczsfbreefbtogmzigjw.supabase.co
EMERGENCIA_JOCH_SUPABASE_ANON_KEY=tu_publishable_key

ENABLE_LOCALIZADOS_VENEZUELA=true
LOCALIZADOS_VENEZUELA_BASE_URL=https://localizadosvenezuela.com

ENABLE_DESAPARECIDOS_TERREMOTO_VENEZUELA=true
DESAPARECIDOS_TERREMOTO_BASE_URL=https://desaparecidos-terremoto-api.theempire.tech
DESAPARECIDOS_TERREMOTO_PUBLIC_URL=https://desaparecidosterremotovenezuela.com

ENABLE_VENEZUELA_TE_BUSCA=true
VENEZUELA_TE_BUSCA_BASE_URL=https://venezuelatebusca.com
```

### Comportamiento

- `SearchService` consulta **DB local primero**.
- Si `ENABLE_EXTERNAL_SOURCES=true`, consulta fuentes externas con el mismo query.
- Rate limit local: **1 req/s** por fuente, timeout **10s**, **1 reintento**.
- No se guarda cédula completa, teléfono, contacto ni ubicación exacta.

### Advertencia ética

- No enumerar tablas completas si la fuente está diseñada para búsqueda.
- No intentar bypass de RLS ni datos privados.
- Verificar siempre en el enlace original de la fuente.

### Tests

```bash
pytest tests/test_external_sources.py tests/test_localizados_venezuela_source.py tests/test_desaparecidos_terremoto_source.py -v
```

## Fase 8 — Seguridad y uso público

- Rate limit Telegram: **10 búsquedas / 5 min** por usuario (memoria local).
- Validación de query: nombre ≥ 3 chars, cédula ≥ 5 dígitos, bloqueo de consultas genéricas.
- Logs enmascarados para cédulas (`***5678`).
- Endpoint `GET /sources/health` (sin exponer keys).
- Bot sin `raw_data` ni cédula completa en respuestas.

```bash
curl http://localhost:8000/sources/health
pytest tests/test_phase8_hardening.py -v
```

## Scrapers legacy (solo pruebas locales)

Los scrapers en `app/scrapers/` siguen disponibles para fixtures, pero **no** deben usarse para volcado masivo de fuentes públicas de búsqueda.

```bash
python -m app.scrapers.example_static_scraper
python -m app.scrapers.sync
```

## Deploy en Railway (Fase 9)

Arquitectura recomendada: **dos servicios** en el mismo proyecto Railway:

| Servicio | Comando de inicio | Rol |
|----------|-------------------|-----|
| **API** | `uvicorn app.main:app --host 0.0.0.0 --port $PORT` | FastAPI público |
| **Bot** | `python -m app.bot.telegram_bot` | Worker Telegram (polling) |

También documentado en `Procfile` (`web` / `worker`).

### Requisitos

- Python **3.11** (`runtime.txt`)
- PostgreSQL (plugin Railway)
- Variables de entorno (ver abajo)

### Paso 1 — Crear proyecto en Railway

1. Entra en [railway.app](https://railway.app) y crea un **New Project**.
2. Conecta este repositorio (GitHub) o despliega con Railway CLI.

### Paso 2 — Agregar PostgreSQL

1. En el proyecto: **Add Service → Database → PostgreSQL**.
2. Railway crea `DATABASE_URL` automáticamente (formato `postgresql://...`).
3. La app normaliza a `postgresql+psycopg2://...` en `app/config.py` — no hace falta editarla a mano.

### Paso 3 — Configurar variables de entorno

En el servicio **API**, agrega (o comparte desde el proyecto):

```env
APP_ENV=production
DATABASE_URL=${{Postgres.DATABASE_URL}}
TELEGRAM_BOT_TOKEN=tu_token_de_botfather

ENABLE_EXTERNAL_SOURCES=true
ENABLE_RED_AYUDA_VENEZUELA=true
ENABLE_EMERGENCIA_JOCH=true
ENABLE_LOCALIZADOS_VENEZUELA=true
ENABLE_DESAPARECIDOS_TERREMOTO_VENEZUELA=true
ENABLE_VENEZUELA_TE_BUSCA=true

RED_AYUDA_SUPABASE_URL=https://cpavwkdonvkvrwygfzfo.supabase.co
RED_AYUDA_SUPABASE_ANON_KEY=tu_anon_key
EMERGENCIA_JOCH_SUPABASE_URL=https://pczsfbreefbtogmzigjw.supabase.co
EMERGENCIA_JOCH_SUPABASE_ANON_KEY=tu_publishable_key

LOCALIZADOS_VENEZUELA_BASE_URL=https://localizadosvenezuela.com
DESAPARECIDOS_TERREMOTO_BASE_URL=https://desaparecidos-terremoto-api.theempire.tech
DESAPARECIDOS_TERREMOTO_PUBLIC_URL=https://desaparecidosterremotovenezuela.com
VENEZUELA_TE_BUSCA_BASE_URL=https://venezuelatebusca.com
```

**Nunca** subas `.env` al repo. Usa el panel de Railway o secrets compartidos.

El servicio **Bot** necesita al menos:

```env
APP_ENV=production
DATABASE_URL=${{Postgres.DATABASE_URL}}
TELEGRAM_BOT_TOKEN=tu_token_de_botfather
ENABLE_EXTERNAL_SOURCES=true
# ... mismas flags de fuentes que la API si el bot consulta externas
```

### Paso 4 — Deploy del servicio API

1. Crea un servicio desde el repo (o duplica el existente).
2. **Start Command**:

```bash
uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

3. Railway detecta `requirements.txt` y `runtime.txt` (Nixpacks).
4. Genera dominio público: **Settings → Networking → Generate Domain**.

### Paso 5 — Crear worker del Bot

1. **Add Service → GitHub Repo** (mismo repo).
2. **Start Command**:

```bash
python -m app.bot.telegram_bot
```

3. Comparte `DATABASE_URL`, `TELEGRAM_BOT_TOKEN` y flags de fuentes con la API.
4. No expone puerto HTTP; solo ejecuta polling de Telegram.

### Paso 6 — Migraciones Alembic

Ejecuta **una vez** después del primer deploy (Railway shell o job one-off):

```bash
alembic upgrade head
```

Alternativa:

```bash
python -m app.scripts.run_migrations
```

Ambos usan `DATABASE_URL` normalizada desde `app/config.py`.

### Paso 7 — Probar endpoints (smoke tests)

Reemplaza `TU_API` por tu dominio Railway:

```bash
curl https://TU_API.railway.app/health
# → {"status":"ok","database":"connected"}

curl https://TU_API.railway.app/sources/health
# → {"sources":[...]}

curl "https://TU_API.railway.app/search?q=maria+perez"
# → {"query":"maria perez","matches":[...]}
```

### Paso 8 — Probar Telegram

1. Abre el bot en Telegram.
2. Envía `/start` y una búsqueda (`Juan Pérez` o cédula).
3. Verifica logs del worker: consultas enmascaradas (`***5678`), sin tokens ni keys.

### Comandos útiles

| Acción | Comando |
|--------|---------|
| API local (prod-like) | `uvicorn app.main:app --host 0.0.0.0 --port 8000` |
| Bot local | `python -m app.bot.telegram_bot` |
| Migraciones | `alembic upgrade head` |
| Migraciones (script) | `python -m app.scripts.run_migrations` |
| Tests | `pip install -r requirements-dev.txt && pytest` |

### Logs y seguridad en producción

- `mask_query_for_log` se usa en API (`/search`), `SearchService` y bot Telegram.
- Cédulas completas **no** aparecen en logs; solo `***last4`.
- `/sources/health` no expone anon keys ni tokens.
- No loguees `TELEGRAM_BOT_TOKEN`, `RED_AYUDA_SUPABASE_ANON_KEY` ni `EMERGENCIA_JOCH_SUPABASE_ANON_KEY`.

### Health checks

| Endpoint | Uso |
|----------|-----|
| `GET /health` | Liveness + conexión PostgreSQL |
| `GET /sources/health` | Estado de fuentes externas (sin secrets) |

Configura Railway health check del servicio API contra `/health`.

## Telegram webhook en Render Free (Fase 10)

En Render **Free** no hay Background Worker de pago. El bot corre **dentro del mismo Web Service** vía webhook.

**API en producción:** https://red-de-encuentro-api.onrender.com

### Arquitectura

| Componente | Rol |
|------------|-----|
| Web Service Render | FastAPI + `POST /telegram/webhook` |
| Telegram | Envía updates al webhook |
| Polling (`telegram_bot.py`) | **Solo desarrollo local** |

**Start Command (Render):**

```bash
uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

No levantar polling en producción.

### Variables de entorno (Render)

```env
APP_ENV=production
DATABASE_URL=...   # desde PostgreSQL de Render
TELEGRAM_BOT_TOKEN=tu_token_de_botfather
PUBLIC_BASE_URL=https://red-de-encuentro-api.onrender.com
ADMIN_SECRET=un_secreto_largo_y_aleatorio

ENABLE_EXTERNAL_SOURCES=true
# ... resto de flags de fuentes (igual que local)
```

### Paso 1 — Deploy del Web Service

1. Conecta el repo en Render.
2. Start Command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
3. Agrega PostgreSQL y variables de entorno.
4. Corre migraciones: `python -m app.scripts.run_migrations`

### Paso 2 — Registrar webhook en Telegram

**Opción A — Desde tu máquina (si tienes `.env` con token):**

```bash
python -m app.scripts.set_telegram_webhook
```

**Opción B — Sin shell en Render (endpoint admin):**

```bash
curl -X POST "https://red-de-encuentro-api.onrender.com/admin/telegram/set-webhook" \
  -H "X-Admin-Secret: TU_ADMIN_SECRET" \
  -H "Content-Type: application/json" \
  -d '{}'
```

O con URL explícita:

```bash
curl -X POST "https://red-de-encuentro-api.onrender.com/admin/telegram/set-webhook" \
  -H "X-Admin-Secret: TU_ADMIN_SECRET" \
  -H "Content-Type: application/json" \
  -d '{"webhook_url":"https://red-de-encuentro-api.onrender.com/telegram/webhook"}'
```

Eliminar webhook:

```bash
curl -X POST "https://red-de-encuentro-api.onrender.com/admin/telegram/delete-webhook" \
  -H "X-Admin-Secret: TU_ADMIN_SECRET"
```

O localmente: `python -m app.scripts.delete_telegram_webhook`

### Paso 3 — Verificar

```bash
curl https://red-de-encuentro-api.onrender.com/telegram/status
# → {"mode":"webhook","configured":true}
```

Luego escribe al bot en Telegram: `/start` y una búsqueda.

### Endpoints Telegram

| Método | Ruta | Descripción |
|--------|------|-------------|
| `POST` | `/telegram/webhook` | Recibe updates de Telegram |
| `GET` | `/telegram/status` | Modo webhook + si hay token configurado |
| `POST` | `/admin/telegram/set-webhook` | Registra webhook (requiere `X-Admin-Secret`) |
| `POST` | `/admin/telegram/delete-webhook` | Elimina webhook (requiere `X-Admin-Secret`) |

### Seguridad

- Sin `ADMIN_SECRET`, los endpoints `/admin/telegram/*` responden **404**.
- Nunca expongas `TELEGRAM_BOT_TOKEN` ni `ADMIN_SECRET` en logs o respuestas.
- Las búsquedas en logs usan `mask_query_for_log`.

### Desarrollo local

Polling solo para pruebas locales:

```bash
python -m app.bot.telegram_bot
```

## Private analytics (Fase 11)

Estadísticas privadas de uso del bot y la API. Solo visibles con `ADMIN_SECRET`.

### Qué se registra

Cada búsqueda en `search_logs` guarda:

- fuente (`telegram` / `api`)
- query enmascarada (`maria perez` o `***5678`)
- hash de query y de usuario (sin IDs reales ni IPs)
- resultados, tiempo de respuesta, éxito/error

**No se guarda:** query completa, cédula completa, telegram ID, IP, tokens.

### Migración

```bash
alembic upgrade head
# o
python -m app.scripts.run_migrations
```

### Consultar stats (solo admin)

```bash
curl "https://red-de-encuentro-api.onrender.com/admin/stats?days=7" \
  -H "X-Admin-Secret: TU_ADMIN_SECRET"
```

Respuesta ejemplo:

```json
{
  "period_days": 7,
  "total_searches": 120,
  "unique_users": 45,
  "telegram_searches": 90,
  "api_searches": 30,
  "successful_searches": 100,
  "empty_results": 20,
  "average_response_ms": 850,
  "top_queries": [{"query": "maria perez", "count": 12}],
  "searches_by_day": [{"date": "2026-06-27", "count": 44}]
}
```

Sin `ADMIN_SECRET` configurado, `/admin/stats` responde **404**.

## Private dashboard (Fase 12)

Panel visual privado con gráficos de uso.

```
https://red-de-encuentro-api.onrender.com/admin/dashboard?secret=TU_ADMIN_SECRET
```

También disponible:

- `GET /admin/dashboard-data?days=7&secret=TU_ADMIN_SECRET` → JSON
- Header alternativo: `X-Admin-Secret: TU_ADMIN_SECRET`

Muestra totales, usuarios únicos, Telegram vs API, top consultas enmascaradas, búsquedas por día y errores recientes. Sin exponer tokens, IPs, IDs de Telegram ni cédulas completas.
