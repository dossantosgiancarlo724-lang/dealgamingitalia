import asyncio
import html
import json
import os
import re
from io import BytesIO
from urllib.parse import urljoin, urlparse, parse_qsl, urlencode, urlunparse

import feedparser
import requests
from bs4 import BeautifulSoup
from PIL import Image, ImageDraw, ImageFont
from telegram import Bot, Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

TOKEN = os.getenv("TOKEN") or os.getenv("BOT_TOKEN") or ""
AMAZON_TAG = os.getenv("AMAZON_TAG", "").strip()
CHANNEL_GAMING = "@DealGamingItalia"
CHANNEL_GENERAL = "@SuperDealItalia"
ADMIN_ID = 8816533518
RSS_URL = "https://www.tomshw.it/feed/offerte"
DEALS_PAGE_URL = "https://www.tomshw.it/offerte"
AUTO_DEALS = os.getenv("AUTO_DEALS", "true").lower() == "true"
AUTO_DEAL_INTERVAL = int(os.getenv("AUTO_DEAL_INTERVAL", "900"))
MIN_DISCOUNT = float(os.getenv("AUTO_DEAL_MIN_DISCOUNT", "30"))
SEEN_FILE = "rss_visti.json"
ACTIVE_DEALS_FILE = "offerte_attive.json"

PAROLE_GAMING = ["playstation", "ps5", "ps4", "ps3", "xbox", "nintendo", "switch", "switch 2", "steam deck", "rog ally", "gaming", "videogioco", "videogiochi", "gpu", "rtx", "radeon", "scheda video", "monitor gaming", "mouse gaming", "tastiera gaming", "cuffie gaming", "controller", "dual sense", "manette", "thrustmaster", "logitech"]


def e_gaming(text):
    return any(word in (text or "").lower() for word in PAROLE_GAMING)


def font(size, bold=False):
    path = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    return ImageFont.truetype(path, size) if os.path.exists(path) else ImageFont.load_default()


