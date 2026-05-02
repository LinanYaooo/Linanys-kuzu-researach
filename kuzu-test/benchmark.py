import kuzu
import time
import statistics

db = kuzu.Database("./test_db")
conn = kuzu.Connection(db)

def bench(label, query, runs=5):
    times = []
    rows_count = None
    for _ in range(runs):
        start = time.perf_counter()
        result = conn.execute(query)
        rows = []
        while result.has_next():
            rows.append(result.get_next())
        elapsed = time.perf_counter() - start
        times.append(elapsed)
        if rows_count is None:
            rows_count = len(rows)
    avg = statistics.mean(times)
    med = statistics.median(times)
    mi = min(times)
    ma = max(times)
    print(f"{label:<45} rows={rows_count:<10} avg={avg:.4f}s  med={med:.4f}s  min={mi:.4f}s  max={ma:.4f}s")

print("=" * 110)
print("Kuzu Benchmark: 20 tables x 1M rows x 60 attrs = 20M nodes + ~39M edges")
print("=" * 110)

# --- 1. Count ---
bench("1. Count single table (1M rows)",      "MATCH (n:Account) RETURN count(n)")
bench("2. Count all nodes (20M)",              "MATCH (n) RETURN count(n)")
bench("3. Count all edges",                    "MATCH ()-[e]->() RETURN count(e)")

# --- 2. PK point lookup ---
bench("4. PK lookup id=0",                    "MATCH (n:Account {id: 0}) RETURN n.name, n.email, n.score")
bench("5. PK lookup id=500000",               "MATCH (n:Account {id: 500000}) RETURN n.name, n.email, n.score")
bench("6. PK lookup id=999999",               "MATCH (n:Account {id: 999999}) RETURN n.name, n.email, n.score")

# --- 3. Numeric filter ---
bench("7. Filter score > 90",                 "MATCH (n:Account) WHERE n.score > 90 RETURN count(n)")
bench("8. Filter balance > 90000",            "MATCH (n:Account) WHERE n.balance > 90000 RETURN count(n)")
bench("9. Multi-filter score>80 AND age<30",  "MATCH (n:Account) WHERE n.score > 80 AND n.age < 30 RETURN count(n)")

# --- 4. String filter ---
bench("10. City = 'Beijing'",                  'MATCH (n:Account) WHERE n.city = "Beijing" RETURN count(n)')
bench("11. Name prefix 'aaa'",                 'MATCH (n:Account) WHERE n.name STARTS WITH "aaa" RETURN count(n)')

# --- 5. Aggregation ---
bench("12. AVG score",                         "MATCH (n:Account) RETURN avg(n.score)")
bench("13. MIN/MAX balance",                   "MATCH (n:Account) RETURN min(n.balance), max(n.balance)")
bench("14. GROUP BY city + count",             "MATCH (n:Account) RETURN n.city, count(n) ORDER BY count(n) DESC")
bench("15. GROUP BY country + AVG score",      "MATCH (n:Account) RETURN n.country, avg(n.score) ORDER BY avg(n.score) DESC")

# --- 6. Sort + Limit ---
bench("16. Top 10 by score",                   "MATCH (n:Account) RETURN n.id, n.name, n.score ORDER BY n.score DESC LIMIT 10")
bench("17. Top 100 by balance",                "MATCH (n:Account) RETURN n.id, n.name, n.balance ORDER BY n.balance DESC LIMIT 100")

# --- 7. Multi-column projection ---
bench("18. Project 5 cols + LIMIT 1000",       "MATCH (n:Account) RETURN n.id, n.name, n.email, n.city, n.score LIMIT 1000")
bench("19. Project 20 cols + LIMIT 1000",      "MATCH (n:Account) RETURN n.id, n.name, n.email, n.phone, n.city, n.country, n.status, n.role, n.tier, n.score, n.rating, n.balance, n.income, n.age, n.views, n.likes, n.followers, n.posts, n.metric_a, n.metric_b LIMIT 1000")

# --- 8. Edge traversal (1-hop) ---
bench("20. 1-hop: Account->Post",              "MATCH (a:Account)-[:AccountCreatesPost]->(p:PostItem) RETURN count(*)")
bench("21. 1-hop: Account->Order",             "MATCH (a:Account)-[:AccountPlacesOrder]->(o:OrderItem) RETURN count(*)")
bench("22. 1-hop filtered: Account->Post where score>80", 'MATCH (a:Account {score: 95})-[:AccountCreatesPost]->(p:PostItem) RETURN count(*)')

# --- 9. Edge traversal (2-hop) ---
bench("23. 2-hop: Account->Post->Tag",         "MATCH (a:Account)-[:AccountCreatesPost]->(p:PostItem)-[:PostHasTag]->(t:Tag) RETURN count(*)")
bench("24. 2-hop: Account->Order->Product",    "MATCH (a:Account)-[:AccountPlacesOrder]->(o:OrderItem)-[:OrderContainsProduct]->(p:Product) RETURN count(*)")

# --- 10. Edge aggregation ---
bench("25. Account out-degree (all edges)",     "MATCH (a:Account)-[e]->() RETURN a.id, count(e) ORDER BY count(e) DESC LIMIT 10")
bench("26. Product in-degree via reviews",      "MATCH (p:Product)<-[:ProductHasReview]-(r:ReviewItem) RETURN p.id, count(r) ORDER BY count(r) DESC LIMIT 10")

print("=" * 110)
