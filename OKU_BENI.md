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
