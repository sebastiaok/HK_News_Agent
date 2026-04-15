from typing import Dict, List

from app.services.article_classifier import classify_articles_economic_llm
from app.services.article_parser import extract_article
from app.services.mail_generator import generate_email_draft
from app.services.news_fetcher import fetch_hankyung_articles_by_date
from app.services.summarizer import summarize_all_articles, summarize_article
from app.services.validator import validate_articles


def run_news_mail_agent(
    target_date: str,
    max_articles: int = 5,
    tone: str = "business",
    filter_economic_only: bool = True,
) -> Dict:
    warnings: List[str] = []
    articles = fetch_hankyung_articles_by_date(target_date, max_articles=max_articles)

    if not articles:
        raise ValueError("해당 날짜에 수집된 기사가 없습니다.")

    parsed_articles = []
    for article in articles:
        try:
            parsed = extract_article(article["url"])
            title = parsed.get("title") or article["title"]
            content = parsed["content"]
            published_at = parsed.get("published_at") or article["published_at"]
            description = parsed.get("description", "")

            if len(content.strip()) < 100:
                warnings.append(f"본문이 너무 짧아 제외됨: {title}")
                continue

            parsed_articles.append(
                {
                    "title": title,
                    "url": article["url"],
                    "published_at": published_at,
                    "description": description,
                    "content": content,
                }
            )
        except Exception as e:
            warnings.append(f"기사 처리 실패: {article['title']} / {str(e)}")

    classified_articles = list(parsed_articles)
    if filter_economic_only:
        classified_articles, filter_warnings, all_classified_articles = classify_articles_economic_llm(
            parsed_articles,
            keep_top_k=max_articles,
            min_confidence=3,
        )
        warnings.extend(filter_warnings)
    else:
        all_classified_articles = [
            {
                **article,
                "economic_judgment": {
                    "is_economic": True,
                    "confidence": 5,
                    "category": "other",
                    "reason": "경제기사 필터를 사용하지 않아 전체 기사 포함",
                },
            }
            for article in parsed_articles
        ]

    enriched_articles = []
    for article in classified_articles:
        try:
            summary = summarize_article(article["title"], article["content"])
            enriched_articles.append({**article, "summary": summary})
        except Exception as e:
            warnings.append(f"기사 요약 실패: {article['title']} / {str(e)}")

    warnings.extend(validate_articles(enriched_articles))

    if not enriched_articles:
        raise ValueError("요약 가능한 기사가 없습니다.")

    combined_summary = summarize_all_articles(enriched_articles)
    subject, body = generate_email_draft(
        target_date=target_date,
        combined_summary=combined_summary,
        article_summaries=enriched_articles,
        tone=tone,
    )

    return {
        "target_date": target_date,
        "collected_articles": len(articles),
        "used_articles": len(enriched_articles),
        "subject": subject,
        "body": body,
        "sources": [{"title": a["title"], "url": a["url"]} for a in enriched_articles],
        "warnings": warnings,
        "mode": "sequential",
        "article_details": [
            {
                "title": a["title"],
                "url": a["url"],
                "published_at": a.get("published_at", ""),
                "judgment": a.get("economic_judgment", {}),
                "used_in_summary": any(u["url"] == a["url"] for u in enriched_articles),
                "summary": next((u.get("summary", "") for u in enriched_articles if u["url"] == a["url"]), ""),
            }
            for a in all_classified_articles
        ],
    }
