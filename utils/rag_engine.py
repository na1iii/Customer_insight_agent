# -*- coding: utf-8 -*-
"""
rag_engine.py - RAG 核心检索与重排引擎，支持 BM25 检索、时效性衰减、LLM 重排以及 Agentic 实时网页搜索。
"""

import os
import re
import math
import json
from datetime import datetime
from typing import Any, List, Dict, Tuple, Optional
from openai import OpenAI

class DocumentChunker:
    """
    文档切片器，实现 Parent-Child 双路切分策略：
    - Child (子句段)：约 200 字，用于高精度相似度召回。
    - Parent (父句段)：关联的整篇正文（或段落上下文），用于喂给大模型以保持上下文完整。
    """
    @staticmethod
    def parse_markdown_file(file_path: str) -> Tuple[Dict, str]:
        """
        解析带有 YAML Front-Matter 的 Markdown 文档。
        返回 (metadata, content)
        """
        metadata = {}
        content = ""
        
        if not os.path.exists(file_path):
            return metadata, content
            
        with open(file_path, "r", encoding="utf-8") as f:
            raw_text = f.read()
            
        # 匹配 YAML front matter
        yaml_pattern = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
        match = yaml_pattern.match(raw_text)
        
        if match:
            yaml_text = match.group(1)
            content = raw_text[match.end():].strip()
            
            # 简单解析 key: value
            for line in yaml_text.split("\n"):
                line = line.strip()
                if line and ":" in line:
                    k, v = line.split(":", 1)
                    metadata[k.strip()] = v.strip()
        else:
            content = raw_text.strip()
            
        # 设置默认值
        file_name = os.path.basename(file_path)
        metadata.setdefault("title", file_name.replace(".md", ""))
        metadata.setdefault("publish_date", datetime.now().strftime("%Y-%m-%d"))
        metadata.setdefault("source", "本地知识库")
        
        return metadata, content

    @classmethod
    def split_to_chunks(cls, file_path: str, chunk_size: int = 220, overlap: int = 50) -> List[Dict]:
        """
        将 Markdown 按段落 (Parent) 切分成小的 Child Chunks (子块)，同时保留 Parent Content。
        引入 Heading Context Enrichment（标题上下文增强）：捕捉段落上方的标题，作为子块前缀。
        """
        metadata, full_content = cls.parse_markdown_file(file_path)
        if not full_content:
            return []
            
        chunks = []
        # 按双换行拆分段落
        paragraphs = [p.strip() for p in full_content.split("\n\n") if p.strip()]
        
        chunk_idx = 0
        current_header = ""
        for p in paragraphs:
            # 识别并保存当前的标题行（以 # 开头）
            if p.startswith("#"):
                current_header = p.lstrip("#").strip()
                continue
                
            # 将标题作为上下文拼装前缀
            content_with_header = f"[{current_header}] {p}" if current_header else p
            p_len = len(content_with_header)
            
            # 如果段落很短，直接作为一个 chunk
            if p_len <= chunk_size:
                chunk_idx += 1
                chunks.append({
                    "id": f"{metadata.get('company', 'doc')}_chunk_{chunk_idx}",
                    "content": content_with_header,
                    "parent_content": full_content,
                    "metadata": metadata
                })
            else:
                # 滑动窗口切分超长段落
                start = 0
                while start < p_len:
                    end = start + chunk_size
                    chunk_text = content_with_header[start:end]
                    chunk_idx += 1
                    chunks.append({
                        "id": f"{metadata.get('company', 'doc')}_chunk_{chunk_idx}",
                        "content": chunk_text,
                        "parent_content": full_content,
                        "metadata": metadata
                    })
                    start += (chunk_size - overlap)
                    
        return chunks

    @classmethod
    def split_doc_to_chunks(cls, doc: Dict, chunk_size: int = 220, overlap: int = 50) -> List[Dict]:
        """
        将内存中的文档字典（包含 title, content, publish_date 等）切分成小的 Child Chunks，并保留 Parent Content。
        """
        metadata = {k: v for k, v in doc.items() if k != "content"}
        metadata.setdefault("title", doc.get("title") or "未知标题")
        metadata.setdefault("publish_date", doc.get("publish_date") or datetime.now().strftime("%Y-%m-%d"))
        metadata.setdefault("source", doc.get("source") or "关系型数据库")
        metadata.setdefault("link", doc.get("link") or "")
        metadata.setdefault("company", doc.get("company") or "doc")
        full_content = doc.get("content") or ""
        if not full_content:
            return []
            
        chunks = []
        # 按换行/段落拆分
        paragraphs = [p.strip() for p in full_content.split("\n") if p.strip()]
        
        chunk_idx = 0
        current_header = ""
        for p in paragraphs:
            if p.startswith("#"):
                current_header = p.lstrip("#").strip()
                continue
                
            content_with_header = f"[{current_header}] {p}" if current_header else p
            p_len = len(content_with_header)
            
            if p_len <= chunk_size:
                chunk_idx += 1
                chunks.append({
                    "id": f"{metadata.get('company', 'doc')}_chunk_{chunk_idx}",
                    "content": content_with_header,
                    "parent_content": full_content,
                    "metadata": metadata
                })
            else:
                start = 0
                while start < p_len:
                    end = start + chunk_size
                    chunk_text = content_with_header[start:end]
                    chunk_idx += 1
                    chunks.append({
                        "id": f"{metadata.get('company', 'doc')}_chunk_{chunk_idx}",
                        "content": chunk_text,
                        "parent_content": full_content,
                        "metadata": metadata
                    })
                    start += (chunk_size - overlap)
                    
        return chunks


