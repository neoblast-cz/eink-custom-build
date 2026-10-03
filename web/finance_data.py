"""Local-only financial dashboard data: fetches the user's portfolio Google
Sheet live via OAuth. Not part of the e-ink rendering pipeline or the Pi
deploy — this module is only ever used by the /finance web route.
"""

import json
import logging
import math
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)


def _xirr(cash_flows: list) -> float | None:
    """Annualized money-weighted return (like Excel's XIRR) for a series of
    (datetime, amount) cash flows — negative for money paid in, positive for
    money received/held now. Unlike a simple total-return %, this accounts
    for *when* each purchase happened, so a position built up over years
    doesn't get compared 1:1 against one bought all at once last month.

    Solved via Newton-Raphson (no closed form exists for irregular cash
    flow dates) with a bisection fallback if Newton fails to converge —
    good enough for a dashboard estimate, not audited financial software.
    """
    if len(cash_flows) < 2:
        return None
    amounts = [amt for _, amt in cash_flows]
    if not (min(amounts) < 0 < max(amounts)):
        return None  # no sign change => no real rate solves this

    d0 = min(d for d, _ in cash_flows)
    years = [(d - d0).days / 365.0 for d, _ in cash_flows]

    def npv(rate):
        try:
            return sum(amt / (1.0 + rate) ** yr for yr, (_, amt) in zip(years, cash_flows))
        except (OverflowError, ZeroDivisionError):
            return float("nan")

    def npv_prime(rate):
        try:
            return sum(-yr * amt / (1.0 + rate) ** (yr + 1) for yr, (_, amt) in zip(years, cash_flows))
        except (OverflowError, ZeroDivisionError):
            return float("nan")

    rate = 0.1
    for _ in range(60):
        f, fp = npv(rate), npv_prime(rate)
        if not math.isfinite(f) or not math.isfinite(fp) or fp == 0:
            break
        new_rate = max(rate - f / fp, -0.9999)
        if abs(new_rate - rate) < 1e-7:
            return new_rate
        rate = new_rate

    # Newton didn't settle — bisect over a wide, sane range instead.
    lo, hi = -0.9999, 10.0
    f_lo, f_hi = npv(lo), npv(hi)
    if not (math.isfinite(f_lo) and math.isfinite(f_hi) and f_lo * f_hi < 0):
        return None
    for _ in range(200):
        mid = (lo + hi) / 2
        f_mid = npv(mid)
        if not math.isfinite(f_mid):
            return None
        if abs(f_mid) < 1e-6:
            return mid
        if f_lo * f_mid < 0:
            hi = mid
        else:
            lo, f_lo = mid, f_mid
    return (lo + hi) / 2

# Best-effort fund-manager detection from the free-text "Name" column — the
# sheet has no dedicated manager field, so this is a heuristic over known
# brand names, not a verified data source. Order matters: more specific
# patterns (e.g. "ishares core") aren't needed since these are all distinct
# brand names, but keep this list in a fixed order for stable output.
_MANAGER_PATTERNS = [
    (re.compile(r"ishares", re.IGNORECASE), "iShares (BlackRock)"),
    (re.compile(r"vanguard", re.IGNORECASE), "Vanguard"),
    (re.compile(r"spdr|state street", re.IGNORECASE), "SPDR (State Street)"),
    (re.compile(r"xtrackers|\bdws\b", re.IGNORECASE), "Xtrackers (DWS)"),
    (re.compile(r"amundi", re.IGNORECASE), "Amundi"),
    (re.compile(r"invesco", re.IGNORECASE), "Invesco"),
    (re.compile(r"hsbc", re.IGNORECASE), "HSBC"),
    (re.compile(r"wisdomtree", re.IGNORECASE), "WisdomTree"),
    (re.compile(r"\bubs\b", re.IGNORECASE), "UBS"),
    (re.compile(r"lyxor", re.IGNORECASE), "Lyxor"),
    (re.compile(r"first trust", re.IGNORECASE), "First Trust"),
    (re.compile(r"vaneck", re.IGNORECASE), "VanEck"),
]


def _detect_manager(name: str) -> str:
    if not name:
        return "Other"
    for pattern, label in _MANAGER_PATTERNS:
        if pattern.search(name):
            return label
    return "Other"


def _detect_distribution(name: str) -> str | None:
    if not name:
        return None
    if re.search(r"\(acc\)|\bacc\b", name, re.IGNORECASE):
        return "Accumulating"
    if re.search(r"\(dist\)|\bdist\b", name, re.IGNORECASE):
        return "Distributing"
    return None


def _detect_hedge(name: str) -> str | None:
    if not name:
        return None
    m = re.search(r"(\w{3})\s+hedged", name, re.IGNORECASE)
    if m:
        return f"{m.group(1).upper()} hedged"
    if re.search(r"hedged", name, re.IGNORECASE):
        return "Hedged"
    return None


# Plain-language decoder for the index/benchmark an ETF tracks — the sheet
# has no dedicated field for this, so it's parsed from the free-text fund
# name, same as manager/distribution/hedge above. Ordered most-specific
# first (e.g. the ACWI IMI pattern before the plainer "World" one) so a
# broader pattern doesn't shadow a more precise match.
_INDEX_PATTERNS = [
    (
        re.compile(r"all[\s-]?country world investable market|\bacwi imi\b", re.IGNORECASE),
        "MSCI ACWI IMI",
        "~9,000 large, mid, and small companies across developed and emerging markets — the broadest global stock index in common use.",
    ),
    (
        re.compile(r"ftse all-world", re.IGNORECASE),
        "FTSE All-World",
        "~4,000 large and mid-sized companies across developed and emerging markets.",
    ),
    (
        re.compile(r"msci world", re.IGNORECASE),
        "MSCI World",
        "~1,500 large and mid-sized companies across 23 developed markets only — no emerging markets.",
    ),
    (
        re.compile(r"core s&p 500|\bs&p 500\b|\bs&p500\b", re.IGNORECASE),
        "S&P 500",
        "The 500 largest companies listed in the US.",
    ),
    (
        re.compile(r"nasdaq[\s-]?100", re.IGNORECASE),
        "Nasdaq 100",
        "The 100 largest non-financial companies listed on the Nasdaq exchange — heavily weighted toward tech.",
    ),
]


