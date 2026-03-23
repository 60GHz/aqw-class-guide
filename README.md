# AQW Class Guide 📖⚔️

A community-driven, scalable reference guide for AdventureQuest Worlds classes —
built to help players understand max-stack output, build optimized comps, and
discover synergies.

---

## Project Roadmap

| Phase | Status | Description |
|-------|--------|-------------|
| **1** | 🔨 In Progress | Data acquisition — scrape all class pages, merge duplicates, build JSON repo |
| **2** | ⏳ Planned | Data modeling — max-stack analysis, role tagging, buff/debuff catalog |
| **3** | ⏳ Planned | Discord bot — `/class`, `/comp`, daily legend post |
| **4** | ⏳ Planned | Web interface — searchable DB, visual comp builder |

---

## Phase 1: Getting Started

### Prerequisites

```bash
pip install -r requirements.txt
```

### Run a full scrape

```bash
cd scraper
python scrape_classes.py
```

This will:
1. Fetch the full class list from the AQW wiki tag index
2. Visit each class page and extract skill data
3. Detect and merge alias classes (e.g. `BladeMaster/SwordMaster`)
4. Save everything to `data/classes.json`

### Check for new classes (refresh only)

```bash
python scrape_classes.py --refresh
```

This compares the live wiki list to your stored data and only fetches new entries.
Great for a cron job or Discord bot trigger.

### Test a single class

```bash
python scrape_classes.py --class "BladeMaster"
```

---

## Data Structure

Every class in `data/classes.json` follows this shape:

```json
{
  "name": "BladeMaster/SwordMaster",
  "canonical_name": "BladeMaster",
  "all_names": ["BladeMaster", "SwordMaster"],
  "url": "http://aqwwiki.wikidot.com/blademaster-class",
  "aliases": ["SwordMaster"],
  "role": ["DPS"],
  "mana_type": "Mana",
  "skills": [
    {
      "slot": 1,
      "name": "Blade Flurry",
      "type": "Active",
      "mana_cost": "20 Mana",
      "cooldown": "2 seconds",
      "description": "...",
      "max_stack": 5,
      "max_stack_summary": "At 5 stacks: +50% damage",
      "effects": [
        {
          "type": "Buff",
          "stat": "All Damage",
          "value": "+10% per stack",
          "duration": "8s",
          "target": "Self",
          "stacks": true,
          "max_stacks": 5
        }
      ]
    }
  ],
  "party_buffs": [],
  "enemy_debuffs": [],
  "comp_tags": ["damage_amp"],
  "last_fetched": "2024-01-01T00:00:00"
}
```

---

## Comp Builder (Phase 2 Preview)

The comp builder will accept a party of 4, 7, or up to 20 players and:

- Check role coverage (DPS / Tank / Support / Healer)
- Identify stackable buff/debuff synergies
- Highlight missing damage amplifiers or heals
- Score the comp based on guide-derived weights

---

## Discord Features (Phase 3 Preview)

- `/class [name]` — full class card with skill breakdown at max stack
- `/comp [c1] [c2] [c3] [c4]` — analyze a 4-player party
- `/find-support` — suggests support classes that complement your current comp
- `#daily-legend` — posts a random Legend item pre-2016 daily for outfit inspiration

---

## Contributing

Guides used as the authoritative source for mechanic definitions will be
credited here once provided. The goal is to make this **the** reference
for AQW class optimization.
