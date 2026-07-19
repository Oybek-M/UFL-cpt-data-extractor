# OCR-chiqindi token tozalash (`strip_garbage_tokens`) — Design

## Muammo

Mavjud sifat pipeline (`src/ufl/clean/quality.py`ning `assess()` funksiyasi) butun **blok**
(paragraf) darajasida ishlaydi: aggregat nisbatlarni (nolatin-belgi ulushi, bosh-harf ulushi,
takrorlanish ulushi) hisoblab, butun blokni yoki saqlaydi, yoki butunlay tashlaydi. Natijada,
agar blokda 10 ta yaxshi qator va 1 ta OCR-chiqindi qator bo'lsa, aggregat nisbatlar chegaradan
o'tmaydi va butun blok (chiqindi qator bilan birga) saqlanib qoladi.

Real misol (`UFL-Datas/web_news/10830_xo-jamurod-tojimurodov-ov-hangomalari.txt`, ziyouz'dan
OCR orqali olingan), 5-qator:

```
• kayta nshlaga1^ K r k -^.
```

Bu — tinish-belgi (`•`), raqam+harf yopishgan chiqindi (`nshlaga1^`) va izolyatsiyalangan yakka
harflar (`K r k -^.`) aralashmasi. Bunday chiqindi CPT (Continued Pre-Training) uchun jiddiy
xavf tug'diradi: LLM training paytida har bir ko'rgan token/so'z-birikmasini haqiqiy lug'at
birligi sifatida o'rganadi — chiqindi tokenlar modelning lug'atini "iflos" qiladi.

