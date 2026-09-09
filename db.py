"""
Capa de datos del Sistema de Entrega e Inventario de Uniformes — versión Supabase.

Misma interfaz (mismas funciones, mismos nombres) que la versión local que corre
con SQLite, pero hablando con Supabase (Postgres + PostgREST) para poder vivir en
Streamlit Community Cloud y que el analista lo use desde su celular con datos
móviles, sin depender de una compu prendida en el CEDIS.

Sigue el mismo patrón que ya se usó en la quiniela (sb_execute con reintentos).
Necesita, en `st.secrets` (o variables de entorno SUPABASE_URL / SUPABASE_KEY):

    [supabase]
    url = "https://xxxxxxxx.supabase.co"
    key = "la-llave-anon-de-tu-proyecto"
"""

from __future__ import annotations

import base64
import os
import re
import time
import unicodedata
from datetime import datetime

from supabase import Client, create_client

MOTIVOS_ENTREGA = [
    "Nuevo ingreso",
    "Reposición por desgaste",
    "Cambio de talla",
    "Reposición por pérdida",
    "Otro",
]

TIPOS_TALLA = {
    "Ropa (XS-XXL)": ["XS", "S", "M", "L", "XL", "XXL"],
    "Calzado (numérico)": [str(n) for n in range(22, 31)],
    "Única": ["Única"],
}


# ---------------------------------------------------------------------------
# Conexión
# ---------------------------------------------------------------------------

_client: Client | None = None


def _leer_credenciales() -> tuple[str, str]:
    """Busca la URL/llave de Supabase primero en st.secrets, luego en variables
    de entorno — así el mismo código sirve corriendo en Streamlit Cloud o en
    local para pruebas."""
    try:
        import streamlit as st
        if "supabase" in st.secrets:
            return st.secrets["supabase"]["url"], st.secrets["supabase"]["key"]
    except Exception:
        pass
    url = os.environ.get("SUPABASE_URL", "")
    key = os.environ.get("SUPABASE_KEY", "")
    if not url or not key:
        raise RuntimeError(
            "Faltan las credenciales de Supabase. Agrega [supabase] url/key en "
            "st.secrets (Streamlit Cloud → Settings → Secrets) o define las "
            "variables de entorno SUPABASE_URL y SUPABASE_KEY."
        )
    return url, key


def get_client() -> Client:
    global _client
    if _client is None:
        url, key = _leer_credenciales()
        _client = create_client(url, key)
    return _client


def sb_execute(query, reintentos: int = 3, espera: float = 0.6):
    """Ejecuta una consulta de supabase-py con reintentos — la red corporativa
    de Danone (o cualquier red inestable) puede cortar la primera llamada; este
    es el mismo patrón sb_execute que ya se usó en la quiniela."""
    ultimo_error = None
    for intento in range(reintentos):
        try:
            return query.execute()
        except Exception as e:  # noqa: BLE001 - queremos capturar cualquier error de red
            ultimo_error = e
            if intento < reintentos - 1:
                time.sleep(espera * (intento + 1))
    raise ultimo_error


def init_db():
    """No crea tablas (eso lo hace schema.sql en el SQL Editor de Supabase);
    solo se asegura de que exista la fila de config por default."""
    sb = get_client()
    existente = sb_execute(sb.table("config").select("clave").eq("clave", "cedis")).data
    if not existente:
        sb_execute(sb.table("config").insert({"clave": "cedis", "valor": "CEDIS Mérida ONE"}))


def folio_entrega(entrega_id: int) -> str:
    cedis = get_config("cedis", "CEDIS")
    letras = unicodedata.normalize("NFKD", cedis).encode("ascii", "ignore").decode("ascii")
    codigo = "".join(w[0] for w in letras.split()[:3]).upper() or "UNI"
    return f"UNIF-{codigo}-{entrega_id:06d}"


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

def get_config(clave: str, default: str = "") -> str:
    sb = get_client()
    data = sb_execute(sb.table("config").select("valor").eq("clave", clave)).data
    return data[0]["valor"] if data else default


def set_config(clave: str, valor: str):
    sb = get_client()
    sb_execute(sb.table("config").upsert({"clave": clave, "valor": valor}))


# ---------------------------------------------------------------------------
# Catálogo: prendas y variantes (talla)
# ---------------------------------------------------------------------------

