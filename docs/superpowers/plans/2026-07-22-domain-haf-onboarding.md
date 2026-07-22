# domain_haf (Sog'liq, qishloq xo'jaligi, biznes) — yangi ma'lumotni pipeline'ga qo'shish

> **Bu hujjat boshqa AI agent (Gemini / Antigravity) tomonidan bajarilishi uchun yozilgan.**
> Loyihaning avvalgi suhbat konteksti mavjud emas deb hisoblab, har bir qadam mustaqil
> tushunarli bo'lishi uchun to'liq yozilgan. Kod o'zgartirish shart EMAS — mavjud CLI
> buyruqlari bilan bajariladigan operatsion vazifa.

## Fon / nima uchun kerak

Jamoadan "health, agriculture and business" bo'limi bilan shug'ullangan a'zo jamoadan
chiqib ketdi. Uning ishi qoldi: ma'lumot yig'ilgan, lekin deyarli filterlanmagan.
Bu ma'lumotni loyihaning standart CPT (continued pre-training) korpus pipeline'iga
kiritish kerak.

`config/ufl.toml`da bu mavzular uchun **aynan mos** kategoriya allaqachon mavjud:

```toml
[budget.categories]
...
domain_haf    =  60_000_000  # Health, agriculture, business & finance (5%)
```

## Hozirgi holat (manba fayllar)

