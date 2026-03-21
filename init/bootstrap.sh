psql "$POSTGRES_DSN" -f 001_postgres_init.sql
cypher-shell -a "$NEO4J_URI" -u "$NEO4J_USER" -p "$NEO4J_PASSWORD" -d knowledge -f 001_neo4j_init.cypher
