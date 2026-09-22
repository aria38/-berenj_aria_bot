import os
import sqlite3
from datetime import datetime
from decimal import Decimal, InvalidOperation

import jdatetime
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    Application, CommandHandler, MessageHandler, ConversationHandler,
    ContextTypes, filters
)

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "PASTE_YOUR_BOT_TOKEN_HERE")
DB_PATH = os.getenv("ARIA_DB", "aria_accounting.db")

MAIN = [
    ["🛒 ثبت خرید", "💰 ثبت فروش"],
    ["📒 حساب مشتریان", "💳 ثبت پرداخت"],
    ["📦 موجودی کالا", "💸 هزینه‌های مغازه"],
    ["📊 گزارش‌ها", "🔎 جستجو"],
]

def db():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con

def init_db():
    con = db()
    cur = con.cursor()
    cur.executescript("""
    CREATE TABLE IF NOT EXISTS transactions(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        kind TEXT NOT NULL,
        item TEXT,
        qty REAL DEFAULT 0,
        unit_price INTEGER DEFAULT 0,
        total INTEGER DEFAULT 0,
        person TEXT,
        payment TEXT,
        note TEXT,
        created_at TEXT NOT NULL,
        created_at_j TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS payments(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        person TEXT NOT NULL,
        amount INTEGER NOT NULL,
        note TEXT,
        created_at TEXT NOT NULL,
        created_at_j TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS expenses(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        category TEXT NOT NULL,
        amount INTEGER NOT NULL,
        note TEXT,
        created_at TEXT NOT NULL,
        created_at_j TEXT NOT NULL
    );
    """)
    con.commit()
    con.close()

def now():
    dt = datetime.now()
    return dt.isoformat(timespec="seconds"), jdatetime.datetime.fromgregorian(datetime=dt).strftime("%Y/%m/%d %H:%M")

def money(n):
    return f"{int(n):,} تومان"

def parse_money(s):
    s = s.replace(",", "").replace("٬","").replace("تومان","").strip()
    return int(Decimal(s))

def parse_num(s):
    return float(s.replace(",", "").replace("٬","").strip())

def kb(rows):
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🌾 حسابداری برنج آریا\n\n"
        "ثبت خرید، فروش، نسیه، پرداخت، هزینه و موجودی.\n"
        "برای شروع یکی از گزینه‌های زیر را انتخاب کنید.",
        reply_markup=kb(MAIN)
    )

# ---------- خرید ----------
BUY_ITEM, BUY_QTY, BUY_PRICE, BUY_PERSON, BUY_PAYMENT, BUY_NOTE = range(6)

async def buy_start(update, context):
    context.user_data.clear()
    await update.message.reply_text("🛒 نام کالا را وارد کنید:")
    return BUY_ITEM

async def buy_item(update, context):
    context.user_data["item"]=update.message.text
    await update.message.reply_text("مقدار (کیلو/عدد) را وارد کنید:")
    return BUY_QTY

async def buy_qty(update, context):
    try: context.user_data["qty"]=parse_num(update.message.text)
    except: await update.message.reply_text("❌ مقدار نامعتبر است. دوباره وارد کنید."); return BUY_QTY
    await update.message.reply_text("قیمت هر واحد را به تومان وارد کنید:")
    return BUY_PRICE

async def buy_price(update, context):
    try: context.user_data["price"]=parse_money(update.message.text)
    except: await update.message.reply_text("❌ مبلغ نامعتبر است."); return BUY_PRICE
    await update.message.reply_text("نام فروشنده را وارد کنید (اگر ندارد: -):")
    return BUY_PERSON

async def buy_person(update, context):
    context.user_data["person"]=update.message.text
    await update.message.reply_text("نحوه پرداخت؟", reply_markup=kb([["💵 نقدی","📒 قسطی"],["❌ لغو"]]))
    return BUY_PAYMENT

async def buy_payment(update, context):
    if update.message.text=="❌ لغو": return await cancel(update,context)
    context.user_data["payment"]="نقدی" if "نقدی" in update.message.text else "قسطی"
    await update.message.reply_text("توضیحات (اختیاری؛ اگر ندارد -):")
    return BUY_NOTE

