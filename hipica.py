"""
hipica.py - Descarga y lectura de programas de carreras de caballos de Chile
y buscador por caballo, criador (haras), jinete, preparador y stud.

Fuentes:
  - Valparaíso Sporting : páginas HTML por carrera (campo "Haras" = criador).
  - Club Hípico Santiago: PDF del volante en static.clubhipico.cl/archivos/volantes/DD-MM-AAAA.pdf
  - Hipódromo Chile     : PDF del volante (se entrega por URL o archivo).

Todas las funciones devuelven filas con las mismas columnas (ver COLUMNAS).
"""
from __future__ import annotations

import datetime as dt
import io
import re
import subprocess
import tempfile
import unicodedata
from concurrent.futures import ThreadPoolExecutor

import pandas as pd
import requests
from bs4 import BeautifulSoup

COLUMNAS = [
    "fecha", "hipodromo", "reunion", "carrera", "hora", "prueba", "distancia",
    "mandil", "caballo", "jinete", "preparador", "stud", "criador", "padres",
]

HIP_SPORTING = "Valparaíso Sporting"
HIP_CHS = "Club Hípico de Santiago"
HIP_HCH = "Hipódromo Chile"

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; BuscadorHipicaChile/1.0)"}
TIMEOUT = 25

MESES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10,
    "noviembre": 11, "diciembre": 12,
}


# --------------------------------------------------------------------------
# Utilidades de texto
# --------------------------------------------------------------------------
def quitar_tildes(s: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn"
    )


# Palabras que no distinguen a un criador ("Haras X", "H. X", "Criadero X").
_GENERICAS = {"haras", "hras", "h", "hs", "criadero", "criaderos", "stud", "sta", "st"}


def norm(s: str, quitar_genericas: bool = False) -> str:
    """Minúsculas, sin tildes ni signos. 'Sta.' -> 'santa'."""
    s = quitar_tildes(str(s or "")).lower()
    s = re.sub(r"[^a-z0-9ñ]+", " ", s)
    toks = []
    for t in s.split():
        if t in ("sta",):
            t = "santa"
        if quitar_genericas and t in _GENERICAS:
            continue
        toks.append(t)
    return " ".join(toks)


def limpiar_persona(s: str) -> str:
    """Quita estadísticas pegadas ('1c 14v') y puntos sobrantes de un nombre."""
    s = re.sub(r"\s+", " ", str(s or "")).strip()
    s = re.sub(r"(?:\s+\d+(?:c|ch|m|v)\b)+\s*$", "", s)   # 21c 26ch 39v
    s = re.sub(r"\.\.+", ".", s)
    if re.search(r"[A-Za-zÁÉÍÓÚÑáéíóúñ]{3,}\.$", s):         # 'Sergio Salazar.' -> sin punto
        s = s[:-1]
    return s.strip()


def espaciar_iniciales(s: str) -> str:
    """'L.P.Silva' -> 'L. P. Silva'."""
    return re.sub(r"(?<=\.)(?=[A-Za-zÁÉÍÓÚÑ])", " ", s).strip()


def titulo(s: str) -> str:
    """'BLACK KINGLY' -> 'Black Kingly' (respeta '(ARG)')."""
    s = s.strip().lower().title()
    return re.sub(r"\((\w+)\)", lambda m: "(" + m.group(1).upper() + ")", s)


def fila(**kw) -> dict:
    d = {c: "" for c in COLUMNAS}
    d.update(kw)
    return d


# --------------------------------------------------------------------------
# HTTP
# --------------------------------------------------------------------------
def http_get(url: str) -> requests.Response:
    r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
    return r


# --------------------------------------------------------------------------
# PDF -> texto
# --------------------------------------------------------------------------
def pdf_paginas_layout(pdf_bytes: bytes) -> list[str]:
    """Texto por página conservando el diseño (pdftotext -layout)."""
    with tempfile.NamedTemporaryFile(suffix=".pdf") as f:
        f.write(pdf_bytes)
        f.flush()
        try:
            out = subprocess.run(
                ["pdftotext", "-layout", f.name, "-"],
                capture_output=True, check=True, timeout=180,
            ).stdout.decode("utf-8", "replace")
            return out.split("\f")
        except (FileNotFoundError, subprocess.CalledProcessError):
            pass
    # Respaldo si no existe poppler: más lento y menos fiel
    import pdfplumber
    paginas = []
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for p in pdf.pages:
            paginas.append(p.extract_text(layout=True) or "")
    return paginas


