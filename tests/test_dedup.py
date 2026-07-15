import pytest

from ufl.clean.dedup import DeduplicationStore


def test_check_and_add_returns_false_for_first_occurrence():
    store = DeduplicationStore()
    assert store.check_and_add("Bu birinchi marta ko'rilgan matn.") is False


def test_check_and_add_returns_true_for_exact_repeat():
    store = DeduplicationStore()
    text = "Bu takrorlangan matn bo'lib, ikkinchi marta ham xuddi shunday keladi."
    store.check_and_add(text)
    assert store.check_and_add(text) is True


def test_check_and_add_returns_true_for_normalized_repeat_with_different_whitespace_and_case():
    store = DeduplicationStore()
    store.check_and_add("Bu   Matn  BILAN sinov.")
    assert store.check_and_add("bu matn bilan sinov.") is True


def test_check_and_add_returns_false_for_distinct_texts():
    store = DeduplicationStore()
    store.check_and_add("Birinchi mutlaqo boshqa matn.")
    assert store.check_and_add("Ikkinchi butunlay boshqacha matn.") is False


def test_near_dup_not_yet_implemented_raises_when_enabled():
    with pytest.raises(NotImplementedError):
        DeduplicationStore(near_dup_enabled=True)
