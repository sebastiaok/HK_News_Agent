from app.services.article_filter import filter_economic_articles


def test_filter_economic_articles():
    articles = [
        {"title": "환율 급등에 증시 출렁", "content": "원달러 환율과 코스피가 흔들렸다."},
        {"title": "[포토] 벚꽃이 만개한 거리", "content": "사진 기사"},
    ]
    filtered, warnings = filter_economic_articles(articles, min_score=4)
    assert len(filtered) == 1
    assert "환율 급등" in filtered[0]["title"]
    assert warnings
