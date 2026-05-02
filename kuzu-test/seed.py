import kuzu
import csv
import random
import string
import time
import os

DB_PATH = "./test_db"
CSV_DIR = "./csv_data"

NODES_PER_TABLE = 1_000_000

tables = [
    "Account", "Product", "OrderItem", "Category", "Tag",
    "CommentItem", "PostItem", "GroupItem", "EventItem", "LocationItem",
    "Company", "Department", "ProjectItem", "TaskItem", "ReviewItem",
    "PhotoItem", "VideoItem", "ArticleItem", "CourseItem", "CertificateItem",
]

# 60 attributes: name, type, generator
attrs = [
    ("id",              "INT64",  lambda i: i),
    ("name",            "STRING", lambda i: "".join(random.choices(string.ascii_lowercase, k=8))),
    ("email",           "STRING", lambda i: f"user{i}@example.com"),
    ("phone",           "STRING", lambda i: f"+1-{random.randint(100,999)}-{random.randint(100,999)}-{random.randint(1000,9999)}"),
    ("address",         "STRING", lambda i: f"{random.randint(1,9999)} {random.choice(['Main','Oak','Pine','Elm','Maple'])} St"),
    ("city",            "STRING", lambda i: random.choice(["Beijing","Shanghai","Shenzhen","Guangzhou","Hangzhou","Chengdu","Wuhan","Nanjing"])),
    ("country",         "STRING", lambda i: random.choice(["CN","US","JP","KR","GB","DE","FR","AU"])),
    ("zipcode",         "STRING", lambda i: f"{random.randint(10000,99999)}"),
    ("bio",             "STRING", lambda i: "".join(random.choices(string.ascii_lowercase + " ", k=30)).strip()),
    ("status",          "STRING", lambda i: random.choice(["active","inactive","pending","suspended"])),
    ("role",            "STRING", lambda i: random.choice(["admin","user","moderator","guest","vip"])),
    ("tier",            "STRING", lambda i: random.choice(["free","basic","pro","enterprise"])),
    ("level",           "STRING", lambda i: f"L{random.randint(1,10)}"),
    ("badge",           "STRING", lambda i: random.choice(["gold","silver","bronze","none"])),
    ("category",        "STRING", lambda i: random.choice(["A","B","C","D","E"])),
    ("tag",             "STRING", lambda i: f"tag_{random.randint(1,50)}"),
    ("label",           "STRING", lambda i: f"label_{random.randint(1,20)}"),
    ("score",           "DOUBLE", lambda i: round(random.random() * 100, 2)),
    ("rating",          "DOUBLE", lambda i: round(random.random() * 5, 2)),
    ("balance",         "DOUBLE", lambda i: round(random.random() * 100000, 2)),
    ("income",          "DOUBLE", lambda i: round(random.random() * 50000, 2)),
    ("price",           "DOUBLE", lambda i: round(random.random() * 10000, 2)),
    ("discount",        "DOUBLE", lambda i: round(random.random() * 0.5, 4)),
    ("tax",             "DOUBLE", lambda i: round(random.random() * 0.3, 4)),
    ("weight",          "DOUBLE", lambda i: round(random.random() * 1000, 2)),
    ("age",             "INT64",  lambda i: random.randint(18, 80)),
    ("count",           "INT64",  lambda i: random.randint(0, 10000)),
    ("views",           "INT64",  lambda i: random.randint(0, 1000000)),
    ("likes",           "INT64",  lambda i: random.randint(0, 500000)),
    ("shares",          "INT64",  lambda i: random.randint(0, 100000)),
    ("followers",       "INT64",  lambda i: random.randint(0, 500000)),
    ("friends",         "INT64",  lambda i: random.randint(0, 5000)),
    ("posts",           "INT64",  lambda i: random.randint(0, 10000)),
    ("flag_a",          "BOOL",   lambda i: random.choice([True, False])),
    ("flag_b",          "BOOL",   lambda i: random.choice([True, False])),
    ("flag_c",          "BOOL",   lambda i: random.choice([True, False])),
    ("flag_d",          "BOOL",   lambda i: random.choice([True, False])),
    ("flag_e",          "BOOL",   lambda i: random.choice([True, False])),
    ("flag_f",          "BOOL",   lambda i: random.choice([True, False])),
    ("flag_g",          "BOOL",   lambda i: random.choice([True, False])),
    ("flag_h",          "BOOL",   lambda i: random.choice([True, False])),
    ("flag_i",          "BOOL",   lambda i: random.choice([True, False])),
    ("metric_a",        "DOUBLE", lambda i: round(random.random() * 100, 4)),
    ("metric_b",        "DOUBLE", lambda i: round(random.random() * 100, 4)),
    ("metric_c",        "DOUBLE", lambda i: round(random.random() * 100, 4)),
    ("metric_d",        "DOUBLE", lambda i: round(random.random() * 100, 4)),
    ("desc_a",          "STRING", lambda i: "".join(random.choices(string.ascii_lowercase + " ", k=20)).strip()),
    ("desc_b",          "STRING", lambda i: "".join(random.choices(string.ascii_lowercase + " ", k=20)).strip()),
    ("desc_c",          "STRING", lambda i: "".join(random.choices(string.ascii_lowercase + " ", k=20)).strip()),
    ("desc_d",          "STRING", lambda i: "".join(random.choices(string.ascii_lowercase + " ", k=20)).strip()),
    ("created_at",      "STRING", lambda i: f"202{random.randint(0,5)}-{random.randint(1,12):02d}-{random.randint(1,28):02d}"),
    ("updated_at",      "STRING", lambda i: f"202{random.randint(0,5)}-{random.randint(1,12):02d}-{random.randint(1,28):02d}"),
    ("deleted_at",      "STRING", lambda i: "" if random.random() > 0.1 else f"202{random.randint(3,5)}-{random.randint(1,12):02d}-{random.randint(1,28):02d}"),
    ("published_at",    "STRING", lambda i: f"202{random.randint(0,5)}-{random.randint(1,12):02d}-{random.randint(1,28):02d}"),
    ("extra_a",         "STRING", lambda i: f"ext_{random.randint(1,100)}"),
    ("extra_b",         "STRING", lambda i: f"ext_{random.randint(1,100)}"),
    ("extra_c",         "STRING", lambda i: f"ext_{random.randint(1,100)}"),
    ("extra_d",         "STRING", lambda i: f"ext_{random.randint(1,100)}"),
    ("value_a",         "DOUBLE", lambda i: round(random.random() * 1000, 2)),
    ("value_b",         "DOUBLE", lambda i: round(random.random() * 1000, 2)),
]

