"""Development-only download from the pinned Simple Icons upstream release."""
import hashlib
import json
from pathlib import Path
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1] / 'src/valenza/gui/assets/brands'
BASE = 'https://raw.githubusercontent.com/simple-icons/simple-icons/13.21.0/'
NAMES = {'Spotify': 'spotify', 'YouTube': 'youtube', 'Netflix': 'netflix',
         'Amazon Prime': 'amazonprime', 'Prime Video': 'primevideo',
         'Apple Music': 'applemusic', 'Nubank': 'nubank',
         'Mercado Pago': 'mercadopago', 'HSBC': 'hsbc'}

def main():
    metadata = json.loads(urlopen(BASE + '_data/simple-icons.json', timeout=30).read())
    ROOT.mkdir(parents=True, exist_ok=True)
    records = {}
    for entry in metadata['icons']:
        slug = NAMES.get(entry['title'])
        if not slug:
            continue
        # Do not include marks with a separate restrictive asset license.
        if entry.get('license', {}).get('type', 'CC0-1.0') != 'CC0-1.0':
            raise RuntimeError(f'Review license for {slug}')
        svg = urlopen(BASE + f'icons/{slug}.svg', timeout=30).read()
        (ROOT / f'{slug}.svg').write_bytes(svg)
        records[slug] = dict(entry, sha256=hashlib.sha256(svg).hexdigest(),
                             upstream=BASE + f'icons/{slug}.svg')
    for name in ('LICENSE.md', 'DISCLAIMER.md'):
        (ROOT / name).write_bytes(urlopen(BASE + name, timeout=30).read())
    (ROOT / 'manifest.json').write_text(json.dumps(records, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print(f'Vendored {len(records)} icons with provenance and original SVG paths.')

if __name__ == '__main__':
    main()
