import asyncio
import json
import os
from io import BytesIO

from PIL import Image, ImageDraw, ImageFont
from telegram import Bot, Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes

TOKEN = os.getenv("BOT_TOKEN", "")
CHANNEL_GAMING = "@DealGamingItalia"
CHANNEL_GENERAL = "@SuperDealItalia"
UTENTI_FILE = "utenti.json"
ADMIN_ID = 8816533518

PAROLE_GAMING = [
    "playstation", "ps5", "ps4", "ps3", "xbox", "nintendo", "switch",
    "switch 2", "steam deck", "rog ally", "gaming", "videogioco",
    "videogiochi", "gpu", "rtx", "radeon", "scheda video",
    "monitor gaming", "mouse gaming", "tastiera gaming", "cuffie gaming",
    "controller", "dual sense", "manette"
]


def carica_utenti():
    if not os.path.exists(UTENTI_FILE):
        return {"utenti": []}
    try:
        with open(UTENTI_FILE, "r", encoding="utf-8") as file:
            return json.load(file)
    except Exception:
        return {"utenti": []}


def salva_utenti(database):
    with open(UTENTI_FILE, "w", encoding="utf-8") as file:
        json.dump(database, file, indent=4)


def e_gaming(nome):
    return any(parola in nome.lower() for parola in PAROLE_GAMING)


def font(size, bold=False):
    paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
    ]
    for path in paths:
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def ellissi(draw, text, fnt, max_width):
    if draw.textbbox((0, 0), text, font=fnt)[2] <= max_width:
        return text
    while len(text) > 3 and draw.textbbox((0, 0), text + "...", font=fnt)[2] > max_width:
        text = text[:-1]
    return text.rstrip() + "..."


