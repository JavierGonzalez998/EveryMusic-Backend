# em-back

Backend de una app de streaming de audio/música construido con **FastAPI**. Los usuarios suben audio (`.mp3`, `.flac`, `.wav`), se extraen sus metadatos, se almacena en un bucket S3-compatible y se reproduce en vivo vía URLs prefirmadas. Incluye autenticación JWT, playlists, favoritos, historial, búsqueda, y vinculación de un gadget físico de reproducción.

---

## Stack

| Capa | Tecnología |
|------|-----------|
| Framework | FastAPI + Uvicorn |
| ORM / modelos | SQLModel (sobre SQLAlchemy 2) |
| Base de datos | MySQL (driver PyMySQL) |
| Migraciones | Alembic |
| Almacenamiento | boto3 → bucket S3-compatible (Railway) |
| Auth | JWT (PyJWT) + bcrypt |
| Metadatos de audio | mutagen |
| Config | pydantic-settings |
| Rate limiting | slowapi |
| Emails | smtplib (stdlib) |
| Tests | pytest (SQLite en memoria) |

---

## Estructura del proyecto

```
em-back/
├─ main.py                 # App FastAPI: CORS, error handler global, Sentry, monta routers
├─ config.py               # Settings centralizado (pydantic-settings), fail-fast de vars requeridas
├─ db.py                   # Engine SQLAlchemy + dependencia get_session
├─ storage.py              # Cliente S3 (upload / delete / presigned_url)
├─ models.py               # Tablas SQLModel
├─ ratelimit.py            # Limiter compartido (slowapi)
├─ email_util.py           # Envío de email (o log si no hay SMTP)
├─ controller/
│  ├─ auth/auth.py         # bcrypt, JWT (access/refresh/verify/reset), get_current_user
│  ├─ users/router.py      # registro, login, perfil, verificación y reset de password
│  ├─ files/router.py      # subida, listado, búsqueda, play, cover, favoritos, historial
│  ├─ playlists/router.py  # CRUD de playlists + compartir público/privado
│  └─ devices/router.py    # vinculación del gadget físico (pairing)
├─ alembic/                # Migraciones (fuente única de verdad del esquema)
├─ tests/                  # Suite pytest (SQLite + storage mockeado)
├─ Dockerfile
└─ .github/workflows/ci.yml
```

La lógica de negocio vive en `controller/` separada por área. `db.py`, `models.py`, `storage.py`, `config.py` son infraestructura/datos en la raíz.

---

## Puesta en marcha

### 1. Requisitos
- Python 3.13
- Una base MySQL accesible
- Un bucket S3-compatible con credenciales

### 2. Instalar dependencias

```powershell
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
```

### 3. Variables de entorno

Copia `.env.example` a `.env` y completa los valores:

```ini
# Base de datos (requerido)
MYSQL_URL=mysql://user:pass@host:port/db

# Bucket (requerido)
AWS_ENDPOINT_URL=https://...
AWS_S3_BUCKET_NAME=mi-bucket
AWS_DEFAULT_REGION=auto
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...

# Auth (requerido — la app no arranca sin esto)
JWT_SECRET=<cadena aleatoria de ≥32 bytes>

# CORS (opcional, default *)
ALLOWED_ORIGINS=https://mi-frontend.com,https://otro.com

# Observabilidad (opcional)
SENTRY_DSN=

# Email (opcional; sin SMTP, los links de verificación/reset se loguean)
APP_BASE_URL=https://mi-app.com
SMTP_HOST=
SMTP_PORT=587
SMTP_USER=
SMTP_PASSWORD=
SMTP_FROM=
```

