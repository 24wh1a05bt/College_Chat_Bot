"""Quick test to verify Important Dates table content is retrievable."""
from src.ingest import get_collection

collection = get_collection()

# Test 1: Query about TS EAMCET exam date
print("=== Test 1: TS EAMCET exam date ===")
results = collection.query(query_texts=["TS EAMCET exam date"], n_results=5)
for doc, meta in zip(results["documents"][0], results["metadatas"][0]):
    print(f'  [{meta["section"]}] Page {meta["page"]}')
    print(f'  {doc[:300]}')
    print()

# Test 2: Query about important dates
print("=== Test 2: Important dates ===")
results = collection.query(query_texts=["important dates academic calendar"], n_results=5)
for doc, meta in zip(results["documents"][0], results["metadatas"][0]):
    print(f'  [{meta["section"]}] Page {meta["page"]}')
    print(f'  {doc[:300]}')
    print()

# Test 3: Query about admission deadline
print("=== Test 3: Admission deadline ===")
results = collection.query(query_texts=["admission deadline 2025"], n_results=5)
for doc, meta in zip(results["documents"][0], results["metadatas"][0]):
    print(f'  [{meta["section"]}] Page {meta["page"]}')
    print(f'  {doc[:300]}')
    print()