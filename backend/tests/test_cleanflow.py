"""CleanFlow (DataLab 2.0) test suite.

Covers the scenarios required by the spec: missing values, duplicates,
incorrect data types, outliers, mixed date formats, empty datasets, invalid
uploads, large datasets, exports and session isolation.
"""
import io

import openpyxl

# ---------------------------------------------------------------------------
# Profiling
# ---------------------------------------------------------------------------

def test_profile_detects_issues(client, dirty_dataset):
    r = client.get(f"/api/cleanflow/datasets/{dirty_dataset}/profile")
    assert r.status_code == 200
    p = r.json()
    ov = p["overview"]
    assert ov["rows"] == 10 and ov["cols"] == 4
    assert ov["missing_cells"] >= 2
    assert ov["duplicate_rows"] >= 1
    types = {i["type"] for i in p["issues"]}
    assert "duplicates" in types
    assert "missing_values" in types
    assert "inconsistent_text" in types or "whitespace" in types
    assert 0 <= ov["quality_score"] <= 100
    assert ov["grade"]


def test_profile_score_breakdown_and_column_stats(client, dirty_dataset):
    p = client.get(f"/api/cleanflow/datasets/{dirty_dataset}/profile").json()
    assert set(p["scores"]) == {"completeness", "uniqueness", "validity", "consistency"}
    sales = next(c for c in p["columns"] if c["name"] == "Sales")
    assert sales["stats"]["max"] == 99999          # outlier row exists
    assert sales["outliers"]["iqr"] >= 1
    assert sales["stats"]["mean"] is not None


def test_profile_rejects_empty_dataset(client):
    r = client.post("/api/datasets/manual", json={
        "name": "Empty", "columns": [{"name": "a", "type": "text"}], "rows": []})
    assert r.status_code == 201
    ds = r.json()["id"]
    r = client.get(f"/api/cleanflow/datasets/{ds}/profile")
    assert r.status_code == 400


# ---------------------------------------------------------------------------
# Cleaning operations
# ---------------------------------------------------------------------------

def test_missing_value_strategies(client, dirty_dataset):
    for strategy, value in (("mean", None), ("median", None), ("mode", None),
                            ("constant", "0"), ("ffill", None)):
        ops = [{"type": "fill_missing", "columns": ["Sales"], "strategy": strategy}]
        if value is not None:
            ops[0]["value"] = value
        r = client.post(f"/api/cleanflow/datasets/{dirty_dataset}/clean",
                        json={"operations": ops})
        assert r.status_code == 200, r.text
    after = client.get(f"/api/datasets/{dirty_dataset}/dashboard").json()
    assert after["missing_cells"] == 0


def test_drop_missing_and_duplicates_require_approval(client, dirty_dataset):
    for op in ({"type": "drop_missing", "how": "any"},
               {"type": "drop_duplicates", "keep": "first"}):
        r = client.post(f"/api/cleanflow/datasets/{dirty_dataset}/clean",
                        json={"operations": [op]})
        assert r.status_code == 400
        assert "approval" in r.json()["detail"].lower()
    r = client.post(f"/api/cleanflow/datasets/{dirty_dataset}/clean",
                    json={"operations": [{**op, "approved": True}]})
    assert r.status_code == 200
    assert r.json()["before"]["rows"] > r.json()["after"]["rows"]


def test_duplicate_removal(client, dirty_dataset):
    r = client.post(f"/api/cleanflow/datasets/{dirty_dataset}/clean",
                    json={"operations": [{"type": "drop_duplicates", "keep": "first",
                                          "approved": True}]})
    assert r.status_code == 200
    assert r.json()["summary"].startswith("Removed 1 duplicate")


