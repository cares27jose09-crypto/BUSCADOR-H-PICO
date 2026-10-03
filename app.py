"""Buscador hípico de Chile - app web (Streamlit).

Busca por caballo, criador (haras), jinete, preparador o stud en los próximos programas de
Valparaíso Sporting, Club Hípico de Santiago y (opcional) Hipódromo Chile.
"""
import datetime as dt
import hashlib
import os
from zoneinfo import ZoneInfo

import pandas as pd
import requests
import streamlit as st

import hipica as H

st.set_page_config(page_title="Buscador hípico de Chile", page_icon="🐎", layout="wide")

DIAS = ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"]
HOY = dt.datetime.now(ZoneInfo("America/Santiago")).date()

# Si algún día se conoce la URL directa del volante de Hipódromo Chile, se puede
# activar la descarga automática con una variable de entorno / secret:
#   HCH_URL_TEMPLATE = "https://.../volante_{aaaa}{mm}{dd}.pdf"
def _plantilla_hch() -> str:
    valor = os.environ.get("HCH_URL_TEMPLATE", "")
    if not valor:
        try:
            valor = st.secrets.get("HCH_URL_TEMPLATE", "")
        except Exception:  # noqa: BLE001  (no hay archivo de secretos)
            valor = ""
    return valor


HCH_URL_TEMPLATE = _plantilla_hch()


def fmt_fecha(iso: str) -> str:
    d = dt.date.fromisoformat(iso)
    return f"{DIAS[d.weekday()]} {d:%d-%m-%Y}"


# --------------------------------------------------------------------------
# Carga de datos (con caché de 30 minutos)
# --------------------------------------------------------------------------
@st.cache_data(ttl=1800, show_spinner=False)
def cargar_sporting(fecha_iso: str):
    try:
        return H.cargar_sporting(dt.date.fromisoformat(fecha_iso))
    except requests.RequestException as e:
        return [], f"Sporting {fecha_iso}: no se pudo conectar ({type(e).__name__})."
    except Exception as e:  # noqa: BLE001
        return [], f"Sporting {fecha_iso}: error al leer la página ({e})."


@st.cache_data(ttl=1800, show_spinner=False)
def cargar_chs(fecha_iso: str):
    fecha = dt.date.fromisoformat(fecha_iso)
    try:
        pdf = H.descargar_chs(fecha)
    except requests.RequestException as e:
        return [], f"Club Hípico {fecha_iso}: no se pudo conectar ({type(e).__name__})."
    if pdf is None:
        return [], ""  # ese día no hay reunión
    try:
        return H.parse_chs(pdf), ""
    except Exception as e:  # noqa: BLE001
        return [], f"Club Hípico {fecha_iso}: no se pudo leer el volante ({e})."


@st.cache_data(ttl=1800, show_spinner=False)
def cargar_hch_plantilla(plantilla: str, fecha_iso: str):
    fecha = dt.date.fromisoformat(fecha_iso)
    url = plantilla.format(dd=f"{fecha:%d}", mm=f"{fecha:%m}", aaaa=f"{fecha:%Y}")
    try:
        r = H.http_get(url)
        if r.status_code == 200 and r.content[:4] == b"%PDF":
            return H.parse_hch(r.content), ""
        return [], ""
    except Exception as e:  # noqa: BLE001
        return [], f"Hipódromo Chile {fecha_iso}: {e}"


@st.cache_data(ttl=3600, show_spinner=False)
def leer_hch_pdf(contenido: bytes):
    return H.parse_hch(contenido)


@st.cache_data(ttl=3600, show_spinner=False)
def bajar_pdf(url: str) -> bytes:
    r = H.http_get(url)
    r.raise_for_status()
    if r.content[:4] != b"%PDF":
        raise ValueError("el enlace no es un PDF")
    return r.content


# --------------------------------------------------------------------------
# Encabezado
# --------------------------------------------------------------------------
st.title("🐎 Buscador hípico de Chile")
st.caption(
    "Escribe un caballo, criadero (haras), jinete, preparador o stud y la app revisa los próximos "
    "programas de Valparaíso Sporting y Club Hípico de Santiago."
)