class BM25Retriever:
    """
    纯 Python 实现的 BM25 检索器，支持中英文分词及评分。
    """
    def __init__(self, corpus: List[Dict]):
        self.corpus = corpus
        self.doc_len = [len(doc["content"]) for doc in corpus]
        self.avg_doc_len = sum(self.doc_len) / len(corpus) if corpus else 0
        self.doc_count = len(corpus)
        
        self.dfs = {}
        self.tfs = []
        
        for doc in corpus:
            tf = {}
            tokens = self._tokenize(doc["content"])
            for token in tokens:
                tf[token] = tf.get(token, 0) + 1
            self.tfs.append(tf)
            for token in tf.keys():
                self.dfs[token] = self.dfs.get(token, 0) + 1
                
        self.idfs = {}
        for token, df in self.dfs.items():
            # 避免对数分母为0
            self.idfs[token] = math.log((self.doc_count - df + 0.5) / (df + 0.5) + 1)
            
    def _tokenize(self, text: str) -> List[str]:
        """
        中英文混合轻量分词：中文切分成单字，英文切分成单词。
        """
        tokens = []
        eng_pattern = re.compile(r'[a-zA-Z0-9]+')
        i = 0
        while i < len(text):
            char = text[i]
            # 匹配英文单词
            if eng_pattern.match(char):
                word_match = eng_pattern.match(text[i:])
                if word_match:
                    word = word_match.group()
                    tokens.append(word.lower())
                    i += len(word)
                    continue
            # 匹配中文字符
            if char.strip() and '\u4e00' <= char <= '\u9fff':
                tokens.append(char)
            i += 1
        return tokens

    def retrieve(self, query: str, top_k: int = 10, k1: float = 1.5, b: float = 0.75, metadata_filter: Dict = None) -> List[Dict]:
        if not self.corpus:
            return []
            
        query_tokens = self._tokenize(query)
        scores = []
        
        for idx, doc in enumerate(self.corpus):
            # 过滤 Metadata 条件
            if metadata_filter:
                match = True
                for k, v in metadata_filter.items():
                    if doc["metadata"].get(k) != v:
                        match = False
                        break
                if not match:
                    continue
                    
            score = 0.0
            tf_dict = self.tfs[idx]
            d_len = self.doc_len[idx]
            
            for token in query_tokens:
                if token in tf_dict:
                    tf = tf_dict[token]
                    idf = self.idfs.get(token, 0.0)
                    # 标准 BM25 评分公式
                    score += idf * (tf * (k1 + 1)) / (tf + k1 * (1.0 - b + b * (d_len / self.avg_doc_len)))
            scores.append((idx, score))
            
        scores.sort(key=lambda x: x[1], reverse=True)
        
        results = []
        for rank, (idx, score) in enumerate(scores[:top_k]):
            item = dict(self.corpus[idx])
            item["bm25_score"] = score
            item["bm25_rank"] = rank + 1
            results.append(item)
            
        return results


