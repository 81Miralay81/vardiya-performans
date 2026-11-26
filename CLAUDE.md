# Vardiya Performans — proje haritası (Claude için)

Bu dosya yalnızca geliştirici (Claude) içindir; program okumaz. Her önemli değişiklikten sonra güncelle.

## Kullanıcının kuralları (her zaman)
- Yanıtlar **Türkçe**; İngilizce terim zorunluysa Türkçe açıkla.
- **Talimat almadan başlama.** "not al" / "bekle" → yalnızca not, kod yok. "başla" → yap. "derle" → ana dala (main) gönder.
- **main'e yalnızca "derle" denince** gönder (her push GitHub Actions'ta derler ve "guncel" sürümünü yayınlar). Diğer işler yan dalda.
- Anlamadığın yer olursa sor.
- Ekranlarda ve dosya adlarında **"Meyer" ve "PDKS" kelimeleri kullanılmaz** → "Personel Veri" / "Personel Durum".
- Şifre, anahtar, çerez değerlerini asla isteme/görme. Program kendi bilgisayarında saklar (QSettings base64).
- Kaydedilmeyecek kişisel veri: adres, e-posta, doğum tarihi, kan grubu, kart no, firma geneli liste, anahtarlar.
- Kullanıcı işte claude.ai artifact bağlantısı açamaz → görsel taslakları PNG gönder (SendUserFile).
- Commit sonu: `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` ve `Claude-Session: https://claude.ai/code/session_012PPnjdFjZ6fw174CQBVnSQ`

