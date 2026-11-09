from vardiya import guncelleme as g


def test_surum_karsilastirma():
    assert g.daha_yeni("1.0.12", "1.0.9")
    assert not g.daha_yeni("1.0.9", "1.0.9")
    assert not g.daha_yeni("1.0.8", "1.0.9")
    assert g.daha_yeni("1.1.0", "1.0.99")
    assert not g.daha_yeni("", "1.0.0")


def test_release_coz():
    veri = {"body": "SURUM=1.0.7", "assets": [{"name": "VardiyaPerformans.exe", "browser_download_url": "https://x/y.exe"}]}
    assert g.release_coz(veri) == ("1.0.7", "https://x/y.exe")
    assert g.release_coz({"body": "yok", "assets": []}) is None
    assert g.release_coz({"body": "SURUM=1.0.7", "assets": [{"name": "baska.zip", "browser_download_url": "u"}]}) is None


def test_bat_icerigi():
    b = g.bat_icerigi(r"Z:\a\VardiyaPerformans.exe.yeni", r"Z:\a\VardiyaPerformans.exe")
    assert 'move /Y "Z:\\a\\VardiyaPerformans.exe.yeni" "Z:\\a\\VardiyaPerformans.exe"' in b
    assert 'start "" "Z:\\a\\VardiyaPerformans.exe"' in b


def test_indir_gecersiz_dosyayi_reddeder(tmp_path, monkeypatch):
    import io, pytest

    class Yanit(io.BytesIO):
        headers = {"Content-Length": "5"}
        def __enter__(self): return self
        def __exit__(self, *a): return False

    monkeypatch.setattr(g.urllib.request, "urlopen", lambda *a, **k: Yanit(b"HTML!"))
    with pytest.raises(ValueError):
        g.indir("https://x", str(tmp_path / "a.exe"))
    assert not (tmp_path / "a.exe").exists()
