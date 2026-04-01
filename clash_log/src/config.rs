use serde::Deserialize;

#[derive(Debug, Deserialize)]
pub struct Config {
    pub clash: ClashConfig,
    pub database: DatabaseConfig,
    pub monitor: MonitorConfig,
}

#[derive(Debug, Deserialize)]
pub struct ClashConfig {
    pub socket_path: String,
}

#[derive(Debug, Deserialize)]
pub struct DatabaseConfig {
    pub path: String,
}

#[derive(Debug, Deserialize)]
pub struct MonitorConfig {
    #[serde(default = "default_statistics_interval")]
    pub statistics_interval_secs: u64,
    #[serde(default = "default_reconnect_interval")]
    pub reconnect_interval_secs: u64,
    #[serde(default = "default_max_reconnect_attempts")]
    pub max_reconnect_attempts: u32,
}

fn default_statistics_interval() -> u64 {
    60
}

fn default_reconnect_interval() -> u64 {
    5
}

fn default_max_reconnect_attempts() -> u32 {
    10
}

impl Config {
    pub fn load_from_file(path: &str) -> crate::Result<Self> {
        let content = std::fs::read_to_string(path)
            .map_err(|e| crate::Error::Config(format!("Failed to read config file: {}", e)))?;
        
        toml::from_str(&content)
            .map_err(|e| crate::Error::Config(format!("Failed to parse config: {}", e)))
    }
    
    pub fn get_socket_path(&self) -> &str {
        &self.clash.socket_path
    }
    
    pub fn get_database_path(&self) -> &str {
        &self.database.path
    }
    
    pub fn get_statistics_interval(&self) -> std::time::Duration {
        std::time::Duration::from_secs(self.monitor.statistics_interval_secs)
    }
    
    pub fn get_reconnect_interval(&self) -> std::time::Duration {
        std::time::Duration::from_secs(self.monitor.reconnect_interval_secs)
    }
    
    pub fn get_max_reconnect_attempts(&self) -> u32 {
        self.monitor.max_reconnect_attempts
    }
}

impl Default for Config {
    fn default() -> Self {
        let socket_path = if cfg!(windows) {
            r"\\.\pipe\verge-mihomo".to_string()
        } else {
            "/tmp/verge-mihomo.sock".to_string()
        };
        
        Config {
            clash: ClashConfig {
                socket_path,
            },
            database: DatabaseConfig {
                path: "./connections.db".to_string(),
            },
            monitor: MonitorConfig {
                statistics_interval_secs: 60,
                reconnect_interval_secs: 5,
                max_reconnect_attempts: 10,
            },
        }
    }
}
