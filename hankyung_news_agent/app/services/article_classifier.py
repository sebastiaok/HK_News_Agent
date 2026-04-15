from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Tuple

from app.services.article_filter import economy_score
from app.services.llm_client import chat_completion

CLASSIFIER_SYSTEM = """
너는 한국경제신문 기사 선별 보조자다.
주어진 기사 후보가 '경제 브리핑 메일'에 포함될 만한 경제/산업/금융/정책/기업 실적 관련 기사인지 판별하라.
연예, 문화, 순수 행사 공지, 부고, 포토, 생활정보, 전시, 공연, 단순 인물 인터뷰 등은 제외하라.
반드시 JSON만 출력하라.
"""


def _extract_json(text: str) -> Any:
    text = text.strip()
    try:
        return json.loads(text)
    except Exception:
        pass

    match = re.search(r"(\[.*\]|\{.*\})", text, flags=re.DOTALL)
    if not match:
        raise ValueError("LLM 분류 결과에서 JSON을 찾지 못했습니다.")
    return json.loads(match.group(1))


def classify_articles_economic_llm(
    articles: List[Dict[str, Any]],
    keep_top_k: int | None = None,
    min_confidence: int = 3,
) -> Tuple[List[Dict[str, Any]], List[str], List[Dict[str, Any]]]:
    if not articles:
        return [], [], []

    items_for_prompt = []
    for idx, article in enumerate(articles, start=1):
        snippet = (article.get("description") or article.get("content") or "")[:800]
        items_for_prompt.append(
            {
                "id": idx,
                "title": article.get("title", ""),
                "published_at": article.get("published_at", ""),
                "snippet": snippet,
            }
        )

    user_prompt = f"""
다음 기사 후보들을 경제 브리핑용으로 판별해줘.
각 기사마다 아래 형식의 JSON 객체를 배열로 반환해.

필드 설명:
- id: 입력 id 그대로
- is_economic: true/false
- confidence: 1~5 정수
- category: market | macro | corporate | policy | tech_industry | real_estate | non_economic | other
- reason: 1문장 한국어

입력 기사 목록:
{json.dumps(items_for_prompt, ensure_ascii=False, indent=2)}
"""

    warnings: List[str] = []
    all_classified: List[Dict[str, Any]] = []
    try:
        raw = chat_completion(CLASSIFIER_SYSTEM, user_prompt, temperature=0.0)
        parsed = _extract_json(raw)
        if not isinstance(parsed, list):
            raise ValueError("LLM 분류 결과가 리스트가 아닙니다.")
    except Exception as exc:
        warnings.append(f"LLM 경제기사 판별 실패로 규칙 기반 필터로 대체함: {exc}")
        fallback = []
        for article in articles:
            score = economy_score(article.get("title", ""), article.get("content", ""))
            classified = {
                **article,
                "economic_judgment": {
                    "is_economic": score >= 4,
                    "confidence": min(5, max(1, score // 2 if score > 0 else 1)),
                    "category": "other" if score >= 4 else "non_economic",
                    "reason": "규칙 기반 점수에 따른 대체 판별",
                    "rule_score": score,
                },
            }
            all_classified.append(classified)
            if classified["economic_judgment"]["is_economic"]:
                fallback.append(classified)
        fallback.sort(
            key=lambda x: (
                int(x.get("economic_judgment", {}).get("confidence", 1) or 1),
                economy_score(x.get("title", ""), x.get("content", "")),
            ),
            reverse=True,
        )
        if keep_top_k is not None:
            fallback = fallback[:keep_top_k]
        return fallback, warnings, all_classified

    judgments_by_id: Dict[int, Dict[str, Any]] = {}
    for item in parsed:
        if not isinstance(item, dict) or "id" not in item:
            continue
        try:
            judgments_by_id[int(item["id"])] = item
        except Exception:
            continue

    kept: List[Dict[str, Any]] = []
    for idx, article in enumerate(articles, start=1):
        judgment = judgments_by_id.get(idx)
        if not judgment:
            score = economy_score(article.get("title", ""), article.get("content", ""))
            judgment = {
                "is_economic": score >= 4,
                "confidence": min(5, max(1, score // 2 if score > 0 else 1)),
                "category": "other" if score >= 4 else "non_economic",
                "reason": "LLM 결과 누락으로 규칙 기반 보정",
                "rule_score": score,
            }
            warnings.append(f"LLM 판별 누락으로 규칙 기반 보정: {article.get('title', '제목 미상')}")

        enriched = {**article, "economic_judgment": judgment}
        all_classified.append(enriched)
        is_economic = bool(judgment.get("is_economic", False))
        confidence = int(judgment.get("confidence", 1) or 1)
        if is_economic and confidence >= min_confidence:
            kept.append(enriched)
        else:
            warnings.append(
                f"경제기사 판별 제외(confidence={confidence}, category={judgment.get('category', 'unknown')}): {article.get('title', '제목 미상')}"
            )

    kept.sort(
        key=lambda x: (
            int(x.get("economic_judgment", {}).get("confidence", 1) or 1),
            economy_score(x.get("title", ""), x.get("content", "")),
            len(x.get("title", "")),
        ),
        reverse=True,
    )

    if keep_top_k is not None:
        kept = kept[:keep_top_k]
    return kept, warnings, all_classified