def test_type_correction_number_and_date(client, dirty_dataset):
    # Sales has "N/A" -> after CSV parsing it is numeric already; force text then fix
    client.post(f"/api/cleanflow/datasets/{dirty_dataset}/clean", json={"operations": [
        {"type": "convert_type", "columns": ["Sales"], "target": "text"},
    ]})
    r = client.post(f"/api/cleanflow/datasets/{dirty_dataset}/clean", json={"operations": [
        {"type": "convert_type", "columns": ["Sales"], "target": "number"},
        {"type": "parse_dates", "columns": ["Date"]},
    ]})
    assert r.status_code == 200
    p = client.get(f"/api/cleanflow/datasets/{dirty_dataset}/profile").json()
    sales = next(c for c in p["columns"] if c["name"] == "Sales")
    date = next(c for c in p["columns"] if c["name"] == "Date")
    assert sales["role"] == "numeric"
    assert date["role"] == "datetime"


def test_mixed_date_formats_parsed_and_flagged(client):
    """Default parse_dates is SAFE: invalid dates are flagged, never nulled."""
    csv = "when,value\n2024-01-01,1\n31/12/2023,2\nnot-a-date,3\n03/03/2024,4\n"
    ds = client.post("/api/cleanflow/datasets/upload",
                     files={"file": ("dates.csv", csv.encode())}).json()["id"]
    r = client.post(f"/api/cleanflow/datasets/{ds}/clean", json={"operations": [
        {"type": "parse_dates", "columns": ["when"]},
    ]})
    assert r.status_code == 200
    log = r.json()["operations"][0]
    assert "unparseable" in log["detail"] and "KEPT" in log["detail"]
    p = client.get(f"/api/cleanflow/datasets/{ds}/profile").json()
    when = next(c for c in p["columns"] if c["name"] == "when")
    assert when["missing"] == 0                     # nothing was silently lost
    # the raw value is preserved and a flag column marks it
    preview = client.get(f"/api/datasets/{ds}/preview").json()
    cols = [c["name"] for c in preview["columns"]]
    assert "when_invalid_date" in cols
    bad_rows = [row for row in preview["rows"] if "not-a-date" in row]
    assert bad_rows
    # nulling bad dates is destructive and requires explicit approval
    r = client.post(f"/api/cleanflow/datasets/{ds}/clean", json={"operations": [
        {"type": "parse_dates", "columns": ["when"], "on_error": "missing"}]})
    assert r.status_code == 400 and "approval" in r.json()["detail"].lower()
    r = client.post(f"/api/cleanflow/datasets/{ds}/clean", json={"operations": [
        {"type": "parse_dates", "columns": ["when"], "on_error": "missing",
         "approved": True}]})
    assert r.status_code == 200
    p = client.get(f"/api/cleanflow/datasets/{ds}/profile").json()
    when = next(c for c in p["columns"] if c["name"] == "when")
    assert when["missing"] == 1                     # approved → the bad value is missing


def test_ambiguous_dates_require_user_choice(client):
    """12-05-2024 is ambiguous: profiling flags it; day-first parsing decides."""
    csv = "d,v\n12-05-2024,1\n13-05-2024,2\n"   # 13 can only be a day
    ds = client.post("/api/cleanflow/datasets/upload",
                     files={"file": ("amb.csv", csv.encode())}).json()["id"]
    p = client.get(f"/api/cleanflow/datasets/{ds}/profile").json()
    types = {i["type"] for i in p["issues"]}
    assert "ambiguous_dates" in types
    issue = next(i for i in p["issues"] if i["type"] == "ambiguous_dates")
    assert "12-05-2024" in issue["detail"]
    rec = issue["recommendation"]
    assert rec["params"]["dayfirst"] is True and rec["params"]["on_error"] == "flag"
    # parse day-first: 12 May 2024 (not 5 Dec)
    r = client.post(f"/api/cleanflow/datasets/{ds}/clean", json={"operations": [
        {"type": "parse_dates", "columns": ["d"], "dayfirst": True}]})
    assert r.status_code == 200
    assert "day-first" in r.json()["operations"][0]["detail"]


