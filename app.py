"""
Sistema de Entrega e Inventario de Uniformes — versión nube (Streamlit Cloud + Supabase)
==========================================================================================

Misma app que la versión local, pero con los datos en Supabase (en vez de un
archivo SQLite) y con login, para poder vivir en Streamlit Community Cloud y
que el equipo la use desde cualquier lugar (por ejemplo, el analista
registrando entregas desde su celular con datos móviles).

Cómo correrla en local para probar:
    export SUPABASE_URL="https://tu-proyecto.supabase.co"
    export SUPABASE_KEY="tu-llave-anon"
    streamlit run app.py

En Streamlit Cloud, esas mismas dos credenciales van en Settings → Secrets
(ver README.md) en vez de variables de entorno.
"""

from datetime import date, datetime
from io import BytesIO

import numpy as np
import pandas as pd
import streamlit as st
from PIL import Image
from streamlit_drawable_canvas import st_canvas

import auth
import db
import ticket

st.set_page_config(page_title="Uniformes | Entregas e Inventario", page_icon="👕", layout="wide")

db.init_db()
db.seed_catalogo_default()
auth.require_login()  # no deja seguir hasta que haya una sesión válida

# ---------------------------------------------------------------------------
# Sidebar / navegación
# ---------------------------------------------------------------------------

st.sidebar.title("👕 Uniformes")

usuario = auth.usuario_actual()
st.sidebar.caption(f"Sesión: **{usuario['nombre']}**")
if st.sidebar.button("Cerrar sesión"):
    auth.logout()

cedis_actual = db.get_config("cedis", "CEDIS")
with st.sidebar.expander("⚙️ Sitio (CEDIS)", expanded=False):
    nuevo_cedis = st.text_input("Nombre del sitio", value=cedis_actual)
    if nuevo_cedis != cedis_actual and st.button("Guardar nombre de sitio"):
        db.set_config("cedis", nuevo_cedis)
        st.rerun()

st.sidebar.caption(f"Sitio actual: **{cedis_actual}**")

pagina = st.sidebar.radio(
    "Ir a:",
    ["🏠 Inicio", "📦 Catálogo", "🧑‍🤝‍🧑 Empleados", "📥 Inventario", "🚚 Entregas", "📊 Reportes", "👤 Usuarios"],
)

st.sidebar.divider()
st.sidebar.caption("Sistema de Entrega e Inventario de Uniformes")


