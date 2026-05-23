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


def languages_to_flags(
    language_codes: list[str],
    mappings: list[tuple[str, str]] | None = None,
) -> list[str]:
    """Map a list of ISO 639-2 language codes to deduplicated, ordered flag codes.

    Order and priority are determined by the position in `mappings` (or the
    hardcoded defaults when None).  The first entry has the highest priority.
    """
    if mappings is None:
        mappings = list(LANGUAGE_TO_FLAG.items())
    language_set = set(language_codes)
    seen: set[str] = set()
    result: list[str] = []
    for lang, flag in mappings:
        if lang in language_set and flag not in seen:
            seen.add(flag)
            result.append(flag)
    return result


KNOWN_FLAGS: list[str] = list(
    dict.fromkeys(PRIORITY_FLAGS + list(LANGUAGE_TO_FLAG.values()))
)

ALL_FLAGS: list[str] = sorted(p.stem for p in FLAGS_DIR.glob("*.png"))


def flag_path(flag_code: str) -> Path:
    return FLAGS_DIR / f"{flag_code}.png"
