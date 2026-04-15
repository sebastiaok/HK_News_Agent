from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from email.utils import parsedate_to_datetime
import re
from typing import Dict, Iterable, List, Optional, Sequence, Tuple
from urllib.parse import urljoin
import xml.etree.ElementTree as ET

import requests
from bs4 import BeautifulSoup

from app.config import REQUEST_TIMEOUT, USER_AGENT

BASE_URL = "https://www.hankyung.com"
DAILY_SITEMAP_URL = "https://www.hankyung.com/sitemap/daily-article/{yyyymmdd}.xml"
LEGACY_SITEMAP_URL = "https://www.hankyung.com/sitemap/{yyyy}/{mm}/{dd}"
RSS_FEEDS = [
    "https://www.hankyung.com/feed/all-news",
    "https://www.hankyung.com/feed/economy",
    "https://www.hankyung.com/feed/finance",
    "https://www.hankyung.com/feed/international",
    "https://www.hankyung.com/feed/it",
]

ARTICLE_URL_PATTERNS = [
    re.compile(r"https?://www\.hankyung\.com/article/\d+[A-Za-z0-9]*"),
    re.compile(r"https?://www\.hankyung\.com/.+/article/\d+[A-Za-z0-9]*"),
]

SITEMAP_NS = {
    "sm": "http://www.sitemaps.org/schemas/sitemap/0.9",
    "news": "http://www.google.com/schemas/sitemap-news/0.9",
}

# 한국경제 브리핑 성격에 맞춰, 제목만으로 우선순위를 조정하기 위한 간단한 가중치다.
# 필요하면 프로젝트 성격에 맞게 수정하면 된다.
TITLE_PRIORITY_KEYWORDS: Sequence[Tuple[str, int]] = [
    ("관세", 6),
    ("환율", 6),
    ("금리", 6),
    ("반도체", 5),
    ("증시", 5),
    ("코스피", 5),
    ("코스닥", 5),
    ("AI", 4),
    ("수출", 4),
    ("실적", 4),
    ("투자", 4),
    ("배터리", 4),
    ("철강", 4),
    ("조선", 4),
    ("부동산", 4),
    ("정책", 3),
    ("트럼프", 3),
    ("중국", 3),
    ("미국", 3),
    ("삼성", 3),
    ("SK", 3),
    ("현대", 3),
]

NOISE_TITLE_PATTERNS: Sequence[re.Pattern[str]] = [
    re.compile(r"\[포토\]"),
    re.compile(r"\[오늘의 arte\]"),
    re.compile(r"\[모십니다\]"),
]


@dataclass
class ArticleMeta:
    title: str
    url: str
    published_at: str

    def to_dict(self) -> Dict[str, str]:
        return {
            "title": self.title,
            "url": self.url,
            "published_at": self.published_at,
        }


class NewsFetcherError(RuntimeError):
    pass


