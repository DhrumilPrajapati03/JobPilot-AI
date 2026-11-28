"""Tools and skills a job description names (for "not in your vault" lists and interview gaps).

Two signals, so page chrome like a cookie banner ("Accept", "Decline") or a sentence that
starts with a capital never counts:

* a curated vocabulary of tools, platforms and techniques, matched as whole words;
* tool-shaped tokens: CamelCase (PyTorch, FastAPI), all caps (AWS, GCP), or with digits
  or symbols (C++, Node.js, GPT-4), minus common acronyms that aren't skills (CEO, USA, EEO).
"""
from __future__ import annotations

import re

VOCAB = """python java javascript typescript go golang rust scala kotlin swift c++ c# ruby php r matlab julia bash sql nosql
pytorch tensorflow keras jax scikit-learn sklearn xgboost lightgbm pandas numpy scipy spark pyspark hadoop hive flink beam
kafka rabbitmq airflow dagster prefect luigi dbt snowflake databricks bigquery redshift synapse
kubernetes docker helm terraform ansible pulumi jenkins circleci argo argocd kubeflow mlflow sagemaker vertex bedrock
aws gcp azure lambda s3 ec2 ecs eks gke aks cloudformation
postgres postgresql mysql mongodb redis cassandra dynamodb elasticsearch opensearch neo4j clickhouse
pgvector pinecone weaviate qdrant milvus chroma faiss
langchain langgraph llamaindex haystack dspy autogen crewai semantic-kernel
openai anthropic gemini llama mistral huggingface transformers vllm tgi triton onnx tensorrt cuda
rag llm llms nlp ner ocr asr tts computer-vision cv mlops llmops devops sre etl elt
fine-tuning finetuning lora qlora rlhf dpo peft distillation quantization embeddings reranking
fastapi django flask express nestjs spring rails graphql grpc rest websockets
react nextjs vue angular svelte tailwind node.js
prometheus grafana datadog opentelemetry sentry
linux git github gitlab ci/cd microservices serverless""".split()
TOOLISH = re.compile(r"\b(?:[A-Za-z]+-[0-9]+[A-Za-z]*|[A-Z][a-z]+[A-Z][A-Za-z0-9]*|[A-Z]{2,8}[0-9]*|[A-Za-z]+[0-9]+[A-Za-z0-9]*|[A-Za-z]+[+#]{1,2}|[A-Za-z]+\.(?:js|ai|io|net))(?![A-Za-z])")
NOT_SKILLS = {"ceo", "cto", "cfo", "coo", "vp", "hr", "usa", "us", "uk", "eu", "eeo", "pto", "faq", "ok", "id", "ui", "ux", "qa", "it",
              "llc", "inc", "ltd", "pvt", "gmt", "ist", "pst", "est", "utc", "am", "pm", "ctc", "lpa", "inr", "usd", "phd", "ms", "bs",
              "btech", "mtech", "be", "me", "ba", "ma", "mba", "aa", "iii", "ii", "iv", "nyc", "sf", "la", "dei", "esg", "kpi", "okr",
              "roi", "b2b", "b2c", "saas", "api", "apis", "ai", "ml", "sde", "swe", "jd", "cv", "pdf", "faqs", "covid", "covid19"}


def job_terms(text: str, *, skip: set[str] | None = None) -> list[str]:
    """Distinct tool and skill terms in a job description, in the casing it uses."""
    skip = {s.lower() for s in (skip or set())} | NOT_SKILLS
    found: dict[str, str] = {}
    # Page chrome isn't the job: email addresses, links and handles go before scanning.
    text = re.sub(r"\S+@\S+|https?://\S+|www\.\S+", " ", text or "")
    low = text.lower()
    for term in VOCAB:
        if term not in skip and re.search(r"(?<![a-z0-9])" + re.escape(term) + r"(?![a-z0-9+#])", low):
            m = re.search(re.escape(term), text, re.I)
            found.setdefault(term, m.group(0) if m else term)
    for m in TOOLISH.finditer(text or ""):
        t = m.group(0)
        if re.search(r"\d{4,}", t) or (sum(c.isdigit() for c in t) >= 3 and not re.search(r"-\d", t)):
            continue                     # requisition ids, handles with numbers, years: not skills
        if t.lower() not in skip and len(t) >= 2:
            found.setdefault(t.lower(), t)
    return sorted(found.values(), key=str.lower)
