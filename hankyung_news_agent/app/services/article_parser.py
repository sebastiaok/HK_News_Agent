from __future__ import annotations

import json
import re
from typing import Dict, List, Optional

import requests
from bs4 import BeautifulSoup, Tag

from app.config import REQUEST_TIMEOUT, USER_AGENT

REMOVE_SELECTORS = [
    "script",
    "style",
    "noscript",
    "iframe",
    "figure",
    "figcaption",
    ".related-news",
    ".article-related",
    ".ad-area",
    ".advertisement",
    ".byline",
    ".copyright",
    ".reporter-info",
]

CONTENT_SELECTORS = [
    "#articletxt",
    "#article-body",
    "#newsView",
    ".article-body",
    ".article_view",
    ".article-text",
    "article",
]

STOP_PATTERNS = [
    "무단전재 및 재배포 금지",
    "좋아요 싫어요 후속기사 원해요",
    "구독신청",
    "모바일한경 보기",
    "관련 뉴스",
    "많이 본 뉴스",
    "AI 추천",
]


class ArticleParserError(RuntimeError):
    pass


class HankyungArticleParser:
    def __init__(self) -> None:
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT})

    def extract_article(self, url: str) -> Dict[str, str]:
        response = self.session.get(url, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")

        title = self._extract_title(soup)
        published_at = self._extract_published_at(soup)
        description = self._extract_description(soup)
        content = self._extract_body_text(soup)

        if len(content) < 200:
            raise ArticleParserError(f"본문 추출 실패 또는 본문이 너무 짧습니다: {url}")

        return {
            "title": title,
            "published_at": published_at,
            "description": description,
            "content": content,
            "url": url,
        }

    def extract_article_text(self, url: str) -> str:
        return self.extract_article(url)["content"]

    def _extract_title(self, soup: BeautifulSoup) -> str:
        selectors = [
            "meta[property='og:title']",
            "meta[name='twitter:title']",
            "h1",
            "title",
        ]
        for selector in selectors:
            node = soup.select_one(selector)
            if not node:
                continue
            if node.name == "meta":
                content = node.get("content", "").strip()
                if content:
                    return self._clean_title(content)
            else:
                text = node.get_text(" ", strip=True)
                if text:
                    return self._clean_title(text)
        return "제목 미상 기사"

    def _extract_description(self, soup: BeautifulSoup) -> str:
        selectors = [
            "meta[property='og:description']",
            "meta[name='description']",
            "meta[name='twitter:description']",
        ]
        for selector in selectors:
            node = soup.select_one(selector)
            if node and node.get("content"):
                return self._clean_text(node["content"])
        return ""

    def _extract_published_at(self, soup: BeautifulSoup) -> str:
        meta_selectors = [
            "meta[property='article:published_time']",
            "meta[name='pubdate']",
            "meta[name='publish-date']",
        ]
        for selector in meta_selectors:
            node = soup.select_one(selector)
            if node and node.get("content"):
                return node["content"].strip()

        text = soup.get_text(" ", strip=True)
        match = re.search(r"입력\s*(\d{4}\.\d{2}\.\d{2}\s*\d{2}:\d{2})", text)
        if match:
            return match.group(1)
        return ""

    def _extract_body_text(self, soup: BeautifulSoup) -> str:
        # 1) JSON-LD articleBody가 있으면 가장 먼저 활용
        json_ld_text = self._extract_from_json_ld(soup)
        if len(json_ld_text) >= 200:
            return json_ld_text

        # 2) 본문 selector 기반 추출
        for selector in CONTENT_SELECTORS:
            node = soup.select_one(selector)
            if not node:
                continue
            text = self._clean_node_text(node)
            if len(text) >= 200:
                return text

        # 3) 문단 수집 fallback
        paragraphs = self._extract_visible_paragraphs(soup)
        if len(paragraphs) >= 200:
            return paragraphs

        fallback = self._clean_text(soup.get_text(" ", strip=True))
        return fallback[:5000]

    def _clean_node_text(self, node: Tag) -> str:
        cloned = BeautifulSoup(str(node), "html.parser")
        for selector in REMOVE_SELECTORS:
            for bad in cloned.select(selector):
                bad.decompose()

        text = cloned.get_text("\n", strip=True)
        return self._trim_noise(self._clean_text(text))

    def _extract_from_json_ld(self, soup: BeautifulSoup) -> str:
        texts: List[str] = []
        for script in soup.select("script[type='application/ld+json']"):
            raw = script.string or script.get_text(strip=True)
            if not raw:
                continue
            try:
                data = json.loads(raw)
            except Exception:
                continue
            texts.extend(self._collect_article_body(data))

        merged = "\n".join(t for t in texts if t)
        return self._trim_noise(self._clean_text(merged))

    def _collect_article_body(self, data) -> List[str]:
        found: List[str] = []
        if isinstance(data, dict):
            article_body = data.get("articleBody") or data.get("description")
            if isinstance(article_body, str):
                found.append(article_body)
            for value in data.values():
                found.extend(self._collect_article_body(value))
        elif isinstance(data, list):
            for item in data:
                found.extend(self._collect_article_body(item))
        return found

    def _extract_visible_paragraphs(self, soup: BeautifulSoup) -> str:
        paragraphs: List[str] = []
        for node in soup.select("p"):
            text = self._clean_text(node.get_text(" ", strip=True))
            if len(text) < 40:
                continue
            if any(stop in text for stop in STOP_PATTERNS):
                continue
            paragraphs.append(text)
        return self._trim_noise("\n".join(paragraphs))

    def _trim_noise(self, text: str) -> str:
        earliest_stop: Optional[int] = None
        for stop in STOP_PATTERNS:
            idx = text.find(stop)
            if idx != -1 and (earliest_stop is None or idx < earliest_stop):
                earliest_stop = idx
        if earliest_stop is not None:
            text = text[:earliest_stop]
        return text.strip()

    def _clean_title(self, text: str) -> str:
        text = self._clean_text(text)
        text = re.sub(r"\s*\|\s*한국경제.*$", "", text)
        return text.strip()

    def _clean_text(self, text: str) -> str:
        text = text.replace("\xa0", " ")
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()


_parser = HankyungArticleParser()


def extract_article(url: str) -> Dict[str, str]:
    return _parser.extract_article(url)


def extract_article_text(url: str) -> str:
    return _parser.extract_article_text(url)