def test_outliers_iqr_and_zscore(client):
    # 13 points: 500 is an outlier by both IQR fence AND z>3
    csv = "v\n" + "\n".join(str(x) for x in [10, 10, 11, 11, 12, 12, 13, 13, 11, 12, 10, 11, 500]) + "\n"
    ds = client.post("/api/cleanflow/datasets/upload",
                     files={"file": ("out.csv", csv.encode())}).json()["id"]
    p = client.get(f"/api/cleanflow/datasets/{ds}/profile").json()
    col = p["columns"][0]
    assert col["outliers"]["iqr"] >= 1
    assert col["outliers"]["zscore"] >= 1

    r = client.post(f"/api/cleanflow/datasets/{ds}/clean", json={"operations": [
        {"type": "handle_outliers", "columns": ["v"], "method": "iqr",
         "threshold": 1.5, "action": "flag"}]})
    assert r.status_code == 200
    cols = [c["name"] for c in client.get(f"/api/datasets/{ds}/columns").json()["columns"]]
    assert "v_outlier" in cols
    r = client.post(f"/api/cleanflow/datasets/{ds}/clean", json={"operations": [
        {"type": "handle_outliers", "columns": ["v"], "method": "iqr",
         "threshold": 1.5, "action": "remove", "approved": True}]})
    assert r.status_code == 200
    assert r.json()["after"]["rows"] == 12           # the 500 row is gone


def test_text_cleaning_and_category_standardization(client, dirty_dataset):
    r = client.post(f"/api/cleanflow/datasets/{dirty_dataset}/clean", json={"operations": [
        {"type": "clean_text", "columns": ["Region"], "trim": True, "collapse": True,
         "case": "title"},
        {"type": "standardize_categories", "columns": ["Region"]},
    ]})
    assert r.status_code == 200
    p = client.get(f"/api/cleanflow/datasets/{dirty_dataset}/profile").json()
    region = next(c for c in p["columns"] if c["name"] == "Region")
    assert region["unique"] == 4                    # North/South/East/West — no case variants


def test_sentinel_values_to_missing(client, dirty_dataset):
    r = client.post(f"/api/cleanflow/datasets/{dirty_dataset}/clean", json={"operations": [
        {"type": "replace_invalid", "columns": ["Product"], "values": ["-"]},
    ]})
    assert r.status_code == 200


def test_rename_drop_encode_normalize(client):
    csv = "old name,cat,num\na,x,1\nb,y,2\nc,x,3\n"
    ds = client.post("/api/cleanflow/datasets/upload",
                     files={"file": ("ops.csv", csv.encode())}).json()["id"]
    r = client.post(f"/api/cleanflow/datasets/{ds}/clean", json={"operations": [
        {"type": "rename_column", "column": "old name", "new_name": "label"},
        {"type": "normalize", "columns": ["num"]},
        {"type": "label_encode", "columns": ["cat"]},
    ]})
    assert r.status_code == 200
    cols = client.get(f"/api/datasets/{ds}/columns").json()["columns"]
    names = [c["name"] for c in cols]
    assert "label" in names and "old name" not in names

    r = client.post(f"/api/cleanflow/datasets/{ds}/clean", json={"operations": [
        {"type": "onehot_encode", "columns": [], "approved": True}]})
    assert r.status_code == 400  # no columns selected -> validation error

    r = client.post(f"/api/cleanflow/datasets/{ds}/clean", json={"operations": [
        {"type": "drop_column", "columns": ["cat"], "approved": True}]})
    assert r.status_code == 200
    names = [c["name"] for c in client.get(f"/api/datasets/{ds}/columns").json()["columns"]]
    assert "cat" not in names


def test_undo_restores_previous_state(client, dirty_dataset):
    before = client.get(f"/api/datasets/{dirty_dataset}/dashboard").json()
    client.post(f"/api/cleanflow/datasets/{dirty_dataset}/clean", json={"operations": [
        {"type": "drop_duplicates", "approved": True, "keep": "first"}]})
    after = client.get(f"/api/datasets/{dirty_dataset}/dashboard").json()
    assert after["rows"] == before["rows"] - 1
    r = client.post(f"/api/cleanflow/datasets/{dirty_dataset}/undo")
    assert r.status_code == 200
    restored = client.get(f"/api/datasets/{dirty_dataset}/dashboard").json()
    assert restored["rows"] == before["rows"]
    r = client.post(f"/api/cleanflow/datasets/{dirty_dataset}/undo")
    assert r.status_code == 400                     # nothing left to undo


