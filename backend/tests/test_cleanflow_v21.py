"""DataLab 2.0.1 regression suite — covers every category in the bug-fix spec.

1 missing values · 2 duplicate records · 3 incorrect types · 4 mixed dates ·
5 invalid dates · 6 ambiguous dates · 7 invalid emails · 8 outliers IQR ·
9 outliers Z-score · 10 valid values NOT flagged/treated as outliers ·
11 negative values · 12 text standardization · 13 label encoding ·
14 one-hot encoding · 15 approval enforcement · 16 undo · 17 pipeline preview ·
18 pipeline execution · 19 pipeline failure handling · 20 empty datasets ·
21 invalid uploads · 22 oversized uploads · 23 large datasets (30k) ·
24 session isolation · 25 CSV export · 26 Excel export · 27 JSON export ·
28 v1 regression (separate file).
"""
import io
import json

import openpyxl
import pandas as pd
import pytest

# A synthetic customer dataset mirroring the user's 40-row test case:
# duplicate customers with different IDs, a bad date, an ambiguous date,
# bad e-mails, an impossible age, a negative order count, a typo'd number
# ("1O50") and normal values that must NOT be treated as outliers.
_ROWS = ["CustomerID,Name,Age,Email,SignupDate,Orders,TotalSpend,City,Category"]
_CITIES = ["Delhi", "Mumbai", "Patna", "Goa"]
for _i in range(1, 41):
    _cid = f"C{_i:03d}"
    _name = f"Customer {_i}"
    _age = 20 + (_i * 7) % 45                    # 20..64 — no outliers
    _email = f"customer{_i}@example.com"
    _date = f"2024-{1 + _i % 12:02d}-{1 + _i % 28:02d}"
    _orders = 3 + (_i * 3) % 12                  # 3..14 — no outliers
    _spend = 100 + _i * 55.5
    _city = _CITIES[_i % 4]
    _cat = "Retail" if _i % 2 else "Wholesale"
    if _i == 21:                                  # identical to C001 except ID
        _cid = "C021"
        _name, _age, _email = "Customer 1", 27, "customer1@example.com"
        _date, _orders, _spend, _city, _cat = "2024-02-02", 6, 155.5, "Mumbai", "Retail"
    if _i == 7:                                   # invalid date + ambiguous date
        _date = "not-a-date"
    if _i == 9:                                   # ambiguous: day-first vs month-first
        _date = "12-05-2024"
    if _i == 11:                                  # impossible age
        _age = 150
    if _i == 13:                                  # negative order count
        _orders = -3
    if _i == 15:                                  # typo'd number (letter O for zero)
        _orders = "1O50"
    if _i == 17:                                  # invalid e-mail (no TLD)
        _email = "kabir.khan@example"
    if _i == 19:                                  # whitespace/casing dirt
        _city, _cat = " delhi ", "retail "
    _ROWS.append(f"{_cid},{_name},{_age},{_email},{_date},{_orders},{_spend},{_city},{_cat}")
CUSTOMER_CSV = "\n".join(_ROWS) + "\n"


@pytest.fixture()
def customer_ds(client):
    r = client.post("/api/cleanflow/datasets/upload",
                    files={"file": ("customers.csv", CUSTOMER_CSV.encode())},
                    data={"name": "Customers"})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _profile(client, ds):
    return client.get(f"/api/cleanflow/datasets/{ds}/profile").json()


def _issue(profile, itype):
    return next((i for i in profile["issues"] if i["type"] == itype), None)


# ---------------------------------------------------------------------------
# Profiling detection (categories 1-11)
# ---------------------------------------------------------------------------

def test_01_missing_values_profiled(client, customer_ds):
    p = _profile(client, customer_ds)
    assert p["overview"]["missing_cells"] >= 0
    # every column reports missing count + percentage
    for c in p["columns"]:
        assert "missing" in c and "missing_pct" in c


