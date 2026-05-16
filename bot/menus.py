"""Inline keyboard layouts."""
from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def main_menu():
    rows = [
        [
            InlineKeyboardButton(
                "\u26bd Football",
                callback_data="m:sport:football",
            ),
            InlineKeyboardButton(
                "\U0001f3be Tennis",
                callback_data="m:soon:tennis",
            ),
        ],
        [
            InlineKeyboardButton(
                "\U0001f3c0 Basketball",
                callback_data="m:soon:basketball",
            ),
            InlineKeyboardButton(
                "\U0001f3d0 Volleyball",
                callback_data="m:soon:volleyball",
            ),
        ],
        [
            InlineKeyboardButton(
                "\U0001f534 Live now",
                callback_data="m:live",
            ),
            InlineKeyboardButton(
                "\U0001f4dc History",
                callback_data="m:history",
            ),
        ],
        [
            InlineKeyboardButton(
                "\U0001f4ca My stats",
                callback_data="m:stats",
            ),
            InlineKeyboardButton(
                "\u2699\ufe0f Settings",
                callback_data="m:settings",
            ),
        ],
        [
            InlineKeyboardButton(
                "\U0001f9ea Test signal now",
                callback_data="m:test",
            ),
        ],
    ]
    return InlineKeyboardMarkup(rows)


FOOTBALL_MARKETS = [
    ("Goals", "goals"),
    ("Corners", "corners"),
    ("Cards", "cards"),
    ("Shots", "shots"),
    ("BTTS", "btts"),
    ("HT / FT", "htft"),
]


def football_menu(pinned):
    """Use ticks/blanks instead of pins so it reads as a checkbox list."""
    rows = []
    row = []
    for label, key in FOOTBALL_MARKETS:
        is_on = key in pinned
        prefix = "\u2705" if is_on else "\u2b1c"
        text = f"{prefix} {label}"
        row.append(
            InlineKeyboardButton(text, callback_data=f"p:football:{key}")
        )
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append(
        [InlineKeyboardButton("\u25c0\ufe0f Back", callback_data="m:home")]
    )
    return InlineKeyboardMarkup(rows)


def test_market_menu():
    """Pick a market to fire a test signal for."""
    rows = []
    row = []
    for label, key in FOOTBALL_MARKETS:
        row.append(
            InlineKeyboardButton(
                label,
                callback_data=f"m:testmarket:{key}",
            )
        )
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append(
        [InlineKeyboardButton("\u25c0\ufe0f Back", callback_data="m:home")]
    )
    return InlineKeyboardMarkup(rows)


def back_menu():
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("\u25c0\ufe0f Back", callback_data="m:home")]]
    )
