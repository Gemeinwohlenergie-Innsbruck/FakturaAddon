import os
import sys

import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import eegfaktura_api as api

CONS = "AT0050000000000000000000000000001"
GEN = "AT0050000000000000000000000000002"
STRANGER = "AT0050000000000000000000000000099"


def ms(text):
    return int(pd.Timestamp(text, tz=api.TIMEZONE).timestamp() * 1000)


def sample(text, values, qov=1):
    return {"ts": ms(text), "value": values, "qov": qov}


@pytest.fixture
def members():
    """One member with a consumer and a generator."""
    return pd.DataFrame({
        "Zählpunkt": [CONS, GEN],
        "Name 1": ["Anna", "Anna"],
        "Name 2": ["Müller", "Müller"],
    })


@pytest.fixture
def raw():
    return {
        CONS: {"direction": "CONSUMPTION", "data": [
            sample("2026-07-01 00:00", [0.5, 0.2, 0.1]),
            sample("2026-07-01 00:15", [0.6, 0.3, 0.2], qov=[1, 2, 3]),
            # The API includes the whole end day; this must be cut.
            sample("2026-10-01 00:00", [9.0, 9.0, 9.0]),
        ]},
        GEN: {"direction": "GENERATION", "data": [
            sample("2026-07-01 00:00", [1.0, 0.4, None]),
            sample("2026-07-01 00:15", [1.1, 0.5, None], qov="L2"),
        ]},
        STRANGER: {"direction": "CONSUMPTION", "data": [
            sample("2026-07-01 00:00", [7.0, 7.0, 7.0])]},
    }


def build(raw, members, year=2026, quarter=3):
    start, end = api.quarter_range(year, quarter)
    return api.build_energy_frames(raw, members, start, end)


def test_columns_match_the_export_layout(raw, members):
    energy, _, _ = build(raw, members)
    assert list(energy.columns.names) == api.COLUMN_LEVELS
    assert (CONS, "Anna Müller", "CONSUMPTION",
            "Eigendeckung gemeinschaftliche Erzeugung [KWH]") in energy.columns
    assert (GEN, "Anna Müller", "GENERATION",
            "Gesamt/Überschusserzeugung, Gemeinschaftsüberschuss [KWH]") in energy.columns


def test_slots_map_to_the_right_metercodes(raw, members):
    energy, _, _ = build(raw, members)
    at = pd.Timestamp("2026-07-01 00:15")
    cons = energy.xs(CONS, level="MeteringpointID", axis=1)
    assert cons.loc[at].xs("Gesamtverbrauch lt. Messung (bei Teilnahme gem. Erzeugung) [KWH]",
                           level="Metercode").iloc[0] == 0.6
    assert cons.loc[at].xs("Eigendeckung gemeinschaftliche Erzeugung [KWH]",
                           level="Metercode").iloc[0] == 0.2
    gen = energy.xs(GEN, level="MeteringpointID", axis=1)
    assert gen.loc[at].xs("Gesamte gemeinschaftliche Erzeugung [KWH]",
                          level="Metercode").iloc[0] == 1.1


def test_index_is_local_wall_time_cut_to_the_quarter(raw, members):
    energy, qov, _ = build(raw, members)
    assert energy.index.tz is None
    assert energy.index[0] == pd.Timestamp("2026-07-01 00:00")
    assert energy.index.max() < pd.Timestamp("2026-10-01")
    assert qov.index.max() < pd.Timestamp("2026-10-01")


def test_names_are_kept_verbatim_including_stray_spaces():
    """The rest of the app looks names up as the export spells them."""
    members = pd.DataFrame({"Zählpunkt": [CONS], "Name 1": ["Sonnenstrom GmbH"],
                            "Name 2": [float("nan")]})
    names = api.member_names_by_meter(members)
    assert names[CONS] == "Sonnenstrom GmbH "


def test_unknown_meters_are_reported_not_invented(raw, members):
    energy, _, unmatched = build(raw, members)
    assert unmatched == [STRANGER]
    assert STRANGER not in energy.columns.get_level_values("MeteringpointID")


def test_qov_columns_follow_their_value_column(raw, members):
    """check_energydata takes the column just before each QoV column."""
    _, qov, _ = build(raw, members)
    level0 = list(qov.columns.get_level_values(0))
    for i, label in enumerate(level0):
        if label == "QoV":
            assert level0[i - 1] != "QoV"
    assert level0.count("QoV") == 5          # 3 consumption + 2 generation codes


def test_qov_flags_are_normalised_per_slot(raw, members):
    _, qov, _ = build(raw, members)
    row = qov.loc[pd.Timestamp("2026-07-01 00:15")]
    flags = [v for (k, *_), v in row.items() if k == "QoV"]
    # Consumption came as [1, 2, 3], generation as a single "L2".
    assert flags == ["L1", "L2", "L3", "L2", "L2"]


