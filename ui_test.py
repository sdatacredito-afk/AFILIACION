from playwright.sync_api import sync_playwright
import time

URL = 'http://localhost:8000'

def run():
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page()
        print('Opening page...')
        page.goto(URL, wait_until='domcontentloaded')
        # espera a que la carga de red se estabilice y permite fallbacks
        try:
            page.wait_for_load_state('networkidle', timeout=10000)
        except Exception:
            pass
        time.sleep(0.8)
        # intenta esperar selectores representativos, sin fallar si no aparecen
        try:
            page.wait_for_selector('#productGrid .card, #emptyState, #errorState', timeout=8000)
        except Exception:
            pass

        # Captura homepage
        page.screenshot(path='screenshot_home.png', full_page=True)
        print('Saved screenshot_home.png')

        # Ejecuta búsqueda de prueba
        try:
            page.fill('#searchInput', 'gaming')
            page.keyboard.press('Enter')
            page.wait_for_timeout(1200)
            page.wait_for_selector('.card', timeout=8000)
            page.screenshot(path='screenshot_search.png', full_page=True)
            print('Saved screenshot_search.png')
        except Exception as e:
            print('Search flow may have no local results or timed out:', e)

        # Extrae conteo de productos
        try:
            count = page.eval_on_selector('#productCount', 'el => el.textContent')
            print('Product count:', count)
        except Exception:
            print('Could not read product count')

        browser.close()

if __name__ == '__main__':
    run()
