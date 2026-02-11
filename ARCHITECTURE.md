# Rav Itamar — Architecture

## System Diagram (Text)

```
┌─────────────────────────────────────────────────────────────────────┐
│                         BROWSER (SPA)                               │
│  ┌──────────┐  ┌──────────────────────────────────────────────────┐ │
│  │ Sidebar   │  │ Main Panel                                      │ │
│  │           │  │                                                  │ │
│  │ PDFs      │  │  Chat Messages                                  │ │
│  │ Convos    │  │  ┌─────────────────────────────┐                │ │
│  │ Search    │  │  │ User: ...                    │                │ │
│  │ Profile   │  │  │ Rav Itamar: ...              │                │ │
│  │ KB Tools  │  │  └─────────────────────────────┘                │ │
│  │           │  │                                                  │ │
│  │           │  │  [Chat Input]                  [Send]            │ │
│  └──────────┘  └──────────────────────────────────────────────────┘ │
└─────────────────────────┬───────────────────────────────────────────┘
                          │ HTTP/REST
                          ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    FastAPI Backend (Python)                          │
│                                                                     │
│  ┌──────────────┐  ┌───────────────┐  ┌──────────────────────────┐ │
│  │ API Layer    │  │ Service Layer │  │ Prompt Suite             │ │
│  │              │  │               │  │                          │ │
│  │ /pdfs/*      │  │ Ingestion     │  │ Mentor Prompt            │ │
│  │ /chat        │  │ Retriever     │  │ Verifier Prompt          │ │
│  │ /convo/*     │  │ Chat Pipeline │  │ Principle Map Prompt     │ │
│  │ /profile/*   │  │ Principle Svc │  │ KB Update Prompt         │ │
│  │ /search/*    │  │ Restudy Svc   │  │ Restudy Prompt           │ │
│  │ /restudy/*   │  │ LLM Service   │  │                          │ │
│  │ /kb/*        │  │ Storage Svc   │  │                          │ │
│  └──────────────┘  └───────────────┘  └──────────────────────────┘ │
│                          │                       │                  │
│                          ▼                       ▼                  │
│              ┌───────────────────┐    ┌───────────────────┐        │
│              │    PostgreSQL     │    │   OpenAI API      │        │
│              │    + pgvector     │    │   (embeddings +   │        │
│              │                   │    │    completions)   │        │
│              │  Tables:          │    └───────────────────┘        │
│              │  - pdfs           │                                  │
│              │  - pdf_pages      │    ┌───────────────────┐        │
│              │  - chunks         │    │  File Storage     │        │
│              │  - principles     │    │  (Local / S3)     │        │
│              │  - conversations  │    └───────────────────┘        │
│              │  - messages       │                                  │
│              │  - retrieval_logs │                                  │
│              │  - personal_prof  │                                  │
│              │  - restudy_rpts   │                                  │
│              └───────────────────┘                                  │
└─────────────────────────────────────────────────────────────────────┘
```

## Chat Pipeline Flow

```
User Message
     │
     ▼
┌──────────┐     ┌──────────────┐     ┌──────────────┐
│ RETRIEVER│────▶│   MENTOR     │────▶│  VERIFIER    │
│          │     │              │     │              │
│ 1. Query │     │ 1. Evidence  │     │ 1. Check each│
│    embed │     │    + Profile │     │    claim     │
│ 2. Fetch │     │    + History │     │ 2. Remove    │
│    princ │     │ 2. Draft     │     │    ungrounded│
│ 3. Fetch │     │    response  │     │ 3. Enforce   │
│    chunks│     │ 3. Apply     │     │    refusal   │
│ 4. Score │     │    question  │     │ 4. Return    │
│    filter│     │    gate      │     │    final     │
└──────────┘     └──────────────┘     └──────────────┘
                                            │
                                            ▼
                                      Final Response
                                      + Save to DB
                                      + Retrieval Log
```

## Data Schema

### Tables