def listar_prendas(solo_activas: bool = True):
    sb = get_client()
    q = sb.table("prendas").select("*")
    if solo_activas:
        q = q.eq("activo", True)
    return sb_execute(q.order("nombre")).data


def crear_prenda(nombre: str, categoria: str, tipo_talla: str, stock_minimo_default: int = 0,
                  tallas: list[str] | None = None):
    sb = get_client()
    prenda = sb_execute(sb.table("prendas").insert({
        "nombre": nombre, "categoria": categoria, "tipo_talla": tipo_talla,
        "stock_minimo_default": stock_minimo_default,
    })).data[0]
    prenda_id = prenda["id"]
    tallas = tallas if tallas is not None else TIPOS_TALLA.get(tipo_talla, [])
    if tallas:
        filas = [{"prenda_id": prenda_id, "talla": t, "stock_minimo": stock_minimo_default} for t in tallas]
        sb_execute(sb.table("variantes").upsert(filas, on_conflict="prenda_id,talla"))
    return prenda_id


DEFAULT_CATALOGO = [
    ("Camisa uniforme", "Ropa superior", "Ropa (XS-XXL)", 5),
    ("Pantalón uniforme", "Ropa inferior", "Ropa (XS-XXL)", 5),
    ("Chaleco/Chamarra", "Ropa superior", "Ropa (XS-XXL)", 3),
    ("Botas de seguridad", "Calzado", "Calzado (numérico)", 3),
    ("Gorra", "Accesorio", "Única", 5),
]


def seed_catalogo_default():
    if listar_prendas(solo_activas=False):
        return 0
    for nombre, categoria, tipo_talla, stock_min in DEFAULT_CATALOGO:
        crear_prenda(nombre, categoria, tipo_talla, stock_min)
    return len(DEFAULT_CATALOGO)


def desactivar_prenda(prenda_id: int):
    sb = get_client()
    sb_execute(sb.table("prendas").update({"activo": False}).eq("id", prenda_id))


def listar_variantes(prenda_id: int | None = None):
    sb = get_client()
    q = sb.table("variantes").select("id,prenda_id,talla,stock_minimo,prendas!inner(nombre,categoria,activo)")
    q = q.eq("prendas.activo", True)
    if prenda_id is not None:
        q = q.eq("prenda_id", prenda_id)
    filas = sb_execute(q).data
    resultado = [
        {
            "id": f["id"], "prenda_id": f["prenda_id"], "prenda": f["prendas"]["nombre"],
            "categoria": f["prendas"]["categoria"], "talla": f["talla"], "stock_minimo": f["stock_minimo"],
        }
        for f in filas
    ]
    resultado.sort(key=lambda r: (r["prenda"], r["talla"]))
    return resultado


def actualizar_stock_minimo_variante(variante_id: int, stock_minimo: int):
    sb = get_client()
    sb_execute(sb.table("variantes").update({"stock_minimo": stock_minimo}).eq("id", variante_id))


# ---------------------------------------------------------------------------
# Empleados
# ---------------------------------------------------------------------------

def listar_empleados(solo_activos: bool = True):
    sb = get_client()
    q = sb.table("empleados").select("*")
    if solo_activos:
        q = q.eq("activo", True)
    return sb_execute(q.order("nombre")).data


def crear_empleado(numero_empleado: str, nombre: str, puesto: str, area: str, fecha_ingreso: str):
    sb = get_client()
    fila = sb_execute(sb.table("empleados").insert({
        "numero_empleado": numero_empleado or None, "nombre": nombre, "puesto": puesto or None,
        "area": area or None, "fecha_ingreso": fecha_ingreso or None,
    })).data[0]
    return fila["id"]


COLUMN_ALIASES = {
    "numero_empleado": {
        "numero_empleado", "num_empleado", "no_empleado", "numero_de_empleado",
        "no_de_empleado", "id_empleado", "employee_id", "clave_empleado", "clave",
        "numero", "no_nomina", "numero_de_nomina", "nomina",
    },
    "nombre": {
        "nombre", "nombre_completo", "empleado", "nombre_empleado", "nombre_del_empleado",
        "employee_name", "employee", "name", "trabajador",
    },
    "puesto": {"puesto", "posicion", "position", "cargo", "job_title", "puesto_de_trabajo"},
    "area": {"area", "ruta", "departamento", "department", "zona", "sitio", "cedis", "planta"},
    "fecha_ingreso": {
        "fecha_ingreso", "fecha_de_ingreso", "hire_date", "fecha_alta", "fecha_de_alta",
        "ingreso", "antiguedad", "fecha_contratacion",
    },
}
_ALIAS_TOKENS = {destino: {t for alias in aliases for t in alias.split("_")}
                 for destino, aliases in COLUMN_ALIASES.items()}


