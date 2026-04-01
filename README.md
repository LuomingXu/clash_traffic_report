# Clash Connection Monitor

一个用于监控 Clash/Mihomo 连接数据并将数据持久化存储到 SQLite 数据库的 Rust 程序。


## 快速开始

### 1. 记录traffic log

```bash
cd clash_log
cargo run
# or
clash_log.exe --config config.toml
# 将会保存在connections.db(sqlite)中
```
### 2. 创建报告

```bash
cd clash_log_report
uv sync
# 注意两个路径配置
# DB_PATH = Path(__file__).parent.parent / "clash_log" / "connections.db"
# OUTPUT_PATH = Path(__file__).parent / "index.html"
uv run generate_report.py
# 然后打开index.html
```