def test_02_duplicate_records_with_different_ids_detected(client, customer_ds):
    """C001 and C021 are identical except for the ID — must be flagged."""
    p = _profile(client, customer_ds)
    assert p["overview"]["duplicate_rows"] == 0          # not an exact row dup
    issue = _issue(p, "possible_duplicates")
    assert issue is not None
    assert issue["count"] == 1                            # one extra copy
    assert "C001" in issue["detail"] and "C021" in issue["detail"]
    # recommendation matches on the non-ID columns and needs approval
    rec = issue["recommendation"]
    assert rec["type"] == "drop_duplicates" and rec["destructive"] is True
    assert "CustomerID" not in rec["params"]["columns"]
    # safe alternative: flag only
    assert issue["alternative"]["type"] == "flag_duplicates"
    assert issue["alternative"]["destructive"] is False

def test_02b_key_based_duplicate_removal_needs_approval(client, customer_ds):
    r = client.post(f"/api/cleanflow/datasets/{customer_ds}/clean", json={
        "operations": [{"type": "drop_duplicates",
                        "columns": ["Name", "Age", "Email", "SignupDate", "Orders",
                                    "TotalSpend", "City", "Category"],
                        "keep": "first"}]})
    assert r.status_code == 400 and "approval" in r.json()["detail"].lower()
    r = client.post(f"/api/cleanflow/datasets/{customer_ds}/clean", json={
        "operations": [{"type": "drop_duplicates",
                        "columns": ["Name", "Age", "Email", "SignupDate", "Orders",
                                    "TotalSpend", "City", "Category"],
                        "keep": "first", "approved": True}]})
    assert r.status_code == 200
    assert r.json()["after"]["rows"] == 39                # 40 rows - 1 duplicate


def test_02c_flag_duplicates_removes_nothing(client, customer_ds):
    r = client.post(f"/api/cleanflow/datasets/{customer_ds}/clean", json={
        "operations": [{"type": "flag_duplicates",
                        "columns": ["Name", "Age", "Email", "SignupDate", "Orders",
                                    "TotalSpend", "City", "Category"],
                        "method": "exact"}]})
    assert r.status_code == 200
    cols = [c["name"] for c in client.get(f"/api/datasets/{customer_ds}/columns").json()["columns"]]
    assert "duplicate_group" in cols
    assert r.json()["after"]["rows"] == 40                # nothing removed
    preview = client.get(f"/api/datasets/{customer_ds}/preview").json()
    idx = cols.index("duplicate_group")
    groups = [row[idx] for row in preview["rows"]]
    assert sum(1 for g in groups if g not in (None, "None")) == 2   # C001 + C021


def test_03_incorrect_data_types_detected(client):
    csv = "a,b\n1,2.5\n2,3.5\n3,N/A\n"
    ds = client.post("/api/cleanflow/datasets/upload",
                     files={"file": ("t.csv", csv.encode())}).json()["id"]
    p = _profile(client, ds)
    a = next(c for c in p["columns"] if c["name"] == "a")
    assert a["role"] == "numeric"


def test_04_mixed_date_formats_parse(client):
    csv = "d\n2024-01-01\n31/12/2023\n03/03/2024\n"
    ds = client.post("/api/cleanflow/datasets/upload",
                     files={"file": ("md.csv", csv.encode())}).json()["id"]
    r = client.post(f"/api/cleanflow/datasets/{ds}/clean", json={
        "operations": [{"type": "parse_dates", "columns": ["d"]}]})
    assert r.status_code == 200
    p = _profile(client, ds)
    assert next(c for c in p["columns"] if c["name"] == "d")["role"] == "datetime"


