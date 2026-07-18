"""ziyouz.com "Kutubxona" bo'limidagi Joomla kategoriya nomlarini UFL'ning 8
kategoriyasiga xaritalaydi.

Manba: docs/superpowers/specs/2026-07-18-ziyouz-bulk-downloader-design.md
Nomlar ziyouz.com'dan 2026-07-18'da real olingan (o'zgarmagan bo'lishi kerak,
lekin sayt strukturasi o'zgarsa yangilanadi). Xaritada yo'q nom uchun
`resolve_ufl_category` None qaytaradi — chaqiruvchi tomon bunday elementni
o'tkazib yuborishi va ogohlantirish chiqarishi kerak (hech qachon taxminiy
kategoriyaga yozmaslik — "shubha bo'lsa tashla" tamoyili).
"""

from __future__ import annotations

CATEGORY_MAP: dict[str, str] = {
    # --- Ziyouz.com kutubxonasi (badiiy/ilmiy adabiyot) ---
    "O'zbek xalq og'zaki ijodi": "books",
    "O'zbek mumtoz adabiyoti": "books",
    "Alisher Navoiy asarlari": "books",
    "O'zbek zamonaviy she'riyati": "books",
    "O'zbek nasri": "books",
    "O'zbek dramaturgiyasi": "books",
    "O'zbek adabiy tili": "reference",
    "O'zbek tilining izohli lug'ati": "reference",
    "O'zbekiston Milliy Ensiklopediyasi": "reference",
    "Jahon xalqlari og'zaki ijodi": "books",
    "Sharq mumtoz adabiyoti": "books",
    "Jahon nasri": "books",
    "Jahon she'riyati": "books",
    "Jahon dramaturgiyasi": "books",
    "Bolalar kutubxonasi": "books",
    "Tasavvufga oid kitoblar": "books",
    "Axloq-odobga oid kitoblar": "books",
    "Hikmatlar xazinasi (Aforizmlar)": "books",
    "Tarixga oid kitoblar": "books",
    "Prezident asarlari": "gov_legal",
    "Ilmiy-tarixiy, adabiy maqolalar, risolalar": "books",
    "Adabiyotshunoslik": "books",
    "Adabiy antologiya va to'plamlar": "books",
    "Adabiy, tarixiy bukletlar": "books",
    "Adabiy esdaliklar, xotiralar": "books",
    "Hajviyot": "web_news",
    "Tarjimashunoslik": "books",
    "Eski o'zbek yozuvi": "reference",
    "Lug'atlar": "reference",
    "Turli mavzulardagi kitoblar": "books",
    "Chet tillari": "education",
    "Tibbiyotga oid risolalar": "domain_haf",
    "Publitsistika": "web_news",
    "Falsafa": "books",
    "Aniq fanlar": "education",
    "Jurnalistika": "web_news",
    "San'atshunoslik": "books",
    "Statistika": "books",
    "Hunarmadchilik": "books",
    "Uzbek literature (in English)": "books",
    "Sport": "books",
    # --- Ziyouz.com jurnalxonasi ---
    "\"Tafakkur\" jurnali": "web_news",
    "\"Sharq yulduzi\" jurnali": "web_news",
    "Журнал \"Звезда Востока\"": "web_news",
    "\"Yoshlik\" jurnali": "web_news",
    "\"Jahon adabiyoti\" jurnali": "web_news",
    "\"Hidoyat\" jurnali": "web_news",
    "\"Muloqot\" jurnali": "web_news",
    "\"Moziydan sado\" jurnali": "web_news",
    "\"Guliston\" jurnali": "web_news",
    "\"Vatandosh\" gazetasi": "web_news",
    "\"Yosh kuch\" jurnali": "web_news",
    "Журнал \"Молодая смена\"": "web_news",
    "\"Fan va turmush\" jurnali": "web_news",
    "\"Til va adabiyot ta'limi\" jurnali": "web_news",
    "\"O'zbekistonda ijtimoiy fanlar\" jurnali": "web_news",
    "\"O'zbekiston arxeologiyasi\" jurnali": "web_news",
    "\"O'zbekiston moddiy madaniyati tarixi\" to'plami": "web_news",
    "\"O'zbekistonda arxeologik tadqiqotlar\" to'plami": "web_news",
    "\"Saodat\" jurnali": "web_news",
    "\"Sirli olam\" jurnali": "web_news",
    "\"Iqtisod va hisobot\" jurnali": "domain_haf",
    "\"Ijod olami\" jurnali": "web_news",
    # --- Bibliografik nashrlar ---
    "Gazeta maqolalari solnomasi (1977)": "reference",
    "Jurnal maqolalari letopisi (1961-1967)": "reference",
    "Kitob letopisi (1932-1967)": "reference",
    "Sovet O'zbekiston kitobi (1917-1975)": "reference",
    "O'zbekiston kitoblarining yilnomasi (1976-1998)": "reference",
    "O'zbekiston matbuoti solnomasi (1968-2014)": "reference",
    # --- Oliy va o'rta maxsus ta'lim muassasalari darsliklari (hammasi ta'lim) ---
    "Aloqa va axborot texnologiyalari": "education",
    "Biologiya": "education",
    "Ekologiya": "education",
    "Geodeziya": "education",
    "Geografiya": "education",
    "Geologiya": "education",
    "Huquq": "education",
    "Iqtisodiyot": "education",
    "Jismoniy tarbiya": "education",
    "Kimyo": "education",
    "Mantiq": "education",
    "Ma'naviyat": "education",
    "Matematika": "education",
    "Me'morchilik": "education",
    "Ona tili va adabiyot": "education",
    "Pedagogika": "education",
    "Psixologiya": "education",
    "Qishloq xo'jaligi": "education",
    "San'at": "education",
    "Tabiiy fanlar": "education",
    "Tarix": "education",
    "Texnika va texnologiya": "education",
    "Tibbiyot": "education",
    # --- Maktab darsliklari (hammasi ta'lim) ---
    "Alifbo": "education",
    "Adabiyot": "education",
    "Chizmachilik": "education",
    "Fizika": "education",
    "Fransuz tili": "education",
    "Informatika": "education",
    "Ingliz tili": "education",
    "Musiqa": "education",
    "Nemis tili": "education",
    "Odobnoma": "education",
    "O'zbek tili": "education",
    "Rus tili": "education",
    "Tasviriy san'at": "education",
    "Yangi darsliklar (2014-2023)": "education",
    "Tojik maktablari uchun darsliklar": "education",
    "Turkman maktablari uchun darsliklar": "education",
    # --- Mobil kutubxona ---
    "Badiiy kitoblar": "books",
    "O'zbek xalq og'zaki ijodi": "books",
    "Turli mavzudagi kitoblar": "books",
    "Android uchun kitoblar": "books",
    "E-readerlar uchun EPUB kitoblar": "books",
    # --- Библиотека Ziyouz.com (rus tilida) ---
    "Узбекское устное народное творчество": "books",
    "Узбекская классическая литература": "books",
    "Узбекская современная проза": "books",
    "Узбекская современная поэзия": "books",
    "Узбекская драматургия": "books",
    "Узбекская детская литература": "books",
    "Сборники по узбекской литературы": "books",
    "Русскоязычная проза Узбекистана": "books",
    "Узбекский язык и литература": "reference",
    "Русскоязычная поэзия Узбекистана": "books",
    "Каракалпакская литература": "books",
    "Научные произведения великих мыслителей Узбекистана": "books",
    "Жизнь и деятельность великих предков Узбекистана": "books",
    "Литературы по истории тюркских народов": "books",
    "Словари тюркских языков": "reference",
    "Узбекская кулинария": "books",
    "Избранная лирика Востока": "books",
    # --- Qaraqalpaq kitapxanası ---
    "Qaraqalpaq folklorı": "books",
    "Qaraqalpaq poeziyası": "books",
    "Qaraqalpaq prozası": "books",
    "Qaraqalpaq tili sózlikleri": "reference",
    "Qaraqalpaqstan tariyxı": "books",
    "İlimiy kitaplar": "books",
    "Qaraqalpaqsha sabaqlıqlar": "education",
    "Jáhán ádebiyatı qaraqalpaq tilinde": "books",
    "Balalar ádebiyatı": "books",
}


