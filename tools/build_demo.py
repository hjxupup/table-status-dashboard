"""Export the original Jinja template as a portable, static portfolio demo."""
import argparse
import json
import shutil
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

ROOT = Path(__file__).resolve().parents[1]


def build(output, standalone=None):
    payload = json.loads((ROOT / 'data/snapshots.json').read_text(encoding='utf-8'))
    env = Environment(loader=FileSystemLoader(ROOT / 'app/templates'), autoescape=select_autoescape())
    html = env.get_template('index.html').render(
        tables=[s['table_name'] for s in payload['snapshots']],
        last_refresh=payload['captured_at'], mode='snapshot')
    html = html.replace('<script src="static/app.js"></script>',
                        '<script src="static/demo-api.js"></script>\n    <script src="static/app.js"></script>')
    output.mkdir(parents=True, exist_ok=True)
    (output / 'index.html').write_text(html, encoding='utf-8')
    shutil.copytree(ROOT / 'app/static', output / 'static', dirs_exist_ok=True)
    shutil.copy2(ROOT / 'tools/demo-api.js', output / 'static/demo-api.js')
    (output / 'data').mkdir(exist_ok=True)
    shutil.copy2(ROOT / 'data/snapshots.json', output / 'data/snapshots.json')
    (output / '.nojekyll').write_text('')
    if standalone:
        css = (ROOT / 'app/static/styles.css').read_text(encoding='utf-8')
        api = (ROOT / 'tools/demo-api.js').read_text(encoding='utf-8')
        js = (ROOT / 'app/static/app.js').read_text(encoding='utf-8')
        inline_data = json.dumps(payload, ensure_ascii=False).replace('<', '\\u003c')
        single = html.replace('<link rel="stylesheet" href="static/styles.css" />', f'<style>{css}</style>')
        single = single.replace('<script src="static/demo-api.js"></script>',
                                f'<script>window.DASHBOARD_SNAPSHOT_DATA={inline_data};</script>\n<script>{api}</script>')
        single = single.replace('<script src="static/app.js"></script>', f'<script>{js}</script>')
        standalone.parent.mkdir(parents=True, exist_ok=True)
        standalone.write_text(single, encoding='utf-8')
        print(f'Built standalone page: {standalone}')
    print(f'Built {len(payload["snapshots"])} cards in {output}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=ROOT / 'web-demo')
    parser.add_argument('--standalone', type=Path, help='Optional self-contained HTML file, usable without a server.')
    args = parser.parse_args()
    build(args.output.resolve(), args.standalone.resolve() if args.standalone else None)