Bu chiqindi asosan **ziyouz.com/ziyonet.uz'dan OCR orqali olingan** kitoblarda uchraydi
(`docs/DOCKER.md`ning OCR bo'limi: `pytesseract`, `uzb+uzb_cyrl`, `min_confidence=60`) —
HuggingFace dataset'lari (`tahrirchi/uz-crawl`, `tahrirchi/uz-books-v2`, `yakhyo/uz-wiki`)
deyarli tayyor matn bo'lgani uchun bunday muammo kamdan-kam uchraydi.

## Qamrov (Scope)

Yangi `strip_garbage_tokens(line: str) -> str` funksiyasi — **qator+token darajasida** ishlaydi
(blok emas): har blokni qatorlarga bo'lib, har qatordagi alohida chiqindi tokenlarni olib
tashlaydi, qolgan tokenlarni saqlab, qatorni qayta yig'adi.

**Ikkala joyda ham ishlatiladi** (retroaktiv + kelajakdagi yig'ish):
1. Kelajakdagi barcha yig'ish uchun — `src/ufl/clean/apply.py`ning `clean_paragraphs()` ichida.
2. Mavjud (allaqachon finalize qilingan) korpusni retroaktiv tozalash uchun — yangi
   `finalize-corpus` bosqichi (4-bosqich, dedup→PII→rename'dan keyin).

**Qamrovdan tashqarida (ochiq tan olingan cheklov):** morfologik jihatdan "so'zga o'xshab
qolgan, lekin noto'g'ri harfli" chiqindi (masalan shu faylning 4-qatoridagi `ertaklashvj`,
`xapk` — bular grammatik jihatdan haqiqiy so'zdan farqlanmaydi, faqat noto'g'ri harflar bilan).
Bunday holatlarni ishonchli aniqlash lug'at (Uzbek lexicon) yoki til modeli/API talab qiladi —
loyihada hozircha na lug'at, na shunga mablag' ajratish rejasi bor (MiniMax API butun korpusga
ishlatish uchun juda qimmat, foydalanuvchi buni aniq rad etgan). Bu keyingi, alohida spec
sifatida ko'rib chiqiladi (agar qoldiq chiqindi darajasi CPT sifatiga sezilarli ta'sir qilsa).

## Yondashuv tanlovi

Ko'rib chiqilgan variantlar:
1. **Qoidaga asoslangan (rule-based), faqat obyektiv struktura-belgilar** (tanlangan) — hech
   qanday "yopiq so'z-ro'yxati" ishlatilmaydi (masalan "bu 2-3 harfli so'z ro'yxatda yo'q — demak
   chiqindi" kabi qoida **rad etildi**, chunki bunday ro'yxat abbreviatura/bosh-harflarni
   noto'g'ri yo'qotishi mumkin — loyiha rahbari buni aniq rad etdi).
2. **Lug'at (dictionary) asosidagi tekshirish** — rad etildi: loyihada Uzbek lug'at/lexicon
   mavjud emas, uni qurish/saqlash alohida katta ish, hozir kerak emas (YAGNI).
3. **MiniMax/3rd-party API orqali tekshirish** — rad etildi: butun korpusga ishlatish uchun
   juda qimmat (foydalanuvchi tomonidan aniq rad etilgan).

## Qoidalar (obyektiv struktura-belgilar asosida)

Har bir qator bo'shliq bo'yicha tokenlarga bo'linadi (allaqachon `to_latin()` orqali
transliteratsiya qilingan matn ustida ishlaydi). Har token quyidagi qoidalardan **birortasiga**
mos kelsa, **butunlay olib tashlanadi**:

1. **G'ayrioddiy ramz** — token tarkibida harf/raqam/apostrof/defisdan va **odatiy tinish
   belgilaridan** (`. , ! ? : ; ( ) " « » – — …`) boshqa belgi bo'lsa (masalan `•`, `^`) — token
   olib tashlanadi. **Muhim tuzatish** (dastlabki loyihada xato bor edi): agar faqat
   harf/raqam/apostrof/defisga ruxsat berilsa-yu, oddiy tinish belgilari (nuqta, vergul)
   ruxsat etilmagan deb hisoblansa, deyarli **har bir gap oxiridagi so'z** (masalan "kerak.")
   chiqindi deb noto'g'ri hisoblanadi — bu esa korpusning katta qismini yo'qotib qo'yadi.
   Shuning uchun ruxsat etilgan belgilar to'plamiga standart tinish belgilari ham kiritildi;
   faqat haqiqatan g'ayrioddiy ramzlar (`•`, `^` va shunga o'xshash) chiqindi hisoblanadi.
   - `_ALLOWED_EXTRA_CHARS = set("'-.,!?:;()\"«»–—…")` (harf/raqamdan tashqari ruxsat etilgan
     belgilar to'plami).
2. **Izolyatsiyalangan yakka harf** — token uzunligi 1 ta belgi bo'lsa (masalan yolg'iz `K`,
   `r`, `k`) — olib tashlanadi. Bu **ro'yxatga asoslanmagan, blanket qoida**: zamonaviy o'zbek
   yozma tilida yakka harf mustaqil so'z sifatida deyarli hech qachon uchramaydi.
3. **Raqam+harf "yopishgan"** — token tarkibida ham raqam, ham harf bo'lib, ular orasida defis
   yo'q bo'lsa (masalan `nshlaga1^`, `5abc`) — olib tashlanadi. **Istisno**: agar token
   `{raqam}-{so'z}` shaklida bo'lsa (masalan `5-bet`, `1991-yil`) va `{so'z}` qismi
   `DIGIT_SUFFIX_WORDS` yopiq ro'yxatida bo'lsa — saqlanadi (bu haqiqiy sana/sahifa/raqam
   ko'rsatkichlari uchun standart o'zbekcha yozuv shakli).
   - `DIGIT_SUFFIX_WORDS = {"bet", "yil", "son", "hafta", "kun", "soat", "minut", "sekund",
     "mart", "may", "iyun", "iyul", "avgust", "sentabr", "oktabr", "noyabr", "dekabr", "yanvar",
     "fevral", "aprel"}` — **eslatma**: bu ro'yxat ham loyiha rahbari (ona tilida so'zlovchi)
     tomonidan implementatsiyadan oldin tasdiqlanishi/to'g'irlanishi kerak (spec review
     bosqichida).

**Rad etilgan qoida (aniq ko'rsatilgan sabab bilan):** "2-3 harfli token yopiq ro'yxatda yo'q
bo'lsa — chiqindi" — bu qoida ustidan brainstorming paytida to'xtatildi: xato-tashlash xavfi
yuqori (haqiqiy qisqartma/bosh-harf/kam uchraydigan so'zlarni yo'qotishi mumkin), va aynan shu
loyihada Uzbek tilini to'liq qamrab oluvchi ishonchli ro'yxat mavjud emas.

## Arxitektura

### `src/ufl/clean/quality.py`ga qo'shiladi

```python
def strip_garbage_tokens(line: str) -> str:
    """Qator ichidagi obyektiv chiqindi tokenlarni (ramz, yakka harf, raqam-yopishish)
    olib tashlaydi, qolgan tokenlarni bo'shliq bilan qayta birlashtiradi."""
