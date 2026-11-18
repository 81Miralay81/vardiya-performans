"""Vardiya Performans — web portal başlatıcısı (cmd'den çalıştırılır, Qt/ekran kütüphanesi gerekmez).

    python main_web.py                  # 0.0.0.0:8443, veri tabanı bu klasörde VardiyaPerformans.db
    python main_web.py --port 9000 --db D:\\veri\\VardiyaPerformans.db
Ağdaki herkes tarayıcıdan  http://<bu bilgisayarın IP'si>:8443  adresini açar (adresler başlarken yazılır).
"""
import argparse
import os
import sys


def uygulama_klasoru() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def main() -> int:
    ap = argparse.ArgumentParser(description="Vardiya Performans web portalı")
    ap.add_argument("--port", type=int, default=int(os.environ.get("VARDIYA_PORT", "8443")), help="dinlenecek port (varsayılan 8443)")
    ap.add_argument("--ev", default="0.0.0.0", help="dinlenecek adres (varsayılan: tüm ağ arayüzleri)")
    ap.add_argument("--db", default=os.environ.get("VARDIYA_DB") or os.path.join(uygulama_klasoru(), "VardiyaPerformans.db"),
                    help="SQLite veri tabanı yolu (masaüstü programla aynı dosya kullanılabilir)")
    a = ap.parse_args()
    from vardiya import portal
    return portal.baslat(a.db, a.port, a.ev)


if __name__ == "__main__":
    sys.exit(main())
