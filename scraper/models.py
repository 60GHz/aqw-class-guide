"""
AQW Class Guide — Data Models
==============================
Pydantic models that define the shape of every class entry.
Used for validation, serialization, and IDE autocomplete.

Install: pip install pydantic
"""

from __future__ import annotations
from typing import Optional
from pydantic import BaseModel, Field
from datetime import datetime


# ─── Skill-level Models ───────────────────────────────────────────────────────

class SkillEffect(BaseModel):
    """
    A single buff, debuff, DoT, HoT, or other effect applied by a skill.
    These are filled in either by the scraper or later by the guide data.
    """
    type: str = ""          # e.g. "DoT", "HoT", "Buff", "Debuff", "Aura"
    stat: str = ""          # e.g. "All Damage", "Haste", "Crit Chance"
    value: str = ""         # e.g. "+50%", "-20%", "1500/s"
    duration: str = ""      # e.g. "8s", "Permanent", "Until target dies"
    target: str = "Enemy"   # "Enemy", "Self", "All Allies", "Party"
    stacks: bool = False    # Does this effect stack?
    max_stacks: Optional[int] = None
    notes: str = ""


class Skill(BaseModel):
    """One class skill (auto attack counts as skill 0)."""
    slot:        int = 0        # 0 = auto, 1–5 = skill slots
    name:        str = ""
    type:        str = ""       # "Auto Attack", "Active", "Passive", "Toggle"
    mana_cost:   str = ""       # Can be "0", "20 Mana", "None"
    cooldown:    str = ""       # e.g. "2 seconds", "0 seconds"
    description: str = ""
    effects:     list[SkillEffect] = Field(default_factory=list)
    max_stack:   Optional[int] = None   # Max stacks for stacking skills
    notes:       str = ""

    # Max-stack summary — the key field for our comp builder
    max_stack_summary: str = ""
    """
    Human-readable summary of what this skill does at max stacks.
    Example: "At 5 stacks: +50% All Damage on target, 1500 DoT/s"
    Filled in after the guides are processed.
    """


# ─── Class-level Model ────────────────────────────────────────────────────────

class AQWClass(BaseModel):
    """
    Canonical entry for one AQW class (or merged class group).
    """
    # Identity
    name:           str             # Merged: "BladeMaster/SwordMaster"
    canonical_name: str = ""        # First/primary name: "BladeMaster"
    all_names:      list[str] = Field(default_factory=list)  # All known names
    url:            str = ""        # Wiki URL for the primary class
    aliases:        list[str] = Field(default_factory=list)  # Other names

    # Classification (filled by guides later)
    role:           list[str] = Field(default_factory=list)
    """e.g. ["DPS", "Support"], ["Tank"], ["Hybrid"]"""

    subtype:        list[str] = Field(default_factory=list)
    """e.g. ["Warrior", "Mage", "Healer", "Rogue"]"""

    mana_type:      str = ""
    """e.g. "Mana", "Energy", "Adrenaline", "Chi", "Anima", "Hate"
    This determines how the class regenerates resources."""

    # Skills
    skills: list[Skill] = Field(default_factory=list)

    # Party value — what does this class bring to a comp?
    party_buffs:  list[SkillEffect] = Field(default_factory=list)
    """Buffs this class provides to allies."""

    enemy_debuffs: list[SkillEffect] = Field(default_factory=list)
    """Debuffs this class applies to enemies."""

    # Comp builder metadata
    comp_tags: list[str] = Field(default_factory=list)
    """
    High-level tags for comp building, e.g.:
    - "damage_amp"   → increases party damage
    - "dot_support"  → provides DoT debuffs
    - "hot_support"  → heals over time
    - "tank"         → can hold aggro / survive
    - "self_sustain" → doesn't need a healer
    - "aura"         → provides persistent aura effects
    - "stunner"      → CC/stuns
    """

    # Raw data
    description:  str = ""
    notes:        str = ""
    raw_text:     str = ""
    page_hash:    str = ""
    last_fetched: Optional[datetime] = None
    error:        Optional[str] = None  # Non-None if page failed to scrape

    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}


# ─── Repository Model ─────────────────────────────────────────────────────────

class ClassRepository(BaseModel):
    """The full data repository."""
    meta: RepositoryMeta
    classes: list[AQWClass]

    def find(self, name: str) -> Optional[AQWClass]:
        """Case-insensitive search across all names and aliases."""
        name_lower = name.lower()
        for cls in self.classes:
            if any(n.lower() == name_lower for n in cls.all_names):
                return cls
        return None

    def by_role(self, role: str) -> list[AQWClass]:
        return [c for c in self.classes if role.lower() in [r.lower() for r in c.role]]

    def by_tag(self, tag: str) -> list[AQWClass]:
        return [c for c in self.classes if tag.lower() in [t.lower() for t in c.comp_tags]]


class RepositoryMeta(BaseModel):
    total_classes:    int = 0
    last_full_scrape: Optional[datetime] = None
    last_refresh:     Optional[datetime] = None
    source:           str = "http://aqwwiki.wikidot.com"
