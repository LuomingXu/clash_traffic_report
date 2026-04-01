use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct Connections {
    pub download_total: u64,
    pub upload_total: u64,
    pub connections: Option<Vec<Connection>>,
    pub memory: u32,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct Connection {
    pub id: String,
    pub metadata: ConnectionMetaData,
    pub upload: u64,
    pub download: u64,
    pub start: String,
    pub chains: Vec<String>,
    pub rule: String,
    #[serde(default)]
    pub rule_payload: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct ConnectionMetaData {
    pub network: Network,
    #[serde(rename = "type")]
    pub connection_type: ConnectionType,
    #[serde(rename = "sourceIP")]
    pub source_ip: String,
    #[serde(rename = "destinationIP")]
    pub destination_ip: String,
    #[serde(default)]
    pub source_port: String,
    #[serde(default)]
    pub destination_port: String,
    #[serde(rename = "inboundIP")]
    pub inbound_ip: Option<String>,
    pub inbound_port: Option<String>,
    pub inbound_name: String,
    pub inbound_user: String,
    pub host: Option<String>,
    pub dns_mode: Option<DNSMode>,
    pub uid: u32,
    pub process: Option<String>,
    pub process_path: Option<String>,
    pub special_proxy: String,
    pub special_rules: String,
    pub remote_destination: Option<String>,
    pub dscp: u8,
    pub sniff_host: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum Network {
    TCP,
    UDP,
    #[serde(rename = "all")]
    ALLNet,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum ConnectionType {
    HTTP,
    HTTPS,
    #[serde(rename = "Socks4")]
    SOCKS4,
    #[serde(rename = "Socks5")]
    SOCKS5,
    #[serde(rename = "ShadowSocks")]
    SHADOWSOCKS,
    #[serde(rename = "Vmess")]
    VMESS,
    #[serde(rename = "Vless")]
    VLESS,
    #[serde(rename = "Redir")]
    REDIR,
    #[serde(rename = "TProxy")]
    TPROXY,
    #[serde(rename = "Trojan")]
    TROJAN,
    #[serde(rename = "Tunnel")]
    TUNNEL,
    #[serde(rename = "Tun")]
    TUN,
    #[serde(rename = "Tuic")]
    TUIC,
    #[serde(rename = "Hysteria2")]
    HYSTERIA2,
    #[serde(rename = "AnyTLS")]
    ANYTLS,
    #[serde(rename = "Inner")]
    INNER,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum DNSMode {
    #[serde(rename = "normal")]
    Normal,
    #[serde(rename = "fake-ip")]
    FakeIP,
    #[serde(rename = "redir-host")]
    Mapping,
    #[serde(rename = "hosts")]
    Hosts,
}