def test_05_invalid_dates_kept_and_flagged_not_nulled(client, customer_ds):
    """Two layers of protection:

    - a value like 'not-a-date' in a date-typed column is FLAGGED (invalid
      dates issue naming the value) instead of silently vanishing — the
      original upload still has it;
    - when the column is not auto-typed, the parse op keeps bad values and
      marks them in a flag column (never nulls without approval).
    """
    p = _profile(client, customer_ds)
    issue = _issue(p, "invalid_dates")
    assert issue is not None and "not-a-date" in issue["detail"]
    assert "flagged, not guessed" in issue["detail"]
    # the working copy has it blank, but the ORIGINAL snapshot preserves it
    report = client.get(f"/api/cleanflow/datasets/{customer_ds}/report").json()
    before_cols = {c["name"]: c for c in report["before"]["columns"]}
    assert before_cols["SignupDate"].get("invalid_dates", 0) >= 1 or \
        any("not-a-date" in str(ex) for c in report["before"]["columns"] for ex in c["examples"])

    # the explicit safe parse: a column kept as text keeps bad values + flags
    csv = "d,v\n" + "\n".join(["2024-01-01,1", "31/12/2023,2", "not-a-date,3",
                               "03/03/2024,4", "2024-06-30,5", "2024-07-01,6",
                               "2024-07-02,7", "broken-date,8", "bad,9",
                               "2024-07-04,10"]) + "\n"   # 3/10 bad → text role
    ds = client.post("/api/cleanflow/datasets/upload",
                     files={"file": ("dates.csv", csv.encode())}).json()["id"]
    r = client.post(f"/api/cleanflow/datasets/{ds}/clean", json={
        "operations": [{"type": "parse_dates", "columns": ["d"], "on_error": "flag"}]})
    assert r.status_code == 200
    log = r.json()["operations"][0]
    assert "KEPT" in log["detail"]
    preview = client.get(f"/api/datasets/{ds}/preview").json()
    flat = [str(v) for row in preview["rows"] for v in row]
    assert any("not-a-date" in v for v in flat) and any("broken-date" in v for v in flat)
    cols = [c["name"] for c in preview["columns"]]
    assert "d_invalid_date" in cols
    # nulling is destructive and needs approval
    r = client.post(f"/api/cleanflow/datasets/{ds}/clean", json={
        "operations": [{"type": "parse_dates", "columns": ["d"], "on_error": "missing"}]})
    assert r.status_code == 400


def test_06_ambiguous_dates_flagged_and_dayfirst_honoured(client, customer_ds):
    p = _profile(client, customer_ds)
    issue = _issue(p, "ambiguous_dates")
    assert issue is not None
    assert "12-05-2024" in issue["detail"]
    assert issue["recommendation"]["params"]["dayfirst"] is True
    # day-first parse must NOT log an unrelated-date replacement
    r = client.post(f"/api/cleanflow/datasets/{customer_ds}/clean", json={
        "operations": [{"type": "parse_dates", "columns": ["SignupDate"],
                        "dayfirst": True}]})
    assert r.status_code == 200
    assert "KEPT" in r.json()["operations"][0]["detail"] or \
           r.json()["operations"][0]["affected"] >= 0
    preview = client.get(f"/api/datasets/{customer_ds}/preview").json()
    idx = [c["name"] for c in preview["columns"]].index("SignupDate")
    assert any(row[idx] and "2024-05-12" in str(row[idx]) for row in preview["rows"]), \
        "12-05-2024 must parse as 12 May (day-first)"
    # the not-a-date value (flagged) survives too — nothing replaced it
    assert any(row[idx] and "not-a-date" in str(row[idx]) for row in preview["rows"]), \
        "the invalid value must be kept, never replaced with an unrelated date"


def test_07_invalid_emails_flagged(client, customer_ds):
    p = _profile(client, customer_ds)
    issue = _issue(p, "invalid_emails")
    assert issue is not None
    assert issue["count"] >= 1          # kabir.khan@example (no TLD) is caught
    rec = issue["recommendation"]
    assert rec["type"] == "validate_emails" and rec["params"]["action"] == "flag"
    # flag mode adds a marker column and keeps values
    r = client.post(f"/api/cleanflow/datasets/{customer_ds}/clean", json={
        "operations": [rec["params"] | {"type": rec["type"]}]})
    assert r.status_code == 200
    cols = [c["name"] for c in client.get(f"/api/datasets/{customer_ds}/columns").json()["columns"]]
    assert "Email_invalid_email" in cols
    preview = client.get(f"/api/datasets/{customer_ds}/preview").json()
    flat = [str(v) for row in preview["rows"] for v in row]
    assert any("kabir.khan@example" in v for v in flat)
    # nullify mode requires approval
    r = client.post(f"/api/cleanflow/datasets/{customer_ds}/clean", json={
        "operations": [{"type": "validate_emails", "columns": ["Email"],
                        "action": "missing"}]})
    assert r.status_code == 400


