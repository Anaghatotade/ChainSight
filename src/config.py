"""
config.py - single place for paths and project-wide constants.

Every script imports from here, so if you want to change e.g. the random seed or
the train/dev/test split, you change it in ONE place.
"""
from pathlib import Path

# ---------------------------------------------------------------- paths
ROOT = Path(__file__).resolve().parents[1]
DATA_RAW = ROOT / "data" / "raw"
DATA_PROCESSED = ROOT / "data" / "processed"
SQL_DIR = ROOT / "sql"
OUTPUTS = ROOT / "outputs"
CHARTS = OUTPUTS / "charts"
TABLES = OUTPUTS / "tables"
DASHBOARD = OUTPUTS / "dashboard"
SQL_RESULTS = OUTPUTS / "sql_results"
DB_PATH = DATA_PROCESSED / "chainsight.db"
DOCS = ROOT / "docs"


def ensure_dirs():
    """Create output folders if they do not exist (safe to call many times)."""
    for p in (DATA_RAW, DATA_PROCESSED, CHARTS, TABLES, DASHBOARD, SQL_RESULTS):
        p.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------- synthetic data
SEED = 42
START_DATE = "2024-01-01"   # a Monday, so weeks line up neatly
N_WEEKS = 104               # 2 full years of history
N_DAYS = N_WEEKS * 7        # 728 days
N_SKUS = 90
N_SUPPLIERS = 24

# ---------------------------------------------------------------- KPI conventions
ABC_A_CUTOFF = 0.80         # A = items that make up the first 80% of revenue
ABC_B_CUTOFF = 0.95         # B = next 15%, C = last 5%
CV_LOW = 0.30               # demand CV bands (daily CV): <0.30 low, 0.30-0.50 medium, >=0.50 high
CV_HIGH = 0.50
FILL_RATE_TARGET = 0.95     # service target drawn on charts / used to count months
SERVICE_Z = 1.65            # z-score for ~95% cycle service level
REVIEW_PERIOD_DAYS = 7      # inventory is reviewed weekly (same as the simulated company policy)

# ---------------------------------------------------------------- forecasting
# Time-based split on weekly data (no shuffling!). 72 + 16 + 16 = 104 weeks.
TRAIN_WEEKS = 72
DEV_WEEKS = 16
TEST_WEEKS = 16
PRIMARY_METRIC = "WAPE"     # the ONE metric we optimise
BIAS_LIMIT = 0.05           # satisficing: |bias| must be <= 5% of demand
N_ERROR_ANALYSIS = 100      # how many biggest dev-set errors we tally
MIN_RELATIVE_GAIN = 0.05    # the NN must cut WAPE by >= 5% (relative) vs the best baseline to justify its complexity
NN_SEEDS = (42, 43, 44, 45, 46)   # NN training is random -> we report the spread over 5 seeds
OUTLIER_RATIO_LOW = 0.6     # error analysis: actual / previous-8-week average outside [0.6, 1.6] = "outlier week"
OUTLIER_RATIO_HIGH = 1.6
SEASON_STEP = 0.10          # error analysis: category seasonal index changes by >= 0.10 vs previous month = "seasonal turn"
