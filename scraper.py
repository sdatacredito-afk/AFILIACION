"""
scraper.py - Amazon.com Affiliate Scraper con Inteligencia de Mercado
Motor: Playwright + BeautifulSoup (sin PA-API)
Tag:   dawi01-20
Output: ./AFILIACION/ofertas.json (max 15 productos TOP por puntuacion)

Uso:
  python scraper.py          -> scraping real de Amazon.com
  python scraper.py --demo   -> datos de prueba listos para el frontend
"""

import json
import asyncio
import re
import random
from pathlib import Path
from datetime import datetime, timezone
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup

# Patrones compilados una sola vez — reutilizados en cada iteracion del parser
_ASIN_STRICT  = re.compile(r'^[A-Z0-9]{10}$')          # ASIN valido exacto
_ASIN_IN_URL  = re.compile(r'/(?:dp|gp/product)/([A-Z0-9]{10})(?:[/?#]|$)')  # ASIN embebido en URL
_ASIN_IN_STR  = re.compile(r'(?<![A-Z0-9])([A-Z0-9]{10})(?![A-Z0-9])')       # ASIN en texto libre


# =========================================================================
# CONFIGURACION CENTRAL
# =========================================================================

AFFILIATE_TAG     = "dawi01-20"
OUTPUT_FILE       = Path(__file__).parent / "ofertas.json"
MIN_DISCOUNT_PCT  = 20     # Umbral minimo de descuento real para pasar el filtro
MAX_TOP_PRODUCTS  = 15     # Solo las 15 mejores por puntuacion llegan al JSON

SCRAPE_PAGES = [
    "https://www.amazon.com/deals",
    "https://www.amazon.com/gp/goldbox?dealType=all_deals",
    (
        "https://www.amazon.com/s?i=electronics"
        "&rh=n%3A172282%2Cp_n_deal_type%3A23566065011"
        "&deals-widget=%7B%22version%22%3A1%2C%22viewIndex%22%3A0"
        "%2C%22presetId%22%3A%22deals-collection-lightning-deals%22"
        "%2C%22sorting%22%3A%22BY_SCORE%22%7D"
    ),
    "https://www.amazon.com/s?i=computers-intl-ship&rh=p_n_deal_type%3A23566065011",
    "https://www.amazon.com/s?i=videogames-intl-ship&rh=p_n_deal_type%3A23566065011",
]

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 Edg/124.0.0.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
]


# =========================================================================
# INTELIGENCIA DE MERCADO — PALABRAS CLAVE CON PESO DE TENDENCIA (0-100)
# =========================================================================

KEYWORD_WEIGHTS: dict[str, int] = {
    # --- Gaming (conversion maxima) ---
    "gaming":          95, "gamer":           93, "rtx":             92,
    "gpu":             90, "playstation":      96, "ps5":             97,
    "xbox":            91, "nintendo":         89, "switch":          86,
    "steam deck":      90, "controller":       79, "mechanical":      77,
    "rgb":             82, "headset":          81, "gaming mouse":    83,
    "gaming keyboard": 85, "gaming monitor":   88, "graphics card":   91,
    "geforce":         90, "radeon":           88, "ryzen":           87,
    "processor":       80, "cpu":              82, "ram":             78,
    "ssd":             81, "nvme":             83, "ddr5":            84,

    # --- Smartphones y tablets (alta conversion) ---
    "iphone":          93, "samsung":          86, "galaxy":          87,
    "pixel":           84, "oneplus":          78, "ipad":            89,
    "tablet":          79, "smartphone":       83, "5g":              80,

    # --- Computadoras y perifericos ---
    "laptop":          86, "macbook":          92, "ultrabook":       84,
    "notebook":        80, "monitor":          83, "4k":              82,
    "oled":            90, "curved":           78, "webcam":          76,
    "keyboard":        72, "mouse":            70, "usb hub":         74,

    # --- TV y entretenimiento ---
    "smart tv":        85, "qled":             87, "television":      73,
    "projector":       79, "streaming":        76, "8k":              86,

    # --- Audio y accesorios ---
    "airpods":         89, "earbuds":          83, "headphones":      86,
    "bose":            85, "sony wh":          88, "jbl":             79,
    "speaker":         76, "soundbar":         80, "anc":             82,

    # --- Gadgets y hogar inteligente ---
    "drone":           79, "gopro":            81, "action camera":   80,
    "smartwatch":      81, "apple watch":      89, "fitbit":          73,
    "echo":            75, "kindle":           79, "dyson":           87,
    "robot vacuum":    83, "vacuum":           76, "smart home":      77,
    "ring doorbell":   78, "nest":             74,

    # --- Otros tech de alta conversion ---
    "apple":           89, "lenovo":           80, "asus":            82,
    "acer":            76, "hp":               74, "dell":            77,
    "lg":              80, "panasonic":        73, "razer":           88,
    "corsair":         84, "logitech":         82, "steelseries":     83,
}

