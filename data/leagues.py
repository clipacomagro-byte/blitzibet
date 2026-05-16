"""Hardcoded catalog of supported leagues."""

LEAGUES = [
    {"name": "Premier League", "flag": "\U0001f3f4\udb40\udc67\udb40\udc62\udb40\udc65\udb40\udc6e\udb40\udc67\udb40\udc7f", "country": "England"},
    {"name": "La Liga", "flag": "\U0001f1ea\U0001f1f8", "country": "Spain"},
    {"name": "Serie A", "flag": "\U0001f1ee\U0001f1f9", "country": "Italy"},
    {"name": "Bundesliga", "flag": "\U0001f1e9\U0001f1ea", "country": "Germany"},
    {"name": "Ligue 1", "flag": "\U0001f1eb\U0001f1f7", "country": "France"},
    {"name": "UEFA Champions League", "flag": "\U0001f3c6", "country": "Europe"},
    {"name": "UEFA Europa League", "flag": "\U0001f3c6", "country": "Europe"},
    {"name": "Eredivisie", "flag": "\U0001f1f3\U0001f1f1", "country": "Netherlands"},
    {"name": "Primeira Liga", "flag": "\U0001f1f5\U0001f1f9", "country": "Portugal"},
    {"name": "MLS", "flag": "\U0001f1fa\U0001f1f8", "country": "USA"},
    {"name": "Liga MX", "flag": "\U0001f1f2\U0001f1fd", "country": "Mexico"},
    {"name": "Championship", "flag": "\U0001f3f4\udb40\udc67\udb40\udc62\udb40\udc65\udb40\udc6e\udb40\udc67\udb40\udc7f", "country": "England"},
]


def league_display(name):
    """Return 'flag + name' for a known league, or just name if not in catalog."""
    for lg in LEAGUES:
        if lg["name"] == name:
            return f"{lg['flag']} {lg['name']}"
    return name
