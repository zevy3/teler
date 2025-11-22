import asyncio, re, time
from chromadb import HttpClient
from hashlib import sha256
from source.Logging import Logger
from source.TelegramMessageScrapper.Base import Scrapper
from sentence_transformers import SentenceTransformer
from typing import List, Tuple, Optional
from openai import OpenAI

from source.ChromaAndRAG.prompts import SYSTEM_PROMPT

def _get_collection_name(channel_id: int) -> str:
    """Converts a channel ID to a valid ChromaDB collection name."""
    return f"collection_{abs(channel_id)}"

class RagClient:
    def __init__(self, host: str, port: int, n_result: int, model: str, mistral_api_key: str, mistral_model: str, scrapper: Scrapper):
        self.rag_logger = Logger("RAG_module", "network.log")
        self.client = HttpClient(port=port, host=host)
        self.Scrapper = scrapper
        self.channel_request_queue: asyncio.Queue[Tuple[int, str, List[int]]] = asyncio.Queue()
        self.rag_response_queue: asyncio.Queue = asyncio.Queue()
        self.SentenceTransformer = SentenceTransformer(model)
        self.running = True
        self.n_result = n_result
        self.mistral_client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=mistral_api_key,
            default_headers={
                "HTTP-Referer": "http://localhost:3000",
                "X-Title": "TeleRag",
            },
        )
        self.mistral_model_str = mistral_model
        self._query_task: Optional[asyncio.Task] = None
        self._data_task: Optional[asyncio.Task] = None

    async def create_collection_if_not_exists(self, channel_id: int, channel_name: str):
        try:
            collection_name = _get_collection_name(channel_id)
            self.client.get_or_create_collection(
                name=collection_name,
                metadata={"channel_name": channel_name}
            )
            await self.rag_logger.info(f"Ensured collection {collection_name} exists for channel '{channel_name}'.")
        except Exception as e:
            await self.rag_logger.error(f"Failed to create or verify collection {collection_name}: {e}")

    async def delete_channel(self, channel_id: int):
        collection_name = _get_collection_name(channel_id)
        try:
            self.client.delete_collection(collection_name)
            await self.rag_logger.info(f"Deleted collection {collection_name}.")
        except Exception as e:
            await self.rag_logger.warning(f"Could not delete collection {collection_name}: {e}")

    async def query(self, user_id: int, request: str, channel_ids: List[int]):
        await self.channel_request_queue.put((user_id, request, channel_ids))

    def chunk_and_encode(self, text: str, max_chunk_size: int = 512):
        sentences = re.split(r'(?<=[.!?])\s+', text)
        chunks, current_chunk = [], []
        for sentence in sentences:
            if sum(len(s) for s in current_chunk) + len(sentence) <= max_chunk_size:
                current_chunk.append(sentence)
            else:
                if current_chunk: chunks.append(" ".join(current_chunk))
                current_chunk = [sentence]
        if current_chunk: chunks.append(" ".join(current_chunk))
        
        return [(chunk, self.SentenceTransformer.encode(chunk)) for chunk in chunks if chunk.strip()]

    async def start_rag(self):
        if self._query_task is None or self._query_task.done(): self._query_task = asyncio.create_task(self._query_loop())
        if self._data_task is None or self._data_task.done(): self._data_task = asyncio.create_task(self._data_loop())

    async def _data_loop(self):
        self.Scrapper.getting_messages_event.set()
        await self.rag_logger.info("RAG data loop started. Scrapper is now being polled.")
        while self.running:
            try:
                async for channel_id, channel_name, msg in self.Scrapper:
                    if not self.running: break
                    collection = self.client.get_or_create_collection(
                        name=_get_collection_name(channel_id),
                        metadata={"channel_name": channel_name}
                    )
                    embedded_chunks = self.chunk_and_encode(msg)
                    if not embedded_chunks: continue
                    
                    ids = [sha256(chunk.encode()).hexdigest() for chunk, _ in embedded_chunks]
                    embeddings = [emb.tolist() for _, emb in embedded_chunks]
                    documents = [chunk for chunk, _ in embedded_chunks]
                    metadatas = [{"channel_name": channel_name} for _ in embedded_chunks]

                    collection.add(ids=ids, embeddings=embeddings, documents=documents, metadatas=metadatas)
                    await self.rag_logger.info(f"Added {len(embedded_chunks)} new document(s) to collection for channel '{channel_name}'")
            except asyncio.CancelledError:
                await self.rag_logger.info("Data loop cancelled.")
                break
            except Exception as e:
                await self.rag_logger.error(f"Error in data loop: {e}")
                await asyncio.sleep(5)

    async def _query_loop(self):
        while self.running:
            try:
                user_id, request, channel_ids = await self.channel_request_queue.get()
                start_time = time.monotonic()
                
                query_embedding = self.SentenceTransformer.encode(request).tolist()
                relevant_docs = []
                source_names = set()

                for channel_id in channel_ids:
                    try:
                        collection = self.client.get_collection(_get_collection_name(channel_id))
                        results = collection.query(query_embeddings=[query_embedding], n_results=self.n_result)
                        docs = results.get('documents', [[]])[0]
                        metadatas = results.get('metadatas', [[]])[0]
                        
                        if docs:
                            for i, doc in enumerate(docs):
                                channel_name = metadatas[i].get("channel_name", f"ID: {channel_id}")
                                source_names.add(channel_name)
                                relevant_docs.append(f"Источник: {channel_name}\nСодержание: {doc}\n---")

                    except Exception as e:
                        await self.rag_logger.warning(f"Could not query collection for channel {channel_id}: {e}")

                if not relevant_docs:
                    await self.rag_response_queue.put((user_id, "В ваших источниках нет информации по этому запросу."))
                    continue
                
                context = "\n".join(relevant_docs)
                
                user_prompt = f"ТЕКСТ:\n{context}\n\nВОПРОС: {request}"

                response = self.mistral_client.chat.completions.create(
                    model=self.mistral_model_str,
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": user_prompt}
                    ]
                )
                
                final_response = response.choices[0].message.content
                
                await self.rag_response_queue.put((user_id, final_response))
                await self.rag_logger.info(f"Generated response for {user_id} in {time.monotonic() - start_time:.2f}s")
            
            except asyncio.CancelledError:
                await self.rag_logger.info("Query loop cancelled.")
                break
            except Exception as e:
                await self.rag_logger.error(f"Error in RAG request: {e}")
                user_id_for_error = locals().get('user_id', 'unknown')
                await self.rag_response_queue.put((user_id_for_error, "Произошла ошибка при обработке запроса."))

    def stop(self):
        self.running = False
        if self._data_task: self._data_task.cancel()
        if self._query_task: self._query_task.cancel()
