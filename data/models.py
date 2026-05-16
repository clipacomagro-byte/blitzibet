"""All database queries."""
import json
from data.db import get_pool


def _parse_jsonb(value):
    """Postgres jsonb sometimes comes back as a string. Parse defensively."""
    if value is None:
        return {}
    if isinstance(value, str):
        try:
            return json.loads(value)
        except Exception:
            return {}
    return value


async def upsert_user(telegram_id, username):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            insert into users (telegram_id, username)
            values ($1, $2)
            on conflict (telegram_id) do update
              set username = excluded.username, is_active = true
            """,
            telegram_id, username,
        )


async def toggle_pin(user_id, sport, market):
    pool = await get_pool()
    async with pool.acquire() as conn:
        existing = await conn.fetchval(
            "select id from pins where user_id=$1 and sport=$2 and market=$3",
            user_id, sport, market,
        )
        if existing:
            await conn.execute("delete from pins where id=$1", existing)
            return False
        await conn.execute(
            "insert into pins (user_id, sport, market) values ($1, $2, $3)",
            user_id, sport, market,
        )
        return True


async def get_user_pins(user_id):
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "select sport, market from pins where user_id=$1 order by sport, market",
            user_id,
        )
    return [dict(r) for r in rows]


async def get_users_for_market(sport, market):
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            select u.telegram_id from users u
            join pins p on p.user_id = u.telegram_id
            where p.sport = $1 and p.market = $2 and u.is_active = true
            """,
            sport, market,
        )
    return [r["telegram_id"] for r in rows]


async def save_snapshot(fixture_id, minute, home_score, away_score, stats,
                        fixture_label="", league=""):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            insert into fixture_snapshots
                (fixture_id, minute, home_score, away_score, stats,
                 fixture_label, league)
            values ($1, $2, $3, $4, $5, $6, $7)
            """,
            fixture_id, minute, home_score, away_score, json.dumps(stats),
            fixture_label, league,
        )


async def recent_snapshots(fixture_id, limit=20):
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            select minute, home_score, away_score, stats, taken_at
            from fixture_snapshots where fixture_id = $1
            order by taken_at desc limit $2
            """,
            fixture_id, limit,
        )
    out = []
    for r in rows:
        d = dict(r)
        d["stats"] = _parse_jsonb(d.get("stats"))
        out.append(d)
    return out


async def is_on_cooldown(fixture_id, rule_name, minutes):
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchval(
            """
            select 1 from rule_cooldowns
            where fixture_id = $1 and rule_name = $2
              and fired_at > now() - ($3 || ' minutes')::interval
            """,
            fixture_id, rule_name, str(minutes),
        )
    return row is not None


async def record_cooldown(fixture_id, rule_name):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            insert into rule_cooldowns (fixture_id, rule_name, fired_at)
            values ($1, $2, now())
            on conflict (fixture_id, rule_name)
            do update set fired_at = excluded.fired_at
            """,
            fixture_id, rule_name,
        )


async def insert_signal(sport, market, fixture_id, fixture_label, league,
                        minute, rule_name, criteria, suggested_bet, confidence):
    pool = await get_pool()
    async with pool.acquire() as conn:
        sig_id = await conn.fetchval(
            """
            insert into signals
              (sport, market, fixture_id, fixture_label, league, minute,
               rule_name, criteria, suggested_bet, confidence)
            values ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)