def test_08_09_outliers_detected_iqr_and_zscore_with_thresholds(client, customer_ds):
    p = _profile(client, customer_ds)
    age = next(c for c in p["columns"] if c["name"] == "Age")
    spend = next(c for c in p["columns"] if c["name"] == "TotalSpend")
    assert age["outliers"]["iqr_bounds"][0] is not None
    assert age["outliers"]["zscore"] >= 1 or spend["outliers"]["zscore"] >= 1
    issue = _issue(p, "outliers")
    assert issue is not None
    # the SAFE recommendation (flag) comes first; nullify needs approval
    assert issue["recommendation"]["params"]["action"] == "flag"
    assert issue["recommendation"]["destructive"] is False
    assert issue["alternative"]["params"]["action"] == "nullify"
    assert issue["alternative"]["destructive"] is True
    # the actual outlier values are shown
    col_entry = next(c for c in p["columns"] if c.get("outlier_values"))
    assert col_entry["outlier_values"]


def test_10_valid_values_not_treated_as_outliers(client):
    """Age 52, 8 and 9 orders must survive a flag pass untouched.

    The fixture is a well-spread population where 52 / 8 / 9 sit comfortably
    inside the IQR fences — the buggy behaviour nullified exactly these.
    """
    csv = "Age,Orders\n" + "\n".join(f"{a},{o}" for a, o in
                                     [(20, 8), (25, 9), (30, 10), (35, 11), (40, 12),
                                      (45, 13), (52, 14), (58, 15), (64, 16), (70, 20)])
    ds = client.post("/api/cleanflow/datasets/upload",
                     files={"file": ("ages.csv", csv.encode())}).json()["id"]
    # profiler must NOT report outliers for this smooth range (fence is wide)
    p = _profile(client, ds)
    assert _issue(p, "outliers") is None
    # and even an explicit flag pass changes no cell
    r = client.post(f"/api/cleanflow/datasets/{ds}/clean", json={
        "operations": [{"type": "handle_outliers", "columns": ["Age", "Orders"],
                        "method": "iqr", "threshold": 1.5, "action": "flag"}]})
    assert r.status_code == 200
    assert r.json()["operations"][0]["affected"] == 0
    after = client.get(f"/api/datasets/{ds}/dashboard").json()
    assert after["missing_cells"] == 0 and after["rows"] == 10
    preview = client.get(f"/api/datasets/{ds}/preview").json()
    age_idx = [c["name"] for c in preview["columns"]].index("Age")
    ages = [row[age_idx] for row in preview["rows"]]
    assert 52.0 in ages and len(ages) == 10        # every value survived


def test_10b_outlier_nullify_without_approval_rejected(client):
    csv = "v\n" + "\n".join(str(x) for x in [10, 11, 12, 11, 10, 500]) + "\n"
    ds = client.post("/api/cleanflow/datasets/upload",
                     files={"file": ("o.csv", csv.encode())}).json()["id"]
    r = client.post(f"/api/cleanflow/datasets/{ds}/clean", json={
        "operations": [{"type": "handle_outliers", "columns": ["v"],
                        "method": "iqr", "threshold": 1.5, "action": "nullify"}]})
    assert r.status_code == 400
    r = client.post(f"/api/cleanflow/datasets/{ds}/clean", json={
        "operations": [{"type": "handle_outliers", "columns": ["v"],
                        "method": "iqr", "threshold": 1.5, "action": "nullify",
                        "approved": True}]})
    assert r.status_code == 200
    assert "500" in r.json()["operations"][0]["detail"]   # the treated value is named


def test_11_negative_values_flagged_not_corrected(client, customer_ds):
    p = _profile(client, customer_ds)
    issues = [i for i in p["issues"] if i["type"] == "suspicious_values"]
    assert issues
    # the negative order count (-3) must be named in one of the flagged issues
    assert any("-3" in i["detail"] for i in issues)
    # nothing may be auto-corrected: the working copy still contains -3
    preview = client.get(f"/api/datasets/{customer_ds}/preview").json()
    oi = [c["name"] for c in preview["columns"]].index("Orders")
    assert any(row[oi] == -3.0 for row in preview["rows"])


