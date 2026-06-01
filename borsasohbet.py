# -*- coding: utf-8 -*-
"""
borsasohbet_analist.py

BIST hisseleri için Telegram sohbet botu.
Bu sürümde ana geliştirme:
- Teknik / haber / global / temel verileri tek skor motorunda birleştirir.
- Finansal veri alınamazsa 0/6 yazmaz.
- Ham veri yerine kısa analist yorumu üretir.
- Kullanıcı sadece "THYAO", "Ford nasıl", "haberler ne diyor ASELS" gibi yazabilir.

Kurulum:
pip install python-telegram-bot==21.6 yfinance pandas requests beautifulsoup4 lxml html5lib feedparser numpy

Çalıştırma:
1) BOT_TOKEN alanına Telegram BotFather tokenini yaz.
2) python borsasohbet_analist.py
"""

import os
import re
import math
import json
import logging
import time
import sys
import asyncio
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from datetime import datetime

import numpy as np
import pandas as pd
import requests
from urllib.parse import quote
import yfinance as yf
import feedparser
from bs4 import BeautifulSoup

from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters


# =========================
# AYARLAR
# =========================

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()

DATA_DIR = Path(__file__).parent
PORTFOY_DOSYA = DATA_DIR / "portfoyler.json"
TAKIP_DOSYA = DATA_DIR / "takip_listeleri.json"

logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO
)


# =========================
# HİSSELER
# =========================

HISSE_ADLARI = {
    "türk hava yolları": "THYAO", "turk hava yollari": "THYAO", "thy": "THYAO",
    "pegasus": "PGSUS",
    "arçelik": "ARCLK", "arcelik": "ARCLK",
    "aselsan": "ASELS",
    "tüpraş": "TUPRS", "tupras": "TUPRS",
    "sasa": "SASA",
    "ereğli": "EREGL", "eregli": "EREGL",
    "kardemir": "KRDMD",
    "şişe": "SISE", "sise": "SISE", "şişecam": "SISE", "sisecam": "SISE",
    "garanti": "GARAN",
    "akbank": "AKBNK",
    "yapı kredi": "YKBNK", "yapi kredi": "YKBNK",
    "iş bankası": "ISCTR", "is bankasi": "ISCTR",
    "koç holding": "KCHOL", "koc holding": "KCHOL",
    "sabancı": "SAHOL", "sabanci": "SAHOL",
    "bim": "BIMAS",
    "migros": "MGROS",
    "ford": "FROTO", "ford otosan": "FROTO",
    "tofaş": "TOASO", "tofas": "TOASO",
    "petkim": "PETKM",
    "turkcell": "TCELL",
    "türk telekom": "TTKOM", "turk telekom": "TTKOM",
    "hektas": "HEKTS", "hektaş": "HEKTS",
}

BIST_KODLARI = {
    "AEFES", "AGHOL", "AKBNK", "AKCNS", "AKFGY", "AKSA", "AKSEN", "ALARK", "ALBRK",
    "ALFAS", "ARCLK", "ASELS", "ASTOR", "BIMAS", "BRSAN", "BRYAT", "CCOLA", "CIMSA",
    "CWENE", "DOAS", "DOHOL", "ECILC", "EGEEN", "EKGYO", "ENJSA", "ENKAI", "EREGL",
    "EUPWR", "FROTO", "GARAN", "GESAN", "GUBRF", "HALKB", "HEKTS", "ISCTR", "ISMEN",
    "KCHOL", "KONTR", "KOZAA", "KOZAL", "KRDMD", "MAVI", "MGROS", "ODAS", "OYAKC",
    "PETKM", "PGSUS", "SAHOL", "SASA", "SISE", "SKBNK", "SMRTG", "TAVHL", "TCELL",
    "THYAO", "TKFEN", "TOASO", "TSKB", "TTKOM", "TUPRS", "ULKER", "VAKBN", "VESTL",
    "YKBNK", "ZOREN"
}

SEKTOR_HARITASI = {
    "THYAO": "Havacılık", "PGSUS": "Havacılık", "TAVHL": "Havacılık",
    "GARAN": "Banka", "AKBNK": "Banka", "YKBNK": "Banka", "ISCTR": "Banka", "HALKB": "Banka", "VAKBN": "Banka",
    "ASELS": "Savunma",
    "EREGL": "Demir Çelik", "KRDMD": "Demir Çelik", "BRSAN": "Demir Çelik",
    "TUPRS": "Enerji/Petrol", "PETKM": "Enerji/Petrol",
    "ARCLK": "Beyaz Eşya", "VESTL": "Teknoloji/Beyaz Eşya",
    "BIMAS": "Perakende", "MGROS": "Perakende", "MAVI": "Perakende",
    "FROTO": "Otomotiv", "TOASO": "Otomotiv", "DOAS": "Otomotiv",
    "KCHOL": "Holding", "SAHOL": "Holding",
    "TCELL": "Telekom", "TTKOM": "Telekom",
    "SISE": "Cam/Sanayi", "SASA": "Kimya", "HEKTS": "Tarım/Kimya",
}


# =========================
# YARDIMCI
# =========================

def temizle_metin(text: str) -> str:
    return (text or "").lower().strip()


def tr_upper(s: str) -> str:
    return (s or "").upper().replace("İ", "I").replace("Ç", "C").replace("Ğ", "G").replace("Ö", "O").replace("Ş", "S").replace("Ü", "U")


def hisse_bul(metin: str):
    m = temizle_metin(metin)

    for ad, kod in HISSE_ADLARI.items():
        if ad in m:
            return kod

    komut_kelimeleri = {
        "SINYAL", "KAYDET", "GECMISI", "GEÇMİŞİ", "BASARI", "BAŞARI",
        "ORANI", "PERFORMANS", "HABER", "HABERLER", "NEDEN", "NIYE",
        "DUSUYOR", "DÜŞÜYOR", "YUKSELIYOR", "YÜKSELİYOR", "RISK",
        "ALARM", "ERKEN", "UYARI", "PIYASA", "PİYASA",
        "BES", "BIREYSEL", "BİREYSEL", "EMEKLILIK", "EMEKLİLİK",
        "FON", "FONLARI", "ONERI", "ÖNERI", "ÖNERİ", "YAPABILIRSIN",
        "YAPABİLİRSİN", "KOMUTLAR", "YARDIM"
    }

    words = re.findall(r"\b[A-Za-zÇĞİÖŞÜçğıöşü0-9]{3,10}\b", metin or "")
    for w in words:
        w = tr_upper(w).replace(".IS", "")
        if w in BIST_KODLARI:
            return w

    for w in words:
        w = tr_upper(w).replace(".IS", "")
        if w in komut_kelimeleri:
            continue
        if re.fullmatch(r"[A-Z0-9]{4,6}", w):
            return w

    return None


def fmt(x):
    if x is None:
        return "-"
    try:
        if isinstance(x, float) and math.isnan(x):
            return "-"
        if isinstance(x, (float, int, np.floating, np.integer)):
            return f"{float(x):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except Exception:
        pass
    return str(x)


def guvenli_float(x):
    try:
        if x is None:
            return None
        s = str(x).replace(".", "").replace(",", ".")
        s = re.sub(r"[^0-9\.\-]", "", s)
        if s in ["", "-", "nan"]:
            return None
        return float(s)
    except Exception:
        return None


# =========================
# FİYAT / TEKNİK
# =========================

def fiyat_verisi_cek(hisse: str):
    hisse = tr_upper(hisse).replace(".IS", "")
    sembol = f"{hisse}.IS"

    df = yf.download(
        sembol,
        period="1y",
        interval="1d",
        progress=False,
        auto_adjust=True
    )

    if df is None or df.empty:
        return None

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [c[0] for c in df.columns]

    df = df.dropna()
    return df


def teknik_analiz(df: pd.DataFrame):
    close = df["Close"].dropna()
    high = df["High"].dropna()
    low = df["Low"].dropna()

    son = float(close.iloc[-1])
    onceki = float(close.iloc[-2]) if len(close) > 1 else son
    gunluk = ((son - onceki) / onceki) * 100 if onceki else 0

    ma20 = float(close.rolling(20).mean().iloc[-1]) if len(close) >= 20 else None
    ma50 = float(close.rolling(50).mean().iloc[-1]) if len(close) >= 50 else None
    ma200 = float(close.rolling(200).mean().iloc[-1]) if len(close) >= 200 else None

    destek = float(low.tail(20).min()) if len(low) >= 20 else float(low.min())
    direnc = float(high.tail(20).max()) if len(high) >= 20 else float(high.max())

    destek_mesafe = ((son - destek) / son) * 100 if son and destek else None
    direnc_mesafe = ((direnc - son) / son) * 100 if son and direnc else None

    puan = 50
    nedenler = []

    if ma20:
        if son > ma20:
            puan += 8
            nedenler.append("Fiyat 20 günlük ortalamanın üzerinde; kısa vadeli görünüm destekleniyor.")
        else:
            puan -= 8
            nedenler.append("Fiyat 20 günlük ortalamanın altında; kısa vadede baskı var.")

    if ma50:
        if son > ma50:
            puan += 10
            nedenler.append("Fiyat 50 günlük ortalamanın üzerinde; orta vadeli yapı olumlu.")
        else:
            puan -= 10
            nedenler.append("Fiyat 50 günlük ortalamanın altında; orta vadeli görünüm zayıf.")

    if ma200:
        if son > ma200:
            puan += 14
            nedenler.append("Fiyat 200 günlük ortalamanın üzerinde; ana trend tarafı güçlü.")
        else:
            puan -= 14
            nedenler.append("Fiyat 200 günlük ortalamanın altında; ana trend tarafı temkinli.")

    if ma20 and ma50 and ma200:
        if son > ma20 > ma50 > ma200:
            trend = "Güçlü yükseliş"
            puan += 12
        elif son < ma20 and son < ma50 and son < ma200:
            trend = "Zayıf / ortalamaların altında"
            puan -= 12
        elif ma20 < ma50 < ma200:
            trend = "Düşen trend"
            puan -= 10
        else:
            trend = "Karışık / yatay"
    else:
        trend = "Veri sınırlı"

    if destek_mesafe is not None and destek_mesafe < 3:
        puan += 4
        nedenler.append("Fiyat desteğe yakın; tepki ihtimali izlenebilir.")
    if direnc_mesafe is not None and direnc_mesafe < 3:
        puan -= 4
        nedenler.append("Fiyat dirence yakın; kısa vadede kâr satışı riski artabilir.")

    if gunluk > 2:
        puan += 4
    elif gunluk < -2:
        puan -= 4

    puan = max(0, min(100, int(round(puan))))

    if puan >= 70:
        karar = "POZİTİF"
        emoji = "🟢"
    elif puan >= 55:
        karar = "HAFİF POZİTİF"
        emoji = "🟢"
    elif puan >= 45:
        karar = "NÖTR"
        emoji = "🟡"
    elif puan >= 30:
        karar = "HAFİF NEGATİF"
        emoji = "🟠"
    else:
        karar = "NEGATİF"
        emoji = "🔴"

    return {
        "son_fiyat": son,
        "gunluk": gunluk,
        "ma20": ma20,
        "ma50": ma50,
        "ma200": ma200,
        "destek": destek,
        "direnc": direnc,
        "destek_mesafe": destek_mesafe,
        "direnc_mesafe": direnc_mesafe,
        "trend": trend,
        "puan": puan,
        "karar": karar,
        "emoji": emoji,
        "nedenler": nedenler[:5],
    }


# =========================
# TEMEL VERİ
# =========================

def is_yatirim_temel_veri(hisse: str):
    hisse = tr_upper(hisse).replace(".IS", "")
    url = f"https://www.isyatirim.com.tr/tr-tr/analiz/hisse/Sayfalar/sirket-karti.aspx?hisse={hisse}"

    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7"
    }

    sonuc = {
        "fk": None,
        "pddd": None,
        "net_kar": None,
        "ozsermaye": None,
        "skor": None,
        "durum": "Veri alınamadı",
        "veri_var": False,
    }

    try:
        r = requests.get(url, headers=headers, timeout=12)
        r.raise_for_status()
        tablolar = pd.read_html(r.text)

        for tablo in tablolar:
            for i in range(len(tablo)):
                satir = " ".join(map(str, tablo.iloc[i].values)).lower()
                deger = tablo.iloc[i].values[-1] if len(tablo.iloc[i].values) > 1 else None

                if sonuc["fk"] is None and ("f/k" in satir or "fk" in satir):
                    sonuc["fk"] = deger
                if sonuc["pddd"] is None and ("pd/dd" in satir or "pddd" in satir):
                    sonuc["pddd"] = deger
                if sonuc["net_kar"] is None and ("net dönem kar" in satir or "net dönem kâr" in satir or "ana ortaklık net dönem" in satir):
                    sonuc["net_kar"] = deger
                if sonuc["ozsermaye"] is None and ("özkaynak" in satir or "özsermaye" in satir or "ozkaynak" in satir):
                    sonuc["ozsermaye"] = deger

        fk = guvenli_float(sonuc["fk"])
        pddd = guvenli_float(sonuc["pddd"])
        net_kar = guvenli_float(sonuc["net_kar"])
        oz = guvenli_float(sonuc["ozsermaye"])

        if any(v is not None for v in [fk, pddd, net_kar, oz]):
            sonuc["veri_var"] = True

        if not sonuc["veri_var"]:
            sonuc["skor"] = None
            sonuc["durum"] = "Temel veri bulunamadı"
            return sonuc

        skor = 0
        if net_kar is not None and net_kar > 0:
            skor += 2
        if oz is not None and oz > 0:
            skor += 2
        if fk is not None and 0 < fk < 30:
            skor += 1
        if pddd is not None and 0 < pddd < 5:
            skor += 1

        sonuc["skor"] = skor

        if skor >= 5:
            sonuc["durum"] = "Güçlü"
        elif skor >= 3:
            sonuc["durum"] = "Orta"
        else:
            sonuc["durum"] = "Zayıf / sınırlı"

        return sonuc

    except Exception as e:
        sonuc["hata"] = str(e)
        return sonuc


# =========================
# HABER
# =========================

HABER_POZITIF_AGIRLIK = {
    "geri alım": 4, "pay geri alım": 4, "temettü": 4, "bedelsiz": 4,
    "anlaşma": 3, "ihale": 3, "yatırım": 3, "rekor": 3,
    "kâr": 3, "kar": 3, "büyüme": 2, "artış": 2, "hedef fiyat": 2,
    "tavsiye": 1, "potansiyel": 1,
}

HABER_NEGATIF_AGIRLIK = {
    "zarar": 5, "ceza": 5, "soruşturma": 5, "dava": 4,
    "iptal": 4, "düşüş": 3, "azalış": 3, "risk": 2,
    "satış baskısı": 2, "grev": 3,
}

def haberleri_cek(hisse: str, adet: int = 5):
    try:
        sorgular = [
            f"{hisse} hisse Borsa İstanbul",
            f"{hisse} haber",
        ]
        haberler = []
        gorulen = set()

        for sorgu in sorgular:
            url = "https://news.google.com/rss/search?q=" + requests.utils.quote(sorgu) + "&hl=tr&gl=TR&ceid=TR:tr"
            feed = feedparser.parse(url)

            for entry in feed.entries[:adet]:
                baslik = BeautifulSoup(entry.title, "html.parser").get_text(" ", strip=True)
                key = baslik.lower()
                if key in gorulen:
                    continue
                gorulen.add(key)
                haberler.append({
                    "baslik": baslik,
                    "link": getattr(entry, "link", ""),
                    "tarih": getattr(entry, "published", ""),
                })

        return haberler[:adet]

    except Exception:
        return []


