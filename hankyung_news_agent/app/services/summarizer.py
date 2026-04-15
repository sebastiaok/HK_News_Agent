from typing import Dict, List
from app.services.llm_client import chat_completion

ARTICLE_SUMMARY_SYSTEM = """
너는 경제 뉴스 요약 전문가다.
기사 내용을 사실 기반으로 간결하게 요약하라.
추측은 하지 말고, 기사에 있는 정보 중심으로 정리하라.
출력은 한국어로 작성하라.
"""

COMBINED_SUMMARY_SYSTEM = """
너는 경제 브리핑 작성 전문가다.
여러 뉴스 요약을 바탕으로 그날의 핵심 이슈를 종합 정리하라.
중복은 제거하고, 중요한 흐름 중심으로 정리하라.
출력은 한국어로 작성하라.
"""


def summarize_article(title: str, content: str) -> str:
    user_prompt = f"""
다음 경제 기사를 3~4문장으로 요약해줘.

[기사 제목]
{title}

[기사 본문]
{content[:3500]}
"""
    return chat_completion(ARTICLE_SUMMARY_SYSTEM, user_prompt)


def summarize_all_articles(article_summaries: List[Dict]) -> str:
    joined = "\n\n".join(
        [f"[기사{i+1}] {item['title']}\n요약: {item['summary']}" for i, item in enumerate(article_summaries)]
    )

    user_prompt = f"""
다음은 특정 일자의 경제 뉴스 요약 목록이다.
이를 바탕으로 전체 핵심 이슈를 4~6개 bullet 또는 문단 형태로 정리해줘.

{joined}
"""
    return chat_completion(COMBINED_SUMMARY_SYSTEM, user_prompt)