def _fecha_es(texto: str):
    """Primera fecha tipo '3 de Octubre de 2026' o '5 de octubre del año 2026'."""
    m = re.search(r"(\d{1,2})\s+de\s+([A-Za-zñÑáéíóú]+)\s+(?:de|del año)\s+(?:año\s+)?(\d{4})", texto)
    if not m:
        return None
    mes = MESES.get(quitar_tildes(m.group(2)).lower())
    if not mes:
        return None
    try:
        return dt.date(int(m.group(3)), mes, int(m.group(1)))
    except ValueError:
        return None


def corregir_horas(filas: list[dict]) -> list[dict]:
    """Si una carrera figura con una hora muy posterior a la siguiente (p.ej. 22:30 antes de 11:20),
    es un error de impresión de 12 h: se corrige restando 12 horas."""
    por_carrera = {}
    for f in filas:
        if f["carrera"] and f["hora"] and f["carrera"] not in por_carrera:
            por_carrera[f["carrera"]] = f["hora"]
    orden = sorted(por_carrera, key=lambda c: int(c))
    def minutos(h):
        a, b = h.split(":")
        return int(a) * 60 + int(b)
    nuevas = dict(por_carrera)
    for i, c in enumerate(orden[:-1]):
        sig = minutos(nuevas[orden[i + 1]]) if orden[i + 1] in nuevas else None
        cur = minutos(por_carrera[c])
        # comparar contra la mediana de las horas siguientes
        siguientes = [minutos(por_carrera[x]) for x in orden[i + 1:i + 4]]
        if siguientes and cur - min(siguientes) > 6 * 60:
            h, m = divmod(cur - 12 * 60, 60)
            nuevas[c] = f"{h:02d}:{m:02d}"
    for f in filas:
        if f["carrera"] in nuevas:
            f["hora"] = nuevas[f["carrera"]]
    return filas


# ==========================================================================
# HIPÓDROMO CHILE  (volante PDF)
# ==========================================================================
_RE_HCH_HORA = re.compile(r"(\d{1,2}:\d{2})\s+hrs\.\s+NOM\.\s+PREMIO:\s*(.*?)\s*$")
_RE_HCH_CARRERA = re.compile(r"^\s*(\d{1,2})ª")
_RE_HCH_CABALLO = re.compile(
    r"^\s{2,}(\d{1,2})\s{2,}([A-ZÁÉÍÓÚÑ][A-ZÁÉÍÓÚÑ0-9'’.\-&() ]*?)\s{2,}(?:\d|\()"
)
_RE_HCH_JINETE = re.compile(r"^\s*\([A-Z]\.[A-Z]\.\)\s+(?:\(\s*\d+\)\s+)?\d+\s+[\d,]+\s+\d+\s+(.+)$")
_RE_HCH_STUD = re.compile(r"^\s*<<\s*(.+?)\s*>>")
_RE_PAREN_FINAL = re.compile(r"\(\s*([^()]*?)\s*\)\s*$")


