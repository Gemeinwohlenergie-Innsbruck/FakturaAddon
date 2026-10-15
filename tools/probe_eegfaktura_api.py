"""Read-only probe: which EEG Faktura API routes can this app actually reach?

Run it yourself - it asks for your EEG Faktura password with getpass, never
echoes, logs or stores it, and prints only counts and field *names*, never
member data.

    .venv/bin/python tools/probe_eegfaktura_api.py

It makes GET requests and the two POSTs the energystore uses for reads.
It never touches the routes that change anything - in particular
GET /billingRuns/{id}/billingDocuments/sendmail, which mails every member
despite being a GET, and any DELETE.
"""
import datetime as dt
import getpass
import io
import sys

import requests

BASE = "https://eegfaktura.at"
TOKEN_URL = "https://login.eegfaktura.at/realms/EEGFaktura/protocol/openid-connect/token"
CLIENT_ID = "at.ourproject.vfeeg.app"           # the web app's public client
DEFAULT_TENANT = "CC100438"
DEFAULT_EC_ID = "ATCC9999DYNAMCC100438000000000249"
TIMEOUT = 30



def guard(method, url):
    if method not in ("GET", "POST") or "sendmail" in url:
        raise SystemExit(f"refusing {method} {url} - this probe is read-only")
    if method == "POST" and not (url.endswith("/metadata") or "/rawdata" in url
                                 or url == TOKEN_URL):
        raise SystemExit(f"refusing POST {url} - not a known read endpoint")


def call(method, url, **kw):
    guard(method, url)
    return requests.request(method, url, timeout=TIMEOUT, **kw)


def line(ok, label, detail=""):
    mark = {True: "OK  ", False: "FAIL", None: "--  "}[ok]
    print(f"  [{mark}] {label}" + (f"  - {detail}" if detail else ""))


