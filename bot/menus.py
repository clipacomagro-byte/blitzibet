"""Keyboard layouts for the bot UI."""
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from data.leagues import LEAGUES


def main_menu():
    rows = [
        [
            InlineKeyboardButton("\u26bd Football", callback_data="football"),
            InlineKeyboardButton("\U0001f3be Tennis", callback_data="tennis"),
        ],
        [
            InlineKeyboardButton("\U0001f3c0 Basketball", callback_data="basketball"),
            InlineKeyboardButton("\U0001f3d0 Volleyball", callback_data="volleyball"),
        ],
        [
            InlineKeyboardButton("\U0001f534 Live now", callback_data="livenow"),
            InlineKeyboardButton("\U0001f4dc History", callback_data="history"),
        ],
        [
            InlineKeyboardButton("\U0001f4ca My stats", callback_data="stats"),
            InlineKeyboardButton("\u2699\ufe0f Settings", callback_data="settings"),
        ],
        [
            InlineKeyboardButton(
                "\U0001f9ea Test signal now", callback_data="test"
            ),
        ],
    ]
    return InlineKeyboardMarkup(rows)


def football_menu(pinned_markets):
    def cb(market):
        return f"toggle:football:{market}"

    def label(market_key, display):
        prefix = "\u2705" if market_key in pinned_markets else "\u2b1c"
        return f"{prefix} {display}"

    rows = [
        [InlineKeyboardButton(label("goals", "Goals"), callback_data=cb("goals")),
         InlineKeyboardButton(label("corners", "Corners"), callback_data=cb("corners"))],
        [InlineKeyboardButton(label("cards", "Cards"), callback_data=cb("cards")),
         InlineKeyboardButton(label("shots", "Shots"), callback_data=cb("shots"))],
        [InlineKeyboardButton(label("btts", "BTTS"), callback_data=cb("btts")),
         InlineKeyboardButton(label("htft", "HT/FT"), callback_data=cb("htft"))],
        [InlineKeyboardButton("\u2b05\ufe0f Back", callback_data="main")],
    ]
    return InlineKeyboardMarkup(rows)


def settings_menu():
    rows = [
        [InlineKeyboardButton("\U0001f30d Leagues", callback_data="leagues")],
        [InlineKeyboardButton("\u2b05\ufe0f Back", callback_data="main")],
    ]
    return InlineKeyboardMarkup(rows)


def leagues_menu(enabled_set):
    """Show each league with a checkmark if enabled."""
    rows = []
    pair = []
    for lg in LEAGUES:
        check = "\u2705" if lg["name"] in enabled_set else "\u2b1c"
        text = f"{check} {lg['flag']} {lg['name']}"
        pair.append(
            InlineKeyboardButton(
                text, callback_data=f"toggleleague:{lg['name']}"
            )
        )
        if len(pair) == 2:
            rows.append(pair)
            pair = []
    if pair:
        rows.append(pair)
    rows.append([
        InlineKeyboardButton("\u2b05\ufe0f Back", callback_data="settings"),
    ])
    return InlineKeyboardMarkup(rows)


def history_menu():
    rows = [[InlineKeyboardButton("\u2b05\ufe0f Back", callback_data="main")]]
    return InlineKeyboardMarkup(rows)


def test_market_menu():
    rows = [
        [InlineKeyboardButton("\u26bd Goals", callback_data="testfire:goals"),
         InlineKeyboardButton("\U0001f6a9 Corners", callback_data="testfire:corners")],
        [InlineKeyboardButton("\U0001f7e8 Cards", callback_data="testfire:cards"),
         InlineKeyboardButton("\U0001f3af Shots", callback_data="testfire:shots")],
        [InlineKeyboardButton("\U0001f91d BTTS", callback_data="testfire:btts"),
         InlineKeyboardButton("\u23f1\ufe0f HT/FT", callback_data="testfire:htft")],
        [InlineKeyboardButton("\u2b05\ufe0f Back", callback_data="main")],
    ]
    return InlineKeyboardMarkup(rows)
