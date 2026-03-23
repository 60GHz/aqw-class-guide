"""
AQW Class Guide Scraper
=======================
Fetches all class pages from the AQW wiki, extracts skill data,
detects and merges duplicate/alias classes, and outputs a
structured JSON repository.

Usage:
    python scrape_classes.py              # Full scrape
    python scrape_classes.py --refresh    # Only fetch new/changed classes
    python scrape_classes.py --class "BladeMaster"  # Scrape a single class
"""

import requests
from bs4 import BeautifulSoup
import json
import os
import time
import re
import argparse
import hashlib
from datetime import datetime
from pathlib import Path

# ─── Configuration ───────────────────────────────────────────────────────────

BASE_URL        = "http://aqwwiki.wikidot.com"
TAG_LIST_URL    = f"{BASE_URL}/system:page-tags/tag/class"
DATED_LIST_URL  = (
    f"{BASE_URL}/search-items-by-tag/parent/Classes/tags/"
    "-_index%20-_redirect/perPage/250/order/created_at/p/"
)
OUTPUT_DIR      = Path("../data")
CLASSES_FILE    = OUTPUT_DIR / "classes.json"
RAW_INDEX_FILE  = OUTPUT_DIR / "raw_index.json"
FETCH_DELAY     = 1.2   # seconds between requests — be polite to the wiki

HEADERS = {
    "User-Agent": (
        "AQWClassGuideBot/1.0 "
        "(community project; github.com/YOUR_REPO; "
        "contact: YOUR_EMAIL)"
    )
}

# ─── Helpers ─────────────────────────────────────────────────────────────────

def get_page(url: str, retries: int = 3) -> BeautifulSoup | None:
    """Fetch a page and return a BeautifulSoup object, with retries."""
    for attempt in range(retries):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=15)
            resp.raise_for_status()
            return BeautifulSoup(resp.text, "html.parser")
        except requests.RequestException as e:
            print(f"  [!] Attempt {attempt+1}/{retries} failed for {url}: {e}")
            if attempt < retries - 1:
                time.sleep(3 * (attempt + 1))
    return None


def page_hash(soup: BeautifulSoup) -> str:
    """Return a hash of the page content for change detection."""
    content = soup.find("div", id="page-content")
    text = content.get_text() if content else soup.get_text()
    return hashlib.md5(text.encode()).hexdigest()


def load_json(path: Path) -> dict | list:
    if path.exists():
        with open(path) as f:
            return json.load(f)
    return {}


def save_json(data, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"  [✓] Saved → {path}")

# ─── Step 1: Collect Class Links ─────────────────────────────────────────────

def get_all_class_links() -> dict[str, str]:
    """
    Scrape the tag page to get {class_name: wiki_url} for all classes.
    Falls back to paginated dated list if tag page fails.
    Returns a dict: { "BladeMaster": "http://aqwwiki.wikidot.com/blademaster-class", ... }
    """
    print("\n[1] Fetching class list from tag index...")
    links = {}

    soup = get_page(TAG_LIST_URL)
    if soup:
        links = _parse_tag_page(soup)

    # If tag page failed or returned nothing, try paginated list
    if not links:
        print("  [!] Tag page failed, trying paginated list...")
        links = _parse_paginated_list()

    print(f"  Found {len(links)} class pages.")
    return links


def _parse_tag_page(soup: BeautifulSoup) -> dict[str, str]:
    """Parse the /system:page-tags/tag/class page."""
    links = {}
    # The tag page lists pages in a <div class="pages-list"> or similar
    content = soup.find("div", {"class": "pages-list"}) or soup.find("div", id="page-content")
    if not content:
        return links

    for a in content.find_all("a", href=True):
        href = a["href"]
        name = a.get_text(strip=True)
        if not name or not href:
            continue
        # Wiki links are like /blademaster-class or full URLs
        if href.startswith("/"):
            href = BASE_URL + href
        if "aqwwiki.wikidot.com" in href and name:
            # Filter out nav/meta links
            if any(skip in href for skip in ["system:", "forum:", "nav:", "search"]):
                continue
            # Clean up name — remove "(Class)" suffix if present
            clean = re.sub(r"\s*\(Class\)\s*$", "", name).strip()
            if clean:
                links[clean] = href

    return links