class HankyungFetcher:
    def __init__(self) -> None:
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT})

    def fetch_hankyung_articles_by_date(self, target_date: str, max_articles: int = 5) -> List[Dict[str, str]]:
        dt = self._validate_date(target_date)

        strategies = [
            self._fetch_from_daily_sitemap,
            self._fetch_from_legacy_sitemap,
            self._fetch_from_rss,
        ]

        all_items: List[ArticleMeta] = []
        errors: List[str] = []
        for strategy in strategies:
            try:
                all_items.extend(strategy(dt))
            except Exception as exc:  # pragma: no cover - network dependent
                errors.append(f"{strategy.__name__}: {exc}")

        ranked_items = self._rank_items(self._dedupe(all_items), target_date=target_date)
        trimmed = ranked_items[:max_articles]
        if trimmed:
            return [item.to_dict() for item in trimmed]

        raise NewsFetcherError(
            f"{target_date} 기사 수집에 실패했습니다."
            + (f" 세부 오류: {' | '.join(errors)}" if errors else "")
        )

    def _validate_date(self, target_date: str) -> datetime:
        try:
            return datetime.strptime(target_date, "%Y-%m-%d")
        except ValueError as exc:
            raise NewsFetcherError("target_date must be YYYY-MM-DD") from exc

    def _fetch_from_daily_sitemap(self, dt: datetime) -> List[ArticleMeta]:
        url = DAILY_SITEMAP_URL.format(yyyymmdd=dt.strftime("%Y%m%d"))
        response = self.session.get(url, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()

        root = ET.fromstring(response.text)
        items: List[ArticleMeta] = []

        for node in root.findall("sm:url", SITEMAP_NS):
            loc = self._read_xml_text(node, "sm:loc")
            if not loc or not self._is_article_url(loc):
                continue

            title = self._read_xml_text(node, "news:news/news:title") or self._infer_title_from_url(loc)
            published_at = self._read_xml_text(node, "news:news/news:publication_date") or dt.strftime("%Y-%m-%d")
            items.append(ArticleMeta(title=title.strip(), url=loc.strip(), published_at=published_at.strip()))

        return items

    def _fetch_from_legacy_sitemap(self, dt: datetime) -> List[ArticleMeta]:
        url = LEGACY_SITEMAP_URL.format(yyyy=dt.strftime("%Y"), mm=dt.strftime("%m"), dd=dt.strftime("%d"))
        response = self.session.get(url, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")
        items: List[ArticleMeta] = []

        for anchor in soup.select("a[href]"):
            href = anchor.get("href", "").strip()
            title = anchor.get_text(" ", strip=True)
            full_url = urljoin(BASE_URL, href)

            if not title or not self._is_article_url(full_url):
                continue

            items.append(
                ArticleMeta(
                    title=title,
                    url=full_url,
                    published_at=dt.strftime("%Y-%m-%d"),
                )
            )

        return items

    def _fetch_from_rss(self, dt: datetime) -> List[ArticleMeta]:
        target_day = dt.date()
        items: List[ArticleMeta] = []

        for feed_url in RSS_FEEDS:
            response = self.session.get(feed_url, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
            root = ET.fromstring(response.text)

            for item in root.findall("./channel/item"):
                link = self._read_xml_text(item, "link")
                title = self._read_xml_text(item, "title")
                pub_date = self._read_xml_text(item, "pubDate")

                if not link or not title or not pub_date:
                    continue
                if not self._is_article_url(link):
                    continue

                parsed = parsedate_to_datetime(pub_date)
                if parsed.date() != target_day:
                    continue

                items.append(
                    ArticleMeta(
                        title=BeautifulSoup(title, "html.parser").get_text(" ", strip=True),
                        url=link.strip(),
                        published_at=parsed.isoformat(),
                    )
                )

        return items

    def _dedupe(self, items: Iterable[ArticleMeta]) -> List[ArticleMeta]:
        deduped: List[ArticleMeta] = []
        seen = set()
        for item in items:
            normalized = self._normalize_article_url(item.url)
            if normalized in seen:
                continue
            seen.add(normalized)
            deduped.append(
                ArticleMeta(
                    title=item.title.strip() or self._infer_title_from_url(item.url),
                    url=normalized,
                    published_at=item.published_at,
                )
            )
        return deduped

    def _rank_items(self, items: Sequence[ArticleMeta], target_date: str) -> List[ArticleMeta]:
        def score(item: ArticleMeta) -> Tuple[int, int, str]:
            title = item.title.strip()
            s = 0
            for pattern in NOISE_TITLE_PATTERNS:
                if pattern.search(title):
                    s -= 10
            for keyword, weight in TITLE_PRIORITY_KEYWORDS:
                if keyword.lower() in title.lower():
                    s += weight
            # target_date 문자열이 title에 직접 들어가진 않지만,
            # 발행일이 정확히 맞는 경우 RSS fallback 쪽에서 우선되게 한다.
            if target_date in item.published_at:
                s += 2
            return (s, len(title), title)

        return sorted(items, key=score, reverse=True)

    def _read_xml_text(self, node: ET.Element, path: str) -> Optional[str]:
        found = node.find(path, SITEMAP_NS)
        if found is None or found.text is None:
            return None
        return found.text

    def _is_article_url(self, url: str) -> bool:
        return any(pattern.match(url) for pattern in ARTICLE_URL_PATTERNS)

    def _normalize_article_url(self, url: str) -> str:
        return url.split("?", 1)[0].strip().rstrip("/")

    def _infer_title_from_url(self, url: str) -> str:
        token = url.rstrip("/").rsplit("/", 1)[-1]
        token = re.sub(r"^\d+[A-Za-z0-9]*", "", token).strip("-")
        return token or "제목 미상 기사"


def fetch_hankyung_articles_by_date(target_date: str, max_articles: int = 5) -> List[Dict[str, str]]:
    return HankyungFetcher().fetch_hankyung_articles_by_date(target_date=target_date, max_articles=max_articles)