## Ortam
- Exe ve SQLite veri tabanı NAS'ta: `\\KALIPNAS2019\kaliphanenas\OMUR\vardiyaperformans\` (VardiyaPerformans.exe / .db).
- Kullanıcının bilgisayarı: **PC-KALIP18** (Windows). Exe içinde web sunucusu (iç ağ, ör. http://192.168.3.47:8090).
- Sürüm: Actions her main push'ta `1.0.N` üretir; yayın etiketi `guncel`. Program açılışta güncellemeyi indirir.
- Testler: `python3 -m pytest -q tests` (çoğu `tests/test_personel_veri.py`). Ekransız deneme: `QT_QPA_PLATFORM=offscreen`.
- Teşhis: açılış kaydı (`teshis.py`, `%LOCALAPPDATA%`), Personel Veri penceresinde "Tanı kaydını kaydet" → `personel_veri_tani.txt`.

## Dosya haritası (vardiya/)
| Dosya | Görev |
|---|---|
| main.py | giriş; `pencere.giris()` sonra ana pencere |
| pencere.py | ana pencere, sol menü, `yetki_uygula`, `menu_izinli`, köprü etiketi |
| veritabani.py | SQLite, `ayar_oku/ayar_yaz` (ayar_gecmis kaydı), `okuma_baglantisi` (kalıcı okuma bağlantısı + kilit) |
| hesap.py | Cormind vardiya hesap motoru; vardiyalar 1=00–08, 2=08–16, 3=16–24 |
| operator_vardiya.py | Cormind operatörünü kendi vardiyasına bağlar (`bagla`): ad → personel eşleştirme (Ayarlar `op_eslestirme` elle tablo önce), plan dışı parça ≥ `pv_fazla_en_az_dk` → "ad (mesai)", altı → operatörsüz; listede yoksa "ad (kalıphane dışı)". `temel_ad` etiketi atar |
| kirilim.py | Performans kırılımları; `donem_kayitlari`, `operator_ayrinti`, `VARDIYA_SAAT` |
| sayfa_performans.py | Performans sayfası, kırılım seviye 1–5 (operatör → makine/zaman grafikleri → zaman çizelgesi) |
| zaman_cizelgesi.py | gank çizelgesi (Ay/Hafta/Gün/Saat, tekerlek, sürükle, alan seç) |
| cizim.py / cizim_ek.py | QPainter grafikler; `_web(p, rect, "ad", locals())` → web_secenek'teki ECharts karşılığı |
| web_secenek.py | ECharts seçenek yapıcıları (`YAPICILAR`) |
| web_sunucu.py | iç ağ web sunucusu + `/api/...` uçları, `YETKI` haritası, oturum çerezi `vp_oturum` |
| assets/web/uygulama.html | tarayıcı uygulaması (tek sayfa; Performans, Personel Durum, kart, operatör ayrıntısı) |
| kullanici.py | kullanıcılar (pbkdf2), `EKRANLAR` + `OZELLIKLER` yetkileri, `etkin_yetkiler` (eski kayıtları açar, `_v2` işareti) |
| oto_cekim.py | Cormind otomatik çekimi + **personel verisi otomatik çekimi** (`pv_plan`: sabah 08:29 dün+bugün, akşam 20:00 dün teyit; `pv_en_eski` 01.07.2026) |
| personel_veri.py | personel verisi veri katmanı (tablolar, ayrıştırma, sınıflandırma, özet, kart özeti) |
| personel_pencere.py | Personel Veri penceresi (Meyer sayfası gömülü QWebEngine) — öğrenme, otomatik çekim, ekran yolu, izin formu yolu |
| sayfa_personel.py | Personel Durum sayfası (Devam özeti, Vardiya listesi, Sıralamalar, Personel kartı) |
| ozet_gorsel.py | personel kartı görsel özeti (halka, 5 kutu tıklanınca gün listesi, çubuklar, gün şeridi) |
| sayfa_ayar.py | Ayarlar (personel veri saatleri/en eski tarih, kullanıcılar, mola yedekleri, köprü kartı) |
| sayfa_veri.py | Veri Aktar (Cormind bölümü `cormind`, personel bölümü `pv_satir`; yetkiye göre gizlenir) |
| kopru.py | **GEÇİCİ** geliştirici köprüsü (iş bitince kaldırılacak) |
| teshis.py | açılış kaydı, donma bekçisi |

## Personel verisi (kaynak: meyer.teknorot.com, AngularJS, API meyerapi.teknorot.com)
- Program sayfanın kendi XHR/fetch yanıtlarını yakalar (`_YAKALA` betiği, konsol iletisi `VPPV|...`). Başlıklar yalnızca sayfada (`__vpB`, adres başına `__vpBY`).
- Öğrenilen istek şablonları: QSettings `pveri/sablon/<tur>` (u, m, b, ct, sayfa). Türler: `liste_hepsi`, `liste_aktif`, `bakiye`, `kisi_karti`, `giris_cikis`.
- **Pivot (TAPIVOT)**: tarih istekte şifreli (`Name=SCI!...`) → **ekran yolu**: `#!/pdkspiv` ekranında önce "Ay" bağlantısı + ◀ ▶ oklarıyla ay seçilir, olmazsa tarih kutularına yazılır (kutular: ng-model `bugun`, `yarin`), sonra "Planlanan + Gerçekleşen" düğmesi. Aylar **mevcut aydan geriye** çekilir. Sayfa **alta kaydırılmaz**. Pivot yüklenene kadar beklenir (bekleyen istek sayacı `__vpBekleyen`).
- Büyük aralıkta ("Görüntüleme sınırı aşımı") hücreler saatsiz/2 satırlı gelir → `eksik_liste_mi` reddeder; 2 satırlı hücre gerçekleşen sayılmaz.
- Hücre biçimi: `plan<br>plankod [izinkod]<br>giriş çıkış<br>…<br>GuE,renk,…`. `pv_gun` alan alan birleştirilir (yeni saat boşsa eskisi kalır; mükerrer olmaz).
- İzin bakiyesi (`GET /api/Dynamic`) ve kişi kartı (`POST /api/PersonD`) kişi numarası şifreli → istekle tekrar edilemez → **izin formu yolu**: Sicil Liste ekranı `#!/sicil_pdks`, Sicil No sütunu süzgecine sicil no yaz (ID sütununda süzgeç yok), tek satırı işaretle, "İzin Talep Formu"nu aç, iki yanıtı bekle, × ile kapat, işareti kaldır. Kaydet'e asla basılmaz. Eksik kalan varsa çekim "tamam" sayılmaz.
- Meyer'deki **kalan izin günleri doğru değil** (kullanıcı söyledi) — gösterim kararı bekliyor.
- Kaynakta 01.07.2026 öncesi veri yok.
- Tablolar: `pv_personel` (sicilid, ad, sicilno, pozisyon, yaka, vardiya düzeni, giris_tarih, telefon, foto, cikis_tarih), `pv_gun` (PK sicilid+gun), `pv_izin_tur`, `pv_bakiye`.
- **Grup lideri türü**: `pv_lider_tur` {sicilid: "CNC"|"Mekanik"} (varsayılan CNC). Performans şefleri `cnc_liderleri` → `veritabani.sef_getir` (yalnız CNC, personel vardiya listesinden).
- **Ayrılan personel** (`cikis_tarih` dolu): sayıya, devam oranına, toplamlara, vardiya listesine, sıralamalara girmez; Sıralamalar'da ayrı "Ayrılan personel" kartı; "Ayrılanları göster" kutusu listeyi açar.
- **Devam özeti kutuları** tıklanır: `devam_gun_listeleri` (gelmedi/gec/erken/fazla/izin gün listeleri) → altta liste; devam oranı → pasta penceresi (geldi / izinsiz gelmedi / izinli), dilim → ayrıntı. Web'de `/api/personel` → `liste`.
- Yetki `personel_kimlik`: fotoğraf, telefon, yıllık izin (yoksa gizli). Yıllık izin satırları `izin_satirlari` (toplam = kalan + kullanılan + planlanan).
- Yetki `personel_beyaz`: yoksa beyaz yaka personel (yaka "BEYAZ YAKA") hiç görünmez — `yaka_suz` (exe `yenile`, web `_pv_temel`), grup lideri adları `ad_suz`, foto ucu da kapalı.
- **Vardiya adları (kullanıcının numarası)**: 1. vardiya 00–08, 2. vardiya 08–16, 3. vardiya 16–00. İç kodlar personel verisinden: "1"=08–16, "2"=16–00, "3"=00–08 → ekranda `VARDIYA_AD`/`VARDIYA_KISA`, sıra `VARDIYA_SIRA` ("3","1","2","G"). "24" yazılmaz (`plan_kisa` 16–00).
- **Kayan çıkış**: 16–00 vardiyasının gece yarısından sonraki çıkışı kaynakta ertesi güne yazılır → `kayan_cikislari_duzelt` (donem_hesabi içinde) önceki güne taşır.
- **Operatör esnemesi**: plan ± `pv_fazla_en_az_dk` (yarım saat) kendi vardiyası; dışı ≥5 dk → "(mesai)". Geç gelme / erken çıkma tespitini ETKİLEMEZ (onlar kaynaktaki g_dk/e_dk + 5 dk tolerans).
- Eşik altı makineler "çalışmayan makineleri gösterme" ayarına bağlı (`calismayan_makineler`).
- Sınıflar: GELDI (tek okutma da), GELMEDI, IZIN_TAM, IZIN_SAAT, TATIL, TATIL_CALISTI, RESMI, PLAN. "Eksik kart" kaldırıldı.

## Hariç / hatalı duruşlar (26.11, yan dalda hazır)
- `operator_haric_durus` (Ayarlar > Duruşlar kartı, Operatör sayfasındaki seçimle aynı anahtar): hesaptan ve raporlardan çıkar (`HesapAyar.haric`, `durus_dokumu`).
  Operatör ya da ürün kodu varsa `vt.aralik_satirlari(..., hatali_etiket=True)` tür adına `HATALI_EK` (" (hatalı)") ekler → hariç tutulmaz. Kayıtlar ekranı ham.
- `hatali_durus.py`: `tespit` (kontrol türleri = `hatali_durus_turleri` ∪ hariç; `hatali_durus_en_az_dk` alt eşik 5), tür "operator" / "is"; kırılım yardımcıları; `zaman_bloklari`.
- `sayfa_hatali.py` (menü "Hatalı Duruşlar", yetki = performans): makine → vardiya | operatör var | operatör yok·iş var | duruş adı | gün → liste → gant.
- Gant (`zaman_cizelgesi.py`): modern görünüm; vurgulu bloklar kırmızı taralı yarı saydam çerçeve (yan yana olanlar birleşir, zoomla büyür).
- Performans "Operatör yok" tıklanınca soru: bu makine → doğrudan gant / tüm makineler → 4. seviye.
- Hatalı sayfa akışı: makine → (vardiya | duruş adı) → (operatöre göre | işe göre) → gant + olay listesi; veri `bekleme.arka_planda` ile.
- `bekleme.py`: ortak bekleme kartı (`Bekleme`, `bekle` bağlam yöneticisi, `arka_planda` iş parçacığı, `kaydir` yumuşak kaydırma). Performans kırılımları, Operatör/Personel yenileme, dönem hesabı kullanır.
- Web sürümünde Hatalı Duruşlar sayfası henüz yok. Kalan izin gösterimi (a/b/c) kararı bekliyor.

## Geçici köprü (kopru.py) — iş bitince sil
- Gizli depo `81Miralay81/vp-kopru` (yerel klon `/home/claude/vp-kopru`). Ben `komut/<PC>.json` (ya da `komut/hepsi.json`) yazarım; program `sonuc/<PC>/<id>.json` yazar, bağlanınca `sonuc/<PC>/canli.json`.
- Gönderme betiği: `scratchpad/kopru.sh '{"tur":"durum"}'` (PC=PC-KALIP18).
- Komutlar: durum, tani, ekran {pencere}, sayfa_ac, pv_ac, pv_js {kod}, pv_cek {ilk,son}, pv_form {siciller}, sql {sorgu (SELECT)}, ayar, kapat.
- Ayarlar'dan açılır, 8 saatte kapanır; anahtar yalnızca kullanıcının bilgisayarında.
