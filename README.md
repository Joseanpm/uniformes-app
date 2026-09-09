# Sistema de Entrega e Inventario de Uniformes — versión nube

Misma app que la versión local (registro de entregas, firma digital opcional,
comprobante en PDF con folio, inventario, reportes), pero pensada para vivir
en **Streamlit Community Cloud + Supabase** — igual patrón que ya usaste para
la quiniela — en vez de correr en una sola compu por WiFi local.

Se usa cuando el equipo necesita entrar desde cualquier lugar (por ejemplo,
el analista registrando entregas desde su celular con datos móviles, no solo
conectado a la WiFi del CEDIS). Si tu caso es "siempre estamos en el mismo
CEDIS", la versión local (con SQLite, sin login) es más simple y te ahorra
todo este setup.

## Qué cambia frente a la versión local

- Los datos viven en **Supabase** (Postgres en la nube) en vez de un archivo
  SQLite — así Streamlit Cloud no pierde la información cada vez que se
  reinicia o redespliega la app.
- Tiene **login** (usuario + contraseña por persona). La versión local no lo
  necesita porque solo la ve quien está en la misma WiFi; esta sí, porque la
  URL queda en internet. El nombre de quien inicia sesión se usa para
  prellenar "Entregado por" en cada entrega — de paso, mejora la trazabilidad
  para la evidencia que le vas a mostrar al sindicato.
- La firma digital se guarda como texto (base64) en la base en vez de un
  archivo local — el comprobante en PDF sale exactamente igual.

## 1. Crear el proyecto de Supabase

1. Entra a [supabase.com](https://supabase.com) y crea un proyecto nuevo
   (gratis alcanza de sobra para este tamaño de equipo).
2. Ve a **SQL Editor** → pega el contenido completo de `schema.sql` (en esta
   carpeta) → **Run**. Esto crea todas las tablas, la vista de stock y dejan
   listo todo — es el mismo flujo que ya usaste para la quiniela (SQL Editor
   en vez de un script local, para no depender de la red de Danone).
3. Ve a **Project Settings → API** y copia dos cosas: la **URL** del
   proyecto y la llave **anon / public**.

## 2. Configurar las credenciales

Copia `.streamlit/secrets.toml.example` a `.streamlit/secrets.toml` y pon ahí
la URL y la llave que copiaste:

```toml
[supabase]
url = "https://tu-proyecto.supabase.co"
key = "tu-llave-anon-publica"
```

Ese archivo `secrets.toml` **no se sube a GitHub** (ya está en
`.gitignore`) — en Streamlit Cloud, esas mismas credenciales se agregan por
separado en **Settings → Secrets** del deploy, con este mismo formato.

Para probarlo en tu compu antes de desplegarlo:

```bash
pip install -r requirements.txt
streamlit run app.py
```

## 3. Subir el código a GitHub

Crea un repo nuevo (puede ser privado — Streamlit Community Cloud permite
desplegar desde repos privados si conectas tu cuenta de GitHub) y sube esta
carpeta completa **menos** `.streamlit/secrets.toml` (el `.gitignore` ya lo
excluye):

```bash
git init
git add .
git commit -m "Sistema de uniformes - version nube"
git branch -M main
git remote add origin https://github.com/tu-usuario/uniformes-app.git
git push -u origin main
```

## 4. Desplegar en Streamlit Community Cloud

1. Entra a [share.streamlit.io](https://share.streamlit.io) con tu cuenta de
   GitHub.
2. **New app** → elige el repo que acabas de subir, rama `main`, archivo
   principal `app.py`.
3. Antes de darle Deploy (o justo después, en **Settings → Secrets**), pega
   el mismo contenido de tu `secrets.toml`.
4. Deploy. Te va a dar una URL pública tipo
   `https://uniformes-app-xxxxx.streamlit.app` — esa es la que comparten tú y
   el analista, desde donde sea.

## 5. Primer uso

La primera vez que alguien abre la URL, como todavía no hay usuarios
configurados, la app pide crear el primer usuario ahí mismo (queda como el
administrador inicial). Después, desde la página **Usuarios** dentro de la
app, das de alta al resto del equipo (por ejemplo, al analista) sin tocar
nada de código ni la base de datos directamente.

## Seguridad — qué sí y qué no cubre esto

- La llave "anon" de Supabase está pensada para ser pública (así funcionan
  todas las apps de Supabase, incluida la quiniela) — el control de acceso
  real de esta app lo da el login que se agregó (tabla `usuarios`,
  contraseñas con hash bcrypt, nunca en texto plano).
- Esto es un login básico para un equipo chico, no un sistema de permisos
  por rol — cualquier persona que inicia sesión puede ver y hacer todo
  (incluyendo dar de alta a otros usuarios). Para este tamaño de equipo es
  razonable; si más adelante crece mucho, valdría la pena separar roles
  (por ejemplo, que el analista no pueda editar el catálogo).
- Como capa adicional (opcional, no indispensable para este tamaño), Supabase
  permite activar Row Level Security por tabla — queda como posible
  siguiente paso si algún día se necesita.

## Estructura

- `schema.sql` — todo el esquema de Postgres para pegar en el SQL Editor de
  Supabase (tablas, índices, la vista `v_stock_actual` y la tabla
  `usuarios`).
- `db.py` — capa de datos, misma interfaz que la versión local pero hablando
  con Supabase (usa el mismo patrón `sb_execute` con reintentos que ya
  usaste en la quiniela).
- `auth.py` — login: alta de usuarios, verificación de contraseña (bcrypt),
  arranque en frío (crear el primer usuario cuando la tabla está vacía).
- `app.py` — la interfaz (idéntica a la versión local, más el login y la
  página de Usuarios).
- `ticket.py` — genera el comprobante en PDF (sin cambios respecto a la
  versión local).
- `requirements.txt` — dependencias, incluyendo `supabase` y `bcrypt`.

## Ideas para siguientes iteraciones

- Row Level Security en Supabase, si el equipo crece.
- Roles (ej. "solo lectura" vs "puede registrar entregas") si hace falta
  diferenciar quién puede hacer qué.
- Las mismas ideas pendientes de la versión local: editar stock mínimo desde
  la interfaz, alertas automáticas de reabastecimiento, evidencia
  fotográfica adicional, reporte de cumplimiento consolidado para el
  sindicato.
