from datetime import datetime, timedelta

from vardiya import oto_cekim


class _Pencere:
    def __init__(self):
        self.kapandi = False
        self._bitince = lambda *a: None

    def close(self):
        self.kapandi = True


class _Oto:
    _pv_takildi_mi = oto_cekim.OtoCekim._pv_takildi_mi

    def __init__(self):
        self._pv_pencere = None


def _oto():
    return _Oto()


def test_takilan_cekim_temizlenir(monkeypatch):
    from vardiya import teshis
    monkeypatch.setattr(teshis, "adim", lambda *a, **k: None)
    o = _oto()
    assert o._pv_takildi_mi() is False
    w = _Pencere()
    o._pv_pencere, o._pv_basla = w, datetime.now()
    assert o._pv_takildi_mi() is True                     # yeni başladı: bekle
    o._pv_basla = datetime.now() - timedelta(minutes=oto_cekim.PV_EN_UZUN_DK + 1)
    assert o._pv_takildi_mi() is False and o._pv_pencere is None and w.kapandi