def test_autumn_clock_change_does_not_break_merging(members):
    """02:00-02:45 happens twice on 25 Oct 2026; two meters must still merge."""
    first = pd.Timestamp("2026-10-25 01:45", tz=api.TIMEZONE).tz_convert("UTC")
    stamps = [int((first + pd.Timedelta(minutes=15 * i)).timestamp() * 1000) for i in range(8)]
    raw = {m: {"direction": d, "data": [{"ts": t, "value": [1.0, 1.0, 1.0], "qov": 1}
                                        for t in stamps]}
           for m, d in ((CONS, "CONSUMPTION"), (GEN, "GENERATION"))}
    energy, _, _ = build(raw, members, quarter=4)
    assert len(energy) == 8
    assert energy.index.duplicated().sum() == 3     # 02:00, 02:15, 02:30 twice


def test_community_comes_from_the_member_list():
    meta = {"Tenant": "GC106314", "Gemeinschafts-ID": "ATGC9999DYNAMGC106314000000000123"}
    assert api.community_from_meta(meta) == ("GC106314", "ATGC9999DYNAMGC106314000000000123")


def test_tenant_falls_back_to_the_one_inside_the_ec_id():
    meta = {"Gemeinschafts-ID": "ATCC9999DYNAMCC100438000000000249"}
    assert api.community_from_meta(meta) == ("CC100438", "ATCC9999DYNAMCC100438000000000249")


def test_no_member_list_means_no_community():
    assert api.community_from_meta(None) == (None, None)


@pytest.mark.parametrize("today, expected", [
    ("2026-10-15", (2026, 3)),
    ("2026-02-01", (2025, 4)),
])
def test_last_complete_quarter(today, expected):
    assert api.last_complete_quarter(pd.Timestamp(today, tz=api.TIMEZONE)) == expected


def test_billing_period_is_parsed_from_whatever_surrounds_the_digits():
    assert api.parse_billing_period("Abr_YQ_2026", "3") == (2026, 3)
    assert api.parse_billing_period("2026", "Q3") == (2026, 3)
    assert api.parse_billing_period("", "") is None


class FakeResponse:
    def __init__(self, status, body=None):
        self.status_code = status
        self.ok = 200 <= status < 300
        self._body = body

    def json(self):
        return self._body


class FakeSession:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def post(self, url, **kw):
        self.calls.append((url, kw))
        return self.response


def test_fetch_sends_tenant_and_quarter_bounds(raw, members):
    session = FakeSession(FakeResponse(200, raw))
    energy, _, _ = api.fetch_quarter("u", "p", "CC100438", "EC", 2026, 3, members,
                                     session=session)
    url, kw = session.calls[0]
    assert url == api.RAWDATA_URL
    assert kw["headers"]["X-Tenant"] == "CC100438"
    assert kw["json"]["start"] == ms("2026-07-01 00:00")
    assert kw["json"]["end"] == ms("2026-10-01 00:00")
    assert not energy.empty


@pytest.mark.parametrize("status, words", [
    (401, "Passwort"),
    (403, "keinen Zugriff"),
    (500, "HTTP 500"),
])
def test_http_errors_become_readable_messages(members, status, words):
    with pytest.raises(api.EEGFakturaError, match=words):
        api.fetch_quarter("u", "p", "CC100438", "EC", 2026, 3, members,
                          session=FakeSession(FakeResponse(status)))


def test_no_matching_meters_is_an_error_not_an_empty_success():
    with pytest.raises(api.EEGFakturaError, match="keine Energiedaten"):
        api.fetch_quarter("u", "p", "CC100438", "EC", 2026, 3, pd.DataFrame(),
                          session=FakeSession(FakeResponse(200, {})))


# --- the export's blanking rules -------------------------------------------

def frames_for(holders, samples, direction="CONSUMPTION", meter=CONS, quarter=3):
    """Build from one meter's samples with the given member-list rows."""
    members = pd.DataFrame([{"Zählpunkt": meter, "Name 1": n1, "Name 2": n2,
                             "aktiviert": since, "deaktiviert": until}
                            for n1, n2, since, until in holders])
    return build({meter: {"direction": direction, "data": samples}}, members, quarter=quarter)


def day_of_samples(day, values=(1.0, 0.5, 0.25), qov=1):
    return [sample(f"{day} {h:02d}:{m:02d}", list(values), qov)
            for h in range(24) for m in (0, 15, 30, 45)]


def test_no_reading_cells_are_empty_but_labelled_l0():
    """The export leaves L0 cells empty; 0 kWh would be a claim, not a gap."""
    energy, qov, _ = frames_for([("Anna", "Müller", "2024-01-01", "2999-12-31")],
                                [sample("2026-07-01 00:00", [0.0, 0.0, 0.0], qov=[0, 0, 0]),
                                 sample("2026-07-01 00:15", [0.4, 0.1, 0.1], qov=[1, 1, 1])])
    assert energy.iloc[0].isna().all()
    assert energy.iloc[1].notna().all()
    labels = qov.loc[:, qov.columns.get_level_values(0) == "QoV"]
    assert set(labels.iloc[0]) == {"L0"}