def parse_hch(pdf_bytes: bytes) -> list[dict]:
    paginas = pdf_paginas_layout(pdf_bytes)
    texto = "\n".join(paginas)
    lineas = texto.split("\n")
    fecha = _fecha_es(texto[:3000]) or _fecha_es(texto)
    m = re.search(r"REUNION\s+N[ºo°]?\s*(\d+)", texto[:3000], re.I)
    reunion = m.group(1) if m else ""

    # Posiciones de encabezados de carrera y de caballos
    carrera = hora = prueba = ""
    i_hdr = []
    for i, l in enumerate(lineas):
        if _RE_HCH_HORA.search(l):
            i_hdr.append(i)
    # Mapa línea -> contexto de carrera
    ctx = {}
    for i in i_hdr:
        mh = _RE_HCH_HORA.search(lineas[i])
        num = ""
        for j in range(i, min(i + 8, len(lineas))):
            mc = _RE_HCH_CARRERA.match(lineas[j])
            if mc:
                num = mc.group(1)
                break
        ctx[i] = (num, mh.group(1), mh.group(2).strip())

    filas = []
    n = len(lineas)
    inicio_caballo = []
    for i, l in enumerate(lineas):
        if _RE_HCH_CABALLO.match(l):
            inicio_caballo.append(i)
    inicio_caballo_set = set(inicio_caballo)
    hdrs_ordenados = sorted(i_hdr)

    for idx, i in enumerate(inicio_caballo):
        # carrera vigente = último encabezado antes de esta línea
        previos = [h for h in hdrs_ordenados if h < i]
        if not previos:
            continue
        carrera, hora, prueba = ctx[previos[-1]]
        mm = _RE_HCH_CABALLO.match(lineas[i])
        mandil, nombre = mm.group(1), mm.group(2).strip()
        limite = inicio_caballo[idx + 1] if idx + 1 < len(inicio_caballo) else n
        # no cruzar al siguiente encabezado de carrera
        sig_hdr = [h for h in hdrs_ordenados if h > i]
        if sig_hdr:
            limite = min(limite, sig_hdr[0])

        jinete = prep = padres = criador = stud = ""
        for j in range(i + 1, min(i + 6, limite)):
            mj = _RE_HCH_JINETE.match(lineas[j])
            if mj:
                partes = [p for p in re.split(r"\s{2,}", mj.group(1).strip()) if p]
                if partes:
                    jinete = espaciar_iniciales(partes[0])
                    ultimo = partes[-1]
                    if len(partes) > 1 and re.search(r"[A-Za-z]{2}", ultimo) and not re.match(r"^\(?\d", ultimo):
                        prep = ultimo
                # línea de padres/haras: la siguiente con paréntesis final
                for k in range(j + 1, min(j + 4, limite)):
                    mp = _RE_PAREN_FINAL.search(lineas[k])
                    if mp and (" por " in lineas[k] or " y " in lineas[k]):
                        criador = mp.group(1).strip()
                        padres = lineas[k][: mp.start()].strip()
                        break
                break
        for j in range(i + 1, limite):
            ms = _RE_HCH_STUD.match(lineas[j])
            if ms:
                stud = titulo(ms.group(1))
                break
        filas.append(fila(
            fecha=fecha.isoformat() if fecha else "", hipodromo=HIP_HCH, reunion=reunion,
            carrera=carrera, hora=hora, prueba=prueba, mandil=mandil,
            caballo=titulo(nombre), jinete=jinete, preparador=prep, stud=stud,
            criador=criador, padres=padres,
        ))
    return corregir_horas(filas)


# ==========================================================================
# CLUB HÍPICO DE SANTIAGO  (volante PDF)
# ==========================================================================
def chs_url(fecha: dt.date) -> str:
    return f"https://static.clubhipico.cl/archivos/volantes/{fecha:%d-%m-%Y}.pdf"


def descargar_chs(fecha: dt.date) -> bytes | None:
    """Devuelve el PDF del día, o None si no hay reunión ese día."""
    r = http_get(chs_url(fecha))
    if r.status_code == 200 and r.content[:4] == b"%PDF":
        return r.content
    return None


def _lineas_columna(pagina, x0, x1) -> list[str]:
    recorte = pagina.crop((x0, 0, x1, pagina.height))
    txt = recorte.extract_text(x_tolerance=1.5) or ""
    return [l.strip() for l in txt.split("\n") if l.strip()]


_RE_CHS_REFS = re.compile(r"(\d{1,2})ª\s+(\d{1,2})")


def _leer_indice(lineas: list[str]) -> dict[str, list[tuple[str, str]]]:
    """Índice 'NOMBRE  14ª 3  15ª 5' -> {nombre: [(carrera, mandil)]}.
    El nombre puede venir solo en una línea y las referencias en la siguiente;
    las referencias pueden continuar en varias líneas (y pasar a la otra columna)."""
    res: dict[str, list[tuple[str, str]]] = {}
    actual = None
    for l in lineas:
        if l.startswith(("CHS Reunión", "Indice de", "Criador", "Preparador", "Jinete", "Carrera N")):
            continue
        refs = _RE_CHS_REFS.findall(l)
        primera = _RE_CHS_REFS.search(l)
        nombre = l[: primera.start()].strip() if primera else l.strip()
        if refs:
            if nombre:
                actual = nombre
                res.setdefault(actual, [])
            if actual is not None:
                res[actual].extend(refs)
        else:
            # línea sólo con nombre (o con la continuación de un nombre largo)
            if actual is not None and not res.get(actual):
                nuevo_nombre = f"{actual} {nombre}"
                res[nuevo_nombre] = res.pop(actual)
                actual = nuevo_nombre
            else:
                actual = nombre
                res.setdefault(actual, [])
    return res


