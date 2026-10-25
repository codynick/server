"""Browser acceptance of the actual RPi interfaces, backed by real user containers."""
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from adapt_rpi import adapt

with tempfile.TemporaryDirectory() as directory:
    root = Path(directory)
    adapt(ROOT / 'upstream', root / 'adapted')
    shutil.copytree(root / 'adapted/ide', root / 'web')
    shutil.copytree(root / 'adapted/simulator', root / 'web/simulator', dirs_exist_ok=True)
    os.environ.update(CN_DATA=str(root / 'data'), CN_SECRET='test-signing-secret', CN_WEB_ROOT=str(root / 'web'))
    sys.path.insert(0, str(ROOT / 'server'))
    import app
    with app.db() as conn:
        for name, role in [('teacher', 'teacher'), ('student1', 'student'), ('student2', 'student')]:
            conn.execute('INSERT INTO users(name,password,role) VALUES(?,?,?)', (name, app.generate_password_hash('a'), role))
    server = subprocess.Popen([sys.executable, '-m', 'flask', '--app', 'app:app', 'run', '--port', '8124'],
                               cwd=ROOT / 'server', env=dict(os.environ))
    browser = None
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            context = browser.new_context(viewport=dict(width=1440, height=1000))
            page = context.new_page()
            errors = []
            page.on('pageerror', lambda exc: errors.append(str(exc)))
            for _ in range(30):
                try:
                    page.goto('http://127.0.0.1:8124', timeout=5000)
                    break
                except Exception:
                    time.sleep(.3)
            page.locator('[name=name]').fill('teacher')
            page.locator('[name=password]').fill('a')
            page.get_by_role('button', name='Sign In', exact=True).click()
            page.get_by_text('On-Device IDE', exact=True).wait_for()
            page.get_by_text('Student Management', exact=True).wait_for()
            Path('screenshots').mkdir(exist_ok=True)
            page.screenshot(path='screenshots/main-panel.png', full_page=True)
            page.goto('http://127.0.0.1:8124/code/')
            page.wait_for_function('typeof ace !== "undefined" && typeof api === "function"')
            page.locator('#tree').get_by_text('CodyNick examples', exact=True).wait_for()
            page.screenshot(path='screenshots/ide.png', full_page=True)
            page.goto('http://127.0.0.1:8124/blocks/')
            page.locator('#generalToolboxTab').wait_for()
            page.wait_for_function('typeof workspace !== "undefined" && workspace !== null')
            page.locator('#spriteToolboxTab').click()
            page.locator('#spriteCanvas').wait_for()
            assert page.locator('#spriteCanvas').evaluate('(canvas)=>{const d=canvas.getContext("2d").getImageData(0,0,canvas.width,canvas.height).data;let n=0;for(let i=0;i<d.length;i+=4){if(d[i]<150&&d[i+1]<150&&d[i+2]<150)n++;}return n>30;}')
            page.screenshot(path='screenshots/blockly.png', full_page=True)
            page.goto('http://127.0.0.1:8124/simulator/')
            page.locator('[data-add=seven]').click()
            page.locator('#gadget-seven').wait_for(state='visible')
            assert page.locator('#mainPanel').get_attribute('href') == 'http://127.0.0.1:8124/'
            page.wait_for_function('Array.from(document.images).every(i=>i.complete && i.naturalWidth>0)')
            page.screenshot(path='screenshots/simulator.png', full_page=True)
            page.goto('http://127.0.0.1:8124/dashboard/')
            assert 'Unable to load dashboard' not in page.content()
            page.screenshot(path='screenshots/dashboard.png', full_page=True)
            page.goto('http://127.0.0.1:8124/')
            page.set_viewport_size(dict(width=390, height=844))
            page.screenshot(path='screenshots/main-mobile.png', full_page=True)
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            assert not errors, errors
            second = browser.new_context()
            student = second.new_page()
            student.goto('http://127.0.0.1:8124/')
            student.locator('[name=name]').fill('student1')
            student.locator('[name=password]').fill('a')
            student.get_by_role('button', name='Sign In', exact=True).click()
            student.get_by_text('On-Device IDE', exact=True).wait_for()
            assert student.get_by_text('Student Management', exact=True).count() == 0
            response = second.request.get('http://127.0.0.1:8124/account/students')
            assert response.status == 403
            print('Original RPi main panel, Ace IDE, Blockly/sprite pixels, simulator images/toolbox, dashboard and teacher-only navigation: OK')
            browser.close()
            browser = None
    finally:
        if browser:
            browser.close()
        server.terminate()
        server.wait(timeout=10)
