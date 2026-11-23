"""Regression tests: the original DataLab v1 features must keep working
after the CleanFlow upgrade (charts, stats, cleaning, export, history)."""
import io

import openpyxl


def test_v1_upload_csv_and_dashboard(client):
    csv = "city,population,area\nParis,2100,105\nBerlin,3600,891\nMadrid,3200,604\n"
    r = client.post("/api/datasets/upload", files={"file": ("cities.csv", csv.encode())},
                    data={"name": "Cities"})
    assert r.status_code == 201
    ds = r.json()["id"]
    dash = client.get(f"/api/datasets/{ds}/dashboard").json()
    assert dash["rows"] == 3 and dash["cols"] == 3
    assert dash["missing_cells"] == 0
    roles = {c["name"]: c["role"] for c in dash["column_details"]}
    assert roles["population"] == "numeric"
    assert roles["city"] == "categorical"


def test_v1_chart_recommendations_and_all_seven_charts(client):
    csv = ("month,sales,profit,region\n"
           "2024-01,100,22,East\n2024-02,120,31,East\n2024-03,90,12,West\n"
           "2024-04,140,44,West\n2024-05,130,37,East\n")
    ds = client.post("/api/datasets/upload",
                     files={"file": ("sales.csv", csv.encode())}).json()["id"]
    recs = client.get(f"/api/datasets/{ds}/recommendations").json()["recommendations"]
    assert recs and all("chart_type" in r and "params" in r for r in recs)

    cases = [
        {"chart_type": "bar", "x": "region", "y": "sales", "agg": "mean"},
        {"chart_type": "line", "x": "month", "y": "sales", "agg": "sum"},
        {"chart_type": "pie", "x": "region"},
        {"chart_type": "histogram", "x": "sales", "bins": 10},
        {"chart_type": "scatter", "x": "sales", "y": "profit"},
        {"chart_type": "box", "x": "region", "y": "sales"},
        {"chart_type": "heatmap", "heatmap_mode": "correlation"},
    ]
    for params in cases:
        r = client.post(f"/api/datasets/{ds}/chart", json=params)
        assert r.status_code == 200, f"{params['chart_type']}: {r.text}"
        fig = r.json()["figure"]
        assert fig["data"], params["chart_type"]

    # x == y must fail with a clean validation error, not a Plotly crash
    r = client.post(f"/api/datasets/{ds}/chart",
                    json={"chart_type": "scatter", "x": "sales", "y": "sales"})
    assert r.status_code == 400


def test_v1_statistics(client):
    csv = "x,y\n1,2\n2,4\n3,6\n4,8\n"
    ds = client.post("/api/datasets/upload",
                     files={"file": ("nums.csv", csv.encode())}).json()["id"]
    stats = client.get(f"/api/datasets/{ds}/stats").json()
    x = next(s for s in stats["summary"] if s["column"] == "x")
    assert x["mean"] == 2.5 and x["median"] == 2.5
    assert x["std"] is not None and x["modes"]
    assert stats["correlation"]["columns"] == ["x", "y"]
    assert abs(stats["correlation"]["matrix"][0][1] - 1.0) < 1e-6


def test_v1_clean_endpoint_still_works(client):
    csv = "a,b\n1,x\n1,x\n,y\n"
    ds = client.post("/api/datasets/upload",
                     files={"file": ("v1.csv", csv.encode())}).json()["id"]
    r = client.post(f"/api/datasets/{ds}/clean", json={"operations": [
        {"type": "drop_duplicates", "keep": "first"},
        {"type": "fill_missing", "columns": ["a"], "strategy": "mean"},
    ]})
    assert r.status_code == 200
    assert r.json()["after"]["rows"] == 2


def test_v1_manual_entry_grid_flow(client):
    r = client.post("/api/datasets/manual", json={
        "name": "Typed",
        "columns": [{"name": "when", "type": "date"}, {"name": "amount", "type": "number"}],
        "rows": [["2024-01-05", "10"], ["2024-02-05", "20.5"], ["oops", "bad"]],

    })
    assert r.status_code == 201
    data = r.json()
    assert data["rows"] == 3
    assert any("not valid" in w for w in data["warnings"])  # invalid cells cleared


def test_v1_export_csv_xlsx_and_history(client):
    csv = "a,b\n1,2\n3,4\n"
    ds = client.post("/api/datasets/upload",
                     files={"file": ("exp.csv", csv.encode())}).json()["id"]
    r = client.get(f"/api/datasets/{ds}/export?format=csv")
    assert r.status_code == 200 and b"a,b" in r.content
    r = client.get(f"/api/datasets/{ds}/export?format=xlsx")
    assert r.status_code == 200 and r.content.startswith(b"PK")
    hist = client.get("/api/history").json()["history"]
    assert any(h["action"] == "exported" for h in hist)
    assert any(h["action"] == "uploaded" for h in hist)


def test_v1_preview_pagination(client):
    csv = "n\n" + "\n".join(str(i) for i in range(120)) + "\n"
    ds = client.post("/api/datasets/upload",
                     files={"file": ("many.csv", csv.encode())}).json()["id"]
    r = client.get(f"/api/datasets/{ds}/preview?page=2&page_size=50").json()
    assert r["page"] == 2 and len(r["rows"]) == 50 and r["total_rows"] == 120


def test_v1_xlsx_upload_still_supported(client):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["k", "v"])
    ws.append(["a", 1])
    buf = io.BytesIO()
    wb.save(buf)
    r = client.post("/api/datasets/upload", files={"file": ("legacy.xlsx", buf.getvalue())})
    assert r.status_code == 201
    assert r.json()["rows"] == 1
