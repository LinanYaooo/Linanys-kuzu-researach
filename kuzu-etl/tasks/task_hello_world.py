from kuzu_etl import ETLTask

task = ETLTask(
    source_db="postgresql",
    source_host="______",                   # ← 填写主机地址
    source_port=5432,
    source_username="______",               # ← 填写用户名
    source_password="______",               # ← 填写密码
    source_database="______",               # ← 填写数据库名
    source_schema="______",                 # ← 填写 schema，MySQL/SQLite 留 None
    source_table="suppliers",
    # 留空则自动映射源端所有列（列名 = 属性名）
    # 需要改名或转换时手动指定：
    # fields=[
    #     {"source_field": "id",    "target_property": "id"},
    #     {"source_field": "name",  "target_property": "name", "transform": "str(value).strip()"},
    # ],
    target_entity="Supplier",
    write_chunk_size=5000,
)
print(task.count())  # 查数量
n = task.clear()  # 清空并返回删了多少条
print(f"deleted {n}")

if __name__ == "__main__":
    result = task.run()
    print(result)  # extracted=100 written=100 elapsed_ms=523.4