from typing import Dict, List


def validate_articles(articles: List[Dict]) -> List[str]:
    warnings: List[str] = []
    if not articles:
        warnings.append("수집된 기사가 없습니다.")
        return warnings

    titles = set()
    for article in articles:
        title = article.get("title", "")
        if title in titles:
            warnings.append(f"중복 기사 감지: {title}")
        titles.add(title)

        content = article.get("content", "")
        if content and len(content.strip()) < 100:
            warnings.append(f"본문이 매우 짧음: {title}")

    return warnings