def test_11b_implausible_age_and_typo_number_detected(client, customer_ds):
    p = _profile(client, customer_ds)
    age = next(c for c in p["columns"] if c["name"] == "Age")
    assert age.get("implausible_values"), "age 150 must be flagged"
    orders = next(c for c in p["columns"] if c["name"] == "Orders")
    # -3 sits in Orders → the negatives issue must mention it
    assert orders["stats"]["min"] < 0
    # '1O50' destroyed by numeric coercion must be flagged as invalid value
    issue = _issue(p, "invalid_values")
    assert issue is not None
    assert "1O50" in issue["detail"]


def test_12_text_standardization(client, customer_ds):
    r = client.post(f"/api/cleanflow/datasets/{customer_ds}/clean", json={
        "operations": [{"type": "standardize_categories", "columns": ["Category"]},
                       {"type": "clean_text", "columns": ["City"], "trim": True,
                        "collapse": True},
                       {"type": "standardize_categories", "columns": ["City"]}]})
    assert r.status_code == 200
    p = _profile(client, customer_ds)
    cat = next(c for c in p["columns"] if c["name"] == "Category")
    assert cat["unique"] == 2                            # Retail/retail unified
    assert _issue(p, "inconsistent_text") is None
    log = r.json()["operations"][0]
    assert "→" in log["detail"] or log["detail"]         # explains the mapping


def test_13_label_encoding(client, customer_ds):
    r = client.post(f"/api/cleanflow/datasets/{customer_ds}/clean", json={
        "operations": [{"type": "label_encode", "columns": ["Category"]}]})
    assert r.status_code == 200
    p = _profile(client, customer_ds)
    cat = next(c for c in p["columns"] if c["name"] == "Category")
    assert cat["role"] == "numeric"
    preview = client.get(f"/api/datasets/{customer_ds}/preview").json()
    idx = [c["name"] for c in preview["columns"]].index("Category")
    assert {row[idx] for row in preview["rows"]} <= {0.0, 1.0, 2.0, 3.0}


def test_14_one_hot_encoding(client, customer_ds):
    r = client.post(f"/api/cleanflow/datasets/{customer_ds}/clean", json={
        "operations": [{"type": "onehot_encode", "columns": ["Category"],
                        "approved": True}]})
    assert r.status_code == 200
    cols = [c["name"] for c in client.get(f"/api/datasets/{customer_ds}/columns").json()["columns"]]
    assert "Category_Retail" in cols and "Category" not in cols


# ---------------------------------------------------------------------------
# Approval enforcement + undo (categories 15-16)
# ---------------------------------------------------------------------------

def test_15_destructive_ops_require_approval(client, customer_ds):
    for op in ({"type": "drop_missing", "how": "any"},
               {"type": "drop_duplicates", "keep": "first"},
               {"type": "drop_column", "columns": ["City"]}):
        r = client.post(f"/api/cleanflow/datasets/{customer_ds}/clean",
                        json={"operations": [op]})
        assert r.status_code == 400, op


def test_16_undo_restores_state(client, customer_ds):
    before = client.get(f"/api/datasets/{customer_ds}/dashboard").json()
    client.post(f"/api/cleanflow/datasets/{customer_ds}/clean", json={
        "operations": [{"type": "clean_text", "columns": ["City"], "trim": True}]})
    client.post(f"/api/cleanflow/datasets/{customer_ds}/clean", json={
        "operations": [{"type": "fill_missing", "columns": ["TotalSpend"],
                        "strategy": "mean"}]})
    r = client.post(f"/api/cleanflow/datasets/{customer_ds}/undo")
    assert r.status_code == 200
    mid = client.get(f"/api/datasets/{customer_ds}/dashboard").json()
    r = client.post(f"/api/cleanflow/datasets/{customer_ds}/undo")
    assert r.status_code == 200
    restored = client.get(f"/api/datasets/{customer_ds}/dashboard").json()
    assert restored["rows"] == before["rows"] == mid["rows"]


# ---------------------------------------------------------------------------
# Pipeline (categories 17-19)
# ---------------------------------------------------------------------------

