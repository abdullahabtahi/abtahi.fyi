import re
import hashlib
from app.domain.models import MarkdownChunk
from bs4 import BeautifulSoup
from markdownify import markdownify as md

def html_to_markdown(html_content: str) -> str:
    """
    Cleans HTML content and converts it to Markdown.
    Strips out script and style tags to prevent garbage text.
    """
    soup = BeautifulSoup(html_content, "html.parser")
    
    # Remove script and style elements
    for script in soup(["script", "style"]):
        script.extract()
        
    cleaned_html = str(soup)
    markdown_text = md(cleaned_html, heading_style="ATX").strip()
    return markdown_text

def extract_headings(text: str):
    """Simple regex to extract markdown headings."""
    headings = []
    lines = text.split('\n')
    for line in lines:
        match = re.match(r'^(#{1,6})\s+(.*)', line)
        if match:
            level = len(match.group(1))
            title = match.group(2).strip()
            headings.append((level, title))
    return headings

def chunk_markdown_ast(markdown_content: str, max_chars: int = 2000):
    """
    Chunks markdown while preserving AST heading hierarchies as breadcrumbs.
    Targeting ~350-500 tokens (approx 1500-2000 chars) per chunk.
    """
    lines = markdown_content.split('\n')
    
    current_breadcrumb = []
    current_chunk_lines = []
    current_chars = 0
    
    def yield_chunk():
        if not current_chunk_lines:
            return None
            
        text = "\n".join(current_chunk_lines).strip()
        if not text:
            return None
            
        breadcrumb_str = f"[{' > '.join(current_breadcrumb)}]" if current_breadcrumb else "[]"
        chunk_id = hashlib.sha256((breadcrumb_str + text).encode("utf-8")).hexdigest()
        
        return MarkdownChunk(
            chunk_id=chunk_id,
            breadcrumb=breadcrumb_str,
            text=text
        )

    for line in lines:
        match = re.match(r'^(#{1,6})\s+(.*)', line)
        if match:
            # It's a heading. Yield the previous chunk if any.
            chunk = yield_chunk()
            if chunk:
                yield chunk
            
            # Reset current chunk text
            current_chunk_lines = []
            current_chars = 0
            
            level = len(match.group(1))
            title = match.group(2).strip()
            
            # Update breadcrumb stack
            if len(current_breadcrumb) >= level:
                current_breadcrumb = current_breadcrumb[:level-1]
            current_breadcrumb.append(title)
            
        else:
            # It's normal text
            import textwrap
            wrapped_lines = textwrap.wrap(line, width=max_chars) if len(line) > max_chars else [line]
            
            for wline in wrapped_lines:
                line_len = len(wline) + 1 # +1 for newline
                if current_chars + line_len > max_chars and current_chunk_lines:
                    # Chunk is too big, yield it and start a new one with same breadcrumb
                    chunk = yield_chunk()
                    if chunk:
                        yield chunk
                    current_chunk_lines = []
                    current_chars = 0
                    
                if wline.strip():
                    current_chunk_lines.append(wline)
                    current_chars += line_len
                
    # Yield remainder
    chunk = yield_chunk()
    if chunk:
        yield chunk
