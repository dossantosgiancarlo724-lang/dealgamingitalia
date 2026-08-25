import asyncio
import json
import os
from io import BytesIO

from PIL import Image, ImageDraw, ImageFont
from telegram import Bot, Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes

TOKEN = os.getenv("TOKEN") or os.getenv("BOT_TOKEN") or ""
CHANNEL_GAMING = "@DealGamingItalia"
CHANNEL_GENERAL = "@SuperDealItalia"
UTENTI_FILE = "utenti.json"
ADMIN_ID = 8816533518

PAROLE_GAMING = [
    "playstation", "ps5", "ps4", "ps3", "xbox", "nintendo", "switch", "switch 2",
    "steam deck", "rog ally", "gaming", "videogioco", "videogiochi", "gpu", "rtx",
    "radeon", "scheda video", "monitor gaming", "mouse gaming", "tastiera gaming",
    "cuffie gaming", "controller", "dual sense", "manette"
]


def carica_utenti():
    if not os.path.exists(UTENTI_FILE):
        return {"utenti": []}
    try:
        with open(UTENTI_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"utenti": []}


def salva_utenti(database):
    with open(UTENTI_FILE, "w", encoding="utf-8") as f:
        json.dump(database, f, indent=4)


def e_gaming(nome):
    nome = nome.lower()
    return any(p in nome for p in PAROLE_GAMING)


def get_font(size, bold=False):
    paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
    ]
    for path in paths:
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def crea_grafica(nome, prezzo, sconto, image_bytes):
    W, H = 1080, 1350
    canvas = Image.new("RGB", (W, H), "#f4f5f7")
    draw = ImageDraw.Draw(canvas)
    draw.rounded_rectangle((35, 35, 1045, 190), 32, fill="#111827")
    draw.text((70, 58), "DEAL GAMING ITALIA", font=get_font(42, True), fill="white")
    draw.text((72, 118), "🔥 OCCASIONE ECCEZIONALE", font=get_font(30, True), fill="#fbbf24")

    try:
        product = Image.open(BytesIO(image_bytes)).convert("RGB")
        product.thumbnail((880, 610), Image.Resampling.LANCZOS)
        card = Image.new("RGB", (920, 650), "white")
        card.paste(product, ((920-product.width)//2, (650-product.height)//2))
        canvas.paste(card, (80, 225))
        draw.rounded_rectangle((80, 225, 1000, 875), 28, outline="#d1d5db", width=3)
    except Exception:
        draw.rounded_rectangle((80, 225, 1000, 875), 28, fill="white", outline="#d1d5db", width=3)

    draw.rounded_rectangle((790, 255, 965, 345), 24, fill="#dc2626")
    draw.text((815, 275), f"-{sconto:.0f}%", font=get_font(48, True), fill="white")
    draw.text((80, 925), nome[:42], font=get_font(40, True), fill="#111827")
    draw.text((80, 995), "PREZZO DELL'OFFERTA", font=get_font(24, True), fill="#6b7280")
    draw.text((80, 1020), f"{prezzo:.2f} €", font=get_font(72, True), fill="#16a34a")
    draw.text((80, 1115), f"Risparmio indicativo: {prezzo*sconto/100:.2f} €", font=get_font(28, True), fill="#374151")
    draw.rounded_rectangle((80, 1180, 1000, 1275), 24, fill="#111827")
    draw.text((260, 1204), "ACQUISTA ORA", font=get_font(38, True), fill="white")

    output = BytesIO()
    output.name = "offerta.png"
    canvas.save(output, "PNG", optimize=True)
    output.seek(0)
    return output


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    db = carica_utenti()
    if user_id not in db["utenti"]:
        db["utenti"].append(user_id)
        salva_utenti(db)
    await update.message.reply_text(
        "🔔 AVVISI ATTIVATI!\n\nRiceverai una notifica quando troviamo un'occasione davvero interessante. 🔥\n\nPer disattivare usa /stop"
    )


async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    db = carica_utenti()
    if user_id in db["utenti"]:
        db["utenti"].remove(user_id)
        salva_utenti(db)
    await update.message.reply_text("🔕 Avvisi disattivati.\n\nPuoi riattivarli con /start.")


async def pubblica_offerta(nome, prezzo, sconto, link, image_id):
    channel = CHANNEL_GAMING if e_gaming(nome) else CHANNEL_GENERAL
    category = "🎮 GAMING" if e_gaming(nome) else "🛍️ SUPER DEAL"
    risparmio = prezzo * sconto / 100
    caption = (
        "🔥 <b>OFFERTA DA NON PERDERE!</b> 🔥\n\n"
        f"{category}\n\n📦 <b>{nome}</b>\n\n"
        f"💰 <b>{prezzo:.2f} €</b>\n📉 <b>-{sconto:.0f}%</b> di sconto\n"
        f"💸 Risparmi circa <b>{risparmio:.2f} €</b>\n\n"
        "🟢 <b>OFFERTA ATTIVA</b>\n\n"
        "⚡ Controllala subito: il prezzo può cambiare in qualsiasi momento.\n\n👇 <b>VEDI L'OFFERTA</b>"
    )
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("🛒 ACQUISTA ORA", url=link)]])
    bot = Bot(TOKEN)
    try:
        file = await bot.get_file(image_id)
        image_bytes = bytes(await file.download_as_bytearray())
        graphic = crea_grafica(nome, prezzo, sconto, image_bytes)
        await bot.send_photo(chat_id=channel, photo=graphic, caption=caption, parse_mode="HTML", reply_markup=keyboard)
        db = carica_utenti()
        for user_id in db["utenti"]:
            try:
                graphic.seek(0)
                await bot.send_photo(chat_id=user_id, photo=graphic, caption=caption, parse_mode="HTML", reply_markup=keyboard)
            except Exception as exc:
                print(f"⚠️ Impossibile inviare a {user_id}: {exc}")
    finally:
        await bot.shutdown()