def test_values_start_at_midnight_of_the_activation_day():
    energy, _, unmatched = frames_for([("Anna", "Müller", "2026-07-02", "2999-12-31")],
                                      day_of_samples("2026-07-01") + day_of_samples("2026-07-02"))
    first = energy.dropna(how="all").index[0]
    assert first == pd.Timestamp("2026-07-02 00:00")
    assert energy.loc[:"2026-07-01 23:45"].isna().all().all()
    assert unmatched == [CONS]          # 1 July has readings nobody held the meter for


def test_the_deactivation_day_still_counts():
    """The export adds 23:59 to the deactivation date."""
    energy, _, _ = frames_for([("Anna", "Müller", "2024-01-01", "2026-07-01")],
                              day_of_samples("2026-07-01") + day_of_samples("2026-07-02"))
    held = energy.dropna(how="all").index
    assert held[0] == pd.Timestamp("2026-07-01 00:00")
    assert held[-1] == pd.Timestamp("2026-07-01 23:45")


def test_a_meter_that_changed_hands_gets_columns_for_each_holder():
    energy, _, unmatched = frames_for(
        [("Anna", "Müller", "2024-01-01", "2026-07-01"),
         ("Peter", "Schmidt", "2026-07-02", "2999-12-31")],
        day_of_samples("2026-07-01") + day_of_samples("2026-07-02"))
    anna = energy.xs("Anna Müller", level="Name", axis=1)
    peter = energy.xs("Peter Schmidt", level="Name", axis=1)
    assert anna.loc["2026-07-01"].notna().all().all() and anna.loc["2026-07-02"].isna().all().all()
    assert peter.loc["2026-07-01"].isna().all().all() and peter.loc["2026-07-02"].notna().all().all()
    assert unmatched == []


def test_a_holder_from_another_quarter_gets_no_columns():
    energy, _, unmatched = frames_for(
        [("Anna", "Müller", "2024-01-01", "2026-03-31"),
         ("Peter", "Schmidt", "2026-07-01", "2999-12-31")],
        day_of_samples("2026-07-01"))
    assert set(energy.columns.get_level_values("Name")) == {"Peter Schmidt"}
    assert unmatched == []


def test_l0_only_data_outside_membership_is_no_alarm():
    """Nothing was delivered there, so nothing was lost."""
    _, _, unmatched = frames_for([("Anna", "Müller", "2026-07-02", "2999-12-31")],
                                 day_of_samples("2026-07-01", values=(0, 0, 0), qov=[0, 0, 0])
                                 + day_of_samples("2026-07-02"))
    assert unmatched == []


def test_member_list_without_dates_keeps_everything():
    """Older member list exports may lack the date columns."""
    energy, _, unmatched = frames_for([("Anna", "Müller", float("nan"), float("nan"))],
                                      day_of_samples("2026-07-01"))
    assert energy.notna().all().all()
    assert unmatched == []


# --- logging in despite the server's quirks --------------------------------

import base64 as _b64


def test_plain_logins_send_one_standard_header():
    headers = api.basic_auth_headers("anna@example.at", "secret")
    assert headers == ["Basic " + _b64.b64encode(b"anna@example.at:secret").decode()]


def test_logins_the_server_would_misdecode_try_url_safe_first():
    """"a:?" encodes to YTo/ - the "/" stops the server's URL-safe decoder."""
    headers = api.basic_auth_headers("a", "?")
    assert headers == ["Basic YTo_", "Basic YTo/"]


def test_credentials_are_utf8():
    header = api.basic_auth_headers("a", "Grüß")[0]
    assert _b64.urlsafe_b64decode(header[len("Basic "):]) == "a:Grüß".encode("utf-8")


class SequenceSession(FakeSession):
    def __init__(self, responses):
        super().__init__(None)
        self.responses = list(responses)

    def post(self, url, **kw):
        self.calls.append((url, kw))
        return self.responses.pop(0)


def test_refused_url_safe_header_falls_back_to_standard(raw, members):
    session = SequenceSession([FakeResponse(403), FakeResponse(200, raw)])
    api.fetch_quarter("a", "?", "CC100438", "EC", 2026, 3, members, session=session)
    sent = [kw["headers"]["Authorization"] for _, kw in session.calls]
    assert sent == ["Basic YTo_", "Basic YTo/"]


def test_a_password_with_a_colon_is_refused_before_sending(members):
    session = FakeSession(FakeResponse(200, {}))
    with pytest.raises(api.EEGFakturaError, match="Doppelpunkt"):
        api.fetch_quarter("u", "pa:ss", "CC100438", "EC", 2026, 3, members, session=session)
    assert session.calls == []
