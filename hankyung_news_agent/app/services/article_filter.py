from __future__ import annotations

import re
from typing import Dict, List, Sequence, Tuple

ECONOMY_KEYWORDS: Sequence[Tuple[str, int]] = [
    ("경제", 4),
    ("증시", 5),
    ("코스피", 5),
    ("코스닥", 5),
    ("환율", 6),
    ("원달러", 6),
    ("달러", 4),
    ("금리", 6),
    ("연준", 4),
    ("인플레이션", 5),
    ("물가", 5),
    ("수출", 5),
    ("실적", 4),
    ("매출", 4),
    ("영업이익", 4),
    ("반도체", 4),
    ("배터리", 4),
    ("AI", 3),
    ("정책", 3),
    ("부동산", 4),
    ("채권", 4),
    ("국채", 4),
    ("관세", 4),
    ("무역", 4),
    ("투자", 4),
    ("은행", 4),
    ("삼성전자", 3),
    ("SK하이닉스", 3),
]

NOISE_PATTERNS: Sequence[re.Pattern[str]] = [
    re.compile(r"\[포토\]"),
    re.compile(r"\[부고\]"),
    re.compile(r"\[오늘의 arte\]"),
    re.compile(r"\[모십니다\]"),
    re.compile(r"\[한경 arteTV\]"),
]


def economy_score(title: str, content: str = "") -> int:
    text = f"{title}\n{content[:1200]}".lower()
    score = 0
    for pattern in NOISE_PATTERNS:
        if pattern.search(title):
            score -= 12
    for keyword, weight in ECONOMY_KEYWORDS:
        if keyword.lower() in text:
            score += weight
    if len(title.strip()) < 8:
        score -= 2
    return score


def filter_economic_articles(articles: List[Dict], min_score: int = 4, keep_top_k: int | None = None) -> tuple[List[Dict], List[str]]:
    scored: List[Dict] = []
    warnings: List[str] = []

    for article in articles:
        score = economy_score(article.get("title", ""), article.get("content", ""))
        enriched = {**article, "economy_score": score}
        if score >= min_score:
            scored.append(enriched)
        else:
            warnings.append(f"경제성 점수 부족으로 제외됨(score={score}): {article.get('title', '제목 미상')}")

    scored.sort(key=lambda x: (x.get("economy_score", 0), len(x.get("title", ""))), reverse=True)

    if keep_top_k is not None:
        return scored[:keep_top_k], warnings
    return scored, warnings
