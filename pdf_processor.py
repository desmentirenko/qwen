#!/usr/bin/env python3
"""
PDF and EPUB Book Processor
Converts books to HTML, Markdown, and processes content for knowledge base storage.
Supports both .pdf and .epub formats.
"""

import os
import json
import hashlib
import re  # MEJORA 3: Importado para el splitting inteligente de oraciones
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from datetime import datetime

# PDF imports
try:
    from pypdf import PdfReader
    PDF_SUPPORT = True
except ImportError:
    PDF_SUPPORT = False
    print("Warning: pypdf not installed. PDF support disabled. Install with: pip install pypdf")

# EPUB imports
try:
    from ebooklib import epub
    from bs4 import BeautifulSoup
    EPUB_SUPPORT = True
except ImportError:
    EPUB_SUPPORT = False
    print("Warning: ebooklib or beautifulsoup4 not installed. EPUB support disabled. Install with: pip install ebooklib beautifulsoup4")

import markdownify  # MEJORA 1 y 2: Librería lista para ser usada


@dataclass
class PageContent:
    """Represents content from a single PDF page."""
    page_number: int
    text: str
    html: str
    markdown: str
    word_count: int


@dataclass
class DocumentMetadata:
    """Metadata for a processed document."""
    filename: str
    file_path: str
    file_hash: str
    total_pages: int
    total_words: int
    processed_at: str
    title: Optional[str] = None
    author: Optional[str] = None
    subject: Optional[str] = None
    keywords: Optional[str] = None


@dataclass
class ProcessedDocument:
    """Complete processed document with all formats."""
    metadata: DocumentMetadata
    full_text: str
    full_html: str
    full_markdown: str
    pages: List[PageContent]
    knowledge_base_entries: List[Dict[str, Any]]


