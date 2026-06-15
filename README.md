# Parts Catalog Parser

Parses parts manuals from [genuinefactoryparts.com](https://www.genuinefactoryparts.com/en_US/ari-partstream.html) and exports structured data to CSV.

## Output

- `export.csv` — all parts with columns: `PATH`, `OEM`, `Description`
- `parser.db` — SQLite database with change tracking (upsert logic, no duplicates on re-run)
- `parser.log` — execution log with timestamps, errors, and summary stats

## Requirements

- Python 3.9+
- Dependencies: `requests`, `beautifulsoup4`

## Configuration

Example `config.json`:

```json
{
  "root_prefix": "MTD Merged Data Staging",
  "branches": [
    ["Troy-Bilt", "11-Push Walk-Behind Mowers", "2025 Models"],
    ["Troy-Bilt", "11-Push Walk-Behind Mowers", "2024 Models"],
    ["Troy-Bilt", "23-FLEX"],
    ["Troy-Bilt", "Garden Tools", "Loppers"]
  ],
  "ignore_quick_reference": true
}
```

- `root_prefix` — prepended to PATH in output (catalog name)
- `branches` — list of filters (each filter is a path from root to desired depth)
- `ignore_quick_reference` — skip `.Quick Reference` and `Label Map` nodes

## Run

```bash
python parser.py
```
or
```bash
python3 parser.py
```

## Deploy on Windows (Task Scheduler)

1. Install Python from [python.org](https://www.python.org/downloads/) (check "Add to PATH")
2. Install git from [git-scm.com](https://git-scm.com/install/windows)
3. Open CMD (press `Win+R` > write `cmd` > press `Enter`) and navigate to the directory where you want to place the parser code
4. Setup:
   ```
   # Clone the repository 
   git clone git@github.com:EugeneLVB/UDCPartsPracticeAssignment.git
   # Go to the catalog
   cd .\UDCPartsPracticeAssignment\
   # Install dependencies
   pip install -r requirements.txt
   ```
7. Open **Task Scheduler** (press `Win+R` > write `taskschd.msc` > press `Enter`)
8. Click **Create Basic Task**
9. Set trigger (e.g., Daily at 08:00)
10. Action: **Start a program**
   - Program: `python`
   - Arguments: `C:\path\to\UDCPartsPracticeAssignment\parser.py`
   - Start in: `C:\path\to\UDCPartsPracticeAssignment`
9. Finish

## Log output example

```
2026-06-15T10:00:00 [INFO] Starting parser run
2026-06-15T10:00:01 [INFO] App Key: 555qPs25Mt...
2026-06-15T10:00:01 [INFO] Filters: [["Troy-Bilt", "11-Push Walk-Behind Mowers"]]
2026-06-15T10:00:05 [INFO] [PATH] MTD Merged Data Staging > Troy-Bilt > ... [LEAF] Blade
2026-06-15T10:00:05 [INFO] [+PART] ... | Blade | 942-04312 — Blade-21"
2026-06-15T10:00:30 [INFO] === Summary: total=1234, new=56, updated=3 ===
```