# Subconjunto de palabras que clasifican un producto como "GAMER"
GAMING_KEYWORDS: set[str] = {
    "gaming", "gamer", "rtx", "gpu", "geforce", "radeon", "playstation", "ps5",
    "xbox", "nintendo", "switch", "steam deck", "controller", "rgb",
    "mechanical", "headset", "gaming mouse", "gaming keyboard", "gaming monitor",
    "graphics card", "ryzen", "cpu", "ram", "ssd", "nvme", "ddr5", "razer",
    "corsair", "steelseries",
}


# =========================================================================
# FUNCIONES DE INTELIGENCIA
# =========================================================================

def sanitize_asin(raw: str) -> str | None:
    """
    Limpieza estricta del ASIN extraido de Amazon.

    Orden de limpieza:
      1. Elimina TODOS los espacios / saltos de linea / tabs
      2. Si parece URL, extrae el ASIN del path /dp/ o /gp/product/
      3. Corta en el primer '?', '/', '&', '#' (basura de parametros)
      4. Busca el primer token de 10 alfanumericos consecutivos
      5. Valida: exactamente 10 chars [A-Z0-9] mayusculas
    Retorna el ASIN limpio o None si no supera la validacion.
    """
    if not raw:
        return None

    s = re.sub(r'\s+', '', str(raw))          # paso 1: sin whitespace

    m = _ASIN_IN_URL.search(s)                # paso 2: ASIN dentro de URL
    if m:
        return m.group(1)

    s = re.split(r'[/?&#]', s)[0]            # paso 3: cortar basura de URL

    m = _ASIN_IN_STR.search(s.upper())        # paso 4: token alfanumerico
    if m:
        candidate = m.group(1)
        if _ASIN_STRICT.match(candidate):      # paso 5: validacion exacta
            return candidate

    return None


def build_affiliate_url(asin: str) -> str:
    """
    Construye la URL de afiliado con estructura exacta y limpia.
    Formato garantizado: https://www.amazon.com/dp/{ASIN}/?tag=dawi01-20
    - Sin slashes dobles
    - Sin parametros basura
    - ASIN siempre sanitizado antes de componer la URL
    """
    clean = sanitize_asin(asin)
    if not clean:
        # Fallback: usar el raw pero forzar mayusculas y strip
        clean = asin.strip().upper()[:10]
    return f"https://www.amazon.com/dp/{clean}/?tag={AFFILIATE_TAG}"


def extract_discount_pct(descuento_str: str) -> float:
    """Convierte '-35%' o '35% off' en el numero 35.0."""
    m = re.search(r"(\d+(?:\.\d+)?)", descuento_str or "")
    return float(m.group(1)) if m else 0.0


def get_trend_weight(title: str) -> int:
    """Retorna el mayor peso de tendencia encontrado en el titulo."""
    t = title.lower()
    return max((w for kw, w in KEYWORD_WEIGHTS.items() if kw in t), default=0)


def is_target_keyword(title: str) -> bool:
    """True si el titulo contiene al menos una palabra clave de alta conversion."""
    t = title.lower()
    return any(kw in t for kw in KEYWORD_WEIGHTS)


def calcular_puntuacion(discount_pct: float, trend_weight: int) -> float:
    """
    Formula oficial:
      Puntuacion = (Descuento * 0.6) + (Peso_Tendencia * 0.4)
    Rango esperado: 12 (descuento=20, peso=0) hasta ~82 (descuento=70, peso=97)
    """
    return round((discount_pct * 0.6) + (trend_weight * 0.4), 2)


def assign_badge(puntuacion: float, title: str) -> str:
    """Asigna el badge_tipo segun puntuacion y categoria de producto."""
    t = title.lower()
    has_gaming = any(kw in t for kw in GAMING_KEYWORDS)

    if puntuacion >= 58:
        return "TENDENCIA VIRAL"
    if has_gaming and puntuacion >= 40:
        return "GAMER PICK"
    if puntuacion >= 44:
        return "SUPER OFERTA"
    if puntuacion >= 28:
        return "TECH DEAL"
    return "OFERTA DEL DIA"


