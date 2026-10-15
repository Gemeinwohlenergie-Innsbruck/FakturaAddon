"""Fetch a quarter's energy data straight from EEG Faktura.

Replaces the two manual downloads "Energiedaten" and "QoV Log" from the
Energy Report. The result is built in exactly the shape those sheets load
into, so charts, invoices and the QoV check need no changes.

No Qt in here, so it can be tested without a display.

What the API gives and what it does not:
  - POST /energystore/query/rawdata with Basic auth returns 15-minute values
    per metering point, with a quality flag per value. This is the route the
    Grafana proxy already uses in production.
  - It returns no member names. Those come from the member list export
    ("Mitglieder" sheet), matched on the metering point ID - which also
    tells us which community to ask for (its "Gemeinschafts-ID").
  - Member data and invoices need a Keycloak token whose password grant is
    disabled for the web app's client, so they stay manual for now.

The export rules mirrored here are from eegfaktura-energystore
(excel/EnergySheet.go, EnergyExport.go addLine, utils.IsLineDateOutOfRange)
and were checked against a real Q2 2026 export.
"""

import base64
import datetime as dt
import re

import pandas as pd
import requests

RAWDATA_URL = "https://eegfaktura.at/energystore/query/rawdata"
TIMEOUT = 60
TIMEZONE = "Europe/Vienna"

# Value slot in the API -> metercode as named in the Energy Report export.
# The export writes slot i of its stored matrix under exactly these headers,
# and comparing the API with a real export confirmed it for every column.
METERCODES = {
    "CONSUMPTION": [
        (0, "Gesamtverbrauch lt. Messung (bei Teilnahme gem. Erzeugung) [KWH]"),
        (1, "Anteil gemeinschaftliche Erzeugung [KWH]"),
        (2, "Eigendeckung gemeinschaftliche Erzeugung [KWH]"),
    ],
    "GENERATION": [
        (0, "Gesamte gemeinschaftliche Erzeugung [KWH]"),
        (1, "Gesamt/Überschusserzeugung, Gemeinschaftsüberschuss [KWH]"),
    ],
}

COLUMN_LEVELS = ["MeteringpointID", "Name", "Energy direction", "Metercode"]

# Quality of a value: 0 = L0 no reading delivered, 1 = L1 measured,
# 2 = L2 substitute value, 3 = L3 faulty. The export leaves L0 cells empty.
NO_READING = "L0"


class EEGFakturaError(Exception):
    """A fetch failed for a reason worth showing the operator verbatim."""


# --- which community, which quarter ----------------------------------------

def community_from_meta(meta):
    """(tenant, ecId) from the member list's first sheet, or (None, None).

    The export's first sheet is named after the tenant (e.g. CC100438) and
    holds the community's API id under "Gemeinschafts-ID". Taking both from
    the loaded member list means the fetch can never ask for one community's
    energy while the names come from another's.
    """
    if not meta:
        return None, None
    ec_id = str(meta.get("Gemeinschafts-ID") or "").strip() or None
    tenant = str(meta.get("Tenant") or "").strip() or None
    if tenant is None and ec_id:
        # Fallback for a meta dict without the sheet name: the tenant is
        # embedded in the ecId, e.g. ATCC9999DYNAM*CC100438*000000000249.
        found = re.findall(r"[A-Z]{2}\d{6}", ec_id)
        tenant = found[0] if found else None
    return tenant, ec_id


def quarter_range(year, quarter):
    """[start, end) of a quarter as Vienna-local, timezone-aware Timestamps."""
    if quarter not in (1, 2, 3, 4):
        raise ValueError(f"quarter must be 1-4, not {quarter!r}")
    start = pd.Timestamp(year=year, month=3 * (quarter - 1) + 1, day=1, tz=TIMEZONE)
    return start, start + pd.DateOffset(months=3)


def last_complete_quarter(today=None):
    today = today or pd.Timestamp.now(tz=TIMEZONE)
    current = (today.month - 1) // 3 + 1
    return (today.year, current - 1) if current > 1 else (today.year - 1, 4)


def parse_billing_period(year_text, quarter_text):
    """(year, quarter) from the invoice export's "Abrechnung" pieces, or None.

    The pieces come from splitting the period on "-", and what surrounds the
    digits has varied, so take the digits rather than trusting the format.
    """
    years = re.findall(r"\d{4}", str(year_text))
    quarters = re.findall(r"[1-4]", str(quarter_text))
    if years and quarters:
        return int(years[-1]), int(quarters[-1])
    return None


# --- fetching ---------------------------------------------------------------