c1, c2, c3 = st.columns([3, 1.4, 1.2])
consulta = c1.text_input("¿Qué buscas?", placeholder="Ej.: Haras Santa Mónica, Javivaletu, J. Herrera, Sagardia…")
campo = c2.selectbox("Buscar en", list(H.CAMPOS_BUSQUEDA), index=0)
exacta = c3.checkbox("Nombre exacto", help="Solo nombres idénticos (sin contar 'Haras', 'H.' ni tildes).")

with st.expander("Opciones: fechas, hipódromos y Hipódromo Chile"):
    o1, o2 = st.columns(2)
    dias = o1.slider("Días a revisar (desde hoy)", 0, 10, 4,
                     help="0 = solo hoy. Los días sin reunión se ignoran solos.")
    hips = o2.multiselect("Hipódromos", [H.HIP_SPORTING, H.HIP_CHS, H.HIP_HCH],
                          default=[H.HIP_SPORTING, H.HIP_CHS, H.HIP_HCH])
    st.markdown("**Hipódromo Chile**" + (" (descarga automática activada)" if HCH_URL_TEMPLATE else ""))
    if not HCH_URL_TEMPLATE:
        st.caption(
            "Su volante todavía no se descarga solo. Puedes subir el PDF o pegar su enlace directo "
            "y se incluirá en la búsqueda."
        )
    h1, h2 = st.columns(2)
    hch_archivo = h1.file_uploader("Volante PDF de Hipódromo Chile", type="pdf")
    hch_url = h2.text_input("…o enlace directo al PDF")
    if st.button("Actualizar datos ahora"):
        st.cache_data.clear()
        st.rerun()

fechas = [HOY + dt.timedelta(days=i) for i in range(dias + 1)]

# --------------------------------------------------------------------------
# Cargar reuniones
# --------------------------------------------------------------------------
filas, avisos = [], []
total = len(fechas) * (int(H.HIP_SPORTING in hips) + int(H.HIP_CHS in hips)
                       + int(H.HIP_HCH in hips and bool(HCH_URL_TEMPLATE)))
barra = st.progress(0.0, text="Buscando reuniones…") if total else None
hecho = 0
for f in fechas:
    iso = f.isoformat()
    if H.HIP_SPORTING in hips:
        r, a = cargar_sporting(iso)
        filas += r
        avisos += [a] if a else []
        hecho += 1
        barra.progress(hecho / total, text=f"Valparaíso Sporting {f:%d-%m}…")
    if H.HIP_CHS in hips:
        r, a = cargar_chs(iso)
        filas += r
        avisos += [a] if a else []
        hecho += 1
        barra.progress(hecho / total, text=f"Club Hípico {f:%d-%m}…")
    if H.HIP_HCH in hips and HCH_URL_TEMPLATE:
        r, a = cargar_hch_plantilla(HCH_URL_TEMPLATE, iso)
        filas += r
        avisos += [a] if a else []
        hecho += 1
        barra.progress(hecho / total, text=f"Hipódromo Chile {f:%d-%m}…")
if barra:
    barra.empty()

# Hipódromo Chile manual
if H.HIP_HCH in hips:
    try:
        if hch_archivo is not None:
            filas += leer_hch_pdf(hch_archivo.getvalue())
        elif hch_url.strip():
            filas += leer_hch_pdf(bajar_pdf(hch_url.strip()))
    except Exception as e:  # noqa: BLE001
        avisos.append(f"Hipódromo Chile: no se pudo leer el volante ({e}).")

df = H.a_dataframe(filas)

# --------------------------------------------------------------------------
# Resultados
# --------------------------------------------------------------------------
if df.empty:
    st.warning(
        "No encontré reuniones en las fechas elegidas. Prueba con más días en «Opciones», "
        "o revisa si hay carreras programadas."
    )
    for a in avisos:
        st.caption("⚠️ " + a)
    st.stop()