def _detect_index(name: str) -> tuple[str, str | None]:
    if not name:
        return "Other", None
    for pattern, label, description in _INDEX_PATTERNS:
        if pattern.search(name):
            return label, description
    return "Other", None


# Approximate composition of each index a held ETF tracks — there's no
# per-company or per-region field anywhere in the sheet (and no live
# look-through data source wired up), so this is reference data: rough,
# recent-vintage published weights for the indices _detect_index recognizes,
# not a live feed. Company-level breakdown isn't attempted at all for the
# same reason — a fund's actual top-10 holdings would need to come from the
# fund provider's own fact sheet, updated regularly, which is out of scope
# here. Weights are approximate and will drift from reality over time.
_INDEX_REGION_WEIGHTS = {
    "MSCI World": {
        "United States": 70, "Japan": 6, "United Kingdom": 4, "France": 3,
        "Canada": 3, "Switzerland": 3, "Germany": 3, "Australia": 2,
        "Netherlands": 1, "Other developed": 5,
    },
    "MSCI ACWI IMI": {
        "United States": 62, "Japan": 5, "China": 3, "United Kingdom": 3,
        "France": 2.5, "Canada": 2.5, "India": 2, "Switzerland": 2,
        "Germany": 2, "Other": 16,
    },
    "FTSE All-World": {
        "United States": 63, "Japan": 5.5, "China": 3, "United Kingdom": 3.5,
        "Canada": 3, "France": 2.5, "Switzerland": 2, "India": 2,
        "Germany": 2, "Other": 13.5,
    },
    "S&P 500": {"United States": 100},
    "Nasdaq 100": {"United States": 100},
}

_INDEX_SECTOR_WEIGHTS = {
    "MSCI World": {
        "Information Technology": 24, "Financials": 16, "Industrials": 11,
        "Healthcare": 11, "Consumer Discretionary": 10, "Communication Services": 7,
        "Consumer Staples": 6, "Energy": 4, "Materials": 4, "Utilities": 3, "Real Estate": 4,
    },
    "MSCI ACWI IMI": {
        "Information Technology": 22, "Financials": 17, "Industrials": 11,
        "Consumer Discretionary": 11, "Healthcare": 10, "Communication Services": 7,
        "Consumer Staples": 6, "Energy": 5, "Materials": 4, "Real Estate": 4, "Utilities": 3,
    },
    "FTSE All-World": {
        "Information Technology": 23, "Financials": 17, "Industrials": 11,
        "Consumer Discretionary": 11, "Healthcare": 10, "Communication Services": 7,
        "Consumer Staples": 6, "Energy": 4, "Materials": 4, "Utilities": 2, "Real Estate": 5,
    },
    "S&P 500": {
        "Information Technology": 32, "Financials": 14.5, "Consumer Discretionary": 11,
        "Healthcare": 10, "Communication Services": 9, "Industrials": 8,
        "Consumer Staples": 6, "Energy": 3, "Real Estate": 2, "Utilities": 2.5, "Materials": 2,
    },
    "Nasdaq 100": {
        "Information Technology": 50, "Communication Services": 16, "Consumer Discretionary": 13,
        "Healthcare": 7, "Consumer Staples": 5, "Industrials": 5, "Utilities": 1,
        "Financials": 1, "Other": 2,
    },
}


def _etf_composition(etf_holdings: list) -> dict:
    """Blends each held ETF's *index-level* reference weights (above),
    scaled by that holding's current value, into one portfolio-wide
    breakdown — by region and by sector. Approximate by construction (see
    the weights tables' own caveat); ETFs with an unrecognized index are
    excluded rather than guessed at."""

    def _blend(weights_table: dict) -> list:
        totals = defaultdict(float)
        classified_value = 0.0
        for h in etf_holdings:
            weights = weights_table.get(h["index"])
            if not weights or h["current_value"] <= 0:
                continue
            classified_value += h["current_value"]
            for key, pct in weights.items():
                totals[key] += h["current_value"] * (pct / 100)
        if classified_value <= 0:
            return []
        return sorted(
            [{"label": k, "value": round(v, 2)} for k, v in totals.items() if v > 0],
            key=lambda e: -e["value"],
        )

    return {
        "by_region": _blend(_INDEX_REGION_WEIGHTS),
        "by_sector": _blend(_INDEX_SECTOR_WEIGHTS),
    }


# Individual stock purchases (bought via eToro) carry no ISIN/Ticker/Name —
# the only identifying data is a free-text "EXCHANGE:TICKER" note, e.g.
# "NASDAQ:META". Used as a fallback holding key when ISIN is missing.
_NOTE_TICKER = re.compile(r"^[A-Z]+:([A-Z.]+)$")


def _extract_ticker_from_note(note: str) -> str | None:
    if not note:
        return None
    m = _NOTE_TICKER.match(note.strip())
    return m.group(1) if m else None


TOKEN_PATH = Path(__file__).parent.parent / "google_sheets_token.json"
SHEETS_API = "https://sheets.googleapis.com/v4/spreadsheets"
TOKEN_URL = "https://oauth2.googleapis.com/token"

# Sheet is fetched live over the network — cache briefly so repeated page
# loads/refreshes don't hammer the Sheets API.
_CACHE_TTL = 600  # seconds
_cache = {"data": None, "fetched_at": 0}


class NotAuthorized(Exception):
    pass


def is_authorized() -> bool:
    """True only if a token in this module's own schema exists — guards
    against a stale/incompatible token.json left over from some other tool
    or a prior attempt (e.g. the raw google-auth Credentials.to_json()
    schema uses 'token'/'expiry', not our 'access_token'/'expires_at')."""
    token = _load_token()
    return bool(token and token.get("access_token"))


def available(config) -> bool:
    return is_authorized() and bool(config.get("finance", "spreadsheet_id", default=""))


# ── Token management (mirrors modules/fitness/fitness.py's pattern) ────

def _load_token() -> dict | None:
    if not TOKEN_PATH.exists():
        return None
    try:
        return json.loads(TOKEN_PATH.read_text())
    except Exception:
        return None