def df_export_button(df: pd.DataFrame, filename: str, label: str = "⬇️ Descargar Excel"):
    if df.empty:
        st.info("No hay datos para exportar todavía.")
        return
    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Datos")
    st.download_button(label, data=buffer.getvalue(), file_name=filename,
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


def limpia_nulos(df: pd.DataFrame) -> pd.DataFrame:
    """Cambia None/NaN por '' para que las tablas no muestren la palabra 'None' cuando
    un campo opcional (puesto, área, número de empleado, notas...) viene vacío."""
    return df.where(pd.notnull(df), "")


# ---------------------------------------------------------------------------
# Inicio
# ---------------------------------------------------------------------------

if pagina == "🏠 Inicio":
    st.title(f"👕 Uniformes — {cedis_actual}")
    st.caption("Resumen general de inventario y entregas")

    stock = pd.DataFrame(db.stock_actual())
    entregas = pd.DataFrame(db.historial_entregas())
    empleados = db.listar_empleados()

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Empleados activos", len(empleados))
    col2.metric("Variantes en catálogo", len(stock))
    col3.metric("Entregas registradas", len(entregas))
    bajo_stock = stock[stock["stock"] <= stock["stock_minimo"]] if not stock.empty else pd.DataFrame()
    col4.metric("Variantes en stock bajo", len(bajo_stock))

    st.divider()

    c1, c2 = st.columns(2)
    with c1:
        st.subheader("⚠️ Stock bajo o agotado")
        if bajo_stock.empty:
            st.success("Todo el inventario está por arriba del mínimo configurado.")
        else:
            st.dataframe(
                bajo_stock[["prenda", "talla", "stock", "stock_minimo"]]
                .rename(columns={"prenda": "Prenda", "talla": "Talla", "stock": "Stock actual",
                                 "stock_minimo": "Stock mínimo"}),
                width='stretch', hide_index=True,
            )
    with c2:
        st.subheader("🚚 Últimas entregas")
        if entregas.empty:
            st.info("Todavía no hay entregas registradas.")
        else:
            st.dataframe(
                entregas[["fecha", "empleado", "prenda", "talla", "cantidad", "motivo"]]
                .rename(columns={"fecha": "Fecha", "empleado": "Empleado", "prenda": "Prenda",
                                  "talla": "Talla", "cantidad": "Cant.", "motivo": "Motivo"})
                .head(10),
                width='stretch', hide_index=True,
            )

# ---------------------------------------------------------------------------
# Catálogo
# ---------------------------------------------------------------------------

elif pagina == "📦 Catálogo":
    st.title("📦 Catálogo de prendas y tallas")

    with st.expander("➕ Agregar prenda nueva", expanded=False):
        with st.form("form_nueva_prenda", clear_on_submit=True):
            c1, c2 = st.columns(2)
            nombre = c1.text_input("Nombre de la prenda *")
            categoria = c2.text_input("Categoría (ej. Ropa superior, Calzado)")
            tipo_talla = st.selectbox("Sistema de tallas", list(db.TIPOS_TALLA.keys()))
            stock_min = st.number_input("Stock mínimo por talla (para alertas visuales)", min_value=0, value=3)
            enviado = st.form_submit_button("Agregar prenda")
            if enviado:
                if not nombre.strip():
                    st.error("El nombre de la prenda es obligatorio.")
                else:
                    try:
                        db.crear_prenda(nombre.strip(), categoria.strip(), tipo_talla, int(stock_min))
                        st.success(f"Prenda '{nombre}' agregada con tallas: {', '.join(db.TIPOS_TALLA[tipo_talla])}")
                        st.rerun()
                    except Exception as e:
                        st.error(f"No se pudo agregar (¿ya existe?): {e}")

    st.subheader("Prendas y tallas activas")
    variantes = pd.DataFrame(db.listar_variantes())
    if variantes.empty:
        st.info("Todavía no hay prendas en el catálogo.")
    else:
        for prenda_id, grupo in variantes.groupby("prenda_id"):
            nombre_prenda = grupo.iloc[0]["prenda"]
            categoria = grupo.iloc[0]["categoria"]
            with st.expander(f"**{nombre_prenda}** ({categoria or 'sin categoría'}) — {len(grupo)} tallas"):
                st.dataframe(
                    grupo[["talla", "stock_minimo"]].rename(
                        columns={"talla": "Talla", "stock_minimo": "Stock mínimo"}
                    ),
                    width='stretch', hide_index=True,
                )
                if st.button(f"Desactivar '{nombre_prenda}'", key=f"desactivar_{prenda_id}"):
                    db.desactivar_prenda(int(prenda_id))
                    st.rerun()

# ---------------------------------------------------------------------------
# Empleados
# ---------------------------------------------------------------------------

elif pagina == "🧑‍🤝‍🧑 Empleados":
    st.title("🧑‍🤝‍🧑 Empleados")

    tab1, tab2, tab3 = st.tabs(["Alta manual", "Importar desde Excel", "Listado"])

    with tab1:
        with st.form("form_nuevo_empleado", clear_on_submit=True):
            c1, c2 = st.columns(2)
            numero = c1.text_input("Número de empleado")
            nombre = c2.text_input("Nombre completo *")
            c3, c4 = st.columns(2)
            puesto = c3.text_input("Puesto (ej. Chofer Repartidor)")
            area = c4.text_input("Área / Ruta")
            fecha_ingreso = st.date_input("Fecha de ingreso", value=date.today())
            enviado = st.form_submit_button("Agregar empleado")
            if enviado:
                if not nombre.strip():
                    st.error("El nombre es obligatorio.")
                else:
                    db.crear_empleado(numero.strip(), nombre.strip(), puesto.strip(), area.strip(),
                                       fecha_ingreso.isoformat())
                    st.success(f"Empleado '{nombre}' agregado.")
                    st.rerun()

    with tab2:
        st.caption("El Excel debe tener columnas: numero_empleado, nombre, puesto, area, fecha_ingreso "
                   "(solo 'nombre' es obligatoria).")

        if "empleados_import_uploader_key" not in st.session_state:
            st.session_state["empleados_import_uploader_key"] = 0
        if st.session_state.get("empleados_import_msg"):
            st.success(st.session_state.pop("empleados_import_msg"))

        archivo = st.file_uploader(
            "Sube el Excel de empleados", type=["xlsx", "xls"],
            key=f"empleados_uploader_{st.session_state['empleados_import_uploader_key']}",
        )
        if archivo is not None:
            try:
                df_preview = pd.read_excel(archivo)
                st.dataframe(df_preview.head(20), width='stretch')

                df_mapeado, reconocidas = db.mapear_columnas_empleados(df_preview)
                if reconocidas:
                    detalle = ", ".join(f"'{orig}' → {destino}" for orig, destino in reconocidas)
                    st.caption(f"Columnas reconocidas: {detalle}")
                if "nombre" not in df_mapeado.columns:
                    st.warning(
                        "No reconozco cuál columna trae el nombre del empleado — revisa que exista una "
                        "columna tipo 'Nombre' o 'Nombre completo'. Aun así puedes intentar importar para "
                        "ver el detalle del error."
                    )

                if st.button("Importar empleados"):
                    creados, actualizados, omitidos = db.importar_empleados_df(df_preview)
                    msg = f"Listo: {creados} empleados nuevos, {actualizados} actualizados."
                    if omitidos:
                        msg += f" ({omitidos} filas sin nombre se omitieron.)"
                    st.session_state["empleados_import_msg"] = msg
                    # Cambia la key del uploader para que quede vacío en el siguiente rerun
                    # (evita que el mismo archivo se vuelva a importar por accidente)
                    st.session_state["empleados_import_uploader_key"] += 1
                    st.rerun()
            except Exception as e:
                st.error(f"No se pudo leer el archivo: {e}")

    with tab3:
        empleados = pd.DataFrame(db.listar_empleados())
        if empleados.empty:
            st.info("Todavía no hay empleados registrados.")
        else:
            st.dataframe(
                limpia_nulos(empleados[["numero_empleado", "nombre", "puesto", "area", "fecha_ingreso"]])
                .rename(columns={"numero_empleado": "No. empleado", "nombre": "Nombre", "puesto": "Puesto",
                                  "area": "Área", "fecha_ingreso": "Fecha ingreso"}),
                width='stretch', hide_index=True,
            )
            df_export_button(empleados, "empleados.xlsx")

# ---------------------------------------------------------------------------
# Inventario
# ---------------------------------------------------------------------------

elif pagina == "📥 Inventario":
    st.title("📥 Inventario")

    tab1, tab2, tab3 = st.tabs(["Stock actual", "Registrar entrada / ajuste", "Historial de movimientos"])

    with tab1:
        stock = pd.DataFrame(db.stock_actual())
        if stock.empty:
            st.info("Agrega prendas al catálogo primero.")
        else:
            tabla = stock[["prenda", "talla", "stock", "stock_minimo"]].rename(
                columns={"prenda": "Prenda", "talla": "Talla", "stock": "Stock actual", "stock_minimo": "Stock mínimo"}
            )

            def resalta_bajo(row):
                bajo = row["Stock actual"] <= row["Stock mínimo"]
                return ["background-color: #ffe1e1" if bajo else ""] * len(row)

            st.dataframe(tabla.style.apply(resalta_bajo, axis=1), width='stretch', hide_index=True)
            df_export_button(stock, "stock_actual.xlsx")

    with tab2:
        variantes = db.listar_variantes()
        if not variantes:
            st.info("Agrega prendas al catálogo primero.")
        else:
            opciones = {f"{v['prenda']} — talla {v['talla']}": v["id"] for v in variantes}
            with st.form("form_movimiento", clear_on_submit=True):
                variante_label = st.selectbox("Prenda / talla", list(opciones.keys()))
                c1, c2 = st.columns(2)
                tipo = c1.selectbox("Tipo de movimiento", ["entrada", "ajuste"],
                                     format_func=lambda x: "Entrada (compra/recepción)" if x == "entrada" else "Ajuste (+/-)")
                cantidad = c2.number_input("Cantidad", value=1, step=1,
                                            help="Para ajustes puedes usar números negativos.")
                c3, c4 = st.columns(2)
                fecha = c3.date_input("Fecha", value=date.today())
                referencia = c4.text_input("Referencia (folio, proveedor, etc.)")
                motivo = st.text_input("Motivo / notas")
                enviado = st.form_submit_button("Registrar movimiento")
                if enviado:
                    variante_id = opciones[variante_label]
                    db.registrar_movimiento(variante_id, tipo, int(cantidad), fecha.isoformat(),
                                             motivo=motivo, referencia=referencia)
                    st.success("Movimiento registrado.")
                    st.rerun()

    with tab3:
        c1, c2 = st.columns(2)
        desde = c1.date_input("Desde", value=None, key="mov_desde")
        hasta = c2.date_input("Hasta", value=None, key="mov_hasta")
        movs = pd.DataFrame(db.historial_movimientos(
            fecha_desde=desde.isoformat() if desde else None,
            fecha_hasta=hasta.isoformat() if hasta else None,
        ))
        if movs.empty:
            st.info("No hay movimientos en ese rango.")
        else:
            st.dataframe(
                movs[["fecha", "prenda", "talla", "tipo", "cantidad", "motivo", "referencia", "registrado_por"]]
                .rename(columns={"fecha": "Fecha", "prenda": "Prenda", "talla": "Talla", "tipo": "Tipo",
                                  "cantidad": "Cantidad", "motivo": "Motivo", "referencia": "Referencia",
                                  "registrado_por": "Registrado por"}),
                width='stretch', hide_index=True,
            )
            df_export_button(movs, "movimientos_inventario.xlsx")

# ---------------------------------------------------------------------------
# Entregas
# ---------------------------------------------------------------------------

elif pagina == "🚚 Entregas":
    st.title("🚚 Entregas de uniforme")

    tab1, tab2 = st.tabs(["Registrar entrega", "Historial"])

    with tab1:
        if "firma_canvas_key" not in st.session_state:
            st.session_state["firma_canvas_key"] = 0

        # Banner con el resultado de la última entrega + su comprobante. A propósito NO se
        # hace pop() aquí: el canvas de firma se resetea cambiando su key, y ese remount
        # dispara un rerun extra de Streamlit (el componente reporta su valor inicial):
        # si el mensaje se sacara con pop() en ese primer render, ese rerun automático lo
        # borraría antes de que la persona alcance a verlo o a descargar el PDF. Se
        # reemplaza solo (o desaparece) cuando se registra la siguiente entrega.
        ultimo = st.session_state.get("ultima_entrega")
        if ultimo:
            st.success(ultimo["mensaje"])
            entrega_completa = db.obtener_entrega(ultimo["entrega_id"])
            if entrega_completa:
                pdf_bytes = ticket.generar_ticket_pdf(entrega_completa)
                st.download_button(
                    "⬇️ Descargar comprobante (PDF)",
                    data=pdf_bytes,
                    file_name=f"{db.folio_entrega(ultimo['entrega_id'])}.pdf",
                    mime="application/pdf",
                )

        empleados = db.listar_empleados()
        variantes = db.listar_variantes()
        if not empleados or not variantes:
            st.info("Necesitas al menos un empleado y una prenda en el catálogo para registrar una entrega.")
        else:
            emp_opciones = {f"{e['nombre']} ({e['numero_empleado'] or 's/n'})": e["id"] for e in empleados}
            stock_por_variante = {s["variante_id"]: s["stock"] for s in db.stock_actual()}
            var_opciones = {
                f"{v['prenda']} — talla {v['talla']} (stock: {stock_por_variante.get(v['id'], 0)})": v["id"]
                for v in variantes
            }

            st.caption(
                "✍️ Firma digital del empleado (opcional). Si hoy la firma se toma en papel, "
                "déjala en blanco: el comprobante igual se genera con espacio para firmar a mano."
            )
            # Ancho fijo pensado para que quepa cómodo en la pantalla de un celular
            # (~360-390px de ancho típico) sin necesidad de hacer scroll lateral para
            # firmar; en escritorio se ve un poco más chico que antes, pero funcional.
            canvas_result = st_canvas(
                stroke_width=2,
                stroke_color="#1a1a1a",
                background_color="rgba(255, 255, 255, 0)",
                height=140,
                width=320,
                drawing_mode="freedraw",
                display_toolbar=True,
                key=f"firma_canvas_{st.session_state['firma_canvas_key']}",
            )

            with st.form("form_entrega", clear_on_submit=True):
                empleado_label = st.selectbox("Empleado", list(emp_opciones.keys()))
                variante_label = st.selectbox("Prenda / talla", list(var_opciones.keys()))
                c1, c2 = st.columns(2)
                cantidad = c1.number_input("Cantidad", min_value=1, value=1, step=1)
                fecha = c2.date_input("Fecha de entrega", value=date.today())
                motivo = st.selectbox("Motivo", db.MOTIVOS_ENTREGA)
                c3, c4 = st.columns(2)
                entregado_por = c3.text_input("Entregado por", value=usuario["nombre"])
                notas = c4.text_input("Notas (opcional)")
                enviado = st.form_submit_button("Registrar entrega")
                if enviado:
                    empleado_id = emp_opciones[empleado_label]
                    variante_id = var_opciones[variante_label]

                    firma_png = None
                    if canvas_result is not None and canvas_result.image_data is not None:
                        arr = canvas_result.image_data
                        if arr[:, :, 3].max() > 0:  # algo se dibujó (canal alfa no vacío)
                            img = Image.fromarray(arr.astype("uint8"), mode="RGBA")
                            buf = BytesIO()
                            img.save(buf, format="PNG")
                            firma_png = buf.getvalue()

                    entrega_id = db.registrar_entrega(empleado_id, variante_id, int(cantidad),
                                                        fecha.isoformat(), motivo, entregado_por, notas,
                                                        firma_png=firma_png)
                    folio = db.folio_entrega(entrega_id)
                    detalle_firma = " (con firma digital)" if firma_png else " (pendiente de firma en papel)"
                    st.session_state["ultima_entrega"] = {
                        "entrega_id": entrega_id,
                        "mensaje": f"Entrega registrada — folio {folio}{detalle_firma}.",
                    }
                    # Cambia la key del canvas para que quede en blanco en el siguiente rerun
                    st.session_state["firma_canvas_key"] += 1
                    st.rerun()

    with tab2:
        c1, c2, c3 = st.columns(3)
        empleados = db.listar_empleados()
        emp_filtro = c1.selectbox("Filtrar por empleado", ["Todos"] + [e["nombre"] for e in empleados])
        desde = c2.date_input("Desde", value=None, key="ent_desde")
        hasta = c3.date_input("Hasta", value=None, key="ent_hasta")

        empleado_id = None
        if emp_filtro != "Todos":
            empleado_id = next((e["id"] for e in empleados if e["nombre"] == emp_filtro), None)

        entregas_raw = db.historial_entregas(
            empleado_id=empleado_id,
            fecha_desde=desde.isoformat() if desde else None,
            fecha_hasta=hasta.isoformat() if hasta else None,
        )
        entregas = pd.DataFrame(entregas_raw)
        if entregas.empty:
            st.info("No hay entregas en ese filtro.")
        else:
            tabla = limpia_nulos(entregas.copy())
            tabla["tiene_firma"] = entregas["tiene_firma"].map({1: "✅ Digital", 0: "📝 Papel"})
            st.dataframe(
                tabla[["folio", "fecha", "empleado", "numero_empleado", "prenda", "talla", "cantidad",
                       "motivo", "entregado_por", "tiene_firma", "notas"]]
                .rename(columns={"folio": "Folio", "fecha": "Fecha", "empleado": "Empleado",
                                  "numero_empleado": "No. empleado", "prenda": "Prenda", "talla": "Talla",
                                  "cantidad": "Cant.", "motivo": "Motivo", "entregado_por": "Entregado por",
                                  "tiene_firma": "Firma", "notas": "Notas"}),
                width='stretch', hide_index=True,
            )
            df_export_button(entregas.drop(columns=["tiene_firma"], errors="ignore"),
                              "historial_entregas.xlsx")

            st.divider()
            st.subheader("📄 Reimprimir comprobante")
            opciones_folio = {f"{r['folio']} — {r['empleado']} ({r['fecha']})": r["id"] for r in entregas_raw}
            folio_sel = st.selectbox("Elige una entrega", list(opciones_folio.keys()))
            if folio_sel:
                entrega_id_sel = opciones_folio[folio_sel]
                entrega_completa = db.obtener_entrega(entrega_id_sel)
                if entrega_completa:
                    pdf_bytes = ticket.generar_ticket_pdf(entrega_completa)
                    st.download_button(
                        "⬇️ Descargar comprobante (PDF)",
                        data=pdf_bytes,
                        file_name=f"{db.folio_entrega(entrega_id_sel)}.pdf",
                        mime="application/pdf",
                        key=f"descarga_ticket_{entrega_id_sel}",
                    )

# ---------------------------------------------------------------------------
# Reportes
# ---------------------------------------------------------------------------

elif pagina == "📊 Reportes":
    st.title("📊 Reportes")
    st.caption("Exporta cualquiera de estos reportes a Excel para compartir o archivar.")

    st.subheader("Stock actual por prenda y talla")
    stock = pd.DataFrame(db.stock_actual())
    if not stock.empty:
        st.dataframe(stock[["prenda", "talla", "stock", "stock_minimo"]], width='stretch', hide_index=True)
        df_export_button(stock, "reporte_stock_actual.xlsx", "⬇️ Descargar stock actual")
    else:
        st.info("Sin datos de stock todavía.")

    st.divider()
    st.subheader("Historial completo de entregas")
    entregas = pd.DataFrame(db.historial_entregas())
    if not entregas.empty:
        st.dataframe(entregas[["fecha", "empleado", "prenda", "talla", "cantidad", "motivo"]],
                     width='stretch', hide_index=True)
        df_export_button(entregas, "reporte_entregas.xlsx", "⬇️ Descargar historial de entregas")
    else:
        st.info("Sin entregas registradas todavía.")

    st.divider()
    st.subheader("Consumo por empleado (totales)")
    if not entregas.empty:
        resumen = entregas.groupby(["empleado", "numero_empleado"]).agg(
            prendas_entregadas=("cantidad", "sum"),
            movimientos=("id", "count"),
        ).reset_index().rename(columns={"empleado": "Empleado", "numero_empleado": "No. empleado",
                                         "prendas_entregadas": "Prendas entregadas", "movimientos": "No. entregas"})
        st.dataframe(resumen, width='stretch', hide_index=True)
        df_export_button(resumen, "reporte_consumo_por_empleado.xlsx", "⬇️ Descargar consumo por empleado")
    else:
        st.info("Sin datos suficientes todavía.")

# ---------------------------------------------------------------------------
# Usuarios (quién puede entrar a la app)
# ---------------------------------------------------------------------------

elif pagina == "👤 Usuarios":
    st.title("👤 Usuarios")
    st.caption(
        "Quién puede iniciar sesión en esta app. El nombre de la persona que entra "
        "se usa para prellenar \"Entregado por\" al registrar una entrega."
    )

    with st.expander("➕ Agregar usuario", expanded=False):
        with st.form("form_nuevo_usuario", clear_on_submit=True):
            nombre_nuevo = st.text_input("Nombre completo")
            usuario_nuevo = st.text_input("Usuario (para iniciar sesión, sin espacios)")
            c1, c2 = st.columns(2)
            pw1 = c1.text_input("Contraseña", type="password")
            pw2 = c2.text_input("Confirmar contraseña", type="password")
            enviado = st.form_submit_button("Crear usuario")
            if enviado:
                if not nombre_nuevo.strip() or not usuario_nuevo.strip() or not pw1:
                    st.error("Completa todos los campos.")
                elif pw1 != pw2:
                    st.error("Las contraseñas no coinciden.")
                elif len(pw1) < 6:
                    st.error("Usa una contraseña de al menos 6 caracteres.")
                else:
                    try:
                        auth.crear_usuario(usuario_nuevo, nombre_nuevo, pw1)
                        st.success(f"Usuario '{usuario_nuevo}' creado.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"No se pudo crear (¿el usuario ya existe?): {e}")

    st.subheader("Usuarios activos")
    usuarios = auth.listar_usuarios()
    if not usuarios:
        st.info("No hay usuarios activos.")
    else:
        for u in usuarios:
            c1, c2, c3 = st.columns([3, 2, 1])
            c1.write(f"**{u['nombre']}**")
            c2.write(f"usuario: `{u['usuario']}`")
            if u["id"] == usuario["id"]:
                c3.caption("(tú)")
            else:
                if c3.button("Desactivar", key=f"desactivar_usuario_{u['id']}"):
                    auth.desactivar_usuario(u["id"])
                    st.rerun()
