"""Functions for generating user rank cards."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import Tuple

from PIL import Image, ImageDraw, ImageFont
import discord

FONT_PATH = Path(__file__).parent / "DejaVuSans.ttf"


async def create_rank_card(
    member: discord.Member, xp: int, level: int, next_level_xp: int
) -> BytesIO:
    """Create a simple rank card image and return it as BytesIO."""
    print(f"\U0001F4F7 Generiere Rank-Card für {member.display_name}")
    width, height = 450, 120
    bar_width = int((xp / next_level_xp) * (width - 40)) if next_level_xp else 0

    img = Image.new("RGB", (width, height), color=(54, 57, 63))
    draw = ImageDraw.Draw(img)

    if FONT_PATH.exists():
        font_small = ImageFont.truetype(str(FONT_PATH), 16)
        font_big = ImageFont.truetype(str(FONT_PATH), 24)
    else:
        # Fallback to a basic font if DejaVuSans is not found
        try:
            font_small = ImageFont.truetype("arial.ttf", 16)
            font_big = ImageFont.truetype("arial.ttf", 24)
        except IOError:
            font_small = ImageFont.load_default()
            font_big = ImageFont.load_default()
            print("\u26A0\uFE0F Font 'DejaVuSans.ttf' und 'arial.ttf' nicht gefunden. Benutze Standard-Schriftart.")


    avatar_bytes = await member.display_avatar.read()
    avatar = Image.open(BytesIO(avatar_bytes)).resize((80, 80))

    # Create a circular mask for the avatar
    mask = Image.new('L', (80, 80), 0)
    draw_mask = ImageDraw.Draw(mask)
    draw_mask.ellipse((0, 0, 80, 80), fill=255)

    img.paste(avatar, (20, 20), mask) # Increased left padding for avatar

    draw.text((110, 25), member.display_name, font=font_big, fill="white") # Adjusted y for name
    draw.rectangle([110, 60, 110 + (width - 140), 80], fill=(32, 34, 37))
    draw.rectangle([110, 60, 110 + bar_width, 80], fill=(88, 101, 242))
    draw.text(
        (110, 85),
        f"Level {level} - {xp}/{next_level_xp} XP",
        font=font_small,
        fill="white",
    )

    buffer = BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)
    return buffer
