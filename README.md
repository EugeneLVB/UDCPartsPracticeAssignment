# Parts Catalog Parser

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
9. Enter the name of the task and click `Next`
10. In the next window, specify how often you want the script to run
11. In the `Action` configuration step, select `Start a program` and click `Next`
12. Since the windows scheduler does not use the environment, you need to find your python interpreter location. To do this open CMD (press `Win+R` > write `cmd` > press `Enter`). In the window that opens, enter the command `python -c "import sys; print(sys.executable)"`. In the response, you'll see something like `C:\Users\USER_NAME\AppData\Local\Python\bin\python.exe`. Copy the path to the Python interpreter and enter it in the scheduler settings window, as shown in `Step 14`
14. Action: **Start a program**
   - Program: `C:\Users\USER_NAME\AppData\Local\Python\bin\pythonw.exe`
   - Arguments: `C:\path\to\UDCPartsPracticeAssignment\parser.py`
   - Start in: `C:\path\to\UDCPartsPracticeAssignment`
> **⚠️** Please note that the Python interpreter executable file, python.exe, has been renamed to pythonw.exe. This is necessary to run the script silently as a background task without opening a command window each time the task is launched.
9. In the next window, make sure everything is set up correctly, then click `Finish`
> After each scheduled task runs, a parser output file (export.csv) will be created

## Importing a CSV file into Google Sheets
1. Open the link [Google Sheets](https://docs.google.com/spreadsheets/u/0/)
2. Click on `Blank spreadsheet`
3. In the new spreadsheet that opens, click `File` > `Import` > Tab `Upload`
4. Locate and click on the export.csv file in the UDCPartsPracticeAssignment folder
5. In the next window, just to be safe, you can uncheck the `Convert text to numbers, dates, and formulas` box, and then click `Import data`
6. Finish

## Log output example

```
2026-06-15T10:00:00 [INFO] Starting parser run
2026-06-15T10:00:01 [INFO] App Key: 555qPs25Mt...
2026-06-15T10:00:01 [INFO] Filters: [["Troy-Bilt", "11-Push Walk-Behind Mowers"]]
2026-06-15T10:00:05 [INFO] [PATH] MTD Merged Data Staging > Troy-Bilt > ... [LEAF] Blade
2026-06-15T10:00:05 [INFO] [+PART] ... | Blade | 942-04312 — Blade-21"
2026-06-15T10:00:30 [INFO] === Summary: total=1234, new=56, updated=3 ===
```
