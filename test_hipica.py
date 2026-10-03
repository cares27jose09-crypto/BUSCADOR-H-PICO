"""Pruebas: python test_hipica.py   (o pytest)

Las de Sporting usan una réplica de la estructura de sus páginas (no hay acceso a
internet en este entorno). Las de PDF se omiten si no están los archivos de ejemplo.
"""
import datetime as dt
import os

import hipica as H

FECHA = dt.date(2026, 10, 7)

HTML_CARRERA = """
<html><body>
<nav><a href="https://www.sporting.cl/hipica/front/es/ejemplares/buscador.html">Ejemplares</a></nav>
<h3>Reunión: <strong>Nº61 (3871) - Miércoles 7, Octubre 2026</strong></h3>
<select><option>Kelis</option><option>Dulce Tormenta</option><option>La Carmela</option></select>
<h1>2ª Carrera - Premio "Essen"</h1>
<p>14:00 hrs. aprox.</p>
<ul><li>Tipo: <strong>Condicional</strong></li>
<li>Condición: <strong>Para Hembras De 3 Años</strong></li>
<li>Distancia / Tipo Pista: <strong>1100mts / Arena</strong></li></ul>
<h2>Ejemplares:</h2>

<div>1</div><div>Rojo</div><img alt="casaquilla" src="x.png">
<h2><a href="https://www.sporting.cl/hipica/front/es/ejemplares/45446.html">Kelis</a></h2>
<p>(421k) (I:)</p>
<ul><li>Edad: <strong>HM 3a</strong></li><li>Stud: <strong>Nohelia</strong></li>
<li>Padres: <strong>Kingly (usa) y Ernesta por Ernest Hemingway</strong></li>
<li>Haras: <strong>H. Mocito Guapo</strong></li>
<li>Preparador: <strong>Rafael Bernal T.. 9ch 33v</strong></li>
<li>Jinete: <strong><a href="https://www.sporting.cl/hipica/front/es/jinete/475.html">Benjamin Sancho</a> 38c 32ch 37v</strong></li>
<li>Peso: <strong>57k</strong></li><li>Aperos: <strong>NADA</strong></li></ul>
<table><tr><th>Fecha</th><th>Ganador</th><th>Video</th></tr>
<tr><td>28-09-2026</td><td>La Fajita - (1 1/2) La Carmela - (4 3/4) La Clara</td><td>Ver video de la Carrera</td></tr></table>

<div>2</div><div>Azul Marino</div><img alt="casaquilla" src="y.png">
<h2><a href="https://www.sporting.cl/hipica/front/es/ejemplares/45797.html">Dulce Tormenta</a></h2>
<p>(430k) (I:)</p>
<ul><li>Edad: <strong>HM 3a</strong></li><li>Stud: <strong>Pobre Obrero</strong></li>
<li>Padres: <strong>Gstaad Ii y Halloween Day por A. P. Five Hundred</strong></li>
<li>Haras: <strong>H. Santa Monica</strong></li>
<li>Preparador: <strong>Guillermo Perez. 8v</strong></li>
<li>Jinete: <strong><a href="https://www.sporting.cl/hipica/front/es/jinete/635.html">Juan Tapia</a></strong></li>
<li>Peso: <strong>57k</strong></li><li>Aperos: <strong>NADA</strong></li></ul>
<table><tr><td>16-09-2026</td><td>Cuando Vuelves - (2 3/4) La Chavela - (5 1/2) Brangelina</td></tr></table>

<div>3</div><div>Verde Claro</div><img alt="casaquilla" src="z.png">
<h2><a href="https://www.sporting.cl/hipica/front/es/ejemplares/45609.html">La Carmela</a></h2>
<ul><li>Edad: <strong>HC 3a</strong></li><li>Stud: <strong>Haras Don Luis</strong></li>
<li>Padres: <strong>Alfonso (usa) y Bella Carmela por Gstaad Ii</strong></li>
<li>Haras: <strong>H. Don Luis</strong></li>
<li>Preparador: <strong>Rafael Bernal T.. 9ch 33v</strong></li>
<li>Jinete: <strong><a href="/jinete/500.html">Joaquin Herrera</a> 94c 84ch 67v</strong></li>
<li>Peso: <strong>57k</strong></li></ul>
</body></html>
"""