def crea_grafica(titolo, prezzo, sconto, image_bytes=None, gaming=False):
    W, H = 1080, 1350
    img = Image.new("RGB", (W, H), "#f5f5f5")
    d = ImageDraw.Draw(img)
    brand = "DEAL GAMING ITALIA" if gaming else "SUPER DEAL ITALIA"
    d.rounded_rectangle((35, 35, 1045, 185), 30, fill="#101828")
    d.text((70, 55), brand, font=font(42, True), fill="white")
    d.text((70, 115), "🔥 SUPER OFFERTA", font=font(30, True), fill="#fbbf24")
    if image_bytes:
        try:
            product = Image.open(BytesIO(image_bytes)).convert("RGB")
            product.thumbnail((860, 590), Image.Resampling.LANCZOS)
            card = Image.new("RGB", (920, 640), "white")
            card.paste(product, ((920-product.width)//2, (640-product.height)//2))
            img.paste(card, (80, 220))
            d.rounded_rectangle((80, 220, 1000, 860), 28, outline="#d0d5dd", width=3)
        except Exception:
            pass
    else:
        d.rounded_rectangle((80, 220, 1000, 860), 28, fill="white", outline="#d0d5dd", width=3)
        d.text((330, 505), "OFFERTA", font=font(65, True), fill="#101828")
    if sconto:
        d.rounded_rectangle((795, 250, 970, 345), 24, fill="#e12d39")
        d.text((820, 270), f"-{sconto:.0f}%", font=font(48, True), fill="white")
    d.text((80, 910), (titolo or "Offerta")[:45], font=font(38, True), fill="#101828")
    if prezzo is not None:
        d.text((80, 985), "ORA", font=font(24, True), fill="#667085")
        d.text((80, 1010), f"{prezzo:.2f} €", font=font(70, True), fill="#12b76a")
    d.rounded_rectangle((80, 1170, 1000, 1270), 24, fill="#101828")
    d.text((285, 1195), "🛒 VEDI L'OFFERTA", font=font(36, True), fill="white")
    out = BytesIO(); out.name = "deal.png"; img.save(out, "PNG", optimize=True); out.seek(0)
    return out


def load_seen():
    try:
        with open(SEEN_FILE, "r", encoding="utf-8") as f: return json.load(f)
    except Exception: return {}


def save_seen(data):
    with open(SEEN_FILE, "w", encoding="utf-8") as f: json.dump(data, f, indent=2)


def load_active_deals():
    try:
        with open(ACTIVE_DEALS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_active_deals(data):
    with open(ACTIVE_DEALS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def amazon_offer_is_ended(url):
    """Return True only for explicit Amazon unavailability messages."""
    try:
        response = requests.get(url, timeout=25, headers={"User-Agent": "Mozilla/5.0 (compatible; DealGamingItalia/1.2)"})
        response.raise_for_status()
        page_text = BeautifulSoup(response.text, "html.parser").get_text(" ", strip=True).lower()
        unavailable_markers = (
            "currently unavailable",
            "temporarily out of stock",
            "non disponibile per la consegna",
            "questo articolo non è al momento disponibile",
            "attualmente non disponibile",
        )
        return any(marker in page_text for marker in unavailable_markers)
    except Exception as exc:
        print(f"⚠️ CONTROLLO SCADENZA NON RIUSCITO: {type(exc).__name__}: {exc}", flush=True)
        return False


async def expire_finished_deals():
    active = load_active_deals()
    if not active:
        return
    bot = Bot(TOKEN)
    changed = 0
    try:
        for deal_id, deal in list(active.items()):
            if deal.get("status") != "active" or not deal.get("amazon_link"):
                continue
            if not await asyncio.to_thread(amazon_offer_is_ended, deal["amazon_link"]):
                continue
            expired_caption = (
                f"{deal.get('caption', '🔥 <b>SUPER OFFERTA</b>')}\n\n"
                "❌ <b>OFFERTA TERMINATA</b>\n"
                "<i>Il prodotto non risulta più disponibile al prezzo segnalato.</i>"
            )
            try:
                if deal.get("has_photo"):
                    await bot.edit_message_caption(
                        chat_id=deal["channel"], message_id=deal["message_id"],
                        caption=expired_caption, parse_mode="HTML", reply_markup=None,
                    )
                else:
                    await bot.edit_message_text(
                        chat_id=deal["channel"], message_id=deal["message_id"],
                        text=expired_caption, parse_mode="HTML", reply_markup=None,
                    )
                deal["status"] = "expired"
                deal["caption"] = expired_caption
                changed += 1
                print(f"❌ OFFERTA TERMINATA → messaggio {deal['message_id']}", flush=True)
            except Exception as exc:
                print(f"⚠️ AGGIORNAMENTO OFFERTA TERMINATA FALLITO: {type(exc).__name__}: {exc}", flush=True)
        if changed:
            save_active_deals(active)
    finally:
        await bot.shutdown()


def extract_discount(text):
    values = [int(x) for x in re.findall(r"(?:-|−)?\s*(\d{1,3})\s*%", text or "") if 0 <= int(x) <= 100]
    return max(values) if values else 0


def extract_prices(text):
    matches = re.findall(r"(?<!\d)(\d{1,5}(?:[.,]\d{1,2})?)\s*€", text or "")
    values = []
    for value in matches:
        try:
            values.append(float(value.replace(".", "").replace(",", ".")))
        except ValueError:
            pass
    return values


def extract_price(text):
    values = extract_prices(text)
    return values[-1] if values else None


def calculate_original_price(current_price, discount):
    if current_price is None or not discount or discount >= 100:
        return None
    return current_price / (1 - (discount / 100.0))


def format_eur(value):
    if value is None:
        return "n/d"
    return f"€{value:.2f}"


def build_deal_caption(title, current_price, discount, gaming):
    category = "🔥 <b>SUPER OFFERTA – GAMING</b>" if gaming else "🔥 <b>SUPER OFFERTA</b>"
    safe_title = html.escape(title or "Offerta")
    lines = [category, f"🎮 <b>{safe_title}</b>", "━━━━━━━━━━━━━━━━"]

    original_price = calculate_original_price(current_price, discount)
    if current_price is not None and original_price is not None:
        saved = max(0.0, original_price - current_price)
        lines.extend([
            f"💸 Prima: <s>{format_eur(original_price)}</s>",
            f"✅ Ora: <b>{format_eur(current_price)}</b>",
            f"📉 Sconto: <b>-{discount:.0f}%</b> (risparmi {format_eur(saved)})",
        ])
    elif current_price is not None:
        lines.append(f"✅ Ora: <b>{format_eur(current_price)}</b>")
        lines.append("📉 Sconto: <b>da verificare</b>")
    else:
        lines.append("💰 Prezzo: <b>da verificare</b>")

    lines.extend([
        "━━━━━━━━━━━━━━━━",
        "⏳ <i>Offerta valida fino a esaurimento scorte oppure fino alla fine dell'offerta.</i>",
    ])
    return "\n".join(lines)


def fetch_article(url):
    r = requests.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0 (compatible; DealGamingItalia/1.2)"})
    r.raise_for_status()
    return r.text


def make_affiliate_url(url):
    """Add the configured Amazon.it Associate tag without using a shortener."""
    if not AMAZON_TAG or not url:
        return None
    parsed = urlparse(url)
    host = parsed.netloc.lower().split(":")[0]
    if host not in {"amazon.it", "www.amazon.it", "smile.amazon.it"}:
        return None
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query["tag"] = AMAZON_TAG
    parsed = parsed._replace(netloc="www.amazon.it", query=urlencode(query))
    return urlunparse(parsed)


def find_amazon_product_link(article_url):
    """Find a direct Amazon.it product link in the source article, then tag it."""
    try:
        html_text = fetch_article(article_url)
        soup = BeautifulSoup(html_text, "html.parser")
        candidates = []
        for a in soup.find_all("a", href=True):
            absolute = urljoin(article_url, a["href"])
            tagged = make_affiliate_url(absolute)
            if tagged:
                score = 2 if "/dp/" in absolute.lower() or "/gp/product/" in absolute.lower() else 1
                candidates.append((score, tagged))
        if not candidates:
            return None
        candidates.sort(key=lambda x: x[0], reverse=True)
        return candidates[0][1]
    except Exception as exc:
        print(f"⚠️ Link Amazon non recuperato: {exc}", flush=True)
        return None


def get_image_from_html(html_text):
    try:
        soup = BeautifulSoup(html_text, "html.parser")
        meta = soup.find("meta", property="og:image")
        image_url = meta.get("content") if meta else None
        if image_url:
            ir = requests.get(image_url, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
            if ir.ok and ir.content:
                return ir.content
    except Exception as exc:
        print(f"⚠️ Immagine non recuperata: {exc}", flush=True)
    return None


def get_image_from_article(url):
    try:
        return get_image_from_html(fetch_article(url))
    except Exception as exc:
        print(f"⚠️ Immagine RSS non recuperata: {exc}", flush=True)
    return None


def get_feed_entries():
    try:
        response = requests.get(RSS_URL, timeout=25, headers={"User-Agent": "DealGamingItalia/1.2 (+RSS monitor)"})
        response.raise_for_status()
        parsed = feedparser.parse(response.content)
        if parsed.bozo:
            print(f"⚠️ RSS non perfettamente valido: {parsed.bozo_exception}", flush=True)
        return list(parsed.entries or [])
    except Exception as exc:
        print(f"❌ RSS FETCH ERROR: {type(exc).__name__}: {exc}", flush=True)
        return []


def get_offers_page_entries():
    try:
        html_text = fetch_article(DEALS_PAGE_URL)
        soup = BeautifulSoup(html_text, "html.parser")
        entries, seen_urls = [], set()
        for article in soup.select("article"):
            link = article.find("a", href=True)
            heading = article.find(["h1", "h2", "h3", "h4"])
            if not link:
                continue
            url = urljoin(DEALS_PAGE_URL, link["href"])
            title = (heading.get_text(" ", strip=True) if heading else link.get_text(" ", strip=True))
            text = article.get_text(" ", strip=True)
            if not title or url in seen_urls or "tomshw.it" not in urlparse(url).netloc:
                continue
            seen_urls.add(url)
            entries.append({"id": url, "link": url, "title": title, "summary": text})
        print(f"📄 PAGINA OFFERTE → articoli={len(entries)}", flush=True)
        return entries
    except Exception as exc:
        print(f"❌ PAGINA OFFERTE ERROR: {type(exc).__name__}: {exc}", flush=True)
        return []


def entry_text(entry):
    title = entry.get("title", "")
    summary = BeautifulSoup(entry.get("summary", ""), "html.parser").get_text(" ")
    return f"{title} {summary}"


def article_is_deal(entry):
    text = entry_text(entry)
    lowered = text.lower()
    return "offert" in lowered or extract_discount(text) >= MIN_DISCOUNT


async def publish_rss_deal(entry, amazon_link=None):
    title = entry.get("title", "Offerta")
    article_url = entry.get("link")
    summary = BeautifulSoup(entry.get("summary", ""), "html.parser").get_text(" ")
    text = f"{title} {summary}"
    discount = extract_discount(text)
    price = extract_price(text)
    if not article_url:
        return False

    if not AMAZON_TAG:
        print("⚠️ AMAZON_TAG non configurato: offerta automatica saltata.", flush=True)
        return False

    amazon_link = amazon_link or await asyncio.to_thread(find_amazon_product_link, article_url)
    if not amazon_link:
        print(f"ℹ️ Nessun link Amazon.it diretto trovato: {title}", flush=True)
        return False

    gaming = e_gaming(text)
    channel = CHANNEL_GAMING if gaming else CHANNEL_GENERAL
    image = await asyncio.to_thread(get_image_from_article, article_url)
    caption = build_deal_caption(title, price, discount, gaming)
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("🛒 ACQUISTA ORA →", url=amazon_link)]])
    bot = Bot(TOKEN)
    try:
        if image:
            message = await bot.send_photo(chat_id=channel, photo=image, caption=caption, parse_mode="HTML", reply_markup=keyboard)
            has_photo = True
        else:
            message = await bot.send_message(chat_id=channel, text=caption, parse_mode="HTML", reply_markup=keyboard, disable_web_page_preview=False)
            has_photo = False
        return {
            "channel": channel, "message_id": message.message_id, "amazon_link": amazon_link,
            "caption": caption, "has_photo": has_photo, "status": "active",
            "title": title, "current_price": price, "discount": discount,
        }
    finally:
        await bot.shutdown()


async def automatic_rss_once():
    if not AUTO_DEALS:
        print("⏸️ CICLO OFFERTE disattivato da AUTO_DEALS.", flush=True)
        return

    print("🔄 CICLO OFFERTE → avvio", flush=True)
    await expire_finished_deals()
    seen = load_seen()
    rss_entries = await asyncio.to_thread(get_feed_entries)
    page_entries = await asyncio.to_thread(get_offers_page_entries)

    all_entries, entry_urls = [], set()
    for entry in list(reversed(rss_entries)) + list(reversed(page_entries)):
        uid = entry.get("id") or entry.get("link")
        if uid and uid not in entry_urls:
            entry_urls.add(uid)
            all_entries.append(entry)

    candidates = [entry for entry in all_entries
                  if (entry.get("id") or entry.get("link")) not in seen and article_is_deal(entry)]
    print(f"🔎 CICLO OFFERTE → feed={len(rss_entries)} pagina={len(page_entries)} candidate={len(candidates)}", flush=True)

    verified = 0
    published = 0
    for entry in candidates[:30]:
        uid = entry.get("id") or entry.get("link")
        try:
            amazon_link = await asyncio.to_thread(find_amazon_product_link, entry.get("link"))
            if not amazon_link:
                print(f"⏭️ OFFERTA SCARTATA → link Amazon assente: {entry.get('title', '')[:90]}", flush=True)
                continue
            verified += 1
            print(f"✅ OFFERTA VERIFICATA → {entry.get('title', '')[:90]}", flush=True)
            published_deal = await publish_rss_deal(entry, amazon_link=amazon_link)
            if published_deal:
                seen[uid] = True
                active_deals = load_active_deals()
                active_deals[uid] = published_deal
                save_seen(seen)
                save_active_deals(active_deals)
                published += 1
                print(f"📢 OFFERTA PUBBLICATA → {entry.get('title', '')[:90]}", flush=True)
                if published >= 2:
                    break
        except Exception as exc:
            print(f"❌ OFFERTA ERROR → {type(exc).__name__}: {exc}", flush=True)

    print(f"📊 CICLO OFFERTE → candidate={len(candidates)} verificate={verified} pubblicate={published}", flush=True)
    if len(seen) > 1000:
        save_seen({k: True for k in list(seen)[-500:]})


async def automatic_loop():
    print(f"🔎 Motore offerte avviato (intervallo {AUTO_DEAL_INTERVAL}s).", flush=True)
    while True:
        try:
            await automatic_rss_once()
        except Exception as exc:
            print(f"❌ CICLO OFFERTE FATALE → {type(exc).__name__}: {exc}", flush=True)
        await asyncio.sleep(AUTO_DEAL_INTERVAL)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 Benvenuto!\n\n🔥 Le offerte vengono pubblicate automaticamente nei nostri canali.\n\n🎮 @DealGamingItalia\n🛍️ @SuperDealItalia")


async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("ℹ️ Il bot non invia notifiche private.")


async def ricevi_foto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    context.user_data["offerta_photo_id"] = update.message.photo[-1].file_id
    await update.message.reply_text("🖼️ Foto ricevuta! Ora invia /offerta NOME PREZZO SCONTO LINK")


async def offerta(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Non sei autorizzato.")
        return
    photo_id = update.message.photo[-1].file_id if update.message.photo else context.user_data.get("offerta_photo_id")
    if not photo_id:
        await update.message.reply_text("📸 Prima inviami la foto del prodotto.")
        return
    parts = (update.message.caption or update.message.text or "").split(maxsplit=4)
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
    bot = Bot(TOKEN)
    try:
        f = await bot.get_file(photo_id)
        image_bytes = bytes(await f.download_as_bytearray())
    finally:
        await bot.shutdown()
    gaming = e_gaming(name)
    graphic = crea_grafica(name, price, discount, image_bytes, gaming=gaming)
    caption = build_deal_caption(name, price, discount, gaming)
    bot = Bot(TOKEN)
    try:
        channel = CHANNEL_GAMING if gaming else CHANNEL_GENERAL
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("🛒 ACQUISTA ORA →", url=link)]])
        message = await bot.send_photo(chat_id=channel, photo=graphic, caption=caption, parse_mode="HTML", reply_markup=keyboard)
        active_deals = load_active_deals()
        active_deals[f"manual:{message.message_id}"] = {
            "channel": channel, "message_id": message.message_id, "amazon_link": link,
            "caption": caption, "has_photo": True, "status": "active",
            "title": name, "current_price": price, "discount": discount,
        }
        save_active_deals(active_deals)
    finally:
        await bot.shutdown()
    context.user_data.pop("offerta_photo_id", None)
    await update.message.reply_text("✅ OFFERTA PUBBLICATA NEL CANALE!")


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
    app.add_handler(MessageHandler(filters.PHOTO, ricevi_foto))
    port = int(os.getenv("PORT", "8080"))
    domain = os.getenv("RAILWAY_PUBLIC_DOMAIN") or "dealgamingitalia-production.up.railway.app"
    path = "telegram-webhook"
    url = f"https://{domain}/{path}"
    print("================================", flush=True)
    print("🤖 DealGaming Bot ONLINE!", flush=True)
    print("🌐 WEBHOOK MODE", flush=True)
    print("📢 SOLO PUBBLICAZIONE NEI CANALI", flush=True)
    print("🔎 RICERCA OFFERTE RSS: ATTIVA", flush=True)
    print(f"🔗 AMAZON AFFILIAZIONE: {'ATTIVA' if AMAZON_TAG else 'NON CONFIGURATA'}", flush=True)
    print("================================", flush=True)
    await app.initialize()
    await app.start()
    await app.updater.start_webhook(listen="0.0.0.0", port=port, url_path=path, webhook_url=url, drop_pending_updates=True, allowed_updates=Update.ALL_TYPES)
    task = asyncio.create_task(automatic_loop())
    try:
        while True:
            await asyncio.sleep(3600)
    finally:
        task.cancel()
        await app.updater.stop()
        await app.stop()
        await app.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
