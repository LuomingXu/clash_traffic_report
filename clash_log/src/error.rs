pub type Result<T> = std::result::Result<T, Error>;

#[derive(Debug, thiserror::Error)]
pub enum Error {
    #[error("I/O error: {0}")]
    Io(#[from] std::io::Error),
    
    #[error("WebSocket error: {0}")]
    WebSocket(String),
    
    #[error("Database error: {0}")]
    Database(#[from] rusqlite::Error),
    
    #[error("JSON parse error: {0}")]
    Json(#[from] serde_json::Error),
    
    #[error("Config error: {0}")]
    Config(String),
    
    #[error("HTTP error: {0}")]
    Http(String),
    
    #[error("Task join error: {0}")]
    Join(#[from] tokio::task::JoinError),
}