def _parse_paginated_list(pages: int = 3) -> dict[str, str]:
    """Parse the paginated search-items-by-tag list."""
    links = {}
    for p in range(1, pages + 1):
        url = DATED_LIST_URL + str(p)
        print(f"  Fetching page {p}: {url}")
        soup = get_page(url)
        if not soup:
            break

        content = soup.find("div", id="page-content") or soup
        found_any = False
        for a in content.find_all("a", href=True):
            href = a["href"]
            name = a.get_text(strip=True)
            if not name or not href:
                continue
            if href.startswith("/"):
                href = BASE_URL + href
            if "aqwwiki.wikidot.com" in href:
                clean = re.sub(r"\s*\(Class\)\s*$", "", name).strip()
                if clean and clean not in links:
                    links[clean] = href
                    found_any = True

        if not found_any:
            print(f"  No new entries on page {p}, stopping.")
            break
        time.sleep(FETCH_DELAY)

    return links

# ─── Step 2: Scrape Individual Class Pages ────────────────────────────────────

def scrape_class_page(name: str, url: str) -> dict:
    """
    Scrape a single class page and return a structured dict.
    """
    soup = get_page(url)
    if not soup:
        return {"name": name, "url": url, "error": "fetch_failed"}

    content = soup.find("div", id="page-content")
    if not content:
        return {"name": name, "url": url, "error": "no_content"}

    data = {
        "name":          name,
        "url":           url,
        "aliases":       [],         # Other names this class is also known as
        "description":   "",
        "tags":          [],         # e.g. ["Support", "DoT", "Warrior"]
        "mana_type":     "",         # e.g. "Mana", "Energy", "Adrenaline"
        "skills":        [],
        "notes":         "",
        "raw_text":      content.get_text("\n", strip=True),
        "page_hash":     page_hash(soup),
        "last_fetched":  datetime.utcnow().isoformat()
    }

    text = data["raw_text"]

    # ── Detect aliases ("This class has the same skills as:") ────────────────
    alias_block = re.search(
        r"This class has the same skills as[:\s]+(.*?)(?:\n\n|\Z)",
        text, re.DOTALL | re.IGNORECASE
    )
    if alias_block:
        raw_aliases = alias_block.group(1)
        # Each alias is on its own line, possibly with "(0 AC)", "(AC)", "(Merge)" etc.
        for line in raw_aliases.splitlines():
            line = line.strip()
            if not line:
                continue
            # Strip the type suffix like "(Class) (0 AC)" or "(Class) (Merge)"
            alias_clean = re.sub(r"\s*\(.*?\)\s*", "", line).strip()
            if alias_clean and alias_clean != name:
                data["aliases"].append(alias_clean)

    # ── Skills ───────────────────────────────────────────────────────────────
    data["skills"] = _parse_skills(content, text)

    # ── Description / Notes ──────────────────────────────────────────────────
    # Usually the first paragraph before the skills table
    paras = content.find_all("p")
    desc_parts = []
    for p in paras[:4]:
        t = p.get_text(strip=True)
        if t and len(t) > 20 and "same skills" not in t.lower():
            desc_parts.append(t)
    data["description"] = " ".join(desc_parts[:2])

    # ── Mana type ────────────────────────────────────────────────────────────
    mana_match = re.search(
        r"(Mana(?:gem[ae]nt)?|Adrenaline|Focus|Energy|Chi|Anima|Hate|Favour)",
        text, re.IGNORECASE
    )
    if mana_match:
        data["mana_type"] = mana_match.group(1)

    return data


