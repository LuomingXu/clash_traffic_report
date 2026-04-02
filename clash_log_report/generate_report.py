import json
import sqlite3
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

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
        .time-range-tabs {
            display: flex;
            justify-content: center;
            gap: 10px;
            margin-bottom: 30px;
        }
        .time-tab {
            padding: 10px 20px;
            background: rgba(255, 255, 255, 0.05);
            border: 1px solid rgba(255, 255, 255, 0.1);
            border-radius: 8px;
            color: #888;
            cursor: pointer;
            transition: all 0.3s;
        }
        .time-tab:hover {
            background: rgba(255, 255, 255, 0.1);
        }
        .time-tab.active {
            background: rgba(0, 217, 255, 0.2);
            border-color: #00d9ff;
            color: #00d9ff;
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
        .legend {
            display: flex;
            justify-content: center;
            gap: 20px;
            margin-bottom: 20px;
            flex-wrap: wrap;
        }
        .legend-item {
            display: flex;
            align-items: center;
            gap: 8px;
        }
        .legend-color {
            width: 20px;
            height: 20px;
            border-radius: 4px;
        }
        .direct-download { background-color: #58D68D; }
        .direct-upload { background-color: #1E8449; }
        .proxy-download { background-color: #EC7063; }
        .proxy-upload { background-color: #943126; }
        .time-range-content {
            display: none;
        }
        .time-range-content.active {
            display: block;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>Clash Connection Report</h1>
        <p class="report-time">Report generated at: {{ generated_at }}</p>
        
        <div class="time-range-tabs">
            <button class="time-tab active" data-range="8h">8h</button>
            <button class="time-tab" data-range="24h">24h</button>
            <button class="time-tab" data-range="1D">1D</button>
            <button class="time-tab" data-range="1M">1M</button>
            <button class="time-tab" data-range="All">All</button>
        </div>

        <div class="legend">
            <div class="legend-item">
                <div class="legend-color direct-download"></div>
                <span>直连下载 (DL)</span>
            </div>
            <div class="legend-item">
                <div class="legend-color direct-upload"></div>
                <span>直连上传 (UL)</span>
            </div>
            <div class="legend-item">
                <div class="legend-color proxy-download"></div>
                <span>代理下载 (DL)</span>
            </div>
            <div class="legend-item">
                <div class="legend-color proxy-upload"></div>
                <span>代理上传 (UL)</span>
            </div>
        </div>

        {% for time_range in time_ranges %}
        <div class="time-range-content {% if time_range == '8h' %}active{% endif %}" id="content-{{ time_range }}">
            <div class="overview-cards">
                <div class="card">
                    <div class="card-value">{{ overview_data[time_range].total_connections }}</div>
                    <div class="card-label">Total Connections</div>
                </div>
                <div class="card">
                    <div class="card-value">{{ overview_data[time_range].total_upload }}</div>
                    <div class="card-label">Total Upload</div>
                </div>
                <div class="card">
                    <div class="card-value">{{ overview_data[time_range].total_download }}</div>
                    <div class="card-label">Total Download</div>
                </div>
                <div class="card">
                    <div class="card-value">{{ overview_data[time_range].unique_hosts }}</div>
                    <div class="card-label">Unique Hosts</div>
                </div>
                <div class="card">
                    <div class="card-value">{{ overview_data[time_range].unique_processes }}</div>
                    <div class="card-label">Unique Processes</div>
                </div>
            </div>

            <div class="section">
                <h2>Host Traffic Ranking By Domain (Top 20)</h2>
                <div class="chart-container">
                    <canvas id="domainChart-{{ time_range }}"></canvas>
                </div>
            </div>

            <div class="two-charts">
                <div class="section">
                    <h2>Proxy Node Usage</h2>
                    <div class="chart-container">
                        <canvas id="nodeChart-{{ time_range }}"></canvas>
                    </div>
                </div>
                <div class="section">
                    <h2>Process Traffic Statistics</h2>
                    <div class="chart-container">
                        <canvas id="processChart-{{ time_range }}"></canvas>
                    </div>
                </div>
            </div>
        </div>
        {% endfor %}
    </div>

    <script>
        const chartColors = {
            directDownload: '#58D68D',
            directUpload: '#1E8449',
            proxyDownload: '#EC7063',
            proxyUpload: '#943126',
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

        const chartData = {{ chart_data | safe }};

        Object.keys(chartData).forEach(timeRange => {
            const data = chartData[timeRange];

            new Chart(document.getElementById(`domainChart-${timeRange}`), {
                type: 'bar',
                data: {
                    labels: data.domain.labels,
                    datasets: [{
                        label: '直连下载 (DL)',
                        data: data.domain.directDownload,
                        backgroundColor: chartColors.directDownload,
                    }, {
                        label: '直连上传 (UL)',
                        data: data.domain.directUpload,
                        backgroundColor: chartColors.directUpload,
                    }, {
                        label: '代理下载 (DL)',
                        data: data.domain.proxyDownload,
                        backgroundColor: chartColors.proxyDownload,
                    }, {
                        label: '代理上传 (UL)',
                        data: data.domain.proxyUpload,
                        backgroundColor: chartColors.proxyUpload,
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

            new Chart(document.getElementById(`nodeChart-${timeRange}`), {
                type: 'doughnut',
                data: {
                    labels: data.node.labels,
                    datasets: [{
                        data: data.node.traffic,
                        backgroundColor: data.node.colors
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

            new Chart(document.getElementById(`processChart-${timeRange}`), {
                type: 'bar',
                data: {
                    labels: data.process.labels,
                    datasets: [{
                        label: '直连下载 (DL)',
                        data: data.process.directDownload,
                        backgroundColor: chartColors.directDownload,
                    }, {
                        label: '直连上传 (UL)',
                        data: data.process.directUpload,
                        backgroundColor: chartColors.directUpload,
                    }, {
                        label: '代理下载 (DL)',
                        data: data.process.proxyDownload,
                        backgroundColor: chartColors.proxyDownload,
                    }, {
                        label: '代理上传 (UL)',
                        data: data.process.proxyUpload,
                        backgroundColor: chartColors.proxyUpload,
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
        });

        document.querySelectorAll('.time-tab').forEach(tab => {
            tab.addEventListener('click', function() {
                const range = this.dataset.range;
                
                document.querySelectorAll('.time-tab').forEach(t => t.classList.remove('active'));
                this.classList.add('active');
                
                document.querySelectorAll('.time-range-content').forEach(content => {
                    content.classList.remove('active');
                });
                document.getElementById(`content-${range}`).classList.add('active');
            });
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


def get_time_range_condition(time_range: str) -> tuple:
    now = datetime.now()
    if time_range == "8h":
        start_time = now - timedelta(hours=8)
    elif time_range == "24h":
        start_time = now - timedelta(hours=24)
    elif time_range == "1D":
        start_time = now - timedelta(days=1)
    elif time_range == "1M":
        start_time = now - timedelta(days=30)
    else:
        return "", []

    return "AND start_time >= ?", [int(start_time.timestamp())]


def is_direct(chains_json: str) -> bool:
    try:
        chains = json.loads(chains_json)
        if isinstance(chains, list) and len(chains) > 0:
            return chains[0].upper() == "DIRECT"
        return True
    except (json.JSONDecodeError, TypeError):
        return True


def extract_domain(host: str) -> str:
    if not host:
        return "Unknown"

    parts = host.split(".")

    if len(parts) == 4:
        is_ip = True
        for part in parts:
            if not part.isdigit():
                is_ip = False
                break
            num = int(part)
            if num < 0 or num > 255:
                is_ip = False
                break

        if is_ip:
            return host

    if ":" in host:
        return host

    if len(parts) >= 2:
        return ".".join(parts[-2:])
    return host


def parse_chains_first(chains_json: str) -> str:
    try:
        chains = json.loads(chains_json)
        if isinstance(chains, list) and len(chains) > 0:
            return chains[0]
        return "DIRECT"
    except (json.JSONDecodeError, TypeError):
        return "DIRECT"


def get_overview(conn, time_range: str):
    time_condition, time_params = get_time_range_condition(time_range)

    query = f"SELECT COUNT(*) FROM connections WHERE 1=1 {time_condition}"
    total_connections = conn.execute(query, time_params).fetchone()[0]

    query = f"SELECT COALESCE(SUM(upload), 0), COALESCE(SUM(download), 0) FROM connections WHERE 1=1 {time_condition}"
    upload, download = conn.execute(query, time_params).fetchone()

    query = f"SELECT COUNT(DISTINCT host) FROM connections WHERE host IS NOT NULL AND host != '' {time_condition}"
    unique_hosts = conn.execute(query, time_params).fetchone()[0]

    query = f"SELECT COUNT(DISTINCT process_name) FROM connections WHERE process_name IS NOT NULL AND process_name != '' {time_condition}"
    unique_processes = conn.execute(query, time_params).fetchone()[0]

    return {
        "total_connections": total_connections,
        "total_upload": format_bytes(upload or 0),
        "total_download": format_bytes(download or 0),
        "unique_hosts": unique_hosts,
        "unique_processes": unique_processes,
    }


def get_domain_stats(conn, time_range: str, limit=20):
    time_condition, time_params = get_time_range_condition(time_range)

    query = f"""
        SELECT 
            CASE 
                WHEN host IS NOT NULL AND host != '' THEN host
                WHEN destination_ip IS NOT NULL AND destination_ip != '' THEN destination_ip
                ELSE NULL
            END as host,
            chains,
            SUM(upload) as upload,
            SUM(download) as download
        FROM connections
        WHERE 1=1 {time_condition}
        GROUP BY host, chains
    """
    results = conn.execute(query, time_params).fetchall()

    domain_data = defaultdict(
        lambda: {
            "upload": 0,
            "download": 0,
            "direct_upload": 0,
            "direct_download": 0,
            "proxy_upload": 0,
            "proxy_download": 0,
        }
    )

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

    sorted_domains = sorted(
        domain_data.items(),
        key=lambda x: x[1]["upload"] + x[1]["download"],
        reverse=True,
    )[:limit]

    return {
        "labels": [domain or "Unknown" for domain, data in sorted_domains],
        "directDownload": [data["direct_download"] for domain, data in sorted_domains],
        "proxyDownload": [data["proxy_download"] for domain, data in sorted_domains],
        "directUpload": [data["direct_upload"] for domain, data in sorted_domains],
        "proxyUpload": [data["proxy_upload"] for domain, data in sorted_domains],
    }


def get_node_stats(conn, time_range: str):
    time_condition, time_params = get_time_range_condition(time_range)

    query = f"""
        SELECT 
            chains,
            COUNT(*) as count,
            SUM(upload) + SUM(download) as traffic
        FROM connections
        WHERE 1=1 {time_condition}
        GROUP BY chains
        ORDER BY traffic DESC
    """
    results = conn.execute(query, time_params).fetchall()

    node_data = defaultdict(lambda: {"count": 0, "traffic": 0})
    for row in results:
        chains_json, count, traffic = row
        node_name = parse_chains_first(chains_json)
        node_data[node_name]["count"] += count
        node_data[node_name]["traffic"] += traffic or 0

    sorted_nodes = sorted(
        node_data.items(), key=lambda x: x[1]["traffic"], reverse=True
    )

    red_colors = [
        "#EC7063",
        "#E74C3C",
        "#C0392B",
        "#FF6B6B",
        "#F38181",
        "#FCBAD3",
        "#FFB6B9",
        "#E57373",
        "#EF5350",
        "#F44336",
        "#D32F2F",
        "#C62828",
    ]

    colors = []
    red_index = 0
    for name, data in sorted_nodes:
        if name.upper() == "DIRECT":
            colors.append("#58D68D")
        else:
            colors.append(red_colors[red_index % len(red_colors)])
            red_index += 1

    return {
        "labels": [name for name, data in sorted_nodes],
        "traffic": [data["traffic"] for name, data in sorted_nodes],
        "colors": colors,
    }


def get_process_stats(conn, time_range: str, limit=15):
    time_condition, time_params = get_time_range_condition(time_range)

    query = f"""
        SELECT 
            COALESCE(process_name, 'Unknown') as process,
            chains,
            SUM(upload) as upload,
            SUM(download) as download
        FROM connections
        WHERE 1=1 {time_condition}
        GROUP BY process_name, chains
    """
    results = conn.execute(query, time_params).fetchall()

    process_data = defaultdict(
        lambda: {
            "upload": 0,
            "download": 0,
            "direct_upload": 0,
            "direct_download": 0,
            "proxy_upload": 0,
            "proxy_download": 0,
        }
    )

    for row in results:
        process, chains_json, upload, download = row
        upload = upload or 0
        download = download or 0

        process_data[process]["upload"] += upload
        process_data[process]["download"] += download

        if is_direct(chains_json):
            process_data[process]["direct_upload"] += upload
            process_data[process]["direct_download"] += download
        else:
            process_data[process]["proxy_upload"] += upload
            process_data[process]["proxy_download"] += download

    sorted_processes = sorted(
        process_data.items(),
        key=lambda x: x[1]["upload"] + x[1]["download"],
        reverse=True,
    )[:limit]

    return {
        "labels": [
            process[:20] + "..." if len(process or "") > 20 else (process or "Unknown")
            for process, data in sorted_processes
        ],
        "directDownload": [
            data["direct_download"] for process, data in sorted_processes
        ],
        "proxyDownload": [data["proxy_download"] for process, data in sorted_processes],
        "directUpload": [data["direct_upload"] for process, data in sorted_processes],
        "proxyUpload": [data["proxy_upload"] for process, data in sorted_processes],
    }


def generate_report():
    if not DB_PATH.exists():
        print(f"Database not found: {DB_PATH}")
        return

    conn = get_db_connection()

    try:
        time_ranges = ["8h", "24h", "1D", "1M", "All"]
        overview_data = {}
        chart_data = {}

        for time_range in time_ranges:
            overview_data[time_range] = get_overview(conn, time_range)

            chart_data[time_range] = {
                "domain": get_domain_stats(conn, time_range, 20),
                "node": get_node_stats(conn, time_range),
                "process": get_process_stats(conn, time_range, 15),
            }

        template = Template(HTML_TEMPLATE)
        html = template.render(
            generated_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            time_ranges=time_ranges,
            overview_data=overview_data,
            chart_data=json.dumps(chart_data),
        )

        with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
            f.write(html)

        print(f"Report generated: {OUTPUT_PATH}")

    finally:
        conn.close()


if __name__ == "__main__":
    generate_report()
