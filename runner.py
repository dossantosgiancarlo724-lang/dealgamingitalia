import asyncio
from urllib.parse import urljoin

import feedparser
import requests
from bs4 import BeautifulSoup

import bot

RSS_INDEX = "https://www.tomshw.it/feed-rss"
OFFERS_PAGE = "https://www.tomshw.it/argomenti/offerte"


def _discover_feed_urls():
    """Discover the official RSS feeds listed by Tom's Hardware."""
    urls = set()
    try:
        response = requests.get(
            RSS_INDEX,
            timeout=20,
            headers={"User-Agent": "Mozilla/5.0 (compatible; DealGamingItalia/1.0)"},
        )
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        for anchor in soup.find_all("a", href=True):
            href = urljoin(RSS_INDEX, anchor["href"])
            if href.startswith("http") and ("rss" in href.lower() or "feed" in href.lower() or "xml" in href.lower()):
                urls.add(href)
    except Exception as exc:
        print(f"⚠️ Scoperta feed RSS fallita: {exc}", flush=True)
    return sorted(urls)


def _entries_from_offers_page():
    """Read current offer cards from Tom's official offers page as a fallback/second source."""
    entries = []
    try:
        response = requests.get(
            OFFERS_PAGE,
            timeout=20,
            headers={"User-Agent": "Mozilla/5.0 (compatible; DealGamingItalia/1.0)"},
        )
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        seen = set()
        for a in soup.find_all("a", href=True):
            href = urljoin(OFFERS_PAGE, a["href"])
            title = a.get_text(" ", strip=True)
            if not title or "tomshw.it" not in href or len(title) < 12:
                continue
            if href in seen:
                continue
            # Only keep links that look like actual articles, not category/navigation links.
            if href.rstrip("/") in {OFFERS_PAGE.rstrip("/"), RSS_INDEX.rstrip("/")}:
                continue
            low = title.lower()
            if not any(token in low for token in ["€", "%", "offerta", "minimo storico", "meno", "scende", "scont", "prezzo", "affare", "costata"]):
                continue
            seen.add(href)
            entries.append({"id": href, "link": href, "title": title, "summary": title})
    except Exception as exc:
        print(f"⚠️ Pagina offerte non raggiungibile: {exc}", flush=True)
    return entries


def _feed_entries():
    """Combine official RSS entries with the live offers page and remove duplicates."""
    combined = {}
    feeds = _discover_feed_urls()
    working = 0

    for url in feeds:
        try:
            parsed = feedparser.parse(url)
            entries = parsed.entries or []
            if entries:
                working += 1
                for entry in entries:
                    key = entry.get("id") or entry.get("link") or entry.get("title")
                    if key:
                        combined[key] = entry
        except Exception as exc:
            print(f"⚠️ Feed saltato {url}: {exc}", flush=True)

    page_entries = _entries_from_offers_page()
    for entry in page_entries:
        combined[entry["id"]] = entry

    print(
        f"🔎 CICLO OFFERTE | feed={len(feeds)} attivi={working} | pagina={len(page_entries)} | candidate={len(combined)}",
        flush=True,
    )
    return list(combined.values())


def _deal_score(entry):
    title = entry.get("title", "")
    summary = BeautifulSoup(entry.get("summary", ""), "html.parser").get_text(" ")
    text = f"{title} {summary}"
    discount = bot.extract_discount(text)
    score = min(65, discount * 1.6)

    strong_terms = [
        "minimo storico", "minimo di sempre", "mai costata così poco",
        "mai costato così poco", "prezzo più basso", "super offerta", "affare",
        "da non perdere", "cala ancora", "prezzo record",
    ]
    medium_terms = ["offerta", "sconto", "scende", "ribasso", "in meno", "scontato", "prezzo"]
    low = text.lower()
    if any(term in low for term in strong_terms):
        score += 25
    elif any(term in low for term in medium_terms):
        score += 12

    if bot.e_gaming(text):
        score += 10

    price = bot.extract_price(text)
    if price is not None and price <= 100:
        score += 5

    return min(100, round(score)), discount


def _is_good_deal(entry):
    score, discount = _deal_score(entry)
    # Accept either a strong percentage or a strong editorial signal such as a historical low.
    text = f"{entry.get('title', '')} {entry.get('summary', '')}".lower()
    strong_signal = any(term in text for term in ["minimo storico", "minimo di sempre", "mai costata così poco", "mai costato così poco", "prezzo più basso"])
    good = (discount >= 25 and score >= 50) or (strong_signal and score >= 45)
    if good:
        print(f"⭐ CANDIDATA | score={score}/100 | sconto={discount}% | {entry.get('title', 'Offerta')}", flush=True)
    return good


async def _automatic_once():
    if not bot.AUTO_DEALS:
        print("⏸️ AUTO_DEALS disattivato.", flush=True)
        return

    seen = bot.load_seen()
    entries = list(reversed(_feed_entries()))
    checked = 0
    published = 0

    for entry in entries:
        uid = entry.get("id") or entry.get("link")
        if not uid or uid in seen or not _is_good_deal(entry):
            continue
        checked += 1
        try:
            if await bot.publish_rss_deal(entry):
                seen[uid] = True
                published += 1
                bot.save_seen(seen)
                print(f"🔥 PUBBLICATA | {entry.get('title')}", flush=True)
                if published >= 3:
                    break
        except Exception as exc:
            print(f"❌ ERRORE PUBBLICAZIONE | {entry.get('title')}: {exc}", flush=True)

    print(f"📊 CICLO FINITO | candidate_verificate={checked} | pubblicate={published}", flush=True)
    if len(seen) > 1000:
        bot.save_seen({k: True for k in list(seen)[-500:]})


bot.get_feed_entries = _feed_entries
bot.article_is_deal = _is_good_deal
bot.automatic_rss_once = _automatic_once

if __name__ == "__main__":
    asyncio.run(bot.main())
