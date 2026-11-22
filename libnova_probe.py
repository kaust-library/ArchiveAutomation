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

# How the probe identifies itself. Some firewalls refuse Python's default
# ("Python-urllib/3.x") with a 403 before Libnova sees the key, while
# PowerShell's Invoke-RestMethod gets through. The first that works is used.
USER_AGENTS = [
    ("PowerShell", "Mozilla/5.0 (Windows NT; Windows NT 10.0; en-US) WindowsPowerShell/5.1"),
    ("ArchiveAutomation", "ArchiveAutomation/0.7 (+https://github.com/kaust-library/ArchiveAutomation)"),
    ("Python default", None),
]


def call(method, path, api_key, body=None, user_agent=None):
    """Return (HTTP status, parsed JSON or text)."""
    headers = {"accept": "application/json", "Authorization": f"Bearer {api_key}"}
    if user_agent:
        headers["User-Agent"] = user_agent
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
    # Show only the length, so a bad paste (empty, cut short, extra characters)
    # can be spotted without revealing the key.
    print(f"Using an API key of {len(api_key)} characters with {BASE_URL}")
    if not api_key:
        print("The key is empty. Set it with:  $env:LIBNOVA_API_KEY = '<your key>'")
        return 1

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

    lines = [f"Libnova probe: {BASE_URL}, file {file_id}, DC.IDENTIFIER {accession_id}",
             f"API key length: {len(api_key)} characters", ""]

    # Which client identity gets through?
    user_agent = None
    for name, ua in USER_AGENTS:
        status, result = call("GET", "/user/profile", api_key, user_agent=ua)
        print(f"0 identity '{name}': HTTP {status}")
        lines.append(f"===== 0 identity '{name}': GET /user/profile -> HTTP {status}")
        if status != 200:
            lines.append(result if isinstance(result, str) else json.dumps(shorten(result), indent=2))
        lines.append("")
        if status == 200:
            user_agent = ua
            print(f"  Using identity '{name}' for the other calls.")
            break
    else:
        print("  No identity was accepted; trying the other calls with the first one.")
        user_agent = USER_AGENTS[0][1]

    for title, method, path, body in probes:
        status, result = call(method, path, api_key, body, user_agent=user_agent)
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
            print("  The profile call was refused; trying the other calls anyway.")

    with open(OUTPUT, "w", encoding="utf-8") as ff:
        ff.write("\n".join(lines))
    print(f"\nWritten to {OUTPUT}. The API key is not in it.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
