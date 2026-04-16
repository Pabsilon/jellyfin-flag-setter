from pathlib import Path

# ISO 639-2 language code to ISO 3166-1 alpha-2 flag code
LANGUAGE_TO_FLAG: dict[str, str] = {
    "spa": "es",
    "eng": "gb",
    "fra": "fr",
    "deu": "de",
    "jpn": "jp",
}

# Flags that should always appear first, in this order
PRIORITY_FLAGS = ["es"]

FLAGS_DIR = Path(__file__).parent.parent.parent / "flags"


def languages_to_flags(language_codes: list[str]) -> list[str]:
    """Map a list of ISO 639-2 language codes to deduplicated, ordered flag codes."""
    seen: set[str] = set()
    flags: list[str] = []

    for lang in language_codes:
        flag = LANGUAGE_TO_FLAG.get(lang)
        if flag and flag not in seen:
            seen.add(flag)
            flags.append(flag)

    # Move priority flags to the front, preserving their relative order
    priority = [f for f in PRIORITY_FLAGS if f in seen]
    rest = [f for f in flags if f not in set(PRIORITY_FLAGS)]
    return priority + rest


def flag_path(flag_code: str) -> Path:
    return FLAGS_DIR / f"{flag_code}.png"
