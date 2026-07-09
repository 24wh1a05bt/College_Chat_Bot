"""Test accreditation retrieval."""
from src.ingest import get_collection
collection = get_collection()

results = collection.query(query_texts=["accreditations of BVRIT Hyderabad NAAC NBA"], n_results=5)
print("=== Accreditation query ===")
for doc, meta in zip(results["documents"][0], results["metadatas"][0]):
    print(f'  [{meta["section"]}] Page {meta["page"]}')
    print(f'  {doc[:300]}')
    print()

results = collection.query(query_texts=["leadership management chairman principal BVRIT"], n_results=5)
print("=== Leadership query ===")
for doc, meta in zip(results["documents"][0], results["metadatas"][0]):
    print(f'  [{meta["section"]}] Page {meta["page"]}')
    print(f'  {doc[:300]}')
    print()