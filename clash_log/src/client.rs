use crate::error::{Error, Result};
use crate::models::Connections;
use crate::storage::Database;
use futures_util::StreamExt;
use std::collections::HashMap;
use std::sync::Arc;
use tokio::net::windows::named_pipe::ClientOptions;
use tokio_tungstenite::tungstenite::protocol::WebSocketConfig;
use tokio_tungstenite::tungstenite::http::Request;
use tokio_tungstenite::WebSocketStream;
use tokio_tungstenite::{client_async, tungstenite};

#[cfg(unix)]
use tokio::net::UnixStream;

pub struct ClashClient {
    socket_path: String,
    db: Arc<Database>,
}

impl ClashClient {
    pub fn new(socket_path: String, db: Arc<Database>) -> Self {
        ClashClient { socket_path, db }
    }
    
    pub async fn connect_and_monitor(&self) -> Result<()> {
        let mut reconnect_attempts = 0;
        
        loop {
            match self.connect_websocket().await {
                Ok(ws_stream) => {
                    reconnect_attempts = 0;
                    log::info!("WebSocket connected successfully");
                    
                    if let Err(e) = self.handle_messages(ws_stream).await {
                        log::error!("WebSocket error: {}", e);
                    }
                }
                Err(e) => {
                    log::error!("Failed to connect: {}", e);
                }
            }
            
            reconnect_attempts += 1;
            log::warn!(
                "Connection lost. Reconnect attempt {} in 5 seconds...",
                reconnect_attempts
            );
            
            tokio::time::sleep(std::time::Duration::from_secs(5)).await;
        }
    }
    
    async fn connect_websocket(&self) -> Result<WebSocketStream<WrapStream>> {
        let stream = self.connect_pipe().await?;
        
        let request = Request::builder()
            .uri("ws://localhost/connections")
            .header("Host", "clash-verge")
            .header("Connection", "Upgrade")
            .header("Upgrade", "websocket")
            .header("Sec-WebSocket-Version", "13")
            .header(
                "Sec-WebSocket-Key",
                tungstenite::handshake::client::generate_key(),
            )
            .body(())
            .map_err(|e| Error::Http(format!("Failed to build request: {}", e)))?;
        
        let ws_config = WebSocketConfig::default();
        let (ws_stream, _) = client_async(request, stream)
            .await
            .map_err(|e| Error::WebSocket(format!("WebSocket handshake failed: {}", e)))?;
        
        Ok(ws_stream)
    }
    
    #[cfg(windows)]
    async fn connect_pipe(&self) -> Result<WrapStream> {
        let client = ClientOptions::new()
            .open(&self.socket_path)
            .map_err(|e| Error::Io(e))?;
        
        Ok(WrapStream::NamedPipe(client))
    }
    
    #[cfg(unix)]
    async fn connect_pipe(&self) -> Result<WrapStream> {
        let stream = UnixStream::connect(&self.socket_path).await?;
        Ok(WrapStream::Unix(stream))
    }
    
    async fn handle_messages(&self, mut ws_stream: WebSocketStream<WrapStream>) -> Result<()> {
        let mut active_connections: HashMap<String, crate::models::Connection> = HashMap::new();
        
        while let Some(message) = ws_stream.next().await {
            match message {
                Ok(msg) => {
                    if msg.is_text() {
                        let text = msg.to_text()
                            .map_err(|e| Error::WebSocket(format!("Failed to parse message: {}", e)))?;
                        
                        match serde_json::from_str::<Connections>(text) {
                            Ok(connections) => {
                                self.process_connections(&mut active_connections, connections).await?;
                            }
                            Err(e) => {
                                log::error!("Failed to parse connections: {}", e);
                            }
                        }
                    }
                }
                Err(e) => {
                    log::error!("WebSocket error: {}", e);
                    return Err(Error::WebSocket(format!("Stream error: {}", e)));
                }
            }
        }
        
        Ok(())
    }
    