def parse_chs(pdf_bytes: bytes) -> list[dict]:
    import pdfplumber

    paginas = pdf_paginas_layout(pdf_bytes)
    texto = "\n".join(paginas)
    fecha = _fecha_es(texto[:2000]) or _fecha_es(texto)
    m = re.search(r"Reuni[oó]n\s+(\d+)", texto[:2000])
    reunion = m.group(1) if m else ""

    idx_listado, idx_prep, idx_crit, idx_programa = [], [], [], []
    for i, p in enumerate(paginas):
        cab = "\n".join(p.split("\n")[:4])
        if "Ejemplares por Carrera" in cab:
            idx_listado.append(i)
        if "Indice de Preparadores" in cab:
            idx_prep.append(i)
        if "Indice de Criadores" in cab:
            idx_crit.append(i)
        if "Programa de Hoy" in cab:
            idx_programa.append(i)

    # ---- Programa de hoy: prueba, distancia, condición -------------------
    info_carrera: dict[str, dict] = {}
    for i in idx_programa:
        for l in paginas[i].split("\n"):
            mm = re.match(
                r"^\s*(\d+)ª\s+(\d{1,2}:\d{2})\s+(.+?)\s+(\d{3,4})m\s+(.*?)\s+\$[\d.]+\s*$", l)
            if mm:
                info_carrera[mm.group(1)] = dict(
                    hora=mm.group(2), prueba=titulo(mm.group(3)),
                    distancia=mm.group(4) + " m", cond=re.sub(r"\s{2,}", " ", mm.group(5)))

    horses: dict[tuple[str, str], dict] = {}
    criadores: dict[str, list] = {}
    preparadores: dict[str, list] = {}

    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        mitad = pdf.pages[0].width / 2 - 2

        def col(pn, lado):
            p = pdf.pages[pn]
            return _lineas_columna(p, 0, mitad) if lado == 0 else _lineas_columna(p, mitad, p.width)

        # ---- Listado de ejemplares por carrera (dos columnas) ------------
        flujo = []
        for pn in idx_listado:
            flujo += col(pn, 0) + col(pn, 1)
        carrera_act = ""
        for l in flujo:
            mc = re.match(r"^(\d{1,2})ª\s+(\d{1,2}:\d{2})\b", l)
            if mc:
                carrera_act = mc.group(1)
                continue
            mh = re.match(r"^(\d{1,2})\s+(.+?)\s+G\d\s+(\d{2,3})\s+(.+)$", l)
            if mh and carrera_act:
                horses[(carrera_act, mh.group(1))] = dict(
                    caballo=titulo(mh.group(2)), jinete=titulo(mh.group(4)))

        # ---- Índice de preparadores (columna izquierda) ------------------
        flujo = []
        for pn in idx_prep:
            flujo += col(pn, 0)
        preparadores = _leer_indice(flujo)

        # ---- Índice de criadores (izquierda y luego derecha) -------------
        flujo = []
        for pn in idx_crit:
            flujo += col(pn, 0) + col(pn, 1)
        criadores = _leer_indice(flujo)

    prep_de, crit_de = {}, {}
    for nombre, refs in preparadores.items():
        nom = re.sub(r"^\(\w+\)\s*", "", nombre)          # '(AP) JOSE ARAYA B.'
        for r in refs:
            prep_de[r] = titulo(nom)
    for nombre, refs in criadores.items():
        for r in refs:
            crit_de[r] = titulo(nombre)

    # ---- Studs desde las fichas: 'NOMBRE (h, c, 5)  JIN: ...  STUD: «X»' ---
    stud_de: dict[str, str] = {}
    nombre_ficha = None
    for l in texto.split("\n"):
        mf = re.match(r"^\s{6,}(.+?)\s+(?:\([A-Za-z ]+\)\s+)?\(([a-z]),\s*[a-z]+,\s*\d+\)\s+JIN:", l)
        if mf:
            nombre_ficha = norm(re.sub(r"\(.*?\)", "", mf.group(1)))
        ms = re.search(r"STUD:\s*[«\"]\s*(.+?)\s*[»\"]", l)
        if ms and nombre_ficha:
            stud_de.setdefault(nombre_ficha, titulo(ms.group(1)))

    filas = []
    for (car, mandil), h in sorted(horses.items(), key=lambda kv: (int(kv[0][0]), int(kv[0][1]))):
        info = info_carrera.get(car, {})
        filas.append(fila(
            fecha=fecha.isoformat() if fecha else "", hipodromo=HIP_CHS, reunion=reunion,
            carrera=car, hora=info.get("hora", ""), prueba=info.get("prueba", ""),
            distancia=info.get("distancia", ""), mandil=mandil, caballo=h["caballo"],
            jinete=h["jinete"], preparador=prep_de.get((car, mandil), ""),
            stud=stud_de.get(norm(re.sub(r"\(.*?\)", "", h["caballo"])), ""), criador=crit_de.get((car, mandil), ""),
        ))
    return filas


