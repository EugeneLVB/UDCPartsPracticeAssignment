import requests
import json
import time
import sqlite3
import logging
from datetime import datetime, timezone
from bs4 import BeautifulSoup
from urllib.parse import urlparse, parse_qs
from pathlib import Path


LOG_PATH = Path(__file__).parent / "parser.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_PATH, encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger(__name__)

URL_ASSEMBLY = "https://partstreamstg.arinet.com/Parts/GetAssembly"
URL_DETAILS = "https://partstreamstg.arinet.com/Parts/GetDetails"
IFRAME_URL = "https://www.genuinefactoryparts.com/en_US/ari-iframe.html"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}


def get_app_key():
    try:
        r = requests.get(IFRAME_URL, headers=HEADERS, timeout=30)
        r.raise_for_status()
    except requests.RequestException as e:
        log.error("Failed to fetch iframe page: %s", e)
        raise
    soup = BeautifulSoup(r.text, "html.parser")
    script_tag = soup.find("script", id="aripartstream")
    if not script_tag or not script_tag.get("src"):
        log.error("Cannot find aripartstream script tag or its src attribute")
        raise RuntimeError("Cannot find aripartstream script tag or its src attribute")
    parsed_url = urlparse(script_tag["src"])
    query_params = parse_qs(parsed_url.query)
    app_key = query_params.get("appKey", [None])[0]
    if not app_key:
        log.error("appKey not found in script src URL")
        raise RuntimeError("appKey not found in script src URL")
    return app_key


def validate_filters(filters):
    for i, a in enumerate(filters):
        for j, b in enumerate(filters):
            if i == j:
                continue
            prefix_len = min(len(a), len(b))
            if a[:prefix_len] == b[:prefix_len]:
                raise ValueError(
                    f"Filters overlap: {a} and {b} — one is a prefix of the other"
                )


def load_config():
    config_path = Path(__file__).parent / "config.json"
    if not config_path.exists():
        log.warning("config.json not found, using defaults")
        return [[]], True
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        log.error("Failed to read config.json: %s", e)
        raise
    raw = data.get("branches", [])
    if raw and isinstance(raw[0], str):
        filters = [raw]
    else:
        filters = raw if raw else [[]]
    validate_filters(filters)
    ignore_quick_ref = data.get("ignore_quick_reference", True)
    return filters, ignore_quick_ref


def build_params(app_key, aria=None, ariq=None):
    params = {
        "arib": "MTF2_STAGING",
        "includeImgs": "true",
        "responsive": "true",
        "imgIsThmb": "true",
        "arik": app_key,
        "aril": "en-US",
        "ariv": IFRAME_URL,
        "_": str(int(time.time() * 1000)),
    }
    if ariq is not None:
        params["ariq"] = ariq
    elif aria is not None:
        params["aria"] = aria
    return params


def fetch_children(app_key, aria=None):
    params = build_params(app_key, aria=aria)
    try:
        resp = requests.get(URL_ASSEMBLY, params=params, headers=HEADERS, timeout=30)
        resp.raise_for_status()
    except requests.RequestException as e:
        log.error("Failed to fetch children (aria=%s): %s", aria, e)
        raise
    try:
        data = resp.json()
        return data["model"]["json"]
    except (json.JSONDecodeError, KeyError) as e:
        log.error("Unexpected response structure for children (aria=%s): %s", aria, e)
        raise


def fetch_leaf(app_key, slug):
    params = build_params(app_key, ariq=slug)
    try:
        resp = requests.get(URL_DETAILS, params=params, headers=HEADERS, timeout=30)
        resp.raise_for_status()
    except requests.RequestException as e:
        log.error("Failed to fetch leaf (slug=%s): %s", slug, e)
        raise
    try:
        return resp.json()
    except json.JSONDecodeError as e:
        log.error("Invalid JSON in leaf response (slug=%s): %s", slug, e)
        raise


def parse_leaf_html(html):
    soup = BeautifulSoup(html, "html.parser")
    parts = {}
    for li in soup.find_all("li"):
        part_number_div = li.find("div", class_="ariPartNumber")
        desc_div = li.find("div", class_="ariPLDesc")
        if not (part_number_div and desc_div):
            continue
        part_number = part_number_div.get_text(strip=True)
        if part_number == "N/A":
            continue
        desc_text = desc_div.find(string=True, recursive=False)
        if not desc_text:
            log.warning("Empty description for part_number=%s, skipping", part_number)
            continue
        parts[part_number] = desc_text.strip()
    return parts


