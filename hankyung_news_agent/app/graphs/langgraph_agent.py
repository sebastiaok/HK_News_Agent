from typing import Any, Dict, List, TypedDict

from langgraph.graph import END, StateGraph

from app.services.article_classifier import classify_articles_economic_llm
from app.services.article_parser import extract_article
from app.services.mail_generator import generate_email_draft
from app.services.news_fetcher import fetch_hankyung_articles_by_date
from app.services.summarizer import summarize_all_articles, summarize_article
from app.services.validator import validate_articles


class AgentState(TypedDict, total=False):
    target_date: str
    max_articles: int
    tone: str
    warnings: List[str]
    articles: List[Dict[str, Any]]
    parsed_articles: List[Dict[str, Any]]
    classified_articles: List[Dict[str, Any]]
    enriched_articles: List[Dict[str, Any]]
    combined_summary: str
    subject: str
    body: str
    filter_economic_only: bool


def fetch_news_node(state: AgentState) -> AgentState:
    articles = fetch_hankyung_articles_by_date(
        state["target_date"],
        max_articles=state.get("max_articles", 5),
    )
    return {**state, "articles": articles, "warnings": state.get("warnings", [])}


def parse_articles_node(state: AgentState) -> AgentState:
    warnings = list(state.get("warnings", []))
    parsed_articles: List[Dict[str, Any]] = []

    for article in state.get("articles", []):
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

    return {**state, "parsed_articles": parsed_articles, "warnings": warnings}


def classify_articles_node(state: AgentState) -> AgentState:
    warnings = list(state.get("warnings", []))
    parsed_articles = list(state.get("parsed_articles", []))

    if state.get("filter_economic_only", True):
        classified_articles, filter_warnings, all_classified_articles = classify_articles_economic_llm(
            parsed_articles,
            keep_top_k=state.get("max_articles", 5),
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
        classified_articles = all_classified_articles

    return {**state, "parsed_articles": all_classified_articles, "classified_articles": classified_articles, "warnings": warnings}


def summarize_articles_node(state: AgentState) -> AgentState:
    warnings = list(state.get("warnings", []))
    enriched_articles: List[Dict[str, Any]] = []

    for article in state.get("classified_articles", []):
        try:
            summary = summarize_article(article["title"], article["content"])
            enriched_articles.append({**article, "summary": summary})
        except Exception as e:
            warnings.append(f"기사 요약 실패: {article['title']} / {str(e)}")

    warnings.extend(validate_articles(enriched_articles))
    return {**state, "enriched_articles": enriched_articles, "warnings": warnings}


def summarize_all_node(state: AgentState) -> AgentState:
    if not state.get("enriched_articles"):
        raise ValueError("요약 가능한 기사가 없습니다.")
    combined_summary = summarize_all_articles(state["enriched_articles"])
    return {**state, "combined_summary": combined_summary}


def draft_mail_node(state: AgentState) -> AgentState:
    subject, body = generate_email_draft(
        target_date=state["target_date"],
        combined_summary=state["combined_summary"],
        article_summaries=state["enriched_articles"],
        tone=state.get("tone", "business"),
    )
    return {**state, "subject": subject, "body": body}


def build_langgraph_agent():
    graph = StateGraph(AgentState)
    graph.add_node("fetch_news", fetch_news_node)
    graph.add_node("parse_articles", parse_articles_node)
    graph.add_node("classify_articles", classify_articles_node)
    graph.add_node("summarize_articles", summarize_articles_node)
    graph.add_node("summarize_all", summarize_all_node)
    graph.add_node("draft_mail", draft_mail_node)

    graph.set_entry_point("fetch_news")
    graph.add_edge("fetch_news", "parse_articles")
    graph.add_edge("parse_articles", "classify_articles")
    graph.add_edge("classify_articles", "summarize_articles")
    graph.add_edge("summarize_articles", "summarize_all")
    graph.add_edge("summarize_all", "draft_mail")
    graph.add_edge("draft_mail", END)
    return graph.compile()


def run_langgraph_news_mail_agent(
    target_date: str,
    max_articles: int = 5,
    tone: str = "business",
    filter_economic_only: bool = True,
) -> Dict[str, Any]:
    app = build_langgraph_agent()
    result = app.invoke(
        {
            "target_date": target_date,
            "max_articles": max_articles,
            "tone": tone,
            "warnings": [],
            "filter_economic_only": filter_economic_only,
        }
    )
    enriched_articles = result.get("enriched_articles", [])
    all_classified = result.get("parsed_articles", [])
    return {
        "target_date": target_date,
        "collected_articles": len(result.get("articles", [])),
        "used_articles": len(enriched_articles),
        "subject": result.get("subject", ""),
        "body": result.get("body", ""),
        "sources": [
            {"title": a["title"], "url": a["url"]}
            for a in enriched_articles
        ],
        "warnings": result.get("warnings", []),
        "mode": "langgraph",
        "article_details": [
            {
                "title": a["title"],
                "url": a["url"],
                "published_at": a.get("published_at", ""),
                "judgment": a.get("economic_judgment", {}),
                "used_in_summary": any(u["url"] == a["url"] for u in enriched_articles),
                "summary": next((u.get("summary", "") for u in enriched_articles if u["url"] == a["url"]), ""),
            }
            for a in all_classified
        ],
    }
