"""Build the server image from preserved RPi sources with narrow integration edits."""
import shutil
import re
from pathlib import Path


def replace(path, old, new):
    text = path.read_text(encoding='utf-8')
    if old not in text:
        raise RuntimeError(f'Upstream integration point changed: {path}: {old[:70]}')
    path.write_text(text.replace(old, new), encoding='utf-8')


def adapt(source, target):
    source, target = Path(source), Path(target)
    for folder in ('ide', 'simulator', 'sprite-stage', 'client', 'examples', 'gadget-tests'):
        shutil.copytree(source / folder, target / folder, dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    shutil.copytree(source.parent / 'extra/ace', target / 'ide/assets/ace', dirs_exist_ok=True)
    for old, new in [('ace.js', 'ace.js'), ('mode-python.min.js', 'mode-python.js'), ('theme-monokai.min.js', 'theme-monokai.js')]:
        replace(target / 'ide/code/index.php', 'https://cdnjs.cloudflare.com/ajax/libs/ace/1.32.6/' + old, '/assets/ace/' + new)
    replace(target / 'ide/blocks/index.php', "$DATA_DIR           = __DIR__ . '/data';", "$DATA_DIR           = '/home/client/blockdata';")
    replace(target / 'ide/blocks/designs.php', "$directory = __DIR__ . '/data/designs';", "$directory = '/home/client/blockdata/designs';")
    for page in ('code/index.php', 'blocks/index.php'):
        replace(target / 'ide' / page, '/run/codynick-script-control.sock', '/tmp/codynick-script-control.sock')
    replace(target / 'ide/dashboard/config.php', '$db_name = "codynick";', '$db_name = getenv("CN_DB_NAME");')
    replace(target / 'ide/dashboard/config.php', '$db_user = "codynick";', '$db_user = getenv("CN_DB_USER");')
    replace(target / 'ide/dashboard/config.php', '$db_pass = "codynick";', '$db_pass = getenv("CN_DB_PASSWORD");')
    dashboard = target / 'client/Dashboard.py'
    replace(dashboard, 'import json\n', 'import json\nimport os\n')
    replace(dashboard, '"user": "codynick",', '"user": os.environ["CN_DB_USER"],')
    replace(dashboard, '"password": "codynick",', '"password": os.environ["CN_DB_PASSWORD"],')
    replace(dashboard, '"database": "codynick",', '"database": os.environ["CN_DB_NAME"],\n    "unix_socket": "/run/mysqld/mysqld.sock",')
    with (target / 'client/CodyNick.py').open('a', encoding='utf-8') as stream:
        stream.write('\n# Server edition: physical serial is deferred; use this private simulator.\nCN = Simulator\n')
    replace(target / 'ide/index.php', '$jsonFile = "/device_info.json";', '$jsonFile = "/tmp/device_info.json";')
    replace(target / 'ide/index.php', '<div class="links">', '''<div class="links">
                <?php if (getenv('CN_ROLE') === 'teacher'): ?>
                <a class="link-card" href="/account/students"><div class="link-title">Student Management</div><div class="link-desc">Student accounts and password resets.</div></a>
                <?php endif; ?>''')
    for name in ('index.html', 'app.js'):
        path = target / 'simulator' / name
        text = re.sub(r'(["\'])/(?!/)', r'\1/simulator/', path.read_text(encoding='utf-8'))
        path.write_text(text.replace('http://start.codynick/', '/'), encoding='utf-8')
    replace(target / 'simulator/app.js', "mainPanelUrl.port = '';", '// Keep the current reverse-proxy port.')
    replace(target / 'simulator/app.js', "mainPanelUrl.pathname = '/simulator/';", "mainPanelUrl.pathname = '/';")
    with (target / 'simulator/app.js').open('a', encoding='utf-8') as stream:
        stream.write('\n// Wait for the private workspace first snapshot before enabling the toolbox.\n'
                     'for (const button of document.querySelectorAll("[data-add]")) button.disabled = true;\n')
    replace(target / 'ide/index.php', 'CodyNick On-Device Information Page', 'CodyNick Classroom')
    replace(target / 'ide/index.php', '</style>', '''
        @media (max-width: 600px) {
            .info-box { display: block; }
            .info-box .label { white-space: normal; margin-bottom: 6px; }
            .info-box .value { text-align: left; overflow-wrap: anywhere; }
        }
    </style>''')


if __name__ == '__main__':
    import sys
    adapt(sys.argv[1], sys.argv[2])
