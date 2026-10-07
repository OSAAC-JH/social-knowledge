# Social Knowledge Repository

## Purpose

Capture useful content from Instagram, Threads, LinkedIn, blogs, newsletters, YouTube, websites, images, PDFs, and user-provided text; convert it into structured Markdown notes; and accumulate a reusable personal knowledge base.

## Storage model

- **GitHub**: Markdown, metadata, taxonomy, templates, scripts
- **Google Drive**: images, screenshots, PDFs, and other binary assets
- **Obsidian**: local interface for browsing and editing
- **ChatGPT Work**: capture, curator, and librarian workflow

## Design principles

- Folder = physical or operational structure
- Metadata = semantic classification
- Links = relationships between knowledge units
- Preserve Raw Content separately from AI-generated interpretation
- Reuse canonical taxonomy before creating new topics
- Keep the system app-agnostic and Markdown-first

## Knowledge units

### Source Note
Represents one source item and preserves its source, summary, claims, concepts, and raw content.

### Insight Note
Synthesizes patterns across multiple Source Notes. Insight Notes are introduced only after enough source material accumulates.

## Initial workflow

Input → Capture → Raw Content → Curator → Librarian → Markdown Source Note → GitHub

Binary assets are stored separately in Google Drive and referenced from notes.
