# Vardiya Performans

Cormind'den alınan Excel listesinden vardiya / makine performans, duruş ve mola raporlarını üretir.
Eski `vardiya_performans.xlsm` dosyasının yerine geçer.

## Kullanım
1. **Veri Aktar** sayfasından Cormind Excel dosyasını seçin (ya da sürükleyin). Aynı kayıt tekrar gelirse çoğalmaz,
   hatalı satırlar atlanır.
2. **Performans / Genel Duruş / Mola** sayfalarında dönemi seçin (Son 7 Gün, Dün, Geçen Hafta, tarih aralığı…).
   Tek tek günleri "Günleri işaretle…" ile çıkarabilirsiniz.
3. **Raporlar** sayfasından günlük / haftalık / aylık raporu seçin, Cormind grafiğini Ctrl+V ile yapıştırın,
   PDF (A3) kaydedin, yazdırın ya da arşive kaydedin.
4. **Ayarlar** sayfasından eşik (%60), süreler, makine listesi ve grup liderlerini değiştirin.

Veri tabanı (`VardiyaPerformans.db`) programın yanında durur; aynı klasörden birden çok kişi açabilir.

## Web portal (tarayıcıdan, ağdaki herkes)
Masaüstü programın tüm sayfaları tarayıcıda da çalışır. Bir bilgisayarda cmd açıp sunucuyu başlatın, diğerleri adresi tarayıcıya yazsın:
```
pip install -r requirements-web.txt     # ilk seferde (ya da portal_baslat.bat dosyasına çift tıklayın)
python main_web.py                       # varsayılan: tüm ağ arayüzleri, port 8443
python main_web.py --port 9000 --db D:\veri\VardiyaPerformans.db
```
Başlarken `http://192.168.x.x:8443` gibi adresler yazılır; aynı ağdaki herkes bu adresi açar. Windows Güvenlik Duvarı sorarsa bu port'a izin verin.
Veri tabanı masaüstü programla **aynı dosya** olabilir (aynı hesap motoru). İsteğe bağlı parola: `set VARDIYA_PAROLA=gizli` (tarayıcı parola ister).
Şirket ağı dışına açmayın: sunucu şifreleme (HTTPS) yapmaz, parola yalnızca basit korumadır.

Web'de olanlar: Veri Aktar (Excel yükleme + Cormind'den çekim), Kayıtlar (bozuk süzgeci, silme), Performans / Çalışma / Genel Duruş / Mola, Operatör,
Raporlar (günlük/haftalık/aylık/dönem, şef atama, Cormind grafiği yapıştırma, A3 yazdır/PDF, arşiv, KOT + idari özet), Geçmiş, Ayarlar.
Web'de henüz olmayanlar: Outlook'tan mail okuma ve Gemini ile KOT çevirme, "operatör varken duran makineler" listesi, 3 boyutlu grafikler,
otomatik güncelleme. PDF, tarayıcının "Yazdır → PDF olarak kaydet" özelliğiyle alınır. Masaüstünde oluşan arşiv kayıtları (PDF'siz) web'de açılmaz.

## Hesap kuralları
* Net vardiya süresi = 480 dk − 30 dk yemek − 10 dk çay = **7,33 saat** (Ayarlar'dan değişir).
* Kayıtlar vardiya sınırlarında (00:00 / 08:00 / 16:00) bölünür; her parça kendi gün ve vardiyasına yazılır.
* Aynı anda birden fazla kayıt varsa (örn. "Çalışmıyor" üstüne "Kurulum") o an **bir kez** sayılır:
  Çalışma > Mola > Duruş.
* **%60 kuralı her gün, her vardiya için ayrı** uygulanır: o gün o vardiyada çalışma oranı eşiği geçen makine sayılır.
* Haftalık / aylık makine sayısı ve vardiya ortalaması, **günlük değerlerin ortalamasıdır**.
* Hiç kaydı olmayan gün (tatil) ya da hiçbir makinenin eşiği geçemediği vardiya ortalamaya girmez, raporda belirtilir.
* Duruş ve mola oranı, o gün o vardiyada eşiği geçen makinelerden hesaplanır.

## Geliştirme
```
pip install -r requirements.txt pytest
python -m pytest -q tests        # hesap motoru + içe aktarma testleri
python main.py                   # çalıştır
python main.py --kendini-sina    # ekran açmadan tüm sayfaları + PDF'i dener (CI bunu exe'ye de uygular)
```
`VARDIYA_ORNEK=<örnek xlsm>` ortam değişkeni verilirse hesap testleri Excel'deki 3 Kasım sonuçlarıyla karşılaştırır.
Exe, GitHub Actions ile (Windows) derlenir; çıktı "Actions → Artifacts" ve "Releases → guncel" altındadır.

## Otomatik güncelleme

Program açıldıktan birkaç saniye sonra GitHub'daki `guncel` sürümünü arka planda denetler. Yeni sürüm varsa indirir, "Güncelle" denince kapanır, exe'nin yerine yenisini koyar ve programı yeniden açar. İnternet yoksa sessizce atlanır.
Not: depo özel (private) ise bu denetim yetki olmadan sürümü okuyamaz; güncelleme için depo herkese açık olmalı (ya da başka bir dağıtım yolu seçilmeli).