class BookProcessor:
    """Main class for processing PDF and EPUB books."""
    
    def __init__(self, output_dir: str = "output"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Create subdirectories for different formats
        (self.output_dir / "html").mkdir(exist_ok=True)
        (self.output_dir / "markdown").mkdir(exist_ok=True)
        (self.output_dir / "knowledge_base").mkdir(exist_ok=True)
    
    def _calculate_file_hash(self, file_path: Path) -> str:
        """Calculate SHA256 hash of a file."""
        sha256_hash = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                sha256_hash.update(chunk)
        return sha256_hash.hexdigest()
    
    def _extract_metadata_pdf(self, reader: PdfReader, file_path: Path) -> DocumentMetadata:
        """Extract metadata from PDF."""
        metadata = reader.metadata or {}
        
        return DocumentMetadata(
            filename=file_path.name,
            file_path=str(file_path.absolute()),
            file_hash=self._calculate_file_hash(file_path),
            total_pages=len(reader.pages),
            total_words=0,  # Will be calculated later
            processed_at=datetime.now().isoformat(),
            title=metadata.get('/Title', ''),
            author=metadata.get('/Author', ''),
            subject=metadata.get('/Subject', ''),
            keywords=metadata.get('/Keywords', '')
        )
    
    def _extract_metadata_epub(self, book, file_path: Path) -> DocumentMetadata:
        """Extract metadata from EPUB."""
        # Get authors from metadata
        authors = []
        if hasattr(book, 'metadata') and book.metadata:
            for meta in book.metadata:
                if meta[0] == 'creator':
                    authors.append(meta[1])
        
        return DocumentMetadata(
            filename=file_path.name,
            file_path=str(file_path.absolute()),
            file_hash=self._calculate_file_hash(file_path),
            total_pages=len(list(book.get_items())),  # Chapters/items count
            total_words=0,
            processed_at=datetime.now().isoformat(),
            title=book.title or '',
            author=', '.join(authors) if authors else '',
            subject=getattr(book, 'language', ''),
            keywords=''
        )
    
    def _text_to_html(self, text: str) -> str:
        """Convert plain text to basic HTML (used mainly for PDFs)."""
        text = text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
        paragraphs = text.split('\n\n')
        html_parts = []
        for para in paragraphs:
            if para.strip():
                para = para.replace('\n', '<br/>\n')
                html_parts.append(f'<p>{para.strip()}</p>')
        return '\n'.join(html_parts)
    
    # MEJORA 1 y 2: Eliminada la función heurística antigua. 
    # Ahora usamos markdownify para una conversión precisa de HTML a Markdown.
    def _generate_markdown(self, html_content: str) -> str:
        """Convert HTML to high-quality Markdown using markdownify."""
        # heading_style="ATX" asegura que use # en lugar de === para los títulos
        return markdownify.markdownify(html_content, heading_style="ATX").strip()

    # MEJORA 3: Chunking inteligente que respeta los límites de las oraciones
    def _create_knowledge_base_entry(self, page: PageContent, doc_metadata: DocumentMetadata) -> List[Dict[str, Any]]:
        """Create knowledge base entries with sentence-aware chunking."""
        text = page.text
        chunks = []
        
        # 1. Dividir primero por párrafos para mantener estructura
        paragraphs = [p.strip() for p in text.split('\n\n') if p.strip()]
        
        # 2. Regex para dividir por oraciones (detecta . ! ? seguidos de espacio)
        sentence_splitter = re.compile(r'(?<=[.!?])\s+')
        
        current_chunk = []
        current_length = 0
        MAX_CHUNK_SIZE = 500  # Límite de caracteres por chunk
        
        for para in paragraphs:
            # Dividir el párrafo en oraciones
            sentences = sentence_splitter.split(para)
            
            for sentence in sentences:
                sentence = sentence.strip()
                if not sentence:
                    continue
                
                sentence_length = len(sentence)
                
                # Caso borde: una sola oración es más larga que el límite (ej. URL larga)
                if sentence_length > MAX_CHUNK_SIZE:
                    if current_chunk:
                        chunks.append(' '.join(current_chunk))
                        current_chunk = []
                        current_length = 0
                    # Forzar división de la oración gigante
                    for i in range(0, len(sentence), MAX_CHUNK_SIZE):
                        chunks.append(sentence[i:i+MAX_CHUNK_SIZE])
                    continue
                
                # Si añadir la oración supera el límite, guardamos el chunk actual y empezamos uno nuevo
                if current_length + sentence_length + 1 > MAX_CHUNK_SIZE: # +1 por el espacio
                    chunks.append(' '.join(current_chunk))
                    current_chunk = [sentence]
                    current_length = sentence_length
                else:
                    current_chunk.append(sentence)
                    current_length += sentence_length + 1
                    
        # Guardar el último chunk si queda algo
        if current_chunk:
            chunks.append(' '.join(current_chunk))
        
        entries = []
        for i, chunk in enumerate(chunks):
            if len(chunk.strip()) > 50:  # Tamaño mínimo para ser útil
                entry = {
                    'id': f"{doc_metadata.file_hash}_page{page.page_number}_chunk{i}",
                    'document': doc_metadata.filename,
                    'page': page.page_number,
                    'chunk_index': i,
                    'content': chunk,
                    'word_count': len(chunk.split()),
                    'metadata': {
                        'title': doc_metadata.title,
                        'author': doc_metadata.author,
                        'source_path': doc_metadata.file_path,
                        'processed_at': doc_metadata.processed_at
                    }
                }
                entries.append(entry)
        
        return entries
    
    def process_pdf(self, pdf_path: str) -> ProcessedDocument:
        """Process a single PDF file."""
        if not PDF_SUPPORT:
            raise RuntimeError("PDF support is not available. Install pypdf.")
        
        pdf_path = Path(pdf_path)
        
        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF file not found: {pdf_path}")
        
        if not pdf_path.suffix.lower() == '.pdf':
            raise ValueError(f"File is not a PDF: {pdf_path}")
        
        print(f"Processing PDF: {pdf_path.name}")
        
        # Read PDF
        reader = PdfReader(str(pdf_path))
        
        # Extract metadata
        doc_metadata = self._extract_metadata_pdf(reader, pdf_path)
        
        # Process each page
        pages = []
        full_text_parts = []
        full_html_parts = []
        full_markdown_parts = []
        knowledge_base_entries = []
        
        for i, page in enumerate(reader.pages):
            page_num = i + 1
            
            # Extract text
            text = page.extract_text() or ""
            
            # Generar HTML básico desde el texto plano
            html = self._text_to_html(text)
            
            # MEJORA: Usar markdownify sobre el HTML generado para un Markdown mucho mejor
            markdown = self._generate_markdown(html)
            
            # Calculate word count
            word_count = len(text.split())
            
            # Create page content
            page_content = PageContent(
                page_number=page_num,
                text=text,
                html=html,
                markdown=markdown,
                word_count=word_count
            )
            pages.append(page_content)
            
            # Accumulate full document content
            full_text_parts.append(text)
            full_html_parts.append(html)
            full_markdown_parts.append(markdown)
            
            # Create knowledge base entries
            kb_entries = self._create_knowledge_base_entry(page_content, doc_metadata)
            knowledge_base_entries.extend(kb_entries)
        
        # Update total word count
        doc_metadata.total_words = sum(p.word_count for p in pages)
        
        # Create full document content with structure
        full_text = '\n\n---\n\n'.join(full_text_parts)
        
        full_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{doc_metadata.title or pdf_path.stem}</title>
    <style>
        body {{ font-family: Arial, sans-serif; max-width: 800px; margin: 0 auto; padding: 20px; }}
        .page-break {{ page-break-after: always; border-top: 1px solid #ccc; margin: 20px 0; }}
    </style>
</head>
<body>
<h1>{doc_metadata.title or pdf_path.stem}</h1>
{''.join(full_html_parts)}
</body>
</html>"""
        
        full_markdown = f"""# {doc_metadata.title or pdf_path.stem}

**Author:** {doc_metadata.author or 'Unknown'}  
**Processed:** {doc_metadata.processed_at}

---

""" + '\n\n---\n\n'.join(full_markdown_parts)
        
        # Create result
        result = ProcessedDocument(
            metadata=doc_metadata,
            full_text=full_text,
            full_html=full_html,
            full_markdown=full_markdown,
            pages=pages,
            knowledge_base_entries=knowledge_base_entries
        )
        
        print(f"  - Pages: {doc_metadata.total_pages}")
        print(f"  - Total words: {doc_metadata.total_words}")
        print(f"  - Knowledge base entries: {len(knowledge_base_entries)}")
        
        return result
    
    def process_epub(self, epub_path: str) -> ProcessedDocument:
        """Process a single EPUB file."""
        if not EPUB_SUPPORT:
            raise RuntimeError("EPUB support is not available. Install ebooklib and beautifulsoup4.")
        
        epub_path = Path(epub_path)
        
        if not epub_path.exists():
            raise FileNotFoundError(f"EPUB file not found: {epub_path}")
        
        if not epub_path.suffix.lower() == '.epub':
            raise ValueError(f"File is not an EPUB: {epub_path}")
        
        print(f"Processing EPUB: {epub_path.name}")
        
        # Read EPUB
        book = epub.read_epub(str(epub_path))
        
        # Extract metadata
        doc_metadata = self._extract_metadata_epub(book, epub_path)
        
        # Process each chapter/item
        chapters = []
        full_text_parts = []
        full_html_parts = []
        full_markdown_parts = []
        knowledge_base_entries = []
        
        chapter_num = 0
        for item in book.get_items():
            # Check if item is an HTML content item (EpubHtml with xhtml media type)
            if hasattr(item, 'media_type') and 'xhtml' in item.media_type:
                chapter_num += 1
                
                # Get HTML content
                html_content = item.get_content().decode('utf-8', errors='ignore')
                
                soup = BeautifulSoup(html_content, 'lxml')
                
                # MEJORA: Eliminar scripts y estilos para evitar basura en el texto/markdown
                for script_or_style in soup(["script", "style"]):
                    script_or_style.extract()
                
                clean_html = str(soup)
                text = soup.get_text(separator='\n', strip=True)
                
                # MEJORA: Usar markdownify directamente sobre el HTML limpio del EPUB
                markdown = self._generate_markdown(clean_html)
                
                # Calculate word count
                word_count = len(text.split())
                
                # Create chapter content (treating chapters like pages)
                chapter_content = PageContent(
                    page_number=chapter_num,
                    text=text,
                    html=clean_html,
                    markdown=markdown,
                    word_count=word_count
                )
                chapters.append(chapter_content)
                
                # Accumulate full document content
                full_text_parts.append(text)
                full_html_parts.append(clean_html)
                full_markdown_parts.append(markdown)
                
                # Create knowledge base entries
                kb_entries = self._create_knowledge_base_entry(chapter_content, doc_metadata)
                knowledge_base_entries.extend(kb_entries)
        
        # Update total word count and page count
        doc_metadata.total_words = sum(c.word_count for c in chapters)
        doc_metadata.total_pages = len(chapters)
        
        # Create full document content with structure
        full_text = '\n\n---\n\n'.join(full_text_parts)
        
        full_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{doc_metadata.title or epub_path.stem}</title>
    <style>
        body {{ font-family: Arial, sans-serif; max-width: 800px; margin: 0 auto; padding: 20px; }}
        .chapter-break {{ page-break-after: always; border-top: 1px solid #ccc; margin: 20px 0; }}
    </style>
</head>
<body>
<h1>{doc_metadata.title or epub_path.stem}</h1>
<p><strong>Author:</strong> {doc_metadata.author or 'Unknown'}</p>
{''.join(full_html_parts)}
</body>
</html>"""
        
        full_markdown = f"""# {doc_metadata.title or epub_path.stem}

**Author:** {doc_metadata.author or 'Unknown'}  
**Processed:** {doc_metadata.processed_at}

---

""" + '\n\n---\n\n'.join(full_markdown_parts)
        
        # Create result
        result = ProcessedDocument(
            metadata=doc_metadata,
            full_text=full_text,
            full_html=full_html,
            full_markdown=full_markdown,
            pages=chapters,  # Reusing pages field for chapters
            knowledge_base_entries=knowledge_base_entries
        )
        
        print(f"  - Chapters: {doc_metadata.total_pages}")
        print(f"  - Total words: {doc_metadata.total_words}")
        print(f"  - Knowledge base entries: {len(knowledge_base_entries)}")
        
        return result
    
    def save_document(self, doc: ProcessedDocument, base_name: Optional[str] = None):
        """Save processed document in all formats."""
        if base_name is None:
            base_name = Path(doc.metadata.filename).stem
        
        # Save HTML
        html_path = self.output_dir / "html" / f"{base_name}.html"
        with open(html_path, 'w', encoding='utf-8') as f:
            f.write(doc.full_html)
        print(f"  Saved HTML: {html_path}")
        
        # Save Markdown
        md_path = self.output_dir / "markdown" / f"{base_name}.md"
        with open(md_path, 'w', encoding='utf-8') as f:
            f.write(doc.full_markdown)
        print(f"  Saved Markdown: {md_path}")
        
        # Save knowledge base entries
        kb_path = self.output_dir / "knowledge_base" / f"{base_name}_kb.json"
        with open(kb_path, 'w', encoding='utf-8') as f:
            json.dump(doc.knowledge_base_entries, f, indent=2, ensure_ascii=False)
        print(f"  Saved Knowledge Base: {kb_path}")
        
        # Save metadata
        meta_path = self.output_dir / "knowledge_base" / f"{base_name}_metadata.json"
        with open(meta_path, 'w', encoding='utf-8') as f:
            json.dump(asdict(doc.metadata), f, indent=2, ensure_ascii=False)
        print(f"  Saved Metadata: {meta_path}")
    
    def process_directory(self, input_dir: str, pattern: str = "*.*"):
        """Process all PDF and EPUB files in a directory."""
        input_path = Path(input_dir)
        
        if not input_path.exists():
            raise FileNotFoundError(f"Directory not found: {input_dir}")
        
        # Find both PDF and EPUB files
        pdf_files = list(input_path.glob("*.pdf"))
        epub_files = list(input_path.glob("*.epub"))
        all_files = pdf_files + epub_files
        
        if not all_files:
            print(f"No PDF or EPUB files found in {input_dir}")
            return []
        
        print(f"Found {len(all_files)} book file(s) ({len(pdf_files)} PDF, {len(epub_files)} EPUB)")
        results = []
        
        for book_file in all_files:
            try:
                if book_file.suffix.lower() == '.pdf':
                    doc = self.process_pdf(book_file)
                elif book_file.suffix.lower() == '.epub':
                    doc = self.process_epub(book_file)
                else:
                    continue
                self.save_document(doc)
                results.append(doc)
            except Exception as e:
                print(f"Error processing {book_file.name}: {e}")
        
        return results
    
    def create_knowledge_base_index(self, output_file: str = "knowledge_base_index.json"):
        """Create an index of all knowledge base entries."""
        kb_dir = self.output_dir / "knowledge_base"
        all_entries = []
        
        for kb_file in kb_dir.glob("*_kb.json"):
            with open(kb_file, 'r', encoding='utf-8') as f:
                entries = json.load(f)
                all_entries.extend(entries)
        
        index = {
            'total_entries': len(all_entries),
            'total_documents': len(set(e['document'] for e in all_entries)),
            'created_at': datetime.now().isoformat(),
            'entries': all_entries
        }
        
        index_path = self.output_dir / output_file
        with open(index_path, 'w', encoding='utf-8') as f:
            json.dump(index, f, indent=2, ensure_ascii=False)
        
        print(f"Knowledge base index created: {index_path}")
        print(f"  Total entries: {index['total_entries']}")
        print(f"  Total documents: {index['total_documents']}")
        
        return index


def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Process PDF and EPUB books to HTML, Markdown, and Knowledge Base')
    parser.add_argument('input', nargs='?', default='.', help='Input book file (PDF/EPUB) or directory')
    parser.add_argument('-o', '--output', default='output', help='Output directory')
    parser.add_argument('--index', action='store_true', help='Create knowledge base index')
    
    args = parser.parse_args()
    
    processor = BookProcessor(output_dir=args.output)
    input_path = Path(args.input)
    
    if input_path.is_file():
        if input_path.suffix.lower() == '.pdf':
            doc = processor.process_pdf(input_path)
        elif input_path.suffix.lower() == '.epub':
            doc = processor.process_epub(input_path)
        else:
            print(f"Unsupported file format: {input_path.suffix}")
            return 1
        processor.save_document(doc)
    elif input_path.is_dir():
        docs = processor.process_directory(input_path)
        if args.index and docs:
            processor.create_knowledge_base_index()
    else:
        print(f"Input path not found: {input_path}")
        return 1
    
    return 0


if __name__ == '__main__':
    exit(main())
