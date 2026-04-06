import json
import os
import re
import sqlite3
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path

from jinja2 import Template
from pyinstrument import Profiler

DB_PATH = Path(__file__).parent.parent / "clash_log" / "connections.db"
OUTPUT_PATH = Path(__file__).parent / "index.html"

_executor = None


def get_executor(num_workers=None):
    global _executor
    if _executor is None:
        _executor = ProcessPoolExecutor(
            max_workers=num_workers or (os.cpu_count() or 4)
        )
    return _executor


def shutdown_executor():
    global _executor
    if _executor is not None:
        _executor.shutdown(wait=True)
        _executor = None


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


def parse_chains_in_chunk(chunk):
    result = []
    for row in chunk:
        start_time, host, chains_json, upload, download, process_name = row
        try:
            chains = json.loads(chains_json)
            if isinstance(chains, list) and len(chains) > 0:
                node_name = chains[0]
                is_direct = node_name.upper() == "DIRECT"
            else:
                node_name, is_direct = "DIRECT", True
        except (json.JSONDecodeError, TypeError):
            node_name, is_direct = "DIRECT", True
        result.append(
            (start_time, host, node_name, is_direct, upload, download, process_name)
        )
    return result


IPV4_PATTERN = re.compile(r"^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$")


@lru_cache(maxsize=4096)
def extract_domain(host: str) -> str:
    if not host:
        return "Unknown"

    if ":" in host:
        return host

    if IPV4_PATTERN.match(host):
        return host

    parts = host.split(".")
    if len(parts) >= 2:
        return ".".join(parts[-2:])
    return host


def process_chunk(chunk):
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

    node_data = defaultdict(lambda: {"count": 0, "traffic": 0})

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

    for row in chunk:
        start_time, host, node_name, is_direct, upload, download, process_name = row
        upload = upload or 0
        download = download or 0

        domain = extract_domain(host)
        node_name = node_name or "Unknown"

        domain_data[domain]["upload"] += upload
        domain_data[domain]["download"] += download

        node_data[node_name]["count"] += 1
        node_data[node_name]["traffic"] += upload + download

        process = process_name or "Unknown"
        process_data[process]["upload"] += upload
        process_data[process]["download"] += download

        if is_direct:
            domain_data[domain]["direct_upload"] += upload
            domain_data[domain]["direct_download"] += download
            process_data[process]["direct_upload"] += upload
            process_data[process]["direct_download"] += download
        else:
            domain_data[domain]["proxy_upload"] += upload
            domain_data[domain]["proxy_download"] += download
            process_data[process]["proxy_upload"] += upload
            process_data[process]["proxy_download"] += download

    return dict(domain_data), dict(node_data), dict(process_data)


