// Run against the target database, for example: cypher-shell -d knowledge -f 001_neo4j_init.cypher

CREATE CONSTRAINT document_doc_id IF NOT EXISTS
FOR (n:Document) REQUIRE n.doc_id IS UNIQUE;

CREATE CONSTRAINT page_page_id IF NOT EXISTS
FOR (n:Page) REQUIRE n.page_id IS UNIQUE;

CREATE CONSTRAINT chunk_chunk_id IF NOT EXISTS
FOR (n:Chunk) REQUIRE n.chunk_id IS UNIQUE;

CREATE CONSTRAINT asset_asset_id IF NOT EXISTS
FOR (n:Asset) REQUIRE n.asset_id IS UNIQUE;

CREATE CONSTRAINT ocrblock_ocr_block_id IF NOT EXISTS
FOR (n:OCRBlock) REQUIRE n.ocr_block_id IS UNIQUE;

CREATE CONSTRAINT entity_entity_id IF NOT EXISTS
FOR (n:Entity) REQUIRE n.entity_id IS UNIQUE;

CREATE CONSTRAINT project_project_id IF NOT EXISTS
FOR (n:Project) REQUIRE n.project_id IS UNIQUE;

CREATE CONSTRAINT repo_repo_id IF NOT EXISTS
FOR (n:Repo) REQUIRE n.repo_id IS UNIQUE;

CREATE CONSTRAINT file_file_id IF NOT EXISTS
FOR (n:File) REQUIRE n.file_id IS UNIQUE;

CREATE CONSTRAINT symbol_symbol_id IF NOT EXISTS
FOR (n:Symbol) REQUIRE n.symbol_id IS UNIQUE;

CREATE FULLTEXT INDEX document_search_text IF NOT EXISTS
FOR (n:Document) ON EACH [n.title, n.source_path, n.source_type];

CREATE FULLTEXT INDEX entity_search_text IF NOT EXISTS
FOR (n:Entity) ON EACH [n.canonical_name, n.entity_type];

CREATE FULLTEXT INDEX symbol_search_text IF NOT EXISTS
FOR (n:Symbol) ON EACH [n.symbol_name, n.fq_name, n.symbol_kind];

CREATE FULLTEXT INDEX file_search_text IF NOT EXISTS
FOR (n:File) ON EACH [n.relative_path, n.language];

CREATE FULLTEXT INDEX repo_search_text IF NOT EXISTS
FOR (n:Repo) ON EACH [n.name, n.root_path];

// Optional: only if you later store embeddings in Neo4j itself.
// CREATE VECTOR INDEX chunk_embedding_idx IF NOT EXISTS
// FOR (n:Chunk) ON (n.embedding)
// OPTIONS {indexConfig: {
//   `vector.dimensions`: 768,
//   `vector.similarity_function`: 'cosine'
// }};
