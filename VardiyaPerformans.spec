# -*- mode: python ; coding: utf-8 -*-
# Tek exe, web grafikli. Boyut için web motorunun kullanılmayan dil dosyaları, geliştirici araçları ve
# Qt çevirileri (Türkçe ve İngilizce dışındakiler) çıkarılır. Açılışta başlatıcı penceresi (assets/acilis.png)
# exe'nin kendini açtığı sırada dosya adlarını gösterir.

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[('assets', 'assets')],
    hiddenimports=['win32timezone', 'win32com.client', 'PySide6.QtWebEngineWidgets', 'PySide6.QtWebEngineCore'],
    excludes=['PySide6.Qt3DCore', 'PySide6.Qt3DRender', 'PySide6.QtQuick3D', 'PySide6.QtCharts', 'PySide6.QtDataVisualization',
              'PySide6.QtGraphs', 'PySide6.QtMultimedia', 'PySide6.QtMultimediaWidgets', 'PySide6.QtBluetooth', 'PySide6.QtNfc',
              'PySide6.QtSensors', 'PySide6.QtSerialPort', 'PySide6.QtSerialBus', 'PySide6.QtTextToSpeech', 'PySide6.QtSpatialAudio',
              'PySide6.QtRemoteObjects', 'PySide6.QtScxml', 'PySide6.QtLocation', 'PySide6.QtHttpServer', 'PySide6.QtDesigner',
              'PySide6.QtHelp', 'PySide6.QtSql', 'PySide6.QtTest', 'PySide6.QtUiTools', 'PySide6.QtSvgWidgets'],
    noarchive=False,
)


def gerekli(yol: str) -> bool:
    y = yol.replace('\\', '/').lower()
    if 'qtwebengine_locales/' in y:
        return y.endswith('/tr.pak') or y.endswith('/en-us.pak')
    if 'qtwebengine_devtools_resources' in y:
        return False
    if '/translations/' in y and y.endswith('.qm'):
        return y.endswith('_tr.qm') or y.endswith('_en.qm')
    return True


once = sum(1 for _ in a.datas)
a.datas = [d for d in a.datas if gerekli(d[0])]
a.binaries = [b for b in a.binaries if gerekli(b[0])]
print(f'VARDIYA: {once - len(a.datas)} gereksiz dosya çıkarıldı')

pyz = PYZ(a.pure)
splash = Splash('assets/acilis.png', binaries=a.binaries, datas=a.datas, text_pos=(26, 196), text_size=9,
                text_color='#6b7285', text_default='Hazırlanıyor…', minify_script=True, always_on_top=False)
exe = EXE(
    pyz, a.scripts, splash, splash.binaries, a.binaries, a.datas, [],
    name='VardiyaPerformans', debug=False, bootloader_ignore_signals=False, strip=False, upx=False,
    runtime_tmpdir=None, console=False, icon='assets/uygulama.ico', version='surum_bilgisi.txt',
)
