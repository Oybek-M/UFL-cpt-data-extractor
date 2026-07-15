"""Byudjet hisobi: kategoriya bo'yicha yig'ilgan token vs maqsad.

Qoidalar: docs/superpowers/specs/2026-07-15-ufl-data-pipeline-design.md §1, §12
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class CategoryBudget:
    category: str
    target_tokens: int
    collected_tokens: int

    @property
    def progress_pct(self) -> float:
        if self.target_tokens == 0:
            return 0.0
        return min(self.collected_tokens / self.target_tokens * 100, 100.0)


def compute_budget(
    target_tokens_by_category: dict[str, int], collected_tokens_by_category: dict[str, int]
) -> list[CategoryBudget]:
    return [
        CategoryBudget(
            category=category,
            target_tokens=target,
            collected_tokens=collected_tokens_by_category.get(category, 0),
        )
        for category, target in target_tokens_by_category.items()
    ]


def total_budget(budgets: list[CategoryBudget]) -> CategoryBudget:
    return CategoryBudget(
        category="JAMI",
        target_tokens=sum(b.target_tokens for b in budgets),
        collected_tokens=sum(b.collected_tokens for b in budgets),
    )