def save_token(token_data: dict):
    TOKEN_PATH.write_text(json.dumps(token_data, indent=2))


def _refresh_if_needed(config) -> str:
    token_data = _load_token()
    if not token_data:
        raise NotAuthorized("Google Sheets not authorized")

    access_token = token_data.get("access_token", "")
    expires_at = token_data.get("expires_at", 0)
    if time.time() < expires_at - 300:
        return access_token

    refresh_token = token_data.get("refresh_token", "")
    if not refresh_token:
        if time.time() < expires_at:
            return access_token
        raise NotAuthorized("Google Sheets token expired, no refresh token")

    client_id = config.get("google", "client_id", default="")
    client_secret = config.get("google", "client_secret", default="")
    if not client_id or not client_secret:
        logger.warning("Google credentials not configured, cannot refresh token")
        if time.time() < expires_at:
            return access_token
        raise NotAuthorized("Google credentials not configured")

    try:
        data = urllib.parse.urlencode({
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": client_id,
            "client_secret": client_secret,
        }).encode()
        req = urllib.request.Request(
            TOKEN_URL, data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            new_token = json.loads(resp.read())

        # Google's refresh response omits refresh_token — keep the existing one.
        new_token.setdefault("refresh_token", refresh_token)
        new_token["expires_at"] = time.time() + new_token.get("expires_in", 3600)
        save_token(new_token)
        logger.info("Google Sheets token refreshed successfully")
        return new_token["access_token"]
    except Exception as e:
        logger.error(f"Google Sheets token refresh failed: {e}")
        if time.time() < expires_at:
            return access_token
        raise NotAuthorized("Google Sheets token refresh failed")


# ── Sheets API ───────────────────────────────────────────────────────

def _batch_get(access_token: str, spreadsheet_id: str, ranges: list) -> dict:
    params = urllib.parse.urlencode(
        [("ranges", r) for r in ranges] + [
            ("valueRenderOption", "UNFORMATTED_VALUE"),
            ("dateTimeRenderOption", "SERIAL_NUMBER"),
        ]
    )
    url = f"{SHEETS_API}/{spreadsheet_id}/values:batchGet?{params}"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {access_token}"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read())


def _sheet_titles(access_token: str, spreadsheet_id: str) -> list:
    url = f"{SHEETS_API}/{spreadsheet_id}?fields=sheets.properties.title"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {access_token}"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        meta = json.loads(resp.read())
    return [s["properties"]["title"] for s in meta.get("sheets", [])]


def _add_sheet(access_token: str, spreadsheet_id: str, title: str):
    url = f"{SHEETS_API}/{spreadsheet_id}:batchUpdate"
    body = json.dumps({"requests": [{"addSheet": {"properties": {"title": title}}}]}).encode()
    req = urllib.request.Request(
        url, data=body, method="POST",
        headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        resp.read()


def _append_row(access_token: str, spreadsheet_id: str, sheet_range: str, row: list):
    params = urllib.parse.urlencode({
        "valueInputOption": "RAW",
        "insertDataOption": "INSERT_ROWS",
    })
    url = f"{SHEETS_API}/{spreadsheet_id}/values/{urllib.parse.quote(sheet_range)}:append?{params}"
    body = json.dumps({"values": [row]}).encode()
    req = urllib.request.Request(
        url, data=body, method="POST",
        headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        resp.read()


DRIVE_UPLOAD_API = "https://www.googleapis.com/upload/drive/v3/files"


def _upload_png_to_drive(access_token: str, filename: str, png_bytes: bytes) -> dict:
    """Multipart upload: JSON metadata + raw PNG bytes in one request. No
    sharing permissions are set — drive.file already makes the file
    private to this app/the user who owns it, which is exactly right for
    a portfolio screenshot; the owner can always open their own file."""
    boundary = "einkpi-finance-snapshot"
    metadata = json.dumps({"name": filename, "mimeType": "image/png"})
    body = (
        f"--{boundary}\r\n"
        f"Content-Type: application/json; charset=UTF-8\r\n\r\n"
        f"{metadata}\r\n"
        f"--{boundary}\r\n"
        f"Content-Type: image/png\r\n\r\n"
    ).encode() + png_bytes + f"\r\n--{boundary}--".encode()

    req = urllib.request.Request(
        f"{DRIVE_UPLOAD_API}?uploadType=multipart&fields=id,webViewLink",
        data=body, method="POST",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": f"multipart/related; boundary={boundary}",
        },
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read())


def _update_row(access_token: str, spreadsheet_id: str, sheet_range: str, row: list):
    """Overwrites (not appends) — used to keep the header row in sync even
    if the Snapshot tab already existed under an older column layout."""
    params = urllib.parse.urlencode({"valueInputOption": "RAW"})
    url = f"{SHEETS_API}/{spreadsheet_id}/values/{urllib.parse.quote(sheet_range)}?{params}"
    body = json.dumps({"values": [row]}).encode()
    req = urllib.request.Request(
        url, data=body, method="PUT",
        headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        resp.read()


def _serial_to_date(serial) -> str | None:
    """Sheets/Excel date serial (days since 1899-12-30) -> ISO date string."""
    if not isinstance(serial, (int, float)):
        return None
    try:
        return (datetime(1899, 12, 30) + timedelta(days=serial)).date().isoformat()
    except (OverflowError, ValueError):
        return None


# ── Parsing ──────────────────────────────────────────────────────────

VALUE_CATEGORIES = ["Cash", "Crowdlending", "Crypto", "ETF", "Gold", "Savings", "Stocks"]


def _parse_historic(rows: list) -> dict:
    """Historic tab: A=Date, B=Net value, C-G=NetProfit(P2P/HYSA/ETF/Crypto/Stocks),
    H-N=Value(Cash/Crowdlending/Crypto/ETF/Gold/Savings/Stocks)."""
    net_worth = []
    allocation_over_time = []
    current_allocation = {}

    for row in rows[2:]:  # skip the two header rows
        if not row or not isinstance(row[0], (int, float)):
            continue
        date = _serial_to_date(row[0])
        if not date:
            continue

        def cell(i):
            return row[i] if i < len(row) and isinstance(row[i], (int, float)) else 0.0

        net_worth.append({"date": date, "value": cell(1)})

        allocation = {cat: cell(7 + i) for i, cat in enumerate(VALUE_CATEGORIES)}
        allocation_over_time.append({"date": date, **allocation})
        current_allocation = allocation  # last populated row wins

    return {
        "net_worth": net_worth,
        "allocation_over_time": allocation_over_time,
        "current_allocation": current_allocation,
    }


def _accumulate_chronological(events: list) -> list:
    """events: list of (date_str, key, amount) in any order. Returns a time
    series of running-total snapshots, one per distinct date, with every
    previously-seen key's latest total forward-filled onto later dates.

    Sorting here (rather than trusting caller order) matters: this sheet's
    rows are grouped by institution/holding, not by date, so accumulating
    a running total while scanning rows in sheet order — then only later
    presenting it sorted by date — produces a total that visibly goes up
    and down instead of monotonically growing.
    """
    if not events:
        return []
    events = sorted(events, key=lambda e: e[0])
    running: dict = defaultdict(float)
    result = []
    prev_date = events[0][0]
    for date, key, amount in events:
        if date != prev_date:
            result.append({"date": prev_date, **running})
            prev_date = date
        running[key] += amount
    result.append({"date": prev_date, **running})
    return result


def _compute_net_worth_stats(net_worth: list) -> dict:
    """Latest value plus signed change vs ~30 days ago, ~365 days ago, and the
    first data point on record — the closest available date to each target,
    since snapshots aren't taken on a fixed schedule."""
    if not net_worth:
        return {}

    latest = net_worth[-1]
    latest_date = datetime.fromisoformat(latest["date"])

    def closest_to(target_date):
        return min(net_worth, key=lambda e: abs(datetime.fromisoformat(e["date"]) - target_date))

    def delta(baseline):
        change = latest["value"] - baseline["value"]
        pct = (change / baseline["value"] * 100) if baseline["value"] else 0.0
        return {"date": baseline["date"], "change": round(change, 2), "pct": round(pct, 2)}

    return {
        "latest": {"date": latest["date"], "value": round(latest["value"], 2)},
        "vs_30d": delta(closest_to(latest_date - timedelta(days=30))),
        "vs_1y": delta(closest_to(latest_date - timedelta(days=365))),
        "vs_all_time": delta(net_worth[0]),
    }


def _parse_portfolio(rows: list, current_allocation: dict) -> dict:
    """Portfolio tab: A=Date, E=Place, F=Type, G=Category, H=Amount, I=Price,
    K=Money Spent EUR, L=Total Net, N=ISIN, O=Ticker, Q=Name.

    Money Spent EUR is only populated on acquisition-type transactions
    (Deposit/Purchase/Initial/Bonus), not on Withdrawal/Interest, so summing
    it directly gives capital contributed.

    Total Net on ETF/Stock rows is NOT a historical value — verified against
    the actual sheet that every row for a given holding divides out to the
    exact same per-unit value regardless of transaction date (today's price
    applied retroactively). So per-holding current value = sum(Total Net);
    cost basis = sum(Money Spent EUR); the gap between them is real gain/loss,
    but there's no historical value-over-time series to chart honestly —
    only cost-basis-over-time (position size growing), which we do chart.

    Grouped by ISIN, not ticker: the same fund can trade under different
    ticker symbols on different exchanges/brokers, but ISIN is the one
    identifier that's actually unique per security.
    """
    by_category = defaultdict(float)

    # Collected raw, sorted and accumulated chronologically *after* the row
    # scan — the sheet's rows are grouped by institution, not by date, so
    # accumulating a running total in row order and only later presenting it
    # sorted by date produced a running total that visibly went up and down.
    # Category tags along for the ride so interest can be split by
    # Crowdlending vs Savings — "Savings Long"/"Savings Term" (the sheet's
    # raw Portfolio-tab categories) are folded into the single "Savings"
    # bucket the Historic tab already uses everywhere else.
    interest_events = []  # (date, place, value_category, amount)
    interest_by_place = defaultdict(lambda: defaultdict(float))  # value_category -> place -> total

    holdings = {}  # isin -> {name, ticker, units, cost_basis, current_value}
    holdings_cost_basis_events = []  # (date, isin, spent) — same chronological-accumulation fix as interest
    holdings_transactions = defaultdict(list)  # isin -> [{date, type, units, price, spent, value}, ...]

    # Crowdlending/Savings have no re-priced "current value" column like ETFs
    # do — Total Net on these rows is just that transaction's own cash-flow
    # amount (deposit/withdrawal/interest), not a live snapshot. So instead
    # of the ETF-style "gain = current − contributed" (which double-counts:
    # money withdrawn and never redeposited still inflated "contributed"),
    # these categories get a proper XIRR using only Deposit/Withdrawal as
    # cash flows (sign-flipped: the sheet records a Withdrawal as a negative
    # platform-balance change, but it's a positive cash flow back to me) and
    # the Historic tab's real current-value snapshot as the terminal flow.
    # Interest/Bonus are deliberately excluded from the XIRR flows — they're
    # value that either stayed in the platform (already inside the terminal
    # current_value) or was already paid out via a Withdrawal row.
    category_deposited = defaultdict(float)
    category_withdrawn = defaultdict(float)
    category_flow_events = defaultdict(list)  # value_category -> [(date, signed_amount)]

    # "Cumulative portfolio per platform" reconstruction: running balance =
    # deposits + bonus + interest − withdrawals, per Crowdlending platform.
    # Approximate (doesn't capture principal losses from a defaulted loan),
    # but every one of these transaction types already carries the right
    # sign in the sheet, so it's a straight running sum.
    crowdlending_position_events = []  # (date, place, signed_amount)
    crowdlending_exited_platforms = set()  # platforms with an ACCOUNT DELETE row

    cash_by_place = defaultdict(float)

    stock_purchase_events = []  # (date, spent)
    crypto_purchase_events = []  # (date, spent)
    etf_purchase_events = []  # (date, spent)

    # "Peerberry" vs "PeerBerry" — same platform, inconsistent capitalization
    # in the sheet. Canonicalize case-insensitively so it doesn't fork into
    # two separate series; first-seen casing wins for the display label.
    _place_canonical = {}

    def canon_place(p):
        if not p:
            return p
        key = p.strip().lower()
        return _place_canonical.setdefault(key, p.strip())

    for row in rows[1:]:  # skip header row
        if not row or not isinstance(row[0], (int, float)):
            continue
        date = _serial_to_date(row[0])
        if not date:
            continue

        place = canon_place(row[4] if len(row) > 4 else None)
        txn_type = row[5] if len(row) > 5 else None
        category = row[6] if len(row) > 6 else None
        amount = row[7] if len(row) > 7 and isinstance(row[7], (int, float)) else None
        price = row[8] if len(row) > 8 and isinstance(row[8], (int, float)) else None
        spent = row[10] if len(row) > 10 and isinstance(row[10], (int, float)) else None
        total_net_raw = row[11] if len(row) > 11 else None
        total_net = total_net_raw if isinstance(total_net_raw, (int, float)) else None
        # Total Net is a live price-lookup formula in the sheet — it can
        # come back as an error string (e.g. "#N/A (Resource at url not
        # found.)") for a ticker the price source doesn't recognize, rather
        # than genuinely empty. Tracked per-holding below so a broken
        # formula flags the position as "price unavailable" instead of
        # silently reading as a fully-sold, zero-value holding.
        total_net_broken = total_net_raw not in (None, "") and total_net is None
        note = row[12] if len(row) > 12 else None
        isin = row[13] if len(row) > 13 else None
        ticker = row[14] if len(row) > 14 else None
        name = row[16] if len(row) > 16 else None

        # "Savings Long"/"Savings Term" (raw Portfolio-tab categories) fold
        # into the single "Savings" bucket the Historic tab already uses.
        value_category = "Savings" if category in ("Savings Long", "Savings Term") else category

        if spent and category:
            by_category[category] += spent

        if txn_type == "Interest" and total_net:
            interest_events.append((date, place or "Other", value_category, total_net))
            if place:
                interest_by_place[value_category][place] += total_net

        if value_category in ("Crowdlending", "Savings") and total_net:
            if txn_type == "Deposit":
                category_deposited[value_category] += total_net
                category_flow_events[value_category].append((date, -total_net))
            elif txn_type == "Withdrawal":
                category_withdrawn[value_category] += abs(total_net)
                category_flow_events[value_category].append((date, -total_net))

        if value_category == "Crowdlending" and total_net and place:
            crowdlending_position_events.append((date, place, total_net))
        if value_category == "Crowdlending" and txn_type == "ACCOUNT DELETE" and place:
            crowdlending_exited_platforms.add(place)

        if value_category == "Cash" and place and total_net:
            cash_by_place[place] += total_net

        if value_category == "Stocks" and txn_type == "Purchase" and spent:
            stock_purchase_events.append((date, spent))
        if value_category == "Crypto" and txn_type == "Purchase" and spent:
            crypto_purchase_events.append((date, spent))
        if value_category == "ETF" and txn_type == "Purchase" and spent:
            etf_purchase_events.append((date, spent))

        # ETF rows are always ISIN-tagged. Individual stock rows (eToro) never
        # are — fall back to the ticker parsed out of the Note column so
        # these still group into per-position holdings instead of being
        # dropped entirely. holding_key is namespaced ("TICKER:META") so it
        # can never collide with a real ISIN.
        #
        # Broker is folded into the key too — the same ETF can be (and is:
        # VWCE, IE00BK5BQT80) held at more than one broker, and merging
        # those into a single holding silently attributed the whole
        # position to whichever broker's row happened to be scanned first,
        # which then fed a wrong number into the "ETF value/performance by
        # broker" charts. Keying per (isin-or-ticker, broker) makes each
        # broker's position its own holding/card instead.
        place_key = place or "Unknown"
        holding_key = f"{isin}@{place_key}" if isin else None
        note_ticker = None
        if not holding_key and category == "Stocks":
            note_ticker = _extract_ticker_from_note(note)
            if note_ticker:
                holding_key = f"TICKER:{note_ticker}@{place_key}"

        if category in ("ETF", "Stocks") and holding_key:
            h = holdings.setdefault(holding_key, {"isin": isin or None, "name": None, "ticker": None, "broker": place_key, "category": category, "units": 0.0, "cost_basis": 0.0, "current_value": 0.0, "price_unavailable": False})
            # A holding's name/ticker can vary by row (e.g. a data-entry slip
            # spotted on a later Sell row) — keep the first non-empty value
            # seen, from whichever Purchase established the position.
            if name and not h["name"]:
                h["name"] = name
            if (ticker or note_ticker) and not h["ticker"]:
                h["ticker"] = ticker or note_ticker
            if amount:
                h["units"] += amount
            if spent:
                h["cost_basis"] += spent
                holdings_cost_basis_events.append((date, holding_key, spent))
            if total_net:
                h["current_value"] += total_net
            if total_net_broken:
                h["price_unavailable"] = True

            holdings_transactions[holding_key].append({
                "date": date,
                "type": txn_type,
                "units": round(amount, 4) if amount else None,
                "price": round(price, 4) if price else None,
                "spent": round(spent, 2) if spent else None,
                "value": round(total_net, 2) if total_net else None,
            })

    contributions_by_category = {k: round(v, 2) for k, v in sorted(by_category.items(), key=lambda kv: -kv[1])}

    def _place_breakdown(value_category: str) -> dict:
        totals = interest_by_place.get(value_category, {})
        return {k: round(v, 2) for k, v in sorted(totals.items(), key=lambda kv: -kv[1])}

    def _cumulative_by_place(value_category: str, by_place_sorted: dict) -> list:
        # Cap at the top 7 (the fixed categorical palette's safe series
        # count) and fold the rest into "Other" so a many-institution stack
        # doesn't turn into unreadable noise.
        top_places = set(list(by_place_sorted.keys())[:7])
        return _accumulate_chronological([
            (date, place if place in top_places else "Other", amount)
            for date, place, cat, amount in interest_events
            if cat == value_category
        ])

    interest_by_place_crowdlending = _place_breakdown("Crowdlending")
    interest_by_place_savings = _place_breakdown("Savings")
    interest_cumulative_by_place_crowdlending = _cumulative_by_place("Crowdlending", interest_by_place_crowdlending)
    interest_cumulative_by_place_savings = _cumulative_by_place("Savings", interest_by_place_savings)

    def _interest_monthly(value_category: str, by_place_sorted: dict) -> list:
        """Interest actually posted each month (not cumulative) — deposits/
        withdrawals move around a lot, but this isolates just the recurring
        income signal month by month. Broken down per institution (same
        top-7 + "Other" fold as the cumulative chart) rather than a single
        total, so the stacked chart shows which accounts actually paid
        out that month."""
        top_places = set(list(by_place_sorted.keys())[:7])
        monthly = defaultdict(lambda: defaultdict(float))
        for date, place, cat, amount in interest_events:
            if cat == value_category:
                key = place if place in top_places else "Other"
                monthly[date[:7]][key] += amount
        return [
            {"month": m, **{k: round(v, 2) for k, v in places.items()}}
            for m, places in sorted(monthly.items())
        ]

    interest_monthly_crowdlending = _interest_monthly("Crowdlending", interest_by_place_crowdlending)
    interest_monthly_savings = _interest_monthly("Savings", interest_by_place_savings)

    today = datetime.now()

    def _category_flow_stats(value_category: str) -> dict:
        """Crowdlending/Savings return, computed from actual cash flows
        (XIRR) rather than the ETF-style current−contributed subtraction.
        That subtraction was wrong here: these categories see money get
        withdrawn and never redeposited (an exited platform, or principal
        moved into a different asset class entirely) — "contributed" kept
        accumulating every historical deposit while "current" only reflects
        what's still parked today, so the gap looked like a huge loss even
        though the money was simply withdrawn intact. XIRR treats a
        Withdrawal as a real positive cash flow back to me, so a fully
        exited platform correctly nets out near zero instead of reading as
        a loss."""
        current_value = current_allocation.get(value_category, 0.0)
        flows = [(datetime.fromisoformat(d), amt) for d, amt in category_flow_events.get(value_category, [])]
        annualized_pct = None
        if flows and current_value > 0:
            rate = _xirr(flows + [(today, current_value)])
            annualized_pct = round(rate * 100, 2) if rate is not None else None
        interest_total = sum(interest_by_place.get(value_category, {}).values())
        return {
            "current_value": round(current_value, 2),
            "total_deposited": round(category_deposited.get(value_category, 0.0), 2),
            "total_withdrawn": round(category_withdrawn.get(value_category, 0.0), 2),
            "total_interest": round(interest_total, 2),
            "annualized_pct": annualized_pct,
        }

    crowdlending_stats = _category_flow_stats("Crowdlending")
    savings_stats = _category_flow_stats("Savings")

    # Reconstructed running balance per platform (deposits + bonus + interest
    # − withdrawals) — approximate, since a defaulted loan's principal loss
    # isn't a recorded transaction, but the best available proxy for "how
    # much do I have parked at each platform over time."
    crowdlending_place_totals = defaultdict(float)
    for _date, place, amount in crowdlending_position_events:
        crowdlending_place_totals[place] += amount
    top_crowdlending_places = set(
        sorted(crowdlending_place_totals, key=lambda p: -crowdlending_place_totals[p])[:7]
    )
    crowdlending_position_by_place = _accumulate_chronological([
        (date, place if place in top_crowdlending_places else "Other", amount)
        for date, place, amount in crowdlending_position_events
    ])

    cash_by_place_sorted = {
        k: round(v, 2) for k, v in sorted(cash_by_place.items(), key=lambda kv: -kv[1]) if v > 1
    }

    def _monthly_purchases(events: list) -> list:
        monthly = defaultdict(float)
        for date, spent in events:
            monthly[date[:7]] += spent
        return [{"month": m, "amount": round(v, 2)} for m, v in sorted(monthly.items())]

    stock_purchases_monthly = _monthly_purchases(stock_purchase_events)
    crypto_purchases_monthly = _monthly_purchases(crypto_purchase_events)
    etf_purchases_monthly = _monthly_purchases(etf_purchase_events)

    def holding_annualized(key: str, current_value: float) -> dict:
        """XIRR-based annualized return for one holding — the fix for total
        gain % overstating performance on positions built up over years via
        repeated purchases, since it ignores how long each euro was invested."""
        txns = holdings_transactions.get(key, [])
        flows = [(datetime.fromisoformat(t["date"]), -t["spent"]) for t in txns if t["spent"]]
        if not flows or current_value <= 0:
            return {"annualized_pct": None, "held_days": 0, "reliable": False}
        flows.append((today, current_value))
        rate = _xirr(flows)
        held_days = (today - min(d for d, _ in flows)).days
        return {
            "annualized_pct": round(rate * 100, 2) if rate is not None else None,
            "held_days": held_days,
            # Annualizing a very young position is noisy (dividing a small
            # swing by a tiny time fraction) — flag it so the UI can show a
            # caveat instead of a wild-looking number.
            "reliable": held_days >= 90,
        }

    holdings_list = []
    for key, h in holdings.items():
        # A fully sold-out position is real history, not a "current
        # holding" — skip it based on units, the one field that's exact
        # here (a Sell nets units to precisely 0). current_value is NOT a
        # reliable signal for this: it's Total Net re-priced at *today's*
        # price for every historical row, Purchases and the Sell alike, so
        # it rarely nets to exactly zero even when the position is fully
        # closed — it leaves a residual (seen live on a closed VGWL
        # position: units 48+17+3-68=0 exactly, but current_value landed
        # at €44.88 and cost_basis at -€3,041 from the same re-pricing
        # drift), which a `current_value <= 1` check alone let through as
        # a live holding with a nonsense gain %.
        if h["units"] <= 0.0001:
            continue

        # A holding whose live price formula errored out in the sheet
        # (h["price_unavailable"]) can likewise have current_value stuck
        # at 0 despite real units held — fall back to cost basis (gain
        # reads as 0 until the sheet's price formula is fixed) instead of
        # dropping it.
        current_value = h["current_value"]
        if h["price_unavailable"] and current_value <= 1:
            current_value = h["cost_basis"]
        if current_value <= 1:
            continue

        holdings_list.append({
            # `key` is the only field guaranteed unique per holding — same
            # ISIN can now appear on two rows if the same fund is held at
            # two brokers (isin alone used to silently merge those into
            # one). isin stays display-only; use `key` for lookups (into
            # holdings_cost_basis_over_time, e.g.) and React list keys.
            "key": key,
            "isin": h["isin"],
            "ticker": h["ticker"] or h["isin"] or key,
            "name": h["name"] or h["ticker"] or h["isin"] or key,
            "category": h["category"],
            "broker": h["broker"] or "Other",
            "manager": _detect_manager(h["name"]) if h["category"] == "ETF" else None,
            "distribution": _detect_distribution(h["name"]) if h["category"] == "ETF" else None,
            "hedge": _detect_hedge(h["name"]) if h["category"] == "ETF" else None,
            "index": _detect_index(h["name"])[0] if h["category"] == "ETF" else None,
            "index_description": _detect_index(h["name"])[1] if h["category"] == "ETF" else None,
            "units": round(h["units"], 4),
            "cost_basis": round(h["cost_basis"], 2),
            "current_value": round(current_value, 2),
            "price_unavailable": h["price_unavailable"],
            "gain": round(current_value - h["cost_basis"], 2),
            "gain_pct": round((current_value - h["cost_basis"]) / h["cost_basis"] * 100, 2) if h["cost_basis"] else 0.0,
            "transactions": sorted(holdings_transactions.get(key, []), key=lambda t: t["date"], reverse=True),
            **holding_annualized(key, round(current_value, 2)),
        })

    holdings_list.sort(key=lambda h: -h["current_value"])

    holdings_cost_basis_over_time = _accumulate_chronological(holdings_cost_basis_events)

    def _blended_annualized(group_holdings: list) -> dict:
        """Same XIRR blend as growth_xirr below, scoped to one broker/manager
        group — every purchase across the group's holdings as one cash-flow
        stream, ending in the group's combined current value. Gives "average
        yearly gain %" alongside the simple total gain %, since total gain
        alone rewards whichever group happened to hold its positions
        longest, not which one actually performed best per year."""
        flows = []
        for h in group_holdings:
            for t in holdings_transactions.get(h["key"], []):
                if t["spent"]:
                    flows.append((datetime.fromisoformat(t["date"]), -t["spent"]))
        current_value = sum(h["current_value"] for h in group_holdings)
        if not flows or current_value <= 0:
            return {"annualized_pct": None, "reliable": False}
        rate = _xirr(flows + [(today, current_value)])
        held_days = (today - min(d for d, _ in flows)).days
        return {
            "annualized_pct": round(rate * 100, 2) if rate is not None else None,
            # Same 90-day floor as individual holdings — a group dominated
            # by one very recent purchase annualizes into a wild number.
            "reliable": held_days >= 90,
        }

    # Broker/manager comparisons are ETF-scoped — "managed by
    # BlackRock/Vanguard/..." or brokerage-account grouping isn't a
    # meaningful label for an individual stock, so mixing Stocks in would
    # just dilute the chart with an "Other" slice for every stock held.
    etf_holdings_list = [h for h in holdings_list if h["category"] == "ETF"]

    broker_groups = defaultdict(list)
    for h in etf_holdings_list:
        broker_groups[h["broker"]].append(h)

    etf_by_broker = sorted(
        [
            {
                "broker": broker,
                "cost_basis": round(sum(h["cost_basis"] for h in group), 2),
                "current_value": round(sum(h["current_value"] for h in group), 2),
                "gain_pct": round(
                    (sum(h["current_value"] for h in group) - sum(h["cost_basis"] for h in group))
                    / sum(h["cost_basis"] for h in group) * 100, 2,
                ) if sum(h["cost_basis"] for h in group) else 0.0,
                **_blended_annualized(group),
            }
            for broker, group in broker_groups.items()
        ],
        key=lambda b: -b["current_value"],
    )

    manager_groups = defaultdict(list)
    for h in etf_holdings_list:
        manager_groups[h["manager"]].append(h)

    etf_by_manager = sorted(
        [
            {
                "manager": manager,
                "cost_basis": round(sum(h["cost_basis"] for h in group), 2),
                "current_value": round(sum(h["current_value"] for h in group), 2),
                "gain_pct": round(
                    (sum(h["current_value"] for h in group) - sum(h["cost_basis"] for h in group))
                    / sum(h["cost_basis"] for h in group) * 100, 2,
                ) if sum(h["cost_basis"] for h in group) else 0.0,
                **_blended_annualized(group),
            }
            for manager, group in manager_groups.items()
        ],
        key=lambda m: -m["current_value"],
    )

    # Blended growth-asset XIRR — every ETF/Stock purchase across every
    # holding as one cash-flow stream, ending in today's combined value.
    # This is the rate the projection tool below extrapolates: it isolates
    # actual investment performance from new money added, unlike a naive
    # "total net worth grew X%" figure which conflates the two.
    all_growth_flows = []
    for key, h in holdings.items():
        for t in holdings_transactions.get(key, []):
            if t["spent"]:
                all_growth_flows.append((datetime.fromisoformat(t["date"]), -t["spent"]))
    growth_asset_value = round(sum(h["current_value"] for h in holdings_list), 2)
    growth_xirr = None
    if all_growth_flows and growth_asset_value > 0:
        rate = _xirr(all_growth_flows + [(today, growth_asset_value)])
        growth_xirr = round(rate * 100, 2) if rate is not None else None

    etf_composition = _etf_composition([h for h in holdings_list if h["category"] == "ETF"])

    return {
        "contributions_by_category": contributions_by_category,
        "interest_cumulative_by_place_crowdlending": interest_cumulative_by_place_crowdlending,
        "interest_by_place_crowdlending": interest_by_place_crowdlending,
        "interest_monthly_crowdlending": interest_monthly_crowdlending,
        "interest_cumulative_by_place_savings": interest_cumulative_by_place_savings,
        "interest_by_place_savings": interest_by_place_savings,
        "interest_monthly_savings": interest_monthly_savings,
        "crowdlending_stats": crowdlending_stats,
        "savings_stats": savings_stats,
        "crowdlending_position_by_place": crowdlending_position_by_place,
        "crowdlending_exited_platforms": sorted(crowdlending_exited_platforms),
        "cash_by_place": cash_by_place_sorted,
        "stock_purchases_monthly": stock_purchases_monthly,
        "crypto_purchases_monthly": crypto_purchases_monthly,
        "etf_purchases_monthly": etf_purchases_monthly,
        "holdings": holdings_list,
        "holdings_cost_basis_over_time": holdings_cost_basis_over_time,
        "etf_by_broker": etf_by_broker,
        "etf_by_manager": etf_by_manager,
        "etf_composition": etf_composition,
        "growth_asset_value": growth_asset_value,
        "growth_xirr": growth_xirr,
    }


# ── Public entry point ──────────────────────────────────────────────

def get_dashboard_data(config, force: bool = False) -> dict:
    if not force and _cache["data"] and (time.time() - _cache["fetched_at"] < _CACHE_TTL):
        return _cache["data"]

    spreadsheet_id = config.get("finance", "spreadsheet_id", default="")
    if not spreadsheet_id:
        raise NotAuthorized("No spreadsheet configured")

    access_token = _refresh_if_needed(config)

    try:
        result = _batch_get(access_token, spreadsheet_id, ["Historic!A:N", "Portfolio!A:Q"])
    except urllib.error.HTTPError as e:
        logger.error(f"Google Sheets fetch failed: {e.code} {e.read().decode()}")
        raise
    except Exception as e:
        logger.error(f"Google Sheets fetch failed: {e}")
        raise

    value_ranges = result.get("valueRanges", [])
    historic_rows = value_ranges[0].get("values", []) if len(value_ranges) > 0 else []
    portfolio_rows = value_ranges[1].get("values", []) if len(value_ranges) > 1 else []

    data = {}
    data.update(_parse_historic(historic_rows))
    data.update(_parse_portfolio(portfolio_rows, data["current_allocation"]))
    data["net_worth_stats"] = _compute_net_worth_stats(data["net_worth"])

    _cache["data"] = data
    _cache["fetched_at"] = time.time()
    return data


SNAPSHOT_SHEET = "Snapshot"
SNAPSHOT_HEADER = [
    "Timestamp", "Net Worth",
    "Cash", "Crowdlending", "Crypto", "ETF", "Gold", "Savings", "Stocks",
    "Growth Asset Value", "Growth XIRR %",
    "Crowdlending Value", "Crowdlending Interest", "Crowdlending Annualized %",
    "Savings Value", "Savings Interest", "Savings Annualized %",
    "Screenshot",
]


def save_snapshot(config, base_url: str) -> dict:
    """On-demand snapshot: appends one row of headline numbers — plus a
    link to a full-page screenshot of the dashboard, uploaded to Drive —
    to a "Snapshot" tab in the same spreadsheet, creating the tab (and
    keeping its header row in sync with SNAPSHOT_HEADER) as needed.
    Always fetches fresh (force=True) — a snapshot should reflect what's
    on screen right now, not whatever happened to still be in the
    10-minute cache. base_url is this Flask app's own address (e.g.
    "http://localhost:8080/"), needed so the headless browser can load
    the same dashboard the user is looking at.
    """
    spreadsheet_id = config.get("finance", "spreadsheet_id", default="")
    if not spreadsheet_id:
        raise NotAuthorized("No spreadsheet configured")

    access_token = _refresh_if_needed(config)
    data = get_dashboard_data(config, force=True)

    if SNAPSHOT_SHEET not in _sheet_titles(access_token, spreadsheet_id):
        _add_sheet(access_token, spreadsheet_id, SNAPSHOT_SHEET)
    _update_row(access_token, spreadsheet_id, f"{SNAPSHOT_SHEET}!A1", SNAPSHOT_HEADER)

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")

    screenshot_link = ""
    screenshot_error = None
    try:
        from web.finance_screenshot import capture_finance_screenshot
        png = capture_finance_screenshot(base_url.rstrip("/") + "/finance")
        uploaded = _upload_png_to_drive(access_token, f"EinkPi Finance Snapshot {timestamp}.png", png)
        screenshot_link = uploaded.get("webViewLink", "")
    except urllib.error.HTTPError as e:
        # A broken screenshot/upload shouldn't cost the user the numbers
        # row, which is cheap and already fetched — save it anyway and
        # report the screenshot failure separately. The response body (not
        # just str(e)) is where Google actually explains a 403 — e.g.
        # insufficient scope vs. the Drive API simply not being enabled
        # for the project, which look identical without it.
        body = e.read().decode(errors="replace")
        logger.error(f"Finance visual snapshot failed: {e.code} {body}")
        screenshot_error = f"{e.code} {body}"
    except Exception as e:
        logger.error(f"Finance visual snapshot failed: {e}")
        screenshot_error = str(e)

    alloc = data["current_allocation"]
    cl = data["crowdlending_stats"]
    sv = data["savings_stats"]
    row = [
        timestamp,
        data["net_worth_stats"]["latest"]["value"],
        alloc.get("Cash", 0), alloc.get("Crowdlending", 0), alloc.get("Crypto", 0),
        alloc.get("ETF", 0), alloc.get("Gold", 0), alloc.get("Savings", 0), alloc.get("Stocks", 0),
        data["growth_asset_value"], data["growth_xirr"],
        cl["current_value"], cl["total_interest"], cl["annualized_pct"],
        sv["current_value"], sv["total_interest"], sv["annualized_pct"],
        screenshot_link,
    ]
    _append_row(access_token, spreadsheet_id, f"{SNAPSHOT_SHEET}!A1", row)
    return {
        "sheet": SNAPSHOT_SHEET,
        "timestamp": timestamp,
        "screenshot_link": screenshot_link or None,
        "screenshot_error": screenshot_error,
    }
