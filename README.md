# 🐎 Buscador hípico de Chile

App web que, sin que el usuario suba nada, entra a los programas oficiales y permite buscar por
**caballo, criador (haras), jinete, preparador o stud**.

| Hipódromo | Fuente | Estado |
|---|---|---|
| Valparaíso Sporting | Páginas HTML de cada carrera | Automático |
| Club Hípico de Santiago | `static.clubhipico.cl/archivos/volantes/DD-MM-AAAA.pdf` | Automático |
| Hipódromo Chile | PDF del volante | Manual (subir PDF o pegar enlace) hasta conocer su URL fija |

## Publicarla gratis (Streamlit Community Cloud)

1. Crea un repositorio público en GitHub y sube estos archivos: `app.py`, `hipica.py`,
   `requirements.txt`, `packages.txt` (y opcionalmente `test_hipica.py` y este README).
2. Entra a <https://share.streamlit.io>, inicia sesión con GitHub y pulsa **Create app**.
3. Elige el repositorio, rama `main` y archivo principal `app.py`. Pulsa **Deploy**.
4. En unos minutos tendrás un enlace público para compartir (funciona desde el celular).

`packages.txt` instala `poppler-utils`, necesario para leer los PDF.

## Activar la descarga automática de Hipódromo Chile

Cuando se conozca el enlace fijo de su volante, en Streamlit Cloud ve a
**Settings → Secrets** y agrega:

```toml
HCH_URL_TEMPLATE = "https://.../volante_{aaaa}{mm}{dd}.pdf"
```

`{dd}`, `{mm}` y `{aaaa}` se reemplazan por la fecha de cada reunión.

## Probarla en tu computador

```bash
pip install -r requirements.txt     # y tener poppler-utils instalado
streamlit run app.py
python test_hipica.py               # pruebas de los lectores y del buscador
```

## Mantenimiento

Los lectores dependen del formato de cada sitio o PDF. Si un hipódromo cambia su diseño, la
app lo mostrará en el panel **⚠️ Avisos** (carreras sin caballos, PDF ilegible). Los lectores
están en `hipica.py`, una función por hipódromo.

## Importante

* Los retiros de última hora no figuran en los programas: confirmarlos en el hipódromo.
* Los datos se descargan de los sitios oficiales y se guardan 30 minutos para no sobrecargarlos.
* Revisa los términos de uso de cada sitio si piensas difundir la herramienta ampliamente.
