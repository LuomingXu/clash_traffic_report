mod error;
mod config;
mod models;
mod storage;
mod client;

pub use error::{Error, Result};

use std::sync::Arc;

#[tokio::main]
async fn main() {
    env_logger::Builder::from_env(env_logger::Env::default().default_filter_or("info")).init();
    
    log::info!("Starting Clash Connection Monitor...");
    
    let config = match config::Config::load_from_file("config.toml") {
        Ok(cfg) => cfg,
        Err(e) => {
            log::warn!("Failed to load config file: {}. Using default config.", e);
            config::Config::default()
        }
    };
    
    log::info!("Socket path: {}", config.get_socket_path());
    log::info!("Database path: {}", config.get_database_path());
    
    let db = match storage::Database::new(config.get_database_path()) {
        Ok(db) => Arc::new(db),
        Err(e) => {
            log::error!("Failed to initialize database: {}", e);
            std::process::exit(1);
        }
    };
    
    log::info!("Database initialized successfully");
    
    let client = client::ClashClient::new(
        config.get_socket_path().to_string(),
        db,
    );
    
    log::info!("Connecting to Clash...");
    
    if let Err(e) = client.connect_and_monitor().await {
        log::error!("Monitor error: {}", e);
        std::process::exit(1);
    }
}
