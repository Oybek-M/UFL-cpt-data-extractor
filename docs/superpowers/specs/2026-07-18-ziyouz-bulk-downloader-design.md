# ziyouz.com — ommaviy fayl-yuklovchi (dizayn)

## Kontekst

Foydalanuvchining shaxsiy asosiy yo'nalishi — "Books and Literature". `ziyouz.com`
real ko'rib chiqildi (2026-07-18): bu HTML-matn sayti emas, **Joomla + Phoca Download**
asosidagi fayl-katalog. "Kutubxona" bo'limi ~42 kichik kategoriyaga bo'lingan (kutubxona,
audiokutubxona, jurnalxona, darsliklar, maktab darsliklari, mobil kutubxona, rus tilidagi
b-ka, qoraqalpoq kitobxonasi, bibliografik nashrlar) — jami **~13,000+ element**.

Har bir element sahifasida ikkita havola bor: `SAQLASH` (yuklab olish, `?download=<id>:<slug>`
query — bu 303 redirect qilib haqiqiy statik faylga yo'naltiradi, masalan
`/books/uzbek_zamonaviy_sheriyati/A'zam O'ktam. Kuzda kulgan chechaklar.pdf`) va `HAQIDA`
(metadata, JS orqali ochiladi — kerak emas). Kategoriyalar sahifalangan (masalan
"O'zbek zamonaviy she'riyati" — 8 sahifa, ~779 element).

`robots.txt` ruxsat beradi (faqat `/administrator/`, `/cache/` va sh.k. taqiqlangan —
kontent-sahifalar ochiq). Litsenziya: "faqat shaxsiy mutolaa uchun, tijoriy foydalanish
taqiqlanadi" — foydalanuvchi bu xavfni ongli ravishda qabul qildi (MVP bosqichi, tijoriy
holatga o'tishdan oldin alohida shartnoma/qayta o'qitish bo'ladi — huquqiy jamoasi bor).

