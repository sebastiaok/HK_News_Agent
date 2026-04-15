# Hankyung News Mail Agent

특정 날짜의 한국경제신문 기사를 수집하고, 경제 브리핑용 기사만 선별한 뒤, 이메일 형식의 초안을 생성하는 AI Agent 예제 프로젝트입니다.

## 포함 기능
- FastAPI 기반 API 서버
- Streamlit 기반 UI
- 순차 실행 Agent
- LangGraph 기반 그래프 Agent
- mermaid 포함 설계 문서
- 사이트맵/RSS 우선 수집 전략
- 다중 selector + JSON-LD fallback 본문 파싱
- LLM 기반 경제기사 판별 노드
- 이메일 형식 초안 생성 및 TXT 다운로드

## 처리 흐름
1. **일별 XML 사이트맵** 우선 조회
2. 실패 시 **레거시 일자 사이트맵 HTML** fallback
3. 그래도 부족하면 **RSS feed**에서 해당 날짜 기사 재탐색
4. 기사 본문 추출 후 **LLM으로 경제기사 여부 판별**
5. 통과 기사만 요약하여 **이메일 초안** 생성

## 빠른 시작
```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

`.env`에 OpenAI API 키를 입력합니다.

## API 실행
```bash
uvicorn app.main:app --reload
```

- Swagger: `http://127.0.0.1:8000/docs`

## Streamlit 실행
```bash
streamlit run streamlit_app.py
```

## 구조
```text
hankyung_news_agent/
├─ app/
│  ├─ main.py
│  ├─ agent.py
│  ├─ config.py
│  ├─ schemas.py
│  ├─ graphs/langgraph_agent.py
│  └─ services/
├─ docs/design.md
├─ streamlit_app.py
├─ tests/
└─ requirements.txt
```

## 주의사항
- 한국경제 기사 접근 제한, 유료 기사, 사이트 구조 변경에 따라 수집 정확도가 달라질 수 있습니다.
- 실서비스에서는 robots 정책, 저작권, 이용약관 검토가 필요합니다.
- 운영 환경에서는 요청 간격 제한, 캐시, 재시도(backoff), 실패 로그 저장을 추가하는 것이 좋습니다.
- LLM 경제기사 판별이 실패하면 규칙 기반 필터로 자동 대체됩니다.

## 추천 고도화
- 기사 날짜 메타 검증 강화
- HTML 이메일 템플릿 생성
- 기사 카테고리 분류 고도화
- 캐시 및 재시도 전략 추가
- 요약 전 중복 기사/속보 묶기
- 메일 수신자별 템플릿 커스터마이징

## API 요청 예시
```json
{
  "target_date": "2026-04-10",
  "max_articles": 5,
  "tone": "business",
  "mode": "langgraph",
  "filter_economic_only": true
}
```
