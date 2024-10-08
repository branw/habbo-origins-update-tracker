import hashlib
import json
import re
from datetime import datetime
from pathlib import Path

import httpx

CLIENT_URLS_URL = 'https://origins.habbo.com/gamedata/clienturls'
EXTERNAL_VARS_URL = 'http://origins-gamedata.habbo.com/external_variables/1'

EXTERNAL_VAR_LINE_PATTERN = br' *([\w\.]+) *=(.+)'

CURRENT_FILES_PATH = Path('.').resolve()
HISTORICAL_FILES_PATH = Path('./history').resolve()
README_PATH = CURRENT_FILES_PATH / 'README.md'


def get_http_client():
    transport = httpx.HTTPTransport(retries=3)
    return httpx.Client(transport=transport)


def parse_external_vars(content):
    external_vars = {}

    lines = content.split(b'\n')
    for line in lines:
        if match := re.match(EXTERNAL_VAR_LINE_PATTERN, line):
            key = match.group(1).strip()
            value = match.group(2).strip()

            external_vars[key] = value

    return external_vars


def save_response(name, response, prettify=False):
    current_file_path = CURRENT_FILES_PATH / name

    # Try grabbing a timestamp from the HTTP caching headers
    timestamp = None
    if 'Last-Modified' in response.headers:
        timestamp = datetime.strptime(response.headers['Last-Modified'], '%a, %d %b %Y %H:%M:%S %Z')

    content = response.content
    # Try to format the response better for Git diffs
    if prettify:
        try:
            decoded_json = json.loads(content.decode('utf8'))
            content = json.dumps(decoded_json, indent=4).encode('utf8')
        except json.JSONDecodeError as e:
            print(f'failed to prettify response for {name}: {e}')

    # Check if the (prettified) file was changed. This will miss any purely
    # formatting related changes, but we don't really care about those.
    current_hash = hashlib.sha256(content).hexdigest()
    existing_hash = None
    if current_file_path.exists():
        with open(current_file_path, 'rb') as f:
            old_content = f.read()
            existing_hash = hashlib.sha256(old_content).hexdigest()

    if existing_hash == current_hash:
        print(f'file "{name}" has not changed (last modified {timestamp}; {current_hash})')
        return

    print(f'file "{name}" was changed ({existing_hash} -> {current_hash})')

    with open(current_file_path, 'wb') as f:
        f.write(content)

    if not timestamp:
        timestamp = datetime.utcnow()
    formatted_timestamp = timestamp.isoformat(timespec='seconds').replace(':', '-')

    file_name, file_ext = name.rsplit('.', 1)
    historical_file_name = f'{file_name}_{formatted_timestamp}_{current_hash}.{file_ext}'
    historical_file_path = HISTORICAL_FILES_PATH / historical_file_name

    print(f'saving copy to {historical_file_path}')

    # Save the raw, un-prettified response to the historical file
    with open(historical_file_path, 'wb') as f:
        f.write(response.content)

    # Update the README
    with open(README_PATH, 'r') as f:
        readme = f.read()
    with open(README_PATH, 'w') as f:
        f.write(re.sub(
            fr'\[`{re.escape(name)}`](.*)\|(.*)\|',
            f'[`{name}`]\\1| `{formatted_timestamp}` |',
            readme))


def main():
    if not HISTORICAL_FILES_PATH.exists():
        HISTORICAL_FILES_PATH.mkdir()

    http_client = get_http_client()

    r = http_client.get(CLIENT_URLS_URL)
    save_response('client_urls.txt', r, prettify=True)

    r = http_client.get(EXTERNAL_VARS_URL)
    save_response('external_vars.txt', r)

    parsed_external_vars = parse_external_vars(r.content)

    external_texts_url = parsed_external_vars.get(b'external.texts.txt', None)
    external_figure_part_list_url = parsed_external_vars.get(b'external.figurepartlist.txt', None)
    external_override_texts_url = parsed_external_vars.get(b'external.override.texts.txt', None)

    if external_texts_url:
        r = http_client.get(external_texts_url.decode())
        save_response('external_texts.txt', r)

    if external_figure_part_list_url:
        r = http_client.get(external_figure_part_list_url.decode())
        save_response('figuredata.txt', r)

    if external_override_texts_url:
        r = http_client.get(external_override_texts_url.decode())
        save_response('external_flash_override_texts.txt', r)


if __name__ == '__main__':
    main()
