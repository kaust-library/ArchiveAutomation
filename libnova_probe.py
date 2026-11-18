"""Read-only probe of the Libnova API, to learn how DC.IDENTIFIER can be collected.

Usage (from the ArchiveAutomation folder, venv active):
    python libnova_probe.py <file_id> <accession_id>

<file_id>       Libnova ID of one object that has DC.IDENTIFIER set, e.g. the
                accession folder of 001_002_0001 (the number in its Libnova URL).
<accession_id>  Its DC.IDENTIFIER value, e.g. 001_002_0001.

The API key is read from the LIBNOVA_API_KEY environment variable, or asked for
(not shown on screen). Nothing is changed in Libnova: only GET requests and
searches are sent. The results are written to libnova_probe_output.txt.
"""

import getpass
import json
import os
import sys
import urllib.error
import urllib.request

BASE_URL = os.environ.get("LIBNOVA_BASE_URL", "https://ls-kaust.libnova.com/api")
OUTPUT = "libnova_probe_output.txt"


def call(method, path, api_key, body=None):
    """Return (HTTP status, parsed JSON or text)."""
    headers = {"accept": "application/json", "Authorization": f"Bearer {api_key}"}
    data = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(BASE_URL + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            status, raw = resp.status, resp.read()
    except urllib.error.HTTPError as ee:
        status, raw = ee.code, ee.read()
    except urllib.error.URLError as ee:
        return None, f"Could not connect: {ee.reason}"
    text = raw.decode("utf-8", errors="replace")
    try:
        return status, json.loads(text)
    except json.JSONDecodeError:
        return status, text[:2000]


def shorten(obj, depth=0):
    """Keep the structure readable: long lists cut to 3 items, long text cut."""
    if isinstance(obj, dict):
        return {kk: shorten(vv, depth + 1) for kk, vv in obj.items()}
    if isinstance(obj, list):
        cut = [shorten(vv, depth + 1) for vv in obj[:3]]
        if len(obj) > 3:
            cut.append(f"... {len(obj) - 3} more")
        return cut
    if isinstance(obj, str) and len(obj) > 200:
        return obj[:200] + "..."
    return obj


def main():
    if len(sys.argv) != 3:
        print(__doc__)
        return 1
    file_id, accession_id = sys.argv[1], sys.argv[2]
    api_key = os.environ.get("LIBNOVA_API_KEY") or getpass.getpass("Libnova API key: ")
    api_key = api_key.strip()

    nested = lambda field: {"must": [{"nested": {"path": "metadata", "query": {
        "simple_query_string": {"fields": [field], "query": accession_id,
                                "default_operator": "and"}}}}]}

    probes = [
        ("1 API key works", "GET", "/user/profile", None),
        ("2 the object", "GET", f"/file/{file_id}", None),
        ("3 the object's metadata", "GET", f"/file/{file_id}/metadata", None),
        ("4 conditions search by id", "GET", "/file",
         {"conditions": [{"id": int(file_id)}], "limit": 1, "offset": 0}),
        ("5 elastic search, metadata.DC.IDENTIFIER", "POST", "/file/elastic",
         nested("metadata.DC.IDENTIFIER")),
        ("6 elastic search, metadata.value", "POST", "/file/elastic",
         nested("metadata.value")),
        ("7 elastic search, any field", "POST", "/file/elastic",
         {"must": [{"simple_query_string": {"query": f"\"{accession_id}\""}}]}),
    ]

    lines = [f"Libnova probe: {BASE_URL}, file {file_id}, DC.IDENTIFIER {accession_id}", ""]
    for title, method, path, body in probes:
        status, result = call(method, path, api_key, body)
        print(f"{title}: HTTP {status}")
        lines.append(f"===== {title}: {method} {path} -> HTTP {status}")
        if body is not None:
            lines.append("request body: " + json.dumps(body))
        if title.startswith("1") and isinstance(result, dict):
            result = {"keys": sorted(result)}  # don't write profile details
        if not title.startswith("1"):
            result = shorten(result)
        lines.append(json.dumps(result, indent=2, ensure_ascii=False)
                     if not isinstance(result, str) else result)
        lines.append("")
        if title.startswith("1") and status in (401, 403):
            print("The API key was refused; stopping. Check the key and API_ACCESS.")
            break

    with open(OUTPUT, "w", encoding="utf-8") as ff:
        ff.write("\n".join(lines))
    print(f"\nWritten to {OUTPUT}. The API key is not in it.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