def test_original_data_never_modified(client, dirty_dataset):
    """The working copy may change; the original snapshot must not."""
    orig = client.get(f"/api/datasets/{dirty_dataset}").json()
    client.post(f"/api/cleanflow/datasets/{dirty_dataset}/clean", json={"operations": [
        {"type": "fill_missing", "columns": ["Sales"], "strategy": "mean"},
        {"type": "drop_duplicates", "approved": True, "keep": "first"}]})
    client.post(f"/api/cleanflow/datasets/{dirty_dataset}/undo")
    # restore pulls from the immutable original snapshot
    r = client.post(f"/api/datasets/{dirty_dataset}/restore")
    assert r.status_code == 200
    restored = client.get(f"/api/datasets/{dirty_dataset}/dashboard").json()
    assert restored["rows"] == orig["rows"]


# ---------------------------------------------------------------------------
# ELT pipeline
# ---------------------------------------------------------------------------

def test_pipeline_preview_and_run(client, dirty_dataset):
    steps = [
        {"type": "drop_duplicates", "keep": "first"},
        {"type": "clean_text", "columns": ["Region"], "trim": True, "collapse": True},
        {"type": "parse_dates", "columns": ["Date"]},
        {"type": "fill_missing", "columns": ["Sales"], "strategy": "median"},
        {"type": "standardize_categories", "columns": ["Product"]},
    ]
    r = client.post(f"/api/cleanflow/datasets/{dirty_dataset}/pipeline/preview",
                    json={"steps": steps})
    assert r.status_code == 200
    pv = r.json()
    assert pv["summary"]["steps_ok"] == 5
    assert all(s["status"] == "ok" for s in pv["steps"])
    assert pv["steps"][0]["preview"]

    r = client.post(f"/api/cleanflow/datasets/{dirty_dataset}/pipeline/run",
                    json={"steps": steps, "result_name": "Pipeline Output"})
    assert r.status_code == 200
    out = r.json()
    assert out["result"]["name"] == "Pipeline Output"
    assert out["result"]["rows"] == 9

    # source dataset untouched (still 10 rows)
    src = client.get(f"/api/datasets/{dirty_dataset}").json()
    assert src["rows"] == 10


def test_pipeline_failing_step_reports_error(client, dirty_dataset):
    steps = [{"type": "fill_missing", "columns": ["DoesNotExist"], "strategy": "mean"}]
    r = client.post(f"/api/cleanflow/datasets/{dirty_dataset}/pipeline/preview",
                    json={"steps": steps})
    assert r.status_code == 200
    assert r.json()["steps"][0]["status"] == "error"
    r = client.post(f"/api/cleanflow/datasets/{dirty_dataset}/pipeline/run",
                    json={"steps": steps})
    assert r.status_code == 400
    assert "step 1" in r.json()["detail"].lower()


def test_saved_pipelines_crud_and_rerun(client, dirty_dataset):
    steps = [{"type": "drop_duplicates", "keep": "first"}]
    r = client.post("/api/cleanflow/pipelines",
                    json={"name": "Dedup", "description": "remove dupes", "steps": steps})
    assert r.status_code == 201
    pid = r.json()["id"]
    assert client.get("/api/cleanflow/pipelines").json()["pipelines"]
    got = client.get(f"/api/cleanflow/pipelines/{pid}").json()
    assert got["steps"][0]["type"] == "drop_duplicates"
    assert got["steps"][0]["keep"] == "first"
    upd = client.put(f"/api/cleanflow/pipelines/{pid}",
                     json={"name": "Dedup v2", "description": "", "steps": steps})
    assert upd.json()["name"] == "Dedup v2"
    # produce one recorded run so execution history is populated
    run = client.post(f"/api/cleanflow/datasets/{dirty_dataset}/pipeline/run",
                      json={"steps": steps})
    assert run.status_code == 200
    runs = client.get("/api/cleanflow/runs").json()["runs"]
    assert len(runs) >= 1
    assert client.delete(f"/api/cleanflow/pipelines/{pid}").json()["ok"] is True