async def buy_note(update, context):
    note=update.message.text
    d=context.user_data
    total=round(d["qty"]*d["price"])
    created, createdj=now()
    con=db()
    con.execute("""INSERT INTO transactions(kind,item,qty,unit_price,total,person,payment,note,created_at,created_at_j)
                   VALUES('خرید',?,?,?,?,?,?,?,?,?)""",
                (d["item"],d["qty"],d["price"],total,d["person"],d["payment"],note,created,createdj))
    con.commit(); con.close()
    await update.message.reply_text(
        f"✅ خرید ثبت شد\n\nکالا: {d['item']}\nمقدار: {d['qty']:g}\n"
        f"قیمت واحد: {money(d['price'])}\nمبلغ کل: {money(total)}\n"
        f"فروشنده: {d['person']}\nپرداخت: {d['payment']}\nتاریخ: {createdj}",
        reply_markup=kb(MAIN))
    return ConversationHandler.END

# ---------- فروش ----------
SELL_ITEM, SELL_QTY, SELL_PRICE, SELL_PERSON, SELL_PAYMENT, SELL_NOTE = range(10,16)

async def sell_start(update, context):
    context.user_data.clear(); await update.message.reply_text("💰 نام کالا را وارد کنید:"); return SELL_ITEM
async def sell_item(update, context):
    context.user_data["item"]=update.message.text; await update.message.reply_text("مقدار را وارد کنید:"); return SELL_QTY
async def sell_qty(update, context):
    try: context.user_data["qty"]=parse_num(update.message.text)
    except: await update.message.reply_text("❌ مقدار نامعتبر است."); return SELL_QTY
    await update.message.reply_text("قیمت فروش هر واحد را به تومان وارد کنید:"); return SELL_PRICE
async def sell_price(update, context):
    try: context.user_data["price"]=parse_money(update.message.text)
    except: await update.message.reply_text("❌ مبلغ نامعتبر است."); return SELL_PRICE
    await update.message.reply_text("نام مشتری را وارد کنید (اگر ندارد: مشتری نقدی):"); return SELL_PERSON
async def sell_person(update, context):
    context.user_data["person"]=update.message.text; await update.message.reply_text(
        "نحوه پرداخت؟", reply_markup=kb([["💵 نقدی","📒 نسیه"],["❌ لغو"]]))
    return SELL_PAYMENT
async def sell_payment(update, context):
    if update.message.text=="❌ لغو": return await cancel(update,context)
    context.user_data["payment"]="نقدی" if "نقدی" in update.message.text else "نسیه"
    await update.message.reply_text("توضیحات (اختیاری؛ اگر ندارد -):"); return SELL_NOTE
async def sell_note(update, context):
    d=context.user_data; total=round(d["qty"]*d["price"]); created,createdj=now()
    con=db()
    con.execute("""INSERT INTO transactions(kind,item,qty,unit_price,total,person,payment,note,created_at,created_at_j)
                   VALUES('فروش',?,?,?,?,?,?,?,?,?)""",
                (d["item"],d["qty"],d["price"],total,d["person"],d["payment"],update.message.text,created,createdj))
    con.commit(); con.close()
    await update.message.reply_text(
        f"✅ فروش ثبت شد\n\nکالا: {d['item']}\nمقدار: {d['qty']:g}\n"
        f"مبلغ کل: {money(total)}\nمشتری: {d['person']}\nپرداخت: {d['payment']}\nتاریخ: {createdj}",
        reply_markup=kb(MAIN))
    return ConversationHandler.END

# ---------- پرداخت ----------
PAY_PERSON, PAY_AMOUNT, PAY_NOTE = range(20,23)
async def pay_start(update, context):
    context.user_data.clear(); await update.message.reply_text("👤 نام مشتری/شخص را وارد کنید:"); return PAY_PERSON
async def pay_person(update, context):
    context.user_data["person"]=update.message.text; await update.message.reply_text("مبلغ پرداختی را به تومان وارد کنید:"); return PAY_AMOUNT
async def pay_amount(update, context):
    try: context.user_data["amount"]=parse_money(update.message.text)
    except: await update.message.reply_text("❌ مبلغ نامعتبر است."); return PAY_AMOUNT
    await update.message.reply_text("توضیحات (اختیاری):"); return PAY_NOTE
async def pay_note(update, context):
    created,createdj=now(); d=context.user_data; con=db()
    con.execute("INSERT INTO payments(person,amount,note,created_at,created_at_j) VALUES(?,?,?,?,?)",
                (d["person"],d["amount"],update.message.text,created,createdj))
    con.commit(); con.close()
    await update.message.reply_text(f"✅ پرداخت ثبت شد\n{d['person']}\n{money(d['amount'])}\n{createdj}", reply_markup=kb(MAIN))
    return ConversationHandler.END

