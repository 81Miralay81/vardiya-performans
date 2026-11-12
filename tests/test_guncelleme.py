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


def test_zip_tercih_edilir_ve_icinden_program_cikar(tmp_path, monkeypatch):
    import io, zipfile
    veri = {"body": "SURUM=1.0.40", "assets": [{"name": "VardiyaPerformans.exe", "browser_download_url": "https://x/a.exe"},
                                               {"name": "VardiyaPerformans.zip", "browser_download_url": "https://x/a.zip"}]}
    assert g.release_coz(veri) == ("1.0.40", "https://x/a.zip")
    assert g.release_coz({"body": "SURUM=1.0.40", "assets": veri["assets"][:1]}) == ("1.0.40", "https://x/a.exe")
    tampon = io.BytesIO()
    with zipfile.ZipFile(tampon, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("VardiyaPerformans.exe", b"MZ" + b"\0" * 6_000_000)

    class Yanit(io.BytesIO):
        headers = {"Content-Length": str(len(tampon.getvalue()))}
        def __enter__(self): return self
        def __exit__(self, *a): return False

    monkeypatch.setattr(g.urllib.request, "urlopen", lambda *a, **k: Yanit(tampon.getvalue()))
    hedef = tmp_path / "VardiyaPerformans.exe.yeni"
    g.indir("https://x/a.zip", str(hedef))
    assert hedef.read_bytes()[:2] == b"MZ" and hedef.stat().st_size == 6_000_002
