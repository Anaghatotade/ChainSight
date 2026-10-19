"""
config.py - single place for paths and project-wide constants.

Every script imports from here, so if you want to change e.g. the train/dev/test split or the assumed
lead time, you change it in ONE place.

DATA: the real Kaggle "M5 Forecasting - Accuracy" data (Walmart daily unit sales, 2011-2016). See docs/DATA_SOURCE.md.
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
DB_PATH = DATA_PROCESSED / "m5_retail.db"
DOCS = ROOT / "docs"

# the three raw files you download from Kaggle (a plain .csv or a gzipped .csv.gz both work)
RAW_FILES = {"calendar": "calendar.csv", "sales": "sales_train_validation.csv", "prices": "sell_prices.csv"}


def ensure_dirs():
    """Create output folders if they do not exist (safe to call many times)."""
    for p in (DATA_RAW, DATA_PROCESSED, CHARTS, TABLES, DASHBOARD, SQL_RESULTS):
        p.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------- reproducibility
SEED = 42                   # only the neural network and the permutation-importance shuffles are random

# ---------------------------------------------------------------- cleaning rules
DELIST_WEEKS = 8            # a series with no price listing in the last 8 weeks is treated as delisted
SPIKE_MULT = 10             # flag (never delete) a week with > 10x the series' median on-sale week
PRICE_JUMP = 3.0            # flag a week-to-week price change by more than 3x (up or down)

# ---------------------------------------------------------------- KPI conventions
ABC_A_CUTOFF = 0.80         # A = items that make up the first 80% of revenue
ABC_B_CUTOFF = 0.95         # B = next 15%, C = last 5%
CV_LOW = 0.50               # weekly demand CV bands (item-state level): < 0.50 stable, 0.50-1.00 variable, >= 1.00 erratic
CV_HIGH = 1.00
SLOW_ZERO_SHARE = 0.30      # a C item with no sale in more than 30% of its listed weeks is a "slow mover"
ADI_CUTOFF = 1.32           # Syntetos-Boylan demand classes (ADI, CV^2 of non-zero demand)
CV2_CUTOFF = 0.49
PRICE_CUT_RATIO = 0.90      # a week is a "price-cut week" if price <= 90% of the previous-8-week average price
EVENT_WINDOW_WEEKS = 8

# ---------------------------------------------------------------- inventory-policy ASSUMPTIONS
# The M5 data has NO inventory, lead-time, supplier or cost data. These numbers are ASSUMPTIONS (not findings)
# used only to show what a reorder policy would look like on top of the REAL demand. All outputs that use
# them are labelled "assumed" in the tables, charts and README.
ASSUMED_LEAD_TIME_WEEKS = 1     # order placed at the weekly review arrives 1 week later
REVIEW_PERIOD_WEEKS = 1         # inventory reviewed weekly
SERVICE_Z = 1.65                # z-score for ~95% cycle service level
FILL_RATE_TARGET = 0.95         # service target for the policy simulation
SERVICE_Z_BY_CLASS = {"A": 1.88, "B": 1.65, "C": 1.28}   # what-if: ~97% / 95% / 90% cycle service by ABC class
Z_GRID = (0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0)    # safety factors swept in the simulation

# ---------------------------------------------------------------- forecasting
# Time-based split on weekly data (no shuffling!). 225 + 24 + 24 = 273 full weeks.
TRAIN_WEEKS = 225
DEV_WEEKS = 24
TEST_WEEKS = 24
FORECAST_LEVEL = "item x state"  # 9,147 weekly series = what a regional distribution centre would forecast
MIN_HISTORY = 52                 # a row needs 52 earlier on-sale weeks (lag_52 = same week last year)
PRIMARY_METRIC = "WAPE"          # the ONE metric we optimise
BIAS_LIMIT = 0.05                # satisficing: |bias| must be <= 5% of demand
N_ERROR_ANALYSIS = 100           # how many biggest dev-set errors we tally
MIN_RELATIVE_GAIN = 0.05         # the NN must cut WAPE by >= 5% (relative) vs the best baseline to justify its complexity
NN_SEEDS = (42, 43, 44, 45, 46)  # NN training is random -> we report the spread over 5 seeds
SCALE_FLOOR = 1.0                # a series' scale is max(train mean, 1 unit/week) so near-dormant items cannot blow up
WINSOR_Q = 0.999                 # model INPUTS and training TARGETS are capped at the train 99.9th percentile (evaluation is never capped)
NN_EPOCHS = 60
NN_BATCH = 512
NN_LR = 0.003
NN_PATIENCE = 5
OUTLIER_RATIO_LOW = 0.6          # error analysis: actual / previous-8-week average outside [0.6, 1.6] = "outlier week"
OUTLIER_RATIO_HIGH = 1.6
SEASON_STEP = 0.10               # error analysis: category seasonal index changes by >= 0.10 vs previous month = "seasonal turn"
