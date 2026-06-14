import requests
import json
import time
from bs4 import BeautifulSoup
from urllib.parse import urlparse, parse_qs
from pathlib import Path


URL_ASSEMBLY = "https://partstreamstg.arinet.com/Parts/GetAssembly"
URL_DETAILS = "https://partstreamstg.arinet.com/Parts/GetDetails"
IFRAME_URL = "https://www.genuinefactoryparts.com/en_US/ari-iframe.html"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}


def get_app_key():
    r = requests.get(IFRAME_URL, headers=HEADERS)
    soup = BeautifulSoup(r.text, "html.parser")
    script_tag = soup.find("script", id="aripartstream")
    if not script_tag or not script_tag.get("src"):
        raise RuntimeError("Cannot find aripartstream script tag or its src attribute")
    parsed_url = urlparse(script_tag["src"])
    query_params = parse_qs(parsed_url.query)
    app_key = query_params.get("appKey", [None])[0]
    if not app_key:
        raise RuntimeError("appKey not found in script src URL")
    return app_key


def load_config():
    config_path = Path(__file__).parent / "config.json"
    if not config_path.exists():
        return [], True
    with open(config_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    branches = data.get("branches", [])
    ignore_quick_ref = data.get("ignore_quick_reference", True)
    return branches, ignore_quick_ref


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
    resp = requests.get(URL_ASSEMBLY, params=params, headers=HEADERS)
    resp.raise_for_status()
    data = resp.json()
    return data["model"]["json"]


def fetch_leaf(app_key, slug):
    params = build_params(app_key, ariq=slug)
    resp = requests.get(URL_DETAILS, params=params, headers=HEADERS)
    resp.raise_for_status()
    return resp.json()


def parse_leaf_html(html):
    soup = BeautifulSoup(html, "html.parser")
    parts = {}
    for li in soup.find_all("li"):
        tag_div = li.find("div", class_="ariPLTag")
        part_number_div = li.find("div", class_="ariPartNumber")
        desc_div = li.find("div", class_="ariPLDesc")
        if not (tag_div and part_number_div and desc_div):
            continue
        ref_number = tag_div.get_text(strip=True).replace("Ref:", "").strip()
        ref_key = f"Ref:{ref_number}"
        part_number = part_number_div.get_text(strip=True)
        description = desc_div.find(string=True, recursive=False).strip()
        if ref_key not in parts:
            parts[ref_key] = []
        parts[ref_key].append({"part_number": part_number, "description": description})
    return parts


def traverse(app_key, branch_filter, ignore_quick_ref, breadcrumb=None, aria=None, depth=0):
    if breadcrumb is None:
        breadcrumb = []

    nodes = fetch_children(app_key, aria)

    for node in nodes:
        node_name = node["data"]
        node_aria = node["attr"]["aria"]
        node_slug = node["attr"]["slug"]

        if depth < len(branch_filter) and node_name != branch_filter[depth]:
            continue

        if ignore_quick_ref and node_name == ".Quick Reference":
            continue

        current_breadcrumb = breadcrumb + [node_name]

        if node_slug == "":
            traverse(app_key, branch_filter, ignore_quick_ref, current_breadcrumb, node_aria, depth + 1)
        else:
            result = fetch_leaf(app_key, node_slug)
            parts = parse_leaf_html(result.get("html", ""))
            print(f"[PATH] {' > '.join(current_breadcrumb)}")
            print(f"[DATA] {json.dumps(parts, indent=2, ensure_ascii=False)}")
            print("=" * 60)


def main():
    app_key = get_app_key()
    branch_filter, ignore_quick_ref = load_config()
    print(f"App Key: {app_key}")
    print(f"Branch Filter: {branch_filter}")
    print(f"Ignore .Quick Reference: {ignore_quick_ref}")
    print("=" * 60)
    traverse(app_key, branch_filter, ignore_quick_ref)


if __name__ == "__main__":
    main()
