#!/usr/bin/env python3
"""
IZSU ariza kaynakli su kesintisi poller.
Calisma mantigi:
1. Birincil API'yi dene. 500/baglanti hatasi alirsan CKAN yedek API'yi dene.
2. Ikisi de basarisizsa uyari yazip exit 0 ile cik (API'nin cokuk olmasi
   workflow'u kirmiziya dusurmesin - bu dis servis sorunu, script hatasi degil).
3. Basariliysa: takip edilen ilce/mahalle listesine gore filtrele.
4. state.json dosyasindaki onceki listeyle karsilastir.
5. Yeni kayit varsa ntfy.sh uzerinden push bildirimi gonder.
6. state.json guncelle (repo icinde tutulur, GitHub Actions commit atar).
"""
import json
import sys
import time
import urllib.error
import urllib.request

API_URL = "https://openapi.izmir.bel.tr/api/izsu/arizakaynaklisukesintileri"
# Birincil API cokerse (500) buradan deneriz - CKAN datastore_search
CKAN_URL = (
    "https://acikveri.bizizmir.com/api/3/action/datastore_search"
    "?resource_id=adecfa0d-3f19-427f-bf40-25117921f938&limit=1000"
)
STATE_FILE = "state.json"

# TAKIP EDILECEK ILCE/MAHALLE ANAHTAR KELIMELERI - kendi bolgene gore duzenle
TAKIP_LISTESI = ["Karabaglar"]

# ntfy.sh konu adi - kendine ozel, tahmin edilemez bir isim sec
NTFY_TOPIC = "izsu-kesinti-987654321"


def _get(url: str, deneme: int = 3):
    son_hata = None
    for i in range(deneme):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=15) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:
            son_hata = e
            time.sleep(2 * (i + 1))
    raise son_hata


def veri_cek() -> list:
    """Birincil API'yi dener, basarisizsa CKAN yedegine duser. Liste dondurur."""
    try:
        veri = _get(API_URL)
        if isinstance(veri, dict):
            for anahtar in ("data", "sonuc", "kayitlar", "result"):
                if anahtar in veri and isinstance(veri[anahtar], list):
                    return veri[anahtar]
            raise ValueError(f"Beklenmeyen sozluk formati, anahtarlar: {list(veri.keys())}")
        return veri
    except Exception as e1:
        print(f"UYARI: birincil API basarisiz ({e1}), CKAN yedegi deneniyor.", file=sys.stderr)
        veri = _get(CKAN_URL)
        kayitlar = veri.get("result", {}).get("records", [])
        if not kayitlar:
            raise ValueError("CKAN yedeginden de kayit alinamadi.")
        return kayitlar


def kayit_id(kayit: dict) -> str:
    return json.dumps(kayit, sort_keys=True, ensure_ascii=False)


def filtrele(veri: list) -> list:
    sonuc = []
    for kayit in veri:
        metin = json.dumps(kayit, ensure_ascii=False).lower()
        if any(k.lower() in metin for k in TAKIP_LISTESI):
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
        veri = veri_cek()
    except Exception as e:
        print(f"UYARI: veri alinamadi, bu calisma atlaniyor: {e}", file=sys.stderr)
        return

    filtreli = filtrele(veri)
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
