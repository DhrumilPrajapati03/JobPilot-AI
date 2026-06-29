import os
import sys

# 1. Ensure the 'backend' folder is in Python's path so we can import 'app'
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.models.resume import Resume, ResumeExperience, ResumeSkills
from app.services.vector_store import embed_resume, search_relevant
from app.services.llm import get_embeddings_client

def test_pipeline():
    print("==================================================")
    print("🤖 STARTING CHROMADB & EMBEDDING TESTS")
    print("==================================================")

    # 2. Verify which embedding client is loaded
    try:
        client = get_embeddings_client()
        print(f"✅ Embedding client initialized successfully!")
        print(f"   Model Class: {client.__class__.__name__}")
    except Exception as e:
        print(f"❌ Failed to initialize embedding client: {str(e)}")
        return

    # 3. Create a mock resume matching your Pydantic schemas
    # This represents a typical AI/ML engineer's resume
    mock_resume = Resume(
        name="Dhrumil Prajapati",
        headline="AI/ML Engineer",
        summary="AI Engineer specialized in agentic workflows and retrieval systems.",
        experience=[
            ResumeExperience(
                company="JobPilot AI Corp",
                role="Lead AI Developer",
                duration="2024-Present",
                bullets=[
                    "Developed a semantic search engine using local ChromaDB and Hugging Face Serverless APIs.",
                    "Designed secure token-based authorization workflows using FastAPI, JWKS, and Supabase RLS.",
                    "Maintained a legacy Python service, optimizing SQL queries and memory performance."
                ]
            )
        ],
        skills=ResumeSkills(
            primary=["Python", "FastAPI", "ChromaDB", "LangChain"],
            secondary=["PostgreSQL", "Docker", "Git"]
        )
    )

    # 4. Try embedding the resume
    user_id = "test-learning-user-777"
    print("\n--- Step A: Embedding Resume Chunks ---")
    try:
        embed_resume(user_id, mock_resume)
    except Exception as e:
        print(f"❌ Failed to embed resume: {str(e)}")
        return

    # 5. Run Semantic Queries
    print("\n--- Step B: Running Semantic Queries ---")
    
    # Query 1: Test security authorization concepts
    query_1 = "FastAPI authorization and security"
    print(f"\n🔍 Query 1: '{query_1}'")
    results_1 = search_relevant(query_1, user_id, top_k=2)
    for idx, r in enumerate(results_1):
        print(f"  [{idx + 1}] (Distance: {r['distance']:.4f}) -> {r['text']}")

    # Query 2: Test database/storage concepts
    query_2 = "vector database indexing and search"
    print(f"\n🔍 Query 2: '{query_2}'")
    results_2 = search_relevant(query_2, user_id, top_k=2)
    for idx, r in enumerate(results_2):
        print(f"  [{idx + 1}] (Distance: {r['distance']:.4f}) -> {r['text']}")

    print("\n==================================================")
    print("🎉 ALL TESTS EXECUTED")
    print("==================================================")

if __name__ == "__main__":
    test_pipeline()