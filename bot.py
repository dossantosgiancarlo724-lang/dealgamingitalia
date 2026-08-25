import asyncio
import json
import os
from io import BytesIO
from pathlib import Path

import requests
from PIL import Image, ImageDraw, ImageFont
from telegram import Bot, Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

TOKEN = os.getenv("TOKEN") or os.getenv("BOT_TOKEN") or ""
CHANNEL_GAMING = "@DealGamingItalia"
CHANNEL_GENERAL = "@SuperDealItalia"
ADMIN_ID = 8816533518

# Motore automatico Amazon/Keepa
KEEPA_API_KEY = os.getenv("KEEPA_API_KEY", "").strip()
AMAZON_TAG = os.getenv("AMAZON_TAG", "").strip()
AUTO_DEALS = os.getenv("AUTO_DEALS", "true").lower() == "true"
AUTO_DEAL_MIN_DISCOUNT = float(os.getenv("AUTO_DEAL_MIN_DISCOUNT", "35"))
AUTO_DEAL_INTERVAL = int(os.getenv("AUTO_DEAL_INTERVAL", "900"))

PUBLISHED_FILE = "offerte_pubblicate.json"

PAROLE_GAMING = [
    "playstation", "ps5", "ps4", "ps3", "xbox", "nintendo", "switch", "switch 2",
    "steam deck", "rog ally", "gaming", "videogioco", "videogiochi", "gpu", "rtx",
    "radeon", "scheda video", "monitor gaming", "mouse gaming", "tastiera gaming",
    "cuffie gaming", "controller", "dual sense", "manette"
]


