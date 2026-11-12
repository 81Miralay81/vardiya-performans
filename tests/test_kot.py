from datetime import date

from vardiya.kot import idari_icerik, kot_coz, metne_cevir

# Copilot çıktısı gibi: satır sonları kaybolmuş, bir satırda "TEZGAHLAR:" yazım hatası var (uydurma örnek)
ORNEK = ("=== KOT === KOT NO: 2026-1107-0732 TARIH: 07.11.2026 SAAT: 07:32 VARDIYA: 1 KONU: OEE ler hk. GRUP LIDERI: - "
         "--- TEZGAHLAR --- TEZGAH: IM54 | KOD: - | OLAY SAATI: - | KATEGORI: SETUP | NEDEN: Setup fazla oldu | "
         "ACIKLAMA: Deneme kalıpları işleniyor, setup fazla oldu. | AKSIYON: - "
         "TEZGAHLAR: IM56 | KOD: - | OLAY SAATI: 01:00 | KATEGORI: PLANLAMA | NEDEN: Mevcut iş bitti | "
         "ACIKLAMA: 01:00'da mevcut iş bittiğinden planlı duruşa alındı. | AKSIYON: Sıradaki iş hazırlanmalı "
         "--- SONUC --- Setup ve planlı duruş nedeniyle OEE düşük çıkmıştır. DURUM: ACIK === SON ===\n\n"
         "=== KOT ===\nKOT NO: 2026-1110-2344\nTARIH: 10.11.2026\nSAAT: 23:44\nVARDIYA: 9\nKONU: OEE HAK;\nGRUP LIDERI: Ali Veli\n"
         "--- TEZGAHLAR ---\nTEZGAH: im 60 | KOD: CNC5 | OLAY SAATI: - | KATEGORI: Revizyon | NEDEN: Uyumsuzluk 【1-ab】 | "
         "ACIKLAMA: Parçalar arasında farklılık vardı. | AKSIYON: -\n--- SONUC ---\nAçıklamalardan dolayı OEE düşük.\nDURUM: TAMAMLANDI\n=== SON ===\nTOPLAM KOT: 2")


def test_kot_coz():
    k = kot_coz(ORNEK)
    assert len(k) == 2
    a, b = k
    assert a.no == "2026-1107-0732" and a.tarih == date(2026, 11, 7) and a.vardiya == 1 and a.lider == ""
    assert [t.tezgah for t in a.tezgahlar] == ["IM54", "IM56"]
    assert a.tezgahlar[0].kategori == "SETUP" and a.tezgahlar[0].aksiyon == "" and "setup fazla" in a.tezgahlar[0].aciklama
    assert a.tezgahlar[1].kategori == "PLANLAMA" and a.tezgahlar[1].olay_saati == "01:00" and a.tezgahlar[1].aksiyon == "Sıradaki iş hazırlanmalı"
    assert a.sonuc.startswith("Setup ve planlı") and a.durum == "ACIK"
    assert b.vardiya == 3 and b.lider == "Ali Veli" and b.durum == "TAMAMLANDI"      # vardiya saatten hesaplanır
    assert b.tezgahlar[0].tezgah == "IM60" and b.tezgahlar[0].kategori == "REVIZYON" and b.tezgahlar[0].neden == "Uyumsuzluk"


def test_idari_icerik():
    k = kot_coz(ORNEK)
    cm = {"IM54": {"oee": 46.0, "durus": {"SETUP": 40.0}, "mola": -9.0, "toplam": 54.0},
          "IM56": {"oee": 70.0, "durus": {"İŞ EMRİ PLAN YOK": 30.0}, "mola": -9.0, "toplam": 30.0},
          "IM60": {"oee": 90.0, "durus": {"SETUP": 10.0}, "mola": -9.0, "toplam": 10.0},
          "IM21": {"oee": 60.0, "durus": {"Çalışmıyor": 40.0}, "mola": -9.0, "toplam": 40.0},
          "IM27": {"oee": 100.0, "durus": {}, "mola": -9.0, "toplam": -9.0}}
    ic = idari_icerik(k, cm, {"IM54": 0.5})
    assert [p["tezgah"] for p in ic["perf"]] == ["IM54", "IM21", "IM56", "IM60"]       # IM27 hedefte ve notsuz: yok
    assert ic["perf"][0]["durum"] == "Kritik düşük" and ic["perf"][1]["kayip"] == "Çalışmıyor"
    assert abs(sum(x["pay"] for x in ic["kok"]) - 100) < 1e-6 and ic["kot_sayisi"] == 2
    assert any("IM56: Sıradaki iş hazırlanmalı" in o for o in ic["oneriler"])
    assert "ÖNE ÇIKAN KÖK NEDENLER" in metne_cevir(ic)
    bos = idari_icerik([], cm, {})
    assert "KOT kaydı yok" in bos["ozet"] and bos["kok"] == []
