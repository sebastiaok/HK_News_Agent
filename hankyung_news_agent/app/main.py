from fastapi import FastAPI, HTTPException

from app.schemas import GenerateDraftRequest, GenerateDraftResponse
from app.agent import run_news_mail_agent
from app.graphs.langgraph_agent import run_langgraph_news_mail_agent

app = FastAPI(title="Hankyung News Mail Agent")


@app.get("/")
def root():
    return {"message": "Hankyung News Mail Agent is running"}


@app.post("/generate-email-draft", response_model=GenerateDraftResponse)
def generate_email_draft_api(payload: GenerateDraftRequest):
    try:
        if payload.mode == "langgraph":
            result = run_langgraph_news_mail_agent(
                target_date=payload.target_date,
                max_articles=payload.max_articles,
                tone=payload.tone,
                filter_economic_only=payload.filter_economic_only,
            )
        else:
            result = run_news_mail_agent(
                target_date=payload.target_date,
                max_articles=payload.max_articles,
                tone=payload.tone,
                filter_economic_only=payload.filter_economic_only,
            )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
