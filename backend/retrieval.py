import time

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.chains import RetrievalQA
from sqlalchemy.orm import Session

from config import settings
from ingest import load_index
from prompts import get_prompt

_llm = ChatGoogleGenerativeAI(
    model=settings.model_name,
    google_api_key=settings.google_api_key,
)


def answer_question(
    document_id: str,
    question: str,
    db: Session,
    prompt_version: str = "v1",
) -> dict:
    index = load_index(document_id, db)
    retriever = index.as_retriever(search_kwargs={"k": settings.retriever_k})

    chain = RetrievalQA.from_chain_type(
        llm=_llm,
        chain_type="stuff",
        retriever=retriever,
        chain_type_kwargs={"prompt": get_prompt(prompt_version)},
        return_source_documents=True,
    )

    start = time.perf_counter()
    result = chain.invoke({"query": question})
    latency_ms = int((time.perf_counter() - start) * 1000)

    sources = [doc.page_content for doc in result["source_documents"]]

    return {
        "answer": result["result"],
        "sources": sources,
        "latency_ms": latency_ms,
    }
