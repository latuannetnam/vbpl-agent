# Query count of document in onyx
docker exec vbpl-onyx-relational_db-1 psql -U postgres -d postgres -c "SELECT COUNT(*) FROM document;"