Bu **HTML-matn crawl emas** (`ufl crawl` mos emas) — bu **fayl yuklab olish + mavjud
`ufl run` fayl-pipeline'i** (PDF/EPUB/DOCX/FB2/DJVU/TXT/HTML, OCR bilan) orqali qayta
ishlash. Audio (mp3) va boshqa matn-bo'lmagan fayllar avtomatik o'tkazib yuboriladi
(kengaytma bo'yicha filtr — foydalanuvchi tasdiqlagan).

## Qamrov (v1)

**Butun kutubxona** (foydalanuvchi tanlovi) — barcha ~42 kategoriya, quyidagi UFL
kategoriyalarga xaritalanadi (`src/ufl/ziyouz/category_map.py`, oddiy dict — kerak
bo'lsa keyin qo'lda tuzatiladi):

| Ziyouz bo'limi | UFL kategoriyasi |
|---|---|
| Ziyouz.com kutubxonasi (badiiy adabiyot: xalq og'zaki ijodi, mumtoz, Navoiy, she'riyat, nasr, drama, jahon adabiyoti, bolalar) | `books` |
| O'zbek adabiy tili, izohli lug'at, Milliy Ensiklopediya, Lug'atlar | `reference` |
| Tasavvufga oid, Axloq-odobga oid, Hikmatlar xazinasi | `books` |
| Tarixga oid kitoblar, Adabiy esdaliklar/xotiralar, Adabiyotshunoslik, antologiya | `books` |
| Prezident asarlari | `gov_legal` |
| Ilmiy-tarixiy maqolalar/risolalar, Falsafa | `books` |
| Tibbiyotga oid risolalar | `domain_haf` |
| Publitsistika, Jurnalistika, Hajviyot | `web_news` |
| Oliy/o'rta maxsus ta'lim darsliklari (barcha fan) | `education` |
| Maktab darsliklari (barcha fan) | `education` |
| Tojik/Turkman maktab darsliklari | `education` |
| Chet tillari, Aniq fanlar, San'atshunoslik | `education` |
| Ziyouz.com jurnalxonasi (barcha jurnal/gazeta) | `web_news` |
| Bibliografik nashrlar (kitob/gazeta yilnomasi) | `reference` |
| Библиотека Ziyouz.com (rus tilidagi bo'lim — barchasi) | `books` |
| Qaraqalpaq kitapxanası (barchasi) | `books` |
| Statistika, Hunarmadchilik, Sport, Pazandalik | `books` (aniq mos kategoriya yo'q — fallback) |

**Chiqarib tashlanadi (kengaytma bo'yicha avtomatik):** audiokutubxona (mp3), video —
`SUPPORTED_EXTENSIONS = {.pdf, .epub, .docx, .doc, .fb2, .djvu, .txt, .html}` dan
tashqari hamma narsa `skip` qilinadi (yuklab olinmaydi ham — avval final URL kengaytmasi
tekshiriladi).

## Arxitektura

Yangi CLI buyruq: **`ufl fetch-ziyouz`** (`fetch-hf`ga o'xshash nom-uslubi).

```
docker compose run --rm ufl ufl fetch-ziyouz
docker compose run --rm ufl ufl fetch-ziyouz --limit 20        # sinov
docker compose run --rm ufl ufl fetch-ziyouz --category books  # faqat bitta UFL-kategoriya
```

**Bosqichlar:**

1. **Kategoriya-daraxtini kashf qilish** — `https://ziyouz.com/kutubxona` sahifasini
   olib, `/kutubxona/category/<id>-<slug>` naqshiga mos havolalarni BeautifulSoup bilan
   topadi (mavjud crawler'dagi kabi). Har biri `category_map.py`dagi nom bo'yicha
   UFL-kategoriyaga bog'lanadi; xaritada yo'q nom — ogohlantirish bilan o'tkazib
   yuboriladi (yangi bo'lim qo'shilsa spec yangilanadi).
2. **Sahifalash** — har bir kategoriya sahifasidan barcha `?download=<id>:<slug>`
   havolalarini yig'adi, so'ng "keyingi sahifa" havolasini (raqamli pager, DOM'dan)
   topib davom etadi (Joomla query-parametrlarini taxmin qilish shart emas — DOM'dan
   real havola olinadi, xuddi mavjud crawler'ning `_discover_links` uslubida).
3. **Yuklab olish** — har bir `?download=` havolasi uchun mavjud `WebClient.get()`
   (redirect avtomatik ergashadi, `request_delay` orqali odobli tezlik) chaqiriladi.
   Final URL yo'lidan haqiqiy fayl nomi/kengaytmasi olinadi. Kengaytma
   `SUPPORTED_EXTENSIONS`da bo'lmasa — **yuklanmaydi**, faqat o'tkazib yuboriladi.
4. **Qayta ishlash** — fayl `data/tmp/ziyouz/`ga yoziladi, mavjud
   `process_file()` (xuddi `ufl run`dagi kabi — bir xil pipeline, bir xil sifat/til
   filtri) orqali o'tkaziladi, `write_output()` bilan `data/output/<kategoriya>/`ga
   yoziladi, `Store.record_book()`ga yozg'iriladi. Vaqtinchalik yuklab olingan xom fayl
   **darhol o'chiriladi** (disk joyi tejash uchun — HF fetch-hf'dagi kabi tamoyil).
5. **Davomiylik (resumable)** — har bir element uchun sintetik kalit
   `f"ziyouz:{item_id}"` (havoladagi raqamli ID) `Store.is_processed()` orqali
   tekshiriladi — allaqachon qayta ishlangan bo'lsa, hatto qayta yuklab olinmaydi ham
   (bosqich 3'dan oldin tekshiriladi). Alohida state-fayl kerak emas — mavjud
   `ufl.db`dagi `books` jadvali yetarli (xuddi `ufl run`dagi fayl-yo'l kabi, faqat
   `ziyouz:` prefiksi bilan).

**Yangi fayllar:**
- `src/ufl/ziyouz/category_map.py` — yuqoridagi jadval (dict: Joomla category-nomi →
  UFL kategoriya).
- `src/ufl/ziyouz/catalog.py` — kategoriya-daraxti kashfiyoti + sahifalash + havola
  yig'ish (BeautifulSoup, mavjud `WebClient` DI orqali).
- CLI: `src/ufl/cli.py`ga `fetch-ziyouz` buyrug'i qo'shiladi.

**Qayta ishlatiladigan mavjud komponentlar (yangi yozilmaydi):** `WebClient`,
`RobotsPolicy`, `process_file`, `write_output`, `Store`, `DeduplicationStore`,
`load_fasttext_predictor`, `load_tokenizer_counter`.

## Xavfsizlik va odob

- `RobotsPolicy` orqali `robots.txt` tekshiriladi (allaqachon ruxsat berilgan).
- `WebClient.request_delay` orqali xost-boshiga so'rov oralig'i saqlanadi (config'dagi
  `crawl.request_delay` qayta ishlatiladi).
- Fayl hajmi cheklovi: 200MB'dan katta fayl o'tkazib yuboriladi (disk himoyasi,
  `client_max_body_size` bilan mos — Nginx qoidasi bilan bir xil raqam).

## Litsenziya eslatmasi

Sayt litsenziyasi "faqat shaxsiy mutolaa, tijoriy foydalanish taqiqlanadi" deydi.
Foydalanuvchi (2026-07-18) buni ongli qabul qildi: hozirgi bosqich — investorlarga MVP
ko'rsatish uchun tijoriy bo'lmagan tayyorgarlik, tijoriy ishga tushirishdan oldin
huquqiy jamoa bilan alohida shartnoma/qayta o'qitish bosqichi bo'ladi. Bu qaror
qayta ko'rib chiqilishi kerak bo'lganda ushbu hujjatga qaytish kerak.

## Sinov strategiyasi

TDD: `category_map.py` (sof funksiya/dict — trivial), `catalog.py` (HTTP DI orqali
soxta HTML javob bilan sinaladi — havola/sahifalash parsingi), CLI integratsiya testi
(soxta `WebClient` bilan 2-3 element oqimi, `process_file` chaqirilishini tekshiradi).
Real sayt bilan yakuniy tekshiruv qo'lda (`--limit 5`) — fetch-hf'da qilingandek.