def haber_puanla(haberler):
    if not haberler:
        return {
            "puan": 0,
            "etki": "Nötr / haber yok",
            "emoji": "🟡",
            "detaylar": [],
        }

    toplam = 0
    detaylar = []

    for h in haberler:
        t = h["baslik"].lower()
        hp = 0

        for k, v in HABER_POZITIF_AGIRLIK.items():
            if k in t:
                hp += v

        for k, v in HABER_NEGATIF_AGIRLIK.items():
            if k in t:
                hp -= v

        # Genel borsa/varant/türev limiti gibi başlıklar şirkete direkt etki etmeyebilir.
        if "türev" in t or "varant" in t or "üst fiyat limiti" in t:
            hp = min(hp, 1)

        toplam += hp
        if hp > 0:
            detaylar.append(f"🟢 {h['baslik']}")
        elif hp < 0:
            detaylar.append(f"🔴 {h['baslik']}")
        else:
            detaylar.append(f"🟡 {h['baslik']}")

    if toplam >= 4:
        etki, emoji = "Pozitif", "🟢"
    elif toplam <= -4:
        etki, emoji = "Negatif", "🔴"
    else:
        etki, emoji = "Nötr / Karışık", "🟡"

    return {
        "puan": toplam,
        "etki": etki,
        "emoji": emoji,
        "detaylar": detaylar[:5],
    }


# =========================
# GLOBAL HABER / ETKİ
# =========================

KONU_HARITASI = {
    "petrol": {
        "baslik": "PETROL",
        "sorgular": ["Brent petrol fiyatı OPEC arz talep", "oil prices OPEC supply demand"],
        "pozitif": ["düştü", "geriledi", "arz arttı", "talep zayıf"],
        "negatif": ["yükseldi", "arttı", "arz kesintisi", "savaş", "gerilim"],
    },
    "dolar": {
        "baslik": "DOLAR",
        "sorgular": ["dolar endeksi DXY faiz Fed", "US dollar index DXY Fed"],
        "pozitif": ["düştü", "zayıfladı", "geriledi"],
        "negatif": ["yükseldi", "güçlendi", "arttı"],
    },
    "savaş": {
        "baslik": "SAVAŞ / JEOPOLİTİK RİSK",
        "sorgular": ["savaş jeopolitik risk petrol altın piyasalar", "war geopolitical risk markets"],
        "pozitif": ["ateşkes", "barış", "anlaşma", "görüşme"],
        "negatif": ["saldırı", "savaş", "gerilim", "füze", "çatışma", "yaptırım", "kriz"],
    },
    "faiz": {
        "baslik": "FAİZ",
        "sorgular": ["faiz kararı merkez bankası tahvil piyasalar", "interest rate decision markets"],
        "pozitif": ["faiz indirimi", "gevşeme", "tahvil faizi düştü"],
        "negatif": ["faiz artışı", "sıkılaşma", "tahvil faizi yükseldi"],
    },
    "enflasyon": {
        "baslik": "ENFLASYON",
        "sorgular": ["enflasyon TÜFE piyasa beklentisi", "CPI inflation market expectation"],
        "pozitif": ["düştü", "beklentinin altında", "yavaşladı"],
        "negatif": ["yükseldi", "beklentinin üstünde", "kalıcı"],
    },
    "çin": {
        "baslik": "ÇİN EKONOMİSİ",
        "sorgular": ["Çin ekonomisi büyüme PMI emtia", "China economy growth PMI commodities"],
        "pozitif": ["teşvik", "büyüme", "pmi yükseldi", "talep arttı"],
        "negatif": ["yavaşlama", "emlak krizi", "pmi düştü", "talep zayıf"],
    },
}

HISSE_GLOBAL_ETKI = {
    "THYAO": ["petrol", "dolar", "savaş"],
    "PGSUS": ["petrol", "dolar", "savaş"],
    "TAVHL": ["petrol", "dolar", "savaş"],
    "TUPRS": ["petrol", "dolar"],
    "PETKM": ["petrol", "dolar"],
    "EREGL": ["çin", "dolar"],
    "KRDMD": ["çin", "dolar"],
    "ASELS": ["savaş", "dolar"],
    "GARAN": ["faiz", "dolar", "enflasyon"],
    "AKBNK": ["faiz", "dolar", "enflasyon"],
    "YKBNK": ["faiz", "dolar", "enflasyon"],
    "ISCTR": ["faiz", "dolar", "enflasyon"],
    "ARCLK": ["dolar", "enflasyon", "faiz"],
    "FROTO": ["dolar", "faiz"],
    "TOASO": ["dolar", "faiz"],
    "BIMAS": ["enflasyon", "faiz"],
    "MGROS": ["enflasyon", "faiz"],
}

def google_news_ara(sorgu: str, adet: int = 5):
    try:
        url = "https://news.google.com/rss/search?q=" + requests.utils.quote(sorgu) + "&hl=tr&gl=TR&ceid=TR:tr"
        feed = feedparser.parse(url)
        haberler = []
        for entry in feed.entries[:adet]:
            baslik = BeautifulSoup(entry.title, "html.parser").get_text(" ", strip=True)
            haberler.append({"baslik": baslik, "link": getattr(entry, "link", ""), "tarih": getattr(entry, "published", "")})
        return haberler
    except Exception:
        return []


def global_haberleri_cek(konu: str, adet: int = 4):
    ayar = KONU_HARITASI.get(konu)
    if not ayar:
        return []

    tum = []
    gorulen = set()
    for sorgu in ayar["sorgular"]:
        for h in google_news_ara(sorgu, adet=adet):
            key = h["baslik"].lower()
            if key not in gorulen:
                gorulen.add(key)
                tum.append(h)
    return tum[:adet]


def konu_haber_etkisi(konu: str, haberler):
    ayar = KONU_HARITASI[konu]
    p = 0
    n = 0

    for h in haberler:
        t = h["baslik"].lower()
        if any(k in t for k in ayar["pozitif"]):
            p += 1
        if any(k in t for k in ayar["negatif"]):
            n += 1

    if p > n:
        return "Pozitif", "🟢", p - n
    if n > p:
        return "Negatif", "🔴", p - n
    return "Nötr / Karışık", "🟡", 0


def global_etki_analizi(hisse: str):
    hisse = tr_upper(hisse).replace(".IS", "")
    sektor = SEKTOR_HARITASI.get(hisse, "")
    konular = HISSE_GLOBAL_ETKI.get(hisse)

    if not konular:
        if sektor == "Havacılık":
            konular = ["petrol", "dolar", "savaş"]
        elif sektor == "Banka":
            konular = ["faiz", "dolar", "enflasyon"]
        elif sektor == "Demir Çelik":
            konular = ["çin", "dolar"]
        else:
            konular = ["dolar", "faiz", "enflasyon"]

    satirlar = []
    puan = 0

    for konu in konular:
        haberler = global_haberleri_cek(konu, adet=3)
        if not haberler:
            satirlar.append(f"🟡 {KONU_HARITASI[konu]['baslik']}: Veri yok")
            continue

        etki, emoji, ham_puan = konu_haber_etkisi(konu, haberler)
        hisse_etki = etki
        hisse_emoji = emoji
        etki_puan = ham_puan

        # Havacılıkta petrol ve jeopolitik risk ters çalışır.
        if konu == "petrol" and sektor == "Havacılık":
            if etki == "Pozitif":
                hisse_etki, hisse_emoji, etki_puan = "Negatif", "🔴", -1
            elif etki == "Negatif":
                hisse_etki, hisse_emoji, etki_puan = "Pozitif", "🟢", 1

        if konu == "savaş":
            if sektor == "Havacılık" and etki == "Negatif":
                hisse_etki, hisse_emoji, etki_puan = "Negatif", "🔴", -2
            elif sektor == "Savunma" and etki == "Negatif":
                hisse_etki, hisse_emoji, etki_puan = "Pozitif", "🟢", 2

        puan += etki_puan
        satirlar.append(f"{hisse_emoji} {KONU_HARITASI[konu]['baslik']}: {hisse_etki}")

    if puan >= 2:
        genel = "Destekleyici"
        emoji = "🟢"
    elif puan <= -2:
        genel = "Baskılayıcı"
        emoji = "🔴"
    else:
        genel = "Karışık / Nötr"
        emoji = "🟡"

    return {
        "puan": puan,
        "genel": genel,
        "emoji": emoji,
        "satirlar": satirlar,
    }


# =========================
# ANA KARAR MOTORU
# =========================

def karar_etiketi(skor: int):
    if skor >= 70:
        return "POZİTİF", "🟢"
    if skor >= 55:
        return "HAFİF POZİTİF", "🟢"
    if skor >= 45:
        return "NÖTR", "🟡"
    if skor >= 30:
        return "HAFİF NEGATİF", "🟠"
    return "NEGATİF", "🔴"


def temel_puan_katkisi(temel):
    if not temel.get("veri_var"):
        return 0
    skor = temel.get("skor")
    if skor is None:
        return 0
    if skor >= 5:
        return 8
    if skor >= 3:
        return 3
    return -5


def haber_puan_katkisi(haber):
    p = haber.get("puan", 0)
    if p >= 6:
        return 10
    if p >= 3:
        return 5
    if p <= -6:
        return -10
    if p <= -3:
        return -5
    return 0


def global_puan_katkisi(global_):
    p = global_.get("puan", 0)
    if p >= 2:
        return 6
    if p <= -2:
        return -6
    return 0


def teknik_kisa_yorum(teknik):
    son = teknik["son_fiyat"]
    ma20 = teknik["ma20"]
    ma50 = teknik["ma50"]
    ma200 = teknik["ma200"]

    if ma20 and ma50 and ma200 and son < ma20 and son < ma50 and son < ma200:
        return "Fiyat 20, 50 ve 200 günlük ortalamaların altında. Bu yüzden teknik görünüm kısa ve orta vadede zayıf."
    if ma20 and ma50 and ma200 and son > ma20 and son > ma50 and son > ma200:
        return "Fiyat 20, 50 ve 200 günlük ortalamaların üzerinde. Teknik görünüm güçlü tarafta."
    if teknik["puan"] >= 55:
        return "Teknik görünüm pozitif tarafa yakın, fakat destek ve direnç seviyeleri yine takip edilmeli."
    if teknik["puan"] <= 45:
        return "Teknik görünüm zayıf tarafa yakın. Fiyatın destek bölgesindeki davranışı önemli."
    return "Teknik görünüm karışık. Net yön için destek veya direnç kırılımı beklenmeli."


def seviye_yorumu(teknik):
    dm = teknik.get("destek_mesafe")
    rm = teknik.get("direnc_mesafe")

    if dm is None or rm is None:
        return "Destek ve direnç mesafesi net hesaplanamadı."

    if dm < 3:
        return "Fiyat desteğe yakın. Bu bölgede tepki gelirse görünüm toparlanabilir; destek kırılırsa risk artar."
    if rm < 3:
        return "Fiyat dirence yakın. Direnç aşılmadan yeni yükseliş için alan sınırlı kalabilir."
    if rm > dm * 1.5:
        return "Fiyat destek bölgesine daha yakın ve yukarı potansiyel aşağı riske göre daha geniş görünüyor."
    if dm > rm * 1.5:
        return "Fiyat dirence daha yakın. Kısa vadede risk-getiri çok avantajlı görünmüyor."
    return "Fiyat destek ve direnç arasında orta bölgede. Yeni yön için kırılım beklemek daha sağlıklı."


def analiz_mesaji_olustur(hisse: str):
    hisse = tr_upper(hisse).replace(".IS", "")

    df = fiyat_verisi_cek(hisse)
    if df is None or df.empty:
        return f"{hisse} için yorumlayabileceğim fiyat verisi şu an gelmedi."

    teknik = teknik_analiz(df)
    temel = is_yatirim_temel_veri(hisse)
    haberler = haberleri_cek(hisse, adet=5)
    haber = haber_puanla(haberler)
    global_ = global_etki_analizi(hisse)

    genel_skor = teknik["puan"]
    genel_skor += temel_puan_katkisi(temel)
    genel_skor += haber_puan_katkisi(haber)
    genel_skor += global_puan_katkisi(global_)
    genel_skor = max(0, min(100, int(round(genel_skor))))

    karar, emoji = karar_etiketi(genel_skor)

    yorumlar = [
        teknik_kisa_yorum(teknik),
        seviye_yorumu(teknik),
    ]

    if haberler:
        if haber["etki"] == "Pozitif":
            yorumlar.append("Haber akışı pozitif tarafta; ancak teknik görünümle birlikte okunmalı.")
        elif haber["etki"] == "Negatif":
            yorumlar.append("Haber akışı baskılayıcı tarafta; bu durum fiyat üzerinde ek risk yaratabilir.")
        else:
            yorumlar.append("Haber akışı net yön vermiyor; ana belirleyici şimdilik teknik seviyeler.")

    if global_["genel"] == "Baskılayıcı":
        yorumlar.append("Global tarafta hisseye özel riskler baskılayıcı görünüyor.")
    elif global_["genel"] == "Destekleyici":
        yorumlar.append("Global tarafta hisseyi destekleyen başlıklar var.")
    elif any("Veri yok" not in s for s in global_["satirlar"]):
        yorumlar.append("Global tarafta net bir destek veya baskı oluşmuş görünmüyor.")

    bolumler = []

    bolumler.append(f"""{emoji} {hisse} Analist Değerlendirmesi

💵 Son Fiyat: {fmt(teknik['son_fiyat'])} TL
Günlük Değişim: %{teknik['gunluk']:+.2f}

📊 Genel Skor: {genel_skor}/100
📌 Genel Sonuç: {emoji} {karar}""")

    teknik_satirlari = [
        "📈 Teknik Görünüm",
        f"Trend: {teknik['trend']}",
        f"Teknik Skor: {teknik['puan']}/100",
    ]
    if teknik.get("ma20") is not None:
        teknik_satirlari.append(f"20 Günlük Ortalama: {fmt(teknik['ma20'])}")
    if teknik.get("ma50") is not None:
        teknik_satirlari.append(f"50 Günlük Ortalama: {fmt(teknik['ma50'])}")
    if teknik.get("ma200") is not None:
        teknik_satirlari.append(f"200 Günlük Ortalama: {fmt(teknik['ma200'])}")
    bolumler.append("\n".join(teknik_satirlari))

    seviye_satirlari = [
        "🎯 Destek / Direnç",
        f"Destek: {fmt(teknik['destek'])} TL",
        f"Direnç: {fmt(teknik['direnc'])} TL",
    ]
    if teknik.get("destek_mesafe") is not None:
        seviye_satirlari.append(f"Desteğe Uzaklık: %{teknik['destek_mesafe']:.2f}")
    if teknik.get("direnc_mesafe") is not None:
        seviye_satirlari.append(f"Dirence Uzaklık: %{teknik['direnc_mesafe']:.2f}")
    bolumler.append("\n".join(seviye_satirlari))

    if temel.get("veri_var"):
        finans_satirlari = [
            "💰 Temel Görünüm",
            f"Finansal Durum: {temel.get('durum', '-')}",
        ]
        if temel.get("skor") is not None:
            finans_satirlari.append(f"Finansal Skor: {temel.get('skor')}/6")
        if temel.get("fk") is not None:
            finans_satirlari.append(f"F/K: {fmt(temel.get('fk'))}")
        if temel.get("pddd") is not None:
            finans_satirlari.append(f"PD/DD: {fmt(temel.get('pddd'))}")
        if temel.get("net_kar") is not None:
            finans_satirlari.append(f"Net Kâr: {fmt(temel.get('net_kar'))}")
        if temel.get("ozsermaye") is not None:
            finans_satirlari.append(f"Özsermaye: {fmt(temel.get('ozsermaye'))}")
        bolumler.append("\n".join(finans_satirlari))

    if haberler:
        haber_satirlari = "\n".join(f"{i}. {h['baslik']}" for i, h in enumerate(haberler[:3], 1))
        bolumler.append(f"📰 Haber Etkisi: {haber['emoji']} {haber['etki']}\n{haber_satirlari}")

    global_satirlar = [s for s in global_["satirlar"] if "Veri yok" not in s]
    if global_satirlar:
        bolumler.append(
            f"🌍 Hisseye Özel Global Etki\n"
            f"{chr(10).join(global_satirlar)}\n"
            f"Toplam Etki: {global_['emoji']} {global_['genel']}"
        )

    bolumler.append(f"🤖 Kısa Yorum\n{chr(10).join('- ' + y for y in yorumlar)}")

    return "\n\n".join(bolumler).strip()


