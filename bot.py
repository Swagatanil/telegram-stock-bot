"""
Telegram Stock Screener Bot
----------------------------
Kaam: NSE (National Stock Exchange, India) ka roz ka "bhavcopy" data download
karta hai, usme se EQ series ke stocks filter karta hai jinka:
  - Price upward move hua ho (gainers)
  - Delivery % < 25 (kam delivery = zyada intraday/speculative trading)
aur top 20 list Telegram pe bhejta hai.

Data source: https://nsearchives.nseindia.com  (NSE ka official bhavcopy archive)
Note: Ye sirf market data screening tool hai, koi financial advice nahi hai.
"""

import os
import json
import time
import logging
from datetime import datetime, timedelta
from io import StringIO

import requests
import pandas as pd

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

try:
    from zoneinfo import ZoneInfo
    IST = ZoneInfo("Asia/Kolkata")
except ImportError:
    IST = None

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# CONFIG — environment variables se uthayega (neeche README me set karne ka
# tareeka diya hai)
# ---------------------------------------------------------------------------
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
# Optional: agar daily auto-send chahiye to apna chat id yahan/.env me set karo
DEFAULT_CHAT_ID = os.environ.get("CHAT_ID", "")
DELIVERY_THRESHOLD = float(os.environ.get("DELIVERY_THRESHOLD", "25"))
TOP_N = int(os.environ.get("TOP_N", "20"))

NSE_HOME = "https://www.nseindia.com"
# NOTE: NSE ne 2024-25 me domain badal diya — purana "archives.nseindia.com" 404 deta hai ab
NSE_BHAVCOPY_URL = "https://nsearchives.nseindia.com/products/content/sec_bhavdata_full_{date}.csv"
NSE_QUOTE_API = "https://www.nseindia.com/api/quote-equity?symbol={symbol}"

# Shaam ki list ko save karne ke liye file (agle din ka intraday tracking isse padhega)
WATCHLIST_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "watchlist.json")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


# ---------------------------------------------------------------------------
# NSE DATA FETCH
# ---------------------------------------------------------------------------
def _get_nse_session() -> requests.Session:
    """NSE site cookies maange bina seedha file download nahi deta,
    isliye pehle homepage hit karke session cookies le lete hain."""
    session = requests.Session()
    session.headers.update(HEADERS)
    session.get(NSE_HOME, timeout=10)
    return session


def _fetch_bhavcopy_for_date(session: requests.Session, date: datetime) -> pd.DataFrame:
    url = NSE_BHAVCOPY_URL.format(date=date.strftime("%d%m%Y"))
    resp = session.get(url, timeout=15)
    resp.raise_for_status()
    if "SYMBOL" not in resp.text[:200]:
        # NSE weekends/holidays par 404 ya HTML error page deta hai
        raise ValueError("No valid bhavcopy data for this date")
    df = pd.read_csv(StringIO(resp.text))
    df.columns = [c.strip() for c in df.columns]
    return df


def get_latest_trading_data(max_back_days: int = 7):
    """Aaj se peeche jaate hue, jis din ka valid data mile wahi return karega
    (weekends/holidays automatically skip ho jaayenge)."""
    session = _get_nse_session()
    date = datetime.now(IST) if IST else datetime.now()
    last_error = None
    for _ in range(max_back_days):
        try:
            df = _fetch_bhavcopy_for_date(session, date)
            return df, date
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            date -= timedelta(days=1)
    raise RuntimeError(f"Pichle {max_back_days} dino me valid NSE data nahi mila: {last_error}")


# ---------------------------------------------------------------------------
# WATCHLIST PERSISTENCE — shaam ki list save karke agle din intraday track
# ---------------------------------------------------------------------------
def save_watchlist(selected_records: list, date: datetime) -> None:
    """selected_records = user dwara button se select kiye gaye stocks ki list,
    [{"SYMBOL": "...", "CLOSE_PRICE": ...}, ...]"""
    payload = {
        "saved_on": date.strftime("%Y-%m-%d"),
        "stocks": [
            {"SYMBOL": r["SYMBOL"], "CLOSE_PRICE": r["CLOSE_PRICE"]} for r in selected_records
        ],
    }
    with open(WATCHLIST_FILE, "w", encoding="utf-8") as f:
        json.dump(payload, f)


def load_watchlist() -> list:
    if not os.path.exists(WATCHLIST_FILE):
        return []
    try:
        with open(WATCHLIST_FILE, "r", encoding="utf-8") as f:
            payload = json.load(f)
        return payload.get("stocks", [])
    except Exception:  # noqa: BLE001
        return []


# ---------------------------------------------------------------------------
# LIVE INTRADAY QUOTE — har 15 min ke tracking ke liye
# ---------------------------------------------------------------------------
def get_live_quote(session: requests.Session, symbol: str) -> dict:
    url = NSE_QUOTE_API.format(symbol=symbol)
    resp = session.get(url, timeout=8)
    resp.raise_for_status()
    data = resp.json()
    price_info = data.get("priceInfo", {})
    return {
        "lastPrice": price_info.get("lastPrice"),
        "pChange": price_info.get("pChange"),
    }


