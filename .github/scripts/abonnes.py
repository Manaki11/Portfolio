"""Met à jour le nombre d'abonnés des chaînes listées dans index.html.

Utilise l'API YouTube Data si le secret YOUTUBE_API_KEY est défini,
sinon lit le compteur affiché sur la page publique de la chaîne.
En cas d'échec pour une chaîne, l'ancienne valeur est conservée.
"""
import json
import os
import re
import sys
import urllib.parse
import urllib.request

PAGE = 'index.html'
ROW = re.compile(
    r'(href="https://www\.youtube\.com/@(?P<handle>[\w.-]+)"[^\n]*?'
    r'<span class="ch-subs mono">)(?P<subs>[^<]*)(</span>)'
)
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36'


def fetch(url):
    req = urllib.request.Request(url, headers={'User-Agent': UA, 'Accept-Language': 'en-US,en;q=0.9'})
    with urllib.request.urlopen(req, timeout=20) as res:
        return res.read().decode('utf-8', 'replace')


def via_api(handle, key):
    query = urllib.parse.urlencode({'part': 'statistics', 'forHandle': '@' + handle, 'key': key})
    data = json.loads(fetch('https://www.googleapis.com/youtube/v3/channels?' + query))
    stats = data['items'][0]['statistics']
    if stats.get('hiddenSubscriberCount'):
        raise ValueError('compteur masqué')
    return int(stats['subscriberCount'])


def via_page(handle):
    html = fetch('https://www.youtube.com/@' + handle + '?hl=en&gl=US')
    # La page liste aussi d'autres chaînes avec leur propre nombre d'abonnés :
    # on lit le compteur placé juste après l'identifiant de la chaîne
    anchor = re.search(r'"content":"@' + re.escape(handle) + '"', html, re.IGNORECASE)
    if not anchor:
        raise ValueError('identifiant introuvable dans l\'en-tête')
    match = re.search(r'"content":"([\d.,]+)\s*([KMB]?) subscribers"', html[anchor.end():anchor.end() + 2000])
    if not match:
        raise ValueError('compteur introuvable')
    number = float(match.group(1).replace(',', ''))
    return int(round(number * {'': 1, 'K': 1e3, 'M': 1e6, 'B': 1e9}[match.group(2)]))


def format_fr(count):
    # Même arrondi que YouTube : trois chiffres significatifs
    for unit, size in ((' M', 1e6), (' k', 1e3)):
        if count >= size:
            value = count / size
            decimals = 0 if value >= 100 else 1 if value >= 10 else 2
            text = f'{value:.{decimals}f}'
            if '.' in text:
                text = text.rstrip('0').rstrip('.')
            return text.replace('.', ',') + unit
    return str(count)


def parse_fr(text):
    match = re.fullmatch(r'\s*([\d,]+)\s*([kM]?)\s*', text)
    if not match:
        return None
    return float(match.group(1).replace(',', '.')) * {'': 1, 'k': 1e3, 'M': 1e6}[match.group(2)]


def main():
    key = os.environ.get('YOUTUBE_API_KEY', '').strip()
    with open(PAGE, encoding='utf-8') as f:
        page = f.read()

    failures = 0

    def update(match):
        nonlocal failures
        handle = match.group('handle')
        try:
            count = via_api(handle, key) if key else via_page(handle)
            old = parse_fr(match.group('subs'))
            if old and not old / 2 <= count <= old * 2:
                raise ValueError(f'{count} trop éloigné de la valeur actuelle, vérification manuelle nécessaire')
        except Exception as error:
            failures += 1
            print(f'@{handle} : échec ({error}), valeur conservée : {match.group("subs")}')
            return match.group(0)
        new = format_fr(count)
        print(f'@{handle} : {match.group("subs")} -> {new}')
        return match.group(1) + new + match.group(4)

    page, rows = ROW.subn(update, page)
    with open(PAGE, 'w', encoding='utf-8') as f:
        f.write(page)

    if rows == 0 or failures == rows:
        sys.exit('Aucune chaîne mise à jour')


main()
