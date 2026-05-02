import kuzu
import os
import psutil
import gc

proc = psutil.Process(os.getpid())

def mem_mb():
    gc.collect()
    return proc.memory_info().rss / 1024 / 1024

before = mem_mb()
print(f"1. Python baseline:                     {before:.1f} MB")

db = kuzu.Database("./test_db")
after_db = mem_mb()
print(f"2. After Database():                    {after_db:.1f} MB  (delta: +{after_db - before:.1f} MB)")

conn = kuzu.Connection(db)
after_conn = mem_mb()
print(f"3. After Connection():                  {after_conn:.1f} MB  (delta: +{after_conn - after_db:.1f} MB)")

# Count all nodes
result = conn.execute("MATCH (n) RETURN count(n)")
node_count = result.get_next()[0]
after_count = mem_mb()
print(f"4. After COUNT all nodes ({node_count:,}):    {after_count:.1f} MB  (delta: +{after_count - after_conn:.1f} MB)")

# Count all edges
result = conn.execute("MATCH ()-[e]->() RETURN count(e)")
edge_count = result.get_next()[0]
after_edges = mem_mb()
print(f"5. After COUNT all edges ({edge_count:,}):  {after_edges:.1f} MB  (delta: +{after_edges - after_count:.1f} MB)")

# PK lookup
result = conn.execute("MATCH (n:Account {id: 500000}) RETURN n.name, n.email, n.score, n.city")
row = result.get_next()
after_lookup = mem_mb()
print(f"6. After PK lookup (1 row, 4 cols):     {after_lookup:.1f} MB  (delta: +{after_lookup - after_edges:.1f} MB)")

# Fetch 1000 rows wide
result = conn.execute("MATCH (n:Account) RETURN n.id, n.name, n.email, n.phone, n.city, n.country, n.status, n.role, n.tier, n.score, n.rating, n.balance, n.income, n.age, n.views, n.likes, n.followers, n.posts, n.metric_a, n.metric_b LIMIT 1000")
rows = []
while result.has_next():
    rows.append(result.get_next())
after_1k = mem_mb()
print(f"7. After fetching 1000 rows (20 cols):  {after_1k:.1f} MB  (delta: +{after_1k - after_lookup:.1f} MB)")

# Fetch 10000 rows narrow
result = conn.execute("MATCH (n:Account) RETURN n.id, n.name, n.score LIMIT 10000")
rows = []
while result.has_next():
    rows.append(result.get_next())
after_10k = mem_mb()
print(f"8. After fetching 10000 rows (3 cols):  {after_10k:.1f} MB  (delta: +{after_10k - after_1k:.1f} MB)")

# Aggregation
result = conn.execute("MATCH (n:Account) RETURN avg(n.score), min(n.balance), max(n.income)")
row = result.get_next()
after_agg = mem_mb()
print(f"9. After AVG/MIN/MAX aggregation:       {after_agg:.1f} MB  (delta: +{after_agg - after_10k:.1f} MB)")

# Group by
result = conn.execute("MATCH (n:Account) RETURN n.country, count(n), avg(n.score) ORDER BY count(n) DESC")
rows = []
while result.has_next():
    rows.append(result.get_next())
after_groupby = mem_mb()
print(f"10. After GROUP BY country ({len(rows)} rows):    {after_groupby:.1f} MB  (delta: +{after_groupby - after_agg:.1f} MB)")

# Sort
result = conn.execute("MATCH (n:Account) RETURN n.id, n.name, n.score ORDER BY n.score DESC LIMIT 100")
rows = []
while result.has_next():
    rows.append(result.get_next())
after_sort = mem_mb()
print(f"11. After ORDER BY + LIMIT 100:         {after_sort:.1f} MB  (delta: +{after_sort - after_groupby:.1f} MB)")

# 1-hop edge traversal
result = conn.execute("MATCH (a:Account)-[:AccountCreatesPost]->(p:PostItem) RETURN count(*)")
row = result.get_next()
after_1hop = mem_mb()
print(f"12. After 1-hop traversal (count):      {after_1hop:.1f} MB  (delta: +{after_1hop - after_sort:.1f} MB)")

# 2-hop edge traversal
result = conn.execute("MATCH (a:Account)-[:AccountPlacesOrder]->(o:OrderItem)-[:OrderContainsProduct]->(p:Product) RETURN count(*)")
row = result.get_next()
after_2hop = mem_mb()
print(f"13. After 2-hop traversal (count):      {after_2hop:.1f} MB  (delta: +{after_2hop - after_1hop:.1f} MB)")

# DB file size
db_size = os.path.getsize("./test_db") / 1024 / 1024
print(f"\nDatabase file on disk:                  {db_size:.1f} MB")
print(f"Total process RSS:                      {after_2hop:.1f} MB")
print(f"Net Kuzu overhead:                      {after_2hop - before:.1f} MB")