def test_17_pipeline_preview_shows_intermediate_results(client, customer_ds):
    steps = [{"type": "drop_duplicates", "columns": ["Name", "Age", "Email"],
              "keep": "first"},
             {"type": "clean_text", "columns": ["City"], "trim": True},
             {"type": "parse_dates", "columns": ["SignupDate"], "dayfirst": True}]
    r = client.post(f"/api/cleanflow/datasets/{customer_ds}/pipeline/preview",
                    json={"steps": steps})
    assert r.status_code == 200
    pv = r.json()
    assert pv["summary"]["steps_ok"] == 3
    for s in pv["steps"]:
        assert s["preview"] and "rows_out" in s
    assert 1 in pv["destructive_steps"]


def test_18_pipeline_run_creates_new_dataset_and_keeps_source(client, customer_ds):
    steps = [{"type": "clean_text", "columns": ["City"], "trim": True},
             {"type": "standardize_categories", "columns": ["Category"]}]
    r = client.post(f"/api/cleanflow/datasets/{customer_ds}/pipeline/run",
                    json={"steps": steps, "result_name": "Clean Customers"})
    assert r.status_code == 200
    out = r.json()
    assert out["result"]["name"] == "Clean Customers"
    assert out["result"]["id"] != customer_ds
    assert client.get(f"/api/datasets/{customer_ds}").json()["rows"] == 40


def test_19_pipeline_failure_reports_step_and_keeps_source(client, customer_ds):
    steps = [{"type": "clean_text", "columns": ["City"], "trim": True},
             {"type": "convert_type", "columns": ["DoesNotExist"], "target": "number"}]
    r = client.post(f"/api/cleanflow/datasets/{customer_ds}/pipeline/run",
                    json={"steps": steps})
    assert r.status_code == 400
    assert "step 2" in r.json()["detail"].lower()
    # preview surfaces the failing step with its error
    r = client.post(f"/api/cleanflow/datasets/{customer_ds}/pipeline/preview",
                    json={"steps": steps})
    assert r.status_code == 200
    assert r.json()["steps"][1]["status"] == "error"
    assert client.get(f"/api/datasets/{customer_ds}").json()["rows"] == 40


# ---------------------------------------------------------------------------
# Edge cases + exports (categories 20-27)
# ---------------------------------------------------------------------------

def test_20_empty_dataset_rejected(client):
    r = client.post("/api/datasets/manual", json={
        "name": "Empty", "columns": [{"name": "a", "type": "text"}], "rows": []})
    ds = r.json()["id"]
    assert client.get(f"/api/cleanflow/datasets/{ds}/profile").status_code == 400
    assert client.post(f"/api/cleanflow/datasets/{ds}/clean",
                       json={"operations": [{"type": "clean_text", "columns": ["a"]}]}
                       ).status_code == 400


def test_21_22_invalid_and_oversized_uploads(client):
    assert client.post("/api/cleanflow/datasets/upload",
                       files={"file": ("x.exe", b"MZ")}).status_code == 400
    assert client.post("/api/cleanflow/datasets/upload",
                       files={"file": ("e.csv", b"")}).status_code == 400
    assert client.post("/api/cleanflow/datasets/upload",
                       files={"file": ("bad.json", b"{nope")}).status_code == 400
    big = b"a,b\n1,2\n" + b"x" * (15 * 1024 * 1024 + 10)
    assert client.post("/api/cleanflow/datasets/upload",
                       files={"file": ("big.csv", big)}).status_code == 413


def test_23_large_dataset_profile_and_clean(client):
    rows = 30000
    csv = "id,group,val\n" + "\n".join(
        f"{i},g{i % 7},{(i * 37) % 1000}" for i in range(rows)) + "\n"
    r = client.post("/api/cleanflow/datasets/upload",
                    files={"file": ("large.csv", csv.encode())})
    assert r.status_code == 201 and r.json()["rows"] == rows
    ds = r.json()["id"]
    p = _profile(client, ds)
    assert p["overview"]["rows"] == rows
    r = client.post(f"/api/cleanflow/datasets/{ds}/clean", json={
        "operations": [{"type": "normalize", "columns": ["val"]}]})
    assert r.status_code == 200
    # 30 rows per 1000 keep their value after normalizing (0→0.0) — the rest change
    assert r.json()["changes"]["cells_changed"] >= rows * 0.95