def parse_publish_date(value: Any) -> Optional[datetime]:
    """兼容解析业务库中常见的日期/时间字段。"""
    if not value:
        return None
    if isinstance(value, datetime):
        return value

    text = str(value).strip()
    if not text:
        return None
    text = text.replace("/", "-").replace(".", "-")

    for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y年%m月%d日", "%Y年%m月"):
        try:
            return datetime.strptime(text[:len(datetime.now().strftime(fmt))] if "%H" in fmt else text, fmt)
        except Exception:
            continue

    match = re.search(r"(20\d{2})[-年](\d{1,2})[-月](\d{1,2})", text)
    if match:
        try:
            return datetime(int(match.group(1)), int(match.group(2)), int(match.group(3)))
        except Exception:
            return None
    return None


class RAGEngine:
    """
    RAG 核心集成引擎，负责：
    1. 加载和切片本地知识库
    2. 执行 BM25 稀疏检索
    3. 执行时效性得分衰减
    4. 调用大模型重排 (Rerank)
    """
    def __init__(self, knowledge_dir: str = None, documents: List[Dict] = None):
        self.knowledge_dir = knowledge_dir
        self.documents = documents or []
        self.chunks = []
        self.bm25_retriever = None
        
        if self.knowledge_dir:
            self.load_and_index()
        elif self.documents:
            self.index_in_memory_documents()
            
    def index_in_memory_documents(self):
        """
        初始化加载：对传入的内存文档列表，构建 BM25 索引。
        """
        all_chunks = []
        for doc in self.documents:
            # 采用双路切分 (Parent-Child)
            doc_chunks = DocumentChunker.split_doc_to_chunks(doc, chunk_size=220, overlap=50)
            all_chunks.extend(doc_chunks)
            
        self.chunks = all_chunks
        print(f"【RAG Engine】内存数据源共加载了 {len(self.chunks)} 条 Child 文本切片。")
        
        if self.chunks:
            # 建立 BM25 索引
            self.bm25_retriever = BM25Retriever(self.chunks)
        
    def load_and_index(self):
        """
        初始化加载：扫描 data/knowledge 目录下的 Markdown，构建 BM25 索引。
        """
        if not os.path.exists(self.knowledge_dir):
            print(f"【RAG Engine】知识库目录 {self.knowledge_dir} 不存在，已自动创建。")
            os.makedirs(self.knowledge_dir, exist_ok=True)
            return
            
        all_chunks = []
        for file_name in os.listdir(self.knowledge_dir):
            if file_name.endswith(".md"):
                file_path = os.path.join(self.knowledge_dir, file_name)
                # 采用双路切分 (Parent-Child)
                file_chunks = DocumentChunker.split_to_chunks(file_path, chunk_size=220, overlap=50)
                all_chunks.extend(file_chunks)
                
        self.chunks = all_chunks
        print(f"【RAG Engine】共加载了 {len(self.chunks)} 条 Child 文本切片。")
        
        if self.chunks:
            # 建立 BM25 索引
            self.bm25_retriever = BM25Retriever(self.chunks)

    def retrieve(self, query: str, top_k: int = 5, decay_rate: float = 0.003, metadata_filter: Dict = None) -> List[Dict]:
        """
        执行 BM25 检索及时间衰减
        """
        if not self.chunks:
            return []
            
        # 如果未指定过滤条件，智能映射并提取公司过滤器
        if not metadata_filter:
            keyword_map = {
                "电信": "中国电信股份有限公司上海分公司",
                "移动": "中国移动通信集团上海有限公司",
                "联通": "中国联合网络通信有限公司上海市分公司",
                "钛度": "钛度智能机器人设计与研发中心",
                "特斯拉": "特斯拉"
            }
            for kw, comp in keyword_map.items():
                if kw in query:
                    metadata_filter = {"company": comp}
                    break
            
        # 1. 单路 BM25 检索
        bm25_res = self.bm25_retriever.retrieve(query, top_k=top_k * 2, metadata_filter=metadata_filter)
        
        # 2. 时效性衰减 (Temporal Policy)
        now = datetime.now()
        results = []
        for doc in bm25_res:
            pub_date_str = doc["metadata"].get("publish_date", "")
            
            decay_factor = 1.0
            if pub_date_str:
                pub_date = parse_publish_date(pub_date_str)
                if pub_date:
                    days_diff = (now - pub_date).days
                    # 时间衰减公式：e^(-decay_rate * days_diff)
                    decay_factor = math.exp(-decay_rate * max(0, days_diff))
                else:
                    decay_factor = 1.0
            else:
                decay_factor = 0.8 # 缺省日期罚分
                
            doc["temporal_decay"] = decay_factor
            # 融合最终分数 (直接以 bm25_score 代替 rrf_score)
            doc["final_score"] = doc.get("bm25_score", 0.0) * decay_factor
            results.append(doc)
            
        # 按最终分数排序并截取 Top-K
        results.sort(key=lambda x: x["final_score"], reverse=True)
        return results[:top_k]

    def rerank(self, query: str, docs: List[Dict], api_key: str, base_url: str, model_name: str) -> List[Dict]:
        """
        利用大模型 (LLM) 对检索出的 Chunks 进行精准打分与重排 (Reranker)
        """
        if not api_key or "your_api_key" in api_key or not docs:
            # 无有效 Key 降级不重排，保留原始 final_score 排序
            for doc in docs:
                doc["rerank_score"] = doc.get("final_score", 0.0)
            return docs
            
        try:
            client = OpenAI(api_key=api_key, base_url=base_url)
            
            docs_to_grade = []
            for idx, doc in enumerate(docs):
                docs_to_grade.append({
                    "index": idx,
                    "content": doc["content"],
                    "title": doc["metadata"].get("title", "")
                })
                
            system_prompt = (
                "你是一个高精度的 Rerank 重排评判器。请阅读用户的问题以及给出的检索文档片段，"
                "客观判断该文档片段对回答用户问题沾不沾边、有多大帮助，并给出一个 0.0 到 1.0 之间的相关性评分。\n"
                "其中：0.0 代表完全不相关，1.0 代表能完全、直接解答该提问。\n"
                "【重要判定准则】：\n"
                "如果用户问题中的查询实体/公司在待评文档中仅仅是作为背景介绍、偶发的提及、创始人的过往实习/工作经历、"
                "或者纯粹作为外部对比出现，而【不是】该文档片段的核心讨论/论述主体，请务必给其打极低分（低于 0.3，例如 0.0 至 0.2）。\n"
                "你必须输出且仅输出一个合法的 JSON 对象，格式如下：\n"
                "{\n"
                "  \"reranked\": [\n"
                "    {\"index\": 0, \"relevance_score\": 0.95},\n"
                "    {\"index\": 1, \"relevance_score\": 0.12}\n"
                "  ]\n"
                "}\n"
                "不要包含 ```json markdown 标记，不要有任何多余的开头或解释性言论。"
            )
            
            user_prompt = f"用户问题: {query}\n\n待评文档:\n{json.dumps(docs_to_grade, ensure_ascii=False)}"
            
            response = client.chat.completions.create(
                model=model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                response_format={"type": "json_object"},
                temperature=0.0,
                timeout=30.0
            )
            
            content = response.choices[0].message.content
            data = json.loads(content)
            
            # 提取评分映射
            scores_map = {item["index"]: item["relevance_score"] for item in data.get("reranked", [])}
            
            reranked_docs = []
            for idx, doc in enumerate(docs):
                score = scores_map.get(idx, doc.get("final_score", 0.0))
                doc["rerank_score"] = score
                reranked_docs.append(doc)
                
            # 重新根据 Rerank 分数降序排列
            reranked_docs.sort(key=lambda x: x["rerank_score"], reverse=True)
            return reranked_docs
            
        except Exception as e:
            print(f"【Rerank Error】LLM Rerank 失败: {e}，降级保留原混合排序结果。")
            for doc in docs:
                doc["rerank_score"] = doc.get("final_score", 0.0)
            return docs