reuniones = (
    df.groupby(["fecha", "hipodromo"])
    .agg(carreras=("carrera", "nunique"), caballos=("caballo", "count"))
    .reset_index()
)

if not consulta.strip():
    st.subheader("Reuniones cargadas")
    mostrar = reuniones.assign(fecha=reuniones.fecha.map(fmt_fecha)).rename(columns={
        "fecha": "Fecha", "hipodromo": "Hipódromo", "carreras": "Carreras", "caballos": "Caballos"})
    st.dataframe(mostrar, hide_index=True, width="stretch")
    st.info("Escribe arriba lo que quieres buscar. Por ejemplo un criadero: **Haras Santa Mónica**.")
else:
    res = H.buscar(df, consulta, campo, exacta)
    if res.empty:
        st.error(f"No encontré «{consulta}» en las {len(reuniones)} reuniones revisadas.")
        sug = H.sugerencias(df, consulta, campo)
        if sug:
            st.write("¿Quisiste decir…?")
            for s in sug:
                st.write("• " + s)
    else:
        n_reu = res.groupby(["fecha", "hipodromo"]).ngroups
        st.success(f"**{len(res)}** caballo(s) en **{n_reu}** reunión(es) para «{consulta}».")

        # Nombres distintos que coincidieron (para detectar confusiones, p. ej. 'Santa' -> varios haras)
        detalle = []
        for c in H.CAMPOS_BUSQUEDA[campo]:
            vals = res.loc[res.coincide_en.str.contains(c), c]
            distintos = {}
            for v in vals:
                distintos.setdefault(H.norm(v, quitar_genericas=(c == "criador")), []).append(v)
            if distintos:
                detalle.append((c, distintos))
        for c, distintos in detalle:
            if len(distintos) > 1:
                nombres = ", ".join(f"{v[0]} ({len(v)})" for v in distintos.values())
                st.warning(f"La búsqueda coincidió con varios nombres en **{c}**: {nombres}. "
                           "Si buscas uno solo, escribe el nombre completo y marca «Nombre exacto».")

        tabla = res.assign(fecha=res.fecha.map(fmt_fecha)).rename(columns={
            "fecha": "Fecha", "hipodromo": "Hipódromo", "reunion": "Reunión", "carrera": "Carrera",
            "hora": "Hora", "prueba": "Prueba", "distancia": "Distancia", "mandil": "Nº",
            "caballo": "Caballo", "jinete": "Jinete", "preparador": "Preparador",
            "stud": "Stud", "criador": "Criador (haras)", "padres": "Padres",
            "coincide_en": "Coincide en"})
        orden = ["Fecha", "Hipódromo", "Carrera", "Hora", "Prueba", "Distancia", "Nº", "Caballo",
                 "Jinete", "Preparador", "Stud", "Criador (haras)", "Coincide en"]
        st.dataframe(tabla[orden], hide_index=True, width="stretch")
        st.download_button("Descargar resultados (CSV)",
                           tabla[orden].to_csv(index=False).encode("utf-8-sig"),
                           file_name="resultados_hipica.csv", mime="text/csv")

    with st.expander(f"Reuniones revisadas ({len(reuniones)})"):
        st.dataframe(
            reuniones.assign(fecha=reuniones.fecha.map(fmt_fecha)).rename(columns={
                "fecha": "Fecha", "hipodromo": "Hipódromo", "carreras": "Carreras", "caballos": "Caballos"}),
            hide_index=True, width="stretch")

if avisos:
    with st.expander(f"⚠️ Avisos ({len(avisos)})"):
        for a in avisos:
            st.write(a)

st.divider()
st.caption(
    "Los programas son los oficiales publicados por cada hipódromo; los retiros de última hora no "
    "aparecen aquí, confírmalos en el sitio del hipódromo antes de decidir. Datos actualizados cada 30 min. "
    f"Fecha de hoy: {HOY:%d-%m-%Y}. Herramienta independiente, sin relación con los hipódromos."
)