# ---------- هزینه ----------
EXP_CAT, EXP_AMOUNT, EXP_NOTE = range(30,33)
async def exp_start(update, context):
    context.user_data.clear(); await update.message.reply_text(
        "💸 نوع هزینه را وارد کنید:", reply_markup=kb([["🏠 کرایه مغازه","💡 برق"],["💧 آب","🔥 گاز"],["🚚 کرایه حمل","📦 بسته‌بندی"],["➕ سایر"]]))
    return EXP_CAT
async def exp_cat(update, context):
    context.user_data["cat"]=update.message.text; await update.message.reply_text("مبلغ را به تومان وارد کنید:"); return EXP_AMOUNT
async def exp_amount(update, context):
    try: context.user_data["amount"]=parse_money(update.message.text)
    except: await update.message.reply_text("❌ مبلغ نامعتبر است."); return EXP_AMOUNT
    await update.message.reply_text("توضیحات (اختیاری):"); return EXP_NOTE
async def exp_note(update, context):
    created,createdj=now(); d=context.user_data; con=db()
    con.execute("INSERT INTO expenses(category,amount,note,created_at,created_at_j) VALUES(?,?,?,?,?)",
                (d["cat"],d["amount"],update.message.text,created,createdj))
    con.commit(); con.close()
    await update.message.reply_text(f"✅ هزینه ثبت شد\n{d['cat']}\n{money(d['amount'])}\n{createdj}", reply_markup=kb(MAIN))
    return ConversationHandler.END

async def inventory(update, context):
    con=db()
    rows=con.execute("""SELECT item,
        COALESCE(SUM(CASE WHEN kind='خرید' THEN qty ELSE 0 END),0) buys,
        COALESCE(SUM(CASE WHEN kind='فروش' THEN qty ELSE 0 END),0) sells
        FROM transactions WHERE item IS NOT NULL GROUP BY item ORDER BY item""").fetchall()
    con.close()
    if not rows: text="📦 هنوز موجودی ثبت نشده است."
    else:
        text="📦 موجودی فعلی\n\n" + "\n".join(
            f"• {r['item']}: {r['buys']-r['sells']:g} واحد" for r in rows)
    await update.message.reply_text(text, reply_markup=kb(MAIN))

async def customers(update, context):
    con=db()
    people=con.execute("""SELECT person,
        COALESCE((SELECT SUM(total) FROM transactions t2 WHERE t2.person=t.person AND t2.kind='فروش' AND t2.payment='نسیه'),0) debt,
        COALESCE((SELECT SUM(amount) FROM payments p WHERE p.person=t.person),0) paid
        FROM transactions t WHERE person IS NOT NULL AND person!='-' GROUP BY person ORDER BY person""").fetchall()
    con.close()
    if not people: text="📒 هنوز حساب مشتری ثبت نشده است."
    else:
        text="📒 حساب مشتریان\n\n"
        for r in people:
            balance=r["debt"]-r["paid"]
            text+=f"• {r['person']}: {money(balance)}\n"
    await update.message.reply_text(text, reply_markup=kb(MAIN))

async def reports(update, context):
    con=db()
    sales=con.execute("SELECT COALESCE(SUM(total),0) n FROM transactions WHERE kind='فروش'").fetchone()["n"]
    buys=con.execute("SELECT COALESCE(SUM(total),0) n FROM transactions WHERE kind='خرید'").fetchone()["n"]
    exp=con.execute("SELECT COALESCE(SUM(amount),0) n FROM expenses").fetchone()["n"]
    debt=con.execute("SELECT COALESCE(SUM(total),0) n FROM transactions WHERE kind='فروش' AND payment='نسیه'").fetchone()["n"]
    paid=con.execute("SELECT COALESCE(SUM(amount),0) n FROM payments").fetchone()["n"]
    con.close()
    await update.message.reply_text(
        f"📊 گزارش کلی حسابداری برنج آریا\n\n"
        f"💰 کل فروش: {money(sales)}\n"
        f"🛒 کل خرید: {money(buys)}\n"
        f"💸 کل هزینه: {money(exp)}\n"
        f"📒 فروش نسیه: {money(debt)}\n"
        f"💳 پرداخت‌های ثبت‌شده: {money(paid)}\n"
        f"📌 مانده نسیه: {money(debt-paid)}",
        reply_markup=kb(MAIN))

async def search(update, context):
    await update.message.reply_text(
        "🔎 برای جستجو، نام کالا یا مشتری را بعد از /جستجو بنویسید.\n"
        "مثال:\n/جستجو هاشمی\n/جستجو احمدی",
        reply_markup=kb(MAIN))