def crea_grafica(nome, prezzo, sconto, immagine_bytes):
    W, H = 1080, 1350
    canvas = Image.new("RGB", (W, H), "#f4f5f7")
    draw = ImageDraw.Draw(canvas)
    draw.rounded_rectangle((35, 35, W - 35, 190), radius=32, fill="#111827")
    draw.text((70, 58), "DEAL GAMING ITALIA", font=font(42, True), fill="white")
    draw.text((72, 118), "🔥 OCCASIONE ECCEZIONALE", font=font(30, True), fill="#fbbf24")

    try:
        product = Image.open(BytesIO(immagine_bytes)).convert("RGB")
        product.thumbnail((880, 610), Image.Resampling.LANCZOS)
        card = Image.new("RGB", (920, 650), "white")
        card.paste(product, ((920 - product.width) // 2, (650 - product.height) // 2))
        canvas.paste(card, (80, 225))
        draw.rounded_rectangle((80, 225, 1000, 875), radius=28, outline="#d1d5db", width=3)
    except Exception:
        draw.rounded_rectangle((80, 225, 1000, 875), radius=28, fill="white", outline="#d1d5db", width=3)

    draw.rounded_rectangle((790, 255, 965, 345), radius=24, fill="#dc2626")
    draw.text((815, 275), f"-{sconto:.0f}%", font=font(48, True), fill="white")
    draw.text((80, 925), ellissi(draw, nome, font(40, True), 920), font=font(40, True), fill="#111827")
    draw.text((80, 995), "PREZZO DELL'OFFERTA", font=font(24, True), fill="#6b7280")
    draw.text((80, 1020), f"{prezzo:.2f} €", font=font(72, True), fill="#16a34a")
    risparmio = prezzo * sconto / 100
    draw.text((80, 1115), f"Risparmio indicativo: {risparmio:.2f} €", font=font(28, True), fill="#374151")
    draw.rounded_rectangle((80, 1180, 1000, 1275), radius=24, fill="#111827")
    draw.text((260, 1204), "ACQUISTA ORA", font=font(38, True), fill="white")

    output = BytesIO()
    output.name = "offerta.png"
    canvas.save(output, format="PNG", optimize=True)
    output.seek(0)
    return output


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    database = carica_utenti()
    if user_id not in database["utenti"]:
        database["utenti"].append(user_id)
        salva_utenti(database)
    await update.message.reply_text(
        "🔔 AVVISI ATTIVATI!\n\n"
        "Riceverai una notifica quando troviamo un'occasione davvero interessante. 🔥\n\n"
        "Per disattivare gli avvisi usa /stop"
    )


async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    database = carica_utenti()
    if user_id in database["utenti"]:
        database["utenti"].remove(user_id)
        salva_utenti(database)
    await update.message.reply_text("🔕 Avvisi disattivati.\n\nPuoi riattivarli in qualsiasi momento con /start.")


async def pubblica_offerta(nome, prezzo, sconto, link, immagine):
    canale = CHANNEL_GAMING if e_gaming(nome) else CHANNEL_GENERAL
    categoria = "🎮 GAMING" if e_gaming(nome) else "🛍️ SUPER DEAL"
    risparmio = prezzo * sconto / 100
    messaggio = (
        "🔥 <b>OFFERTA DA NON PERDERE!</b> 🔥\n\n"
        f"{categoria}\n\n📦 <b>{nome}</b>\n\n"
        f"💰 <b>{prezzo:.2f} €</b>\n📉 <b>-{sconto:.0f}%</b> di sconto\n"
        f"💸 Risparmi circa <b>{risparmio:.2f} €</b>\n\n"
        "🟢 <b>OFFERTA ATTIVA</b>\n\n"
        "⚡ Controllala subito: le offerte possono terminare in qualsiasi momento.\n\n"
        "👇 <b>VEDI L'OFFERTA</b>"
    )
    pulsante = InlineKeyboardMarkup([[InlineKeyboardButton("🛒 ACQUISTA ORA", url=link)]])
    bot = Bot(token=TOKEN)
    try:
        file = await bot.get_file(immagine)
        image_bytes = bytes(await file.download_as_bytearray())
        grafica = crea_grafica(nome, prezzo, sconto, image_bytes)
        await bot.send_photo(chat_id=canale, photo=grafica, caption=messaggio, parse_mode="HTML", reply_markup=pulsante)
        database = carica_utenti()
        for user_id in database["utenti"]:
            try:
                grafica.seek(0)
                await bot.send_photo(chat_id=user_id, photo=grafica, caption=messaggio, parse_mode="HTML", reply_markup=pulsante)
            except Exception as errore:
                print(f"⚠️ Impossibile inviare a {user_id}: {errore}")
    finally:
        await bot.shutdown()


async def offerta(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Non sei autorizzato a usare questo comando.")
        return
    if not update.message.photo:
        await update.message.reply_text("📸 Invia /offerta come didascalia di una foto.\n\n/offerta PS5 648 10 https://amzn.eu/...")
        return
    parti = (update.message.caption or "").split(maxsplit=4)
    if len(parti) != 5 or parti[0] != "/offerta":
        await update.message.reply_text("❌ Usa: /offerta NOME PREZZO SCONTO LINK")
        return
    _, nome, prezzo_testo, sconto_testo, link = parti
    try:
        prezzo = float(prezzo_testo.replace(",", "."))
        sconto = float(sconto_testo.replace(",", "."))
    except ValueError:
        await update.message.reply_text("❌ Prezzo o sconto non validi.")
        return
    if prezzo <= 0 or not 0 <= sconto <= 100:
        await update.message.reply_text("❌ Controlla prezzo e sconto.")
        return
    try:
        await pubblica_offerta(nome, prezzo, sconto, link, update.message.photo[-1].file_id)
        await update.message.reply_text("✅ OFFERTA PUBBLICATA!\n\n🎨 Grafica automatica: OK\n📢 Canale: OK\n🛒 Pulsante: OK\n🔔 Notifiche: OK")
    except Exception as errore:
        print(f"❌ ERRORE /offerta: {errore}")
        await update.message.reply_text("❌ Errore durante la pubblicazione. Controlla i log.")


async def id_utente(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"🆔 Il tuo Telegram ID è:\n\n<code>{update.effective_user.id}</code>", parse_mode="HTML")


async def main():
    if not TOKEN:
        raise RuntimeError("BOT_TOKEN non configurato nelle variabili d'ambiente di Railway.")

    application = Application.builder().token(TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("stop", stop))
    application.add_handler(CommandHandler("offerta", offerta))
    application.add_handler(CommandHandler("id", id_utente))

    port = int(os.getenv("PORT", "8080"))
    public_domain = os.getenv("RAILWAY_PUBLIC_DOMAIN", "dealgamingitalia-production.up.railway.app")
    webhook_path = f"webhook/{TOKEN}"
    webhook_url = f"https://{public_domain}/{webhook_path}"

    print("================================")
    print("🤖 DealGaming Bot ONLINE!")
    print("🌐 Modalità webhook attiva!")
    print("🎨 Grafica automatica attiva!")
    print("🎮 DealGaming Italia")
    print("🛍️ SuperDeal Italia")
    print("================================")

    await application.initialize()
    await application.start()
    await application.updater.start_webhook(
        listen="0.0.0.0",
        port=port,
        url_path=webhook_path,
        webhook_url=webhook_url,
        drop_pending_updates=True,
        allowed_updates=Update.ALL_TYPES,
    )

    try:
        while True:
            await asyncio.sleep(3600)
    finally:
        await application.updater.stop()
        await application.stop()
        await application.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