DB_PATH = Path(__file__).parent / "parser.db"


def init_db():
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS leaves (
                path TEXT NOT NULL,
                leaf TEXT NOT NULL,
                active INTEGER NOT NULL DEFAULT 1,
                PRIMARY KEY (path, leaf)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS parts (
                path TEXT NOT NULL,
                leaf TEXT NOT NULL,
                part_number TEXT NOT NULL,
                description TEXT NOT NULL,
                PRIMARY KEY (path, leaf, part_number)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS changes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                path TEXT NOT NULL,
                leaf TEXT,
                part_number TEXT,
                change_type TEXT NOT NULL,
                old_value TEXT,
                new_value TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                path TEXT NOT NULL,
                leaf TEXT,
                leaf_count INTEGER,
                part_count INTEGER
            )
        """)
        conn.commit()
    except sqlite3.Error as e:
        log.error("Failed to initialize database: %s", e)
        raise
    return conn


def sync_leaves(conn, path, current_leaves, run_ts):
    try:
        cur = conn.execute(
            "SELECT leaf, active FROM leaves WHERE path = ?", (path,)
        )
        old_leaves = {row[0]: row[1] for row in cur.fetchall()}
    except sqlite3.Error as e:
        log.error("DB read error for leaves path=%s: %s", path, e)
        raise

    current_set = set(current_leaves)
    old_set = set(old_leaves.keys())

    try:
        for leaf in current_set - old_set:
            conn.execute(
                "INSERT INTO leaves (path, leaf, active) VALUES (?, ?, 1)",
                (path, leaf),
            )
            conn.execute(
                "INSERT INTO changes (timestamp, path, leaf, part_number, change_type, old_value, new_value) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (run_ts, path, leaf, None, "leaf_added", None, leaf),
            )
            log.info("[+LEAF] %s | %s", path, leaf)

        for leaf in current_set & old_set:
            if old_leaves[leaf] == 0:
                conn.execute(
                    "UPDATE leaves SET active = 1 WHERE path = ? AND leaf = ?",
                    (path, leaf),
                )
                conn.execute(
                    "INSERT INTO changes (timestamp, path, leaf, part_number, change_type, old_value, new_value) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (run_ts, path, leaf, None, "leaf_returned", None, leaf),
                )
                log.info("[↩LEAF] %s | %s", path, leaf)

        for leaf in old_set - current_set:
            if old_leaves[leaf] == 1:
                conn.execute(
                    "UPDATE leaves SET active = 0 WHERE path = ? AND leaf = ?",
                    (path, leaf),
                )
                conn.execute(
                    "INSERT INTO changes (timestamp, path, leaf, part_number, change_type, old_value, new_value) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (run_ts, path, leaf, None, "leaf_disappeared", leaf, None),
                )
                log.info("[-LEAF] %s | %s", path, leaf)

        conn.execute(
            "INSERT INTO snapshots (timestamp, path, leaf, leaf_count, part_count) VALUES (?, ?, ?, ?, ?)",
            (run_ts, path, None, len(current_set), None),
        )

        conn.commit()
    except sqlite3.Error as e:
        log.error("DB write error for leaves path=%s: %s", path, e)
        conn.rollback()
        raise


def sync_parts(conn, path, leaf, new_parts, run_ts):
    try:
        cur = conn.execute(
            "SELECT part_number, description FROM parts WHERE path = ? AND leaf = ?",
            (path, leaf),
        )
        old_parts = {row[0]: row[1] for row in cur.fetchall()}
    except sqlite3.Error as e:
        log.error("DB read error for path=%s leaf=%s: %s", path, leaf, e)
        raise

    added = set(new_parts.keys()) - set(old_parts.keys())
    common = set(new_parts.keys()) & set(old_parts.keys())
    added_count = 0
    modified_count = 0

    try:
        for pn in added:
            conn.execute(
                "INSERT INTO parts (path, leaf, part_number, description) VALUES (?, ?, ?, ?)",
                (path, leaf, pn, new_parts[pn]),
            )
            conn.execute(
                "INSERT INTO changes (timestamp, path, leaf, part_number, change_type, old_value, new_value) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (run_ts, path, leaf, pn, "part_added", None, new_parts[pn]),
            )
            added_count += 1
            log.info("[+PART] %s | %s | %s — %s", path, leaf, pn, new_parts[pn])

        for pn in common:
            if new_parts[pn] != old_parts[pn]:
                conn.execute(
                    "UPDATE parts SET description = ? WHERE path = ? AND leaf = ? AND part_number = ?",
                    (new_parts[pn], path, leaf, pn),
                )
                conn.execute(
                    "INSERT INTO changes (timestamp, path, leaf, part_number, change_type, old_value, new_value) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (run_ts, path, leaf, pn, "part_modified", old_parts[pn], new_parts[pn]),
                )
                modified_count += 1
                log.info("[~PART] %s | %s | %s — \"%s\" -> \"%s\"", path, leaf, pn, old_parts[pn], new_parts[pn])

        conn.execute(
            "INSERT INTO snapshots (timestamp, path, leaf, leaf_count, part_count) VALUES (?, ?, ?, ?, ?)",
            (run_ts, path, leaf, None, len(new_parts)),
        )

        conn.commit()
    except sqlite3.Error as e:
        log.error("DB write error for path=%s leaf=%s: %s", path, leaf, e)
        conn.rollback()
        raise

    return added_count, modified_count


def traverse(app_key, branch_filter, ignore_quick_ref, conn, run_ts, stats, breadcrumb=None, aria=None, depth=0):
    if breadcrumb is None:
        breadcrumb = []

    try:
        nodes = fetch_children(app_key, aria)
    except Exception:
        log.error("Skipping branch at depth=%d, breadcrumb=%s", depth, breadcrumb)
        return

    leaf_names = []
    path = " > ".join(breadcrumb) if breadcrumb else ""

    for node in nodes:
        node_name = node["data"]
        node_aria = node["attr"]["aria"]
        node_slug = node["attr"]["slug"]

        if depth < len(branch_filter) and node_name != branch_filter[depth]:
            continue

        if ignore_quick_ref and node_name in (".Quick Reference", "Label Map"):
            continue

        current_breadcrumb = breadcrumb + [node_name]

        if node_slug == "":
            traverse(app_key, branch_filter, ignore_quick_ref, conn, run_ts, stats, current_breadcrumb, node_aria, depth + 1)
        else:
            leaf_names.append(node_name)
            try:
                result = fetch_leaf(app_key, node_slug)
                parts = parse_leaf_html(result.get("html", ""))
                log.info("[PATH] %s [LEAF] %s", path, node_name)
                added, modified = sync_parts(conn, path, node_name, parts, run_ts)
                stats["total"] += len(parts)
                stats["added"] += added
                stats["modified"] += modified
            except Exception:
                log.error("Failed processing leaf=%s at path=%s", node_name, path)

    if leaf_names:
        try:
            sync_leaves(conn, path, leaf_names, run_ts)
        except Exception:
            log.error("Failed syncing leaves at path=%s", path)


def export_csv(conn):
    import csv
    csv_path = Path(__file__).parent / "export.csv"
    try:
        cur = conn.execute(
            "SELECT path, leaf, part_number, description FROM parts ORDER BY path, leaf, part_number"
        )
        rows = cur.fetchall()
    except sqlite3.Error as e:
        log.error("Failed to read parts for CSV export: %s", e)
        return
    try:
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["PATH", "OEM", "Description"])
            for path, leaf, part_number, description in rows:
                full_path = f"{path} > {leaf}" if path else leaf
                writer.writerow([full_path, part_number, description])
        log.info("Exported %d rows to %s", len(rows), csv_path)
    except OSError as e:
        log.error("Failed to write CSV: %s", e)


def main():
    log.info("Starting parser run")
    run_ts = datetime.now(timezone.utc).isoformat()

    try:
        app_key = get_app_key()
    except Exception:
        log.critical("Cannot obtain app_key, aborting")
        return

    try:
        filters, ignore_quick_ref = load_config()
    except Exception:
        log.critical("Invalid config, aborting")
        return

    try:
        conn = init_db()
    except Exception:
        log.critical("Cannot initialize database, aborting")
        return

    log.info("App Key: %s", app_key)
    log.info("Filters: %s", filters)
    log.info("Ignore .Quick Reference: %s", ignore_quick_ref)

    stats = {"total": 0, "added": 0, "modified": 0}
    for branch_filter in filters:
        traverse(app_key, branch_filter, ignore_quick_ref, conn, run_ts, stats)

    export_csv(conn)
    conn.close()
    log.info("=== Summary: total=%d, new=%d, updated=%d ===", stats["total"], stats["added"], stats["modified"])


if __name__ == "__main__":
    main()
