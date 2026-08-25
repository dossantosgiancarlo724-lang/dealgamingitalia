import asyncio
import re
from urllib.parse import urljoin

import feedparser
import requests
from bs4 import BeautifulSoup

import bot

RSS_INDEX = "https://www.tomshw.it/feed-rss"


def _discover_feed_urls():
    """Discover the official RSS feed links published by Tom's Hardware."""
    urls = {RSS_INDEX}
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
            label = anchor.get_text(" ", strip=True).lower()
            low = href.lower()
            # Keep only links that look like actual feeds, not normal articles/pages.
            if href.startswith("http") and (
                "rss" in low or "feed" in low or "xml" in low or "rss" in label or "offerte" in label
            ):
                if href.rstrip("/") != RSS_INDEX.rstrip("/"):
                    urls.add(href)
    except Exception as exc:
        print(f"⚠️ Impossibile scoprire i feed RSS: {exc}", flush=True)
    return sorted(urls)


def _feed_entries():
    """Read all discovered official feeds and remove duplicate entries."""
    feeds = _discover_feed_urls()
    combined = {}
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
    print(f"🔎 Feed scoperti: {len(feeds)} | Feed con contenuti: {working} | Offerte candidate: {len(combined)}", flush=True)
    return list(combined.values())


def _deal_score(entry):
    title = entry.get("title", "")
    summary = BeautifulSoup(entry.get("summary", ""), "html.parser").get_text(" ")
    text = f"{title} {summary}"
    discount = bot.extract_discount(text)
    score = min(60, discount * 1.5)

    strong_terms = [
        "minimo storico", "minimo di sempre", "mai costato così poco",
        "prezzo più basso", "super offerta", "affare", "da non perdere",
    ]
    medium_terms = ["offerta", "sconto", "scende", "ribasso", "in meno"]
    low = text.lower()
    if any(term in low for term in strong_terms):
        score += 25
    elif any(term in low for term in medium_terms):
        score += 15

    if bot.e_gaming(text):
        score += 10

    price = bot.extract_price(text)
    if price is not None and price <= 100:
        score += 5

    return min(100, round(score)), discount


def _is_good_deal(entry):
    score, discount = _deal_score(entry)
    # Keep the existing 30% minimum, but require a meaningful overall score.
    good = discount >= bot.MIN_DISCOUNT and score >= 60
    if good:
        print(f"⭐ DEAL SCORE {score}/100 | -{discount}% | {entry.get('title', 'Offerta')}", flush=True)
    return good


async def _automatic_once():
    if not bot.AUTO_DEALS:
        return
    seen = bot.load_seen()
    entries = list(reversed(_feed_entries()))
    published = 0
    for entry in entries:
        uid = entry.get("id") or entry.get("link")
        if not uid or uid in seen or not _is_good_deal(entry):
            continue
        try:
            if await bot.publish_rss_deal(entry):
                seen[uid] = True
                published += 1
                bot.save_seen(seen)
                print(f"🔥 RSS DEAL PUBBLICATO: {entry.get('title')}", flush=True)
                if published >= 2:
                    break
        except Exception as exc:
            print(f"❌ RSS DEAL ERROR: {exc}", flush=True)
    if len(seen) > 1000:
        bot.save_seen({k: True for k in list(seen)[-500:]})


# Replace only the discovery/filter step; all Telegram publishing, Amazon tagging,
# graphics, webhook handling and admin commands remain in bot.py.
bot.get_feed_entries = _feed_entries
bot.article_is_deal = _is_good_deal
bot.automatic_rss_once = _automatic_once

if __name__ == "__main__":
    asyncio.run(bot.main())
