import time
import warnings
from pymilvus import MilvusClient
import weaviate
import chromadb
from pinecone import Pinecone, ServerlessSpec
from sentence_transformers import SentenceTransformer

# --- CONFIG ---
warnings.filterwarnings("ignore")
model = SentenceTransformer('all-MiniLM-L6-v2')
dim = 384
PINECONE_API_KEY = "pcsk_6gRbm6_Nkz1QUEN2wC2zGxq4ZT6WRRReNmMsaUfH9frpeBWizuRHAXHiVcnyE4regWWjCq" 

documents = [
    {"text": "AI is transforming medical diagnostics.", "cat": "Science"},
    {"text": "SpaceX plans a Mars colony by 2030.", "cat": "Engineering"},
    {"text": "Stock markets dipped on tech news.", "cat": "Finance"},
    {"text": "Quantum computing makes encryption vulnerable.", "cat": "Engineering"},
    {"text": "Sustainable energy is the future of transport.", "cat": "Engineering"},
    {"text": "Cryogenic cooling is vital for quantum hardware stability.", "cat": "Engineering"}
]
texts = [d["text"] for d in documents]
embeddings = model.encode(texts).astype('float32').tolist()

def seed_milvus():
    print("🚀 Connecting to Milvus...")
    # Using 127.0.0.1 for better Windows compatibility
    client = MilvusClient(uri="http://127.0.0.1:19530")
    
    if client.has_collection("arena"):
        client.drop_collection("arena")
    
    client.create_collection(collection_name="arena", dimension=dim)
    data = [{"id": i, "vector": embeddings[i], "text": texts[i], "cat": documents[i]["cat"]} for i in range(len(texts))]
    client.insert(collection_name="arena", data=data)
    print("✅ Milvus Seeded Successfully.")

def seed_weaviate():
    print("🚀 Seeding Weaviate...")
    client = weaviate.connect_to_local(port=8081, grpc_port=50052)
    if client.collections.exists("Arena"):
        client.collections.delete("Arena")
    from weaviate.classes.config import Property, DataType as WvData
    client.collections.create(
        name="Arena",
        properties=[Property(name="text", data_type=WvData.TEXT), Property(name="cat", data_type=WvData.TEXT)]
    )
    coll = client.collections.get("Arena")
    with coll.batch.dynamic() as batch:
        for i, doc in enumerate(documents):
            batch.add_object(properties={"text": doc["text"], "cat": doc["cat"]}, vector=embeddings[i])
    client.close()
    print("✅ Weaviate Ready.")

def seed_chroma():
    print("🚀 Seeding ChromaDB...")
    client = chromadb.HttpClient(host='127.0.0.1', port=8000)
    try: client.delete_collection("arena")
    except: pass
    coll = client.create_collection("arena")
    coll.add(ids=[str(i) for i in range(len(texts))], embeddings=embeddings, metadatas=[{"cat": d["cat"]} for d in documents], documents=texts)
    print("✅ ChromaDB Ready.")

def seed_pinecone():
    print("🚀 Seeding Pinecone...")
    pc = Pinecone(api_key=PINECONE_API_KEY)
    index_name = "arena"
    if index_name in [idx.name for idx in pc.list_indexes()]:
        pc.delete_index(index_name)
    pc.create_index(name=index_name, dimension=dim, metric="cosine", spec=ServerlessSpec(cloud="aws", region="us-east-1"))
    while not pc.describe_index(index_name).status['ready']:
        time.sleep(2)
    idx = pc.Index(index_name)
    vectors = [{"id": str(i), "values": embeddings[i], "metadata": {"text": texts[i], "cat": documents[i]["cat"]}} for i in range(len(texts))]
    idx.upsert(vectors)
    print("✅ Pinecone Ready.")

if __name__ == "__main__":
    try:
        seed_milvus()
        seed_weaviate()
        seed_chroma()
        seed_pinecone()
        print("\n🏆 BATTLE READY: All databases seeded!")
    except Exception as e:
        print(f"❌ Error during seeding: {e}")