# ---------------------------------------------------------------------------
# Quality report
# ---------------------------------------------------------------------------

def test_quality_report_before_after(client, dirty_dataset):
    client.post(f"/api/cleanflow/datasets/{dirty_dataset}/clean", json={"operations": [
        {"type": "drop_duplicates", "approved": True, "keep": "first"},
        {"type": "fill_missing", "columns": ["Sales"], "strategy": "mean"},
        {"type": "clean_text", "columns": ["Region"], "trim": True, "collapse": True},
    ]})
    r = client.get(f"/api/cleanflow/datasets/{dirty_dataset}/report")
    assert r.status_code == 200
    rep = r.json()
    assert rep["before"]["overview"]["rows"] == 10
    assert rep["after"]["overview"]["rows"] == 9
    assert rep["deltas"]["duplicates_removed"] == 1
    assert rep["deltas"]["missing_handled"] >= 1
    assert isinstance(rep["operations"], list)


# ---------------------------------------------------------------------------
# Uploads: formats, validation, edge cases
# ---------------------------------------------------------------------------

def test_upload_json_array_of_objects(client):
    payload = '[{"name": "Ada", "score": 90}, {"name": "Ben", "score": 75}]'
    r = client.post("/api/cleanflow/datasets/upload",
                    files={"file": ("people.json", payload.encode())})
    assert r.status_code == 201
    data = r.json()
    assert data["rows"] == 2 and data["cols"] == 2
    assert {c["name"] for c in data["columns"]} == {"name", "score"}


def test_upload_json_lines_and_column_object(client):
    jsonl = b'{"a": 1, "b": "x"}\n{"a": 2, "b": "y"}\n'
    r = client.post("/api/cleanflow/datasets/upload",
                    files={"file": ("recs.jsonl", jsonl)})
    assert r.status_code == 201 and r.json()["rows"] == 2
    colobj = b'{"x": [1, 2, 3], "y": [4, 5, 6]}'
    r = client.post("/api/cleanflow/datasets/upload",
                    files={"file": ("cols.json", colobj)})
    assert r.status_code == 201 and r.json()["rows"] == 3


def test_upload_xlsx(client, tmp_path):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["a", "b"])
    ws.append([1, 2.5])
    ws.append([3, 4.5])
    buf = io.BytesIO()
    wb.save(buf)
    r = client.post("/api/cleanflow/datasets/upload",
                    files={"file": ("sheet.xlsx", buf.getvalue())})
    assert r.status_code == 201
    assert r.json()["rows"] == 2


def test_invalid_uploads_rejected(client):
    # wrong extension
    r = client.post("/api/cleanflow/datasets/upload",
                    files={"file": ("evil.exe", b"MZ...")})
    assert r.status_code == 400
    # empty file
    r = client.post("/api/cleanflow/datasets/upload",
                    files={"file": ("empty.csv", b"")})
    assert r.status_code == 400
    # garbage bytes with a good extension
    r = client.post("/api/cleanflow/datasets/upload",
                    files={"file": ("junk.csv", b"\x00\x01\x02binary\x00garbage")})
    assert r.status_code in (400, 500) and r.status_code != 201
    # malformed JSON
    r = client.post("/api/cleanflow/datasets/upload",
                    files={"file": ("bad.json", b"{not json")})
    assert r.status_code == 400
    # oversized file (>15 MB)
    big = b"a,b\n1,2\n" + b"x" * (15 * 1024 * 1024 + 10)
    r = client.post("/api/cleanflow/datasets/upload",
                    files={"file": ("big.csv", big)})
    assert r.status_code == 413


def test_404_for_missing_dataset(client):
    assert client.get("/api/cleanflow/datasets/99999/profile").status_code == 404
    assert client.get("/api/cleanflow/datasets/99999/report").status_code == 404


