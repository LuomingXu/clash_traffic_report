import sqlite3
import json
from datetime import datetime
from pathlib import Path
from collections import defaultdict
from jinja2 import Template

DB_PATH = Path(__file__).parent.parent / "clash_log" / "connections.db"
OUTPUT_PATH = Path(__file__).parent / "index.html"

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Clash Connection Report</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            min-height: 100vh;
            color: #e0e0e0;
            padding: 20px;
        }
        .container {
            max-width: 1400px;
            margin: 0 auto;
        }
        h1 {
            text-align: center;
            margin-bottom: 30px;
            color: #00d9ff;
            font-size: 2.5em;
            text-shadow: 0 0 20px rgba(0, 217, 255, 0.3);
        }
        .report-time {
            text-align: center;
            color: #888;
            margin-bottom: 30px;
        }
        .overview-cards {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin-bottom: 40px;
        }
        .card {
            background: rgba(255, 255, 255, 0.05);
            border-radius: 15px;
            padding: 25px;
            text-align: center;
            border: 1px solid rgba(255, 255, 255, 0.1);
            backdrop-filter: blur(10px);
            transition: transform 0.3s, box-shadow 0.3s;
        }
        .card:hover {
            transform: translateY(-5px);
            box-shadow: 0 10px 30px rgba(0, 217, 255, 0.2);
        }
        .card-value {
            font-size: 2em;
            font-weight: bold;
            color: #00d9ff;
            margin-bottom: 10px;
        }
        .card-label {
            color: #888;
            font-size: 0.9em;
        }
        .section {
            background: rgba(255, 255, 255, 0.05);
            border-radius: 15px;
            padding: 25px;
            margin-bottom: 30px;
            border: 1px solid rgba(255, 255, 255, 0.1);
        }
        .section h2 {
            color: #00d9ff;
            margin-bottom: 20px;
            padding-bottom: 10px;
            border-bottom: 2px solid rgba(0, 217, 255, 0.3);
        }
        .chart-container {
            position: relative;
            height: 600px;
        }
        .table-container {
            overflow-x: auto;
        }
        table {
            width: 100%;
            border-collapse: collapse;
        }
        th, td {
            padding: 12px 15px;
            text-align: left;
            border-bottom: 1px solid rgba(255, 255, 255, 0.1);
        }
        th {
            background: rgba(0, 217, 255, 0.1);
            color: #00d9ff;
            font-weight: 600;
        }
        tr:hover {
            background: rgba(255, 255, 255, 0.05);
        }
        .badge {
            display: inline-block;
            padding: 4px 10px;
            border-radius: 12px;
            font-size: 0.8em;
            background: rgba(0, 217, 255, 0.2);
            color: #00d9ff;
        }
        .chains-badge {
            background: rgba(255, 107, 107, 0.2);
            color: #ff6b6b;
        }
        .two-charts {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 20px;
        }
        @media (max-width: 900px) {
            .two-charts {
                grid-template-columns: 1fr;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>Clash Connection Report</h1>
        <p class="report-time">Report generated at: {{ generated_at }}</p>
        
        <div class="overview-cards">
            <div class="card">
                <div class="card-value">{{ overview.total_connections }}</div>
                <div class="card-label">Total Connections</div>
            </div>
            <div class="card">
                <div class="card-value">{{ overview.total_upload }}</div>
                <div class="card-label">Total Upload</div>
            </div>
            <div class="card">
                <div class="card-value">{{ overview.total_download }}</div>
                <div class="card-label">Total Download</div>
            </div>
            <div class="card">
                <div class="card-value">{{ overview.unique_hosts }}</div>
                <div class="card-label">Unique Hosts</div>
            </div>
            <div class="card">
                <div class="card-value">{{ overview.unique_processes }}</div>
                <div class="card-label">Unique Processes</div>
            </div>
        </div>

        <div class="section">
            <h2>Host Traffic Ranking (Top 20)</h2>
            <div class="chart-container">
                <canvas id="hostChart"></canvas>
            </div>
        </div>

        <div class="section">
            <h2>Host Traffic Ranking By Domain (Top 20)</h2>
            <div class="chart-container">
                <canvas id="domainChart"></canvas>
            </div>
        </div>

        <div class="two-charts">
            <div class="section">
                <h2>Proxy Node Usage</h2>
                <div class="chart-container">
                    <canvas id="nodeChart"></canvas>
                </div>
            </div>
            <div class="section">
                <h2>Process Traffic Statistics</h2>
                <div class="chart-container">
                    <canvas id="processChart"></canvas>
                </div>
            </div>
        </div>

        <div class="section">
            <h2>Daily Traffic Trend</h2>
            <div class="chart-container">
                <canvas id="dailyChart"></canvas>
            </div>
        </div>

        <div class="section">
            <h2>Rule Hit Statistics</h2>
            <div class="table-container">
                <table>
                    <thead>
                        <tr>
                            <th>Rule</th>
                            <th>Connections</th>
                            <th>Upload</th>
                            <th>Download</th>
                            <th>Total Traffic</th>
                        </tr>
                    </thead>
                    <tbody>
                        {% for rule in rule_stats %}
                        <tr>
                            <td><span class="badge">{{ rule.rule }}</span></td>
                            <td>{{ rule.count }}</td>
                            <td>{{ rule.upload }}</td>
                            <td>{{ rule.download }}</td>
                            <td>{{ rule.total }}</td>
                        </tr>
                        {% endfor %}
                    </tbody>
                </table>
            </div>
        </div>

        <div class="section">
            <h2>Host Details (Top 50)</h2>
            <div class="table-container">
                <table>
                    <thead>
                        <tr>
                            <th>Host</th>
                            <th>Connections</th>
                            <th>Upload</th>
                            <th>Download</th>
                            <th>Total Traffic</th>
                            <th>Proxy Chain</th>
                        </tr>
                    </thead>
                    <tbody>
                        {% for host in host_details %}
                        <tr>
                            <td>{{ host.host }}</td>
                            <td>{{ host.count }}</td>
                            <td>{{ host.upload }}</td>
                            <td>{{ host.download }}</td>
                            <td>{{ host.total }}</td>
                            <td><span class="badge chains-badge">{{ host.chain }}</span></td>
                        </tr>
                        {% endfor %}
                    </tbody>
                </table>
            </div>
        </div>
    </div>

    <script>
        const chartColors = {
            upload: 'rgba(0, 217, 255, 0.8)',
            download: 'rgba(255, 107, 107, 0.8)',
            uploadBg: 'rgba(0, 217, 255, 0.2)',
            downloadBg: 'rgba(255, 107, 107, 0.2)',
            grid: 'rgba(255, 255, 255, 0.1)',
            text: '#888'
        };

        Chart.defaults.color = chartColors.text;
        Chart.defaults.borderColor = chartColors.grid;

        function formatBytes(bytes) {
            if (bytes === 0) return '0 B';
            const k = 1024;
            const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
            const i = Math.floor(Math.log(bytes) / Math.log(k));
            return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
        }

        // Host Chart
        new Chart(document.getElementById('hostChart'), {
            type: 'bar',
            data: {
                labels: {{ host_labels | safe }},
                datasets: [{
                    label: 'Direct Download',
                    data: {{ host_direct_download | safe }},
                    backgroundColor: 'rgba(76, 175, 80, 0.8)',
                }, {
                    label: 'Proxy Download',
                    data: {{ host_proxy_download | safe }},
                    backgroundColor: 'rgba(255, 107, 107, 0.8)',
                }, {
                    label: 'Direct Upload',
                    data: {{ host_direct_upload | safe }},
                    backgroundColor: 'rgba(129, 199, 132, 0.8)',
                }, {
                    label: 'Proxy Upload',
                    data: {{ host_proxy_upload | safe }},
                    backgroundColor: 'rgba(0, 217, 255, 0.8)',
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                indexAxis: 'y',
                plugins: {
                    tooltip: {
                        callbacks: {
                            label: function(context) {
                                return context.dataset.label + ': ' + formatBytes(context.raw);
                            }
                        }
                    }
                },
                scales: {
                    x: {
                        stacked: true,
                        ticks: {
                            callback: function(value) {
                                return formatBytes(value);
                            }
                        }
                    },
                    y: {
                        stacked: true,
                        ticks: {
                            autoSkip: false
                        }
                    }
                }
            }
        });

        // Domain Chart
        new Chart(document.getElementById('domainChart'), {
            type: 'bar',
            data: {
                labels: {{ domain_labels | safe }},
                datasets: [{
                    label: 'Direct Download',
                    data: {{ domain_direct_download | safe }},
                    backgroundColor: 'rgba(76, 175, 80, 0.8)',
                }, {
                    label: 'Proxy Download',
                    data: {{ domain_proxy_download | safe }},
                    backgroundColor: 'rgba(255, 107, 107, 0.8)',
                }, {
                    label: 'Direct Upload',
                    data: {{ domain_direct_upload | safe }},
                    backgroundColor: 'rgba(129, 199, 132, 0.8)',
                }, {
                    label: 'Proxy Upload',
                    data: {{ domain_proxy_upload | safe }},
                    backgroundColor: 'rgba(0, 217, 255, 0.8)',
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                indexAxis: 'y',
                plugins: {
                    tooltip: {
                        callbacks: {
                            label: function(context) {
                                return context.dataset.label + ': ' + formatBytes(context.raw);
                            }
                        }
                    }
                },
                scales: {
                    x: {
                        stacked: true,
                        ticks: {
                            callback: function(value) {
                                return formatBytes(value);
                            }
                        }
                    },
                    y: {
                        stacked: true,
                        ticks: {
                            autoSkip: false
                        }
                    }
                }
            }
        });

        // Node Chart
        new Chart(document.getElementById('nodeChart'), {
            type: 'doughnut',
            data: {
                labels: {{ node_labels | safe }},
                datasets: [{
                    data: {{ node_traffic | safe }},
                    backgroundColor: [
                        '#00d9ff', '#ff6b6b', '#4ecdc4', '#ffe66d', 
                        '#95e1d3', '#f38181', '#aa96da', '#fcbad3',
                        '#a8d8ea', '#ffb6b9', '#fae3d9', '#bbded6'
                    ]
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    tooltip: {
                        callbacks: {
                            label: function(context) {
                                return context.label + ': ' + formatBytes(context.raw);
                            }
                        }
                    }
                }
            }
        });

        // Process Chart
        new Chart(document.getElementById('processChart'), {
            type: 'bar',
            data: {
                labels: {{ process_labels | safe }},
                datasets: [{
                    label: 'Download',
                    data: {{ process_download | safe }},
                    backgroundColor: chartColors.download,
                }, {
                    label: 'Upload',
                    data: {{ process_upload | safe }},
                    backgroundColor: chartColors.upload,
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    tooltip: {
                        callbacks: {
                            label: function(context) {
                                return context.dataset.label + ': ' + formatBytes(context.raw);
                            }
                        }
                    }
                },
                scales: {
                    x: {
                        stacked: true,
                        ticks: {
                            callback: function(value) {
                                return formatBytes(value);
                            }
                        }
                    },
                    y: {
                        stacked: true
                    }
                }
            }
        });

        // Daily Chart
        new Chart(document.getElementById('dailyChart'), {
            type: 'line',
            data: {
                labels: {{ daily_labels | safe }},
                datasets: [{
                    label: 'Download',
                    data: {{ daily_download | safe }},
                    borderColor: chartColors.download,
                    backgroundColor: chartColors.downloadBg,
                    fill: true,
                    tension: 0.4
                }, {
                    label: 'Upload',
                    data: {{ daily_upload | safe }},
                    borderColor: chartColors.upload,
                    backgroundColor: chartColors.uploadBg,
                    fill: true,
                    tension: 0.4
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    tooltip: {
                        callbacks: {
                            label: function(context) {
                                return context.dataset.label + ': ' + formatBytes(context.raw);
                            }
                        }
                    }
                },
                scales: {
                    y: {
                        ticks: {
                            callback: function(value) {
                                return formatBytes(value);
                            }
                        }
                    }
                }
            }
        });
    </script>
</body>
</html>
"""


def format_bytes(bytes_val: int) -> str:
    if bytes_val == 0:
        return "0 B"
    k = 1024
    sizes = ["B", "KB", "MB", "GB", "TB"]
    i = 0
    while bytes_val >= k and i < len(sizes) - 1:
        bytes_val /= k
        i += 1
    return f"{bytes_val:.2f} {sizes[i]}"


def get_db_connection():
    return sqlite3.connect(str(DB_PATH))


def get_overview(conn):
    total_connections = conn.execute("SELECT COUNT(*) FROM connections").fetchone()[0]
    
    upload, download = conn.execute("SELECT COALESCE(SUM(upload), 0), COALESCE(SUM(download), 0) FROM connections").fetchone()
    
    unique_hosts = conn.execute("SELECT COUNT(DISTINCT host) FROM connections WHERE host IS NOT NULL AND host != ''").fetchone()[0]
    
    unique_processes = conn.execute("SELECT COUNT(DISTINCT process_name) FROM connections WHERE process_name IS NOT NULL AND process_name != ''").fetchone()[0]
    
    return {
        "total_connections": total_connections,
        "total_upload": format_bytes(upload or 0),
        "total_download": format_bytes(download or 0),
        "unique_hosts": unique_hosts,
        "unique_processes": unique_processes,
    }


def get_host_stats(conn, limit=20):
    results = conn.execute("""
        SELECT 
            COALESCE(host, destination_ip) as host,
            chains,
            SUM(upload) as upload,
            SUM(download) as download
        FROM connections
        GROUP BY host, chains
        ORDER BY (SUM(upload) + SUM(download)) DESC
    """).fetchall()
    
    host_data = defaultdict(lambda: {"upload": 0, "download": 0, "direct_upload": 0, "direct_download": 0, "proxy_upload": 0, "proxy_download": 0})
    
    for row in results:
        host, chains_json, upload, download = row
        upload = upload or 0
        download = download or 0
        host_data[host]["upload"] += upload
        host_data[host]["download"] += download
        
        if is_direct(chains_json):
            host_data[host]["direct_upload"] += upload
            host_data[host]["direct_download"] += download
        else:
            host_data[host]["proxy_upload"] += upload
            host_data[host]["proxy_download"] += download
    
    sorted_hosts = sorted(host_data.items(), key=lambda x: x[1]["upload"] + x[1]["download"], reverse=True)[:limit]
    return sorted_hosts


def is_direct(chains_json: str) -> bool:
    try:
        chains = json.loads(chains_json)
        if isinstance(chains, list) and len(chains) > 0:
            return chains[0].upper() == "DIRECT"
        return True
    except (json.JSONDecodeError, TypeError):
        return True


def get_host_chains(conn, limit=50):
    return conn.execute("""
        SELECT 
            COALESCE(host, destination_ip) as host,
            COUNT(*) as count,
            SUM(upload) as upload,
            SUM(download) as download,
            chains
        FROM connections
        GROUP BY host
        ORDER BY (SUM(upload) + SUM(download)) DESC
        LIMIT ?
    """, [limit]).fetchall()


def extract_domain(host: str) -> str:
    if not host:
        return "Unknown"
    parts = host.split(".")
    if len(parts) >= 2:
        return ".".join(parts[-2:])
    return host


def get_domain_stats(conn, limit=20):
    results = conn.execute("""
        SELECT 
            COALESCE(host, destination_ip) as host,
            chains,
            SUM(upload) as upload,
            SUM(download) as download
        FROM connections
        GROUP BY host, chains
    """).fetchall()
    
    domain_data = defaultdict(lambda: {"upload": 0, "download": 0, "direct_upload": 0, "direct_download": 0, "proxy_upload": 0, "proxy_download": 0})
    
    for row in results:
        host, chains_json, upload, download = row
        upload = upload or 0
        download = download or 0
        domain = extract_domain(host)
        
        domain_data[domain]["upload"] += upload
        domain_data[domain]["download"] += download
        
        if is_direct(chains_json):
            domain_data[domain]["direct_upload"] += upload
            domain_data[domain]["direct_download"] += download
        else:
            domain_data[domain]["proxy_upload"] += upload
            domain_data[domain]["proxy_download"] += download
    
    sorted_domains = sorted(domain_data.items(), key=lambda x: x[1]["upload"] + x[1]["download"], reverse=True)[:limit]
    return sorted_domains


def get_node_stats(conn):
    results = conn.execute("""
        SELECT 
            chains,
            COUNT(*) as count,
            SUM(upload) + SUM(download) as traffic
        FROM connections
        GROUP BY chains
        ORDER BY traffic DESC
    """).fetchall()
    
    node_data = defaultdict(lambda: {"count": 0, "traffic": 0})
    for row in results:
        chains_json, count, traffic = row
        node_name = parse_chains_first(chains_json)
        node_data[node_name]["count"] += count
        node_data[node_name]["traffic"] += traffic or 0
    
    sorted_nodes = sorted(node_data.items(), key=lambda x: x[1]["traffic"], reverse=True)
    return [(name, data["count"], data["traffic"]) for name, data in sorted_nodes]


def parse_chains_first(chains_json: str) -> str:
    try:
        chains = json.loads(chains_json)
        if isinstance(chains, list) and len(chains) > 0:
            return chains[0]
        return "DIRECT"
    except (json.JSONDecodeError, TypeError):
        return "DIRECT"


def get_process_stats(conn, limit=15):
    return conn.execute("""
        SELECT 
            COALESCE(process_name, 'Unknown') as process,
            COUNT(*) as count,
            SUM(upload) as upload,
            SUM(download) as download
        FROM connections
        GROUP BY process_name
        ORDER BY (SUM(upload) + SUM(download)) DESC
        LIMIT ?
    """, [limit]).fetchall()


def get_daily_stats(conn):
    return conn.execute("""
        SELECT 
            date(start_time, 'unixepoch') as date,
            COUNT(*) as count,
            SUM(upload) as upload,
            SUM(download) as download
        FROM connections
        GROUP BY date
        ORDER BY date ASC
    """).fetchall()


def get_rule_stats(conn):
    return conn.execute("""
        SELECT 
            COALESCE(rule, 'Unknown') as rule,
            COUNT(*) as count,
            SUM(upload) as upload,
            SUM(download) as download
        FROM connections
        GROUP BY rule
        ORDER BY (SUM(upload) + SUM(download)) DESC
    """).fetchall()


def parse_chains(chains_json: str) -> str:
    try:
        chains = json.loads(chains_json)
        if isinstance(chains, list) and len(chains) > 0:
            return chains[0] if len(chains) == 1 else f"{chains[0]} (+{len(chains)-1})"
        return "Direct"
    except (json.JSONDecodeError, TypeError):
        return "Direct"


def generate_report():
    if not DB_PATH.exists():
        print(f"Database not found: {DB_PATH}")
        return
    
    conn = get_db_connection()
    
    try:
        overview = get_overview(conn)
        
        host_stats = get_host_stats(conn, 20)
        host_labels = [host or "Unknown" for host, data in host_stats]
        host_direct_download = [data["direct_download"] for host, data in host_stats]
        host_proxy_download = [data["proxy_download"] for host, data in host_stats]
        host_direct_upload = [data["direct_upload"] for host, data in host_stats]
        host_proxy_upload = [data["proxy_upload"] for host, data in host_stats]
        
        domain_stats = get_domain_stats(conn, 20)
        domain_labels = [domain or "Unknown" for domain, data in domain_stats]
        domain_direct_download = [data["direct_download"] for domain, data in domain_stats]
        domain_proxy_download = [data["proxy_download"] for domain, data in domain_stats]
        domain_direct_upload = [data["direct_upload"] for domain, data in domain_stats]
        domain_proxy_upload = [data["proxy_upload"] for domain, data in domain_stats]
        
        host_details_raw = get_host_chains(conn, 50)
        host_details = []
        for row in host_details_raw:
            host_details.append({
                "host": row[0] or "Unknown",
                "count": row[1],
                "upload": format_bytes(row[2] or 0),
                "download": format_bytes(row[3] or 0),
                "total": format_bytes((row[2] or 0) + (row[3] or 0)),
                "chain": parse_chains(row[4]),
            })
        
        node_stats = get_node_stats(conn)
        node_labels = [row[0] for row in node_stats]
        node_traffic = [row[2] or 0 for row in node_stats]
        
        process_stats = get_process_stats(conn, 15)
        process_labels = [row[0][:20] + "..." if len(row[0] or "") > 20 else (row[0] or "Unknown") for row in process_stats]
        process_upload = [row[2] or 0 for row in process_stats]
        process_download = [row[3] or 0 for row in process_stats]
        
        daily_stats = get_daily_stats(conn)
        daily_labels = [row[0] for row in daily_stats]
        daily_upload = [row[2] or 0 for row in daily_stats]
        daily_download = [row[3] or 0 for row in daily_stats]
        
        rule_stats_raw = get_rule_stats(conn)
        rule_stats = []
        for row in rule_stats_raw:
            rule_stats.append({
                "rule": row[0] or "Unknown",
                "count": row[1],
                "upload": format_bytes(row[2] or 0),
                "download": format_bytes(row[3] or 0),
                "total": format_bytes((row[2] or 0) + (row[3] or 0)),
            })
        
        template = Template(HTML_TEMPLATE)
        html = template.render(
            generated_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            overview=overview,
            host_labels=json.dumps(host_labels),
            host_direct_download=json.dumps(host_direct_download),
            host_proxy_download=json.dumps(host_proxy_download),
            host_direct_upload=json.dumps(host_direct_upload),
            host_proxy_upload=json.dumps(host_proxy_upload),
            domain_labels=json.dumps(domain_labels),
            domain_direct_download=json.dumps(domain_direct_download),
            domain_proxy_download=json.dumps(domain_proxy_download),
            domain_direct_upload=json.dumps(domain_direct_upload),
            domain_proxy_upload=json.dumps(domain_proxy_upload),
            host_details=host_details,
            node_labels=json.dumps(node_labels),
            node_traffic=json.dumps(node_traffic),
            process_labels=json.dumps(process_labels),
            process_upload=json.dumps(process_upload),
            process_download=json.dumps(process_download),
            daily_labels=json.dumps(daily_labels),
            daily_upload=json.dumps(daily_upload),
            daily_download=json.dumps(daily_download),
            rule_stats=rule_stats,
        )
        
        with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
            f.write(html)
        
        print(f"Report generated: {OUTPUT_PATH}")
        
    finally:
        conn.close()


if __name__ == "__main__":
    generate_report()
