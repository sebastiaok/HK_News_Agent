import streamlit as st
from app.agent import run_news_mail_agent
from app.graphs.langgraph_agent import run_langgraph_news_mail_agent

st.set_page_config(page_title="Hankyung News Mail Agent", layout="wide")
st.title("한국경제신문 뉴스 요약 & 이메일 초안 Agent")
st.caption("특정 날짜의 한국경제신문 기사를 수집하고, 경제기사만 선별한 뒤, 이메일 형식의 초안을 생성합니다.")

CATEGORY_LABELS = {
    "market": "시장",
    "macro": "거시경제",
    "corporate": "기업",
    "policy": "정책",
    "tech_industry": "기술/산업",
    "real_estate": "부동산",
    "non_economic": "비경제",
    "other": "기타",
}


def confidence_stars(value: int) -> str:
    value = max(1, min(5, int(value or 1)))
    return "★" * value + "☆" * (5 - value)


with st.sidebar:
    st.header("입력 설정")
    target_date = st.text_input("대상 날짜", value="2026-04-10", help="YYYY-MM-DD 형식")
    max_articles = st.slider("최대 기사 수", min_value=1, max_value=10, value=5)
    tone = st.selectbox("메일 톤", ["business", "casual", "executive"], index=0)
    mode = st.radio("실행 방식", ["sequential", "langgraph"], horizontal=True)
    filter_economic_only = st.checkbox("LLM으로 경제 기사만 선별", value=True)
    show_excluded = st.checkbox("제외된 기사도 보기", value=True)
    run_button = st.button("이메일 초안 생성", type="primary")

if run_button:
    with st.spinner("뉴스 수집 및 초안 생성 중..."):
        try:
            kwargs = dict(
                target_date=target_date,
                max_articles=max_articles,
                tone=tone,
                filter_economic_only=filter_economic_only,
            )
            if mode == "langgraph":
                result = run_langgraph_news_mail_agent(**kwargs)
            else:
                result = run_news_mail_agent(**kwargs)

            c1, c2, c3 = st.columns(3)
            c1.metric("수집 기사 수", result["collected_articles"])
            c2.metric("사용 기사 수", result["used_articles"])
            c3.metric("실행 방식", result["mode"])

            st.subheader("이메일 제목")
            st.code(result["subject"], language=None)

            st.subheader("이메일 본문")
            st.text_area("body", result["body"], height=360, label_visibility="collapsed")

            st.download_button(
                label="이메일 초안 TXT 다운로드",
                data=f"제목: {result['subject']}\n\n{result['body']}",
                file_name=f"hankyung_email_draft_{target_date}.txt",
                mime="text/plain",
            )

            st.subheader("기사별 경제성 판별 결과")
            details = result.get("article_details", [])
            if not show_excluded:
                details = [d for d in details if d.get("used_in_summary")]

            for idx, detail in enumerate(details, start=1):
                judgment = detail.get("judgment", {})
                used = detail.get("used_in_summary", False)
                status = "사용됨" if used else "제외됨"
                conf = int(judgment.get("confidence", 1) or 1)
                category = CATEGORY_LABELS.get(judgment.get("category", "other"), judgment.get("category", "other"))
                reason = judgment.get("reason", "")

                title_line = f"{idx}. {detail['title']}"
                with st.expander(title_line, expanded=used):
                    b1, b2, b3, b4 = st.columns([1.1, 1.1, 1.2, 2.6])
                    b1.markdown(f"**상태**  
{status}")
                    b2.markdown(f"**신뢰도**  
{confidence_stars(conf)}")
                    b3.markdown(f"**분류**  
{category}")
                    b4.markdown(f"**판단 사유**  
{reason or '-'}")
                    st.markdown(f"**기사 링크**: [{detail['url']}]({detail['url']})")
                    if detail.get("published_at"):
                        st.markdown(f"**발행 시각**: {detail['published_at']}")
                    if used and detail.get("summary"):
                        st.markdown("**요약에 반영된 기사 요약**")
                        st.write(detail["summary"])

            st.subheader("출처 기사")
            for idx, source in enumerate(result["sources"], start=1):
                st.markdown(f"{idx}. [{source['title']}]({source['url']})")

            if result.get("warnings"):
                st.subheader("경고 / 참고")
                for w in result["warnings"]:
                    st.warning(w)

        except Exception as e:
            st.error(f"실행 중 오류가 발생했습니다: {e}")
else:
    st.info("좌측 설정을 입력한 뒤 '이메일 초안 생성' 버튼을 눌러주세요.")
