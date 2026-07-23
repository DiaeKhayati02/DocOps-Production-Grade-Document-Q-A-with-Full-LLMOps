from langchain_core.prompts import PromptTemplate

QA_TEMPLATE_V1 = """Answer the question using only the context below. \
If the answer is not contained in the context, say you don't know — \
do not make anything up.

Context:
{context}

Question:
{question}

Answer:"""

PROMPTS = {
    "v1": PromptTemplate(template=QA_TEMPLATE_V1, input_variables=["context", "question"]),
}


def get_prompt(version: str = "v1") -> PromptTemplate:
    try:
        return PROMPTS[version]
    except KeyError:
        raise ValueError(f"Unknown prompt version: {version!r}. Available: {list(PROMPTS)}")