# ==========================================================================
# VALPARAÍSO SPORTING  (HTML)
# ==========================================================================
SPORTING_BASE = "https://www.sporting.cl/hipica/front/es"


def sporting_reunion_url(fecha: dt.date) -> str:
    return f"{SPORTING_BASE}/reunion/{fecha:%Y-%m-%d}.html"


def sporting_programa_url(fecha: dt.date, n: int) -> str:
    return f"{SPORTING_BASE}/programa/{fecha:%Y-%m-%d}/{n:02d}.html"


def sporting_carreras_de_reunion(html: str, fecha: dt.date) -> tuple[list[int], str]:
    """Números de carrera enlazados en la página de la reunión y nº de reunión."""
    ds = fecha.strftime("%Y-%m-%d")
    nums = sorted({int(n) for n in re.findall(rf"/programa/{ds}/(\d{{2}})\.html", html)})
    texto = BeautifulSoup(html, "lxml").get_text(" ", strip=True)
    m = re.search(r"N[ºo°]\s*(\d+)\s*-\s*[A-Za-zÁÉÍÓÚáéíóú]+\s+\d+", texto)
    return nums, (m.group(1) if m else "")


_RE_SP_FICHA = re.compile(
    r"Edad:\s*(?P<edad>.+?)\s+Stud:\s*(?P<stud>.+?)\s+Padres:\s*(?P<padres>.+?)\s+"
    r"Haras:\s*(?P<haras>.+?)\s+Preparador:\s*(?P<prep>.+?)\s+Jinete:\s*(?P<jinete>.+?)\s+"
    r"Peso:"
)