def _normalizar_encabezado(col) -> str:
    col = str(col).strip().lower()
    col = unicodedata.normalize("NFKD", col).encode("ascii", "ignore").decode("ascii")
    col = re.sub(r"[^a-z0-9]+", "_", col).strip("_")
    return col


def mapear_columnas_empleados(df):
    colmap = {}
    reconocidas = []
    for col in df.columns:
        norm = _normalizar_encabezado(col)
        tokens = set(norm.split("_"))
        for destino, alias in COLUMN_ALIASES.items():
            if destino in colmap.values():
                continue
            if norm in alias or (tokens & _ALIAS_TOKENS[destino]):
                colmap[col] = destino
                reconocidas.append((col, destino))
                break
    return df.rename(columns=colmap), reconocidas


def _valor_str(row, campo) -> str:
    if campo not in row.index:
        return ""
    val = row[campo]
    if val is None:
        return ""
    if isinstance(val, float) and val != val:  # NaN
        return ""
    s = str(val).strip()
    if s.endswith(".0") and s.replace(".0", "").lstrip("-").isdigit():
        s = s[:-2]
    return s


def importar_empleados_df(df):
    df, _reconocidas = mapear_columnas_empleados(df)
    if "nombre" not in df.columns:
        columnas_originales = ", ".join(str(c) for c in df.columns)
        raise ValueError(
            "No encontré una columna de nombre del empleado. "
            f"Columnas detectadas en el archivo: {columnas_originales}. "
            "Renombra esa columna a 'nombre' (o 'Nombre completo') e intenta de nuevo."
        )

    sb = get_client()
    creados, actualizados, omitidos = 0, 0, 0
    for _, row in df.iterrows():
        numero = _valor_str(row, "numero_empleado") or None
        nombre = _valor_str(row, "nombre")
        if not nombre:
            omitidos += 1
            continue
        puesto = _valor_str(row, "puesto") or None
        area = _valor_str(row, "area") or None
        fecha_ingreso = _valor_str(row, "fecha_ingreso") or None

        existente = None
        if numero:
            existente = sb_execute(
                sb.table("empleados").select("id").eq("numero_empleado", numero)
            ).data

        if existente:
            sb_execute(sb.table("empleados").update({
                "nombre": nombre, "puesto": puesto, "area": area,
                "fecha_ingreso": fecha_ingreso, "activo": True,
            }).eq("id", existente[0]["id"]))
            actualizados += 1
        else:
            sb_execute(sb.table("empleados").insert({
                "numero_empleado": numero, "nombre": nombre, "puesto": puesto,
                "area": area, "fecha_ingreso": fecha_ingreso,
            }))
            creados += 1
    return creados, actualizados, omitidos


def desactivar_empleado(empleado_id: int):
    sb = get_client()
    sb_execute(sb.table("empleados").update({"activo": False}).eq("id", empleado_id))


# ---------------------------------------------------------------------------
# Inventario
# ---------------------------------------------------------------------------

def registrar_movimiento(variante_id: int, tipo: str, cantidad: int, fecha: str,
                          motivo: str = "", referencia: str = "", registrado_por: str = "") -> int:
    sb = get_client()
    fila = sb_execute(sb.table("movimientos_inventario").insert({
        "variante_id": variante_id, "tipo": tipo, "cantidad": cantidad, "fecha": fecha,
        "motivo": motivo, "referencia": referencia, "registrado_por": registrado_por,
    })).data[0]
    return fila["id"]


def stock_actual():
    """Lee la vista v_stock_actual (ver schema.sql) — la suma de entradas/salidas/
    ajustes la hace Postgres, no Python, para que escale bien sin importar cuántos
    movimientos históricos haya."""
    sb = get_client()
    filas = sb_execute(sb.table("v_stock_actual").select("*").order("prenda").order("talla")).data
    return [{"variante_id": f["variante_id"], "prenda": f["prenda"], "categoria": f["categoria"],
              "talla": f["talla"], "stock_minimo": f["stock_minimo"], "stock": f["stock"]} for f in filas]


