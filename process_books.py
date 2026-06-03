#!/usr/bin/env python3
"""
PDF/EPUB to HTML/Markdown/Knowledge Base Processor
Downloads books from GitHub, processes them, and pushes results back to GitHub.

Usage:
    python process_books.py --repo <github_username>/<repo_name> --branch <branch> --folder <books_folder> --token <github_token>
    
Example:
    python process_books.py --repo desmentirenko/qwen --branch main --folder books/Katchanovski%20Ivan --token YOUR_TOKEN
"""

import os
import sys
import json
import hashlib
import argparse
import subprocess
import tempfile
import shutil
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional

# Try to import PDF/EPUB libraries
try:
    import fitz  # PyMuPDF
    HAS_PDF = True
except ImportError:
    HAS_PDF = False
    print("Warning: PyMuPDF not installed. Install with: pip install pymupdf")

try:
    from ebooklib import epub
    HAS_EPUB = True
except ImportError:
    HAS_EPUB = False
    print("Warning: EbookLib not installed. Install with: pip install ebooklib")

class BookProcessor:
    def __init__(self, output_dir: str = "output"):
        self.output_dir = Path(output_dir)
        self.html_dir = self.output_dir / "html"
        self.md_dir = self.output_dir / "markdown"
        self.kb_dir = self.output_dir / "knowledge_base"
        self.index_file = self.output_dir / "knowledge_base_index.json"
        
        # Create directories
        for d in [self.html_dir, self.md_dir, self.kb_dir]:
            d.mkdir(parents=True, exist_ok=True)
        
        self.all_entries = []
        if self.index_file.exists():
            try:
                with open(self.index_file, 'r', encoding='utf-8') as f:
                    self.all_entries = json.load(f)
            except:
                self.all_entries = []

    def extract_text_from_pdf(self, pdf_path: str) -> List[Dict[str, Any]]:
        """Extract text from PDF with page information"""
        pages = []
        if not HAS_PDF:
            return pages
        
        try:
            doc = fitz.open(pdf_path)
            for i, page in enumerate(doc):
                text = page.get_text()
                if text.strip():
                    pages.append({
                        'page_num': i + 1,
                        'text': text
                    })
            doc.close()
        except Exception as e:
            print(f"Error processing PDF {pdf_path}: {e}")
        
        return pages

    def extract_text_from_epub(self, epub_path: str) -> List[Dict[str, Any]]:
        """Extract text from EPUB with chapter information"""
        chapters = []
        if not HAS_EPUB:
            return chapters
        
        try:
            book = epub.read_epub(epub_path)
            chapter_num = 0
            for item in book.get_items():
                if item.get_type() == 9:  # XHTML content
                    chapter_num += 1
                    text = item.get_content().decode('utf-8', errors='ignore')
                    # Simple text extraction (remove HTML tags)
                    import re
                    clean_text = re.sub(r'<[^>]+>', '', text)
                    if clean_text.strip():
                        chapters.append({
                            'page_num': chapter_num,
                            'text': clean_text
                        })
        except Exception as e:
            print(f"Error processing EPUB {epub_path}: {e}")
        
        return chapters

    def text_to_html(self, text: str, title: str = "") -> str:
        """Convert plain text to HTML"""
        html = f"""<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <style>
        body {{ font-family: Georgia, serif; line-height: 1.6; max-width: 800px; margin: 0 auto; padding: 20px; }}
        h1, h2, h3 {{ color: #333; }}
        .page-break {{ page-break-after: always; border-top: 1px solid #ccc; margin: 20px 0; }}
        pre {{ white-space: pre-wrap; }}
    </style>
</head>
<body>
<h1>{title}</h1>
<pre>{text}</pre>
</body>
</html>"""
        return html

    def text_to_markdown(self, text: str, title: str = "", metadata: Dict = None) -> str:
        """Convert plain text to Markdown"""
        md = f"# {title}\n\n"
        if metadata:
            md += f"**Author:** {metadata.get('author', 'Unknown')}\n\n"
            md += f"**Processed:** {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n"
            md += "---\n\n"
        md += text
        return md

    def chunk_text(self, text: str, doc_name: str, page_num: int, max_chars: int = 500) -> List[Dict]:
        """Split text into searchable chunks"""
        chunks = []
        paragraphs = text.split('\n\n')
        current_chunk = ""
        chunk_id = 0
        
        for para in paragraphs:
            if len(current_chunk) + len(para) > max_chars and current_chunk:
                chunks.append({
                    'id': f"{hashlib.sha256(doc_name.encode()).hexdigest()}_page{page_num}_chunk{chunk_id}",
                    'document': doc_name,
                    'page': page_num,
                    'word_count': len(current_chunk.split()),
                    'content': current_chunk.strip()
                })
                current_chunk = para
                chunk_id += 1
            else:
                current_chunk += "\n\n" + para if current_chunk else para
        
        if current_chunk.strip():
            chunks.append({
                'id': f"{hashlib.sha256(doc_name.encode()).hexdigest()}_page{page_num}_chunk{chunk_id}",
                'document': doc_name,
                'page': page_num,
                'word_count': len(current_chunk.split()),
                'content': current_chunk.strip()
            })
        
        return chunks

    def process_file(self, file_path: str) -> Optional[Dict]:
        """Process a single PDF or EPUB file"""
        file_path = Path(file_path)
        if not file_path.exists():
            print(f"File not found: {file_path}")
            return None
        
        ext = file_path.suffix.lower()
        if ext not in ['.pdf', '.epub']:
            print(f"Unsupported format: {ext}")
            return None
        
        doc_name = file_path.stem
        print(f"\n📚 Processing: {doc_name}{ext}")
        
        # Extract text
        if ext == '.pdf':
            pages = self.extract_text_from_pdf(str(file_path))
        else:
            pages = self.extract_text_from_epub(str(file_path))
        
        if not pages:
            print(f"⚠️  No text extracted from {doc_name}")
            return None
        
        # Combine all text
        full_text = ""
        kb_entries = []
        
        for page_data in pages:
            page_num = page_data['page_num']
            text = page_data['text']
            full_text += f"\n\n--- Page {page_num} ---\n\n{text}"
            
            # Create knowledge base entries
            chunks = self.chunk_text(text, doc_name, page_num)
            kb_entries.extend(chunks)
        
        # Save HTML
        html_content = self.text_to_html(full_text, doc_name)
        html_path = self.html_dir / f"{doc_name}.html"
        with open(html_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        # Save Markdown
        md_content = self.text_to_markdown(full_text, doc_name)
        md_path = self.md_dir / f"{doc_name}.md"
        with open(md_path, 'w', encoding='utf-8') as f:
            f.write(md_content)
        
        # Save Knowledge Base
        kb_path = self.kb_dir / f"{doc_name}_kb.json"
        with open(kb_path, 'w', encoding='utf-8') as f:
            json.dump(kb_entries, f, indent=2, ensure_ascii=False)
        
        # Save Metadata
        metadata = {
            'filename': file_path.name,
            'pages': len(pages),
            'total_words': sum(len(entry['content'].split()) for entry in kb_entries),
            'kb_entries': len(kb_entries),
            'processed_at': datetime.now().isoformat(),
            'file_hash': hashlib.sha256(file_path.read_bytes()).hexdigest() if file_path.exists() else None
        }
        meta_path = self.kb_dir / f"{doc_name}_metadata.json"
        with open(meta_path, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)
        
        # Add to global index
        self.all_entries.extend(kb_entries)
        
        print(f"✅ {doc_name}: {len(pages)} pages, {metadata['total_words']} words, {len(kb_entries)} KB entries")
        
        return metadata

    def save_index(self):
        """Save the unified knowledge base index"""
        with open(self.index_file, 'w', encoding='utf-8') as f:
            json.dump(self.all_entries, f, indent=2, ensure_ascii=False)
        print(f"\n📊 Total KB entries: {len(self.all_entries)}")

def download_from_github(repo: str, branch: str, folder: str, token: str, dest_dir: str):
    """Download files from GitHub using git clone or wget"""
    repo_url = f"https://{token}@github.com/{repo}.git"
    
    print(f"📥 Downloading from {repo}/{folder}...")
    
    # Create temp directory for cloning
    temp_dir = tempfile.mkdtemp()
    try:
        # Clone repository
        subprocess.run(['git', 'clone', '--depth', '1', '--branch', branch, repo_url, temp_dir], 
                      check=True, capture_output=True)
        
        # Copy specific folder
        source_path = Path(temp_dir) / folder.replace('%20', ' ')
        dest_path = Path(dest_dir)
        
        if not source_path.exists():
            # Try URL-decoded version
            import urllib.parse
            decoded_folder = urllib.parse.unquote(folder)
            source_path = Path(temp_dir) / decoded_folder
        
        if source_path.exists():
            shutil.copytree(source_path, dest_path, dirs_exist_ok=True)
            print(f"✅ Downloaded {len(list(dest_path.glob('*')))} files")
        else:
            print(f"❌ Folder not found: {folder}")
            return False
            
    except subprocess.CalledProcessError as e:
        print(f"❌ Git error: {e}")
        return False
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
    
    return True

def push_to_github(repo: str, branch: str, token: str, message: str = "Update processed books"):
    """Push changes back to GitHub"""
    print(f"📤 Pushing to {repo}/{branch}...")
    
    try:
        # Configure git
        subprocess.run(['git', 'config', 'user.email', 'bot@github.com'], check=True, capture_output=True)
        subprocess.run(['git', 'config', 'user.name', 'Book Processor Bot'], check=True, capture_output=True)
        
        # Add all output files
        subprocess.run(['git', 'add', 'output/'], check=True, capture_output=True)
        
        # Check if there are changes
        result = subprocess.run(['git', 'status', '--porcelain'], capture_output=True, text=True)
        if not result.stdout.strip():
            print("ℹ️  No changes to commit")
            return True
        
        # Commit and push
        subprocess.run(['git', 'commit', '-m', message], check=True, capture_output=True)
        
        repo_url = f"https://{token}@github.com/{repo}.git"
        subprocess.run(['git', 'push', repo_url, branch], check=True, capture_output=True)
        
        print(f"✅ Successfully pushed to GitHub")
        return True
        
    except subprocess.CalledProcessError as e:
        print(f"❌ Push failed: {e}")
        if e.stderr:
            print(f"Error details: {e.stderr.decode()}")
        return False

def main():
    parser = argparse.ArgumentParser(description='Process books from GitHub')
    parser.add_argument('--repo', required=True, help='GitHub repo (user/repo)')
    parser.add_argument('--branch', default='main', help='Branch name')
    parser.add_argument('--folder', required=True, help='Folder path in repo')
    parser.add_argument('--token', required=True, help='GitHub personal access token')
    parser.add_argument('--output', default='output', help='Output directory')
    parser.add_argument('--no-push', action='store_true', help='Skip pushing to GitHub')
    
    args = parser.parse_args()
    
    # Check dependencies
    if not HAS_PDF and not HAS_EPUB:
        print("❌ Error: Neither PyMuPDF nor EbookLib is installed.")
        print("Install with: pip install pymupdf ebooklib")
        sys.exit(1)
    
    # Create temporary directory for downloads
    with tempfile.TemporaryDirectory() as temp_dir:
        books_dir = Path(temp_dir) / "books"
        books_dir.mkdir()
        
        # Download books
        if not download_from_github(args.repo, args.branch, args.folder, args.token, str(books_dir)):
            sys.exit(1)
        
        # Process books
        processor = BookProcessor(args.output)
        
        # Find all PDF and EPUB files
        files = list(books_dir.glob('**/*.pdf')) + list(books_dir.glob('**/*.epub'))
        
        if not files:
            print("❌ No PDF or EPUB files found")
            sys.exit(1)
        
        print(f"📚 Found {len(files)} books to process")
        
        for file_path in files:
            processor.process_file(str(file_path))
        
        processor.save_index()
        
        # Push to GitHub
        if not args.no_push:
            push_to_github(args.repo, args.branch, args.token, "Add processed books (HTML/MD/KB)")

if __name__ == '__main__':
    main()