def basic_auth_headers(user, password):
    """Authorization headers to try, most likely to work first.

    The energystore decodes Basic credentials with Go's URL-safe base64 and
    ignores the decode error (middleware/api_authentication.go). A login whose
    standard encoding contains "+" or "/" - any non-ASCII character can cause
    that, and so can "?", ">" or "~" in some positions - is cut short there
    and refused, although the password is right. So send the URL-safe form
    the server actually decodes, then the standard one in case that is ever
    fixed. For most logins the two are identical and only one is sent.

    UTF-8 rather than the latin-1 requests would use: the server hands the
    bytes to Keycloak as a Go string, which is UTF-8.
    """
    token = f"{user}:{password}".encode("utf-8")
    urlsafe = "Basic " + base64.urlsafe_b64encode(token).decode("ascii")
    standard = "Basic " + base64.b64encode(token).decode("ascii")
    return [urlsafe] if urlsafe == standard else [urlsafe, standard]


def fetch_rawdata(user, password, tenant, ec_id, start, end, session=None):
    """POST the rawdata query and return the decoded JSON body."""
    if ":" in password:
        # The server splits the decoded login on every ":" and keeps only the
        # first piece of the password, so such a password can never match.
        raise EEGFakturaError(
            "Die EEG Faktura Schnittstelle kann Passwörter mit Doppelpunkt (:) nicht "
            "annehmen. Bitte das Passwort in EEG Faktura ändern oder die Energiedaten "
            "wie bisher als Excel-Datei laden.")
    http = session or requests
    body = {"ecId": ec_id,
            "start": int(start.timestamp() * 1000),
            "end": int(end.timestamp() * 1000)}
    for header in basic_auth_headers(user, password):
        try:
            response = http.post(RAWDATA_URL, json=body,
                                 headers={"Authorization": header,
                                          "X-Tenant": tenant,
                                          "Accept": "application/json"},
                                 timeout=TIMEOUT)
        except requests.RequestException as e:
            raise EEGFakturaError(f"Keine Verbindung zu EEG Faktura: {e}") from e
        if response.status_code != 403:
            break
    if response.status_code in (401, 403):
        # The server answers 403 to every failed login - wrong password,
        # unknown user, or no access to this community - and says no more.
        raise EEGFakturaError(
            f"EEG Faktura hat die Anmeldung für {tenant} abgelehnt: entweder ist das "
            "Passwort falsch, oder dieses Konto hat keinen Zugriff auf die Gemeinschaft.")
    if not response.ok:
        raise EEGFakturaError(f"EEG Faktura antwortet mit HTTP {response.status_code}.")
    try:
        return response.json()
    except ValueError as e:
        raise EEGFakturaError("EEG Faktura hat keine lesbaren Daten geliefert.") from e


# --- who held which meter when ---------------------------------------------

def _local_midnight(value):
    """Vienna midnight of a member-list date, or None for blank or open-ended.

    Active meters carry 2999-12-31 as their deactivation date.
    """
    if value is None or (not isinstance(value, str) and pd.isna(value)):
        return None
    try:
        day = dt.date.fromisoformat(str(value).strip()[:10])
    except ValueError:
        return None
    if day.year >= 2200:
        return None
    return pd.Timestamp(day).tz_localize(TIMEZONE)


def participations_by_meter(members):
    """Metering point -> [(name, active_from, active_until)], one per row.

    The name is spelled the way the Energy Report spells it: "Name 1" + " " +
    "Name 2" verbatim, stray spaces and all (checked against all 37 meters of
    a real export). The rest of the app looks names up in that form.

    A meter that changed hands has one row per holder, and each holder gets
    their own columns. The period runs from local midnight of "aktiviert" up
    to, but not including, midnight after "deaktiviert": the export counts
    the whole deactivation day as active. None means unbounded.
    """
    result = {}
    if members is None or "Zählpunkt" not in members:
        return result
    for _, row in members.iterrows():
        meter = row.get("Zählpunkt")
        if meter is None or pd.isna(meter):
            continue
        first = "" if pd.isna(row.get("Name 1")) else str(row.get("Name 1"))
        last = "" if pd.isna(row.get("Name 2")) else str(row.get("Name 2"))
        since = _local_midnight(row.get("aktiviert"))
        until = _local_midnight(row.get("deaktiviert"))
        if until is not None:
            until = until + pd.DateOffset(days=1)
        result.setdefault(str(meter).strip(), []).append((f"{first} {last}", since, until))
    return result


def member_names_by_meter(members):
    """Metering point ID -> name of its first listed holder."""
    return {meter: rows[0][0] for meter, rows in participations_by_meter(members).items()}


# --- reshaping --------------------------------------------------------------

def _qov_level(qov, slot):
    """Normalise one quality flag to the export's "L0".."L3" spelling.

    The flag comes as one value per slot; a single value for the whole
    sample is accepted too.
    """
    if isinstance(qov, (list, tuple)):
        qov = qov[slot] if slot < len(qov) else None
    if qov is None or (isinstance(qov, float) and pd.isna(qov)):
        return None
    text = str(qov).strip().upper()
    return text if text.startswith("L") else f"L{text}"