Xom (deyarli filterlanmagan) fayllar shu yerda:
`C:\Users\Oybek\Documents\Projects programming\StartUps\UFL-Datas\ufl health\`

| Fayl | Hajm | Mavzu |
|---|---|---|
| `davolash.txt` | ~24 MB | Sog'liq — davolash |
| `kasalliklar.txt` | ~4.8 MB | Sog'liq — kasalliklar |
| `qishloq xojaligi.txt` | ~7.4 MB | Qishloq xo'jaligi |

Bular oddiy uzun matn fayllar (veb-skrab, OCR EMAS) — paragraflar bo'sh qator bilan
ajratilgan oddiy prose. HTML teg yoki boshqa struktura ko'rilmadi (namunaviy tekshiruv,
fayllar to'liq o'qilmagan — hajm katta).

**"Biznes" mavzusi uchun hali umuman ma'lumot yig'ilmagan.** Bu alohida keyingi qadam
(yangi web-manba topish/crawl qilish kerak bo'ladi) — bu hujjat doirasiga kirmaydi.

## Loyiha pipeline'i haqida bilish kerak bo'lgan narsalar

- `ufl run <papka>` — asosiy ingest buyrug'i. `.txt`, `.pdf`, `.epub`, `.docx`, `.html`
  va boshqa formatlarni avtomatik aniqlab, standart tozalash zanjiridan o'tkazadi:
  struktura tozalash (front-matter/kolontitul/sahifa-raqami/bibliografiya) → OCR-chiqindi
  token tozalash → sifat-filtr (min_chars, min_words, non-letter-ratio va h.k.) →
  til-aniqlash filtri (fastText + evristika) → dedup → `data/output/<kategoriya>/`ga yozadi.
- **Kategoriya papka nomidan avtomatik aniqlanadi**: `data/input/domain_haf/x.txt`
  ingest qilinsa, natija avtomatik `domain_haf` kategoriyasiga yoziladi (`_infer_category`
  funksiyasi, `src/ufl/cli.py`). Agar fayl papkasiz, tekis joylashtirilgan bo'lsa —
  kategoriya "uncategorized" bo'lib qoladi va **MiniMax API** orqali avtomatik
  klassifikatsiya qilishga urinadi. **BUNI ISHLATMASLIK KERAK** — MiniMax jamoaning
  umumiy (shared) resursi, minimal ishlatilishi kerak. Shuning uchun fayllarni albatta
  `data/input/domain_haf/` papkasiga qo'yish SHART (pastda ko'rsatilgan).
- `.txt` ingest moduli (`src/ufl/ingest/txt.py`) faylni bo'sh-qator (`\n\n`) bo'yicha
  paragraflarga ajratadi, har bir paragraf alohida "blok" sifatida sifat-filtrdan o'tadi.
- Docker orqali ishlaydi: `docker compose run --rm ufl ufl run data/input`.
  `docker-compose.override.yml` (git'ga kirmaydi, mahalliy) `/app/data/output`ni
  host'dagi `../UFL-Datas`ga bog'laydi — ya'ni natija ko'rinadigan haqiqiy joy
  `C:\Users\Oybek\...\UFL-Datas\domain_haf\` bo'ladi, `./data/output/domain_haf` EMAS.
  `data/input`, `data/rejected`, `data/reports` esa oddiy `./data/...`da (host loyihasida).

## Amalga oshirish qadamlari

### 1-qadam: Fayllarni to'g'ri joyga ko'chirish (nusxalash, ko'chirib O'TKAZMASLIK)

Xavfsizlik uchun asl fayllarni **ko'chirmang, nusxa oling** — bu ma'lumotning
yagona nusxasi, boshqa backup yo'q.

```powershell
New-Item -ItemType Directory -Force "data\input\domain_haf"
Copy-Item "..\UFL-Datas\ufl health\davolash.txt" "data\input\domain_haf\davolash.txt"
Copy-Item "..\UFL-Datas\ufl health\kasalliklar.txt" "data\input\domain_haf\kasalliklar.txt"
Copy-Item "..\UFL-Datas\ufl health\qishloq xojaligi.txt" "data\input\domain_haf\qishloq_xojaligi.txt"
```

(Oxirgi faylda bo'sh joy olib tashlandi — bash/docker'da problema keltirib chiqarmasligi
uchun, loyihadagi boshqa fayllar konvensiyasiga mos.)

### 2-qadam: Standart ingest pipeline'ni ishga tushirish

```bash
docker compose run --rm ufl ufl run data/input/domain_haf --config config/ufl.toml
```

Bu MiniMax'ni chaqirmaydi (`--verify-with-minimax` berilmagan — standart holat).
Natija: `../UFL-Datas/domain_haf/*.txt` (yangi papka avtomatik yaratiladi).

Tugagach konsol chiqishida "Muvaffaqiyatli: N, ... Aniq yig'ilgan token: X" kabi
xulosani tekshiring — N=3 (3 ta fayl) bo'lishi kerak, Xato: 0.

### 3-qadam: Statistikani tekshirish

```bash
docker compose run --rm ufl ufl stats --config config/ufl.toml
```

`domain_haf` qatorida byudjetga nisbatan qancha token yig'ilgani ko'rinadi (maqsad:
60,000,000 token, 5% ulush).

### 4-qadam: finalize-corpus — FAQAT 1-4-bosqich (imlo-tuzatishsiz)

Bu yangi ma'lumot OCR emas (veb-skrab matn), shuning uchun mavjud OCR-manba
imlo-tuzatish evristikasi (5-bosqich) bu janr uchun HALI SINALMAGAN. Bugungi
tajriba shuni ko'rsatdiki (`docs/superpowers/plans/2026-07-19-ocr-spellcheck.md`),
bu evristika noto'g'ri sinovdan o'tmagan janrda kutilmagan xatolar berishi mumkin
(masalan arxaik/klassik matnlarda "-g'a" qo'shimchasini noto'g'ri "tuzatgan" edi).
Shuning uchun HOZIRCHA spellcheck bosqichini o'CHIRIB qo'llang:

```bash
docker compose run --rm ufl ufl finalize-corpus --apply \
  --no-spellcheck \
  --config config/ufl.toml
```

Bu dedup (1), PII tozalash (2), HF-nomini-yashirish (3, bu fayllarga taalluqli
emas — HF-manba emas), OCR-chiqindi/sahifa-raqami/muallif-yorlig'i tozalash (4)
bosqichlarini ishga tushiradi — **BUTUN korpusga**, nafaqat yangi domain_haf
fayllariga (chunki finalize-corpus butun `data/output/`ni ko'rib chiqadi). Bu
xavfsiz — allaqachon tozalangan fayllarda o'zgarish bo'lmaydi (idempotent).

Agar keyinchalik domain_haf uchun ham imlo-tuzatishni sinab ko'rish kerak bo'lsa,
avval kichik namunada (`--apply` bermasdan, dry-run rejimida) natijalarni qo'lda
tekshirib chiqing, so'ng qaror qiling.

### 5-qadam: Natijani spot-check qilish

Bir nechta qatorni qo'lda o'qib, matn buzilmaganini, chiqindi qolmaganini tekshiring:

```bash
head -c 1000 "../UFL-Datas/domain_haf/davolash.txt"
```

## Muhim eslatmalar / loyiha qoidalari

- **Git gigiyena**: `data/input/**` va `data/output/**` (demak `../UFL-Datas` ham)
  gitignore qilingan — bu ma'lumotlar hech qachon git'ga tushmasligi kerak (repo
  keyinchalik public bo'ladi).
- **MiniMax**: jamoaning umumiy (shared) API resursi — faqat zarur bo'lgandagina,
  minimal ishlatilsin. Yuqoridagi qadamlar buni chaqirmaydi.
- **Backup yo'q**: `UFL-Datas` git bilan boshqarilmaydi, boshqa backup mavjud emas.
  Har qanday operatsiyadan oldin (ayniqsa fayllarni o'chirish/ustidan yozish) ehtiyot
  bo'ling — nusxa olib keyin ishlang.
- Ishlov berilgach, "biznes" mavzusi uchun alohida ma'lumot yig'ish kerakligini
  jamoaga eslatib qo'ying — hozircha bu bo'limda faqat sog'liq va qishloq xo'jaligi bor.