# =========================
# MAKRO BEYİN / PİYASA RÜZGARI
# =========================

MAKRO_VARLIKLAR = {
    "S&P500": {"symbol": "^GSPC", "risk": 2},
    "Nasdaq": {"symbol": "^IXIC", "risk": 2},
    "DAX": {"symbol": "^GDAXI", "risk": 1},
    "Nikkei": {"symbol": "^N225", "risk": 1},
    "VIX": {"symbol": "^VIX", "risk": -3},
    "DXY": {"symbol": "DX-Y.NYB", "risk": -2},
    "Altın": {"symbol": "GC=F", "risk": -1},
    "Brent Petrol": {"symbol": "BZ=F", "risk": -1},
    "Bitcoin": {"symbol": "BTC-USD", "risk": 1},
}

GLOBAL_TEMA_KELIMELERI = {
    "Yapay Zeka": ["ai", "artificial intelligence", "yapay zeka", "nvidia", "chip", "semiconductor", "çip"],
    "ABD Faizleri": ["fed", "faiz", "rate", "powell", "treasury", "yield"],
    "Enflasyon": ["inflation", "cpi", "enflasyon", "price pressures"],
    "Çin Ekonomisi": ["china", "çin", "pmi", "property", "yuan"],
    "Petrol": ["oil", "brent", "opec", "petrol", "crude"],
    "Jeopolitik Risk": ["war", "savaş", "israel", "iran", "russia", "ukraine", "geopolitical", "gerilim"],
    "Savunma": ["defense", "defence", "savunma", "missile", "drone", "nato"],
    "Kripto": ["bitcoin", "crypto", "ethereum", "btc", "etf"],
    "Bankacılık": ["bank", "banks", "bankacılık", "credit"],
}

SEKTOR_AKIS_KURALLARI = {
    "Teknoloji": ["Nasdaq", "Bitcoin"],
    "Savunma": ["Jeopolitik Risk", "Savunma"],
    "Havacılık": ["Brent Petrol", "Jeopolitik Risk"],
    "Bankalar": ["ABD Faizleri", "DXY"],
    "Enerji": ["Brent Petrol"],
    "Altın/Güvenli Liman": ["Altın", "VIX", "Jeopolitik Risk"],
}

BIST_SEKTOR_HISSELERI = {
    "Teknoloji": ["TCELL", "TTKOM", "KONTR", "ALFAS", "ASTOR"],
    "Savunma": ["ASELS"],
    "Havacılık": ["THYAO", "PGSUS", "TAVHL"],
    "Bankalar": ["GARAN", "AKBNK", "YKBNK", "ISCTR"],
    "Enerji": ["TUPRS", "PETKM", "AKSEN", "ENJSA"],
    "Altın/Güvenli Liman": ["KOZAL", "KOZAA"],
}


def makro_veri_cek():
    sonuc = {}
    for ad, cfg in MAKRO_VARLIKLAR.items():
        try:
            df = yf.download(
                cfg["symbol"],
                period="7d",
                interval="1d",
                progress=False,
                auto_adjust=True
            )
            if df is None or df.empty:
                continue
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = [c[0] for c in df.columns]
            close = df["Close"].dropna()
            if len(close) < 2:
                continue
            son = float(close.iloc[-1])
            onceki = float(close.iloc[-2])
            degisim = ((son - onceki) / onceki) * 100 if onceki else 0
            sonuc[ad] = {
                "son": son,
                "degisim": degisim,
                "risk": cfg["risk"],
            }
        except Exception:
            continue
    return sonuc


def makro_risk_skoru(veriler):
    skor = 50
    nedenler = []

    for ad, v in veriler.items():
        deg = v["degisim"]
        risk = v["risk"]

        if abs(deg) < 0.15:
            continue

        katkı = 0
        if deg > 0:
            katkı = risk * min(2.5, abs(deg))
        else:
            katkı = -risk * min(2.5, abs(deg))

        skor += katkı * 3

        if katkı > 0:
            nedenler.append(f"{ad} piyasa iştahını destekliyor.")
        elif katkı < 0:
            nedenler.append(f"{ad} piyasa iştahını baskılıyor.")

    skor = max(0, min(100, int(round(skor))))

    if skor >= 70:
        etiket, emoji = "Risk iştahı güçlü", "🟢"
    elif skor >= 55:
        etiket, emoji = "Risk iştahı pozitif", "🟢"
    elif skor >= 45:
        etiket, emoji = "Risk iştahı nötr", "🟡"
    elif skor >= 30:
        etiket, emoji = "Risk iştahı zayıf", "🟠"
    else:
        etiket, emoji = "Piyasa savunmada", "🔴"

    return {
        "skor": skor,
        "etiket": etiket,
        "emoji": emoji,
        "nedenler": nedenler[:5],
    }


