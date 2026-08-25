import asyncio
import json
import os

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
    nome = nome.lower()
    return any(parola in nome for parola in PAROLE_GAMING)


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

    await update.message.reply_text(
        "🔕 Avvisi disattivati.\n\n"
        "Puoi riattivarli in qualsiasi momento con /start."
    )


async def pubblica_offerta(nome, prezzo, sconto, link, immagine):
    if e_gaming(nome):
        canale = CHANNEL_GAMING
        categoria = "🎮 GAMING"
    else:
        canale = CHANNEL_GENERAL
        categoria = "🛍️ SUPER DEAL"

    risparmio = prezzo * sconto / 100
    messaggio = (
        "🔥 <b>OFFERTA DA NON PERDERE!</b> 🔥\n\n"
        f"{categoria}\n\n"
        f"📦 <b>{nome}</b>\n\n"
        f"💰 <b>{prezzo:.2f} €</b>\n"
        f"📉 <b>-{sconto:.0f}%</b> di sconto\n"
        f"💸 Risparmi circa <b>{risparmio:.2f} €</b>\n\n"
        "🟢 <b>OFFERTA ATTIVA</b>\n\n"
        "⚡ Se il prezzo ti interessa, controllalo subito: "
        "le offerte possono terminare in qualsiasi momento.\n\n"
        "👇 <b>VEDI L'OFFERTA</b>"
    )

    pulsante = InlineKeyboardMarkup([
        [InlineKeyboardButton("🛒 ACQUISTA ORA", url=link)]
    ])

    bot = Bot(token=TOKEN)
    try:
        await bot.send_photo(
            chat_id=canale,
            photo=immagine,
            caption=messaggio,
            parse_mode="HTML",
            reply_markup=pulsante,
        )

        database = carica_utenti()
        for user_id in database["utenti"]:
            try:
                await bot.send_photo(
                    chat_id=user_id,
                    photo=immagine,
                    caption=messaggio,
                    parse_mode="HTML",
                    reply_markup=pulsante,
                )
            except Exception as errore:
                print(f"⚠️ Impossibile inviare a {user_id}: {errore}")
    finally:
        await bot.shutdown()


async def offerta(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Non sei autorizzato a usare questo comando.")
        return

    if not update.message.photo:
        await update.message.reply_text(
            "📸 Devi inviare /offerta come DIDASCALIA di una foto.\n\n"
            "Esempio:\n/offerta PS5 648 10 https://amzn.eu/..."
        )
        return

    didascalia = update.message.caption or ""
    parti = didascalia.split(maxsplit=4)
    if len(parti) != 5 or parti[0] != "/offerta":
        await update.message.reply_text(
            "❌ Formato non corretto.\n\n"
            "Usa:\n/offerta NOME PREZZO SCONTO LINK"
        )
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

    immagine = update.message.photo[-1].file_id

    try:
        await pubblica_offerta(nome, prezzo, sconto, link, immagine)
        await update.message.reply_text(
            "✅ OFFERTA PUBBLICATA!\n\n"
            "🖼️ Immagine: OK\n"
            "📢 Canale: OK\n"
            "🛒 Pulsante: OK\n"
            "🔔 Notifiche: OK"
        )
    except Exception as errore:
        print(f"❌ ERRORE /offerta: {errore}")
        await update.message.reply_text("❌ Errore durante la pubblicazione. Controlla i log.")


async def id_utente(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"🆔 Il tuo Telegram ID è:\n\n<code>{update.effective_user.id}</code>",
        parse_mode="HTML",
    )


async def main():
    if not TOKEN:
        raise RuntimeError("BOT_TOKEN non configurato nelle variabili d'ambiente di Railway.")

    application = Application.builder().token(TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("stop", stop))
    application.add_handler(CommandHandler("offerta", offerta))
    application.add_handler(CommandHandler("id", id_utente))

    print("================================")
    print("🤖 DealGaming Bot ONLINE!")
    print("🔥 Sistema offerte attivo!")
    print("🖼️ Sistema immagini attivo!")
    print("🎮 DealGaming Italia")
    print("🛍️ SuperDeal Italia")
    print("================================")

    await application.initialize()
    await application.start()
    await application.updater.start_polling()

    try:
        while True:
            await asyncio.sleep(3600)
    finally:
        await application.updater.stop()
        await application.stop()
        await application.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
