from wand.color import Color
from wand.image import Image

from jellyfin_flag_setter.flags.mapping import flag_path

# Padding between flags and from the edge of the poster, in pixels
FLAG_PADDING = 8
# Flags are sized relative to poster width (same ratio as the original script)
FLAG_WIDTH_RATIO = 5


def compose_flags(poster_bytes: bytes, flag_codes: list[str]) -> bytes:
    """Overlay flag icons onto a poster image and return the result as JPEG bytes."""
    if not flag_codes:
        return poster_bytes

    with Image(blob=poster_bytes) as poster:
        flag_width = poster.width // FLAG_WIDTH_RATIO

        # Load and resize all flag images
        resized_flags: list[Image] = []
        for code in flag_codes:
            path = flag_path(code)
            if not path.exists():
                continue
            img = Image(filename=str(path))
            # Preserve aspect ratio, scale to flag_width
            ratio = flag_width / img.width
            img.resize(flag_width, round(img.height * ratio))
            resized_flags.append(img)

        if not resized_flags:
            return poster_bytes

        # Build the combined flags strip (transparent background)
        strip_width = flag_width
        strip_height = sum(f.height for f in resized_flags) + FLAG_PADDING * (
            len(resized_flags) - 1
        )

        with Image(
            width=strip_width,
            height=strip_height,
            background=Color("transparent"),
        ) as strip:
            y = 0
            for flag in resized_flags:
                strip.composite(flag, left=0, top=y)
                y += flag.height + FLAG_PADDING

            # Place strip in the top-left corner with padding
            left = FLAG_PADDING
            top = FLAG_PADDING
            poster.composite(strip, left=left, top=top)

        for flag in resized_flags:
            flag.close()

        return poster.make_blob("jpeg")