def global_haber_basliklari(adet=80):
    sorgular = [
        "global markets economy stocks bonds oil dollar fed",
        "world markets economy inflation oil dollar gold",
        "küresel piyasalar ekonomi faiz petrol dolar altın"
    ]
    haberler = []
    gorulen = set()

    for sorgu in sorgular:
        try:
            url = "https://news.google.com/rss/search?q=" + quote(sorgu) + "&hl=tr&gl=TR&ceid=TR:tr"
            feed = feedparser.parse(url)
            for entry in feed.entries[:adet // len(sorgular) + 5]:
                baslik = BeautifulSoup(entry.title, "html.parser").get_text(" ", strip=True)
                key = baslik.lower()
                if key not in gorulen:
                    gorulen.add(key)
                    haberler.append(baslik)
        except Exception:
            continue

    return haberler[:adet]


def global_tema_analizi(haberler):
    skorlar = {k: 0 for k in GLOBAL_TEMA_KELIMELERI}

    for baslik in haberler:
        t = baslik.lower()
        for tema, kelimeler in GLOBAL_TEMA_KELIMELERI.items():
            if any(k in t for k in kelimeler):
                skorlar[tema] += 1

    sirali = sorted(skorlar.items(), key=lambda x: x[1], reverse=True)
    return [(tema, skor) for tema, skor in sirali if skor > 0]


def ok_isareti(deg):
    if deg > 0.25:
        return "🟢"
    if deg < -0.25:
        return "🔴"
    return "🟡"


def varlik_satiri(ad, v):
    return f"{ok_isareti(v['degisim'])} {ad}: %{v['degisim']:+.2f}"


def sektor_para_akisi(veriler, temalar):
    tema_dict = dict(temalar)
    sonuc = []

    nasdaq = veriler.get("Nasdaq", {}).get("degisim")
    sp = veriler.get("S&P500", {}).get("degisim")
    petrol = veriler.get("Brent Petrol", {}).get("degisim")
    vix = veriler.get("VIX", {}).get("degisim")
    dxy = veriler.get("DXY", {}).get("degisim")
    btc = veriler.get("Bitcoin", {}).get("degisim")
    altin = veriler.get("Altın", {}).get("degisim")

    skorlar = {
        "Teknoloji": 0,
        "Savunma": 0,
        "Havacılık": 0,
        "Bankalar": 0,
        "Enerji": 0,
        "Altın/Güvenli Liman": 0,
    }

    if nasdaq is not None:
        skorlar["Teknoloji"] += 2 if nasdaq > 0.4 else (-2 if nasdaq < -0.4 else 0)
    if btc is not None:
        skorlar["Teknoloji"] += 1 if btc > 1 else (-1 if btc < -1 else 0)

    if tema_dict.get("Jeopolitik Risk", 0) >= 2 or tema_dict.get("Savunma", 0) >= 1:
        skorlar["Savunma"] += 2
        skorlar["Havacılık"] -= 2
        skorlar["Altın/Güvenli Liman"] += 1

    if petrol is not None:
        skorlar["Havacılık"] += 2 if petrol < -0.5 else (-2 if petrol > 0.5 else 0)
        skorlar["Enerji"] += 2 if petrol > 0.5 else (-1 if petrol < -0.5 else 0)

    if dxy is not None:
        skorlar["Bankalar"] -= 1 if dxy > 0.3 else 0
        skorlar["Havacılık"] -= 1 if dxy > 0.3 else 0

    if vix is not None:
        skorlar["Altın/Güvenli Liman"] += 2 if vix > 2 else (-1 if vix < -2 else 0)
        if vix > 2:
            skorlar["Teknoloji"] -= 1
            skorlar["Bankalar"] -= 1

    if altin is not None:
        skorlar["Altın/Güvenli Liman"] += 1 if altin > 0.4 else 0

    for sektor, skor in sorted(skorlar.items(), key=lambda x: x[1], reverse=True):
        if skor >= 2:
            durum, emoji = "Güçlü", "🟢"
        elif skor <= -2:
            durum, emoji = "Baskı altında", "🔴"
        else:
            durum, emoji = "Nötr", "🟡"

        hisseler = ", ".join(BIST_SEKTOR_HISSELERI.get(sektor, [])[:5])
        sonuc.append({
            "sektor": sektor,
            "skor": skor,
            "durum": durum,
            "emoji": emoji,
            "hisseler": hisseler,
        })

    return sonuc


def piyasa_ruzgari_mesaji():
    veriler = makro_veri_cek()
    haberler = global_haber_basliklari(adet=70)
    temalar = global_tema_analizi(haberler)
    risk = makro_risk_skoru(veriler)
    sektorler = sektor_para_akisi(veriler, temalar)

    bolumler = []
    bolumler.append(f"🌊 Piyasa Rüzgarı\n\n{risk['emoji']} Risk İştahı: {risk['skor']}/100\n📌 {risk['etiket']}")

    if veriler:
        siralama = ["S&P500", "Nasdaq", "DAX", "Nikkei", "VIX", "DXY", "Altın", "Brent Petrol", "Bitcoin"]
        satirlar = [varlik_satiri(ad, veriler[ad]) for ad in siralama if ad in veriler]
        bolumler.append("🌍 Ana Göstergeler\n" + "\n".join(satirlar))

    if temalar:
        top = temalar[:5]
        bolumler.append("🧠 Dünya Ne Konuşuyor?\n" + "\n".join(f"{i}. {t} ({s})" for i, (t, s) in enumerate(top, 1)))

    if sektorler:
        guclu = [s for s in sektorler if s["durum"] == "Güçlü"]
        zayif = [s for s in sektorler if s["durum"] == "Baskı altında"]
        notr = [s for s in sektorler if s["durum"] == "Nötr"]

        satirlar = []
        for s in guclu[:3]:
            satirlar.append(f"{s['emoji']} {s['sektor']}: {s['durum']} → {s['hisseler']}")
        for s in zayif[:3]:
            satirlar.append(f"{s['emoji']} {s['sektor']}: {s['durum']} → {s['hisseler']}")
        for s in notr[:2]:
            satirlar.append(f"{s['emoji']} {s['sektor']}: {s['durum']} → {s['hisseler']}")

        bolumler.append("💰 Para Nereye Akıyor?\n" + "\n".join(satirlar))

    yorum = piyasa_kokusu_yorumu(veriler, risk, temalar, sektorler)
    if yorum:
        bolumler.append("🤖 Piyasa Kokusu\n" + yorum)

    return "\n\n".join(bolumler).strip()


def piyasa_kokusu_yorumu(veriler, risk, temalar, sektorler):
    cumleler = []

    if risk["skor"] >= 60:
        cumleler.append("Piyasa genelinde risk alma isteği korunuyor.")
    elif risk["skor"] <= 40:
        cumleler.append("Piyasa savunmacı moda geçmiş görünüyor.")
    else:
        cumleler.append("Piyasa net yön arıyor; seçici olmak daha mantıklı.")

    tema_adlari = [t for t, s in temalar[:3]]
    if tema_adlari:
        cumleler.append("Küresel haber akışında öne çıkan başlıklar: " + ", ".join(tema_adlari) + ".")

    guclu = [s["sektor"] for s in sektorler if s["durum"] == "Güçlü"]
    zayif = [s["sektor"] for s in sektorler if s["durum"] == "Baskı altında"]

    if guclu:
        cumleler.append("Kısa vadede güçlenen tema: " + ", ".join(guclu[:3]) + ".")
    if zayif:
        cumleler.append("Baskı altında kalan taraf: " + ", ".join(zayif[:3]) + ".")

    return "\n".join("- " + c for c in cumleler)


def dunya_ne_konusuyor_mesaji():
    haberler = global_haber_basliklari(adet=100)
    temalar = global_tema_analizi(haberler)

    if not temalar:
        return "🌍 Dünya gündeminden yorumlanabilir başlık gelmedi."

    toplam = sum(s for _, s in temalar) or 1
    satirlar = []
    for i, (tema, skor) in enumerate(temalar[:8], 1):
        oran = skor / toplam * 100
        satirlar.append(f"{i}. {tema}: %{oran:.0f}")

    ornekler = "\n".join(f"• {h}" for h in haberler[:5])

    return f"""🌍 Dünya Ne Konuşuyor?

{chr(10).join(satirlar)}

📌 Piyasanın ana odağı:
{temalar[0][0]} ve {temalar[1][0] if len(temalar) > 1 else temalar[0][0]} başlıkları öne çıkıyor.

📰 Öne çıkan başlıklar:
{ornekler}"""


def para_nereye_gidiyor_mesaji():
    veriler = makro_veri_cek()
    haberler = global_haber_basliklari(adet=70)
    temalar = global_tema_analizi(haberler)
    sektorler = sektor_para_akisi(veriler, temalar)

    satirlar = []
    for s in sektorler:
        satirlar.append(f"{s['emoji']} {s['sektor']}: {s['durum']} → {s['hisseler']}")

    return f"""💰 Para Nereye Gidiyor?

{chr(10).join(satirlar)}

📌 Okuma:
Bu tablo endeksler, dolar, petrol, VIX, altın ve global haber temalarının birlikte yorumlanmasıyla hazırlanır."""


def gizli_firsatlar_mesaji():
    veriler = makro_veri_cek()
    haberler = global_haber_basliklari(adet=70)
    temalar = global_tema_analizi(haberler)
    tema_dict = dict(temalar)

    firsatlar = []

    petrol = veriler.get("Brent Petrol", {}).get("degisim")
    nasdaq = veriler.get("Nasdaq", {}).get("degisim")
    vix = veriler.get("VIX", {}).get("degisim")
    dxy = veriler.get("DXY", {}).get("degisim")
    altin = veriler.get("Altın", {}).get("degisim")

    if petrol is not None and petrol < -0.7:
        firsatlar.append("🟢 Petrol geriliyor. Havacılık tarafında THYAO, PGSUS ve TAVHL izlenebilir.")
    if petrol is not None and petrol > 0.7:
        firsatlar.append("🟢 Petrol yükseliyor. Enerji tarafında TUPRS, PETKM ve AKSEN izlenebilir.")
    if nasdaq is not None and nasdaq > 0.5:
        firsatlar.append("🟢 Nasdaq güçlü. Teknoloji/iletişim tarafında TCELL, TTKOM ve teknoloji temalı hisseler izlenebilir.")
    if tema_dict.get("Jeopolitik Risk", 0) >= 2 or tema_dict.get("Savunma", 0) >= 1:
        firsatlar.append("🟢 Jeopolitik/savunma haberleri öne çıkıyor. ASELS tarafı radar listesine alınabilir.")
    if vix is not None and vix > 2 and altin is not None and altin > 0:
        firsatlar.append("🟡 VIX ve altın birlikte yükseliyor. Piyasa savunmaya geçiyor olabilir; güvenli liman teması öne çıkabilir.")
    if dxy is not None and dxy > 0.4:
        firsatlar.append("🔴 Dolar güçleniyor. Gelişen piyasa ve TL varlıkları için temkinli görünüm oluşabilir.")

    if not firsatlar:
        firsatlar.append("🟡 Şu an belirgin bir kopuş teması yok. Piyasa daha çok yön arıyor; güçlü sinyal için endeks, dolar, petrol ve VIX birlikte izlenmeli.")

    return "💡 Gizli Fırsat / Tema Tarayıcı\n\n" + "\n\n".join(firsatlar)


def istek_piyasa_ruzgari(metin: str):
    m = temizle_metin(metin)
    kaliplar = [
        "rüzgar", "ruzgar", "piyasa rüzgarı", "piyasa ruzgari",
        "piyasalar ne diyor", "piyasa ne diyor", "global piyasa",
        "makro", "risk iştahı", "risk istahi"
    ]
    return any(k in m for k in kaliplar)


def istek_dunya_ne_konusuyor(metin: str):
    m = temizle_metin(metin)
    return any(k in m for k in ["dünya ne konuşuyor", "dunya ne konusuyor", "global gündem", "global gundem"])


def istek_para_akisi(metin: str):
    m = temizle_metin(metin)
    return any(k in m for k in ["para nereye gidiyor", "para akışı", "para akisi", "sektör akışı", "sektor akisi"])


def istek_gizli_firsat(metin: str):
    m = temizle_metin(metin)
    return any(k in m for k in ["gizli fırsat", "gizli firsat", "fırsat tarayıcı", "firsat tarayici", "tema tarayıcı", "tema tarayici"])


# =========================
# EK KOMUTLAR
# =========================

def guclu_hisseler_tara(limit=5):
    sonuclar = []

    for hisse in sorted(BIST_KODLARI):
        try:
            df = fiyat_verisi_cek(hisse)
            if df is None or df.empty or len(df) < 60:
                continue

            teknik = teknik_analiz(df)
            haber = haber_puanla(haberleri_cek(hisse, adet=3))
            global_ = global_etki_analizi(hisse)

            skor = teknik["puan"] + haber_puan_katkisi(haber) + global_puan_katkisi(global_)
            skor = max(0, min(100, int(round(skor))))
            karar, emoji = karar_etiketi(skor)

            sonuclar.append({
                "hisse": hisse,
                "skor": skor,
                "karar": karar,
                "emoji": emoji,
                "fiyat": teknik["son_fiyat"],
                "gunluk": teknik["gunluk"],
            })
        except Exception:
            continue

    sonuclar = sorted(sonuclar, key=lambda x: x["skor"], reverse=True)[:limit]

    if not sonuclar:
        return "Şu anda güçlü hisse taraması yapılamadı."

    satirlar = []
    for i, s in enumerate(sonuclar, 1):
        satirlar.append(f"{i}. {s['emoji']} {s['hisse']} — {s['skor']}/100 | {s['karar']} | {fmt(s['fiyat'])} TL | %{s['gunluk']:+.2f}")

    return f"""
🔥 Bugün Öne Çıkan Hisseler

{chr(10).join(satirlar)}

Kriter:
Teknik skor + haber etkisi + hisseye özel global etki birlikte değerlendirilmiştir.
""".strip()


def ekonomik_konu_bul(metin: str):
    m = temizle_metin(metin)
    eslesmeler = {
        "petrol": ["petrol", "brent"],
        "dolar": ["dolar", "dxy", "usd"],
        "savaş": ["savaş", "savas", "jeopolitik", "ukrayna", "israil", "iran", "rusya"],
        "faiz": ["faiz", "tahvil"],
        "enflasyon": ["enflasyon", "tüfe", "tufe", "cpi"],
        "çin": ["çin", "cin", "china"],
    }
    for konu, kelimeler in eslesmeler.items():
        if any(k in m for k in kelimeler):
            return konu
    return None


def konu_mesaji(konu: str):
    if konu not in KONU_HARITASI:
        return "Bu konu için haber analizi tanımlı değil."

    haberler = global_haberleri_cek(konu, adet=5)
    if not haberler:
        return f"{KONU_HARITASI[konu]['baslik']} için şu an yorumlayabileceğim güncel başlık gelmedi."

    etki, emoji, puan = konu_haber_etkisi(konu, haberler)
    satirlar = "\n".join(f"{i}. {h['baslik']}" for i, h in enumerate(haberler, 1))

    return f"""
{emoji} {KONU_HARITASI[konu]['baslik']} Haber Yorumu

Genel Etki: {emoji} {etki}

📰 Öne çıkan haberler:
{satirlar}
""".strip()


def istek_guclu_hisse(metin: str):
    m = temizle_metin(metin)
    return any(k in m for k in ["güçlü hisseler", "guclu hisseler", "fırsat", "firsat", "bugün ne alınır", "bugun ne alinir", "öne çıkan hisseler", "one cikan hisseler"])



def istek_neler_yapiyorsun(metin: str):
    m = temizle_metin(metin)
    kaliplar = [
        "neler yapıyorsun", "neler yapiyorsun", "ne yapıyorsun", "ne yapiyorsun",
        "neler yapabilirsin", "ne yapabilirsin", "neler yaparsın", "neler yaparsin",
        "ne işe yararsın", "ne ise yararsin", "özelliklerin", "ozelliklerin",
        "komutlar", "komut listesi", "yardım", "yardim", "nasıl kullanılır", "nasil kullanilir",
        "bot ne yapar", "bot özellikleri", "bot ozellikleri"
    ]
    return any(k in m for k in kaliplar)


def yetenekler_mesaji():
    return """🤖 Borsa Sohbet - Yapabildiklerim

━━━━━━━━━━━━━━
📈 HİSSE ANALİZİ
━━━━━━━━━━━━━━
• THYAO
• ASELS
• Ford nasıl?
• Bim alınır mı?
• Türk Hava Yolları son durum

Verdiğim bilgiler:
Son fiyat, teknik görünüm, ortalamalar, destek/direnç, haber etkisi, global etki, genel skor ve kısa yorum.

━━━━━━━━━━━━━━
📰 HİSSE HABERLERİ
━━━━━━━━━━━━━━
• THYAO haberleri
• ASELS son durum
• Ford haberler ne diyor?

━━━━━━━━━━━━━━
🌍 MAKRO PİYASA
━━━━━━━━━━━━━━
• rüzgar
• piyasalar ne diyor?
• global piyasa
• risk iştahı
• bugün piyasada ne oluyor?
• piyasa özeti

━━━━━━━━━━━━━━
🧠 GLOBAL GÜNDEM
━━━━━━━━━━━━━━
• dünya ne konuşuyor?
• global gündem
• piyasada ana konu ne?

━━━━━━━━━━━━━━
💰 PARA AKIŞI
━━━━━━━━━━━━━━
• para nereye gidiyor?
• para akışı
• sektör akışı

━━━━━━━━━━━━━━
💡 FIRSAT / TEMA
━━━━━━━━━━━━━━
• gizli fırsatlar
• fırsat tarayıcı
• tema tarayıcı

━━━━━━━━━━━━━━
🔎 SEBEP - SONUÇ
━━━━━━━━━━━━━━
• THYAO neden düşüyor?
• ASELS neden yükseliyor?
• Ford niye geriliyor?

━━━━━━━━━━━━━━
🔮 SENARYO MOTORU
━━━━━━━━━━━━━━
• Petrol 100 dolar olursa ne olur?
• Fed faiz indirirse ne olur?
• Dolar yükselirse BIST ne olur?
• Savaş çıkarsa hangi hisseler etkilenir?

━━━━━━━━━━━━━━
⚠️ ERKEN UYARI
━━━━━━━━━━━━━━
• erken uyarı
• risk alarmı
• piyasada risk var mı?

━━━━━━━━━━━━━━
🔥 HİSSE TARAMASI
━━━━━━━━━━━━━━
• güçlü hisseler
• bugün fırsat var mı?
• öne çıkan hisseler

━━━━━━━━━━━━━━
📉 GEÇMİŞ GRAFİK / BACKTEST
━━━━━━━━━━━━━━
• backtest THYAO
• başarı testi ASELS
• formasyon geçmişi FROTO
• THYAO tp oranı
• backtest THYAO tp 8 sl 4 gün 15

━━━━━━━━━━━━━━
📊 PERFORMANS TAKİBİ
━━━━━━━━━━━━━━
• sinyal kaydet THYAO
• sinyal geçmişi
• başarı oranı
• performans

━━━━━━━━━━━━━━
📡 RADAR / AKILLI PARA
━━━━━━━━━━━━━━
• radar
• bugünün radar listesi
• akıllı para
• olağan dışı hacim
• gizli hareketler

━━━━━━━━━━━━━━
🎯 OLAY → HİSSE
━━━━━━━━━━━━━━
• Petrol yükselirse kim kazanır?
• İran İsrail gerilimi hangi hisseleri etkiler?
• Dolar yükselirse kim etkilenir?
• Yapay zeka teması BIST'te kimi etkiler?

━━━━━━━━━━━━━━
💭 PİYASA HİKAYESİ
━━━━━━━━━━━━━━
• piyasa hikayesi
• piyasayı anlat
• bugünün hikayesi

━━━━━━━━━━━━━━
🏦 BES / EMEKLİLİK FONLARI
━━━━━━━━━━━━━━
• BES haberleri
• BES ne durumda?
• emeklilik fonları
• BES önerileri
• hangi BES fonları izlenmeli?
• altın fonu mu hisse fonu mu?

Verdiğim bilgiler:
BES gündemi, fon türleri, piyasa koşullarına göre fon dağılım fikri ve izlenecek tema önerileri.

━━━━━━━━━━━━━━
💬 NORMAL SOHBET
━━━━━━━━━━━━━━
Komut ezberlemene gerek yok.
Normal şekilde yazabilirsin:

• Şu an korkmalı mıyım?
• Bankalar nasıl?
• Petrol THYAO için iyi mi?
• Dünya nereye gidiyor?
• BES tarafında ne yapmalı?

Ben verileri sadeleştirip yorumlarım.""".strip()


def hisse_sebep_sonuc_mesaji(hisse: str, soru: str = ""):
    hisse = tr_upper(hisse).replace(".IS", "")
    df = fiyat_verisi_cek(hisse)
    if df is None or df.empty:
        return f"{hisse} için yorumlayabileceğim fiyat verisi şu an gelmedi."

    teknik = teknik_analiz(df)
    haberler = haberleri_cek(hisse, adet=5)
    haber = haber_puanla(haberler)
    global_ = global_etki_analizi(hisse)
    makro = makro_veri_cek()
    risk = makro_risk_skoru(makro)

    m = temizle_metin(soru)
    yukselis_sorusu = any(k in m for k in ["neden yüksel", "neden yuksel", "niye yüksel", "niye yuksel", "neden art", "niye art"])
    dusus_sorusu = any(k in m for k in ["neden düş", "neden dus", "niye düş", "niye dus", "neden gerile", "niye gerile"])

    sebepler = []
    olumlu = []
    olumsuz = []

    if teknik["son_fiyat"] < (teknik["ma20"] or teknik["son_fiyat"]):
        olumsuz.append("Fiyat 20 günlük ortalamanın altında; kısa vadede baskı var.")
    else:
        olumlu.append("Fiyat 20 günlük ortalamanın üzerinde; kısa vadeli görünüm destekleniyor.")

    if teknik.get("ma50") and teknik["son_fiyat"] < teknik["ma50"]:
        olumsuz.append("Fiyat 50 günlük ortalamanın altında; orta vadeli görünüm zayıf.")
    elif teknik.get("ma50"):
        olumlu.append("Fiyat 50 günlük ortalamanın üzerinde; orta vadeli yapı olumlu.")

    if teknik.get("ma200") and teknik["son_fiyat"] < teknik["ma200"]:
        olumsuz.append("Fiyat 200 günlük ortalamanın altında; ana trend temkinli.")
    elif teknik.get("ma200"):
        olumlu.append("Fiyat 200 günlük ortalamanın üzerinde; ana trend güçlü.")

    if teknik.get("direnc_mesafe") is not None and teknik["direnc_mesafe"] < 3:
        olumsuz.append("Fiyat dirence yakın; yukarı hareketlerde satış baskısı görülebilir.")
    if teknik.get("destek_mesafe") is not None and teknik["destek_mesafe"] < 3:
        olumlu.append("Fiyat desteğe yakın; tepki alımı ihtimali izlenebilir.")

    if haberler:
        if haber["etki"] == "Pozitif":
            olumlu.append("Haber akışı pozitif tarafta.")
        elif haber["etki"] == "Negatif":
            olumsuz.append("Haber akışı negatif tarafta.")

    if global_["genel"] == "Destekleyici":
        olumlu.append("Hisseye özel global başlıklar destekleyici.")
    elif global_["genel"] == "Baskılayıcı":
        olumsuz.append("Hisseye özel global başlıklar baskılayıcı.")

    if risk["skor"] < 45:
        olumsuz.append("Global risk iştahı zayıf; bu durum BIST tarafında baskı yaratabilir.")
    elif risk["skor"] > 55:
        olumlu.append("Global risk iştahı pozitif; riskli varlıkları destekliyor.")

    if dusus_sorusu:
        sebepler = olumsuz[:5] or ["Düşüşü açıklayacak net negatif sinyal sınırlı; hareket daha çok kısa vadeli fiyat dalgalanması olabilir."]
        baslik = f"🔎 {hisse} Neden Düşüyor Olabilir?"
        sonuc = "En güçlü baskı kaynağı: " + (olumsuz[0] if olumsuz else "Net bir ana sebep görünmüyor.")
    elif yukselis_sorusu:
        sebepler = olumlu[:5] or ["Yükselişi açıklayacak net pozitif sinyal sınırlı; hareket daha çok kısa vadeli fiyat tepkisi olabilir."]
        baslik = f"🔎 {hisse} Neden Yükseliyor Olabilir?"
        sonuc = "En güçlü destek: " + (olumlu[0] if olumlu else "Net bir ana sebep görünmüyor.")
    else:
        sebepler = (olumlu[:3] + olumsuz[:3])[:6]
        baslik = f"🔎 {hisse} Sebep-Sonuç Analizi"
        if len(olumlu) > len(olumsuz):
            sonuc = "Genel tablo hafif pozitif tarafa yakın."
        elif len(olumsuz) > len(olumlu):
            sonuc = "Genel tablo baskılı tarafa yakın."
        else:
            sonuc = "Genel tablo karışık; net yön için teknik seviyeler izlenmeli."

    haber_satirlari = ""
    if haberler:
        haber_satirlari = "\n\n📰 Öne Çıkan Haberler\n" + "\n".join(f"{i}. {h['baslik']}" for i, h in enumerate(haberler[:3], 1))

    return f"""{baslik}

📌 Olası Sebepler
{chr(10).join("- " + s for s in sebepler)}

🎯 Sonuç
{sonuc}{haber_satirlari}""".strip()


def senaryo_mesaji(metin: str):
    m = temizle_metin(metin)
    hisse = hisse_bul(metin)

    senaryolar = []

    if "petrol" in m or "brent" in m:
        if any(k in m for k in ["yüksel", "yuksel", "artar", "100", "110"]):
            senaryolar.append(("Petrol yükselirse", [
                "Havacılıkta yakıt maliyeti artar; THYAO, PGSUS ve TAVHL baskı görebilir.",
                "Enerji/petrol tarafı desteklenebilir; TUPRS ve PETKM izlenebilir.",
                "Enflasyon beklentisi bozulursa genel piyasa iştahı zayıflayabilir."
            ]))
        elif any(k in m for k in ["düş", "dus", "gerile", "iner"]):
            senaryolar.append(("Petrol düşerse", [
                "Havacılık tarafında maliyet baskısı azalır; THYAO, PGSUS ve TAVHL desteklenebilir.",
                "Enerji/petrol şirketlerinde marj ve fiyatlama beklentisi zayıflayabilir.",
                "Enflasyon baskısı azalırsa genel piyasa havası iyileşebilir."
            ]))

    if "fed" in m or "faiz" in m:
        if any(k in m for k in ["indir", "düşür", "dusur"]):
            senaryolar.append(("Fed / faiz indirimi olursa", [
                "Global risk iştahı artabilir.",
                "Teknoloji ve büyüme hisseleri desteklenebilir.",
                "Gelişen piyasalara para girişi beklentisi artabilir; BIST için destekleyici olabilir."
            ]))
        elif any(k in m for k in ["artır", "artir", "yükselt", "yukselt"]):
            senaryolar.append(("Faiz artışı olursa", [
                "Riskli varlıklarda baskı artabilir.",
                "Dolar güçlenirse gelişen piyasalar negatif etkilenebilir.",
                "Bankalar için etki karmaşık olabilir; marj beklentisi ve kredi riski birlikte okunmalı."
            ]))

    if "dolar" in m or "dxy" in m or "usd" in m:
        if any(k in m for k in ["yüksel", "yuksel", "güçlen", "guclen", "artar"]):
            senaryolar.append(("Dolar güçlenirse", [
                "Gelişen piyasa varlıkları baskı görebilir.",
                "Döviz borcu yüksek şirketler için risk artabilir.",
                "İhracatçı şirketler için gelir tarafında destek oluşabilir."
            ]))
        elif any(k in m for k in ["düş", "dus", "zayıfla", "zayifla"]):
            senaryolar.append(("Dolar zayıflarsa", [
                "Risk iştahı genelde desteklenir.",
                "Gelişen piyasalara para girişi artabilir.",
                "BIST için genel hava daha olumlu olabilir."
            ]))

    if "savaş" in m or "savas" in m or "jeopolitik" in m:
        senaryolar.append(("Jeopolitik risk artarsa", [
            "Altın ve savunma teması güçlenebilir.",
            "Havacılık ve turizm tarafı baskı görebilir.",
            "Petrol yükselirse enflasyon ve maliyet baskısı artabilir."
        ]))

    if not senaryolar and hisse:
        return hisse_sebep_sonuc_mesaji(hisse, metin)

    if not senaryolar:
        return """🔮 Senaryo Motoru

Şu tarz yazabilirsin:
• Petrol 100 dolar olursa THYAO ne olur?
• Fed faiz indirirse bankalar ne olur?
• Dolar yükselirse BIST ne olur?
• Savaş çıkarsa hangi hisseler etkilenir?"""

    bolumler = ["🔮 Senaryo Analizi"]
    for baslik, maddeler in senaryolar:
        bolumler.append(f"\n📌 {baslik}\n" + "\n".join("- " + x for x in maddeler))

    if hisse:
        bolumler.append(f"\n🎯 {hisse} özelinde ayrıca teknik ve haber görünümü birlikte kontrol edilmeli.")

    return "\n".join(bolumler).strip()


def erken_uyari_mesaji():
    veriler = makro_veri_cek()
    haberler = global_haber_basliklari(adet=80)
    temalar = global_tema_analizi(haberler)
    risk = makro_risk_skoru(veriler)

    uyarilar = []

    vix = veriler.get("VIX", {}).get("degisim")
    dxy = veriler.get("DXY", {}).get("degisim")
    petrol = veriler.get("Brent Petrol", {}).get("degisim")
    altin = veriler.get("Altın", {}).get("degisim")
    nasdaq = veriler.get("Nasdaq", {}).get("degisim")
    sp = veriler.get("S&P500", {}).get("degisim")

    if vix is not None and vix > 4:
        uyarilar.append("🔴 VIX sert yükseliyor; piyasa korkusu artıyor olabilir.")
    if dxy is not None and dxy > 0.5:
        uyarilar.append("🔴 Dolar endeksi güçleniyor; gelişen piyasalar için baskı yaratabilir.")
    if petrol is not None and petrol > 1:
        uyarilar.append("🔴 Petrol yükseliyor; havacılık ve enflasyon tarafı için risk.")
    if nasdaq is not None and nasdaq < -0.8:
        uyarilar.append("🔴 Nasdaq zayıf; global risk iştahı teknoloji tarafında bozuluyor.")
    if sp is not None and sp < -0.7:
        uyarilar.append("🔴 S&P500 zayıf; genel risk iştahı baskı altında.")
    if altin is not None and altin > 0.7 and vix is not None and vix > 1:
        uyarilar.append("🟠 Altın ve VIX birlikte yükseliyor; güvenli liman arayışı artmış olabilir.")

    tema_dict = dict(temalar)
    if tema_dict.get("Jeopolitik Risk", 0) >= 3:
        uyarilar.append("🟠 Global haberlerde jeopolitik risk teması öne çıkıyor.")
    if tema_dict.get("ABD Faizleri", 0) >= 3:
        uyarilar.append("🟡 ABD faizleri piyasanın ana gündeminde; oynaklık artabilir.")

    if not uyarilar:
        uyarilar.append("🟢 Şu an makro tarafta belirgin alarm sinyali sınırlı.")

    genel = "Piyasa savunmacı moda yakın." if risk["skor"] < 45 else "Piyasa genelinde panik sinyali sınırlı."
    if risk["skor"] > 60:
        genel = "Risk iştahı destekleyici tarafta."

    return f"""⚠️ Erken Uyarı Sistemi

{chr(10).join(uyarilar)}

📊 Risk İştahı: {risk['skor']}/100
📌 Genel Okuma: {genel}""".strip()


def istek_sebep_sonuc(metin: str):
    m = temizle_metin(metin)
    return any(k in m for k in [
        "neden düş", "neden dus", "niye düş", "niye dus",
        "neden yüksel", "neden yuksel", "niye yüksel", "niye yuksel",
        "neden art", "niye art", "sebebi ne", "sebep ne"
    ])


def istek_senaryo(metin: str):
    m = temizle_metin(metin)
    return any(k in m for k in [
        "olursa ne olur", "olursa", "senaryo", "ne olur",
        "petrol 100", "fed faiz", "dolar yüksel", "dolar yuksel",
        "savaş çıkarsa", "savas cikarsa"
    ])


def istek_erken_uyari(metin: str):
    m = temizle_metin(metin)
    return any(k in m for k in [
        "erken uyarı", "erken uyari", "alarm", "risk alarmı", "risk alarmi",
        "tehlike var mı", "tehlike var mi", "piyasada risk var mı", "piyasada risk var mi"
    ])


def bugun_piyasada_ne_oluyor_mesaji():
    veriler = makro_veri_cek()
    haberler = global_haber_basliklari(adet=100)
    temalar = global_tema_analizi(haberler)
    risk = makro_risk_skoru(veriler)
    sektorler = sektor_para_akisi(veriler, temalar)

    uyarilar = []
    vix = veriler.get("VIX", {}).get("degisim")
    dxy = veriler.get("DXY", {}).get("degisim")
    petrol = veriler.get("Brent Petrol", {}).get("degisim")
    nasdaq = veriler.get("Nasdaq", {}).get("degisim")
    sp = veriler.get("S&P500", {}).get("degisim")

    if vix is not None and vix > 4:
        uyarilar.append("VIX sert yükseliyor; piyasa korkusu artıyor.")
    if dxy is not None and dxy > 0.5:
        uyarilar.append("Dolar güçleniyor; gelişen piyasalar için baskı oluşabilir.")
    if petrol is not None and petrol > 1:
        uyarilar.append("Petrol yükseliyor; havacılık ve enflasyon tarafında risk var.")
    if nasdaq is not None and nasdaq < -0.8:
        uyarilar.append("Nasdaq zayıf; teknoloji tarafında risk iştahı düşüyor.")
    if sp is not None and sp < -0.7:
        uyarilar.append("S&P500 zayıf; global risk iştahı baskılanıyor.")
    if not uyarilar:
        uyarilar.append("Makro tarafta sert alarm sinyali sınırlı.")

    ana_gosterge = []
    for ad in ["S&P500", "Nasdaq", "VIX", "DXY", "Altın", "Brent Petrol", "Bitcoin"]:
        if ad in veriler:
            ana_gosterge.append(varlik_satiri(ad, veriler[ad]))

    tema_satirlari = [f"{i}. {tema} ({skor})" for i, (tema, skor) in enumerate(temalar[:5], 1)]

    guclu = [s for s in sektorler if s["durum"] == "Güçlü"]
    zayif = [s for s in sektorler if s["durum"] == "Baskı altında"]

    akis = []
    for s in guclu[:3]:
        akis.append(f"🟢 {s['sektor']}: {s['hisseler']}")
    for s in zayif[:3]:
        akis.append(f"🔴 {s['sektor']}: {s['hisseler']}")
    if not akis:
        akis.append("🟡 Sektörlerde belirgin ayrışma sınırlı.")

    koku = piyasa_kokusu_yorumu(veriler, risk, temalar, sektorler)

    bolumler = [
        f"🧩 Bugün Piyasada Ne Oluyor?\n\n{risk['emoji']} Risk İştahı: {risk['skor']}/100\n📌 {risk['etiket']}"
    ]
    if ana_gosterge:
        bolumler.append("🌍 Ana Göstergeler\n" + "\n".join(ana_gosterge))
    if tema_satirlari:
        bolumler.append("🧠 Dünya Gündemi\n" + "\n".join(tema_satirlari))
    bolumler.append("💰 Para Akışı\n" + "\n".join(akis))
    bolumler.append("⚠️ Erken Uyarı\n" + "\n".join("- " + u for u in uyarilar))
    if koku:
        bolumler.append("🤖 Kısa Piyasa Kokusu\n" + koku)
    return "\n\n".join(bolumler).strip()


def istek_birlesik_piyasa_raporu(metin: str):
    m = temizle_metin(metin)
    return any(k in m for k in [
        "bugün piyasada ne oluyor", "bugun piyasada ne oluyor",
        "piyasa özeti", "piyasa ozeti",
        "genel piyasa raporu", "bugün ne oluyor", "bugun ne oluyor",
        "piyasanın özeti", "piyasanin ozeti"
    ])


# =========================
# PERFORMANS / SİNYAL TAKİP MOTORU
# =========================

SINYAL_DOSYA = DATA_DIR / "sinyal_gecmisi.json"


def json_yukle(path, default):
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return default


def json_kaydet(path, data):
    try:
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


def piyasa_filtresi_ozeti():
    veriler = makro_veri_cek()
    risk = makro_risk_skoru(veriler)
    skor = risk["skor"]

    if skor >= 60:
        return {"skor": skor, "durum": "Destekleyici", "emoji": "🟢", "katsayi": 1.05, "etiket": risk["etiket"]}
    if skor >= 45:
        return {"skor": skor, "durum": "Nötr", "emoji": "🟡", "katsayi": 1.00, "etiket": risk["etiket"]}
    return {"skor": skor, "durum": "Baskılayıcı", "emoji": "🔴", "katsayi": 0.85, "etiket": risk["etiket"]}


def guven_skoru_hesapla(teknik, temel, haberler, global_, piyasa):
    guven = 35

    if teknik.get("ma20") is not None:
        guven += 10
    if teknik.get("ma50") is not None:
        guven += 10
    if teknik.get("ma200") is not None:
        guven += 10
    if haberler:
        guven += 10
    if any("Veri yok" not in s for s in global_.get("satirlar", [])):
        guven += 10
    if temel.get("veri_var"):
        guven += 10
    if piyasa["skor"] < 40:
        guven -= 10

    return max(20, min(95, int(round(guven))))


def disiplinli_karar(genel_skor, guven, teknik, piyasa):
    karar, emoji = karar_etiketi(genel_skor)
    bekle_nedenleri = []

    if guven < 55:
        bekle_nedenleri.append("güven skoru düşük")
    if piyasa["durum"] == "Baskılayıcı" and genel_skor < 75:
        bekle_nedenleri.append("genel piyasa filtresi baskılayıcı")
    if teknik.get("direnc_mesafe") is not None and teknik["direnc_mesafe"] < 3 and genel_skor < 80:
        bekle_nedenleri.append("fiyat dirence yakın")
    if teknik.get("son_fiyat") and teknik.get("ma20") and teknik["son_fiyat"] < teknik["ma20"] and genel_skor < 70:
        bekle_nedenleri.append("fiyat kısa vadeli ortalamanın altında")

    if bekle_nedenleri and karar in ["POZİTİF", "HAFİF POZİTİF"]:
        return "POZİTİF AMA BEKLE", "🟡", bekle_nedenleri

    return karar, emoji, bekle_nedenleri


def sinyal_uret(hisse: str):
    hisse = tr_upper(hisse).replace(".IS", "")
    df = fiyat_verisi_cek(hisse)

    if df is None or df.empty:
        return None, f"{hisse} için fiyat verisi şu an gelmedi."

    teknik = teknik_analiz(df)
    temel = is_yatirim_temel_veri(hisse)
    haberler = haberleri_cek(hisse, adet=5)
    haber = haber_puanla(haberler)
    global_ = global_etki_analizi(hisse)
    piyasa = piyasa_filtresi_ozeti()

    ham_skor = teknik["puan"]
    ham_skor += temel_puan_katkisi(temel)
    ham_skor += haber_puan_katkisi(haber)
    ham_skor += global_puan_katkisi(global_)

    filtreli_skor = int(round(ham_skor * piyasa["katsayi"]))
    filtreli_skor = max(0, min(100, filtreli_skor))

    guven = guven_skoru_hesapla(teknik, temel, haberler, global_, piyasa)
    karar, emoji, bekle_nedenleri = disiplinli_karar(filtreli_skor, guven, teknik, piyasa)

    sinyal = {
        "tarih": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "hisse": hisse,
        "fiyat": teknik["son_fiyat"],
        "teknik_skor": teknik["puan"],
        "ham_skor": ham_skor,
        "filtreli_skor": filtreli_skor,
        "guven": guven,
        "karar": karar,
        "emoji": emoji,
        "piyasa_skor": piyasa["skor"],
        "piyasa_durum": piyasa["durum"],
        "bekle_nedenleri": bekle_nedenleri,
        "durum": "açık",
        "kontrol_gun": 5,
        "sonuc": None,
    }
    return sinyal, None


def sinyal_kaydet_mesaji(hisse: str):
    sinyal, hata = sinyal_uret(hisse)
    if hata:
        return hata

    data = json_yukle(SINYAL_DOSYA, [])
    data.append(sinyal)
    json_kaydet(SINYAL_DOSYA, data)

    neden = ""
    if sinyal["bekle_nedenleri"]:
        neden = "\nBekleme Nedeni: " + ", ".join(sinyal["bekle_nedenleri"])

    return f"""✅ Sinyal Kaydedildi

{sinyal['emoji']} {sinyal['hisse']}
Fiyat: {fmt(sinyal['fiyat'])} TL
Karar: {sinyal['karar']}
Skor: {sinyal['filtreli_skor']}/100
Güven: %{sinyal['guven']}
Piyasa Filtresi: {sinyal['piyasa_durum']} ({sinyal['piyasa_skor']}/100){neden}

Bu sinyal ileride başarı oranı ölçümünde kullanılacak."""


def sinyal_gecmisi_mesaji(limit=10):
    data = json_yukle(SINYAL_DOSYA, [])
    if not data:
        return "Henüz kayıtlı sinyal yok. Örnek: sinyal kaydet THYAO"

    satirlar = []
    for i, s in enumerate(reversed(data[-limit:]), 1):
        sonuc = ""
        if s.get("sonuc"):
            sonuc = f" | Sonuç: {s['sonuc'].get('getiri_pct', 0):+.2f}%"
        satirlar.append(
            f"{i}. {s.get('emoji','')} {s['hisse']} | {s['karar']} | "
            f"Skor {s['filtreli_skor']}/100 | Güven %{s['guven']} | "
            f"{fmt(s['fiyat'])} TL{sonuc}"
        )

    return "📒 Sinyal Geçmişi\n\n" + "\n".join(satirlar)


def sinyal_sonucunu_hesapla(sinyal):
    hisse = sinyal["hisse"]
    giris = float(sinyal["fiyat"])
    df = fiyat_verisi_cek(hisse)

    if df is None or df.empty:
        return None

    son = float(df["Close"].dropna().iloc[-1])
    getiri = ((son - giris) / giris) * 100 if giris else 0
    karar = sinyal.get("karar", "")
    dogru = None

    if "POZİTİF" in karar and "BEKLE" not in karar:
        dogru = getiri > 0
    elif "NEGATİF" in karar:
        dogru = getiri < 0
    elif "BEKLE" in karar or "NÖTR" in karar:
        dogru = abs(getiri) < 3 or getiri >= -2

    return {
        "son_fiyat": son,
        "getiri_pct": getiri,
        "dogru": dogru,
        "guncelleme": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


def basari_orani_mesaji():
    data = json_yukle(SINYAL_DOSYA, [])
    if not data:
        return "Başarı oranı için henüz kayıtlı sinyal yok. Örnek: sinyal kaydet THYAO"

    for s in data:
        sonuc = sinyal_sonucunu_hesapla(s)
        if sonuc:
            s["sonuc"] = sonuc

    json_kaydet(SINYAL_DOSYA, data)

    dogru = 0
    toplam = 0
    acik = 0
    karar_stats = {}

    for s in data:
        sonuc = s.get("sonuc")
        if sonuc and sonuc.get("dogru") is not None:
            toplam += 1
            if sonuc["dogru"]:
                dogru += 1

            k = s.get("karar", "Bilinmiyor")
            karar_stats.setdefault(k, [0, 0])
            karar_stats[k][1] += 1
            if sonuc["dogru"]:
                karar_stats[k][0] += 1
        else:
            acik += 1

    oran = (dogru / toplam * 100) if toplam else 0

    detay = []
    for k, (d, t) in sorted(karar_stats.items(), key=lambda x: x[1][1], reverse=True):
        detay.append(f"• {k}: %{(d/t*100):.0f} ({d}/{t})")

    detay_txt = "\n".join(detay[:5]) if detay else "Henüz detay için yeterli sinyal yok."

    return f"""📊 Başarı Oranı

Toplam Değerlendirilen: {toplam}
Doğru Sinyal: {dogru}
Başarı Oranı: %{oran:.1f}
Açık / Eksik Sinyal: {acik}

Karar Bazlı Performans:
{detay_txt}

Not:
Bu ölçüm kaydedilen sinyaller üzerinden yapılır. Daha sağlıklı oran için farklı piyasa koşullarında daha fazla sinyal birikmesi gerekir."""


def sinyal_komutu_mu(metin: str):
    m = temizle_metin(metin)
    return any(k in m for k in [
        "sinyal kaydet", "sinyali kaydet",
        "sinyal geçmişi", "sinyal gecmisi",
        "başarı oranı", "basari orani",
        "performans"
    ])



def sinyal_hisse_bul(metin: str):
    """
    Sinyal komutlarında 'SINYAL' kelimesinin hisse sanılmasını engeller.
    Önce BIST kodlarını arar, sonra şirket adı eşleşmesine döner.
    """
    temiz = re.sub(r"\b(sinyal|kaydet|sinyali|geçmişi|gecmisi|başarı|basari|oranı|orani|performans)\b", " ", metin, flags=re.IGNORECASE)
    return hisse_bul(temiz)


def sinyal_komutu_mesaji(metin: str):
    m = temizle_metin(metin)

    if "sinyal geçmişi" in m or "sinyal gecmisi" in m:
        return sinyal_gecmisi_mesaji()

    if "başarı oranı" in m or "basari orani" in m or "performans" in m:
        return basari_orani_mesaji()

    hisse = sinyal_hisse_bul(metin)
    if hisse and ("sinyal kaydet" in m or "sinyali kaydet" in m):
        return sinyal_kaydet_mesaji(hisse)

    return """📊 Sinyal Takip Komutları

• sinyal kaydet THYAO
• sinyal kaydet ASELS
• sinyal geçmişi
• başarı oranı
• performans

Bu sistem botun verdiği sinyalleri kaydeder ve zamanla başarı oranını ölçer."""


# =========================
# GEÇMİŞ GRAFİK / BACKTEST BEYNİ
# =========================

def backtest_verisi_cek(hisse: str, period="3y"):
    hisse = tr_upper(hisse).replace(".IS", "")
    df = yf.download(
        f"{hisse}.IS",
        period=period,
        interval="1d",
        progress=False,
        auto_adjust=True
    )
    if df is None or df.empty:
        return None
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [c[0] for c in df.columns]
    df = df.dropna()
    return df


def backtest_indikatorleri(df: pd.DataFrame):
    df = df.copy()
    close = df["Close"]

    df["MA20"] = close.rolling(20).mean()
    df["MA50"] = close.rolling(50).mean()
    df["MA200"] = close.rolling(200).mean()

    df["HH20"] = df["High"].rolling(20).max()
    df["LL20"] = df["Low"].rolling(20).min()

    delta = close.diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    rs = gain / loss.replace(0, np.nan)
    df["RSI"] = 100 - (100 / (1 + rs))

    df["VOL20"] = df["Volume"].rolling(20).mean() if "Volume" in df.columns else np.nan
    return df


def backtest_sinyalleri_uret(df: pd.DataFrame):
    """
    Geçmiş grafikte tekrar eden basit senaryoları yakalar.
    Amaç kesin formasyon değil, ölçülebilir piyasa davranışı üretmek.
    """
    df = backtest_indikatorleri(df)
    sinyaller = []

    for i in range(220, len(df) - 21):
        row = df.iloc[i]
        prev = df.iloc[i - 1]
        close = row["Close"]

        if pd.isna(row["MA20"]) or pd.isna(row["MA50"]) or pd.isna(row["MA200"]):
            continue

        tarih = df.index[i].strftime("%Y-%m-%d")

        # 1) Trend yukarı: MA20 > MA50 > MA200 ve fiyat MA20 üstünde
        if row["MA20"] > row["MA50"] > row["MA200"] and close > row["MA20"]:
            sinyaller.append({
                "tarih": tarih,
                "idx": i,
                "tip": "Yükselen Trend",
                "fiyat": float(close),
            })

        # 2) Ortalamadan tepki: yükselen trendde fiyat MA20'ye değip tekrar üstte kapanır
        if (
            row["MA20"] > row["MA50"] and
            row["Low"] <= row["MA20"] * 1.01 and
            close > row["MA20"] and
            prev["Close"] < prev["MA20"] if not pd.isna(prev["MA20"]) else False
        ):
            sinyaller.append({
                "tarih": tarih,
                "idx": i,
                "tip": "MA20 Tepki",
                "fiyat": float(close),
            })

        # 3) Direnç kırılımı: fiyat önceki 20 günlük tepeyi aşar
        onceki_hh20 = df["High"].iloc[i-20:i].max()
        if close > onceki_hh20 and row["Volume"] > row["VOL20"] * 1.1 if "Volume" in df.columns and not pd.isna(row["VOL20"]) else close > onceki_hh20:
            sinyaller.append({
                "tarih": tarih,
                "idx": i,
                "tip": "Direnç Kırılımı",
                "fiyat": float(close),
            })

        # 4) RSI toparlanma: RSI 30 altından 35 üstüne döner
        if not pd.isna(row["RSI"]) and not pd.isna(prev["RSI"]):
            if prev["RSI"] < 30 and row["RSI"] > 35:
                sinyaller.append({
                    "tarih": tarih,
                    "idx": i,
                    "tip": "RSI Dipten Dönüş",
                    "fiyat": float(close),
                })

        # 5) Düşen trend uyarısı
        if row["MA20"] < row["MA50"] < row["MA200"] and close < row["MA20"]:
            sinyaller.append({
                "tarih": tarih,
                "idx": i,
                "tip": "Düşen Trend",
                "fiyat": float(close),
            })

    # Aynı gün aynı tip tekrarlarını temizle
    temiz = []
    gorulen = set()
    for s in sinyaller:
        key = (s["tarih"], s["tip"])
        if key not in gorulen:
            gorulen.add(key)
            temiz.append(s)
    return temiz


def tp_sl_sonuc(df, idx, giris, tp_pct=5, sl_pct=3, gun=10):
    """
    Sinyalden sonra TP mi önce gelir, SL mi önce gelir?
    """
    tp = giris * (1 + tp_pct / 100)
    sl = giris * (1 - sl_pct / 100)

    son_idx = min(len(df) - 1, idx + gun)

    for j in range(idx + 1, son_idx + 1):
        high = float(df["High"].iloc[j])
        low = float(df["Low"].iloc[j])

        if low <= sl:
            return "SL", -sl_pct, j - idx
        if high >= tp:
            return "TP", tp_pct, j - idx

    kapanis = float(df["Close"].iloc[son_idx])
    getiri = ((kapanis - giris) / giris) * 100
    return "SÜRE", getiri, son_idx - idx


def backtest_hesapla(hisse: str, tp_pct=5, sl_pct=3, gun=10):
    df = backtest_verisi_cek(hisse, period="3y")
    if df is None or df.empty or len(df) < 260:
        return None, f"{hisse} için backtest yapacak kadar geçmiş veri gelmedi."

    sinyaller = backtest_sinyalleri_uret(df)
    if not sinyaller:
        return None, f"{hisse} için ölçülebilir geçmiş senaryo yakalanmadı."

    sonuc = {}
    tum_islemler = []

    for s in sinyaller:
        durum, getiri, kac_gun = tp_sl_sonuc(
            df=df,
            idx=s["idx"],
            giris=s["fiyat"],
            tp_pct=tp_pct,
            sl_pct=sl_pct,
            gun=gun
        )

        islem = {
            **s,
            "durum": durum,
            "getiri": getiri,
            "kac_gun": kac_gun,
        }
        tum_islemler.append(islem)

        tip = s["tip"]
        if tip not in sonuc:
            sonuc[tip] = {
                "adet": 0,
                "tp": 0,
                "sl": 0,
                "sure": 0,
                "toplam_getiri": 0,
                "ortalama_gun": 0,
            }

        sonuc[tip]["adet"] += 1
        sonuc[tip]["toplam_getiri"] += getiri
        sonuc[tip]["ortalama_gun"] += kac_gun

        if durum == "TP":
            sonuc[tip]["tp"] += 1
        elif durum == "SL":
            sonuc[tip]["sl"] += 1
        else:
            sonuc[tip]["sure"] += 1

    for tip, r in sonuc.items():
        adet = r["adet"]
        r["tp_orani"] = (r["tp"] / adet * 100) if adet else 0
        r["sl_orani"] = (r["sl"] / adet * 100) if adet else 0
        r["ortalama_getiri"] = r["toplam_getiri"] / adet if adet else 0
        r["ortalama_gun"] = r["ortalama_gun"] / adet if adet else 0

    sirali = sorted(
        sonuc.items(),
        key=lambda x: (x[1]["tp_orani"], x[1]["ortalama_getiri"], x[1]["adet"]),
        reverse=True
    )

    return {
        "hisse": tr_upper(hisse).replace(".IS", ""),
        "tp_pct": tp_pct,
        "sl_pct": sl_pct,
        "gun": gun,
        "istatistik": sonuc,
        "sirali": sirali,
        "islemler": tum_islemler,
        "sinyal_sayisi": len(tum_islemler),
    }, None


def mevcut_formasyon_oku(hisse: str):
    df = backtest_verisi_cek(hisse, period="1y")
    if df is None or df.empty:
        return []

    df = backtest_indikatorleri(df)
    row = df.iloc[-1]
    prev = df.iloc[-2]
    sinyaller = []

    close = float(row["Close"])

    if not pd.isna(row["MA20"]) and not pd.isna(row["MA50"]) and not pd.isna(row["MA200"]):
        if row["MA20"] > row["MA50"] > row["MA200"] and close > row["MA20"]:
            sinyaller.append("Yükselen Trend")
        if row["MA20"] < row["MA50"] < row["MA200"] and close < row["MA20"]:
            sinyaller.append("Düşen Trend")

    if not pd.isna(row["MA20"]) and not pd.isna(prev["MA20"]):
        if row["Low"] <= row["MA20"] * 1.01 and close > row["MA20"]:
            sinyaller.append("MA20 Tepki")

    onceki_hh20 = df["High"].iloc[-21:-1].max()
    if close > onceki_hh20:
        sinyaller.append("Direnç Kırılımı")

    if not pd.isna(row["RSI"]) and not pd.isna(prev["RSI"]):
        if prev["RSI"] < 30 and row["RSI"] > 35:
            sinyaller.append("RSI Dipten Dönüş")

    return list(dict.fromkeys(sinyaller))


def backtest_mesaji(hisse: str, tp_pct=5, sl_pct=3, gun=10):
    rapor, hata = backtest_hesapla(hisse, tp_pct=tp_pct, sl_pct=sl_pct, gun=gun)
    if hata:
        return hata

    mevcut = mevcut_formasyon_oku(hisse)
    satirlar = []

    for tip, r in rapor["sirali"]:
        if r["adet"] < 3:
            continue
        satirlar.append(
            f"• {tip}: TP %{r['tp_orani']:.0f} | SL %{r['sl_orani']:.0f} | "
            f"Ort. Getiri %{r['ortalama_getiri']:+.2f} | Adet {r['adet']}"
        )

    if not satirlar:
        satirlar.append("Ölçüm için yeterli tekrar eden senaryo yok.")

    en_iyi = None
    for tip, r in rapor["sirali"]:
        if r["adet"] >= 3:
            en_iyi = (tip, r)
            break

    plan = "Yeterli istatistik oluşmadığı için agresif plan üretmek doğru olmaz."
    if en_iyi:
        tip, r = en_iyi
        plan = (
            f"Geçmişte en iyi çalışan yapı: {tip}. "
            f"Bu yapı görüldüğünde {gun} gün içinde TP başarı oranı yaklaşık %{r['tp_orani']:.0f}. "
            f"Yeni sinyallerde bu formasyon daha yüksek öncelikli izlenebilir."
        )

    mevcut_txt = ", ".join(mevcut) if mevcut else "Şu an güçlü bir geçmiş senaryo eşleşmesi yok."

    return f"""📊 {rapor['hisse']} Geçmiş Grafik Başarı Testi

Test Ayarı:
TP: %{tp_pct}
SL: %{sl_pct}
Süre: {gun} işlem günü
Toplam Sinyal: {rapor['sinyal_sayisi']}

📈 Senaryo Başarı Oranları
{chr(10).join(satirlar[:8])}

🔍 Şu Anki Grafik Eşleşmesi
{mevcut_txt}

🎯 Gelecek Planı
{plan}

Not:
Bu sonuçlar geçmiş veriye göre olasılık ölçümüdür. Geleceği garanti etmez; botun sinyal kalitesini ölçmek ve filtrelemek için kullanılır."""


def backtest_komutu_mu(metin: str):
    m = temizle_metin(metin)
    return any(k in m for k in [
        "backtest", "başarı testi", "basari testi", "geçmiş grafik", "gecmis grafik",
        "formasyon geçmişi", "formasyon gecmisi", "tp oranı", "tp orani",
        "geçmiş başarı", "gecmis basari"
    ])


def backtest_komutu_mesaji(metin: str):
    hisse = hisse_bul(metin)
    if not hisse:
        return """📊 Backtest Komutları

Örnek:
• backtest THYAO
• başarı testi ASELS
• formasyon geçmişi FROTO
• THYAO tp oranı

Varsayılan test:
TP: %5
SL: %3
Süre: 10 işlem günü"""

    # Kullanıcı isterse tp/sl/gün yazabilsin: "backtest THYAO tp 8 sl 4 gün 15"
    m = temizle_metin(metin)
    tp = 5
    sl = 3
    gun = 10

    tp_match = re.search(r"tp\s*%?\s*(\d+)", m)
    sl_match = re.search(r"sl\s*%?\s*(\d+)", m)
    gun_match = re.search(r"(gün|gun|süre|sure)\s*(\d+)", m)

    if tp_match:
        tp = int(tp_match.group(1))
    if sl_match:
        sl = int(sl_match.group(1))
    if gun_match:
        gun = int(gun_match.group(2))

    tp = max(1, min(tp, 30))
    sl = max(1, min(sl, 20))
    gun = max(3, min(gun, 60))

    return backtest_mesaji(hisse, tp_pct=tp, sl_pct=sl, gun=gun)


# =========================
# RADAR / AKILLI PARA / OLAY-HİSSE / PİYASA HİKAYESİ
# =========================

RADAR_HISSELER = sorted(list(BIST_KODLARI))


def endeks_verisi_cek():
    try:
        df = yf.download("XU100.IS", period="3mo", interval="1d", progress=False, auto_adjust=True)
        if df is None or df.empty:
            return None
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = [c[0] for c in df.columns]
        return df.dropna()
    except Exception:
        return None


def yuzde_getiri(df, gun=5):
    try:
        close = df["Close"].dropna()
        if len(close) <= gun:
            return 0
        return ((float(close.iloc[-1]) - float(close.iloc[-gun-1])) / float(close.iloc[-gun-1])) * 100
    except Exception:
        return 0


def hacim_orani(df):
    try:
        if "Volume" not in df.columns or len(df) < 25:
            return 1
        son_hacim = float(df["Volume"].tail(5).mean())
        normal_hacim = float(df["Volume"].tail(25).head(20).mean())
        if normal_hacim <= 0:
            return 1
        return son_hacim / normal_hacim
    except Exception:
        return 1


def akilli_para_skoru(hisse: str, endeks_getiri=0):
    hisse = tr_upper(hisse).replace(".IS", "")
    try:
        df = fiyat_verisi_cek(hisse)
        if df is None or df.empty or len(df) < 60:
            return None

        teknik = teknik_analiz(df)
        h_getiri_5 = yuzde_getiri(df, 5)
        h_getiri_20 = yuzde_getiri(df, 20)
        ayrisma = h_getiri_5 - endeks_getiri
        hacim = hacim_orani(df)
        haberler = haberleri_cek(hisse, adet=3)
        haber = haber_puanla(haberler)

        skor = 50
        nedenler = []

        if ayrisma > 5:
            skor += 18
            nedenler.append(f"Endeksten %{ayrisma:.1f} pozitif ayrışıyor.")
        elif ayrisma > 2:
            skor += 10
            nedenler.append(f"Endekse göre güçlü duruyor: %{ayrisma:.1f} ayrışma.")
        elif ayrisma < -5:
            skor -= 15
            nedenler.append(f"Endeksten negatif ayrışıyor: %{ayrisma:.1f}.")

        if hacim > 2:
            skor += 18
            nedenler.append(f"Hacim olağan dışı artmış: {hacim:.1f}x.")
        elif hacim > 1.4:
            skor += 10
            nedenler.append(f"Hacim artışı dikkat çekiyor: {hacim:.1f}x.")

        if teknik["son_fiyat"] > (teknik.get("ma20") or teknik["son_fiyat"]):
            skor += 5
        if teknik.get("ma50") and teknik["son_fiyat"] > teknik["ma50"]:
            skor += 5
        if teknik.get("direnc_mesafe") is not None and teknik["direnc_mesafe"] < 4:
            skor += 4
            nedenler.append("Direnç bölgesine yakın; kırılım takip edilebilir.")

        if haberler and haber["etki"] == "Pozitif":
            skor += 8
            nedenler.append("Haber akışı pozitif.")
        elif not haberler and ayrisma > 3 and hacim > 1.3:
            skor += 8
            nedenler.append("Haber olmadan hareket var; akıllı para ihtimali izlenebilir.")

        skor = max(0, min(100, int(round(skor))))

        if skor >= 75:
            etiket, emoji = "Güçlü radar", "🟢"
        elif skor >= 62:
            etiket, emoji = "Dikkat çekiyor", "🟢"
        elif skor >= 48:
            etiket, emoji = "Nötr", "🟡"
        else:
            etiket, emoji = "Zayıf", "🔴"

        return {
            "hisse": hisse,
            "skor": skor,
            "etiket": etiket,
            "emoji": emoji,
            "getiri_5": h_getiri_5,
            "getiri_20": h_getiri_20,
            "ayrisma": ayrisma,
            "hacim": hacim,
            "teknik_skor": teknik["puan"],
            "fiyat": teknik["son_fiyat"],
            "nedenler": nedenler[:4],
        }
    except Exception:
        return None


def radar_taramasi(limit=8):
    endeks_df = endeks_verisi_cek()
    endeks_getiri = yuzde_getiri(endeks_df, 5) if endeks_df is not None else 0

    sonuclar = []
    for hisse in RADAR_HISSELER:
        r = akilli_para_skoru(hisse, endeks_getiri=endeks_getiri)
        if r:
            sonuclar.append(r)

    sonuclar = sorted(sonuclar, key=lambda x: (x["skor"], x["ayrisma"], x["hacim"]), reverse=True)
    return sonuclar[:limit], endeks_getiri


def radar_mesaji():
    sonuclar, endeks_getiri = radar_taramasi(limit=8)

    if not sonuclar:
        return "📡 Radar taramasında yorumlanabilir hisse bulunamadı."

    satirlar = []
    for i, r in enumerate(sonuclar, 1):
        neden = "; ".join(r["nedenler"]) if r["nedenler"] else "Teknik ve relatif görünüm izleniyor."
        satirlar.append(
            f"{i}. {r['emoji']} {r['hisse']} — {r['skor']}/100 | {r['etiket']}\n"
            f"   Fiyat: {fmt(r['fiyat'])} TL | 5g: %{r['getiri_5']:+.2f} | Endekse fark: %{r['ayrisma']:+.2f} | Hacim: {r['hacim']:.1f}x\n"
            f"   Sebep: {neden}"
        )

    return f"""📡 Bugünün Radar Listesi

BIST 100 son 5 gün: %{endeks_getiri:+.2f}

{chr(10).join(satirlar)}

Okuma:
Radar; endeksten ayrışma, hacim artışı, teknik yapı ve haber etkisini birlikte ölçer."""


def akilli_para_mesaji():
    sonuclar, endeks_getiri = radar_taramasi(limit=12)
    if not sonuclar:
        return "🦈 Akıllı para taramasında yorumlanabilir hareket bulunamadı."

    guclu = [r for r in sonuclar if r["hacim"] >= 1.4 or r["ayrisma"] >= 3]
    if not guclu:
        guclu = sonuclar[:5]

    satirlar = []
    for r in guclu[:8]:
        tip = []
        if r["hacim"] >= 1.4:
            tip.append(f"hacim {r['hacim']:.1f}x")
        if r["ayrisma"] >= 3:
            tip.append(f"endeksten %{r['ayrisma']:.1f} güçlü")
        if not tip:
            tip.append("görece güçlü duruş")

        satirlar.append(f"{r['emoji']} {r['hisse']}: {', '.join(tip)} | Skor {r['skor']}/100")

    return f"""🦈 Akıllı Para Dedektörü

BIST 100 son 5 gün: %{endeks_getiri:+.2f}

{chr(10).join(satirlar)}

📌 Yorum:
Haberden bağımsız hacim artışı ve endeksten pozitif ayrışma, piyasada sessiz para girişi ihtimalini gösterebilir."""


OLAY_HISSE_HARITASI = {
    "petrol": {
        "pozitif": ["TUPRS", "PETKM", "AKSEN"],
        "negatif": ["THYAO", "PGSUS", "TAVHL"],
        "yorum": "Petrol yükselişi enerji tarafını destekleyebilir, havacılıkta maliyet baskısı yaratabilir."
    },
    "savaş": {
        "pozitif": ["ASELS", "KOZAL", "KOZAA"],
        "negatif": ["THYAO", "PGSUS", "TAVHL"],
        "yorum": "Jeopolitik risk savunma ve güvenli liman temasını öne çıkarabilir; havacılık/turizm baskı görebilir."
    },
    "faiz": {
        "pozitif": ["GARAN", "AKBNK", "YKBNK", "ISCTR"],
        "negatif": ["SASA", "HEKTS", "KONTR", "ALFAS"],
        "yorum": "Faiz artışı bankalarda marj beklentisini destekleyebilir; yüksek büyüme/borçlu şirketleri baskılayabilir."
    },
    "dolar": {
        "pozitif": ["FROTO", "TOASO", "TUPRS", "SISE"],
        "negatif": ["THYAO", "PGSUS", "ARCLK"],
        "yorum": "Dolar güçlenmesi ihracatçıları destekleyebilir; döviz maliyeti/borcu yüksek şirketlerde baskı yaratabilir."
    },
    "yapay zeka": {
        "pozitif": ["TCELL", "TTKOM", "KONTR", "ASTOR", "ALFAS"],
        "negatif": [],
        "yorum": "AI/teknoloji teması teknoloji, veri merkezi, enerji altyapısı ve iletişim hisselerini destekleyebilir."
    },
    "altın": {
        "pozitif": ["KOZAL", "KOZAA"],
        "negatif": [],
        "yorum": "Altın yükselişi madencilik ve güvenli liman temasını öne çıkarabilir."
    },
    "çin": {
        "pozitif": ["EREGL", "KRDMD", "SISE"],
        "negatif": [],
        "yorum": "Çin büyümesi ve emtia talebi sanayi/demir çelik tarafını etkileyebilir."
    },
}


def olay_anahtari_bul(metin: str):
    m = temizle_metin(metin)
    if any(k in m for k in ["petrol", "brent", "opec"]):
        return "petrol"
    if any(k in m for k in ["savaş", "savas", "jeopolitik", "iran", "israil", "rusya", "ukrayna"]):
        return "savaş"
    if any(k in m for k in ["faiz", "fed", "tcmb", "merkez bankası", "merkez bankasi"]):
        return "faiz"
    if any(k in m for k in ["dolar", "dxy", "usd"]):
        return "dolar"
    if any(k in m for k in ["yapay zeka", "ai", "nvidia", "çip", "cip"]):
        return "yapay zeka"
    if any(k in m for k in ["altın", "altin", "gold"]):
        return "altın"
    if any(k in m for k in ["çin", "cin", "china"]):
        return "çin"
    return None


def olay_hisse_mesaji(metin: str):
    olay = olay_anahtari_bul(metin)
    if not olay:
        return """🎯 Olay → Hisse Motoru

Örnek:
• Petrol yükselirse kim kazanır?
• İran İsrail gerilimi hangi hisseleri etkiler?
• Dolar yükselirse kim etkilenir?
• Yapay zeka teması BIST'te kimi etkiler?"""

    veri = OLAY_HISSE_HARITASI[olay]
    pozitif = "\n".join(f"🟢 {h}" for h in veri["pozitif"]) if veri["pozitif"] else "Belirgin pozitif eşleşme yok."
    negatif = "\n".join(f"🔴 {h}" for h in veri["negatif"]) if veri["negatif"] else "Belirgin negatif eşleşme yok."

    return f"""🎯 Olay → Hisse Motoru

Konu: {olay.upper()}

📌 Ana Yorum:
{veri['yorum']}

Pozitif Etkilenebilecekler:
{pozitif}

Negatif Etkilenebilecekler:
{negatif}

Not:
Bu eşleşmeler tema bazlıdır. Tek tek hisse analiziyle desteklenmelidir."""


def piyasa_hikayesi_mesaji():
    veriler = makro_veri_cek()
    haberler = global_haber_basliklari(adet=100)
    temalar = global_tema_analizi(haberler)
    risk = makro_risk_skoru(veriler)
    sektorler = sektor_para_akisi(veriler, temalar)

    tema_txt = ", ".join([t for t, s in temalar[:3]]) if temalar else "net bir ana tema yok"
    guclu = [s["sektor"] for s in sektorler if s["durum"] == "Güçlü"]
    zayif = [s["sektor"] for s in sektorler if s["durum"] == "Baskı altında"]

    hikaye = []

    if risk["skor"] >= 60:
        hikaye.append("Bugün piyasa risk almaya daha istekli görünüyor.")
    elif risk["skor"] <= 40:
        hikaye.append("Bugün piyasa daha savunmacı bir ruh halinde.")
    else:
        hikaye.append("Bugün piyasa net yön arıyor; seçici hareket öne çıkıyor.")

    hikaye.append(f"Küresel tarafta ana hikâye {tema_txt} başlıkları etrafında dönüyor.")

    if guclu:
        hikaye.append(f"Para akışında {', '.join(guclu[:3])} tarafı daha güçlü görünüyor.")
    if zayif:
        hikaye.append(f"Baskı altında kalan taraf ise {', '.join(zayif[:3])}.")

    vix = veriler.get("VIX", {}).get("degisim")
    dxy = veriler.get("DXY", {}).get("degisim")
    petrol = veriler.get("Brent Petrol", {}).get("degisim")

    if vix is not None and vix > 3:
        hikaye.append("VIX yükseldiği için piyasada temkin artıyor.")
    if dxy is not None and dxy > 0.4:
        hikaye.append("Doların güçlenmesi gelişen piyasalar için baskı unsuru olabilir.")
    if petrol is not None and petrol > 0.7:
        hikaye.append("Petroldeki yükseliş havacılık ve enflasyon tarafı için negatif okunabilir.")
    elif petrol is not None and petrol < -0.7:
        hikaye.append("Petroldeki gerileme havacılık maliyetleri açısından destekleyici olabilir.")

    sonuc = " ".join(hikaye)

    return f"""💭 Piyasa Hikâyesi

{sonuc}

📌 Özet:
Piyasa şu an sadece tek bir veriye değil; risk iştahı, dolar, petrol, VIX ve haber temalarının birleşimine göre hareket ediyor."""


def radar_komutu_mu(metin: str):
    m = temizle_metin(metin)
    return any(k in m for k in ["radar", "bugünün radar", "bugunun radar", "radar listesi"])


def akilli_para_komutu_mu(metin: str):
    m = temizle_metin(metin)
    return any(k in m for k in ["akıllı para", "akilli para", "gizli hareket", "olağan dışı hacim", "olagan disi hacim", "para girişi", "para girisi"])


def olay_hisse_komutu_mu(metin: str):
    m = temizle_metin(metin)
    return any(k in m for k in ["kim kazanır", "kim kazanir", "hangi hisseleri etkiler", "kimi etkiler", "olay hisse", "etkilenir"])


def piyasa_hikayesi_komutu_mu(metin: str):
    m = temizle_metin(metin)
    return any(k in m for k in ["piyasa hikayesi", "piyasa hikâyesi", "bugünün hikayesi", "bugunun hikayesi", "piyasayı anlat", "piyasayi anlat"])


# =========================
# BES / EMEKLİLİK FONLARI MODÜLÜ
# =========================

BES_TEMA_KELIMELERI = {
    "Altın / Kıymetli Maden": ["altın", "altin", "gold", "kıymetli maden", "kiymetli maden"],
    "Hisse Senedi Fonları": ["hisse", "borsa", "bist", "endeks", "pay senedi"],
    "Para Piyasası": ["para piyasası", "para piyasasi", "likit", "mevduat", "repo"],
    "Borçlanma Araçları": ["tahvil", "bono", "borçlanma", "borclanma", "eurobond"],
    "Döviz / Dolar": ["dolar", "döviz", "doviz", "usd", "euro"],
    "Katılım Fonları": ["katılım", "katilim", "faizsiz"],
    "Devlet Katkısı": ["devlet katkısı", "devlet katkisi", "katkı payı", "katki payi"],
}


def bes_haberleri_cek(adet=8):
    sorgular = [
        "BES bireysel emeklilik fonları haberleri",
        "emeklilik yatırım fonları BES altın hisse para piyasası",
        "BES fon getirileri emeklilik fonları"
    ]
    haberler = []
    gorulen = set()

    for sorgu in sorgular:
        try:
            url = "https://news.google.com/rss/search?q=" + quote(sorgu) + "&hl=tr&gl=TR&ceid=TR:tr"
            feed = feedparser.parse(url)
            for entry in feed.entries[:adet]:
                baslik = BeautifulSoup(entry.title, "html.parser").get_text(" ", strip=True)
                key = baslik.lower()
                if key not in gorulen:
                    gorulen.add(key)
                    haberler.append({
                        "baslik": baslik,
                        "link": getattr(entry, "link", ""),
                        "tarih": getattr(entry, "published", "")
                    })
        except Exception:
            continue

    return haberler[:adet]


def bes_tema_analizi(haberler):
    skorlar = {k: 0 for k in BES_TEMA_KELIMELERI}
    for h in haberler:
        t = h["baslik"].lower()
        for tema, kelimeler in BES_TEMA_KELIMELERI.items():
            if any(k in t for k in kelimeler):
                skorlar[tema] += 1
    return sorted([(k, v) for k, v in skorlar.items() if v > 0], key=lambda x: x[1], reverse=True)


def bes_piyasa_onerisi():
    veriler = makro_veri_cek()
    risk = makro_risk_skoru(veriler)

    altin = veriler.get("Altın", {}).get("degisim")
    bist = None
    try:
        xu = endeks_verisi_cek()
        bist = yuzde_getiri(xu, 5) if xu is not None else None
    except Exception:
        bist = None

    dxy = veriler.get("DXY", {}).get("degisim")
    vix = veriler.get("VIX", {}).get("degisim")

    oneriler = []

    if risk["skor"] >= 60:
        oneriler.append("🟢 Risk iştahı iyi. Hisse senedi ağırlıklı BES fonları izlenebilir.")
    elif risk["skor"] <= 40:
        oneriler.append("🔴 Risk iştahı zayıf. Para piyasası, altın veya daha defansif fonlar öne çıkabilir.")
    else:
        oneriler.append("🟡 Risk iştahı nötr. Dengeli dağılım daha mantıklı görünüyor.")

    if altin is not None:
        if altin > 0.5:
            oneriler.append("🟢 Altın güçlü. Altın / kıymetli maden fonları kısa vadede ilgi görebilir.")
        elif altin < -0.5:
            oneriler.append("🟡 Altın zayıf. Altın fonlarında yeni giriş için aceleci olmamak daha sağlıklı olabilir.")

    if bist is not None:
        if bist > 2:
            oneriler.append(f"🟢 BIST son 5 günde güçlü: %{bist:+.2f}. Hisse fonları destekleniyor.")
        elif bist < -2:
            oneriler.append(f"🔴 BIST son 5 günde zayıf: %{bist:+.2f}. Hisse fonlarında seçici olmak gerekir.")

    if dxy is not None and dxy > 0.4:
        oneriler.append("🟠 Dolar güçleniyor. Döviz/eurobond temalı fonlar izlenebilir; BIST için baskı yaratabilir.")

    if vix is not None and vix > 3:
        oneriler.append("🟠 VIX yükseliyor. Global risk artışı nedeniyle defansif fonlara ilgi artabilir.")

    return risk, oneriler


def bes_mesaji(metin: str = ""):
    haberler = bes_haberleri_cek(adet=8)
    temalar = bes_tema_analizi(haberler)
    risk, oneriler = bes_piyasa_onerisi()

    haber_satirlari = ""
    if haberler:
        haber_satirlari = "\n".join(f"{i}. {h['baslik']}" for i, h in enumerate(haberler[:5], 1))

    tema_satirlari = ""
    if temalar:
        tema_satirlari = "\n".join(f"• {t}: {s}" for t, s in temalar[:5])

    genel_dagilim = []
    if risk["skor"] >= 60:
        genel_dagilim = [
            "Hisse senedi fonları: artırılabilir / izlenebilir",
            "Altın fonları: dengeleyici olarak tutulabilir",
            "Para piyasası fonları: fırsat beklemek için kullanılabilir"
        ]
    elif risk["skor"] <= 40:
        genel_dagilim = [
            "Para piyasası fonları: ağırlık artırılabilir",
            "Altın / kıymetli maden fonları: koruma amaçlı izlenebilir",
            "Hisse fonları: kademeli ve seçici yaklaşım daha mantıklı"
        ]
    else:
        genel_dagilim = [
            "Hisse fonları: sınırlı / dengeli",
            "Altın fonları: portföy dengeleyici",
            "Para piyasası fonları: bekleme ve fırsat alanı"
        ]

    bolumler = [f"🏦 BES / Emeklilik Fonları Yorumu\n\n{risk['emoji']} Piyasa Risk İştahı: {risk['skor']}/100\n📌 {risk['etiket']}"]

    if haber_satirlari:
        bolumler.append("📰 BES Haberleri\n" + haber_satirlari)

    if tema_satirlari:
        bolumler.append("🧠 BES Gündem Temaları\n" + tema_satirlari)

    bolumler.append("📌 Piyasa Koşuluna Göre Fon Fikri\n" + "\n".join("- " + x for x in oneriler))
    bolumler.append("🧺 Genel Dağılım Mantığı\n" + "\n".join("- " + x for x in genel_dagilim))

    bolumler.append("Not: BES uzun vadeli bir sistemdir. Fon değişimi yaparken kısa vadeli dalgalanma yerine risk profili, vade ve dağılım dengesi önemlidir.")

    return "\n\n".join(bolumler).strip()


def bes_komutu_mu(metin: str):
    m = temizle_metin(metin)
    return any(k in m for k in [
        "bes", "bireysel emeklilik", "emeklilik fon", "emeklilik fonları", "emeklilik fonlari",
        "bes haber", "bes haberleri", "bes öneri", "bes önerileri", "bes oneri", "bes onerileri",
        "altın fonu", "altin fonu", "hisse fonu", "para piyasası fonu", "para piyasasi fonu",
        "devlet katkısı", "devlet katkisi", "fon dağılımı", "fon dagilimi",
        "hangi bes", "bes ne durumda", "bes tarafında", "bes tarafinda"
    ])

# =========================
# RENDER KEEP-ALIVE / HEALTH CHECK
# =========================

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write("Borsa Sohbet Bot çalışıyor.".encode("utf-8"))

    def log_message(self, format, *args):
        return


def start_health_server():
    port = int(os.getenv("PORT", "10000"))
    try:
        server = HTTPServer(("0.0.0.0", port), HealthHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        print(f"Health server aktif: {port}")
    except Exception as e:
        print(f"Health server başlatılamadı: {e}")


# =========================
# TELEGRAM
# =========================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Selam 👋 Ben Borsa Sohbet.\n\n"
        "Direkt hisse yazabilirsin:\n"
        "THYAO\n"
        "Ford nasıl\n"
        "Haberler ne diyor ASELS\n\n"
        "Diğer örnekler:\n"
        "neler yapıyorsun\n"
        "rüzgar\n"
        "dünya ne konuşuyor\n"
        "para nereye gidiyor\n"
        "gizli fırsatlar\n"
        "THYAO neden düşüyor\n"
        "Petrol 100 dolar olursa ne olur\n"
        "erken uyarı\n"
        "bugün piyasada ne oluyor\n"
        "güçlü hisseler\n"
        "sinyal kaydet THYAO\n"
        "başarı oranı\n"
        "backtest THYAO\n"
        "radar\n"
        "akıllı para\n"
        "piyasa hikayesi\n"
        "BES haberleri\n"
        "BES önerileri\n"
        "petrol haberleri\n"
        "dolar ne diyor\n"
        "savaş etkisi"
    )


async def yardim(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start(update, context)


async def mesaj_yakala(update: Update, context: ContextTypes.DEFAULT_TYPE):
    metin = update.message.text or ""

    if istek_neler_yapiyorsun(metin):
        await update.message.reply_text(yetenekler_mesaji())
        return

    if bes_komutu_mu(metin):
        await update.message.reply_text("BES haberleri ve fon temalarını inceliyorum...")
        try:
            mesaj = bes_mesaji(metin)
            await update.message.reply_text(mesaj[:3900], disable_web_page_preview=True)
        except Exception as e:
            await update.message.reply_text(f"BES yorumu hazırlanırken hata oluştu: {e}")
        return

    if radar_komutu_mu(metin):
        await update.message.reply_text("Radar listesini tarıyorum...")
        try:
            mesaj = radar_mesaji()
            await update.message.reply_text(mesaj[:3900], disable_web_page_preview=True)
        except Exception as e:
            await update.message.reply_text(f"Radar taraması sırasında hata oluştu: {e}")
        return

    if akilli_para_komutu_mu(metin):
        await update.message.reply_text("Akıllı para hareketlerini tarıyorum...")
        try:
            mesaj = akilli_para_mesaji()
            await update.message.reply_text(mesaj[:3900], disable_web_page_preview=True)
        except Exception as e:
            await update.message.reply_text(f"Akıllı para taraması sırasında hata oluştu: {e}")
        return

    if olay_hisse_komutu_mu(metin):
        await update.message.reply_text("Olayın BIST hisselerine etkisine bakıyorum...")
        try:
            mesaj = olay_hisse_mesaji(metin)
            await update.message.reply_text(mesaj[:3900], disable_web_page_preview=True)
        except Exception as e:
            await update.message.reply_text(f"Olay-hisse analizi sırasında hata oluştu: {e}")
        return

    if piyasa_hikayesi_komutu_mu(metin):
        await update.message.reply_text("Piyasanın hikayesini çıkarıyorum...")
        try:
            mesaj = piyasa_hikayesi_mesaji()
            await update.message.reply_text(mesaj[:3900], disable_web_page_preview=True)
        except Exception as e:
            await update.message.reply_text(f"Piyasa hikayesi hazırlanırken hata oluştu: {e}")
        return

    if sinyal_komutu_mu(metin):
        await update.message.reply_text("Sinyal takip motoruna bakıyorum...")
        try:
            mesaj = sinyal_komutu_mesaji(metin)
            await update.message.reply_text(mesaj[:3900], disable_web_page_preview=True)
        except Exception as e:
            await update.message.reply_text(f"Sinyal takip işlemi sırasında hata oluştu: {e}")
        return

    if backtest_komutu_mu(metin):
        await update.message.reply_text("Geçmiş grafiği ve TP/SL başarı oranlarını inceliyorum...")
        try:
            mesaj = backtest_komutu_mesaji(metin)
            await update.message.reply_text(mesaj[:3900], disable_web_page_preview=True)
        except Exception as e:
            await update.message.reply_text(f"Backtest sırasında hata oluştu: {e}")
        return

    if istek_birlesik_piyasa_raporu(metin):
        await update.message.reply_text("Genel piyasa raporunu hazırlıyorum...")
        try:
            mesaj = bugun_piyasada_ne_oluyor_mesaji()
            await update.message.reply_text(mesaj[:3900], disable_web_page_preview=True)
        except Exception as e:
            await update.message.reply_text(f"Genel piyasa raporu hazırlanırken hata oluştu: {e}")
        return

    if istek_erken_uyari(metin):
        await update.message.reply_text("Makro erken uyarı sinyallerine bakıyorum...")
        try:
            mesaj = erken_uyari_mesaji()
            await update.message.reply_text(mesaj[:3900], disable_web_page_preview=True)
        except Exception as e:
            await update.message.reply_text(f"Erken uyarı yorumlanırken hata oluştu: {e}")
        return

    if istek_sebep_sonuc(metin):
        hisse = hisse_bul(metin)
        if hisse:
            await update.message.reply_text(f"{hisse} için sebep-sonuç analizi yapıyorum...")
            try:
                mesaj = hisse_sebep_sonuc_mesaji(hisse, metin)
                await update.message.reply_text(mesaj[:3900], disable_web_page_preview=True)
            except Exception as e:
                await update.message.reply_text(f"Sebep-sonuç analizi sırasında hata oluştu: {e}")
            return

    if istek_senaryo(metin):
        await update.message.reply_text("Senaryo etkisini yorumluyorum...")
        try:
            mesaj = senaryo_mesaji(metin)
            await update.message.reply_text(mesaj[:3900], disable_web_page_preview=True)
        except Exception as e:
            await update.message.reply_text(f"Senaryo yorumlanırken hata oluştu: {e}")
        return

    if istek_piyasa_ruzgari(metin):
        await update.message.reply_text("Global piyasa rüzgarına bakıyorum...")
        try:
            mesaj = piyasa_ruzgari_mesaji()
            await update.message.reply_text(mesaj[:3900], disable_web_page_preview=True)
        except Exception as e:
            await update.message.reply_text(f"Piyasa rüzgarı yorumlanırken hata oluştu: {e}")
        return

    if istek_dunya_ne_konusuyor(metin):
        await update.message.reply_text("Global haber başlıklarını kokluyorum...")
        try:
            mesaj = dunya_ne_konusuyor_mesaji()
            await update.message.reply_text(mesaj[:3900], disable_web_page_preview=True)
        except Exception as e:
            await update.message.reply_text(f"Global gündem yorumlanırken hata oluştu: {e}")
        return

    if istek_para_akisi(metin):
        await update.message.reply_text("Para akışını yorumluyorum...")
        try:
            mesaj = para_nereye_gidiyor_mesaji()
            await update.message.reply_text(mesaj[:3900], disable_web_page_preview=True)
        except Exception as e:
            await update.message.reply_text(f"Para akışı yorumlanırken hata oluştu: {e}")
        return

    if istek_gizli_firsat(metin):
        await update.message.reply_text("Tema ve gizli fırsat taraması yapıyorum...")
        try:
            mesaj = gizli_firsatlar_mesaji()
            await update.message.reply_text(mesaj[:3900], disable_web_page_preview=True)
        except Exception as e:
            await update.message.reply_text(f"Gizli fırsatlar yorumlanırken hata oluştu: {e}")
        return

    if istek_guclu_hisse(metin):
        await update.message.reply_text("Hisseleri skor motoruyla tarıyorum...")
        try:
            mesaj = guclu_hisseler_tara()
            await update.message.reply_text(mesaj[:3900])
        except Exception as e:
            await update.message.reply_text(f"Tarama sırasında hata oluştu: {e}")
        return

    konu = ekonomik_konu_bul(metin)
    hisse = hisse_bul(metin)

    # Mesaj hem hisse hem konu içeriyorsa hisse analizi öncelikli.
    if hisse:
        await update.message.reply_text(f"{hisse} için bakıyorum...")
        try:
            mesaj = analiz_mesaji_olustur(hisse)
            await update.message.reply_text(mesaj[:3900], disable_web_page_preview=True)
        except Exception as e:
            await update.message.reply_text(f"Analiz sırasında hata oluştu: {e}")
        return

    if konu:
        await update.message.reply_text(f"{KONU_HARITASI[konu]['baslik']} haberlerini tarıyorum...")
        try:
            mesaj = konu_mesaji(konu)
            await update.message.reply_text(mesaj[:3900], disable_web_page_preview=True)
        except Exception as e:
            await update.message.reply_text(f"Haber analizi sırasında hata oluştu: {e}")
        return

    await update.message.reply_text(
        "Hisse kodu, şirket adı veya piyasa konusu yazabilirsin.\n"
        "Örnek: THYAO, Ford, ASELS, güçlü hisseler, petrol, dolar"
    )




# =========================
# RENDER STABİL ÇALIŞMA / HEALTH / WATCHDOG
# =========================

class RenderHealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            self.send_response(200)
            self.send_header("Content-type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"Borsa Sohbet bot is alive.")
        except Exception:
            pass

    def log_message(self, format, *args):
        return


def start_health_server():
    """
    Render Web Service port beklediği için basit health server.
    UptimeRobot bu linki çağırırsa servis daha stabil açık kalır.
    """
    port = int(os.getenv("PORT", "10000"))

    def run():
        try:
            server = HTTPServer(("0.0.0.0", port), RenderHealthHandler)
            print(f"Health server aktif: {port}", flush=True)
            server.serve_forever()
        except OSError as e:
            print(f"Health server uyarı: {e}", flush=True)
        except Exception as e:
            print(f"Health server hata: {e}", flush=True)

    t = threading.Thread(target=run, daemon=True)
    t.start()


def build_application():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN environment variable bulunamadı. Render > Environment içine BOT_TOKEN ekle.")

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("yardim", yardim))
    app.add_handler(CommandHandler("help", yardim))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, mesaj_yakala))

    return app


def run_bot_once():
    """
    Python 3.11/3.12/3.14 uyumlu polling başlatma.
    """
    try:
        asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    app = build_application()
    print("Borsa Sohbet Analist polling başlıyor...", flush=True)
    app.run_polling(
        drop_pending_updates=True,
        close_loop=False,
        allowed_updates=Update.ALL_TYPES,
    )


def main():
    start_health_server()

    while True:
        try:
            run_bot_once()
        except KeyboardInterrupt:
            print("Bot manuel durduruldu.", flush=True)
            break
        except Exception as e:
            print(f"Bot hata aldı, 15 saniye sonra tekrar başlayacak: {repr(e)}", flush=True)
            time.sleep(15)


if __name__ == "__main__":
    main()