def _value(values, slot):
    if not isinstance(values, (list, tuple)) or slot >= len(values):
        return float("nan")
    v = values[slot]
    return float("nan") if v is None else float(v)


def build_energy_frames(raw, members, start, end):
    """Turn a rawdata response into (energy, qov, unmatched_meters).

    energy: what load_energy_data reads from the "Energiedaten" sheet -
        a naive local-time index, columns (MeteringpointID, Name,
        Energy direction, Metercode). Cells are empty where the export
        leaves them empty: no reading delivered (L0), or outside the
        holder's membership.
    qov: what it reads from "QoV Log" - each value column followed by a
        column whose first level is "QoV" holding L0..L3. check_energydata
        finds the value column as the one just before each QoV column.
    unmatched_meters: metering points with readings that no member-list row
        covers. They are left out rather than given a made-up name, and the
        caller reports them.

    Rows are cut to [start, end): the API returns the whole of the end day,
    which would otherwise put a day of the next quarter into this one.
    """
    holders = participations_by_meter(members)
    energy_columns, energy_series = [], []
    qov_columns, qov_series = [], []
    unmatched = []

    for meter, entry in (raw or {}).items():
        direction = (entry or {}).get("direction")
        samples = (entry or {}).get("data") or []
        if direction not in METERCODES or not samples:
            continue
        index = (pd.to_datetime([s["ts"] for s in samples], unit="ms", utc=True)
                 .tz_convert(TIMEZONE))
        in_quarter = (index >= start) & (index < end)
        index = index[in_quarter]
        kept = [s for s, k in zip(samples, in_quarter) if k]
        if not kept:
            continue

        slots = METERCODES[direction]
        levels = {slot: pd.Series([_qov_level(s.get("qov"), slot) for s in kept],
                                  index=index, dtype=object)
                  for slot, _ in slots}
        values = {slot: pd.Series([_value(s.get("value"), slot) for s in kept],
                                  index=index, dtype=float)
                  for slot, _ in slots}
        has_reading = pd.concat([levels[slot] != NO_READING for slot, _ in slots],
                                axis=1).any(axis=1)

        covered = pd.Series(False, index=index)
        for name, since, until in holders.get(meter, []):
            active = pd.Series(True, index=index)
            if since is not None:
                active &= index >= since
            if until is not None:
                active &= index < until
            if not active.any():
                continue                    # held by this person in another quarter
            covered |= active
            for slot, metercode in slots:
                column = (meter, name, direction, metercode)
                shown = values[slot].where(active & (levels[slot] != NO_READING))
                energy_columns.append(column)
                energy_series.append(shown)
                qov_columns.append(column)
                qov_series.append(shown)
                # Mirrors the export's own blank-headed QoV column; the tuple
                # only has to be unique and start with "QoV".
                n = len(qov_columns)
                qov_columns.append(("QoV",) + tuple(f"Unnamed: {n}_level_{i}" for i in (1, 2, 3)))
                qov_series.append(levels[slot].where(active))

        if (has_reading & ~covered).any():
            unmatched.append(meter)

    energy = _frame(energy_series, energy_columns)
    qov = _frame(qov_series, qov_columns)
    return energy, qov, sorted(unmatched)


def _frame(series, columns):
    if not series:
        return pd.DataFrame(columns=pd.MultiIndex.from_tuples([], names=COLUMN_LEVELS))
    # Merge on the timezone-aware index, where every instant is unique, and
    # only then drop to local wall time as the export does: in late October
    # 02:00-02:45 occurs twice, and aligning on those duplicates fails.
    frame = pd.concat(series, axis=1).sort_index()
    frame.columns = pd.MultiIndex.from_tuples(columns, names=COLUMN_LEVELS)
    frame.index = frame.index.tz_localize(None)
    return frame


def fetch_quarter(user, password, tenant, ec_id, year, quarter, members, session=None):
    """Fetch and reshape one quarter. Returns (energy, qov, unmatched_meters)."""
    start, end = quarter_range(year, quarter)
    raw = fetch_rawdata(user, password, tenant, ec_id, start, end, session=session)
    if not isinstance(raw, dict):
        raise EEGFakturaError("EEG Faktura hat Daten in unerwarteter Form geliefert.")
    energy, qov, unmatched = build_energy_frames(raw, members, start, end)
    if energy.empty:
        raise EEGFakturaError(
            f"Für {year} Q{quarter} liefert EEG Faktura keine Energiedaten, "
            "die zur geladenen Mitgliederliste passen.")
    return energy, qov, unmatched