async def do_search(update, context):
    q=" ".join(context.args).strip()
    if not q: return await search(update,context)
    con=db()
    rows=con.execute("""SELECT kind,item,qty,total,person,payment,created_at_j
                        FROM transactions WHERE item LIKE ? OR person LIKE ?
                        ORDER BY id DESC LIMIT 20""",(f"%{q}%",f"%{q}%")).fetchall()
    con.close()
    if not rows: text="❌ موردی پیدا نشد."
    else:
        text="🔎 نتایج جستجو\n\n" + "\n".join(
            f"{r['created_at_j']} | {r['kind']} | {r['item']} | {r['qty']:g} | {money(r['total'])} | {r['person'] or '-'}"
            for r in rows)
    await update.message.reply_text(text, reply_markup=kb(MAIN))

async def cancel(update, context):
    context.user_data.clear()
    await update.message.reply_text("❌ عملیات لغو شد.", reply_markup=kb(MAIN))
    return ConversationHandler.END

def conv(entry, states):
    return ConversationHandler(
        entry_points=[MessageHandler(filters.Regex(entry), entry)],
        states=states,
        fallbacks=[CommandHandler("لغو", cancel), MessageHandler(filters.Regex("^❌ لغو$"), cancel)],
        allow_reentry=True
    )

def main():
    if TOKEN == "PASTE_YOUR_BOT_TOKEN_HERE":
        raise SystemExit("TELEGRAM_BOT_TOKEN را تنظیم کنید.")
    init_db()
    app=Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("جستجو", do_search))

    app.add_handler(conv("^🛒 ثبت خرید$", {BUY_ITEM:[MessageHandler(filters.TEXT & ~filters.COMMAND,buy_item)],
        BUY_QTY:[MessageHandler(filters.TEXT & ~filters.COMMAND,buy_qty)],
        BUY_PRICE:[MessageHandler(filters.TEXT & ~filters.COMMAND,buy_price)],
        BUY_PERSON:[MessageHandler(filters.TEXT & ~filters.COMMAND,buy_person)],
        BUY_PAYMENT:[MessageHandler(filters.TEXT & ~filters.COMMAND,buy_payment)],
        BUY_NOTE:[MessageHandler(filters.TEXT & ~filters.COMMAND,buy_note)]}))
    app.add_handler(conv("^💰 ثبت فروش$", {SELL_ITEM:[MessageHandler(filters.TEXT & ~filters.COMMAND,sell_item)],
        SELL_QTY:[MessageHandler(filters.TEXT & ~filters.COMMAND,sell_qty)],
        SELL_PRICE:[MessageHandler(filters.TEXT & ~filters.COMMAND,sell_price)],
        SELL_PERSON:[MessageHandler(filters.TEXT & ~filters.COMMAND,sell_person)],
        SELL_PAYMENT:[MessageHandler(filters.TEXT & ~filters.COMMAND,sell_payment)],
        SELL_NOTE:[MessageHandler(filters.TEXT & ~filters.COMMAND,sell_note)]}))
    app.add_handler(conv("^💳 ثبت پرداخت$", {PAY_PERSON:[MessageHandler(filters.TEXT & ~filters.COMMAND,pay_person)],
        PAY_AMOUNT:[MessageHandler(filters.TEXT & ~filters.COMMAND,pay_amount)],
        PAY_NOTE:[MessageHandler(filters.TEXT & ~filters.COMMAND,pay_note)]}))
    app.add_handler(conv("^💸 هزینه‌های مغازه$", {EXP_CAT:[MessageHandler(filters.TEXT & ~filters.COMMAND,exp_cat)],
        EXP_AMOUNT:[MessageHandler(filters.TEXT & ~filters.COMMAND,exp_amount)],
        EXP_NOTE:[MessageHandler(filters.TEXT & ~filters.COMMAND,exp_note)]}))

    app.add_handler(MessageHandler(filters.Regex("^📦 موجودی کالا$"), inventory))
    app.add_handler(MessageHandler(filters.Regex("^📒 حساب مشتریان$"), customers))
    app.add_handler(MessageHandler(filters.Regex("^📊 گزارش‌ها$"), reports))
    app.add_handler(MessageHandler(filters.Regex("^🔎 جستجو$"), search))
    app.add_handler(MessageHandler(filters.Regex("^❌ لغو$"), cancel))
    app.add_handler(MessageHandler(filters.COMMAND, lambda u,c: None))
    app.run_polling()

if __name__=="__main__":
    main()