assert len(attrs) == 60, f"Expected 60 attrs, got {len(attrs)}"

# Edge definitions: (rel_name, src_table, dst_table, estimated_count)
edges = [
    ("AccountCreatesPost",   "Account",    "PostItem",       3_000_000),
    ("AccountWritesComment", "Account",    "CommentItem",    5_000_000),
    ("AccountJoinsGroup",    "Account",    "GroupItem",      2_000_000),
    ("AccountPlacesOrder",   "Account",    "OrderItem",      4_000_000),
    ("AccountWritesReview",  "Account",    "ReviewItem",     3_000_000),
    ("AccountWorksAtCompany","Account",    "Company",        1_000_000),
    ("AccountAttendsEvent",  "Account",    "EventItem",      2_000_000),
    ("AccountEnrollsCourse", "Account",    "CourseItem",     1_500_000),
    ("AccountEarnsCert",     "Account",    "CertificateItem",1_000_000),
    ("PostHasTag",           "PostItem",   "Tag",            2_000_000),
    ("PostInCategory",       "PostItem",   "Category",       1_000_000),
    ("ProductInCategory",    "Product",    "Category",       1_000_000),
    ("ProductHasReview",     "Product",    "ReviewItem",     3_000_000),
    ("OrderContainsProduct", "OrderItem",  "Product",        6_000_000),
    ("CompanyHasDept",       "Company",    "Department",     500_000),
    ("ProjectHasTask",       "ProjectItem","TaskItem",       2_000_000),
    ("EventAtLocation",      "EventItem",  "LocationItem",   1_000_000),
]

