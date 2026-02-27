"""
Automated Slot Studio - RAG Document Ingestion (v2)

Enhanced with US State Regulation support.
Ingests regulatory docs into Qdrant with state-level metadata.

Usage:
    python -m tools.ingest_regulations --source data/regulations/ --collection slot_regulations
    python -m tools.ingest_regulations --auto-states
"""
import argparse, hashlib, json, os, sys
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv
from rich.console import Console
from rich.progress import track

load_dotenv()
console = Console()

JURISDICTION_MAP = {
    "georgia": "Georgia", "texas": "Texas", "virginia": "Virginia",
    "illinois": "Illinois", "nebraska": "Nebraska", "wyoming": "Wyoming",
    "south_dakota": "South Dakota", "south-dakota": "South Dakota",
    "southdakota": "South Dakota",
    "ukgc": "UK", "mga": "Malta", "ontario": "Ontario",
    "agco": "Ontario", "gli": "GLI", "nj": "New Jersey",
    "new_jersey": "New Jersey", "curacao": "Curacao",
}
US_STATES = {"Georgia", "Texas", "Virginia", "Illinois", "Nebraska", "Wyoming", "South Dakota"}


def detect_jurisdiction(file_path: Path, override: Optional[str] = None) -> str:
    if override:
        return override
    name_lower = file_path.stem.lower()
    parent_lower = file_path.parent.name.lower()
    for key, jurisdiction in JURISDICTION_MAP.items():
        if key in name_lower or key in parent_lower:
            return jurisdiction
    return "general"


def chunk_text(text: str, chunk_size: int = 800, overlap: int = 200) -> list[dict]:
    chunks = []
    words = text.split()
    lines = text.split("\n")
    current_section = "General"
    section_map = {}
    word_count = 0
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("## ") or stripped.startswith("# "):
            current_section = stripped.lstrip("#").strip()
        line_words = len(line.split())
        for w in range(line_words):
            section_map[word_count + w] = current_section
        word_count += line_words
    i = 0
    while i < len(words):
        chunk_words = words[i:i + chunk_size]
        chunk_text_str = " ".join(chunk_words)
        section = section_map.get(i, "General")
        chunks.append({"text": chunk_text_str, "start_word": i,
                        "end_word": min(i + chunk_size, len(words)), "section": section})
        i += chunk_size - overlap
    return chunks


def extract_text_from_pdf(pdf_path: str) -> str:
    try:
        import fitz
        doc = fitz.open(pdf_path)
        return "\n".join(page.get_text() for page in doc)
    except ImportError:
        try:
            import pdfplumber
            with pdfplumber.open(pdf_path) as pdf:
                return "\n".join(page.extract_text() or "" for page in pdf.pages)
        except ImportError:
            console.print("[red]Install pymupdf or pdfplumber[/red]")
            return ""


def get_embeddings(texts: list[str], model: str = "text-embedding-3-small") -> list[list[float]]:
    from openai import OpenAI
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    all_embeddings = []
    for i in range(0, len(texts), 100):
        batch = texts[i:i + 100]
        response = client.embeddings.create(model=model, input=batch)
        all_embeddings.extend([item.embedding for item in response.data])
    return all_embeddings


def classify_doc_type(text: str, filename: str) -> str:
    text_lower = text[:2000].lower()
    if any(w in text_lower for w in ["loophole", "strategy", "pathway", "compliance checklist"]):
        return "compliance_strategy"
    if any(w in text_lower for w in ["statute", "code §", "sdcl", "o.c.g.a", "penal code"]):
        return "statute_reference"
    if any(w in text_lower for w in ["gli-11", "gli-12", "technical standard"]):
        return "technical_standard"
    if "us_states" in filename.lower():
        return "us_state_regulation"
    return "general_regulation"


