from datetime import date

from vardiya import vardiya_plan as vp


def test_kural_ve_donus():
    assert vp.kural(2)[4] == "(CUMA) 08:00-16:00" and vp.kural(2)[6] == "Hafta Tatili 08"
    assert vp.kural(1)[4] == "24:00-08:00" and vp.kural(1)[6] == "Hafta Tatili 24"
    assert vp.kural(3)[5] == "16:00-24:00" and vp.kural(3)[6] == "Hafta Tatili 16"
    assert [vp.dondur(v) for v in (3, 2, 1)] == [2, 1, 3]


def test_plan_satiri_ve_degisiklik():
    pzt = date(2026, 11, 30)
    cevap = [{"ysicilid": "m17", "ypersonel": "(CUMA) 08:00-16:00"},
             {"ysicilid": 5729, "ypersonel": "ADEM DEMİRCİ", "ysicilno": "16279",
              "y2026x11x30": "08:00-16:00,white,-55_2_59", "y2026x12x01": "08:00-16:00,white,x", "y2026x12x02": "*08:00-16:00,white,x",
              "y2026x12x03": "08:00-16:00,white,x", "y2026x12x04": "(CUMA) 08:00-16:00,white,x", "y2026x12x05": "08:00-16:00,white,x",
              "y2026x12x06": "Hafta Tatili 08,blue,x"}]
    k = vp.plan_satirlari(cevap, pzt)
    assert len(k) == 1 and k[0]["gun"][2] == "08:00-16:00" and vp.vardiya_tahmin(k[0]["gun"]) == 2
    assert vp.degisiklikler(pzt, k[0], 2, {}) == []                      # zaten 2. vardiya: değişiklik yok
    d = vp.degisiklikler(pzt, k[0], 3, {6: "Hafta Tatili 08"})           # 3. vardiya ama Pazar elle korunur
    assert [(g.day, y) for g, _e, y in d] == [(30, "16:00-24:00"), (1, "16:00-24:00"), (2, "16:00-24:00"), (3, "16:00-24:00"),
                                             (4, "16:00-24:00"), (5, "16:00-24:00")]
    assert vp.degisiklikler(pzt, k[0], None, {0: "24:00-08:00"}) == [(pzt, "08:00-16:00", "24:00-08:00")]