def filtrar_y_rankear(products: list[dict]) -> list[dict]:
    """
    Pipeline de inteligencia de mercado:
      1. Filtra por palabras clave de alta conversion
      2. Filtra por descuento real >= MIN_DISCOUNT_PCT
      3. Calcula puntuacion para cada producto
      4. Ordena por puntuacion descendente
      5. Retorna los top MAX_TOP_PRODUCTS
    """
    enriched = []

    for p in products:
        titulo = p.get("titulo", "")

        # Paso 1 — Filtro de relevancia por categoria
        if not is_target_keyword(titulo):
            continue

        # Paso 2 — Filtro matematico de descuento minimo
        discount_pct = extract_discount_pct(p.get("descuento", ""))
        if discount_pct < MIN_DISCOUNT_PCT:
            continue

        # Paso 3 — Calculo de puntuacion
        trend_weight = get_trend_weight(titulo)
        puntuacion   = calcular_puntuacion(discount_pct, trend_weight)

        # Paso 4 — Asignacion de badge
        badge_tipo = assign_badge(puntuacion, titulo)

        enriched.append({
            **p,
            "descuento_pct": discount_pct,
            "trend_weight":  trend_weight,
            "puntuacion":    puntuacion,
            "badge_tipo":    badge_tipo,
        })

    # Paso 5 — Ranking por puntuacion y recorte
    enriched.sort(key=lambda x: x["puntuacion"], reverse=True)
    top = enriched[:MAX_TOP_PRODUCTS]

    print(f"    [PIPELINE] {len(products)} totales "
          f"-> {len(enriched)} calificados "
          f"-> {len(top)} TOP seleccionados")
    return top


def calcular_descuento_str(precio_actual: str, precio_antes: str | None) -> str:
    """Calcula el % de descuento si no hay badge en la pagina."""
    try:
        actual = float(re.sub(r"[^\d.]", "", precio_actual or ""))
        antes  = float(re.sub(r"[^\d.]", "", precio_antes or ""))
        if antes > actual > 0:
            return f"-{round((1 - actual / antes) * 100)}%"
    except (ValueError, ZeroDivisionError):
        pass
    return ""


# =========================================================================
# PARSER HTML
# =========================================================================

def parse_amazon_html(html: str) -> list[dict]:
    """
    Extrae todas las tarjetas con data-asin encontradas en el HTML.
    Usa selectores en cascada para resistir cambios de layout de Amazon.
    Retorna la lista cruda — el filtrado se hace en filtrar_y_rankear().
    """
    soup       = BeautifulSoup(html, "html.parser")
    products   = []
    seen_asins: set[str] = set()

    candidates = soup.select('[data-asin]:not([data-asin=""])')
    print(f"    [PARSER] Candidatos con data-asin: {len(candidates)}")

    for card in candidates:
        try:
            # sanitize_asin() aplica las 5 etapas de limpieza:
            # whitespace → URL path → corte basura → token regex → validacion estricta
            asin = sanitize_asin(card.get("data-asin", ""))
            if not asin:
                continue
            if asin in seen_asins:
                continue

            # -- Titulo --
            title_el = (
                card.select_one("h2 a span")
                or card.select_one("h2 span")
                or card.select_one(".a-size-base-plus")
                or card.select_one(".a-size-medium")
                or card.select_one(".a-size-small.a-color-base")
                or card.select_one("[data-cy='title-recipe'] span")
            )
            if not title_el:
                continue
            title = title_el.get_text(strip=True)
            if len(title) < 8:
                continue

            # -- Precio actual --
            price_el = (
                card.select_one(".a-price .a-offscreen")
                or card.select_one("[data-cy='price-recipe'] .a-offscreen")
                or card.select_one(".a-price-whole")
            )
            precio_actual = price_el.get_text(strip=True) if price_el else "Ver precio"

            # -- Precio original (tachado) --
            old_el = (
                card.select_one(".a-text-price .a-offscreen")
                or card.select_one(".a-price.a-text-price .a-offscreen")
                or card.select_one("span[data-a-strike='true'] .a-offscreen")
            )
            precio_antes = old_el.get_text(strip=True) if old_el else None

            # -- Badge de descuento --
            badge_el = (
                card.select_one(".a-badge-text")
                or card.select_one(".s-coupon-highlight-color")
                or card.select_one("[data-cy='reviews-block'] .a-badge-text")
            )
            if badge_el:
                raw = badge_el.get_text(strip=True)
                m = re.search(r"(\d+)", raw)
                descuento = f"-{m.group(1)}%" if m else raw
            else:
                descuento = calcular_descuento_str(precio_actual, precio_antes)

            # -- Imagen (prioriza data-src de lazy loading) --
            img_el = (
                card.select_one("img.s-image")
                or card.select_one("img[src*='images-amazon']")
                or card.select_one("img[data-src*='images-amazon']")
            )
            imagen = ""
            if img_el:
                imagen = img_el.get("data-src") or img_el.get("src") or ""
                imagen = re.sub(r"\._[A-Z0-9_]+_\.", "._AC_SL400_.", imagen)

            seen_asins.add(asin)
            products.append({
                "id":            asin,
                "asin":          asin,
                "titulo":        title,
                "precio_actual": precio_actual,
                "precio_antes":  precio_antes,
                "descuento":     descuento,
                "imagen":        imagen,
                "url":           build_affiliate_url(asin),
                "tienda":        "amazon",
                "timestamp":     datetime.now(timezone.utc).isoformat(),
            })

        except Exception as e:
            print(f"    [!] Card ignorada: {e}")
            continue

    return products