    async fn process_connections(
        &self,
        active_connections: &mut HashMap<String, crate::models::Connection>,
        connections: Connections,
    ) -> Result<()> {
        let current_ids: std::collections::HashSet<String> = connections
            .connections
            .as_ref()
            .map(|conns| conns.iter().map(|c| c.id.clone()).collect())
            .unwrap_or_default();
        
        if let Some(conns) = connections.connections {
            for conn in conns {
                if !active_connections.contains_key(&conn.id) {
                    log::debug!("New connection: {} -> {}", conn.metadata.process.as_ref().unwrap_or(&"unknown".to_string()), conn.metadata.host.as_ref().unwrap_or(&"unknown".to_string()));
                    self.db.insert_connection(&conn).await?;
                } else {
                    let old_conn = active_connections.get(&conn.id).unwrap();
                    if connection_data_changed(old_conn, &conn) {
                        self.db.update_connection(&conn).await?;
                    }
                }
                
                active_connections.insert(conn.id.clone(), conn);
            }
        }
        
        let closed_ids: Vec<String> = active_connections
            .keys()
            .filter(|id| !current_ids.contains(*id))
            .cloned()
            .collect();
        
        for id in closed_ids {
            active_connections.remove(&id);
            log::debug!("Connection closed: {}", id);
        }
        
        if !active_connections.is_empty() {
            let active_conns: Vec<crate::models::Connection> = active_connections.values().cloned().collect();
            self.db.update_process_statistics(&active_conns).await?;
        }
        
        Ok(())
    }
}

fn connection_data_changed(old: &crate::models::Connection, new: &crate::models::Connection) -> bool {
    old.upload != new.upload
        || old.download != new.download
        || old.rule != new.rule
        || old.rule_payload != new.rule_payload
        || old.chains != new.chains
}

#[cfg(windows)]
pub enum WrapStream {
    NamedPipe(tokio::net::windows::named_pipe::NamedPipeClient),
}

#[cfg(unix)]
pub enum WrapStream {
    Unix(tokio::net::UnixStream),
}

#[cfg(windows)]
impl tokio::io::AsyncRead for WrapStream {
    fn poll_read(
        self: std::pin::Pin<&mut Self>,
        cx: &mut std::task::Context<'_>,
        buf: &mut tokio::io::ReadBuf<'_>,
    ) -> std::task::Poll<std::io::Result<()>> {
        match self.get_mut() {
            WrapStream::NamedPipe(pipe) => std::pin::Pin::new(pipe).poll_read(cx, buf),
        }
    }
}

#[cfg(windows)]
impl tokio::io::AsyncWrite for WrapStream {
    fn poll_write(
        self: std::pin::Pin<&mut Self>,
        cx: &mut std::task::Context<'_>,
        buf: &[u8],
    ) -> std::task::Poll<std::io::Result<usize>> {
        match self.get_mut() {
            WrapStream::NamedPipe(pipe) => std::pin::Pin::new(pipe).poll_write(cx, buf),
        }
    }
    
    fn poll_flush(
        self: std::pin::Pin<&mut Self>,
        cx: &mut std::task::Context<'_>,
    ) -> std::task::Poll<std::io::Result<()>> {
        match self.get_mut() {
            WrapStream::NamedPipe(pipe) => std::pin::Pin::new(pipe).poll_flush(cx),
        }
    }
    
    fn poll_shutdown(
        self: std::pin::Pin<&mut Self>,
        cx: &mut std::task::Context<'_>,
    ) -> std::task::Poll<std::io::Result<()>> {
        match self.get_mut() {
            WrapStream::NamedPipe(pipe) => std::pin::Pin::new(pipe).poll_shutdown(cx),
        }
    }
}

#[cfg(unix)]
impl tokio::io::AsyncRead for WrapStream {
    fn poll_read(
        self: std::pin::Pin<&mut Self>,
        cx: &mut std::task::Context<'_>,
        buf: &mut tokio::io::ReadBuf<'_>,
    ) -> std::task::Poll<std::io::Result<()>> {
        match self.get_mut() {
            WrapStream::Unix(stream) => std::pin::Pin::new(stream).poll_read(cx, buf),
        }
    }
}

#[cfg(unix)]
impl tokio::io::AsyncWrite for WrapStream {
    fn poll_write(
        self: std::pin::Pin<&mut Self>,
        cx: &mut std::task::Context<'_>,
        buf: &[u8],
    ) -> std::task::Poll<std::io::Result<usize>> {
        match self.get_mut() {
            WrapStream::Unix(stream) => std::pin::Pin::new(stream).poll_write(cx, buf),
        }
    }
    
    fn poll_flush(
        self: std::pin::Pin<&mut Self>,
        cx: &mut std::task::Context<'_>,
    ) -> std::task::Poll<std::io::Result<()>> {
        match self.get_mut() {
            WrapStream::Unix(stream) => std::pin::Pin::new(stream).poll_flush(cx),
        }
    }
    
    fn poll_shutdown(
        self: std::pin::Pin<&mut Self>,
        cx: &mut std::task::Context<'_>,
    ) -> std::task::Poll<std::io::Result<()>> {
        match self.get_mut() {
            WrapStream::Unix(stream) => std::pin::Pin::new(stream).poll_shutdown(cx),
        }
    }
}