def e_gaming(nome):
    return any(p in nome.lower() for p in PAROLE_GAMING)


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
        card.paste(product, ((920 - product.width) // 2, (650 - product.height) // 2))
        canvas.paste(card, (80, 225))
        draw.rounded_rectangle((80, 225, 1000, 875), 28, outline="#d1d5db", width=3)
    except Exception:
        draw.rounded_rectangle((80, 225, 1000, 875), 28, fill="white", outline="#d1d5db", width=3)

    draw.rounded_rectangle((790, 255, 965, 345), 24, fill="#dc2626")
    draw.text((815, 275), f"-{sconto:.0f}%", font=get_font(48, True), fill="white")
    draw.text((80, 925), nome[:42], font=get_font(40, True), fill="#111827")
    draw.text((80, 995), "PREZZO DELL'OFFERTA", font=get_font(24, True), fill="#6b7280")
    draw.text((80, 1020), f"{prezzo:.2f} €", font=get_font(72, True), fill="#16a34a")
    draw.text((80, 1115), f"Risparmio indicativo: {prezzo * sconto / 100:.2f} €", font=get_font(28, True), fill="#374151")
    draw.rounded_rectangle((80, 1180, 1000, 1275), 24, fill="#111827")
    draw.text((260, 1204), "ACQUISTA ORA", font=get_font(38, True), fill="white")

    output = BytesIO()
    output.name = "offerta.png"
    canvas.save(output, "PNG", optimize=True)
    output.seek(0)
    return output


def carica_pubblicate():
    if not os.path.exists(PUBLISHED_FILE):
        return {}
    try:
        with open(PUBLISHED_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def salva_pubblicate(data):
    with open(PUBLISHED_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def affiliate_url(asin):
    return f"https://www.amazon.it/dp/{asin}/?tag={AMAZON_TAG}"


def keepa_deals_sync():
    query = {
        "page": 0,
        "domainId": 8,
        "priceTypes": [0],
        "dateRange": 0,
        "isRangeEnabled": True,
        "currentRange": [500, 500000],
        "deltaPercentRange": [int(AUTO_DEAL_MIN_DISCOUNT), 100],
        "minRating": 35,
        "isLowest90": True,
        "mustHaveAmazonOffer": True,
        "filterErotic": True,
        "singleVariation": True,
        "sortType": 4,
    }
    response = requests.post(
        "https://api.keepa.com/deal",
        params={"key": KEEPA_API_KEY},
        json=query,
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def decode_image_name(image_codes):
    if not image_codes:
        return ""
    try:
        return "".join(chr(int(x)) for x in image_codes)
    except Exception:
        return ""


def download_product_image_sync(image_name):
    if not image_name:
        return None
    urls = [
        f"https://images-na.ssl-images-amazon.com/images/I/{image_name}",
        f"https://m.media-amazon.com/images/I/{image_name}",
    ]
    for url in urls:
        try:
            r = requests.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
            if r.ok and r.content:
                return r.content
        except Exception:
            continue
    return None


def extract_deal_values(deal):
    current_raw = deal.get("current", [None])[0]
    if current_raw is None or current_raw < 0:
        return None
    price = current_raw / 100

    discount = None
    delta_percent = deal.get("deltaPercent") or []
    try:
        value = delta_percent[0][0]
        if value is not None and value >= 0:
            discount = float(value)
    except (IndexError, TypeError):
        pass

    if not discount or discount < AUTO_DEAL_MIN_DISCOUNT:
        return None
    return price, discount


async def pubblica_offerta(nome, prezzo, sconto, link, image_bytes):
    channel = CHANNEL_GAMING if e_gaming(nome) else CHANNEL_GENERAL
    category = "🎮 GAMING" if e_gaming(nome) else "🛍️ SUPER DEAL"
    risparmio = prezzo * sconto / 100
    caption = (
        "🔥 <b>OFFERTA DA NON PERDERE!</b> 🔥\n\n"
        f"{category}\n\n"
        f"📦 <b>{nome}</b>\n\n"
        f"💰 <b>{prezzo:.2f} €</b>\n"
        f"📉 <b>-{sconto:.0f}%</b> di sconto\n"
        f"💸 Risparmi circa <b>{risparmio:.2f} €</b>\n\n"
        "🟢 <b>OFFERTA ATTIVA</b>\n\n"
        "⚡ Controllala subito: il prezzo può cambiare in qualsiasi momento.\n\n"
        "👇 <b>VEDI L'OFFERTA</b>\n\n"
        "<i>As an Amazon Associate I earn from qualifying purchases.</i>"
    )
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("🛒 ACQUISTA ORA", url=link)]])
    bot = Bot(TOKEN)
    try:
        graphic = crea_grafica(nome, prezzo, sconto, image_bytes)
        await bot.send_photo(
            chat_id=channel,
            photo=graphic,
            caption=caption,
            parse_mode="HTML",
            reply_markup=keyboard,
        )
    finally:
        await bot.shutdown()


async def automatic_deal_once():
    if not AUTO_DEALS:
        return
    if not KEEPA_API_KEY or not AMAZON_TAG:
        print("ℹ️ AUTO DEALS in attesa: configura KEEPA_API_KEY e AMAZON_TAG su Railway.", flush=True)
        return

    try:
        data = await asyncio.to_thread(keepa_deals_sync)
        deals = (data.get("deals") or {}).get("dr") or []
        published = carica_pubblicate()

        # Conserva solo gli ultimi 7 giorni nel registro locale.
        now = int(asyncio.get_running_loop().time())
        published = {k: v for k, v in published.items() if isinstance(v, int) and now - v < 7 * 86400}

        sent = 0
        for deal in deals:
            if sent >= 2:
                break
            asin = deal.get("asin")
            title = (deal.get("title") or "").strip()
            if not asin or not title or asin in published:
                continue

            values = extract_deal_values(deal)
            if not values:
                continue
            price, discount = values

            image_name = decode_image_name(deal.get("image"))
            image_bytes = await asyncio.to_thread(download_product_image_sync, image_name)
            if not image_bytes:
                print(f"⚠️ Immagine non disponibile per {asin}: salto l'offerta.", flush=True)
                continue

            link = affiliate_url(asin)
            await pubblica_offerta(title, price, discount, link, image_bytes)
            published[asin] = now
            salva_pubblicate(published)
            sent += 1
            print(f"🔥 OFFERTA AUTOMATICA PUBBLICATA: {title} | -{discount:.0f}% | {price:.2f}€", flush=True)

    except Exception as exc:
        print(f"❌ AUTO DEAL ERROR: {exc}", flush=True)


async def automatic_deal_loop():
    print("🔎 Motore offerte automatico avviato.", flush=True)
    while True:
        await automatic_deal_once()
        await asyncio.sleep(AUTO_DEAL_INTERVAL)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Benvenuto in DealGaming Italia!\n\n"
        "🔥 Le migliori occasioni vengono pubblicate direttamente nei nostri canali.\n\n"
        "🎮 @DealGamingItalia\n"
        "🛍️ @SuperDealItalia\n\n"
        "Il sistema automatico sta lavorando 24/7."
    )


async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("ℹ️ Il bot non invia notifiche private. Le offerte vengono pubblicate direttamente nei canali.")


async def ricevi_foto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    if not update.message.photo:
        return
    context.user_data["offerta_photo_id"] = update.message.photo[-1].file_id
    await update.message.reply_text(
        "🖼️ Foto ricevuta!\n\n"
        "Ora invia:\n"
        "/offerta NOME PREZZO SCONTO LINK"
    )


async def offerta(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Non sei autorizzato.")
        return

    photo_id = update.message.photo[-1].file_id if update.message.photo else context.user_data.get("offerta_photo_id")
    if not photo_id:
        await update.message.reply_text("📸 Prima inviami la foto del prodotto.")
        return

    command_text = update.message.caption or update.message.text or ""
    parts = command_text.split(maxsplit=4)
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

    bot = Bot(TOKEN)
    try:
        file = await bot.get_file(photo_id)
        image_bytes = bytes(await file.download_as_bytearray())
    finally:
        await bot.shutdown()

    try:
        await pubblica_offerta(name, price, discount, link, image_bytes)
        context.user_data.pop("offerta_photo_id", None)
        await update.message.reply_text("✅ OFFERTA PUBBLICATA NEL CANALE!")
    except Exception as exc:
        print(f"❌ ERRORE /offerta: {exc}", flush=True)
        await update.message.reply_text("❌ Errore durante la pubblicazione. Controlla i log.")


async def id_utente(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"🆔 Il tuo Telegram ID è:\n\n<code>{update.effective_user.id}</code>",
        parse_mode="HTML",
    )


async def main():
    if not TOKEN:
        raise RuntimeError("Token non configurato: imposta TOKEN o BOT_TOKEN in Railway.")

    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stop", stop))
    app.add_handler(CommandHandler("offerta", offerta))
    app.add_handler(CommandHandler("id", id_utente))
    app.add_handler(MessageHandler(filters.PHOTO, ricevi_foto))

    port = int(os.getenv("PORT", "8080"))
    domain = os.getenv("RAILWAY_PUBLIC_DOMAIN") or "dealgamingitalia-production.up.railway.app"
    path = "telegram-webhook"
    url = f"https://{domain}/{path}"

    print("================================", flush=True)
    print("🤖 DealGaming Bot ONLINE!", flush=True)
    print("🌐 WEBHOOK MODE", flush=True)
    print("📢 SOLO PUBBLICAZIONE NEI CANALI", flush=True)
    print("🔎 RICERCA OFFERTE AUTOMATICA: ATTIVA", flush=True)
    print(f"🎯 SOGLIA SCONTO: {AUTO_DEAL_MIN_DISCOUNT:.0f}%", flush=True)
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

    auto_task = asyncio.create_task(automatic_deal_loop())
    try:
        while True:
            await asyncio.sleep(3600)
    finally:
        auto_task.cancel()
        await app.updater.stop()
        await app.stop()
        await app.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