```

### Pipeline tartibi (integratsiya nuqtasi)

Hozirgi tartib: `to_latin` → `is_uzbek` → `assess` → `normalize` → `dedup`
(`src/ufl/clean/apply.py`ning `clean_paragraphs()`).

**Yangi tartib**: `to_latin` → **har qatorga `strip_garbage_tokens` (yangi)** → `is_uzbek` →
`assess` → `normalize` → `dedup`.

**Sabab (`strip_garbage_tokens`ni `is_uzbek`/`assess`dan OLDIN qo'yish)**: chiqindi tokenlar
ko'pincha aynan `assess()`ning nolatin-belgi va bosh-harf nisbatlarini oshirib yuboradi — token
darajasidagi chiqindini oldin tozalash orqali, ba'zi bloklar `assess()`da noto'g'ri (faqat
ichidagi 1-2 chiqindi so'z sababli) tashlanib ketishining oldi olinadi. Xuddi shunday, til
aniqlash (`is_uzbek`, fastText) ham kamroq shovqin bilan ishlaydi.

`clean_paragraphs()`ning ichida, `to_latin(raw)`dan keyin:
```python
latin = to_latin(raw)
latin = "\n".join(strip_garbage_tokens(line) for line in latin.split("\n"))
```

### Ikkinchi integratsiya nuqtasi: `finalize-corpus` retroaktiv bosqich

`src/ufl/cli.py`ning `finalize_corpus` buyrug'iga **4-bosqich** qo'shiladi (dedup → PII →
rename'dan KEYIN — mavjud fayl nomlariga bog'liq emas, tartib muhim emas, lekin oxiriga
qo'yiladi chunki eng "qimmat" operatsiya, boshqa bosqichlar avval arzon tekshiruvlarni
bajarsin):
- `data/output/*/*.txt` fayllarini birma-bir o'qiydi.
- Har bir qatorga `strip_garbage_tokens` qo'llaydi.
- Agar biror qator o'zgargan bo'lsa, faylni qayta yozadi (dry-run'da faqat hisoblanadi,
  yozilmaydi — mavjud PII bosqichi bilan bir xil naqsh).
- Hisobot: "N ta qatordan M ta chiqindi token olib tashlandi (K faylda)".

## Xatolarni boshqarish

- Fayl o'qib/yozib bo'lmasa (ruxsat, kodировка) — mavjud PII bosqichi naqshiga mos, o'sha
  faylni o'tkazib yuborib, ogohlantirish chiqaradi, jarayonni to'xtatmaydi.
- Bo'sh qator yoki faqat bo'shliqdan iborat qator — o'zgarishsiz qoldiriladi (edge case, testda
  qoplanadi).
- Butun qator chiqindi tokenlardan iborat bo'lib, tozalashdan keyin bo'sh qolsa — bo'sh qator
  sifatida qaytariladi (keyingi bosqichlar, masalan `assess()`ning `min_words` tekshiruvi, buni
  tabiiy ravishda qamrab oladi).

## Testlash

TDD, mavjud naqshga mos:
- `tests/test_quality.py` (mavjud fayl, yangi testlar qo'shiladi) — `strip_garbage_tokens`:
  - Aynan real misol qatori (`• kayta nshlaga1^ K r k -^.`) — chiqindi tokenlar olib
    tashlanishi, `kayta` so'zi saqlanishi.
  - Legitim `5-bet`, `1991-yil` kabi raqam-so'z birikmalari saqlanishi.
  - Legitim apostrofli so'zlar (`o'zbek`, `tug'ilgan`) o'zgarishsiz qolishi.
  - Bo'sh qator, faqat-bo'shliq qator — o'zgarishsiz.
  - Butunlay chiqindidan iborat qator — bo'sh qatorga aylanishi.
- `tests/test_finalize_corpus_denoise.py` (yangi) yoki mavjud
  `tests/test_cli_finalize_corpus.py`ga qo'shimcha — 4-bosqichning dry-run/`--apply`
  xatti-harakati, real fayl bilan integratsion test.
- `tests/test_clean_apply.py` (mavjud fayl) — `clean_paragraphs` testlariga qo'shimcha,
  pipeline tartibida `strip_garbage_tokens` chaqirilishi (masalan chiqindi token bo'lgan
  paragraf endi saqlanishi — avval `assess()` tashlab yuborardi) tekshiriladi.

## Hujjatlar

`docs/DOCKER.md`ning `## 10. Korpusni yakunlash (finalize-corpus)` bo'limiga 4-bosqich haqida
qo'shimcha, va OCR-manba haqidagi eslatma yangilanadi.