> `MYSQL_URL`, `AWS_S3_BUCKET_NAME`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` y `JWT_SECRET` son **obligatorios**: si falta alguno, la app falla al iniciar (fail-fast).

### 4. Aplicar migraciones

```powershell
.venv\Scripts\alembic upgrade head
```

### 5. Levantar la app

```powershell
.venv\Scripts\fastapi dev main.py
```

Documentación interactiva en **http://localhost:8000/docs**.

---

## Autenticación

- **Registro / login** devuelven un `access_token` (12 h) y un `refresh_token` (30 días).
- Endpoints protegidos esperan el header `Authorization: Bearer <access_token>`.
- Los tokens llevan claims `type` (access/refresh/verify/reset) y `ver` (versión). El **logout** o el **cambio/reset de password** incrementan `token_version`, invalidando *todos* los tokens emitidos.
- Las contraseñas se guardan hasheadas con **bcrypt** (nunca en texto plano).

---

## Endpoints

### Auth / usuarios
| Método | Ruta | Auth | Descripción |
|--------|------|------|-------------|
| POST | `/register` | — | Crear usuario (rate 10/min) |
| POST | `/login` | — | Obtener access + refresh (rate 5/min) |
| POST | `/refresh` | — | Renovar tokens con un refresh token |
| POST | `/logout` | ✔ | Revocar todas las sesiones |
| GET | `/users/me` | ✔ | Datos del usuario actual |
| PATCH | `/users/me` | ✔ | Editar nombre/nickname/email/password |
| POST | `/auth/request-verify` | ✔ | Enviar email de verificación |
| POST | `/auth/verify` | — | Confirmar email con token |
| POST | `/auth/request-password-reset` | — | Pedir reset (rate 5/min, no filtra existencia) |
| POST | `/auth/reset-password` | — | Setear nueva contraseña con token |

### Archivos de audio
| Método | Ruta | Auth | Descripción |
|--------|------|------|-------------|
| POST | `/files` | ✔ | Subir audio (máx 50 MB/archivo, cuota 600 MB/usuario) |
| GET | `/files` | ✔ | Listar mi biblioteca (paginado) |
| GET | `/files/{id}` | ✔ | Un archivo + metadatos |
| DELETE | `/files/{id}` | ✔ | Borrar (limpia bucket, metadata, playlists, favoritos, historial) |
| GET | `/files/{id}/play` | ✔ | URL prefirmada para reproducir (soporta Range); registra historial |
| GET | `/files/{id}/cover` | ✔ | URL prefirmada de la carátula (si tiene) |
| GET | `/search?q=` | ✔ | Buscar en título/artista/álbum (solo lo propio) |
| GET | `/history` | ✔ | Historial de reproducción |
| GET | `/favorites` | ✔ | Listar favoritos |
| POST | `/files/{id}/favorite` | ✔ | Marcar favorito (idempotente) |
| DELETE | `/files/{id}/favorite` | ✔ | Quitar favorito |

### Playlists
| Método | Ruta | Auth | Descripción |
|--------|------|------|-------------|
| POST | `/playlists` | ✔ | Crear playlist |
| GET | `/playlists` | ✔ | Listar mis playlists |
| GET | `/playlists/{id}` | ✔* | Ver playlist + tracks ordenados (*público si `is_public`) |
| PATCH | `/playlists/{id}` | ✔ | Renombrar / cambiar visibilidad |
| POST | `/playlists/{id}/files` | ✔ | Agregar canciones (asigna orden) |
| DELETE | `/playlists/{id}/files/{idFile}` | ✔ | Quitar una canción |
| DELETE | `/playlists/{id}` | ✔ | Borrar playlist |

### Dispositivos (gadget físico)
| Método | Ruta | Auth | Descripción |
|--------|------|------|-------------|
| POST | `/devices/register` | — | El gadget obtiene código + secreto (rate 10/min) |
| POST | `/devices/link` | ✔ | El usuario vincula el dispositivo con el código |
| POST | `/devices/auth` | — | El gadget canjea su secreto por un access token (425 si no vinculado) |
| GET | `/devices` | ✔ | Listar mis dispositivos |
| DELETE | `/devices/{id}` | ✔ | Desvincular/revocar |

### Utilidad
| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | `/` | Saludo |
| GET | `/health/db` | Liveness de la base |

---

## Vinculación del gadget (pairing)

Flujo estilo smart-TV para un dispositivo físico de reproducción:

1. El gadget llama a `POST /devices/register` → recibe un **código** y un **secreto** de larga vida (el secreto se guarda hasheado).
2. El gadget muestra el código; el usuario lo ingresa en su app con `POST /devices/link`.
3. El gadget hace polling a `POST /devices/auth`; mientras no esté vinculado responde `425`, y una vez vinculado devuelve un **access token del usuario**.
4. Con ese token el gadget usa todos los endpoints de reproducción como si fuera el usuario.
5. `DELETE /devices/{id}` revoca el dispositivo (ya no puede renovar tokens).

---

## Modelo de datos

| Tabla | Descripción |
|-------|-------------|
| `users` | Usuarios (email único, password bcrypt, `token_version`, `email_verified`) |
| `files` | Archivos de audio (`ext`, `uploaded_by`, `size`, `has_cover`) |
| `metadata` | Metadatos por archivo (título, artista, álbum, duración, fecha) |
| `playlists` | Playlists (`created_by`, `is_public`) |
| `playlist_files` | Junction playlist↔archivo con `position` (orden) |
| `favorites` | Favoritos (usuario↔archivo) |
| `play_events` | Historial de reproducción |
| `devices` | Dispositivos físicos vinculados |

- PKs UUID (`CHAR(36)`). `created_at`/`updated_at` los gestiona la BD (`server_default`/`onupdate`).
- Objetos en el bucket con la clave `{idUser}/{idFile}.{ext}` (y `{idUser}/{idFile}.cover` para carátulas).

---

## Migraciones

```powershell
# Tras cambiar models.py
.venv\Scripts\alembic revision --autogenerate -m "descripcion"
.venv\Scripts\alembic upgrade head

# Utilidades
.venv\Scripts\alembic current    # revisión aplicada
.venv\Scripts\alembic history    # historial
.venv\Scripts\alembic check      # detectar drift modelo↔esquema
.venv\Scripts\alembic downgrade -1
```

Alembic reutiliza el `engine` y `SQLModel.metadata` de la app (fuente única de verdad). `autogenerate` no detecta renombres de columna (los ve como drop+add) — revisa siempre el script generado.

---

## Tests

```powershell
.venv\Scripts\pytest -q
```

Corren sobre **SQLite en memoria** con el storage mockeado y el rate-limiter desactivado, así que no requieren MySQL ni bucket reales (ni secretos). Cubren auth/refresh/logout, subida y validaciones, cuota, ownership, borrado con cascada, playlists y orden, compartir, favoritos, historial, carátulas, verificación/reset de email y pairing de dispositivos.

---

## Despliegue

- **Dockerfile** — instala dependencias, aplica migraciones y arranca uvicorn (usa la variable `PORT`).
- **CI** (`.github/workflows/ci.yml`) — corre `pytest` en cada push/PR.

```powershell
docker build -t em-back .
docker run --env-file .env -p 8000:8000 em-back
```

---

## Notas y límites conocidos

- Subida: máx **50 MB por archivo**, cuota **600 MB por usuario** (413 al exceder). La cuota cuenta bytes de audio, no las carátulas.
- El historial ordena por `played_at` con granularidad de segundo: reproducciones en el mismo segundo no tienen orden garantizado entre sí.
- Rate limiting en memoria (un proceso). Para multi-worker, apuntar el store de slowapi a Redis.
- `JWT_SECRET` no tiene fallback: es obligatorio en todos los entornos.
