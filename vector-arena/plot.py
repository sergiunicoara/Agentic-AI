import pandas as pd
import matplotlib.pyplot as plt

# Load CSV
df = pd.read_csv("./artifacts/results.csv")

# Remove failed engines and recall == 0
df = df[(df["status"] == "ok") & (df["recall@k"] > 0)]

# ===== Plot 1: Recall vs P95 =====
plt.figure(figsize=(8,6))

plt.xscale("log")
plt.scatter(df["batch_p95_ms"], df["recall@k"], s=120)

for i, row in df.iterrows():
    plt.text(row["batch_p95_ms"], row["recall@k"], row["engine"])

plt.xlabel("P95 Latency (ms)")
plt.ylabel("Recall@k")
plt.ylim(0, 1)
plt.title("Recall@k vs P95 Latency")
plt.grid(True)

plt.savefig("recall_vs_p95.png")
plt.show()


# ===== Plot 2: QPS =====
plt.figure(figsize=(8,6))

plt.bar(df["engine"], df["qps"])

plt.xlabel("Engine")
plt.ylabel("QPS")
plt.title("Queries Per Second")

plt.xticks(rotation=45)
plt.tight_layout()

plt.savefig("qps.png")
plt.show()