async def offerta(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Non sei autorizzato.")
        return
    if not update.message.photo:
        await update.message.reply_text("📸 Invia /offerta come didascalia di una foto.\n\n/offerta PS5 648 10 https://amzn.eu/...")
        return
    parts = (update.message.caption or "").split(maxsplit=4)
    if len(parts) != 5 or parts[0] != "/offerta":
        await update.message.reply_text("❌ Usa: /offerta NOME PREZZO SCONTO LINK")
        return
    _, name, price_text, discount_text, link = parts
    try:
        price = float(price_text.replace(",", "."))
        discount = float(discount_text.replace(",", "."))
    except ValueError:
        await update.message.reply_text("❌ Prezzo o sconto non validi.")
        return
    if price <= 0 or not 0 <= discount <= 100:
        await update.message.reply_text("❌ Controlla prezzo e sconto.")
        return
    try:
        await pubblica_offerta(name, price, discount, link, update.message.photo[-1].file_id)
        await update.message.reply_text("✅ OFFERTA PUBBLICATA!\n\n🎨 Grafica: OK\n📢 Canale: OK\n🛒 Pulsante: OK\n🔔 Notifiche: OK")
    except Exception as exc:
        print(f"❌ ERRORE /offerta: {exc}")
        await update.message.reply_text("❌ Errore durante la pubblicazione. Controlla i log.")


async def id_utente(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"🆔 Il tuo Telegram ID è:\n\n<code>{update.effective_user.id}</code>", parse_mode="HTML")


async def main():
    if not TOKEN:
        raise RuntimeError("Token non configurato: imposta TOKEN o BOT_TOKEN in Railway.")

    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stop", stop))
    app.add_handler(CommandHandler("offerta", offerta))
    app.add_handler(CommandHandler("id", id_utente))

    port = int(os.getenv("PORT", "8080"))
    domain = os.getenv("RAILWAY_PUBLIC_DOMAIN") or "dealgamingitalia-production.up.railway.app"
    path = "telegram-webhook"
    url = f"https://{domain}/{path}"

    print("================================")
    print("🤖 DealGaming Bot ONLINE!")
    print("🌐 WEBHOOK MODE")
    print("🎨 GRAFICA AUTOMATICA")
    print("🎮 DealGaming Italia")
    print("🛍️ SuperDeal Italia")
    print("================================", flush=True)

    await app.initialize()
    await app.start()
    await app.updater.start_webhook(
        listen="0.0.0.0",
        port=port,
        url_path=path,
        webhook_url=url,
        drop_pending_updates=True,
        allowed_updates=Update.ALL_TYPES,
    )

    try:
        while True:
            await asyncio.sleep(3600)
    finally:
        await app.updater.stop()
        await app.stop()
        await app.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