def historial_movimientos(fecha_desde: str | None = None, fecha_hasta: str | None = None):
    sb = get_client()
    q = sb.table("movimientos_inventario").select(
        "id,variante_id,tipo,cantidad,fecha,motivo,referencia,registrado_por,creado_en,"
        "variantes(talla,prendas(nombre))"
    )
    if fecha_desde:
        q = q.gte("fecha", fecha_desde)
    if fecha_hasta:
        q = q.lte("fecha", fecha_hasta)
    filas = sb_execute(q.order("fecha", desc=True).order("id", desc=True)).data
    return [
        {**{k: f[k] for k in ("id", "variante_id", "tipo", "cantidad", "fecha", "motivo",
                               "referencia", "registrado_por", "creado_en")},
         "prenda": f["variantes"]["prendas"]["nombre"], "talla": f["variantes"]["talla"]}
        for f in filas
    ]


# ---------------------------------------------------------------------------
# Entregas (registra la entrega Y descuenta inventario en una sola operación)
# ---------------------------------------------------------------------------

def registrar_entrega(empleado_id: int, variante_id: int, cantidad: int, fecha: str,
                       motivo: str, entregado_por: str = "", notas: str = "",
                       firma_png: bytes | None = None) -> int:
    movimiento_id = registrar_movimiento(
        variante_id=variante_id, tipo="salida", cantidad=cantidad, fecha=fecha,
        motivo=f"Entrega: {motivo}", referencia="entrega", registrado_por=entregado_por,
    )
    sb = get_client()
    firma_b64 = base64.b64encode(firma_png).decode("ascii") if firma_png else None
    fila = sb_execute(sb.table("entregas").insert({
        "empleado_id": empleado_id, "variante_id": variante_id, "cantidad": cantidad,
        "fecha": fecha, "motivo": motivo, "entregado_por": entregado_por, "notas": notas,
        "movimiento_id": movimiento_id, "firma_png_b64": firma_b64,
    })).data[0]
    return fila["id"]


def obtener_entrega(entrega_id: int):
    sb = get_client()
    filas = sb_execute(sb.table("entregas").select(
        "*,empleados(nombre,numero_empleado,puesto,area),variantes(talla,prendas(nombre))"
    ).eq("id", entrega_id)).data
    if not filas:
        return None
    f = filas[0]
    firma_png = base64.b64decode(f["firma_png_b64"]) if f.get("firma_png_b64") else None
    return {
        "id": f["id"], "empleado_id": f["empleado_id"], "variante_id": f["variante_id"],
        "cantidad": f["cantidad"], "fecha": f["fecha"], "motivo": f["motivo"],
        "entregado_por": f["entregado_por"], "notas": f["notas"],
        "empleado": f["empleados"]["nombre"], "numero_empleado": f["empleados"]["numero_empleado"],
        "puesto": f["empleados"]["puesto"], "area": f["empleados"]["area"],
        "prenda": f["variantes"]["prendas"]["nombre"], "talla": f["variantes"]["talla"],
        "firma_png": firma_png,
    }


def historial_entregas(empleado_id: int | None = None, fecha_desde: str | None = None,
                        fecha_hasta: str | None = None):
    sb = get_client()
    q = sb.table("entregas").select(
        "id,empleado_id,variante_id,cantidad,fecha,motivo,entregado_por,notas,movimiento_id,creado_en,"
        "firma_png_b64,empleados(nombre,numero_empleado),variantes(talla,prendas(nombre))"
    )
    if empleado_id is not None:
        q = q.eq("empleado_id", empleado_id)
    if fecha_desde:
        q = q.gte("fecha", fecha_desde)
    if fecha_hasta:
        q = q.lte("fecha", fecha_hasta)
    filas = sb_execute(q.order("fecha", desc=True).order("id", desc=True)).data
    registros = []
    for f in filas:
        registros.append({
            "id": f["id"], "empleado_id": f["empleado_id"], "variante_id": f["variante_id"],
            "cantidad": f["cantidad"], "fecha": f["fecha"], "motivo": f["motivo"],
            "entregado_por": f["entregado_por"], "notas": f["notas"],
            "movimiento_id": f["movimiento_id"], "creado_en": f["creado_en"],
            "tiene_firma": 1 if f.get("firma_png_b64") else 0,
            "empleado": f["empleados"]["nombre"], "numero_empleado": f["empleados"]["numero_empleado"],
            "prenda": f["variantes"]["prendas"]["nombre"], "talla": f["variantes"]["talla"],
            "folio": folio_entrega(f["id"]),
        })
    return registros
