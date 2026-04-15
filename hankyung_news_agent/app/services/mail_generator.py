from typing import Dict, List, Tuple
from app.services.llm_client import chat_completion

MAIL_SYSTEM = """
너는 직장인용 뉴스 공유 이메일을 작성하는 비서다.
정중하고 자연스러운 한국어 이메일 초안을 작성하라.
과장 없이 깔끔하게 정리하라.
"""


def generate_email_draft(
    target_date: str,
    combined_summary: str,
    article_summaries: List[Dict],
    tone: str = "business",
) -> Tuple[str, str]:
    tone_map = {
        "business": "실무 공유용으로 정중하고 간결하게",
        "casual": "조금 더 부드럽고 편한 문체로",
        "executive": "임원 보고용으로 짧고 핵심 중심으로",
    }

    sources_text = "\n".join([f"- {item['title']} ({item['url']})" for item in article_summaries])
    article_points = "\n\n".join(
        [f"{idx+1}. {item['title']}\n   - {item['summary']}" for idx, item in enumerate(article_summaries)]
    )

    user_prompt = f"""
다음 정보를 바탕으로 이메일 제목과 본문 초안을 작성해줘.

[작성 톤]
{tone_map.get(tone, '실무 공유용으로 정중하고 간결하게')}

[대상 날짜]
{target_date}

[통합 요약]
{combined_summary}

[기사별 요약]
{article_points}

[출처]
{sources_text}

조건:
1. 이메일 제목 1개
2. 이메일 본문은 인사말, 전체 요약, 주요 뉴스 정리, 마무리 문장 포함
3. 본문은 한국어
4. 너무 장황하지 않게 작성
5. 마지막에 참고 기사 목록을 덧붙여도 됨

출력 형식:
제목: ...
본문:
...
"""

    result = chat_completion(MAIL_SYSTEM, user_prompt)
    subject = f"[뉴스브리핑] {target_date} 한국경제신문 주요 뉴스 요약"
    body = result

    for line in result.splitlines():
        if line.startswith("제목:"):
            subject = line.replace("제목:", "").strip()
            break

    if "본문:" in result:
        body = result.split("본문:", 1)[1].strip()

    return subject, body