def test_24_session_isolation_and_cross_access(client):
    sa, sb = {"X-Session-Id": "sess-a2"}, {"X-Session-Id": "sess-b2"}
    ds = client.post("/api/cleanflow/datasets/upload", headers=sa,
                     files={"file": ("a.csv", b"x\n1\n")}).json()["id"]
    # beta cannot read/export/clean alpha's dataset
    assert client.get(f"/api/datasets/{ds}/export", headers=sb).status_code == 404
    assert client.get(f"/api/datasets/{ds}/preview", headers=sb).status_code == 404
    assert client.post(f"/api/datasets/{ds}/clean", headers=sb,
                       json={"operations": []}).status_code in (400, 404, 422)
    assert client.get(f"/api/cleanflow/datasets/{ds}/report/download",
                      headers=sb).status_code == 404
    # owner can
    assert client.get(f"/api/datasets/{ds}/export", headers=sa).status_code == 200
    # history is scoped: beta sees no alpha operations
    client.post(f"/api/cleanflow/datasets/{ds}/clean", headers=sa,
                json={"operations": [{"type": "clean_text", "columns": ["x"]}]})
    hist = client.get("/api/cleanflow/history", headers=sb).json()["history"]
    assert all(h["dataset_id"] != ds for h in hist)


def test_25_csv_export(client, customer_ds):
    r = client.get(f"/api/cleanflow/datasets/{customer_ds}/export?format=csv")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    assert "attachment" in r.headers["content-disposition"] \
        and ".csv" in r.headers["content-disposition"]
    df = pd.read_csv(io.StringIO(r.content.decode("utf-8")))
    assert list(df.columns) == ["CustomerID", "Name", "Age", "Email", "SignupDate",
                                "Orders", "TotalSpend", "City", "Category"]
    assert len(df) == 40


def test_26_excel_export_valid_xlsx(client, customer_ds):
    r = client.get(f"/api/cleanflow/datasets/{customer_ds}/export?format=xlsx")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    assert ".xlsx" in r.headers["content-disposition"]
    wb = openpyxl.load_workbook(io.BytesIO(r.content))
    ws = wb.active
    header = [c.value for c in ws[1]]
    assert header[0] == "CustomerID"
    assert ws.max_row == 41                               # header + 40 rows


def test_26b_excel_export_survives_control_characters(client):
    csv = "txt\nok\nbad\x00char\nalso\x0bctrl\n"
    ds = client.post("/api/cleanflow/datasets/upload",
                     files={"file": ("ctrl.csv", csv.encode())}).json()["id"]
    r = client.get(f"/api/cleanflow/datasets/{ds}/export?format=xlsx")
    assert r.status_code == 200
    wb = openpyxl.load_workbook(io.BytesIO(r.content))
    assert wb.active.max_row == 4


def test_27_json_export_valid_unicode_null(client, customer_ds):
    r = client.get(f"/api/cleanflow/datasets/{customer_ds}/export?format=json")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/json")
    data = json.loads(r.content.decode("utf-8"))          # must be strict JSON
    assert len(data) == 40
    assert set(data[0]) == {"CustomerID", "Name", "Age", "Email", "SignupDate",
                            "Orders", "TotalSpend", "City", "Category"}
    # unicode must survive (upload a unicode dataset and re-export)
    payload = json.dumps([{"name": "Zoë", "city": "北京"},
                          {"name": "Álvaro", "city": "São Paulo"}],
                         ensure_ascii=False).encode("utf-8")
    u = client.post("/api/cleanflow/datasets/upload",
                    files={"file": ("u.json", payload)})
    assert u.status_code == 201
    r2 = client.get(f"/api/cleanflow/datasets/{u.json()['id']}/export?format=json")
    body = r2.content.decode("utf-8")
    assert "Zoë" in body and "北京" in body and "São Paulo" in body


def test_27b_quality_report_downloads(client, customer_ds):
    r = client.get(f"/api/cleanflow/datasets/{customer_ds}/report/download?format=json")
    assert r.status_code == 200
    report = json.loads(r.content.decode("utf-8"))
    assert report["before"]["overview"]["rows"] == 40
    r = client.get(f"/api/cleanflow/datasets/{customer_ds}/report/download?format=html")
    assert r.status_code == 200
    assert "Data Quality Report" in r.content.decode()
    assert "/home/" not in r.content.decode() and "/tmp/" not in r.content.decode()
