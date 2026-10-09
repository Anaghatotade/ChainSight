# Setup and run guide (Windows PowerShell)

Tested with Python 3.10 - 3.12. No Docker, no database server, no `.sh` scripts: SQLite is built into Python.

## 1. Open PowerShell in the project folder
```powershell
cd C:\path\to\ChainSight
python --version
```

## 2. Create and activate a virtual environment
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```
If PowerShell blocks the activation script, allow it for this window only and retry:
```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```
(Command Prompt users: `.\.venv\Scripts\activate.bat`.)

## 3. Install packages
```powershell
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## 4. Run the pipeline - in this order
```powershell
python src/01_generate_data.py      # raw (messy) CSVs  -> data/raw
python src/02_clean_data.py         # cleaning + log    -> data/processed, outputs/tables/cleaning_log.csv
python src/03_build_database.py     # SQLite database   -> data/processed/chainsight.db
python src/04_run_sql_kpis.py       # all SQL queries   -> outputs/sql_results
python src/05_eda.py                # EDA charts/tables
python src/06_kpi_analysis.py       # KPIs, ABC, lead time, reorder-point check
python src/07_forecasting.py        # baselines vs linear vs NumPy MLP (1-3 minutes)
python src/08_recommendations.py    # business recommendations from the numbers
python src/09_export_dashboard.py   # Excel + Power BI-ready CSVs
python src/10_render_docs.py        # writes README.md and INTERVIEW_NOTES.md from the real outputs
```
Or everything in one go (steps 1-10, then the tests):
```powershell
python src/run_all.py
```
The data are generated with a fixed seed, so you get identical numbers every time.

## 5. Run the tests
```powershell
pytest
```
All tests should pass (takes a few seconds).

## 6. Open the notebooks
```powershell
python -m ipykernel install --user --name chainsight
jupyter notebook notebooks
```
Run notebooks in order 01 -> 05 (each one reads files written by the scripts, so run the pipeline first). Choose the `chainsight` kernel if asked.

## 7. Use the outputs
- Charts: `outputs/charts/*.png` (drop into PowerPoint / Power BI)
- Excel workbook: `outputs/dashboard/ChainSight_Dashboard_Data.xlsx`
- Power BI: *Get data -> Text/CSV*, load the files in `outputs/dashboard/` (dim_* and fact_* tables relate on `sku`, `supplier_code`, `warehouse_code`, `week_start`)
- Browse the database with any SQLite viewer on `data/processed/chainsight.db`, or in Python:
```powershell
python -c "import sqlite3; c=sqlite3.connect('data/processed/chainsight.db'); print(c.execute('select count(*) from demand_daily').fetchone())"
```
- Re-run only the SQL: `python src/04_run_sql_kpis.py`; edit the queries in `sql/*.sql` (each starts with `-- name: <query_name>`).

## Troubleshooting
| Problem | Fix |
|---|---|
| `python` not found | Install Python from python.org and tick "Add Python to PATH", or use `py -3` instead of `python` |
| `ModuleNotFoundError` | The venv is not active (prompt should start with `(.venv)`); repeat steps 2 and 3 |
| Charts do not appear | Normal: scripts save PNG files to `outputs/charts/` instead of opening windows |
| Notebook cannot import modules | Start Jupyter from the project root (`jupyter notebook notebooks`) - the notebooks add `src/` to the path themselves |