def main():
    print("EEG Faktura API probe (read-only)\n")
    user = input("EEG Faktura username (email): ").strip()
    password = getpass.getpass("Password (not echoed): ")
    tenant = input(f"Tenant [{DEFAULT_TENANT}]: ").strip() or DEFAULT_TENANT
    ec_id = input(f"ecId [{DEFAULT_EC_ID}]: ").strip() or DEFAULT_EC_ID
    basic = (user, password)
    hdr = {"X-Tenant": tenant, "Content-Type": "application/json"}
    print()

    # 1. Energystore metadata - Basic auth. Replaces nothing yet, proves access.
    r = call("POST", f"{BASE}/energystore/query/{ec_id}/metadata",
             auth=basic, headers=hdr, json={})
    if r.ok:
        meta = r.json()
        line(True, "energystore metadata (Basic)", f"{len(meta)} metering points with data")
        first = (meta[0] if isinstance(meta, list) and meta
                 else next(iter(meta.values()), None) if isinstance(meta, dict) else None)
        if isinstance(first, dict):
            # Names only: decides whether member names come with the energy data
            # or have to be joined from the Mitglieder export.
            print(f"         fields: {', '.join(sorted(first.keys()))}")
    else:
        line(False, "energystore metadata (Basic)", f"HTTP {r.status_code}")

    # 2. Energystore rawdata for the last complete quarter - replaces the
    #    Energiedaten and QoV Excel exports.
    today = dt.date.today()
    q = (today.month - 1) // 3                   # 0 = this quarter's predecessor
    year, quarter = (today.year, q) if q else (today.year - 1, 4)
    start = dt.datetime(year, 3 * (quarter - 1) + 1, 1)
    end = (dt.datetime(year + (quarter == 4), (3 * quarter) % 12 + 1, 1))
    r = call("POST", f"{BASE}/energystore/query/rawdata", auth=basic, headers=hdr,
             json={"ecId": ec_id, "start": int(start.timestamp() * 1000),
                   "end": int(end.timestamp() * 1000)})
    if r.ok:
        data = r.json()
        points = len(data)
        samples = sum(len(v.get("data", [])) for v in data.values()) if isinstance(data, dict) else 0
        has_qov = any("qov" in s for v in data.values() for s in v.get("data", [])[:1]) \
            if isinstance(data, dict) else False
        line(True, f"energystore rawdata {year} Q{quarter} (Basic)",
             f"{points} metering points, {samples} samples, qov field: {'yes' if has_qov else 'no'}")
        if isinstance(data, dict) and data:
            point = next(iter(data.values()))
            print(f"         per point: {', '.join(sorted(point.keys()))}")
            if point.get("data"):
                s0 = point["data"][0]
                print(f"         per sample: {', '.join(sorted(s0.keys()))}, "
                      f"{len(s0.get('value', []))} value slots")
                print(f"         first/last ts: {dt.datetime.fromtimestamp(point['data'][0]['ts'] / 1000)}"
                      f" / {dt.datetime.fromtimestamp(point['data'][-1]['ts'] / 1000)}")
    else:
        line(False, f"energystore rawdata {year} Q{quarter} (Basic)", f"HTTP {r.status_code}")

    # 3. Master data - Basic auth. Replaces member names + metering points.
    r = call("GET", f"{BASE}/api/master/masterdata", auth=basic, headers=hdr)
    if r.ok:
        body = r.json()
        rows = body if isinstance(body, list) else body.get("participants", [])
        meters = sum(len(p.get("meters", [])) for p in rows) if rows else 0
        line(True, "master data (Basic)", f"{len(rows)} participants, {meters} metering points")
        if rows:
            print(f"         fields: {', '.join(sorted(rows[0].keys()))}")
    else:
        line(False, "master data (Basic)", f"HTTP {r.status_code}")

    # 4. Keycloak password grant against the web app's client. This is the
    #    make-or-break question for everything behind a bearer token.
    r = call("POST", TOKEN_URL, data={"grant_type": "password", "client_id": CLIENT_ID,
                                      "username": user, "password": password})
    password = None                              # done with it
    if not r.ok:
        err = r.json().get("error", "?") if r.headers.get("content-type", "").startswith("application/json") else "?"
        hint = {"unauthorized_client": "direct grants are disabled for this client",
                "invalid_grant": "credentials rejected by Keycloak"}.get(err, "")
        line(False, "Keycloak token (password grant)", f"{err}" + (f": {hint}" if hint else ""))
        print("\nStopped: the billing and participant routes need a bearer token.")
        return
    token = r.json()["access_token"]
    line(True, "Keycloak token (password grant)", "direct grants are enabled")
    bearer = {"Authorization": f"Bearer {token}", "X-Tenant": tenant}

    # 5. Participants - email, IBAN, mandate live here, not in master data.
    r = call("GET", f"{BASE}/api/participant", headers=bearer)
    if r.ok:
        rows = r.json()
        line(True, "participants (Bearer)", f"{len(rows)} participants")
        if rows:
            print(f"         fields: {', '.join(sorted(rows[0].keys()))}")
    else:
        line(False, "participants (Bearer)", f"HTTP {r.status_code}")

    # 6. Billing documents by year, then the run's xlsx export - the file the
    #    operator currently downloads by hand.
    run_id = None
    for y in (today.year, today.year - 1):
        r = call("GET", f"{BASE}/cash/api/billingDocuments/tenant/{tenant}/{y}", headers=bearer)
        if not r.ok:
            line(False, f"billing documents {y} (Bearer)", f"HTTP {r.status_code}")
            continue
        docs = r.json()
        line(True, f"billing documents {y} (Bearer)", f"{len(docs)} documents")
        if docs:
            print(f"         fields: {', '.join(sorted(docs[0].keys()))}")
            run_id = run_id or next((d[k] for d in docs for k in d
                                     if k.lower() in ("billingrunid", "billingrun") and d[k]), None)
    if not run_id:
        line(None, "billing run xlsx", "no billing run id found in the documents")
        return

    r = call("GET", f"{BASE}/cash/api/billingRuns/{run_id}/billingDocuments/xlsx", headers=bearer)
    if not r.ok:
        line(False, "billing run xlsx (Bearer)", f"HTTP {r.status_code}")
        return
    try:
        from openpyxl import load_workbook
        wb = load_workbook(io.BytesIO(r.content), read_only=True)
        sheets = {ws.title: ws.max_row - 1 for ws in wb.worksheets}
        same = {"Liste", "Details"} <= set(sheets)
        line(True, "billing run xlsx (Bearer)",
             ", ".join(f"{k}: {v} rows" for k, v in sheets.items())
             + ("  -> same layout the app reads today" if same else "  -> DIFFERENT layout"))
    except Exception as e:
        line(False, "billing run xlsx (Bearer)", f"downloaded but unreadable: {e}")


if __name__ == "__main__":
    try:
        main()
    except requests.RequestException as e:
        sys.exit(f"network error: {e}")