def _parse_skills(content: BeautifulSoup, text: str) -> list[dict]:
    """
    Extract the skill list from the page content.
    AQW class pages typically have a table or list with skill name,
    mana cost, cooldown, description, and notes.
    """
    skills = []

    # Strategy 1: look for skill tables (most class pages use these)
    tables = content.find_all("table")
    for table in tables:
        rows = table.find_all("tr")
        if len(rows) < 2:
            continue

        headers = [th.get_text(strip=True).lower() for th in rows[0].find_all(["th", "td"])]
        # Check this looks like a skills table
        if not any(h in headers for h in ["skill", "name", "mana", "cooldown", "description"]):
            continue

        col_map = {}
        for i, h in enumerate(headers):
            for key in ["name", "mana", "cooldown", "description", "type", "effect"]:
                if key in h:
                    col_map[key] = i

        for row in rows[1:]:
            cells = row.find_all(["td", "th"])
            if not cells:
                continue
            skill = {
                "name":        _cell(cells, col_map.get("name", 0)),
                "mana_cost":   _cell(cells, col_map.get("mana", 1)),
                "cooldown":    _cell(cells, col_map.get("cooldown", 2)),
                "description": _cell(cells, col_map.get("description", 3)),
                "type":        _cell(cells, col_map.get("type", -1)),
                "effects":     [],
                "max_stack":   None,   # filled by guides later
            }
            if skill["name"]:
                # Try to detect stack count from description
                stack_match = re.search(
                    r"(?:up to|max(?:imum)?)\s+(\d+)\s+(?:stack|time)",
                    skill["description"], re.IGNORECASE
                )
                if stack_match:
                    skill["max_stack"] = int(stack_match.group(1))
                skills.append(skill)

        if skills:
            break   # Found skills in a table, stop looking

    # Strategy 2: fallback — look for bold skill names in paragraphs
    if not skills:
        skills = _parse_skills_from_text(text)

    return skills


def _cell(cells: list, index: int) -> str:
    """Safely get text from a table cell by index."""
    if index < 0 or index >= len(cells):
        return ""
    return cells[index].get_text(strip=True)


def _parse_skills_from_text(text: str) -> list[dict]:
    """
    Fallback skill parser using regex on raw text.
    Looks for patterns like:
      Auto Attack
      Type: Auto Attack
      Mana Cost: 0 Mana
      Cooldown: 0 seconds
    """
    skills = []
    # Split on double newlines to find blocks
    blocks = re.split(r"\n{2,}", text)
    for block in blocks:
        name_match = re.match(r"^([A-Z][^\n]{2,40})\n", block)
        if not name_match:
            continue
        name = name_match.group(1).strip()
        # Heuristic: block should contain mana or cooldown info
        if not re.search(r"(mana|cooldown|seconds)", block, re.IGNORECASE):
            continue
        skill = {
            "name": name,
            "mana_cost": _extract(block, r"Mana Cost[:\s]+([^\n]+)"),
            "cooldown":  _extract(block, r"Cooldown[:\s]+([^\n]+)"),
            "description": "",
            "type": _extract(block, r"Type[:\s]+([^\n]+)"),
            "effects": [],
            "max_stack": None,
        }
        skills.append(skill)
    return skills


def _extract(text: str, pattern: str) -> str:
    m = re.search(pattern, text, re.IGNORECASE)
    return m.group(1).strip() if m else ""

# ─── Step 3: Merge Duplicates ─────────────────────────────────────────────────

def merge_duplicates(classes: list[dict]) -> list[dict]:
    """
    Merge classes that are duplicates of each other.
    When class A lists class B (and C) as aliases, we:
      - Keep one canonical entry
      - Set its name to "A/B/C"
      - Remove the duplicate entries
    """
    print("\n[3] Merging duplicate/alias classes...")

    # Build alias → canonical index
    alias_to_canonical: dict[str, str] = {}
    by_name = {c["name"]: c for c in classes}

    for cls in classes:
        for alias in cls.get("aliases", []):
            alias_to_canonical[alias] = cls["name"]

    merged = []
    seen = set()

    for cls in classes:
        name = cls["name"]
        if name in seen:
            continue

        # Is this class itself an alias of something else?
        if name in alias_to_canonical:
            canonical_name = alias_to_canonical[name]
            # It will be handled when we process the canonical
            seen.add(name)
            continue

        # Collect all aliases and build merged name
        all_names = [name] + cls.get("aliases", [])
        unique_names = list(dict.fromkeys(all_names))  # preserve order, dedupe
        merged_name = "/".join(unique_names)

        canonical = cls.copy()
        canonical["name"] = merged_name
        canonical["canonical_name"] = name
        canonical["all_names"] = unique_names

        # Mark all alias entries as seen so we skip them
        for a in unique_names:
            seen.add(a)

        merged.append(canonical)

    # Sort alphabetically by canonical name (case-insensitive)
    merged.sort(key=lambda c: c["canonical_name"].lower())

    print(f"  {len(classes)} pages → {len(merged)} unique classes after merging.")
    return merged