def ingest_documents(source_dir: str, collection_name: str = "slot_regulations",
                     jurisdiction: Optional[str] = None, chunk_size: int = 800, chunk_overlap: int = 200):
    from qdrant_client import QdrantClient
    from qdrant_client.models import Distance, VectorParams, PointStruct

    qdrant_url = os.getenv("QDRANT_URL", "http://localhost:6333")
    qdrant_key = os.getenv("QDRANT_API_KEY", "")
    console.print(f"[cyan]Connecting to Qdrant: {qdrant_url}[/cyan]")
    client = QdrantClient(url=qdrant_url, api_key=qdrant_key)

    collections = [c.name for c in client.get_collections().collections]
    if collection_name not in collections:
        client.create_collection(collection_name=collection_name,
                                  vectors_config=VectorParams(size=1536, distance=Distance.COSINE))
        console.print(f"[green]Created collection: {collection_name}[/green]")

    source_path = Path(source_dir)
    supported = {".pdf", ".txt", ".md"}
    documents = [source_path] if source_path.is_file() else [
        f for f in source_path.rglob("*") if f.suffix.lower() in supported]
    console.print(f"\n📄 Found {len(documents)} documents")

    all_chunks, all_metadata = [], []
    for doc_path in track(documents, description="Processing..."):
        text = (extract_text_from_pdf(str(doc_path)) if doc_path.suffix.lower() == ".pdf"
                else doc_path.read_text(encoding="utf-8", errors="ignore"))
        if not text.strip():
            continue
        doc_jurisdiction = detect_jurisdiction(doc_path, jurisdiction)
        doc_type = classify_doc_type(text, str(doc_path))
        console.print(f"  📋 {doc_path.name} → [cyan]{doc_jurisdiction}[/cyan] ({doc_type})")
        for chunk in chunk_text(text, chunk_size, chunk_overlap):
            all_chunks.append(chunk["text"])
            all_metadata.append({"source": doc_path.name, "jurisdiction": doc_jurisdiction,
                                  "section": chunk.get("section", "General"), "document_type": doc_type,
                                  "is_us_state": doc_jurisdiction in US_STATES})

    if not all_chunks:
        console.print("[red]No text extracted.[/red]")
        return

    console.print(f"\n🧩 {len(all_chunks)} chunks → computing embeddings...")
    embeddings = get_embeddings(all_chunks)
    console.print("💾 Uploading to Qdrant...")
    points = []
    for embedding, metadata, text in zip(embeddings, all_metadata, all_chunks):
        point_id = int(hashlib.md5(text.encode()).hexdigest()[:16], 16) % (2**63)
        points.append(PointStruct(id=point_id, vector=embedding, payload={"text": text, **metadata}))
    for i in track(range(0, len(points), 100), description="Uploading..."):
        client.upsert(collection_name=collection_name, points=points[i:i + 100])

    console.print(f"\n[green]✅ Ingested {len(points)} chunks into '{collection_name}'[/green]")
    jurisdictions = {}
    for m in all_metadata:
        j = m["jurisdiction"]
        jurisdictions[j] = jurisdictions.get(j, 0) + 1
    console.print("\n📊 Chunks by jurisdiction:")
    for j, count in sorted(jurisdictions.items()):
        console.print(f"  {j}: {count} chunks")


def auto_ingest_states(collection_name: str = "slot_regulations"):
    """Auto-ingest all built-in US state regulation documents."""
    states_dir = Path(__file__).parent.parent / "data" / "regulations" / "us_states"
    if not states_dir.exists():
        console.print(f"[red]Not found: {states_dir}[/red]")
        return
    state_files = list(states_dir.glob("*.md"))
    if not state_files:
        console.print(f"[yellow]No .md files in {states_dir}[/yellow]")
        return
    console.print(f"\n🇺🇸 Auto-ingesting {len(state_files)} US state docs")
    console.print(f"   States: {', '.join(f.stem.replace('_', ' ').title() for f in state_files)}")
    ingest_documents(str(states_dir), collection_name, chunk_size=800, chunk_overlap=200)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ingest regulatory docs into Qdrant")
    parser.add_argument("--source", help="Source directory or file path")
    parser.add_argument("--collection", default="slot_regulations", help="Qdrant collection name")
    parser.add_argument("--jurisdiction", default=None, help="Override jurisdiction tag")
    parser.add_argument("--chunk-size", type=int, default=800)
    parser.add_argument("--chunk-overlap", type=int, default=200)
    parser.add_argument("--auto-states", action="store_true", help="Auto-ingest all US state docs")
    args = parser.parse_args()
    if args.auto_states:
        auto_ingest_states(args.collection)
    elif args.source:
        ingest_documents(args.source, args.collection, args.jurisdiction, args.chunk_size, args.chunk_overlap)
    else:
        parser.print_help()
