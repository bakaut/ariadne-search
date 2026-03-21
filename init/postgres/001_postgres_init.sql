BEGIN;

CREATE SCHEMA IF NOT EXISTS kb;

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE OR REPLACE FUNCTION kb.touch_updated_at()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$;

CREATE TABLE IF NOT EXISTS kb.projects (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name text NOT NULL UNIQUE,
  kind text,
  description text,
  metadata_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS kb.repos (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id uuid REFERENCES kb.projects(id) ON DELETE SET NULL,
  name text NOT NULL,
  root_path text NOT NULL,
  default_branch text,
  vcs_type text,
  metadata_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (root_path)
);

CREATE TABLE IF NOT EXISTS kb.documents (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  source_path text NOT NULL UNIQUE,
  source_type text NOT NULL,
  title text,
  checksum text,
  mime_type text,
  language text,
  project_id uuid REFERENCES kb.projects(id) ON DELETE SET NULL,
  repo_id uuid REFERENCES kb.repos(id) ON DELETE SET NULL,
  created_at timestamptz,
  updated_at timestamptz NOT NULL DEFAULT now(),
  indexed_at timestamptz,
  status text NOT NULL DEFAULT 'new',
  metadata_json jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS kb.pages (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  document_id uuid NOT NULL REFERENCES kb.documents(id) ON DELETE CASCADE,
  page_number integer NOT NULL,
  page_label text,
  page_text text,
  render_path text,
  width integer,
  height integer,
  page_embedding_model text,
  page_embedding vector(768),
  metadata_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (document_id, page_number)
);

CREATE TABLE IF NOT EXISTS kb.chunks (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  document_id uuid NOT NULL REFERENCES kb.documents(id) ON DELETE CASCADE,
  page_id uuid REFERENCES kb.pages(id) ON DELETE CASCADE,
  chunk_index integer NOT NULL,
  chunk_kind text NOT NULL DEFAULT 'text',
  heading text,
  content text NOT NULL,
  token_count integer,
  char_count integer,
  start_offset integer,
  end_offset integer,
  content_hash text NOT NULL,
  embedding_model text,
  embedding vector(768),
  tsv tsvector GENERATED ALWAYS AS (
    to_tsvector('simple', coalesce(heading, '') || ' ' || coalesce(content, ''))
  ) STORED,
  metadata_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (document_id, chunk_index),
  UNIQUE (document_id, content_hash)
);

CREATE TABLE IF NOT EXISTS kb.assets (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  document_id uuid NOT NULL REFERENCES kb.documents(id) ON DELETE CASCADE,
  page_id uuid REFERENCES kb.pages(id) ON DELETE CASCADE,
  asset_type text NOT NULL,
  asset_role text,
  storage_path text NOT NULL,
  mime_type text,
  width integer,
  height integer,
  caption_text text,
  ocr_text text,
  metadata_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (storage_path)
);

CREATE TABLE IF NOT EXISTS kb.ocr_blocks (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  document_id uuid NOT NULL REFERENCES kb.documents(id) ON DELETE CASCADE,
  page_id uuid REFERENCES kb.pages(id) ON DELETE CASCADE,
  asset_id uuid REFERENCES kb.assets(id) ON DELETE CASCADE,
  block_index integer NOT NULL,
  text text NOT NULL,
  confidence numeric(5,4),
  bbox_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  tsv tsvector GENERATED ALWAYS AS (
    to_tsvector('simple', coalesce(text, ''))
  ) STORED,
  metadata_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS kb.image_embeddings (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  document_id uuid NOT NULL REFERENCES kb.documents(id) ON DELETE CASCADE,
  page_id uuid REFERENCES kb.pages(id) ON DELETE CASCADE,
  asset_id uuid REFERENCES kb.assets(id) ON DELETE CASCADE,
  embedding_kind text NOT NULL,
  embedding_model text NOT NULL,
  embedding vector(768) NOT NULL,
  metadata_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS kb.files (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  repo_id uuid REFERENCES kb.repos(id) ON DELETE CASCADE,
  document_id uuid NOT NULL REFERENCES kb.documents(id) ON DELETE CASCADE,
  relative_path text NOT NULL,
  file_type text,
  extension text,
  language text,
  checksum text,
  metadata_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (document_id),
  UNIQUE (repo_id, relative_path)
);

CREATE TABLE IF NOT EXISTS kb.entities (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  canonical_name text NOT NULL,
  entity_type text NOT NULL,
  normalized_name text NOT NULL,
  confidence numeric(5,4),
  description text,
  metadata_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (entity_type, normalized_name)
);

CREATE TABLE IF NOT EXISTS kb.chunk_entities (
  chunk_id uuid NOT NULL REFERENCES kb.chunks(id) ON DELETE CASCADE,
  entity_id uuid NOT NULL REFERENCES kb.entities(id) ON DELETE CASCADE,
  mention_text text,
  mention_count integer NOT NULL DEFAULT 1,
  start_offset integer,
  end_offset integer,
  confidence numeric(5,4),
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (chunk_id, entity_id)
);

CREATE TABLE IF NOT EXISTS kb.asset_entities (
  asset_id uuid NOT NULL REFERENCES kb.assets(id) ON DELETE CASCADE,
  entity_id uuid NOT NULL REFERENCES kb.entities(id) ON DELETE CASCADE,
  mention_text text,
  confidence numeric(5,4),
  source text,
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (asset_id, entity_id)
);

CREATE TABLE IF NOT EXISTS kb.relations (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  from_entity_id uuid NOT NULL REFERENCES kb.entities(id) ON DELETE CASCADE,
  to_entity_id uuid NOT NULL REFERENCES kb.entities(id) ON DELETE CASCADE,
  relation_type text NOT NULL,
  confidence numeric(5,4),
  source text,
  metadata_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (from_entity_id, to_entity_id, relation_type)
);

CREATE TABLE IF NOT EXISTS kb.symbols (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  file_id uuid NOT NULL REFERENCES kb.files(id) ON DELETE CASCADE,
  repo_id uuid REFERENCES kb.repos(id) ON DELETE CASCADE,
  symbol_name text NOT NULL,
  symbol_kind text NOT NULL,
  fq_name text,
  signature text,
  language text,
  start_line integer,
  end_line integer,
  metadata_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (file_id, symbol_kind, symbol_name, start_line)
);

CREATE TABLE IF NOT EXISTS kb.symbol_links (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  from_symbol_id uuid NOT NULL REFERENCES kb.symbols(id) ON DELETE CASCADE,
  to_symbol_id uuid NOT NULL REFERENCES kb.symbols(id) ON DELETE CASCADE,
  link_type text NOT NULL,
  confidence numeric(5,4),
  metadata_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (from_symbol_id, to_symbol_id, link_type)
);

CREATE TABLE IF NOT EXISTS kb.document_links (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  from_document_id uuid NOT NULL REFERENCES kb.documents(id) ON DELETE CASCADE,
  to_document_id uuid NOT NULL REFERENCES kb.documents(id) ON DELETE CASCADE,
  link_type text NOT NULL,
  raw_target text,
  metadata_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (from_document_id, to_document_id, link_type)
);

CREATE TABLE IF NOT EXISTS kb.index_jobs (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  document_id uuid REFERENCES kb.documents(id) ON DELETE CASCADE,
  job_type text NOT NULL,
  status text NOT NULL,
  started_at timestamptz,
  finished_at timestamptz,
  error_text text,
  worker_id text,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_documents_project_id ON kb.documents(project_id);
CREATE INDEX IF NOT EXISTS idx_documents_repo_id ON kb.documents(repo_id);
CREATE INDEX IF NOT EXISTS idx_documents_source_type ON kb.documents(source_type);
CREATE INDEX IF NOT EXISTS idx_documents_status ON kb.documents(status);
CREATE INDEX IF NOT EXISTS idx_documents_title_trgm ON kb.documents USING gin (title gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_documents_source_path_trgm ON kb.documents USING gin (source_path gin_trgm_ops);

CREATE INDEX IF NOT EXISTS idx_pages_document_id ON kb.pages(document_id);
CREATE INDEX IF NOT EXISTS idx_pages_embedding_hnsw ON kb.pages USING hnsw (page_embedding vector_cosine_ops);

CREATE INDEX IF NOT EXISTS idx_chunks_document_id ON kb.chunks(document_id);
CREATE INDEX IF NOT EXISTS idx_chunks_page_id ON kb.chunks(page_id);
CREATE INDEX IF NOT EXISTS idx_chunks_kind ON kb.chunks(chunk_kind);
CREATE INDEX IF NOT EXISTS idx_chunks_tsv ON kb.chunks USING gin (tsv);
CREATE INDEX IF NOT EXISTS idx_chunks_embedding_hnsw ON kb.chunks USING hnsw (embedding vector_cosine_ops);

CREATE INDEX IF NOT EXISTS idx_assets_document_id ON kb.assets(document_id);
CREATE INDEX IF NOT EXISTS idx_assets_page_id ON kb.assets(page_id);
CREATE INDEX IF NOT EXISTS idx_assets_type ON kb.assets(asset_type);
CREATE INDEX IF NOT EXISTS idx_assets_ocr_text_trgm ON kb.assets USING gin (ocr_text gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_assets_caption_text_trgm ON kb.assets USING gin (caption_text gin_trgm_ops);

CREATE INDEX IF NOT EXISTS idx_ocr_blocks_document_id ON kb.ocr_blocks(document_id);
CREATE INDEX IF NOT EXISTS idx_ocr_blocks_page_id ON kb.ocr_blocks(page_id);
CREATE INDEX IF NOT EXISTS idx_ocr_blocks_asset_id ON kb.ocr_blocks(asset_id);
CREATE INDEX IF NOT EXISTS idx_ocr_blocks_tsv ON kb.ocr_blocks USING gin (tsv);

CREATE INDEX IF NOT EXISTS idx_image_embeddings_document_id ON kb.image_embeddings(document_id);
CREATE INDEX IF NOT EXISTS idx_image_embeddings_page_id ON kb.image_embeddings(page_id);
CREATE INDEX IF NOT EXISTS idx_image_embeddings_asset_id ON kb.image_embeddings(asset_id);
CREATE INDEX IF NOT EXISTS idx_image_embeddings_hnsw ON kb.image_embeddings USING hnsw (embedding vector_cosine_ops);

CREATE INDEX IF NOT EXISTS idx_files_repo_id ON kb.files(repo_id);
CREATE INDEX IF NOT EXISTS idx_files_document_id ON kb.files(document_id);
CREATE INDEX IF NOT EXISTS idx_files_relative_path_trgm ON kb.files USING gin (relative_path gin_trgm_ops);

CREATE INDEX IF NOT EXISTS idx_entities_name_trgm ON kb.entities USING gin (canonical_name gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_entities_normalized_name ON kb.entities(normalized_name);
CREATE INDEX IF NOT EXISTS idx_entities_type ON kb.entities(entity_type);

CREATE INDEX IF NOT EXISTS idx_chunk_entities_entity_id ON kb.chunk_entities(entity_id);
CREATE INDEX IF NOT EXISTS idx_asset_entities_entity_id ON kb.asset_entities(entity_id);
CREATE INDEX IF NOT EXISTS idx_relations_from ON kb.relations(from_entity_id);
CREATE INDEX IF NOT EXISTS idx_relations_to ON kb.relations(to_entity_id);
CREATE INDEX IF NOT EXISTS idx_relations_type ON kb.relations(relation_type);

CREATE INDEX IF NOT EXISTS idx_symbols_file_id ON kb.symbols(file_id);
CREATE INDEX IF NOT EXISTS idx_symbols_repo_id ON kb.symbols(repo_id);
CREATE INDEX IF NOT EXISTS idx_symbols_name_trgm ON kb.symbols USING gin (symbol_name gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_symbols_fq_name_trgm ON kb.symbols USING gin (fq_name gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_symbol_links_from ON kb.symbol_links(from_symbol_id);
CREATE INDEX IF NOT EXISTS idx_symbol_links_to ON kb.symbol_links(to_symbol_id);

CREATE INDEX IF NOT EXISTS idx_document_links_from ON kb.document_links(from_document_id);
CREATE INDEX IF NOT EXISTS idx_document_links_to ON kb.document_links(to_document_id);
CREATE INDEX IF NOT EXISTS idx_index_jobs_document_id ON kb.index_jobs(document_id);
CREATE INDEX IF NOT EXISTS idx_index_jobs_status ON kb.index_jobs(status);
CREATE INDEX IF NOT EXISTS idx_index_jobs_job_type ON kb.index_jobs(job_type);

DROP TRIGGER IF EXISTS trg_projects_touch_updated_at ON kb.projects;
CREATE TRIGGER trg_projects_touch_updated_at
BEFORE UPDATE ON kb.projects
FOR EACH ROW EXECUTE FUNCTION kb.touch_updated_at();

DROP TRIGGER IF EXISTS trg_repos_touch_updated_at ON kb.repos;
CREATE TRIGGER trg_repos_touch_updated_at
BEFORE UPDATE ON kb.repos
FOR EACH ROW EXECUTE FUNCTION kb.touch_updated_at();

DROP TRIGGER IF EXISTS trg_documents_touch_updated_at ON kb.documents;
CREATE TRIGGER trg_documents_touch_updated_at
BEFORE UPDATE ON kb.documents
FOR EACH ROW EXECUTE FUNCTION kb.touch_updated_at();

DROP TRIGGER IF EXISTS trg_files_touch_updated_at ON kb.files;
CREATE TRIGGER trg_files_touch_updated_at
BEFORE UPDATE ON kb.files
FOR EACH ROW EXECUTE FUNCTION kb.touch_updated_at();

DROP TRIGGER IF EXISTS trg_entities_touch_updated_at ON kb.entities;
CREATE TRIGGER trg_entities_touch_updated_at
BEFORE UPDATE ON kb.entities
FOR EACH ROW EXECUTE FUNCTION kb.touch_updated_at();

COMMIT;