# =========================================================================
# MOTOR PLAYWRIGHT (anti-bot + retardos aleatorios)
# =========================================================================

async def scrape_page(page, url: str) -> list[dict]:
    """Navega con retardos humanos, scroll progresivo y parsea el HTML."""
    print(f"\n  -> {url}")

    try:
        response = await page.goto(url, wait_until="domcontentloaded", timeout=45_000)

        if response and response.status >= 400:
            print(f"    [!] HTTP {response.status} - omitiendo")
            return []

        # Espera al primer elemento con ASIN
        try:
            await page.wait_for_selector('[data-asin]:not([data-asin=""])', timeout=10_000)
        except Exception:
            pass

        # Scroll progresivo con retardos aleatorios (simula usuario humano)
        for step in [0.2, 0.45, 0.7, 1.0]:
            await page.evaluate(f"window.scrollTo(0, document.body.scrollHeight * {step})")
            await page.wait_for_timeout(random.randint(700, 1400))

        html     = await page.content()
        products = parse_amazon_html(html)
        print(f"    [OK] {len(products)} productos brutos extraidos")
        return products

    except Exception as e:
        print(f"    [ERROR] {e}")
        return []


async def main():
    print("\n" + "=" * 60)
    print(f"  Amazon Scraper con IA de Mercado  |  Tag: {AFFILIATE_TAG}")
    print(f"  Filtro: >={MIN_DISCOUNT_PCT}% descuento + palabras clave")
    print(f"  Output: Top {MAX_TOP_PRODUCTS} por puntuacion")
    print("=" * 60)

    raw_products:  list[dict] = []
    seen_asins:    set[str]   = set()

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
        )

        context = await browser.new_context(
            user_agent=random.choice(USER_AGENTS),
            viewport={"width": 1366, "height": 768},
            locale="en-US",
            timezone_id="America/New_York",
            extra_http_headers={
                "Accept":                    "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
                "Accept-Language":           "en-US,en;q=0.9",
                "Accept-Encoding":           "gzip, deflate, br",
                "DNT":                       "1",
                "Upgrade-Insecure-Requests": "1",
                "Sec-Fetch-Dest":            "document",
                "Sec-Fetch-Mode":            "navigate",
                "Sec-Fetch-Site":            "none",
                "Sec-Fetch-User":            "?1",
                "Cache-Control":             "max-age=0",
            },
        )

        # Bloquea recursos que ralentizan sin aportar datos
        await context.route(re.compile(r"\.(woff2?|ttf|eot|otf)(\?|$)"),      lambda r: r.abort())
        await context.route(re.compile(r"(doubleclick|googlesyndication|adnxs)"), lambda r: r.abort())

        page = await context.new_page()

        # Oculta el flag webdriver antes de cualquier navegacion
        await page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            Object.defineProperty(navigator, 'plugins',   { get: () => [1, 2, 3] });
            window.chrome = { runtime: {} };
        """)

        # Visita la home para establecer cookies de sesion
        print("\n  -> Sesion en amazon.com...")
        await page.goto("https://www.amazon.com", wait_until="domcontentloaded", timeout=30_000)
        await page.wait_for_timeout(random.randint(1800, 3000))

        # Scraping de cada pagina de ofertas
        for url in SCRAPE_PAGES:
            prods = await scrape_page(page, url)
            for p_ in prods:
                if p_["asin"] not in seen_asins:
                    seen_asins.add(p_["asin"])
                    raw_products.append(p_)

            # Pausa anti-bot entre paginas (3-6 segundos)
            delay = random.randint(3000, 6000)
            print(f"    [PAUSA] {delay}ms antes de la siguiente pagina")
            await page.wait_for_timeout(delay)

        await browser.close()

    print(f"\n  [TOTAL RAW] {len(raw_products)} productos unicos antes de filtrar")

    # Aplicar pipeline de inteligencia de mercado
    top_products = filtrar_y_rankear(raw_products)

    # Guardar en ./AFILIACION/ofertas.json
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).isoformat()
    payload = {
        "generado_en":  now,
        "total":        len(top_products),
        "tag":          AFFILIATE_TAG,
        "min_descuento": MIN_DISCOUNT_PCT,
        "formula":      "puntuacion = (descuento * 0.6) + (trend_weight * 0.4)",
        "productos":    top_products,
    }
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print(f"\n[DONE] {len(top_products)} productos TOP -> {OUTPUT_FILE}")
    print(f"       Tag: {AFFILIATE_TAG}")
    print(f"       Ejemplo URL: {build_affiliate_url('B09XS7JWHH')}\n")


# =========================================================================
# DATOS DEMO (10 productos con scoring y badges pre-calculados)
# =========================================================================

def generar_datos_demo():
    """
    Genera productos demo con badge_tipo y puntuacion ya calculados.
    Todos pasan el filtro de >={MIN_DISCOUNT_PCT}% descuento.
    """
    # (asin, titulo, precio_actual, precio_antes, descuento, imagen)
    items_raw = [
        ("B09XS7JWHH",
         "Sony WH-1000XM5 Wireless Industry Leading Noise Canceling Headphones",
         "$279.99", "$399.99", "-30%",
         "https://m.media-amazon.com/images/I/61+btxzpfDL._AC_SL400_.jpg"),

        ("B0CV5TBM7Q",
         "LG C4 Series 55-Inch Class OLED evo 4K Smart TV 2024",
         "$1,196.99", "$1,999.99", "-40%",
         "https://m.media-amazon.com/images/I/91VoTn7YOBL._AC_SL400_.jpg"),

        ("B0CRMN4ZMV",
         "Dyson V15 Detect Cordless Vacuum Cleaner Absolute",
         "$549.99", "$949.99", "-42%",
         "https://m.media-amazon.com/images/I/61PlXrDgizL._AC_SL400_.jpg"),

        ("B0CMDWC436",
         "Samsung Galaxy S24 Ultra 512GB Titanium Black Unlocked Smartphone",
         "$999.99", "$1,299.99", "-23%",
         "https://m.media-amazon.com/images/I/61vN1isnThL._AC_SL400_.jpg"),

        ("B0D3J6L3K9",
         "Apple iPad Air 11-inch M2 Chip Wi-Fi 256GB Blue",
         "$699.00", "$899.00", "-22%",
         "https://m.media-amazon.com/images/I/61UMHf2dE2L._AC_SL400_.jpg"),

        ("B0CX22Y2BL",
         "Apple MacBook Air 13-inch M3 Chip 8GB RAM 256GB SSD Midnight",
         "$849.00", "$1,099.00", "-23%",
         "https://m.media-amazon.com/images/I/71f5Eu5lJSL._AC_SL400_.jpg"),

        ("B09BRFJ8KH",
         "Nintendo Switch OLED Model Gaming Console White Joy-Con",
         "$279.99", "$349.99", "-20%",
         "https://m.media-amazon.com/images/I/51WBHH0xQcL._AC_SL400_.jpg"),

        ("B0CFPJYX9P",
         "Kindle Paperwhite Signature Edition 32GB Waterproof E-Reader",
         "$134.99", "$189.99", "-29%",
         "https://m.media-amazon.com/images/I/61Ui0i9INLL._AC_SL400_.jpg"),

        ("B0BDJH6RMF",
         "Apple AirPods Pro 2nd Generation with MagSafe Case USB-C",
         "$189.99", "$249.00", "-24%",
         "https://m.media-amazon.com/images/I/61SUj2aKoEL._AC_SL400_.jpg"),

        ("B0CD2FSRDD",
         "Bose QuietComfort Ultra Earbuds True Wireless Noise Canceling",
         "$229.00", "$299.00", "-23%",
         "https://m.media-amazon.com/images/I/51xnCH7KCQL._AC_SL400_.jpg"),

        ("B0BN7HPKY2",
         "ASUS ROG Strix G16 Gaming Laptop RTX 4070 Intel Core i9 32GB DDR5",
         "$1,299.99", "$1,799.99", "-28%",
         "https://m.media-amazon.com/images/I/81GJxXZv8wL._AC_SL400_.jpg"),

        ("B0C5G3C8W1",
         "Logitech G Pro X Superlight 2 Gaming Mouse RGB Ultra-light",
         "$109.99", "$159.99", "-31%",
         "https://m.media-amazon.com/images/I/61OYvTBbTGL._AC_SL400_.jpg"),

        ("B0BL6FQMKF",
         "Razer DeathAdder V3 Pro Wireless Gaming Mouse 30000 DPI",
         "$99.99", "$149.99", "-33%",
         "https://m.media-amazon.com/images/I/71xHNTIBj8L._AC_SL400_.jpg"),

        ("B0C1J1LC1H",
         "Corsair K100 AIR Wireless Mechanical Gaming Keyboard RGB",
         "$169.99", "$229.99", "-26%",
         "https://m.media-amazon.com/images/I/71rT5jSL8FL._AC_SL400_.jpg"),

        ("B0BN1Y1YVP",
         "Samsung 990 PRO 2TB PCIe 4.0 x4 NVMe M.2 SSD Internal Gaming",
         "$134.99", "$199.99", "-33%",
         "https://m.media-amazon.com/images/I/61GhFJlZvXL._AC_SL400_.jpg"),
    ]

    now      = datetime.now(timezone.utc).isoformat()
    productos = []

    for asin, titulo, precio_actual, precio_antes, descuento, imagen in items_raw:
        discount_pct = extract_discount_pct(descuento)
        trend_weight = get_trend_weight(titulo)
        puntuacion   = calcular_puntuacion(discount_pct, trend_weight)
        badge_tipo   = assign_badge(puntuacion, titulo)

        productos.append({
            "id":            asin,
            "asin":          asin,
            "titulo":        titulo,
            "precio_actual": precio_actual,
            "precio_antes":  precio_antes,
            "descuento":     descuento,
            "descuento_pct": discount_pct,
            "trend_weight":  trend_weight,
            "puntuacion":    puntuacion,
            "badge_tipo":    badge_tipo,
            "imagen":        imagen,
            "url":           build_affiliate_url(asin),
            "tienda":        "amazon",
            "timestamp":     now,
        })

    # Ordena por puntuacion descendente (igual que el scraper real)
    productos.sort(key=lambda x: x["puntuacion"], reverse=True)
    productos = productos[:MAX_TOP_PRODUCTS]

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump({
            "generado_en":   now,
            "total":         len(productos),
            "tag":           AFFILIATE_TAG,
            "min_descuento": MIN_DISCOUNT_PCT,
            "modo":          "demo",
            "formula":       "puntuacion = (descuento * 0.6) + (trend_weight * 0.4)",
            "productos":     productos,
        }, f, ensure_ascii=False, indent=2)

    print(f"\n[DEMO] {len(productos)} productos TOP -> {OUTPUT_FILE}")
    print(f"       Formula aplicada: puntuacion = (descuento*0.6) + (trend*0.4)")
    print(f"       Tag: {AFFILIATE_TAG}")
    print(f"       Ejemplo URL: {build_affiliate_url(productos[0]['asin'])}")
    print()

    # Muestra tabla de ranking en consola
    print(f"  {'#':<3} {'ASIN':<11} {'Score':>6} {'Desc%':>6} {'Trend':>6}  Badge")
    print(f"  {'-'*3} {'-'*11} {'-'*6} {'-'*6} {'-'*6}  {'-'*20}")
    for i, p in enumerate(productos, 1):
        print(f"  {i:<3} {p['asin']:<11} {p['puntuacion']:>6.1f} "
              f"{p['descuento_pct']:>5.0f}%  {p['trend_weight']:>6}  {p['badge_tipo']}")


# =========================================================================
# PUNTO DE ENTRADA
# =========================================================================

if __name__ == "__main__":
    import sys

    if "--demo" in sys.argv:
        generar_datos_demo()
    else:
        asyncio.run(main())
