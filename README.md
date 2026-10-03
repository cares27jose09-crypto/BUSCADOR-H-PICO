# 🐎 Buscador hípico de Chile

Cómo se usa:
1. **Hipódromo Chile** y **Club Hípico**: adjunta el volante PDF de la reunión.
2. **Valparaíso Sporting**: pega el link de la reunión (por ejemplo
   `https://www.sporting.cl/hipica/front/es/reunion/2026-10-07.html`). La app busca sola las
   páginas de todas las carreras.
3. Escribe lo que buscas (caballo, criadero/haras, jinete, preparador o stud) y listo.

## Publicarla (Streamlit Community Cloud)
Sube estos TRES archivos sueltos a la raíz de tu repositorio de GitHub (no una carpeta ni un zip):
`app.py`, `requirements.txt`, `packages.txt`.

Luego en https://share.streamlit.io → Create app → elige tu repositorio, rama `main`,
archivo `app.py` → Deploy.

Si ya la habías publicado antes, basta con reemplazar `app.py` en GitHub: la app se actualiza sola.

## Notas
* Los retiros de última hora no aparecen en los programas; confírmalos en el hipódromo.
* Si un hipódromo cambia el formato de su volante o su página, la app mostrará un aviso.
