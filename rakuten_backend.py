"""rakuten_backend.py
Backend seguro para consultar Rakuten Advertising Product Search.

Este archivo expone un endpoint HTTP sencillo que recibe la consulta del usuario
como parámetro `q` y devuelve productos en formato JSON compatible con el frontend.

IMPORTANTE:
- No guardes tu CLIENT_SECRET en el frontend. Usa variables de entorno.
- Ajusta los PATHs y el parseo según el API real de Rakuten.
- El endpoint se diseña para desplegarse en un servidor (Heroku, Railway, Cloud Run, etc.).
"""

import os
import time
import json
import requests
from flask import Flask, request, jsonify

app = Flask(__name__)

# -----------------------------
# CREDENTIALS (EDITABLE PLACEHOLDERS)
# -----------------------------
# Reemplaza estos valores con tus datos reales en variables de entorno.
# Si ejecutas localmente para desarrollo, puedes definirlos aquí o en tu shell.
RAKUTEN_CLIENT_ID     = os.environ.get('RAKUTEN_CLIENT_ID', 'TU_CLIENT_ID_AQUI')
RAKUTEN_CLIENT_SECRET = os.environ.get('RAKUTEN_CLIENT_SECRET', 'TU_SECRET_AQUI')
RAKUTEN_ACCESS_TOKEN  = os.environ.get('RAKUTEN_ACCESS_TOKEN', 'TU_ACCESS_TOKEN_AQUI')
RAKUTEN_MID           = os.environ.get('RAKUTEN_MID', 'TU_MID_AQUI')

# Endpoint de búsqueda de producto Rakuten / LinkShare
RAKUTEN_SEARCH_URL = 'https://api.linksynergy.com/productsearch/1.0'

# Cache de token simple en memoria
_token_cache = {
    'token': None,
    'expires_at': 0,
}


def is_configured():
    placeholders = [RAKUTEN_CLIENT_ID, RAKUTEN_CLIENT_SECRET, RAKUTEN_MID]
    return all(v and not v.startswith('TU_') for v in placeholders)


def get_access_token():
    """Retorna un access token válido o None si no está configurado."""
    now = int(time.time())
    if _token_cache['token'] and _token_cache['expires_at'] > now + 60:
        return _token_cache['token']

    # Nota: la forma de obtener token depende de tu integración Rakuten/LinkShare.
    # Aquí se ilustra un flujo POST de client credentials si estuviera disponible.
    resp = requests.post(
        'https://api.rakutenmarketing.com/token',
        data={
            'grant_type': 'client_credentials',
            'client_id': RAKUTEN_CLIENT_ID,
            'client_secret': RAKUTEN_CLIENT_SECRET,
        },
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()
    _token_cache['token'] = data.get('access_token')
    _token_cache['expires_at'] = now + int(data.get('expires_in', 3600))
    return _token_cache['token']


@app.route('/api/rakuten_search')
def rakuten_search():
    q = request.args.get('q', '').strip()
    if not q:
        return jsonify({'error': 'Missing query parameter q'}), 400

    if not is_configured():
        return jsonify({'error': 'Rakuten credentials not configured'}), 500

    mid = RAKUTEN_MID
    params = {
        'keyword': q,
        'records': '24',
        'mid': mid,
        # Ajusta aquí parámetros adicionales si tu endpoint lo requiere.
    }

    headers = {
        'Content-Type': 'application/json',
    }

    # Usa un access token provisto o genera uno con client credentials.
    if RAKUTEN_ACCESS_TOKEN and not RAKUTEN_ACCESS_TOKEN.startswith('TU_'):
        headers['Authorization'] = f'Bearer {RAKUTEN_ACCESS_TOKEN}'
    else:
        token = get_access_token()
        if not token:
            return jsonify({'error': 'No access token available for Rakuten.'}), 500
        headers['Authorization'] = f'Bearer {token}'

    try:
        resp = requests.get(RAKUTEN_SEARCH_URL, params=params, headers=headers, timeout=15)
        resp.raise_for_status()

        # Ajusta el parseo según el formato real de la API
        text = resp.text
        try:
            data = resp.json()
        except ValueError:
            data = text

        products = []
        if isinstance(data, dict) and isinstance(data.get('products'), list):
            for p in data['products']:
                products.append({
                    'id': p.get('asin') or p.get('id') or '',
                    'asin': p.get('asin') or p.get('id') or '',
                    'titulo': p.get('title') or p.get('name') or p.get('product_name') or '',
                    'precio_actual': p.get('price') or p.get('sale_price') or '',
                    'precio_antes': p.get('list_price') or p.get('retail_price') or '',
                    'descuento': p.get('discount') or '',
                    'imagen': p.get('image') or p.get('image_url') or '',
                    'url': p.get('affiliate_url') or p.get('link') or '',
                    'tienda': 'rakuten',
                })
        else:
            # Si la respuesta no es JSON con products, devolver lista vacía.
            products = []

        return jsonify({'productos': products})

    except requests.RequestException as err:
        return jsonify({'error': 'Rakuten request failed', 'detail': str(err)}), 502


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080, debug=True)
