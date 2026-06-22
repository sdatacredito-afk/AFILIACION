/*
 rakuten_search.js
 Helper module to query Rakuten Advertising (LinkShare) Product Search API.

 IMPORTANT:
 - This file contains PLACEHOLDERS for credentials. Do NOT commit real secrets.
 - Replace 'TU_CLIENT_ID_AQUI', 'TU_SECRET_AQUI', 'TU_ACCESS_TOKEN_AQUI' and 'TU_MID_AQUI'
   with your real values in a secure environment (or better: move them server-side).
 - The LinkShare / Rakuten Product Search endpoint historically returns XML/CSV in
   some flows; adapt parsing according to the API version you use. This client
   uses a permissive approach and falls back to demo data when not configured.

 USAGE:
 - The frontend calls `await window.searchRakuten(query)` which returns an array
   of product objects in the same shape as the local `ofertas.json` items.
 - Example product fields returned: asin, titulo, precio_actual, precio_antes,
   descuento, imagen, url, tienda

 SECURITY NOTE:
 - It's strongly recommended to perform Rakuten API calls from a backend that
   stores `CLIENT_SECRET` securely and to expose a minimal public endpoint for
   your frontend. Leaving secrets in client-side code is unsafe.
*/

// -----------------------------
// CREDENTIALS (EDITABLE PLACEHOLDERS)
// -----------------------------
// Reemplaza estos valores en un entorno seguro. No dejes valores reales en el frontend.
const RAKUTEN_CLIENT_ID     = 'TU_CLIENT_ID_AQUI';      // Client ID (editable)
const RAKUTEN_CLIENT_SECRET = 'TU_SECRET_AQUI';         // Client Secret (editable)
const RAKUTEN_ACCESS_TOKEN  = 'TU_ACCESS_TOKEN_AQUI';   // Access Token (editable)
// Merchant ID (MID) — se obtiene por tienda una vez aprobad@ en el Dashboard
const RAKUTEN_MID           = 'TU_MID_AQUI';           // Aquí va el Merchant ID (MID)

// Backend URL opcional: si tienes un backend seguro, configúralo aquí.
// Ejemplo: const RAKUTEN_BACKEND_URL = 'https://api.tu-sitio.com/api/rakuten_search';
const RAKUTEN_BACKEND_URL   = ''; // Deja vacío si vas a usar la llamada directa al endpoint de Rakuten.

// Endpoint (según requisito): https://api.linksynergy.com/productsearch/1.0
const RAKUTEN_SEARCH_URL    = 'https://api.linksynergy.com/productsearch/1.0';

// Demo fallback data (used when credentials are placeholders)
const DEMO_RAKUTEN_PRODUCTS = [
  {
    asin: 'RKT1234567',
    titulo: 'Demo: Auriculares Inalámbricos Rakuten',
    precio_actual: '$59.99',
    precio_antes: '$99.99',
    descuento: '-40%',
    imagen: 'https://placehold.co/400x400/6b21a8/fff?text=Rakuten+Demo',
    url: '#',
    tienda: 'rakuten'
  },
  {
    asin: 'RKT2345678',
    titulo: 'Demo: Disco SSD 1TB Rakuten',
    precio_actual: '$119.99',
    precio_antes: '$199.99',
    descuento: '-40%',
    imagen: 'https://placehold.co/400x400/6b21a8/fff?text=Rakuten+Demo',
    url: '#',
    tienda: 'rakuten'
  }
];

// Helper: check if placeholders still present
function isConfigured() {
  const placeholders = [RAKUTEN_CLIENT_ID, RAKUTEN_CLIENT_SECRET, RAKUTEN_MID];
  return placeholders.every(v => v && !v.startsWith('TU_'));
}

// Public function exposed to the page: window.searchRakuten
window.searchRakuten = async function searchRakuten(query) {
  query = String(query || '').trim();
  if (!query) return [];

  // Si no está configurado con credenciales reales y no hay backend, devolver demo
  if (!isConfigured() && !RAKUTEN_BACKEND_URL) {
    console.warn('Rakuten client no configurado — devolviendo datos demo. Replace placeholders in rakuten_search.js or call from backend.');
    return DEMO_RAKUTEN_PRODUCTS.filter(p => p.titulo.toLowerCase().includes(query.toLowerCase()));
  }

  // Si existe un backend seguro, llamarlo primero
  if (RAKUTEN_BACKEND_URL) {
    try {
      const endpoint = `${RAKUTEN_BACKEND_URL}?q=${encodeURIComponent(query)}`;
      const resp = await fetch(endpoint, { method: 'GET' });
      if (!resp.ok) {
        console.warn('Rakuten backend returned', resp.status, resp.statusText);
        return [];
      }
      const data = await resp.json();
      if (Array.isArray(data.productos)) {
        return data.productos;
      }
      if (Array.isArray(data)) {
        return data;
      }
      return [];
    } catch (err) {
      console.error('Error calling Rakuten backend:', err);
      return [];
    }
  }

  // Construir parámetros (ajusta según versión de API de Rakuten/LinkShare)
  const params = new URLSearchParams({
    keyword: query,
    records: '24',
    mid: RAKUTEN_MID,
    // token/access parameters: algunos endpoints usan 'token' o HTTP Authorization
    // Aquí mostramos la forma de incluir un token si ya lo tienes
  });

  // Si tienes un access token prefabricado, puedes usarlo en headers
  const headers = {};
  if (RAKUTEN_ACCESS_TOKEN && !RAKUTEN_ACCESS_TOKEN.startsWith('TU_')) {
    headers['Authorization'] = `Bearer ${RAKUTEN_ACCESS_TOKEN}`;
  }

  const url = `${RAKUTEN_SEARCH_URL}?${params.toString()}`;

  try {
    const resp = await fetch(url, { method: 'GET', headers });
    if (!resp.ok) {
      console.warn('Rakuten API returned', resp.status, resp.statusText);
      return [];
    }

    // Nota: ajusta parseo según content-type (XML vs JSON). Intentamos JSON primero.
    const text = await resp.text();
    let data = null;
    try { data = JSON.parse(text); } catch (e) { data = text; }

    // Transformación genérica: intenta mapear a formato esperado
    // Si la respuesta es XML/text, el usuario deberá adaptar este bloque.
    if (Array.isArray(data?.products)) {
      return data.products.map(p => ({
        asin: p.asin || p.id || '',
        titulo: p.title || p.name || p.product_name || '',
        precio_actual: p.price || p.sale_price || p.offer_price || '',
        precio_antes: p.list_price || p.retail_price || '',
        descuento: p.discount || '',
        imagen: p.image || p.image_url || '',
        url: p.affiliate_url || p.link || '',
        tienda: 'rakuten'
      }));
    }

    // Si data no tiene estructura JSON esperada, avisa y devuelve vacío
    console.warn('Rakuten response did not match expected shape. Inspect `resp.text()` for details.');
    return [];

  } catch (err) {
    console.error('Error fetching Rakuten:', err);
    return [];
  }
};