# ---------------------------------------------------------------------------
# Large datasets
# ---------------------------------------------------------------------------

def test_large_dataset_operations(client):
    rows = 30000
    csv = "id,group,value\n" + "\n".join(
        f"{i},g{i % 7},{(i * 37) % 1000}" for i in range(rows)) + "\n"
    r = client.post("/api/cleanflow/datasets/upload",
                    files={"file": ("large.csv", csv.encode())})
    assert r.status_code == 201
    ds = r.json()["id"]
    assert r.json()["rows"] == rows

    r = client.post(f"/api/cleanflow/datasets/{ds}/clean", json={"operations": [
        {"type": "clean_text", "columns": ["group"], "trim": True, "collapse": True},
        {"type": "normalize", "columns": ["value"]},
        {"type": "fill_missing", "columns": ["value"], "strategy": "mean"},
    ]})
    assert r.status_code == 200
    p = client.get(f"/api/cleanflow/datasets/{ds}/profile").json()
    assert p["overview"]["rows"] == rows


# ---------------------------------------------------------------------------
# Export center
# ---------------------------------------------------------------------------

def test_exports_csv_xlsx_json(client, dirty_dataset):
    for fmt, magic in (("csv", None), ("xlsx", b"PK"), ("json", b"[")):
        r = client.get(f"/api/cleanflow/datasets/{dirty_dataset}/export?format={fmt}")
        assert r.status_code == 200
        body = r.content
        assert len(body) > 20
        if magic:
            assert body.startswith(magic)
        assert "attachment" in r.headers["content-disposition"]
    # JSON must keep the column names
    js = client.get(f"/api/cleanflow/datasets/{dirty_dataset}/export?format=json").json()
    rec = js[0]
    assert {"Date", "Region", "Sales", "Product"} == set(rec.keys())


def test_quality_report_downloads(client, dirty_dataset):
    r = client.get(f"/api/cleanflow/datasets/{dirty_dataset}/report/download?format=json")
    assert r.status_code == 200 and r.headers["content-type"].startswith("application/json")
    r = client.get(f"/api/cleanflow/datasets/{dirty_dataset}/report/download?format=html")
    assert r.status_code == 200
    html = r.content.decode()
    assert "Data Quality Report" in html
    assert "/home/" not in html and "/tmp/" not in html   # no local paths leaked


def test_cleanflow_history_listing(client, dirty_dataset):
    client.post(f"/api/cleanflow/datasets/{dirty_dataset}/clean", json={"operations": [
        {"type": "fill_missing", "columns": ["Sales"], "strategy": "mean"}]})
    rows = client.get("/api/cleanflow/history").json()["history"]
    assert any(h["action"] == "clean" for h in rows)
    by_ds = client.get(f"/api/cleanflow/history?dataset_id={dirty_dataset}").json()["history"]
    assert all(h["dataset_id"] == dirty_dataset for h in by_ds)


# ---------------------------------------------------------------------------
# Session isolation
# ---------------------------------------------------------------------------

def test_session_isolation(client):
    sa = {"X-Session-Id": "session-alpha"}
    sb = {"X-Session-Id": "session-beta"}
    r = client.post("/api/cleanflow/datasets/upload", headers=sa,
                    files={"file": ("a.csv", b"x,y\n1,2\n")})
    ds_a = r.json()["id"]
    # beta does not see alpha's dataset in the list
    names = [d["id"] for d in client.get("/api/datasets", headers=sb).json()["datasets"]]
    assert ds_a not in names
    # alpha sees it
    names_a = [d["id"] for d in client.get("/api/datasets", headers=sa).json()["datasets"]]
    assert ds_a in names_a
    # beta cannot touch alpha's dataset
    assert client.get(f"/api/cleanflow/datasets/{ds_a}/profile", headers=sb).status_code == 404
    # no header -> legacy behaviour (sees everything)
    names_all = [d["id"] for d in client.get("/api/datasets").json()["datasets"]]
    assert ds_a in names_all
