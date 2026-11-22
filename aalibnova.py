"""Small read-only client for the Libnova (LIBSAFE Go) API.

Notes learned on ls-kaust.libnova.com:
* Python's default User-Agent ("Python-urllib/3.x") gets HTTP 403 on every call,
  so a PowerShell-like User-Agent is sent.
* GET requests carry no Content-Type; requests with a body do.
* The search index (POST /file/elastic) stores metadata under keys with the
  dots replaced by underscores: DC.IDENTIFIER -> metadata.DC_IDENTIFIER.

The API key comes from the LIBNOVA_API_KEY environment variable, or from a
.env file next to this script (LIBNOVA_API_KEY=...), or is asked for.
"""

import getpass
import json
import os
import pathlib
import socket
import time
import urllib.error
import urllib.request

REPO_DIR = pathlib.Path(__file__).resolve().parent
DEFAULT_BASE_URL = "https://ls-kaust.libnova.com/api"
USER_AGENT = "Mozilla/5.0 (Windows NT; Windows NT 10.0; en-US) WindowsPowerShell/5.1"


class LibnovaError(Exception):
    pass


class _Transient(Exception):
    """A failure worth retrying: timeout, dropped connection, 5xx."""


def _key_from_dotenv():
    env_file = REPO_DIR / ".env"
    if env_file.is_file():
        for line in env_file.read_text(encoding="utf-8-sig").splitlines():
            if line.strip().startswith("LIBNOVA_API_KEY="):
                return line.split("=", 1)[1].strip().strip("'\"")
    return None


def get_api_key():
    key = os.environ.get("LIBNOVA_API_KEY") or _key_from_dotenv()
    if not key:
        key = getpass.getpass("Libnova API key: ")
    key = (key or "").strip()
    if not key:
        raise LibnovaError(
            "No API key. Set it with:  $env:LIBNOVA_API_KEY = '<your key>'"
        )
    return key


def iecode_from_index_key(key):
    """Search-index key -> IECode: DC_FORMAT_MEDIUM -> DC.FORMAT_MEDIUM."""
    return "DC." + key[3:] if key.startswith("DC_") else key


def index_key(iecode):
    """IECode -> search-index key: DC.IDENTIFIER -> DC_IDENTIFIER."""
    return iecode.replace(".", "_")


class Libnova:
    def __init__(self, api_key, base_url=None, timeout=120):
        self.base_url = (base_url or os.environ.get("LIBNOVA_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")
        self.api_key = api_key
        self.timeout = timeout

    # Waits (seconds) before each retry of a request that timed out, lost its
    # connection or got a 5xx server error. Only used for read requests.
    RETRY_WAITS = (10, 30, 60)

    def call(self, method, path, body=None, retry=True):
        """Send one request; retry slow or failed reads (see RETRY_WAITS)."""
        waits = list(self.RETRY_WAITS) if retry else []
        while True:
            try:
                return self._call_once(method, path, body)
            except _Transient as ee:
                if not waits:
                    raise LibnovaError(f"{path}: {ee} (gave up after {len(self.RETRY_WAITS) + 1} tries)")
                wait = waits.pop(0)
                print(f"\n  {path}: {ee}; trying again in {wait} s ...", flush=True)
                time.sleep(wait)

    def _call_once(self, method, path, body):
        headers = {
            "accept": "application/json",
            "Authorization": f"Bearer {self.api_key}",
            "User-Agent": USER_AGENT,
        }
        data = None
        if body is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(self.base_url + path, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read()
        except urllib.error.HTTPError as ee:
            detail = ee.read().decode("utf-8", errors="replace")[:500]
            if ee.code in (401, 403):
                raise LibnovaError(
                    f"HTTP {ee.code} from {path}: the API key was refused. Check the key, "
                    f"and that API_ACCESS is enabled for your account. {detail}"
                )
            if ee.code >= 500 or ee.code == 429:
                raise _Transient(f"HTTP {ee.code} from the server")
            raise LibnovaError(f"HTTP {ee.code} from {path}: {detail}")
        except urllib.error.URLError as ee:
            if isinstance(ee.reason, (socket.timeout, TimeoutError, ConnectionError, OSError)):
                raise _Transient(f"connection problem ({ee.reason})")
            raise LibnovaError(f"Could not connect to {self.base_url}: {ee.reason}")
        except (socket.timeout, TimeoutError, ConnectionError) as ee:
            raise _Transient(f"no answer within {self.timeout} s" if isinstance(ee, (socket.timeout, TimeoutError)) else f"connection lost ({ee})")
        try:
            result = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError:
            raise LibnovaError(f"{path} did not return JSON: {raw[:200]!r}")
        if isinstance(result, dict) and result.get("success") is False:
            raise LibnovaError(f"{path} answered success=false: {json.dumps(result)[:500]}")
        return result

    def search(self, must, start=0, size=None):
        """POST /file/elastic. Returns (total, [hit _source dicts])."""
        body = {"must": must}
        if size is not None:
            body.update({"from": start, "size": size})
        result = self.call("POST", "/file/elastic", body)
        hits = result.get("hits", {})
        total = hits.get("total", {})
        total = total.get("value") if isinstance(total, dict) else total
        sources = [hh.get("_source", {}) for hh in hits.get("hits", [])]
        return total, sources
