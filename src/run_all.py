"""
run_all.py - run the whole pipeline in the right order (same as running steps 01..10 by hand).

Run:  python src/run_all.py            (add --skip-tests to skip pytest)
"""
import subprocess
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parent
STEPS = ["01_generate_data.py", "02_clean_data.py", "03_build_database.py", "04_run_sql_kpis.py", "05_eda.py",
         "06_kpi_analysis.py", "07_forecasting.py", "08_recommendations.py", "09_export_dashboard.py", "10_render_docs.py"]


def main():
    for step in STEPS:
        print(f"\n=== {step} ===", flush=True)
        subprocess.run([sys.executable, str(SRC / step)], check=True, cwd=SRC.parent)
    if "--skip-tests" not in sys.argv:
        print("\n=== pytest ===", flush=True)
        subprocess.run([sys.executable, "-m", "pytest", "-q"], check=True, cwd=SRC.parent)
    print("\nDone. Open README.md, outputs/charts/ and outputs/dashboard/.")


if __name__ == "__main__":
    main()
