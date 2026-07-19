"""HF dataset manbasini fayl nomidan yashirish — dataset_slug (masalan
'tahrirchi_uz-crawl') o'rniga generic alias ('corpus-a') qo'yiladi, split va
shard raqami saqlanib qoladi."""

from ufl.finalize.hf_rename import (
    is_hf_sourced_filename,
    match_hf_shard_filename,
    renamed_filename,
    source_path_for_filename,
)


def test_match_recognizes_known_dataset_shard_filename():
    match = match_hf_shard_filename("tahrirchi_uz-crawl__news__shard-000001.txt")
    assert match is not None
    assert match.dataset_id == "tahrirchi/uz-crawl"
    assert match.split == "news"
    assert match.shard == "000001"


def test_match_handles_split_names_containing_underscores():
    """'telegram_blogs' split nomining o'zida bitta pastki chiziq bor —
    slug/split/shard ajratish shu holatda ham to'g'ri ishlashi kerak."""
    match = match_hf_shard_filename("tahrirchi_uz-crawl__telegram_blogs__shard-000242.txt")
    assert match is not None
    assert match.dataset_id == "tahrirchi/uz-crawl"
    assert match.split == "telegram_blogs"
    assert match.shard == "000242"


def test_match_returns_none_for_unknown_dataset_but_reports_slug():
    match = match_hf_shard_filename("boshqa_dataset__train__shard-000001.txt")
    assert match is not None
    assert match.dataset_id is None
    assert match.slug == "boshqa_dataset"


def test_match_returns_none_for_non_shard_filename():
    """ziyouz uslubidagi fayl (id_slug.txt) HF shard naqshiga mos kelmaydi."""
    assert match_hf_shard_filename("10763_hamza-hakimzoda-niyoziy.txt") is None


def test_source_path_for_filename_known_dataset():
    path = source_path_for_filename("tahrirchi_uz-books-v2__lat__shard-000003.txt")
    assert path == "hf:tahrirchi/uz-books-v2:lat:shard-000003"


def test_source_path_for_filename_unknown_dataset_returns_none():
    assert source_path_for_filename("boshqa_dataset__train__shard-000001.txt") is None


def test_source_path_for_filename_non_shard_returns_none():
    assert source_path_for_filename("10763_hamza-hakimzoda-niyoziy.txt") is None


def test_renamed_filename_strips_dataset_name_keeps_split_and_shard():
    assert (
        renamed_filename("tahrirchi_uz-crawl__news__shard-000001.txt")
        == "corpus-a__news__shard-000001.txt"
    )


def test_renamed_filename_unknown_dataset_returns_none():
    assert renamed_filename("boshqa_dataset__train__shard-000001.txt") is None


def test_renamed_filename_non_shard_returns_none():
    assert renamed_filename("10763_hamza-hakimzoda-niyoziy.txt") is None


def test_is_hf_sourced_filename_original_naming():
    assert is_hf_sourced_filename("tahrirchi_uz-crawl__news__shard-000001.txt") is True


def test_is_hf_sourced_filename_renamed_alias():
    assert is_hf_sourced_filename("corpus-a__news__shard-000001.txt") is True
    assert is_hf_sourced_filename("corpus-b__lat__shard-000001.txt") is True
    assert is_hf_sourced_filename("corpus-c__train__shard-000001.txt") is True


def test_is_hf_sourced_filename_ziyouz_style_returns_false():
    assert is_hf_sourced_filename("10763_hamza-hakimzoda-niyoziy.txt") is False


def test_is_hf_sourced_filename_unrecognized_slug_returns_false():
    assert is_hf_sourced_filename("boshqa_dataset__train__shard-000001.txt") is False
