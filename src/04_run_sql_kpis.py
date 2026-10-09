"""
Step 4 - run every SQL query in sql/ and save the results as CSV.

Reads  data/processed/chainsight.db  and  sql/01_*.sql ... sql/06_*.sql
Writes outputs/sql_results/<file>__<query>.csv

Run:  python src/04_run_sql_kpis.py
"""
import db


def main():
    results = db.run_all_sql_files()
    for key, df in results.items():
        print(f"{key:<55} {len(df):>5} rows")
    print("\nIntegrity checks (all should be 0):")
    print(results["06_data_quality_checks__dq_integrity_checks"].to_string(index=False))


if __name__ == "__main__":
    main()
