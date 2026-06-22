# AFILIACION — OfertasHoy

Repositorio con scraper (Playwright + BeautifulSoup) y frontend estático.

Pasos locales rápidos:

1. Crear entorno virtual y activar:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

2. Instalar dependencias:

```powershell
python -m pip install -r requirements.txt
playwright install --with-deps
```

3. Ejecutar en modo demo (seguro):

```powershell
python scraper.py --demo
```

4. Ejecutar el backend de Rakuten (opcional y recomendado para no exponer secretos en el frontend):

```powershell
python -m pip install -r requirements.txt
set RAKUTEN_CLIENT_ID=TU_CLIENT_ID_AQUI
set RAKUTEN_CLIENT_SECRET=TU_CLIENT_SECRET_AQUI
set RAKUTEN_MID=TU_MID_AQUI
# Opcional: si ya tienes un token válido y solo quieres usarlo directamente,
# también puedes definir RAKUTEN_ACCESS_TOKEN.
set RAKUTEN_ACCESS_TOKEN=TU_ACCESS_TOKEN_AQUI
python rakuten_backend.py
```

5. Configurar `rakuten_search.js` para usar el backend:

- Si despliegas `rakuten_backend.py` en un servidor, actualiza `RAKUTEN_BACKEND_URL` en `rakuten_search.js`.
- Deja `RAKUTEN_CLIENT_SECRET` vacío o en placeholders en el frontend para no filtrar secretos.

6. Servir la UI y abrir en el navegador:

```powershell
python -m http.server 8000
# Abrir http://localhost:8000
```

CI:
- El workflow `.github/workflows/scrape.yml` ejecuta el scraper (por defecto en modo demo) y guarda `ofertas.json` como artifact. Configura la variable de entorno `SCRAPE_REAL=true` en Actions si quieres ejecutar scraping real (ten en cuenta implicaciones de uso).