# ziyouz.com HTML'da qo'shtirnoq apostrof turli joyda turlicha kodlangan (ASCII '
# yoki Unicode qayrilma ‘/’) — 2026-07-18 real crawl'da bu farq "O'zbek xalq
# og'zaki ijodi" kabi nomlarni "Noma'lum kategoriya" deb noto'g'ri belgilagan.
# Solishtirishdan oldin barcha variantlar bitta ASCII apostrofga normallashtiriladi.
_APOSTROPHE_VARIANTS = ("‘", "’", "ʼ", "´", "`")


def _normalize_category_name(name: str) -> str:
    normalized = name.strip()
    for variant in _APOSTROPHE_VARIANTS:
        normalized = normalized.replace(variant, "'")
    return normalized


_NORMALIZED_CATEGORY_MAP: dict[str, str] = {
    _normalize_category_name(name): category for name, category in CATEGORY_MAP.items()
}


def resolve_ufl_category(joomla_category_name: str) -> str | None:
    """Ziyouz kategoriya nomini UFL kategoriyasiga o'giradi; xaritada yo'q
    bo'lsa None (chaqiruvchi tomon bunday elementni o'tkazib yuborishi kerak).
    Apostrof kodlash farqlariga chidamli (`_normalize_category_name`)."""
    return _NORMALIZED_CATEGORY_MAP.get(_normalize_category_name(joomla_category_name))
