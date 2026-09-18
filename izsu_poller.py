#!/usr/bin/env python3
"""
IZSU ariza ve bakim bilgisi sorgulama sayfasindan (izsu.gov.tr) veri ceker.
Bu sayfa JSON API degil, HTML tablo dondurur - BeautifulSoup ile parse edilir.

Calisma mantigi:
1. Sayfayi GET ile cek (retry ile, 3 deneme).
2. "Ariza Bilgileri" ve "Planli Bakim Bilgileri" tablolarini parse et.
3. Takip edilen ilce listesine gore filtrele.
4. state.json'daki onceki listeyle karsilastir, yeni kayit varsa ntfy.sh ile bildir.
5. state.json guncelle.
"""
import json
import sys
import time
import urllib.request

from bs4 import BeautifulSoup

PAGE_URL = "https://izsu.gov.tr/bilgi-merkezi/ariza-ve-bakim-bilgisi-sorgulama"
STATE_FILE = "state.json"

# TAKIP EDILECEK ILCE ADLARI (BUYUK HARF, Turkce karakter kullanma - siteyle birebir eslemesi icin
# once script'i calistirip ciktidaki ilce adlarina bak, gerekirse duzelt)
TAKIP_LISTESI = ["KARABAGLAR", "KARABAĞLAR"]

# ntfy.sh konu adi - kendine ozel, tahmin edilemez bir isim sec
NTFY_TOPIC = "izsu-kesinti-987654321"


def sayfa_cek(deneme: int = 3) -> str:
    son_hata = None
    for i in range(deneme):
        try:
            req = urllib.request.Request(PAGE_URL, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=20) as r:
                return r.read().decode("utf-8")
        except Exception as e:
            son_hata = e
            time.sleep(3 * (i + 1))
    raise son_hata


def tablolari_parse_et(html: str) -> list:
    """Sayfadaki tum tablolari satir satir sozluk listesine cevirir."""
    soup = BeautifulSoup(html, "html.parser")
    kayitlar = []
    for tablo in soup.find_all("table"):
        basliklar = [th.get_text(strip=True) for th in tablo.find_all("th")]
        if not basliklar:
            continue
        for tr in tablo.find_all("tr"):
            hucreler = [td.get_text(strip=True) for td in tr.find_all("td")]
            if not hucreler or len(hucreler) != len(basliklar):
                continue
            kayit = dict(zip(basliklar, hucreler))
            kayitlar.append(kayit)
    return kayitlar


def kayit_id(kayit: dict) -> str:
    return json.dumps(kayit, sort_keys=True, ensure_ascii=False)


def filtrele(kayitlar: list) -> list:
    sonuc = []
    for kayit in kayitlar:
        metin = json.dumps(kayit, ensure_ascii=False).upper()
        if any(k in metin for k in TAKIP_LISTESI):
            sonuc.append(kayit)
    return sonuc


def eski_state_oku() -> set:
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return set(json.load(f))
    except FileNotFoundError:
        return set()


def state_yaz(id_seti: set) -> None:
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(sorted(id_seti), f, ensure_ascii=False, indent=2)


def bildirim_gonder(baslik: str, mesaj: str) -> None:
    req = urllib.request.Request(
        f"https://ntfy.sh/{NTFY_TOPIC}",
        data=mesaj.encode("utf-8"),
        headers={"Title": baslik.encode("utf-8"), "Priority": "high"},
        method="POST",
    )
    urllib.request.urlopen(req, timeout=15)


def main():
    try:
        html = sayfa_cek()
        kayitlar = tablolari_parse_et(html)
    except Exception as e:
        print(f"UYARI: veri alinamadi, bu calisma atlaniyor: {e}", file=sys.stderr)
        return

    if not kayitlar:
        print("UYARI: sayfa acildi ama tablo bulunamadi - site yapisi degismis olabilir.", file=sys.stderr)
        return

    filtreli = filtrele(kayitlar)
    guncel_id_seti = {kayit_id(k) for k in filtreli}
    eski_id_seti = eski_state_oku()

    yeni_kayitlar = [k for k in filtreli if kayit_id(k) not in eski_id_seti]

    if yeni_kayitlar:
        for k in yeni_kayitlar:
            mesaj = json.dumps(k, ensure_ascii=False, indent=2)
            bildirim_gonder("Izmir Su Kesintisi", mesaj[:1000])
        state_yaz(guncel_id_seti)
        print(f"{len(yeni_kayitlar)} yeni kayit bulundu, bildirim gonderildi.")
    else:
        print("Yeni kayit yok.")
        if not eski_id_seti and guncel_id_seti:
            state_yaz(guncel_id_seti)


if __name__ == "__main__":
    main()
