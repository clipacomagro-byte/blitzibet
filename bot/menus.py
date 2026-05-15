"""Inline keyboard layouts. Two-column grid matching the mockup."""
from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def main_menu() -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton("⚽ Football", callback_data="m:sport:football"),
            InlineKeyboardButton("🎾 Tennis", callback_data="m:soon:tennis"),
        ],
        [
            InlineKeyboardButton("🏀 Basketball", callback_data="m:soon:basketball"),
            InlineKeyboardButton("🏐 Volleyball", callback_data="m:soon:volleyball"),
        ],
        [
            InlineKeyboardButton("🔴 Live now", callback_data="m:live"),
            InlineKeyboardButton("📅 Upcoming", callback_data="m:upcoming"),
        ],
        [
            InlineKeyboardButton("📊 My stats", callback_data="m:stats"),
            InlineKeyboardButton("⚙️ Settings", callback_data="m:settings"),
        ],
    ]
    return InlineKeyboardMarkup(rows)


FOOTBALL_MARKETS = [
    ("🎯", "Goals", "goals"),
    ("🚩", "Corners", "corners"),
    ("🟨", "Cards", "cards"),
    ("📌", "Shots", "shots"),
    ("🤝", "BTTS", "btts"),
    ("⏱️", "HT / FT", "htft"),
]


def football_menu(pinned: set[str]) -> InlineKeyboardMarkup:
    rows = []
    row: list[InlineKeyboardButton] = []
    for emoji, label, key in FOOTBALL_MARKETS:
        prefix = "📍 " if key in pinned else ""
        text = f"{prefix}{emoji} {label}"
        row.append(InlineKeyboardButton(text, callback_data=f"p:football:{key}"))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([InlineKeyboardButton("◀️ Back", callback_data="m:home")])
    return InlineKeyboardMarkup(rows)


def back_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("◀️ Back", callback_data="m:home")]]
    )


def soon_menu() -> InlineKeyboardMarkup:
    return back_menu()