def fetch_all_data(conn):
    query = """
        SELECT 
            c.start_time,
            COALESCE(h.host, c.destination_ip) as host,
            ch.chains,
            c.upload,
            c.download,
            p.process_name
        FROM connections c
        LEFT JOIN hosts h ON c.host_id = h.id
        LEFT JOIN chains ch ON c.chains_id = ch.id
        LEFT JOIN processes p ON c.process_id = p.id
        ORDER BY c.start_time DESC
    """
    rows = conn.execute(query).fetchall()

    num_workers = min(os.cpu_count() or 4, len(rows))
    if num_workers < 2:
        return parse_chains_in_chunk(rows)

    chunk_size = max(1, len(rows) // num_workers)
    chunks = [rows[i : i + chunk_size] for i in range(0, len(rows), chunk_size)]

    executor = get_executor(num_workers)
    futures = [executor.submit(parse_chains_in_chunk, chunk) for chunk in chunks]

    result = []
    for future in as_completed(futures):
        result.extend(future.result())

    return result


def filter_by_time(data, min_timestamp):
    if min_timestamp == 0:
        return data
    return [row for row in data if row[0] >= min_timestamp]


def calculate_overview(data):
    if not data:
        return {
            "total_connections": 0,
            "total_upload": "0 B",
            "total_download": "0 B",
            "unique_hosts": 0,
            "unique_processes": 0,
        }

    total_upload = 0
    total_download = 0
    unique_hosts = set()
    unique_processes = set()

    for row in data:
        total_upload += row[4] or 0
        total_download += row[5] or 0
        if row[1]:
            unique_hosts.add(row[1])
        if row[6]:
            unique_processes.add(row[6])

    return {
        "total_connections": len(data),
        "total_upload": format_bytes(total_upload),
        "total_download": format_bytes(total_download),
        "unique_hosts": len(unique_hosts),
        "unique_processes": len(unique_processes),
    }


def process_data_single_thread(data, domain_limit=20, process_limit=15):
    if not data:
        return {
            "domain": {
                "labels": [],
                "directDownload": [],
                "proxyDownload": [],
                "directUpload": [],
                "proxyUpload": [],
            },
            "node": {"labels": [], "traffic": [], "colors": []},
            "process": {
                "labels": [],
                "directDownload": [],
                "proxyDownload": [],
                "directUpload": [],
                "proxyUpload": [],
            },
        }

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

    node_data = defaultdict(lambda: {"count": 0, "traffic": 0})

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

    for row in data:
        start_time, host, node_name, is_direct, upload, download, process_name = row
        upload = upload or 0
        download = download or 0

        domain = extract_domain(host)
        node_name = node_name or "Unknown"

        domain_data[domain]["upload"] += upload
        domain_data[domain]["download"] += download

        node_data[node_name]["count"] += 1
        node_data[node_name]["traffic"] += upload + download

        process = process_name or "Unknown"
        process_data[process]["upload"] += upload
        process_data[process]["download"] += download

        if is_direct:
            domain_data[domain]["direct_upload"] += upload
            domain_data[domain]["direct_download"] += download
            process_data[process]["direct_upload"] += upload
            process_data[process]["direct_download"] += download
        else:
            domain_data[domain]["proxy_upload"] += upload
            domain_data[domain]["proxy_download"] += download
            process_data[process]["proxy_upload"] += upload
            process_data[process]["proxy_download"] += download

    sorted_domains = sorted(
        domain_data.items(),
        key=lambda x: x[1]["upload"] + x[1]["download"],
        reverse=True,
    )[:domain_limit]

    sorted_nodes = sorted(
        node_data.items(), key=lambda x: x[1]["traffic"], reverse=True
    )

    sorted_processes = sorted(
        process_data.items(),
        key=lambda x: x[1]["upload"] + x[1]["download"],
        reverse=True,
    )[:process_limit]

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

    node_colors = []
    red_index = 0
    for name, data_dict in sorted_nodes:
        if name.upper() == "DIRECT":
            node_colors.append("#58D68D")
        else:
            node_colors.append(red_colors[red_index % len(red_colors)])
            red_index += 1

    return {
        "domain": {
            "labels": [domain or "Unknown" for domain, data_dict in sorted_domains],
            "directDownload": [
                data_dict["direct_download"] for domain, data_dict in sorted_domains
            ],
            "proxyDownload": [
                data_dict["proxy_download"] for domain, data_dict in sorted_domains
            ],
            "directUpload": [
                data_dict["direct_upload"] for domain, data_dict in sorted_domains
            ],
            "proxyUpload": [
                data_dict["proxy_upload"] for domain, data_dict in sorted_domains
            ],
        },
        "node": {
            "labels": [name for name, data_dict in sorted_nodes],
            "traffic": [data_dict["traffic"] for name, data_dict in sorted_nodes],
            "colors": node_colors,
        },
        "process": {
            "labels": [
                process[:20] + "..."
                if len(process or "") > 20
                else (process or "Unknown")
                for process, data_dict in sorted_processes
            ],
            "directDownload": [
                data_dict["direct_download"] for process, data_dict in sorted_processes
            ],
            "proxyDownload": [
                data_dict["proxy_download"] for process, data_dict in sorted_processes
            ],
            "directUpload": [
                data_dict["direct_upload"] for process, data_dict in sorted_processes
            ],
            "proxyUpload": [
                data_dict["proxy_upload"] for process, data_dict in sorted_processes
            ],
        },
    }


def process_data_with_multiprocessing(data, domain_limit=20, process_limit=15):
    if not data:
        return {
            "domain": {
                "labels": [],
                "directDownload": [],
                "proxyDownload": [],
                "directUpload": [],
                "proxyUpload": [],
            },
            "node": {"labels": [], "traffic": [], "colors": []},
            "process": {
                "labels": [],
                "directDownload": [],
                "proxyDownload": [],
                "directUpload": [],
                "proxyUpload": [],
            },
        }

    num_workers = min(os.cpu_count() or 4, len(data))
    if num_workers < 2:
        chunks = [data]
    else:
        chunk_size = max(1, len(data) // num_workers)
        chunks = [data[i : i + chunk_size] for i in range(0, len(data), chunk_size)]

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

    node_data = defaultdict(lambda: {"count": 0, "traffic": 0})

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

    executor = get_executor(num_workers)
    futures = [executor.submit(process_chunk, chunk) for chunk in chunks]

    for future in as_completed(futures):
        chunk_domain, chunk_node, chunk_process = future.result()

        for domain, data_dict in chunk_domain.items():
            domain_data[domain]["upload"] += data_dict["upload"]
            domain_data[domain]["download"] += data_dict["download"]
            domain_data[domain]["direct_upload"] += data_dict["direct_upload"]
            domain_data[domain]["direct_download"] += data_dict["direct_download"]
            domain_data[domain]["proxy_upload"] += data_dict["proxy_upload"]
            domain_data[domain]["proxy_download"] += data_dict["proxy_download"]

        for node, data_dict in chunk_node.items():
            node_data[node]["count"] += data_dict["count"]
            node_data[node]["traffic"] += data_dict["traffic"]

        for process, data_dict in chunk_process.items():
            process_data[process]["upload"] += data_dict["upload"]
            process_data[process]["download"] += data_dict["download"]
            process_data[process]["direct_upload"] += data_dict["direct_upload"]
            process_data[process]["direct_download"] += data_dict["direct_download"]
            process_data[process]["proxy_upload"] += data_dict["proxy_upload"]
            process_data[process]["proxy_download"] += data_dict["proxy_download"]

    sorted_domains = sorted(
        domain_data.items(),
        key=lambda x: x[1]["upload"] + x[1]["download"],
        reverse=True,
    )[:domain_limit]

    sorted_nodes = sorted(
        node_data.items(), key=lambda x: x[1]["traffic"], reverse=True
    )

    sorted_processes = sorted(
        process_data.items(),
        key=lambda x: x[1]["upload"] + x[1]["download"],
        reverse=True,
    )[:process_limit]

    red_colors = [
        "#EC7063", "#E74C3C", "#C0392B", "#FF6B6B",
        "#F38181", "#FCBAD3", "#FFB6B9", "#E57373",
        "#EF5350", "#F44336", "#D32F2F", "#C62828",
    ]

    node_colors = []
    red_index = 0
    for name, data_dict in sorted_nodes:
        if name.upper() == "DIRECT":
            node_colors.append("#58D68D")
        else:
            node_colors.append(red_colors[red_index % len(red_colors)])
            red_index += 1

    return {
        "domain": {
            "labels": [domain or "Unknown" for domain, data_dict in sorted_domains],
            "directDownload": [
                data_dict["direct_download"] for domain, data_dict in sorted_domains
            ],
            "proxyDownload": [
                data_dict["proxy_download"] for domain, data_dict in sorted_domains
            ],
            "directUpload": [
                data_dict["direct_upload"] for domain, data_dict in sorted_domains
            ],
            "proxyUpload": [
                data_dict["proxy_upload"] for domain, data_dict in sorted_domains
            ],
        },
        "node": {
            "labels": [name for name, data_dict in sorted_nodes],
            "traffic": [data_dict["traffic"] for name, data_dict in sorted_nodes],
            "colors": node_colors,
        },
        "process": {
            "labels": [
                process[:20] + "..."
                if len(process or "") > 20
                else (process or "Unknown")
                for process, data_dict in sorted_processes
            ],
            "directDownload": [
                data_dict["direct_download"] for process, data_dict in sorted_processes
            ],
            "proxyDownload": [
                data_dict["proxy_download"] for process, data_dict in sorted_processes
            ],
            "directUpload": [
                data_dict["direct_upload"] for process, data_dict in sorted_processes
            ],
            "proxyUpload": [
                data_dict["proxy_upload"] for process, data_dict in sorted_processes
            ],
        },
    }


def generate_report():
    if not DB_PATH.exists():
        print(f"Database not found: {DB_PATH}")
        return

    conn = get_db_connection()

    try:
        print("Fetching all data from database...")
        all_data = fetch_all_data(conn)
        print(f"Total records: {len(all_data)}")

        now = datetime.now()
        time_thresholds = {
            "All": 0,
            "1M": int((now - timedelta(days=30)).timestamp()),
            "1D": int((now - timedelta(days=1)).timestamp()),
            "24h": int((now - timedelta(hours=24)).timestamp()),
            "8h": int((now - timedelta(hours=8)).timestamp()),
        }

        time_ranges = ["8h", "24h", "1D", "1M", "All"]
        overview_data = {}
        chart_data = {}

        print("Processing All...")
        filtered_all = all_data
        overview_data["All"] = calculate_overview(filtered_all)
        chart_data["All"] = process_data_with_multiprocessing(filtered_all, 20, 15)

        print("Processing 1M...")
        filtered_1m = filter_by_time(all_data, time_thresholds["1M"])
        overview_data["1M"] = calculate_overview(filtered_1m)
        chart_data["1M"] = process_data_with_multiprocessing(filtered_1m, 20, 15)

        print("Processing 1D...")
        filtered_1d = filter_by_time(filtered_1m, time_thresholds["1D"])
        overview_data["1D"] = calculate_overview(filtered_1d)
        chart_data["1D"] = process_data_single_thread(filtered_1d, 20, 15)

        print("Processing 24h...")
        filtered_24h = filter_by_time(filtered_1d, time_thresholds["24h"])
        overview_data["24h"] = calculate_overview(filtered_24h)
        chart_data["24h"] = process_data_single_thread(filtered_24h, 20, 15)

        print("Processing 8h...")
        filtered_8h = filter_by_time(filtered_24h, time_thresholds["8h"])
        overview_data["8h"] = calculate_overview(filtered_8h)
        chart_data["8h"] = process_data_single_thread(filtered_8h, 20, 15)
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
        shutdown_executor()


if __name__ == "__main__":
    profiler = Profiler()
    profiler.start()
    generate_report()
    profiler.stop()
    profiler.print(show_all=True)
