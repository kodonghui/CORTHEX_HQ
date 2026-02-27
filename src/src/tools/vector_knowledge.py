"""벡터 지식베이스 도구 — 의미 기반 지식 검색 (RAG)."""
from __future__ import annotations

import json
import logging
import os
from typing import Any

from src.tools.base import BaseTool

logger = logging.getLogger("corthex.tools.vector_knowledge")

VECTOR_DB_DIR = os.path.join(os.getcwd(), "data", "vector_db")


def _get_chromadb():
    try:
        import chromadb
        return chromadb
    except ImportError:
        return None


def _get_openai():
    try:
        import openai
        return openai
    except ImportError:
        return None


class VectorKnowledgeTool(BaseTool):
    """의미 기반 지식 검색 도구 — ChromaDB + OpenAI Embeddings으로 RAG 구현."""

    EMBEDDING_MODEL = "text-embedding-3-small"

    def _get_client(self):
        """ChromaDB 영구 클라이언트 생성."""
        chromadb = _get_chromadb()
        if chromadb is None:
            return None, "chromadb 라이브러리가 설치되지 않았습니다. pip install chromadb"

        os.makedirs(VECTOR_DB_DIR, exist_ok=True)
        try:
            client = chromadb.PersistentClient(path=VECTOR_DB_DIR)
            return client, None
        except Exception as e:
            return None, f"ChromaDB 초기화 실패: {e}"

    def _get_embedding(self, text: str) -> list[float] | str:
        """OpenAI 임베딩 생성."""
        openai = _get_openai()
        if openai is None:
            return "openai 라이브러리가 설치되지 않았습니다."

        api_key = os.getenv("OPENAI_API_KEY", "")
        if not api_key:
            return "OPENAI_API_KEY 환경변수가 설정되지 않았습니다."

        try:
            client = openai.OpenAI(api_key=api_key)
            response = client.embeddings.create(model=self.EMBEDDING_MODEL, input=text)
            return response.data[0].embedding
        except Exception as e:
            return f"임베딩 생성 실패: {e}"

    async def execute(self, **kwargs: Any) -> Any:
        action = kwargs.get("action", "search")
        if action == "search":
            return await self._search(kwargs)
        elif action == "add":
            return await self._add(kwargs)
        elif action == "add_file":
            return await self._add_file(kwargs)
        elif action == "list":
            return await self._list_collections(kwargs)
        elif action == "delete":
            return await self._delete(kwargs)
        elif action == "stats":
            return await self._stats(kwargs)
        else:
            return (
                f"알 수 없는 action: {action}\n"
                "사용 가능한 action: search(검색), add(추가), add_file(파일 추가), "
                "list(컬렉션 목록), delete(삭제), stats(통계)"
            )

    async def _search(self, kwargs: dict) -> str:
        """의미 기반 검색 (RAG)."""
        query = kwargs.get("query", "")
        collection_name = kwargs.get("collection", "default")
        top_k = int(kwargs.get("top_k", 5))

        if not query:
            return "검색어(query)를 입력해주세요."

        client, err = self._get_client()
        if err:
            return err

        try:
            collection = client.get_collection(name=collection_name)
        except Exception:
            return f"컬렉션 '{collection_name}'을 찾을 수 없습니다. add action으로 먼저 지식을 추가하세요."

        query_embedding = self._get_embedding(query)
        if isinstance(query_embedding, str):
            return query_embedding

        try:
            results = collection.query(
                query_embeddings=[query_embedding],
                n_results=min(top_k, collection.count()),
            )
        except Exception as e:
            return f"검색 실패: {e}"

        docs = results.get("documents", [[]])[0]
        distances = results.get("distances", [[]])[0]
        metadatas = results.get("metadatas", [[]])[0]

        if not docs:
            return f"'{query}'에 대한 관련 지식을 찾을 수 없습니다."

        lines = [f"## 지식 검색 결과: {query}\n"]
        context_parts: list[str] = []

        for i, (doc, dist, meta) in enumerate(zip(docs, distances, metadatas), 1):
            similarity = max(0, 1 - dist)  # distance → similarity
            source = meta.get("source", "알 수 없음") if meta else "알 수 없음"
            lines.append(f"### {i}. 유사도: {similarity:.2f} (출처: {source})")
            lines.append(f"{doc[:300]}{'...' if len(doc) > 300 else ''}\n")
            context_parts.append(doc)

        # RAG: 검색 결과를 컨텍스트로 LLM 답변 생성
        context = "\n\n---\n\n".join(context_parts)
        answer = await self._llm_call(
            system_prompt=(
                "당신은 조직 지식을 활용하는 전문가입니다. "
                "아래 참고 자료를 바탕으로 질문에 답변하세요.\n"
                "참고 자료에 없는 내용은 '참고 자료에서 확인할 수 없습니다'라고 말하세요."
            ),
            user_prompt=f"질문: {query}\n\n참고 자료:\n{context[:5000]}",
        )

        formatted = "\n".join(lines)
        return f"{formatted}\n---\n\n## 답변\n\n{answer}"

    async def _add(self, kwargs: dict) -> str:
        """지식 추가."""
        text = kwargs.get("text", "")
        collection_name = kwargs.get("collection", "default")
        source = kwargs.get("source", "manual")

        if not text:
            return "추가할 텍스트(text)를 입력해주세요."

        client, err = self._get_client()
        if err:
            return err

        embedding = self._get_embedding(text)
        if isinstance(embedding, str):
            return embedding

        try:
            collection = client.get_or_create_collection(name=collection_name)
            doc_id = f"doc_{collection.count() + 1}"
            collection.add(
                documents=[text],
                embeddings=[embedding],
                metadatas=[{"source": source, "added_at": str(__import__("datetime").datetime.now())}],
                ids=[doc_id],
            )
            logger.info("지식 추가: %s (컬렉션: %s)", doc_id, collection_name)
            return (
                f"## 지식 추가 완료\n\n"
                f"- 컬렉션: {collection_name}\n"
                f"- 문서 ID: {doc_id}\n"
                f"- 텍스트 길이: {len(text)}자\n"
                f"- 출처: {source}\n"
                f"- 총 문서 수: {collection.count()}"
            )
        except Exception as e:
            return f"지식 추가 실패: {e}"

    async def _add_file(self, kwargs: dict) -> str:
        """파일 내용을 청크로 분할하여 일괄 추가."""
        file_path = kwargs.get("file_path", "")
        collection_name = kwargs.get("collection", "default")
        chunk_size = int(kwargs.get("chunk_size", 500))
        overlap = int(kwargs.get("overlap", 50))

        if not file_path or not os.path.isfile(file_path):
            return f"파일을 찾을 수 없습니다: {file_path}"

        # 파일 읽기
        ext = file_path.lower().rsplit(".", 1)[-1] if "." in file_path else ""
        if ext == "pdf":
            try:
                import fitz
                doc = fitz.open(file_path)
                text = "\n".join(page.get_text() for page in doc)
                doc.close()
            except ImportError:
                return "PDF 읽기에 PyMuPDF가 필요합니다. pip install PyMuPDF"
        elif ext in ("md", "txt", "csv"):
            with open(file_path, "r", encoding="utf-8") as f:
                text = f.read()
        else:
            return f"지원하지 않는 파일 형식: .{ext} (md, txt, csv, pdf 지원)"

        if not text.strip():
            return "파일 내용이 비어있습니다."

        # 청크 분할
        chunks = []
        for i in range(0, len(text), chunk_size - overlap):
            chunk = text[i:i + chunk_size]
            if chunk.strip():
                chunks.append(chunk)

        client, err = self._get_client()
        if err:
            return err

        # 일괄 임베딩 + 저장
        openai = _get_openai()
        api_key = os.getenv("OPENAI_API_KEY", "")
        if not openai or not api_key:
            return "OPENAI_API_KEY가 필요합니다."

        try:
            oa_client = openai.OpenAI(api_key=api_key)
            response = oa_client.embeddings.create(model=self.EMBEDDING_MODEL, input=chunks)
            embeddings = [item.embedding for item in response.data]

            collection = client.get_or_create_collection(name=collection_name)
            base_id = collection.count()
            source = os.path.basename(file_path)

            collection.add(
                documents=chunks,
                embeddings=embeddings,
                metadatas=[{"source": source, "chunk": i} for i in range(len(chunks))],
                ids=[f"doc_{base_id + i + 1}" for i in range(len(chunks))],
            )

            logger.info("파일 지식 추가: %s (%d 청크)", file_path, len(chunks))
            return (
                f"## 파일 지식 추가 완료\n\n"
                f"- 파일: {file_path}\n"
                f"- 컬렉션: {collection_name}\n"
                f"- 청크 수: {len(chunks)}개\n"
                f"- 청크 크기: {chunk_size}자 (겹침: {overlap}자)\n"
                f"- 총 문서 수: {collection.count()}"
            )
        except Exception as e:
            return f"파일 지식 추가 실패: {e}"

    async def _list_collections(self, kwargs: dict) -> str:
        """컬렉션 목록 조회."""
        client, err = self._get_client()
        if err:
            return err

        try:
            collections = client.list_collections()
            if not collections:
                return "저장된 컬렉션이 없습니다. add action으로 지식을 추가하세요."

            lines = ["## 지식베이스 컬렉션 목록\n"]
            lines.append("| 컬렉션 | 문서 수 |")
            lines.append("|--------|--------|")
            for col in collections:
                lines.append(f"| {col.name} | {col.count()} |")

            return "\n".join(lines)
        except Exception as e:
            return f"컬렉션 목록 조회 실패: {e}"

    async def _delete(self, kwargs: dict) -> str:
        """지식 삭제."""
        collection_name = kwargs.get("collection", "")
        doc_id = kwargs.get("doc_id", "")

        if not collection_name:
            return "삭제할 컬렉션 이름(collection)을 입력해주세요."

        client, err = self._get_client()
        if err:
            return err

        try:
            if doc_id:
                collection = client.get_collection(name=collection_name)
                collection.delete(ids=[doc_id])
                return f"문서 삭제 완료: {doc_id} (컬렉션: {collection_name})"
            else:
                client.delete_collection(name=collection_name)
                return f"컬렉션 삭제 완료: {collection_name}"
        except Exception as e:
            return f"삭제 실패: {e}"

    async def _stats(self, kwargs: dict) -> str:
        """저장 통계."""
        client, err = self._get_client()
        if err:
            return err

        try:
            collections = client.list_collections()
            total_docs = sum(col.count() for col in collections)

            lines = [
                f"## 벡터 지식베이스 통계\n",
                f"- 컬렉션 수: {len(collections)}개",
                f"- 총 문서 수: {total_docs}개",
                f"- 저장 경로: {VECTOR_DB_DIR}",
                f"- 임베딩 모델: {self.EMBEDDING_MODEL}",
            ]

            return "\n".join(lines)
        except Exception as e:
            return f"통계 조회 실패: {e}"
