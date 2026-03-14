"""Upload BJJ rank images as a Telegram custom emoji sticker set and print the RANK_CUSTOM_EMOJIS mapping."""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import aiohttp

BOT_TOKEN = sys.argv[1] if len(sys.argv) > 1 else None
SET_SUFFIX = sys.argv[2] if len(sys.argv) > 2 else ""

if not BOT_TOKEN:
    print("Usage: python upload_custom_emojis.py <BOT_TOKEN> [suffix]")
    sys.exit(1)

API = f"https://api.telegram.org/bot{BOT_TOKEN}"
OWNER_ID = 250669360

EMOJI_DIR = Path(__file__).resolve().parent.parent / "emojis" / "BJJRanksv3" / "100x100"

# Mapping: (file_index, rank_key, fallback_emoji)
RANK_MAP: list[tuple[int, str, str]] = [
    # White 0-4
    (1, "white:0", "⚪"), (2, "white:1", "⚪"), (3, "white:2", "⚪"),
    (4, "white:3", "⚪"), (5, "white:4", "⚪"),
    # Blue 0-4
    (6, "blue:0", "🔵"), (7, "blue:1", "🔵"), (8, "blue:2", "🔵"),
    (9, "blue:3", "🔵"), (10, "blue:4", "🔵"),
    # Purple 0-4
    (11, "purple:0", "🟣"), (12, "purple:1", "🟣"), (13, "purple:2", "🟣"),
    (14, "purple:3", "🟣"), (15, "purple:4", "🟣"),
    # Brown 0-4
    (16, "brown:0", "🟤"), (17, "brown:1", "🟤"), (18, "brown:2", "🟤"),
    (19, "brown:3", "🟤"), (20, "brown:4", "🟤"),
    # Black 0-6
    (21, "black:0", "⚫"), (22, "black:1", "⚫"), (23, "black:2", "⚫"),
    (24, "black:3", "⚫"), (25, "black:4", "⚫"), (26, "black:5", "⚫"),
    (27, "black:6", "⚫"),
    # Coral, Red & White, Red
    (35, "coral:0", "🪸"),
    (36, "red_white:0", "🏅"),
    (37, "red:0", "🔴"),
]


async def main() -> None:
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{API}/getMe") as resp:
            me = (await resp.json())["result"]
            bot_username = me["username"]

        set_name = f"bjj_ranks{SET_SUFFIX}_by_{bot_username}"
        print(f"Sticker set name: {set_name}")
        print(f"Uploading {len(RANK_MAP)} custom emojis from {EMOJI_DIR}")

        # Check if set already exists
        async with session.get(f"{API}/getStickerSet", params={"name": set_name}) as resp:
            data = await resp.json()
            if data.get("ok"):
                print(f"Set '{set_name}' already exists with {len(data['result']['stickers'])} stickers.")
                print("Delete it first with --delete flag or use a different suffix.")
                stickers = data["result"]["stickers"]
                mapping = {}
                for i, (_, rank_key, _) in enumerate(RANK_MAP):
                    if i < len(stickers):
                        mapping[rank_key] = stickers[i]["custom_emoji_id"]
                print("\nRANK_CUSTOM_EMOJIS:")
                print(json.dumps(mapping))
                return

        # Create set with first sticker
        file_idx, first_key, first_emoji = RANK_MAP[0]
        first_file = EMOJI_DIR / f"{file_idx:02d}.webp"

        form = aiohttp.FormData()
        form.add_field("user_id", str(OWNER_ID))
        form.add_field("name", set_name)
        form.add_field("title", "BJJ Ranks")
        form.add_field("sticker_type", "custom_emoji")
        form.add_field(
            "stickers",
            json.dumps([{
                "sticker": "attach://file0",
                "format": "static",
                "emoji_list": [first_emoji],
            }]),
        )
        form.add_field("file0", open(first_file, "rb"), filename=first_file.name, content_type="image/webp")

        async with session.post(f"{API}/createNewStickerSet", data=form) as resp:
            result = await resp.json()
            if not result.get("ok"):
                print(f"Failed to create set: {result}")
                sys.exit(1)
            print(f"Created set with {first_key}")

        # Add remaining stickers
        for file_idx, rank_key, emoji in RANK_MAP[1:]:
            file_path = EMOJI_DIR / f"{file_idx:02d}.webp"
            if not file_path.exists():
                print(f"Warning: {file_path} not found, skipping {rank_key}")
                continue

            form = aiohttp.FormData()
            form.add_field("user_id", str(OWNER_ID))
            form.add_field("name", set_name)
            form.add_field(
                "sticker",
                json.dumps({
                    "sticker": "attach://file0",
                    "format": "static",
                    "emoji_list": [emoji],
                }),
            )
            form.add_field("file0", open(file_path, "rb"), filename=file_path.name, content_type="image/webp")

            async with session.post(f"{API}/addStickerToSet", data=form) as resp:
                result = await resp.json()
                if not result.get("ok"):
                    print(f"Failed to add {rank_key}: {result}")
                else:
                    print(f"Added {rank_key}")

        # Fetch custom_emoji_ids
        async with session.get(f"{API}/getStickerSet", params={"name": set_name}) as resp:
            data = await resp.json()
            if not data.get("ok"):
                print(f"Failed to fetch set: {data}")
                sys.exit(1)

        stickers = data["result"]["stickers"]
        mapping = {}
        for i, (_, rank_key, _) in enumerate(RANK_MAP):
            if i < len(stickers):
                mapping[rank_key] = stickers[i]["custom_emoji_id"]

        print(f"\nUploaded {len(stickers)} emojis")
        print("\nRANK_CUSTOM_EMOJIS:")
        print(json.dumps(mapping))


asyncio.run(main())
