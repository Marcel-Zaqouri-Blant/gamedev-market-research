"""Shared settings: Steam tag IDs, search seeds and element definitions."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
DATA = ROOT / "data"

# Steam tag IDs (from store.steampowered.com/tagdata/populartags/english)
TAG = {
    "Hunting": 9564,
    "Dogs": 1637,
    "Animals": 9626,
    "Extraction Shooter": 1199779,
    "Online Co-Op": 3843,
    "Co-op": 1685,
    "Funny": 4136,
    "Comedy": 1719,
    "Physics": 3968,
    "Party Game": 7178,
    "Memes": 10397,
    "Horror": 1667,
}

# Each seed is one Steam search query; tags inside a seed are AND-ed.
# The union of all seeds is our game universe.
SEEDS = {
    "hunting": ["Hunting"],
    "dogs": ["Dogs"],
    "extraction": ["Extraction Shooter"],
    "coop_funny": ["Online Co-Op", "Funny"],
    "coop_comedy": ["Online Co-Op", "Comedy"],
    "coop_physics": ["Online Co-Op", "Physics"],
    "coop_party": ["Online Co-Op", "Party Game"],
    "coop_memes": ["Online Co-Op", "Memes"],
    "coop_horror": ["Online Co-Op", "Horror"],
    "coop_animals": ["Online Co-Op", "Animals"],
}

# Element = tag-based flag computed from a game's full user-tag list.
ELEMENT_TAGS = {
    "hunting": {"Hunting"},
    "dog": {"Dogs"},
    "horror": {"Horror", "Psychological Horror", "Survival Horror"},
    "roguelite": {"Roguelite", "Roguelike", "Action Roguelike"},
    "extraction": {"Extraction Shooter"},
    "coop_online": {"Online Co-Op"},
    "comedy": {"Funny", "Comedy", "Memes", "Dark Comedy"},
    "physics": {"Physics"},
    "party": {"Party Game", "Party"},
    "animals": {"Animals"},
}
DOG_NAME_WORDS = ("dog", "puppy", "pup ", "hound", "doggo", "corgi", "retriever", "k9", "k-9")

# Publishers/developers matched case-insensitively on word boundaries.
# AAA: excluded from analysis. BIG: large AA publishers, kept but flagged.
AAA_PUBLISHERS = [
    "electronic arts", "ea games", "ea sports", "ubisoft", "activision", "blizzard",
    "bethesda", "microsoft", "xbox game studios", "sony", "playstation", "square enix",
    "capcom", "bandai namco", "sega", "take-two", "2k", "2k games", "rockstar",
    "warner bros", "wb games", "konami", "nintendo", "valve", "cd projekt",
    "koei tecmo", "tencent", "netease", "krafton", "nexon", "ncsoft",
]
BIG_PUBLISHERS = [
    "embracer", "plaion", "deep silver", "thq nordic", "focus entertainment",
    "paradox interactive", "epic games", "devolver digital", "team17", "nacon",
    "bigben", "techland", "505 games", "tinybuild", "curve games", "annapurna",
    "raw fury", "kepler interactive", "hooded horse", "playway", "ultimate games",
    "frontier", "saber interactive", "maximum entertainment", "modus games",
    "humble games", "coffee stain", "landfall", "keywords",
]
