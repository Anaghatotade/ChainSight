# Screenshots

This folder is where the real UI screenshots go — captured from *your* running
app, since that's genuinely more convincing (and higher quality) in a
portfolio README than anything generated artificially. The main `README.md`
already references the exact filenames below, so once you drop these in and
push, the images will just appear.

## How to capture them

1. Run the app: `docker compose up` (or `up --build` if it's not already built)
2. Open http://localhost:3000 and log in as `analyst@chainsight.io`
3. For each page below, resize your browser to a clean width (~1400px wide
   is a good balance of detail and file size), let the charts fully load,
   and take a screenshot (Windows: `Win + Shift + S`)
4. Crop tightly to the app content — no browser chrome, no taskbar
5. Save as **PNG**, using the **exact filenames** listed below, into this folder

| Filename | Page | What to capture |
|---|---|---|
| `dashboard.png` | `/dashboard` | The KPI cards + the two trend charts visible together |
| `suppliers.png` | `/suppliers` | The scorecard table with a supplier selected (radar chart visible on the right) |
| `inventory.png` | `/inventory` | The inventory health table + status breakdown pie chart |
| `forecasting.png` | `/forecasting` | A forecast chart showing the historical/forecast split with confidence band |
| `risk.png` | `/risk` | The risk table with a SKU selected, showing the "Why this risk exists" explanation panel |
| `simulator.png` | `/simulator` | The What-If simulator after running a scenario — sliders + comparison chart + narrative |
| `recommendations.png` | `/recommendations` | The recommendations feed with a few different priority badges visible |

## Optional: compress before committing

Large PNGs bloat repo size over time. If any file is over ~500KB, run it
through [tinypng.com](https://tinypng.com) or `pngquant` before committing —
visually identical, much smaller.

## After adding the files

```bash
git add docs/screenshots/*.png
git commit -m "Add UI screenshots to README"
git push
```
