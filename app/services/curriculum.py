import re
import unicodedata
from datetime import datetime, timezone
from typing import Any

from app.domain.models import ConceptNode, CourseModule


def slugify(text: str) -> str:
    """Generate a clean URL-safe slug from text."""
    # Remove subsection numbers if present (e.g., '1.2 Single Points...' -> 'Single Points...')
    cleaned = re.sub(r"^\d+(\.\d+)*\s*", "", text)
    # If title starts with Case:, Example:, Note:, etc., take the rest or combine
    case_match = re.match(r"^(case|example|note|tip|scenario)\s*:\s*(.+)$", cleaned, re.IGNORECASE)
    if case_match:
        cleaned = f"{case_match.group(1)}-{case_match.group(2)}"
    elif ":" in cleaned:
        # If prefix is substantial, keep main part before subtitle
        prefix = cleaned.split(":", 1)[0].strip()
        if len(prefix.split()) >= 2:
            cleaned = prefix
        else:
            cleaned = cleaned.replace(":", "-")
    cleaned = unicodedata.normalize("NFKD", cleaned).encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^\w\s-]", "", cleaned).strip().lower()
    slug = re.sub(r"[-\s]+", "-", slug)
    return slug or "concept"


class CurriculumIngestionService:
    """Parses, extracts, and commits course curriculum and lecture materials into Firestore."""

    @classmethod
    def parse_curriculum_text(
        cls,
        text: str,
        fallback_module: str = "M1L1",
    ) -> tuple[CourseModule, list[ConceptNode]]:
        """Parses structured curriculum text into a CourseModule and list of ConceptNodes."""
        lines = [line.strip() for line in text.splitlines()]
        
        module_id = fallback_module
        module_title = "Untitled Module"
        keywords: list[str] = []
        
        # 1. Parse Header
        for i, line in enumerate(lines[:15]):
            if not line:
                continue
            # Check for MODULE X | LESSON Y
            mod_match = re.search(r"MODULE\s+(\d+)\s*\|\s*LESSON\s+(\d+)", line, re.IGNORECASE)
            if mod_match:
                module_id = f"M{mod_match.group(1)}L{mod_match.group(2)}"
                # Next non-empty line is typically the module title
                for next_line in lines[i + 1 : i + 5]:
                    if next_line and not any(next_line.startswith(p) for p in ["Reading Time", "Prior Knowledge", "Keywords"]):
                        module_title = next_line
                        break
            elif line.startswith("Keywords"):
                raw_kw = re.sub(r"^Keywords\s*[:\t]?", "", line)
                keywords = [k.strip().lower() for k in raw_kw.split(",") if k.strip()]

        # 2. Parse Subsections (e.g. "1.1 The Invisible Infrastructure", "1.2 Single Points of Failure")
        # Split text into sections using regex matching numbered sections like "1.1 " or "2.3 "
        section_pattern = re.compile(r"^(\d+\.\d+)\s+(.+)$")
        
        sections: list[dict[str, Any]] = []
        current_section: dict[str, Any] | None = None
        
        for line in lines:
            match = section_pattern.match(line)
            if match:
                if current_section:
                    current_section["body"] = "\n".join(current_section["lines"]).strip()
                    sections.append(current_section)
                
                sec_num = match.group(1)
                sec_title = match.group(2).strip()
                current_section = {
                    "number": sec_num,
                    "title": sec_title,
                    "lines": [],
                }
            elif current_section is not None:
                current_section["lines"].append(line)
                
        if current_section:
            current_section["body"] = "\n".join(current_section["lines"]).strip()
            sections.append(current_section)

        # 3. If no numbered subsections were found (e.g., plain markdown headers # or ##)
        if not sections:
            header_pattern = re.compile(r"^(#{1,3})\s+(.+)$")
            for line in lines:
                match = header_pattern.match(line)
                if match:
                    hashes = match.group(1)
                    sec_title = match.group(2).strip()
                    if hashes == "#" and (module_title == "Untitled Module" or not module_title):
                        module_title = sec_title
                        continue
                    if current_section:
                        current_section["body"] = "\n".join(current_section["lines"]).strip()
                        sections.append(current_section)
                    current_section = {
                        "number": f"1.{len(sections) + 1}",
                        "title": sec_title,
                        "lines": [],
                    }
                elif current_section is not None:
                    current_section["lines"].append(line)
            if current_section:
                current_section["body"] = "\n".join(current_section["lines"]).strip()
                sections.append(current_section)

        # 4. Convert sections to ConceptNode instances
        concepts: list[ConceptNode] = []
        now = datetime.now(timezone.utc)
        
        for idx, sec in enumerate(sections, start=1):
            title = sec["title"]
            slug = slugify(title)
            body = sec["body"]
            
            # Extract first non-empty paragraph as summary
            paragraphs = [p.strip() for p in body.split("\n\n") if p.strip()]
            summary = paragraphs[0] if paragraphs else f"Core principles of {title}"
            # Limit summary to ~250 chars for UI badges/tooltips
            if len(summary) > 280:
                summary = summary[:277] + "..."
                
            # Filter relevant keywords
            concept_keywords = [
                kw for kw in keywords 
                if kw in title.lower() or kw in body.lower()
            ]
            if not concept_keywords:
                concept_keywords = [slug.replace("-", " ")]

            concept = ConceptNode(
                slug=slug,
                title=title,
                module=module_id,
                module_title=module_title,
                synthesis=body or summary,
                summary=summary,
                citations=[],
                keywords=concept_keywords,
                prerequisites=[],
                order=idx,
                created_at=now,
            )
            concepts.append(concept)

        course_module = CourseModule(
            module_id=module_id,
            title=module_title,
            summary=f"Contains {len(concepts)} key concepts.",
            concepts=concepts,
        )

        return course_module, concepts

    @classmethod
    async def commit_curriculum(
        cls,
        uid: str,
        module: CourseModule,
        concepts: list[ConceptNode],
        concept_store: Any,
        raw_source_text: str | None = None,
    ) -> dict[str, Any]:
        """Saves the module, concepts, and source audit log into Firestore."""
        await concept_store.save_module(uid, module)
        
        for concept in concepts:
            await concept_store.save_concept(uid, concept)
            
        if raw_source_text:
            source_id = f"source-{module.module_id}-{int(datetime.now(timezone.utc).timestamp())}"
            await concept_store.save_source(
                uid,
                source_id,
                {
                    "source_id": source_id,
                    "module_id": module.module_id,
                    "title": module.title,
                    "length": len(raw_source_text),
                    "created_at": datetime.now(timezone.utc).isoformat(),
                },
            )
            
        return {
            "status": "committed",
            "module_id": module.module_id,
            "module_title": module.title,
            "concepts_count": len(concepts),
            "concept_slugs": [c.slug for c in concepts],
        }
