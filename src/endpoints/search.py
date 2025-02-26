from fastapi import APIRouter, HTTPException, Request, Depends
from fastapi.responses import JSONResponse
from fastapi_limiter.depends import RateLimiter
from src.services.embeding_service import EmbeddingService
from src.utils.pinecone_utils import get_pinecone_index
from src.utils.logger_config import AppLogger
from src.config import Config
import traceback

# Configuration and logger
config = Config()
app_logger = AppLogger()
logger = app_logger.logger

embedding_service = EmbeddingService()
router = APIRouter()

@router.get("/search/", dependencies=[Depends(RateLimiter(times=config.search_rate_limit, seconds=60))], response_class=JSONResponse)
async def search(query: str, request: Request):
    try:
        client_ip = request.client.host
        logger.info(f"Received search query from {client_ip}: {query}")

        if not query.strip():
            raise HTTPException(status_code=400, detail="Query cannot be empty.")

        query_embedding = embedding_service.generate_embedding(query).tolist()
        index = get_pinecone_index()
        results = index.query(vector=query_embedding, top_k=config.search_top_k, include_metadata=True)

        if "matches" not in results or not results["matches"]:
            return {"query": query, "results": [], "warning": "No matching documents found."}

        readable_results = [
            {
                "document_id": match.get("id", "unknown"),
                "relevance_score": round(match.get("score", 0), 2),
                "short_answer": embedding_service.refine_answer_based_on_query(
                    query,
                    embedding_service.extract_semantically_relevant_answer(match["metadata"].get("content", ""), query)
                ),
                "details": match["metadata"]
            }
            for match in results["matches"]
        ]

        logger.info(f"Search results: {len(readable_results)} documents found.")
        return {"query": query, "results": readable_results}
    except Exception as e:
        if config.debug_mode:
            logger.error(f"Unhandled exception: {traceback.format_exc()}")
        else:
            logger.error(f"Unhandled exception: {str(e)}")
        raise HTTPException(status_code=500, detail="An unexpected error occurred.")