def parse_sporting_carrera(html: str, fecha: dt.date, reunion: str = "") -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    for t in soup(["script", "style"]):
        t.decompose()

    # cada ejemplar es un enlace a /ejemplares/<id>.html
    for a in soup.find_all("a", href=re.compile(r"/ejemplares/\d+\.html")):
        nombre = a.get_text(" ", strip=True)
        a.replace_with(f" ¤¤{nombre}¤¤ ")
    texto = re.sub(r"\s+", " ", soup.get_text(" ", strip=True))

    mc = re.search(
        r"(\d+)ª\s*Carrera\s*-\s*Premio\s*[\"“«]?\s*(.+?)\s*[\"”»]?\s+(\d{1,2}:\d{2})\s*hrs", texto)
    carrera, prueba, hora = (mc.group(1), mc.group(2), mc.group(3)) if mc else ("", "", "")
    md = re.search(r"Distancia\s*/\s*Tipo Pista:\s*([\d.]+)\s*mts", texto)
    distancia = (md.group(1) + " m") if md else ""

    partes = re.split(r"¤¤(.+?)¤¤", texto)
    # partes = [antes, nombre1, seg1, nombre2, seg2, ...]
    filas = []
    previo = partes[0] if partes else ""
    for k in range(1, len(partes) - 1, 2):
        nombre, seg = partes[k], partes[k + 1]
        mf = _RE_SP_FICHA.search(seg)
        if not mf:
            previo = seg
            continue
        mm = re.search(r"(\d{1,2})\s+[A-Za-zÁÉÍÓÚáéíóúñÑ]+(?:\s+[A-Za-zÁÉÍÓÚáéíóúñÑ]+)?\s*$", previo[-80:])
        mandil = mm.group(1) if mm else str((k + 1) // 2)
        filas.append(fila(
            fecha=fecha.isoformat(), hipodromo=HIP_SPORTING, reunion=reunion,
            carrera=carrera, hora=hora, prueba=prueba, distancia=distancia,
            mandil=mandil, caballo=nombre.strip(),
            jinete=limpiar_persona(mf.group("jinete")),
            preparador=limpiar_persona(mf.group("prep")),
            stud=mf.group("stud").strip(), criador=mf.group("haras").strip(),
            padres=mf.group("padres").strip(),
        ))
        previo = seg
    return filas


def cargar_sporting(fecha: dt.date) -> tuple[list[dict], str]:
    """Todos los ejemplares de la reunión de Sporting de esa fecha (vacío si no hay reunión)."""
    r = http_get(sporting_reunion_url(fecha))
    if r.status_code == 404:
        return [], ""                       # ese día no hay reunión
    if r.status_code != 200:
        return [], f"Sporting {fecha:%d-%m}: el sitio respondió HTTP {r.status_code}."
    nums, reunion = sporting_carreras_de_reunion(r.text, fecha)
    if not nums:
        return [], ""

    def una(n):
        rr = http_get(sporting_programa_url(fecha, n))
        rr.raise_for_status()
        return parse_sporting_carrera(rr.text, fecha, reunion)

    filas, aviso = [], ""
    with ThreadPoolExecutor(max_workers=5) as ex:
        for n, res in zip(nums, ex.map(lambda x: _seguro(una, x), nums)):
            if isinstance(res, Exception):
                aviso += f"Sporting {fecha:%d-%m} carrera {n}: {res}. "
            else:
                if not res:
                    aviso += f"Sporting {fecha:%d-%m} carrera {n}: no se leyeron ejemplares. "
                filas += res
    return filas, aviso


def _seguro(fn, x):
    try:
        return fn(x)
    except Exception as e:  # noqa: BLE001
        return e


# ==========================================================================
# Búsqueda
# ==========================================================================
CAMPOS_BUSQUEDA = {
    "Todo": ["caballo", "criador", "jinete", "preparador", "stud"],
    "Caballo": ["caballo"],
    "Criador (haras)": ["criador"],
    "Jinete": ["jinete"],
    "Preparador": ["preparador"],
    "Stud": ["stud"],
}


def _coincide(valor: str, tokens: list[str], exacta: bool, campo: str) -> bool:
    if not valor:
        return False
    generica = campo == "criador"
    v = norm(valor, quitar_genericas=generica)
    if exacta:
        return v == " ".join(tokens)
    palabras = v.split()
    return all(any(p.startswith(t) for p in palabras) for t in tokens)


def buscar(df: pd.DataFrame, consulta: str, campo: str = "Todo", exacta: bool = False) -> pd.DataFrame:
    """Filtra df. Cada palabra de la consulta debe coincidir (por inicio de palabra)
    dentro de un mismo campo. Agrega la columna 'coincide_en'."""
    if df.empty or not consulta.strip():
        return df.iloc[0:0].assign(coincide_en="")
    campos = CAMPOS_BUSQUEDA[campo]
    tokens_gen = norm(consulta, quitar_genericas=True).split()
    tokens_raw = norm(consulta).split()
    filas, motivos = [], []
    for idx, r in df.iterrows():
        hallado = []
        for c in campos:
            toks = tokens_gen if (c == "criador" and tokens_gen) else tokens_raw
            if toks and _coincide(r[c], toks, exacta, c):
                hallado.append(c)
        if hallado:
            filas.append(idx)
            motivos.append(", ".join(hallado))
    out = df.loc[filas].copy()
    out["coincide_en"] = motivos
    return out


def sugerencias(df: pd.DataFrame, consulta: str, campo: str = "Todo", n: int = 5) -> list[str]:
    """Nombres parecidos cuando no hay resultados."""
    from rapidfuzz import fuzz, process

    valores = set()
    for c in CAMPOS_BUSQUEDA[campo]:
        valores |= {v for v in df[c].unique() if v}
    if not valores:
        return []
    q = norm(consulta, quitar_genericas=True)
    mapa = {v: norm(v, quitar_genericas=True) for v in valores}
    res = process.extract(q, mapa, scorer=fuzz.WRatio, limit=n)
    return [k for (_, score, k) in res if score >= 70]


def a_dataframe(filas: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(filas, columns=COLUMNAS)
    if not df.empty:
        df["_c"] = pd.to_numeric(df["carrera"], errors="coerce")
        df["_m"] = pd.to_numeric(df["mandil"], errors="coerce")
        df = df.sort_values(["fecha", "hipodromo", "_c", "_m"]).drop(columns=["_c", "_m"])
        df = df.reset_index(drop=True)
    return df
