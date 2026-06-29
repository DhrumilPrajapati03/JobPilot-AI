import os
import chromadb
from app.models.resume import Resume
from app.services.llm import get_embeddings_client

# 1. Initialize the persistent local Chroma DB client
# This creates a folder "data/chroma" inside your backend directory to persist data
CHROMA_PATH = os.path.join(os.getcwd(), "data", "chroma")
chroma_client = chromadb.PersistentClient(path=CHROMA_PATH)

# Get or create our vector collection
# We pass the LangChain embedding client's embedding functions so Chroma uses it automatically
embeddings_client = get_embeddings_client()

# Chroma requires an embedding function dictionary format
class ChromaEmbeddingFunction:
    def __call__(self, input: list[str]) -> list[list[float]]:
        return embeddings_client.embed_documents(input)

    def name(self) -> str:
        return "custom"

    def embed_query(self, input: list[str]) -> list[list[float]]:
        # In ChromaDB, embed_query takes a list of strings and returns their embeddings
        return self.__call__(input)

collection = chroma_client.get_or_create_collection(
    name="resume_sections",
    embedding_function=ChromaEmbeddingFunction()
)


def embed_resume(user_id: str, resume: Resume) -> None:
    """Chunks, embeds, and saves a user's resume sections into ChromaDB.
    
    Before saving, it purges any old chunks for this user to avoid duplicates.
    """
    # Step A: Delete any existing records in Chroma for this user
    # Chroma allows metadata filtering to ensure you only delete/query your own data
    try:
        collection.delete(where={"user_id": user_id})
    except Exception as e:
        print(f"No existing embeddings to delete for user {user_id}: {str(e)}")

    # Step B: Parse the Pydantic Resume model into individual text documents
    documents = []
    metadatas = []
    ids = []

    # 1. Chunk: Professional Summary
    if resume.summary:
        documents.append(resume.summary)
        metadatas.append({"user_id": user_id, "section_type": "summary"})
        ids.append(f"{user_id}_summary")

    # 2. Chunk: Work Experience (embed each bullet point individually!)
    # Why? We want granular match. E.g., if a JD requires Docker, we want the specific bullet
    # describing how you used Docker, rather than your entire work history text block.
    for exp_idx, exp in enumerate(resume.experience):
        for bullet_idx, bullet in enumerate(exp.bullets):
            documents.append(bullet)
            metadatas.append({
                "user_id": user_id,
                "section_type": "experience",
                "company": exp.company,
                "role": exp.role,
                "experience_index": exp_idx,
                "bullet_index": bullet_idx
            })
            ids.append(f"{user_id}_exp_{exp_idx}_bullet_{bullet_idx}")

    # 3. Chunk: Projects
    for proj_idx, proj in enumerate(resume.projects):
        proj_text = f"Project: {proj.name}. Description: {proj.description}. Tech: {', '.join(proj.tech)}"
        documents.append(proj_text)
        metadatas.append({
            "user_id": user_id,
            "section_type": "project",
            "project_name": proj.name,
            "project_index": proj_idx
        })
        ids.append(f"{user_id}_project_{proj_idx}")

    # 4. Chunk: Skills (combining them into a clean string)
    primary_skills = ", ".join(resume.skills.primary)
    secondary_skills = ", ".join(resume.skills.secondary)
    
    if primary_skills:
        documents.append(f"Primary Skills: {primary_skills}")
        metadatas.append({"user_id": user_id, "section_type": "skills_primary"})
        ids.append(f"{user_id}_skills_primary")
        
    if secondary_skills:
        documents.append(f"Secondary Skills: {secondary_skills}")
        metadatas.append({"user_id": user_id, "section_type": "skills_secondary"})
        ids.append(f"{user_id}_skills_secondary")

    # Step C: Write to ChromaDB
    if documents:
        collection.add(
            documents=documents,
            metadatas=metadatas,
            ids=ids
        )
        print(f"Successfully embedded {len(documents)} sections for user {user_id}")


def search_relevant(query: str, user_id: str, top_k: int = 5) -> list[dict]:
    """Queries ChromaDB for resume chunks semantically similar to the input query.
    
    Filters search results specifically for the requesting user.
    """
    results = collection.query(
        query_texts=[query],
        n_results=top_k,
        where={"user_id": user_id}  # Security gate: prevents reading other users' embeddings
    )
    
    formatted_results = []
    if not results or not results["documents"]:
        return formatted_results

    # Chroma returns results as dictionary lists: docs, metadatas, distances, ids
    # Let's clean it up for our AI agent to consume
    docs = results["documents"][0]
    metadata_list = results["metadatas"][0]
    distances = results["distances"][0] if results.get("distances") else [0.0] * len(docs)

    for i in range(len(docs)):
        formatted_results.append({
            "text": docs[i],
            "metadata": metadata_list[i],
            "distance": distances[i]  # Lower distance = closer match (higher similarity)
        })

    return formatted_results