os.makedirs(CSV_DIR, exist_ok=True)
db = kuzu.Database(DB_PATH)
conn = kuzu.Connection(db)

# ============ Create node tables ============
print("Creating node tables (60 attributes each)...")
attr_defs = ", ".join(f"{a[0]} {a[1]}" for a in attrs)
pk_def = ", PRIMARY KEY (id)"
for t in tables:
    conn.execute(f"CREATE NODE TABLE {t} ({attr_defs}{pk_def})")
print(f"  {len(tables)} node tables created")

# ============ Generate node CSVs ============
print(f"\nGenerating node CSVs ({NODES_PER_TABLE:,} rows x 60 cols x {len(tables)} tables)...")
header = [a[0] for a in attrs]
for t in tables:
    start = time.time()
    path = os.path.join(CSV_DIR, f"{t}.csv")
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        for i in range(NODES_PER_TABLE):
            row = [a[2](i) for a in attrs]
            writer.writerow(row)
    elapsed = time.time() - start
    print(f"  {t}.csv: {NODES_PER_TABLE:,} rows in {elapsed:.1f}s")

# ============ Import node CSVs ============
print("\nImporting node data via COPY FROM...")
for t in tables:
    start = time.time()
    path = os.path.join(CSV_DIR, f"{t}.csv").replace(os.sep, "/")
    conn.execute(f'COPY {t} FROM "{path}" (HEADER=true)')
    elapsed = time.time() - start
    print(f"  {t}: {NODES_PER_TABLE:,} rows in {elapsed:.1f}s")

result = conn.execute("MATCH (n) RETURN count(n)")
print(f"\nTotal nodes: {result.get_next()[0]:,}")

# ============ Create edge tables ============
print("\nCreating edge tables (17 relationship types)...")
edge_attr = "since INT64, weight DOUBLE, label STRING"
for rel_name, src, dst, _ in edges:
    conn.execute(f"CREATE REL TABLE {rel_name} (FROM {src} TO {dst}, {edge_attr})")
print(f"  {len(edges)} edge tables created")

# ============ Generate edge CSVs ============
print("\nGenerating edge CSVs...")
for rel_name, src, dst, count in edges:
    start = time.time()
    path = os.path.join(CSV_DIR, f"{rel_name}.csv")
    src_max = NODES_PER_TABLE
    dst_max = NODES_PER_TABLE
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["from", "to", "since", "weight", "label"])
        for _ in range(count):
            src_id = random.randint(0, src_max - 1)
            dst_id = random.randint(0, dst_max - 1)
            since = random.randint(2015, 2025)
            weight = round(random.random() * 10, 2)
            label = random.choice(["friend", "member", "owner", "creator", "participant"])
            writer.writerow([src_id, dst_id, since, weight, label])
    elapsed = time.time() - start
    print(f"  {rel_name}.csv: {count:,} rows in {elapsed:.1f}s")

# ============ Import edge CSVs ============
print("\nImporting edge data via COPY FROM...")
total_edges = 0
for rel_name, src, dst, count in edges:
    start = time.time()
    path = os.path.join(CSV_DIR, f"{rel_name}.csv").replace(os.sep, "/")
    conn.execute(f'COPY {rel_name} FROM "{path}" (HEADER=true)')
    elapsed = time.time() - start
    total_edges += count
    print(f"  {rel_name}: {count:,} rows in {elapsed:.1f}s")

result = conn.execute("MATCH ()-[e]->() RETURN count(e)")
actual_edges = result.get_next()[0]
print(f"\nTotal edges: {actual_edges:,}")
print(f"\n{'='*60}")
print(f"Database ready: {len(tables)} node tables x {NODES_PER_TABLE:,} rows = {len(tables)*NODES_PER_TABLE:,} nodes")
print(f"                {len(edges)} edge tables = {actual_edges:,} edges")
print(f"{'='*60}")
