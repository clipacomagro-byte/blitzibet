"""Demo mode — fires synthetic signals on a schedule so the bot can be
demonstrated without a working live-data feed.

Activated when env var DEMO_MODE=true (or 1/yes). Signals look real,
go through Claude enrichment, and land in users' Telegrams.
"""
import logging
import random

from data import models
from engine.rules import Signal
from engine.enrichment import build_narrative
from engine.notifier import dispatch_signal

log = logging.getLogger("blitzibet.demo")


DEMO_MATCHES = [
    {"home_id": 529, "home_name": "Barcelona",
     "away_id": 530, "away_name": "Atlético Madrid", "league": "La Liga"},
    {"home_id": 541, "home_name": "Real Madrid",
     "away_id": 548, "away_name": "Real Sociedad", "league": "La Liga"},
    {"home_id": 33,  "home_name": "Manchester United",
     "away_id": 34,  "away_name": "Newcastle", "league": "Premier League"},
    {"home_id": 40,  "home_name": "Liverpool",
     "away_id": 49,  "away_name": "Chelsea", "league": "Premier League"},
    {"home_id": 489, "home_name": "AC Milan",
     "away_id": 492, "away_name": "Napoli", "league": "Serie A"},
    {"home_id": 165, "home_name": "Borussia Dortmund",
     "away_id": 168, "away_name": "Bayer Leverkusen", "league": "Bundesliga"},
]


DEMO_SCENARIOS = [
    {
        "rule_name": "shots_burst", "market": "goals",
        "minute": 67, "home_goals": 1, "away_goals": 1,
        "suggested_bet": "Next goal within ~10 min · Over current line",
        "confidence": 4, "tier": "signal",
        "criteria": {"shots_delta": 4, "window_min": 10, "minute": 67},
        "home_stats": {"Shots on Goal": 5, "Total Shots": 12, "Corner Kicks": 4,
                       "Dangerous Attacks": 38, "Ball Possession": 64},
        "away_stats": {"Shots on Goal": 2, "Total Shots": 6, "Corner Kicks": 2,
                       "Dangerous Attacks": 18, "Ball Possession": 36},
    },
    {
        "rule_name": "corner_spam_watch", "market": "corners",
        "minute": 54, "home_goals": 0, "away_goals": 1,
        "suggested_bet": "Watch tier · not a bet recommendation",
        "confidence": 2, "tier": "watch",
        "criteria": {"corners_delta": 3, "window_min": 10, "minute": 54},
        "home_stats": {"Shots on Goal": 3, "Total Shots": 9, "Corner Kicks": 6,
                       "Dangerous Attacks": 28, "Ball Possession": 55},
        "away_stats": {"Shots on Goal": 4, "Total Shots": 7, "Corner Kicks": 2,
                       "Dangerous Attacks": 22, "Ball Possession": 45},
    },
    {
        "rule_name": "late_push", "market": "goals",
        "minute": 81, "home_goals": 2, "away_goals": 1,
        "suggested_bet": "Trailing team to score next · BTTS yes",
        "confidence": 3, "tier": "signal",
        "criteria": {"trailing_team": 0, "dangerous_attacks": 42, "possession": 58},
        "home_stats": {"Shots on Goal": 4, "Total Shots": 11, "Corner Kicks": 5,
                       "Dangerous Attacks": 28, "Ball Possession": 42},
        "away_stats": {"Shots on Goal": 5, "Total Shots": 9, "Corner Kicks": 3,
                       "Dangerous Attacks": 42, "Ball Possession": 58},
    },
    {
        "rule_name": "corner_spam", "market": "corners",
        "minute": 72, "home_goals": 1, "away_goals": 0,
        "suggested_bet": "Next corner within ~5 min · Over current line",
        "confidence": 4, "tier": "signal",
        "criteria": {"corners_delta": 5, "window_min": 10, "minute": 72},
        "home_stats": {"Shots on Goal": 4, "Total Shots": 10, "Corner Kicks": 9,
                       "Dangerous Attacks": 34, "Ball Possession": 61},
        "away_stats": {"Shots on Goal": 1, "Total Shots": 4, "Corner Kicks": 2,
                       "Dangerous Attacks": 14, "Ball Possession": 39},
    },
]


async def fire_demo_signal() -> None:
    """Pick a random match + scenario and run it through the full pipeline."""
    match = random.choice(DEMO_MATCHES)
    scenario = random.choice(DEMO_SCENARIOS)
    label = f"{match['home_name']} v {match['away_name']}"

    log.info("[DEMO] firing %s on %s (tier=%s)",
             scenario["rule_name"], label, scenario["tier"])

    fake_fixture = {
        "fixture": {"id": 999000 + random.randint(0, 9999),
                    "status": {"elapsed": scenario["minute"]}},
        "teams": {
            "home": {"id": match["home_id"], "name": match["home_name"]},
            "away": {"id": match["away_id"], "name": match["away_name"]},
        },
        "league": {"name": match["league"]},
        "goals": {"home": scenario["home_goals"], "away": scenario["away_goals"]},
    }
    fake_stats = {
        match["home_id"]: scenario["home_stats"],
        match["away_id"]: scenario["away_stats"],
    }

    signal_id = await models.insert_signal(
        sport="football",
        market=scenario["market"],
        fixture_id=fake_fixture["fixture"]["id"],
        fixture_label=label,
        league=match["league"],
        minute=scenario["minute"],
        rule_name=scenario["rule_name"],
        criteria=scenario["criteria"],
        suggested_bet=scenario["suggested_bet"],
        confidence=scenario["confidence"],
    )

    fake_signal = Signal(
        rule_name=scenario["rule_name"],
        market=scenario["market"],
        suggested_bet=scenario["suggested_bet"],
        confidence=scenario["confidence"],
        criteria=scenario["criteria"],
        tier=scenario["tier"],
    )

    narrative = None
    try:
        narrative = await build_narrative(fake_fixture, fake_stats, [], fake_signal)
    except Exception:
        log.exception("[DEMO] enrichment failed")

    await dispatch_signal(
        signal_id=signal_id,
        sport="football",
        market=scenario["market"],
        fixture_label=label,
        league=match["league"],
        minute=scenario["minute"],
        home_goals=scenario["home_goals"],
        away_goals=scenario["away_goals"],
        suggested_bet=scenario["suggested_bet"],
        confidence=scenario["confidence"],
        rule_name=scenario["rule_name"],
        tier=scenario["tier"],
        narrative=narrative,
    )
