# Setup and run guide (Windows PowerShell)

Tested with Python 3.10 - 3.12. No Docker, no database server, no `.sh` scripts: SQLite is built into Python.
Needs about 4 GB of free RAM for step 02 and about 1 GB of disk for the processed data and the SQLite file.

## 0. Get the data (one time) - you must do this yourself
The project uses the real Kaggle **M5 Forecasting - Accuracy** data. Kaggle needs your login and acceptance of the competition rules, so the files are not in the repository.

1. Open https://www.kaggle.com/competitions/m5-forecasting-accuracy/data, sign in, accept the rules.
2. Download these three files into `data\raw\` (plain `.csv` or gzipped `.csv.gz` both work):
   - `calendar.csv`
   - `sales_train_validation.csv`
   - `sell_prices.csv`
3. Check the folder:
```powershell
dir data\raw
```
(`docs/DATA_SOURCE.md` explains each file; after step 01 the file list with MD5 checksums is in `outputs/tables/raw_files.csv`.)

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
python src/01_prepare_data.py       # checks the 3 raw files, records checksums
python src/02_clean_data.py         # validation + cleaning -> data/processed, outputs/tables/cleaning_log.csv   (~20 s)
python src/verify_against_raw.py    # independent recomputation of revenue from the raw files; stops on a mismatch (~1-2 min)
python src/03_build_database.py     # SQLite database -> data/processed/m5_retail.db   (~40 s, a few hundred MB)
python src/04_run_sql_kpis.py       # all SQL queries -> outputs/sql_results   (~2-3 min)
python src/05_eda.py                # EDA charts/tables
python src/06_kpi_analysis.py       # ABC, demand variability, demand classes, assumption-based safety stock
python src/07_forecasting.py        # baselines vs linear vs NumPy MLP   (~3-10 min depending on your CPU)
python src/08_recommendations.py    # business recommendations from the numbers
python src/09_export_dashboard.py   # Excel + Power BI-ready CSVs
python src/10_render_docs.py        # writes README.md and INTERVIEW_NOTES.md from the real outputs
```
Or everything in one go (all steps, then the tests):
```powershell
python src/run_all.py
```
Run time is roughly 10-20 minutes in total. Step 01 starts a fresh `key_numbers.json`, so numbers from an older run can never leak into the docs. The only random parts (neural-network initialisation and permutation shuffles) use fixed seeds, so you get the same numbers on the same machine; tiny last-digit differences between machines / library versions are possible for the neural network.

## 5. Run the tests
```powershell
pytest
```
The tests use tiny hand-made M5-style data, not the real files, so they run in seconds and do not need the download.

## 6. Open the notebooks
```powershell
python -m ipykernel install --user --name chainsight
jupyter notebook notebooks
```
Run notebooks in order 01 -> 05 (each one reads files written by the scripts, so run the pipeline first). Choose the `chainsight` kernel if asked.

## 7. Use the outputs
- Charts: `outputs/charts/*.png` (drop into PowerPoint / Power BI)
- Excel workbook: `outputs/dashboard/M5_Retail_Dashboard_Data.xlsx`
- Power BI: *Get data -> Text/CSV*, load the files in `outputs/dashboard/` (facts relate to `dim_item`, `dim_store`, `dim_week` on `item_id`, `store_id`, `week_idx`, and to `dim_date` on `date`)
- Browse the database with any SQLite viewer on `data/processed/m5_retail.db`, or in Python:
```powershell
python -c "import sqlite3; c=sqlite3.connect('data/processed/m5_retail.db'); print(c.execute('select count(*) from fact_weekly_sales').fetchone())"
```
- Re-run only the SQL: `python src/04_run_sql_kpis.py`; edit the queries in `sql/*.sql` (each starts with `-- name: <query_name>`).
- Change an assumption (lead time, service level, train/dev/test weeks, thresholds) in **one place**: `src/config.py`, then re-run steps 06-10.

## Troubleshooting
| Problem | Fix |
|---|---|
| `FileNotFoundError: Missing sales_train_validation.csv` | Step 0 not done, or the file is in the wrong folder: it must be in `data\raw\` |
| `python` not found | Install Python from python.org and tick "Add Python to PATH", or use `py -3` instead of `python` |
| `ModuleNotFoundError` | The venv is not active (prompt should start with `(.venv)`); repeat steps 2 and 3 |
| `MemoryError` in step 02 | Close other programs; the wide sales table needs a few GB of RAM while loading |
| Charts do not appear | Normal: scripts save PNG files to `outputs/charts/` instead of opening windows |
| Notebook cannot import modules | Start Jupyter from the project root (`jupyter notebook notebooks`) - the notebooks add `src/` to the path themselves |
| `VERIFICATION FAILED` | The independent check found a difference between the pipeline and the raw data - do not trust the outputs until it is explained |