def is_market_hours(now: datetime = None) -> bool:
    """NSE trading hours: Mon-Fri, 9:15 AM - 3:30 PM IST.
    (Holidays check nahi hota — agar holiday hua to NSE API khud hi
    purana/empty data dega, message me wo dikh jaayega)."""
    now = now or (datetime.now(IST) if IST else datetime.now())
    if now.weekday() >= 5:  # Saturday=5, Sunday=6
        return False
    start = now.replace(hour=9, minute=15, second=0, microsecond=0)
    end = now.replace(hour=15, minute=30, second=0, microsecond=0)
    return start <= now <= end


# ---------------------------------------------------------------------------
# FILTER + FORMAT LOGIC
# ---------------------------------------------------------------------------
def process(df: pd.DataFrame, top_n: int, deliv_threshold: float) -> pd.DataFrame:
    df = df.copy()
    df["SERIES"] = df["SERIES"].astype(str).str.strip()
    df = df[df["SERIES"] == "EQ"]

    for col in ["CLOSE_PRICE", "PREV_CLOSE", "DELIV_PER"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.dropna(subset=["CLOSE_PRICE", "PREV_CLOSE", "DELIV_PER"])
    df["PCT_CHANGE"] = (df["CLOSE_PRICE"] - df["PREV_CLOSE"]) / df["PREV_CLOSE"] * 100

    filtered = df[(df["PCT_CHANGE"] > 0) & (df["DELIV_PER"] < deliv_threshold)]
    top = filtered.sort_values("PCT_CHANGE", ascending=False).head(top_n)
    return top[["SYMBOL", "CLOSE_PRICE", "PCT_CHANGE", "DELIV_PER"]]


def format_message(top_df: pd.DataFrame, date: datetime, deliv_threshold: float) -> str:
    date_str = date.strftime("%d-%b-%Y")
    if top_df.empty:
        return f"📊 {date_str}: Delivery% < {deliv_threshold} wale koi up-move stock nahi mile."

    lines = [
        f"📈 *Top {len(top_df)} Gainers — Delivery% < {deliv_threshold}*",
        f"🗓 {date_str}\n",
    ]
    for i, row in enumerate(top_df.itertuples(index=False), start=1):
        lines.append(
            f"{i}. *{row.SYMBOL}* — ₹{row.CLOSE_PRICE:.2f} "
            f"(+{row.PCT_CHANGE:.2f}%) | Del%: {row.DELIV_PER:.2f}"
        )
    lines.append("\n_Source: NSE bhavcopy | Sirf screening hai, advice nahi._")
    return "\n".join(lines)


def generate_daily_results():
    """Returns (top_df, date, message) — top_df watchlist save karne ke liye
    use hota hai, message Telegram pe bhejne ke liye."""
    df, date = get_latest_trading_data()
    top_df = process(df, TOP_N, DELIVERY_THRESHOLD)
    message = format_message(top_df, date, DELIVERY_THRESHOLD)
    return top_df, date, message


def build_top_list_message() -> str:
    _, _, message = generate_daily_results()
    return message


# ---------------------------------------------------------------------------
# STOCK SELECTION (inline buttons) — user 20 me se jo chahe wahi select kare
# ---------------------------------------------------------------------------
# chat_id (str) -> {"candidates": list[dict], "selected": set[str], "date": datetime}
PENDING_SELECTIONS: dict = {}


def build_selection_keyboard(candidates: list, selected: set) -> InlineKeyboardMarkup:
    rows, row = [], []
    for i, item in enumerate(candidates, start=1):
        symbol = item["SYMBOL"]
        label = f"✅ {symbol}" if symbol in selected else symbol
        row.append(InlineKeyboardButton(label, callback_data=f"toggle:{symbol}"))
        if i % 2 == 0:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([InlineKeyboardButton("✅ Confirm Selection", callback_data="confirm_selection")])
    return InlineKeyboardMarkup(rows)


async def _send_list_with_selection(chat_id, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Evening list bhejta hai, aur uske neeche buttons taaki user select kar
    sake ki kaunse stocks 15-min intraday tracking me chahiye."""
    try:
        top_df, date, msg = generate_daily_results()
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to build list")
        await context.bot.send_message(chat_id=chat_id, text=f"⚠️ Data fetch nahi ho paaya: {exc}")
        return

    await context.bot.send_message(chat_id=chat_id, text=msg, parse_mode="Markdown")

    candidates = top_df.to_dict("records")
    if not candidates:
        return

    key = str(chat_id)
    PENDING_SELECTIONS[key] = {"candidates": candidates, "selected": set(), "date": date}
    keyboard = build_selection_keyboard(candidates, set())
    await context.bot.send_message(
        chat_id=chat_id,
        text=(
            "👇 Inme se jo stocks tumhe *15-min intraday tracking* ke liye chahiye, "
            "unpe tap karo (multiple select kar sakte ho), phir neeche "
            "*'Confirm Selection'* dabao:"
        ),
        parse_mode="Markdown",
        reply_markup=keyboard,
    )


async def selection_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    key = str(query.message.chat_id)
    state = PENDING_SELECTIONS.get(key)

    if not state:
        await query.answer("Ye selection expire ho gayi, /top20 dobara try karo.", show_alert=True)
        return

    data = query.data
    if data == "confirm_selection":
        selected_records = [c for c in state["candidates"] if c["SYMBOL"] in state["selected"]]
        if not selected_records:
            await query.answer("Pehle kam se kam ek stock select karo!", show_alert=True)
            return
        save_watchlist(selected_records, state["date"])
        symbols_str = ", ".join(r["SYMBOL"] for r in selected_records)
        await query.edit_message_text(
            f"✅ Tracking shuru: {symbols_str}\n\n"
            "Market hours (9:15 AM–3:30 PM, Mon-Fri) me har 15 min update milega."
        )
        PENDING_SELECTIONS.pop(key, None)
        await query.answer()
        return

    if data.startswith("toggle:"):
        symbol = data.split(":", 1)[1]
        if symbol in state["selected"]:
            state["selected"].remove(symbol)
        else:
            state["selected"].add(symbol)
        keyboard = build_selection_keyboard(state["candidates"], state["selected"])
        await query.edit_message_reply_markup(reply_markup=keyboard)
        await query.answer()


# ---------------------------------------------------------------------------
# TELEGRAM BOT HANDLERS
# ---------------------------------------------------------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Namaste! 👋\n\n"
        "Main NSE stocks screen karta hoon: top up-move gainers jinka "
        f"delivery % {DELIVERY_THRESHOLD} se kam hai.\n\n"
        "Command: /top20 — abhi ki list mangwane ke liye.\n"
        "List ke baad buttons se select karo kaunse stocks ka 15-min "
        "intraday movement track karna hai."
    )


async def top20(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    await update.message.reply_text("Data fetch kar raha hoon, thoda ruko... ⏳")
    await _send_list_with_selection(chat_id, context)


async def daily_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Har trading day shaam ko auto-send (sirf agar CHAT_ID set hai).
    Saath me selection buttons bhejta hai — jo stocks user select karega
    sirf unhi ka agle din intraday tracking hoga."""
    if not DEFAULT_CHAT_ID:
        return
    await _send_list_with_selection(DEFAULT_CHAT_ID, context)


async def intraday_tracker_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Har 15 min (sirf market hours me) — pichli shaam ki watchlist ke
    stocks ka live price/% change bhejta hai."""
    if not DEFAULT_CHAT_ID:
        return
    if not is_market_hours():
        return

    watchlist = load_watchlist()
    if not watchlist:
        return

    session = _get_nse_session()
    now_str = (datetime.now(IST) if IST else datetime.now()).strftime("%I:%M %p")
    lines = [f"⏱ *Intraday Move Update — {now_str}*\n"]
    for item in watchlist:
        symbol = item.get("SYMBOL")
        try:
            quote = get_live_quote(session, symbol)
            lp = quote.get("lastPrice")
            pchg = quote.get("pChange")
            if lp is None or pchg is None:
                lines.append(f"{symbol}: data nahi mila")
            else:
                arrow = "🟢" if pchg >= 0 else "🔴"
                lines.append(f"{arrow} *{symbol}* — ₹{lp:.2f} ({pchg:+.2f}%)")
        except Exception:  # noqa: BLE001
            lines.append(f"{symbol}: fetch fail")
        time.sleep(0.2)  # NSE rate-limit se bachne ke liye

    await context.bot.send_message(
        chat_id=DEFAULT_CHAT_ID, text="\n".join(lines), parse_mode="Markdown"
    )


def main() -> None:
    if not BOT_TOKEN:
        raise SystemExit("BOT_TOKEN environment variable set nahi hai. README dekho.")

    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("top20", top20))
    app.add_handler(CallbackQueryHandler(selection_callback))

    # Daily auto-send: market band hone ke baad bhavcopy file ~6:30-7 PM IST
    # tak aa jaati hai, isliye 7:00 PM IST par schedule kiya hai.
    if IST is not None:
        app.job_queue.run_daily(daily_job, time=datetime.strptime("19:00", "%H:%M").time().replace(tzinfo=IST))

    # Har 15 minute (900 seconds) — intraday_tracker_job khud check karega
    # ki abhi market hours hai ya nahi.
    app.job_queue.run_repeating(intraday_tracker_job, interval=900, first=15)

    logger.info("Bot start ho gaya, polling shuru...")
    app.run_polling()


if __name__ == "__main__":
    main()