# ─── Step 4: Refresh (diff-only) ─────────────────────────────────────────────

def refresh(existing_data: dict) -> list[dict]:
    """
    Fetch the current class list, compare to stored list,
    and only scrape new or changed pages.
    """
    print("\n[REFRESH] Checking for new/changed classes...")
    links = get_all_class_links()
    save_json(links, RAW_INDEX_FILE)

    existing_by_url = {}
    for cls in existing_data.get("classes", []):
        existing_by_url[cls["url"]] = cls

    new_or_changed = []
    for name, url in links.items():
        if url not in existing_by_url:
            print(f"  [+] New class: {name}")
            new_or_changed.append((name, url))
        # Could also check page_hash here by fetching lightly — skip for now

    print(f"  {len(new_or_changed)} new classes to fetch.")
    scraped = []
    for i, (name, url) in enumerate(new_or_changed, 1):
        print(f"  [{i}/{len(new_or_changed)}] Scraping: {name}")
        data = scrape_class_page(name, url)
        scraped.append(data)
        time.sleep(FETCH_DELAY)

    return scraped

# ─── Main Orchestrator ────────────────────────────────────────────────────────

def full_scrape():
    print("\n=== AQW Class Guide — Full Scrape ===")

    # Step 1: get list
    links = get_all_class_links()
    save_json(links, RAW_INDEX_FILE)

    # Step 2: scrape each page
    print(f"\n[2] Scraping {len(links)} class pages...")
    all_classes = []
    for i, (name, url) in enumerate(links.items(), 1):
        print(f"  [{i:>3}/{len(links)}] {name}")
        data = scrape_class_page(name, url)
        all_classes.append(data)
        time.sleep(FETCH_DELAY)

    # Step 3: merge duplicates
    merged = merge_duplicates(all_classes)

    # Step 4: save
    output = {
        "meta": {
            "total_classes":    len(merged),
            "last_full_scrape": datetime.utcnow().isoformat(),
            "source":           BASE_URL,
        },
        "classes": merged
    }
    save_json(output, CLASSES_FILE)
    print(f"\n✅ Done! {len(merged)} classes saved to {CLASSES_FILE}")


def scrape_one(class_name: str):
    """Scrape a single class for testing."""
    slug = class_name.lower().replace(" ", "-")
    url  = f"{BASE_URL}/{slug}-class"
    print(f"\n=== Scraping single class: {class_name} ===")
    data = scrape_class_page(class_name, url)
    print(json.dumps(data, indent=2))


def do_refresh():
    existing = load_json(CLASSES_FILE) if CLASSES_FILE.exists() else {"classes": []}
    new_classes = refresh(existing)
    if new_classes:
        merged_new = merge_duplicates(new_classes)
        combined = existing.get("classes", []) + merged_new
        # Re-sort the full list alphabetically by canonical name
        combined.sort(key=lambda c: c.get("canonical_name", c.get("name", "")).lower())
        existing["classes"] = combined
        existing.setdefault("meta", {})["last_refresh"] = datetime.utcnow().isoformat()
        existing["meta"]["total_classes"] = len(combined)
        save_json(existing, CLASSES_FILE)
        print(f"\n✅ Added {len(merged_new)} new classes (list re-sorted alphabetically).")
    else:
        print("\n✅ Nothing new to add.")


# ─── Entry Point ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AQW Class Guide Scraper")
    parser.add_argument("--refresh",  action="store_true", help="Only fetch new/changed classes")
    parser.add_argument("--class",    dest="cls",          help="Scrape a single class by name")
    parser.add_argument("--delay",    type=float, default=FETCH_DELAY, help="Delay between requests (seconds)")
    args = parser.parse_args()

    FETCH_DELAY = args.delay

    if args.cls:
        scrape_one(args.cls)
    elif args.refresh:
        do_refresh()
    else:
        full_scrape()
