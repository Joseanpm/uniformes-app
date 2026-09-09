"""
Login del Sistema de Entrega e Inventario de Uniformes (versión Supabase/nube).

La versión local (misma WiFi del CEDIS) no lo necesita porque solo la ve quien
está conectado a esa red. Esta versión sí, porque la URL queda accesible desde
cualquier lugar una vez desplegada en Streamlit Community Cloud.

Usuarios y contraseñas viven en la tabla `usuarios` de Supabase (ver schema.sql),
con la contraseña guardada como hash (bcrypt), nunca en texto plano.

La primera vez que se usa la app (tabla `usuarios` vacía) se muestra un
formulario para crear el primer usuario, en vez de pedir credenciales que
todavía no existen.
"""

import bcrypt
import streamlit as st

import db


def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def _verificar_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except Exception:
        return False


def usuarios_existen() -> bool:
    sb = db.get_client()
    filas = db.sb_execute(sb.table("usuarios").select("id").limit(1)).data
    return bool(filas)


def listar_usuarios(solo_activos: bool = True):
    sb = db.get_client()
    q = sb.table("usuarios").select("id,usuario,nombre,activo,creado_en")
    if solo_activos:
        q = q.eq("activo", True)
    return db.sb_execute(q.order("nombre")).data


def crear_usuario(usuario: str, nombre: str, password: str) -> int:
    usuario = usuario.strip().lower()
    sb = db.get_client()
    fila = db.sb_execute(sb.table("usuarios").insert({
        "usuario": usuario, "nombre": nombre.strip(), "password_hash": _hash_password(password),
    })).data[0]
    return fila["id"]


def desactivar_usuario(usuario_id: int):
    sb = db.get_client()
    db.sb_execute(sb.table("usuarios").update({"activo": False}).eq("id", usuario_id))


def autenticar(usuario: str, password: str):
    """Regresa el dict del usuario si las credenciales son correctas y está
    activo, o None si no. No distingue "usuario no existe" de "password
    incorrecta" en el mensaje que ve la persona, por seguridad."""
    sb = db.get_client()
    filas = db.sb_execute(
        sb.table("usuarios").select("id,usuario,nombre,password_hash,activo")
        .eq("usuario", usuario.strip().lower())
    ).data
    if not filas or not filas[0]["activo"]:
        return None
    fila = filas[0]
    if not _verificar_password(password, fila["password_hash"]):
        return None
    return {"id": fila["id"], "usuario": fila["usuario"], "nombre": fila["nombre"]}


def usuario_actual():
    return st.session_state.get("auth_usuario")


def logout():
    st.session_state.pop("auth_usuario", None)
    st.rerun()


def require_login():
    """Bloquea el resto de la app hasta que haya una sesión válida. Se llama al
    principio de app.py, antes de dibujar cualquier página."""
    if st.session_state.get("auth_usuario"):
        return  # ya hay sesión, seguir con la app normal

    st.title("👕 Uniformes")

    if not usuarios_existen():
        st.info(
            "Todavía no hay usuarios configurados. Crea el primero (va a quedar "
            "como el usuario administrador inicial; después puedes dar de alta "
            "al resto del equipo desde la página de Usuarios)."
        )
        with st.form("form_primer_usuario"):
            nombre = st.text_input("Tu nombre")
            usuario = st.text_input("Usuario (para iniciar sesión)")
            password = st.text_input("Contraseña", type="password")
            password2 = st.text_input("Confirma la contraseña", type="password")
            enviado = st.form_submit_button("Crear usuario y entrar")
            if enviado:
                if not nombre.strip() or not usuario.strip() or not password:
                    st.error("Completa todos los campos.")
                elif password != password2:
                    st.error("Las contraseñas no coinciden.")
                elif len(password) < 6:
                    st.error("Usa una contraseña de al menos 6 caracteres.")
                else:
                    crear_usuario(usuario, nombre, password)
                    st.session_state["auth_usuario"] = autenticar(usuario, password)
                    st.rerun()
        st.stop()

    with st.form("form_login"):
        usuario = st.text_input("Usuario")
        password = st.text_input("Contraseña", type="password")
        enviado = st.form_submit_button("Entrar")
        if enviado:
            resultado = autenticar(usuario, password)
            if resultado:
                st.session_state["auth_usuario"] = resultado
                st.rerun()
            else:
                st.error("Usuario o contraseña incorrectos.")
    st.stop()
