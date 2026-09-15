#!/usr/bin/env python3
"""
IZSU ariza kaynakli su kesintisi poller.
Calisma mantigi:
1. API'den mevcut kesinti listesini cek.
2. Takip edilen ilce/mahalle listesine gore filtrele.
3. state.json dosyasindaki onceki listeyle karsilastir.
4. Yeni kayit varsa ntfy.sh uzerinden push bildirimi gonder.
5. state.json guncelle (repo icinde tutulur, GitHub Actions commit atar).
"""
import json
import sys
import urllib.request

API_URL = "https://openapi.izmir.bel.tr/api/izsu/arizakaynaklisukesintileri"
STATE_FILE = "state.json"

# TAKIP EDILECEK ILCE/MAHALLE ANAHTAR KELIMELERI - kendi bolgene gore duzenle
TAKIP_LISTESI = ["Bornova", "Karsiyaka", "Gulyaka", "Reis", "Refet Bele", "Karabaglar"]

# ntfy.sh konu adi - kendine ozel, tahmin edilemez bir isim sec
NTFY_TOPIC = "izsu-kesinti-987654321"


def veri_cek():
    req = urllib.request.Request(API_URL, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode("utf-8"))


def kayit_id(kayit: dict) -> str:
    # API alan adlari dogrulanana kadar tum kaydi string'e cevirip hash gibi kullan
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
    veri = veri_cek()
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
        # state degismediyse bile ilk calistirmada dosya yoksa yaz
        if not eski_id_seti and guncel_id_seti:
            state_yaz(guncel_id_seti)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"HATA: {e}", file=sys.stderr)
        sys.exit(1)