| Table | Purpose |
|-------|---------|
| `pdfs` | PDF metadata (id, title, filename, storage_key, version_tag, total_pages, upload_date) |
| `pdf_pages` | Per-page extracted text (pdf_id, page_number, text) |
| `chunks` | Chunked text with embeddings (pdf_id, pdf_title, page_start, page_end, section_header, short_label, chunk_text, token_count, embedding) |
| `principles` | Principle Map entries (principle_name, explanation, tags, keywords, canonical_pages, embedding) |
| `conversations` | Chat sessions (title, created_at, updated_at) |
| `messages` | Chat messages (conversation_id, role, content, created_at) |
| `retrieval_logs` | Debug/citation log (message_id, retrieved_chunk_ids, scores, principle_ids) |
| `personal_profile` | Single-row user profile (identity, values, goals, constraints, preferences, recurring_patterns, decision_history, vocabulary) |
| `restudy_reports` | Periodic restudy results (report_text, top_principles, contradictions, weak_support, scenario_results) |

### Indexes

| Index | Type | Purpose |
|-------|------|---------|
| `ix_chunks_embedding` | IVFFlat (cosine) | Vector similarity search on chunks |
| `ix_principles_embedding` | IVFFlat (cosine) | Vector similarity search on principles |
| `ix_messages_content_trgm` | GIN (trigram) | Full-text fuzzy search on messages |
| `ix_pdf_pages_pdf_page` | B-tree | Fast page lookup by pdf_id + page_number |
| `ix_messages_conversation` | B-tree | Fast message retrieval by conversation |
| `ix_conversations_updated` | B-tree | Sort conversations by recency |

## API Endpoints

### PDF & KB
| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/pdfs/upload` | Upload PDF (multipart form: file, title, version_tag) |
| GET | `/api/pdfs` | List all PDFs |
| DELETE | `/api/pdfs/{pdf_id}` | Delete a PDF and its chunks |
| POST | `/api/kb/reindex` | Re-chunk and re-embed all PDFs |
| POST | `/api/principles/rebuild` | Rebuild entire Principle Map |
| GET | `/api/principles` | List all principles |

### Chat & Conversations
| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/chat` | Send message (conversation_id, message) → response |
| POST | `/api/conversations` | Create new conversation |
| GET | `/api/conversations` | List all conversations |
| GET | `/api/conversations/{id}` | Get conversation with messages |
| PATCH | `/api/conversations/{id}` | Rename conversation |
| DELETE | `/api/conversations/{id}` | Delete conversation |
| GET | `/api/search/messages?q=` | Full-text search across messages |

### Profile & Restudy
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/profile` | Get personal profile |
| POST | `/api/profile/update` | Update profile fields |
| POST | `/api/restudy/run` | Trigger restudy cycle |
| GET | `/api/restudy/reports` | List restudy reports |

## Phased Build Plan

### Phase 1: Foundation
- [x] Project scaffolding
- [x] Database models + pgvector setup
- [x] Config management
- [x] Storage service (local/S3)

### Phase 2: PDF Pipeline
- [x] PDF upload + text extraction (PyPDF2)
- [x] Page-boundary-aware chunking (700-1200 tokens, 80-150 overlap)
- [x] Embedding generation (OpenAI text-embedding-3-small)
- [x] Chunk storage with vector index

### Phase 3: Retrieval + Principles
- [x] Vector search with cosine similarity
- [x] Relevance threshold filtering
- [x] Evidence budget enforcement (<=10K tokens)
- [x] Principle Map builder (LLM-based extraction)
- [x] Incremental principle updates
- [x] Two-stage retrieval: principles first, then supporting chunks

### Phase 4: Chat Pipeline
- [x] Retriever → Mentor → Verifier flow
- [x] KB-only refusal enforcement
- [x] Citation detection and conditional inclusion
- [x] Question Gate (broad question detection)
- [x] Personal Profile integration
- [x] Conversation history context

### Phase 5: Persistence + Search
- [x] Conversation CRUD
- [x] Message persistence
- [x] Retrieval logging
- [x] Trigram-based full-text search
- [x] Profile management

### Phase 6: UI
- [x] SPA with sidebar (PDFs, conversations, search)
- [x] Chat interface with streaming-style display
- [x] PDF upload modal
- [x] Profile editor
- [x] KB management buttons
- [x] Search with navigation to source message

### Phase 7: Restudy + Polish
- [x] Restudy service (principle ranking, scenario tests, conflict detection)
- [x] KB Update Report generation
- [x] Acceptance tests
- [x] Deployment configs (Docker, Render)
