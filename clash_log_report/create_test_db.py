import json
import os
import random
import sqlite3
from datetime import datetime, timedelta

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "clash_log", "connections.db")


def create_test_database():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS connections (
            id TEXT PRIMARY KEY,
            start_time INTEGER NOT NULL,
            end_time INTEGER,
            duration INTEGER,
            network TEXT NOT NULL,
            connection_type TEXT NOT NULL,
            source_ip TEXT NOT NULL,
            source_port TEXT NOT NULL,
            source_geo_ip TEXT,
            source_ip_asn TEXT,
            destination_ip TEXT NOT NULL,
            destination_port TEXT NOT NULL,
            destination_geo_ip TEXT,
            destination_ip_asn TEXT,
            host TEXT,
            sniff_host TEXT,
            chains TEXT NOT NULL,
            inbound_name TEXT,
            inbound_user TEXT,
            rule TEXT,
            rule_payload TEXT,
            upload INTEGER NOT NULL DEFAULT 0,
            download INTEGER NOT NULL DEFAULT 0,
            process TEXT,
            process_path TEXT,
            uid INTEGER,
            dns_mode TEXT,
            special_proxy TEXT,
            special_rules TEXT,
            remote_destination TEXT,
            dscp INTEGER,
            created_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL
        )
    """)

    hosts = [
        "google.com",
        "youtube.com",
        "github.com",
        "stackoverflow.com",
        "reddit.com",
        "twitter.com",
        "facebook.com",
        "instagram.com",
        "amazon.com",
        "netflix.com",
        "spotify.com",
        "discord.com",
        "slack.com",
        "zoom.us",
        "teams.microsoft.com",
        "cloudflare.com",
    ]

    processes = [
        "chrome.exe",
        "firefox.exe",
        "code.exe",
        "discord.exe",
        "spotify.exe",
        "slack.exe",
        "zoom.exe",
        "msedge.exe",
    ]

    chains = [
        '["HongKong-01"]',
        '["Japan-02"]',
        '["US-03"]',
        '["Singapore-04"]',
        '["Taiwan-05"]',
        '["Korea-06"]',
        '["Germany-07"]',
        '["UK-08"]',
    ]

    rules = ["DOMAIN-SUFFIX", "IP-CIDR", "GEOIP", "MATCH", "DOMAIN-KEYWORD"]

    now = datetime.now()

    for i in range(500):
        start_time = int(
            (
                now - timedelta(days=random.randint(0, 7), hours=random.randint(0, 23))
            ).timestamp()
        )
        end_time = start_time + random.randint(10, 3600)

        host = random.choice(hosts)
        process = random.choice(processes)
        chain = random.choice(chains)
        rule = random.choice(rules)

        upload = random.randint(1000, 100000000)
        download = random.randint(10000, 500000000)

        cursor.execute(
            """
            INSERT OR REPLACE INTO connections (
                id, start_time, end_time, duration,
                network, connection_type,
                source_ip, source_port,
                destination_ip, destination_port,
                host, chains, rule, rule_payload,
                upload, download, process, process_path,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                f"conn-{i:04d}",
                start_time,
                end_time,
                end_time - start_time,
                random.choice(["TCP", "UDP"]),
                random.choice(["HTTP", "HTTPConnect", "SOCKS5", "Tun"]),
                "192.168.1.100",
                str(random.randint(40000, 60000)),
                f"203.{random.randint(1, 255)}.{random.randint(1, 255)}.{random.randint(1, 255)}",
                "443",
                host,
                chain,
                rule,
                host,
                upload,
                download,
                process,
                f"C:/Program Files/{process}",
                start_time,
                end_time,
            ),
        )

    conn.commit()
    conn.close()
    print(f"Test database created: {DB_PATH}")


if __name__ == "__main__":
    create_test_database()
