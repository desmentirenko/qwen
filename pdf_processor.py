#!/usr/bin/env python3
"""
PDF Book Processor
Converts PDF books to HTML and Markdown formats, and processes content for knowledge base storage.
"""

import os
import json
import hashlib
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from datetime import datetime

from pypdf import PdfReader
from bs4 import BeautifulSoup
import markdownify


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


class PDFProcessor:
    """Main class for processing PDF books."""
    
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
    
    def _extract_metadata(self, reader: PdfReader, file_path: Path) -> DocumentMetadata:
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
    
    def _text_to_html(self, text: str) -> str:
        """Convert plain text to basic HTML."""
        # Escape HTML special characters
        text = text.replace('&', '&amp;')
        text = text.replace('<', '&lt;')
        text = text.replace('>', '&gt;')
        
        # Convert paragraphs
        paragraphs = text.split('\n\n')
        html_parts = []
        for para in paragraphs:
            if para.strip():
                # Convert line breaks within paragraphs
                para = para.replace('\n', '<br/>\n')
                html_parts.append(f'<p>{para.strip()}</p>')
        
        return '\n'.join(html_parts)
    
    def _text_to_markdown(self, text: str) -> str:
        """Convert plain text to Markdown format."""
        lines = text.split('\n')
        markdown_lines = []
        
        for line in lines:
            stripped = line.strip()
            
            # Detect headers (simple heuristic)
            if len(stripped) < 100 and stripped.endswith(':'):
                markdown_lines.append(f'## {stripped[:-1]}')
            # Detect lists
            elif stripped.startswith('- ') or stripped.startswith('* '):
                markdown_lines.append(stripped)
            elif stripped and len(stripped) > 0:
                markdown_lines.append(stripped)
            else:
                markdown_lines.append('')
        
        return '\n'.join(markdown_lines)
    
    def _create_knowledge_base_entry(self, page: PageContent, doc_metadata: DocumentMetadata) -> Dict[str, Any]:
        """Create a knowledge base entry from a page."""
        # Extract potential chunks for knowledge base
        text = page.text
        chunks = []
        
        # Split by paragraphs
        paragraphs = [p.strip() for p in text.split('\n\n') if p.strip()]
        
        current_chunk = []
        current_length = 0
        
        for para in paragraphs:
            para_length = len(para)
            if current_length + para_length > 500:  # Chunk size limit
                if current_chunk:
                    chunks.append(' '.join(current_chunk))
                current_chunk = [para]
                current_length = para_length
            else:
                current_chunk.append(para)
                current_length += para_length
        
        if current_chunk:
            chunks.append(' '.join(current_chunk))
        
        entries = []
        for i, chunk in enumerate(chunks):
            if len(chunk.strip()) > 50:  # Minimum chunk size
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
        pdf_path = Path(pdf_path)
        
        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF file not found: {pdf_path}")
        
        if not pdf_path.suffix.lower() == '.pdf':
            raise ValueError(f"File is not a PDF: {pdf_path}")
        
        print(f"Processing: {pdf_path.name}")
        
        # Read PDF
        reader = PdfReader(str(pdf_path))
        
        # Extract metadata
        doc_metadata = self._extract_metadata(reader, pdf_path)
        
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
            
            # Convert to HTML
            html = self._text_to_html(text)
            
            # Convert to Markdown
            markdown = self._text_to_markdown(text)
            
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
    
    def process_directory(self, input_dir: str, pattern: str = "*.pdf"):
        """Process all PDF files in a directory."""
        input_path = Path(input_dir)
        
        if not input_path.exists():
            raise FileNotFoundError(f"Directory not found: {input_dir}")
        
        pdf_files = list(input_path.glob(pattern))
        
        if not pdf_files:
            print(f"No PDF files found in {input_dir}")
            return []
        
        print(f"Found {len(pdf_files)} PDF file(s)")
        results = []
        
        for pdf_file in pdf_files:
            try:
                doc = self.process_pdf(pdf_file)
                self.save_document(doc)
                results.append(doc)
            except Exception as e:
                print(f"Error processing {pdf_file.name}: {e}")
        
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
    
    parser = argparse.ArgumentParser(description='Process PDF books to HTML, Markdown, and Knowledge Base')
    parser.add_argument('input', nargs='?', default='.', help='Input PDF file or directory')
    parser.add_argument('-o', '--output', default='output', help='Output directory')
    parser.add_argument('--index', action='store_true', help='Create knowledge base index')
    
    args = parser.parse_args()
    
    processor = PDFProcessor(output_dir=args.output)
    input_path = Path(args.input)
    
    if input_path.is_file():
        doc = processor.process_pdf(input_path)
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