HTML_REUNION = """
<h1>Nº61 - Miércoles 7, Octubre 2026</h1><table>
<tr><td>1</td><td><a href="https://www.sporting.cl/hipica/front/es/programa/2026-10-07/01.html">Programa</a></td></tr>
<tr><td>2</td><td><a href="/hipica/front/es/programa/2026-10-07/02.html">Programa</a></td></tr>
<tr><td>3</td><td><a href="https://www.sporting.cl/hipica/front/es/programa/2026-10-07/03.html">Programa</a></td></tr>
</table>
"""


def test_sporting_carrera():
    f = H.parse_sporting_carrera(HTML_CARRERA, FECHA, "61")
    assert len(f) == 3
    k, d, c = f
    assert (k["carrera"], k["hora"], k["prueba"], k["distancia"]) == ("2", "14:00", "Essen", "1100 m")
    assert [x["mandil"] for x in f] == ["1", "2", "3"]
    assert d["caballo"] == "Dulce Tormenta"
    assert d["criador"] == "H. Santa Monica"
    assert d["jinete"] == "Juan Tapia"
    assert d["preparador"] == "Guillermo Perez"
    assert d["stud"] == "Pobre Obrero"
    assert k["jinete"] == "Benjamin Sancho"
    assert k["preparador"] == "Rafael Bernal T."
    assert c["jinete"] == "Joaquin Herrera"


def test_sporting_reunion():
    nums, reunion = H.sporting_carreras_de_reunion(HTML_REUNION, FECHA)
    assert nums == [1, 2, 3]
    assert reunion == "61"


def test_busqueda_criador():
    df = H.a_dataframe(H.parse_sporting_carrera(HTML_CARRERA, FECHA, "61"))
    # "Haras Santa Mónica" encuentra "H. Santa Monica" (haras/h. no cuentan, tildes ignoradas)
    r = H.buscar(df, "Haras Santa Mónica", "Criador (haras)")
    assert r.caballo.tolist() == ["Dulce Tormenta"]
    # "Santa Marta"/"Santa Olga" no deben confundirse con Santa Mónica
    assert H.buscar(df, "Santa Marta", "Criador (haras)").empty
    # por jinete, preparador, stud y caballo
    assert H.buscar(df, "tapia", "Jinete").caballo.tolist() == ["Dulce Tormenta"]
    assert len(H.buscar(df, "Bernal", "Preparador")) == 2
    assert H.buscar(df, "pobre obrero", "Stud").caballo.tolist() == ["Dulce Tormenta"]
    assert H.buscar(df, "kelis", "Caballo").caballo.tolist() == ["Kelis"]
    # modo "Todo" busca en todos los campos
    assert "Dulce Tormenta" in H.buscar(df, "santa monica").caballo.tolist()
    # sugerencias cuando se escribe mal
    assert any("Santa Monica" in s for s in H.sugerencias(df, "Santa Monika", "Criador (haras)"))


def test_normalizacion():
    assert H.norm("H. Sta. Mónica", True) == "santa monica"
    assert H.norm("HARAS SANTA MONICA", True) == "santa monica"
    assert H.limpiar_persona("Luis Salinas T.. 19v") == "Luis Salinas T."
    assert H.limpiar_persona("Sergio Salazar. 1c 14v") == "Sergio Salazar"
    assert H.espaciar_iniciales("L.P.Silva") == "L. P. Silva"


def _pdf(ruta):
    return open(ruta, "rb").read() if os.path.exists(ruta) else None


def test_pdf_hch_si_existe():
    b = _pdf("/mnt/user-data/uploads/102133.pdf")
    if not b:
        return
    df = H.a_dataframe(H.parse_hch(b))
    assert len(df) == 362 and df.carrera.nunique() == 25
    r = H.buscar(df, "Haras Santa Mónica", "Criador (haras)")
    assert sorted(r.caballo) == sorted(
        ["Black Kingly", "Yo No Vine A Esto", "Cappo Di Cappo", "Tio Juan", "Beast Mode", "Potro De Lampa"])


def test_pdf_chs_si_existe():
    b = _pdf("/mnt/user-data/uploads/05-10-2026.pdf")
    if not b:
        return
    df = H.a_dataframe(H.parse_chs(b))
    assert len(df) == 147 and df.carrera.nunique() == 15
    r = H.buscar(df, "Haras Santa Mónica", "Criador (haras)")
    assert r.caballo.tolist() == ["Javivaletu"]
    assert r.iloc[0].preparador == "Alejandro Padovani E."


if __name__ == "__main__":
    for nombre, fn in list(globals().items()):
        if nombre.startswith("test_"):
            fn()
            print("OK ", nombre)
