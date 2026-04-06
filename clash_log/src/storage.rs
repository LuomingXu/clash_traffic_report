use crate::error::Result;
use crate::models::Connection as Conn;
use rusqlite::Connection as SqliteConnection;
use std::sync::Mutex;
use std::sync::Arc;
use std::time::Instant;
use time::OffsetDateTime;

pub struct Database {
    conn: Arc<Mutex<SqliteConnection>>,
    last_stats_update: Mutex<Instant>,
}

impl Database {
    pub fn new(path: &str) -> Result<Self> {
        let conn = SqliteConnection::open(path)?;
        
        conn.execute_batch(
            r#"
            CREATE TABLE IF NOT EXISTS processes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                process_name TEXT NOT NULL,
                process_path TEXT,
                UNIQUE(process_name, process_path)
            );
            
            CREATE INDEX IF NOT EXISTS idx_processes_name ON processes(process_name);
            
            CREATE TABLE IF NOT EXISTS source_ips (
                id INTEGER PRIMARY KEY,
                ip TEXT NOT NULL UNIQUE
            );
            
            CREATE TABLE IF NOT EXISTS hosts (
                id INTEGER PRIMARY KEY,
                host TEXT NOT NULL UNIQUE
            );
            
            CREATE TABLE IF NOT EXISTS chains (
                id INTEGER PRIMARY KEY,
                chains TEXT NOT NULL UNIQUE
            );
            
            CREATE TABLE IF NOT EXISTS connections (
                id TEXT PRIMARY KEY,
                start_time INTEGER NOT NULL,
                network TEXT NOT NULL,
                connection_type TEXT NOT NULL,
                source_ip_id INTEGER REFERENCES source_ips(id),
                destination_ip TEXT NOT NULL,
                host_id INTEGER REFERENCES hosts(id),
                chains_id INTEGER NOT NULL REFERENCES chains(id),
                rule TEXT,
                rule_payload TEXT,
                upload INTEGER NOT NULL DEFAULT 0,
                download INTEGER NOT NULL DEFAULT 0,
                process_id INTEGER REFERENCES processes(id)
            );
            
            CREATE INDEX IF NOT EXISTS idx_connections_start_time ON connections(start_time);
            CREATE INDEX IF NOT EXISTS idx_connections_destination_ip ON connections(destination_ip);
            CREATE INDEX IF NOT EXISTS idx_connections_host_id ON connections(host_id);
            CREATE INDEX IF NOT EXISTS idx_connections_chains_id ON connections(chains_id);
            CREATE INDEX IF NOT EXISTS idx_connections_process_id ON connections(process_id);
            
            CREATE TABLE IF NOT EXISTS process_statistics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                process_id INTEGER NOT NULL,
                connection_count INTEGER NOT NULL,
                total_upload INTEGER NOT NULL,
                total_download INTEGER NOT NULL,
                FOREIGN KEY (process_id) REFERENCES processes(id),
                UNIQUE(date, process_id)
            );
            
            CREATE INDEX IF NOT EXISTS idx_process_statistics_date_process ON process_statistics(date, process_id);
            "#,
        )?;
        
        let db = Database {
            conn: Arc::new(Mutex::new(conn)),
            last_stats_update: Mutex::new(Instant::now()),
        };
        
        db.cleanup_old_data()?;
        
        Ok(db)
    }
    
    fn cleanup_old_data(&self) -> Result<()> {
        let db = self.conn.lock().unwrap();
        let ninety_days_ago = (OffsetDateTime::now_utc() - time::Duration::days(90)).unix_timestamp();
        
        db.execute(
            "DELETE FROM connections WHERE start_time < ?1",
            rusqlite::params![ninety_days_ago],
        )?;
        
        db.execute(
            "DELETE FROM process_statistics WHERE date < date('now', '-90 days')",
            rusqlite::params![],
        )?;
        
        log::info!("已清理 90 天前的旧数据");
        
        Ok(())
    }
    
    pub async fn insert_connection(&self, conn: &Conn) -> Result<()> {
        let db = self.conn.clone();
        let conn_data = conn.clone();
        
        tokio::task::spawn_blocking(move || {
            let db = db.lock().unwrap();
            let start_time = parse_connection_time(&conn_data.start);
            
            let process_id = if let Some(process_name) = &conn_data.metadata.process {
                Some(get_or_create_process(
                    &db,
                    process_name,
                    conn_data.metadata.process_path.as_deref(),
                )?)
            } else {
                None
            };
            
            let source_ip_id = get_or_create_source_ip(&db, &conn_data.metadata.source_ip)?;
            
            let host_id = if let Some(host) = &conn_data.metadata.host {
                if !host.is_empty() {
                    Some(get_or_create_host(&db, host)?)
                } else {
                    None
                }
            } else {
                None
            };
            
            let chains_json = serde_json::to_string(&conn_data.chains).unwrap_or_default();
            let chains_id = get_or_create_chains(&db, &chains_json)?;
            
            db.execute(
                "INSERT OR REPLACE INTO connections (
                    id, start_time,
                    network, connection_type,
                    source_ip_id, destination_ip,
                    host_id, chains_id,
                    rule, rule_payload, upload, download,
                    process_id
                ) VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11, ?12, ?13)",
                rusqlite::params![
                    conn_data.id,
                    start_time,
                    format!("{:?}", conn_data.metadata.network),
                    format!("{:?}", conn_data.metadata.connection_type),
                    source_ip_id,
                    conn_data.metadata.destination_ip,
                    host_id,
                    chains_id,
                    if conn_data.rule.is_empty() { None } else { Some(&conn_data.rule) },
                    if conn_data.rule_payload.is_empty() { None } else { Some(&conn_data.rule_payload) },
                    conn_data.upload as i64,
                    conn_data.download as i64,
                    process_id,
                ],
            )?;
            
            Ok::<_, crate::Error>(())
        }).await??;
        
        Ok(())
    }
    
    pub async fn update_connection(&self, conn: &Conn) -> Result<()> {
        let db = self.conn.clone();
        let conn_data = conn.clone();
        
        tokio::task::spawn_blocking(move || {
            let db = db.lock().unwrap();
            
            let chains_json = serde_json::to_string(&conn_data.chains).unwrap_or_default();
            let chains_id = get_or_create_chains(&db, &chains_json)?;
            
            db.execute(
                "UPDATE connections SET 
                    upload = ?1, 
                    download = ?2, 
                    chains_id = ?3,
                    rule = ?4,
                    rule_payload = ?5
                WHERE id = ?6",
                rusqlite::params![
                    conn_data.upload as i64,
                    conn_data.download as i64,
                    chains_id,
                    if conn_data.rule.is_empty() { None } else { Some(&conn_data.rule) },
                    if conn_data.rule_payload.is_empty() { None } else { Some(&conn_data.rule_payload) },
                    conn_data.id,
                ],
            )?;
            
            Ok::<_, crate::Error>(())
        }).await??;
        
        Ok(())
    }
    
    pub async fn update_process_statistics(&self, connections: &[Conn]) -> Result<()> {
        let should_update = {
            let last_update = self.last_stats_update.lock().unwrap();
            last_update.elapsed().as_secs() >= 60
        };
        
        if !should_update {
            return Ok(());
        }
        
        {
            let mut last_update = self.last_stats_update.lock().unwrap();
            *last_update = Instant::now();
        }
        
        let db = self.conn.clone();
        let connections = connections.to_vec();
        
        tokio::task::spawn_blocking(move || {
            let db = db.lock().unwrap();
            let today = OffsetDateTime::now_utc().date().to_string();
            
            let mut process_stats: std::collections::HashMap<String, (Option<String>, u64, u64, u64)> = std::collections::HashMap::new();
            
            for conn in connections.iter() {
                if let Some(process) = &conn.metadata.process {
                    let entry = process_stats.entry(process.clone()).or_insert((
                        conn.metadata.process_path.clone(),
                        0,
                        0,
                        0,
                    ));
                    entry.1 += 1;
                    entry.2 += conn.upload;
                    entry.3 += conn.download;
                }
            }
            
            for (process, (path, count, upload, download)) in process_stats.iter() {
                let process_id = get_or_create_process(&db, process, path.as_deref())?;
                
                db.execute(
                    "INSERT INTO process_statistics (date, process_id, connection_count, total_upload, total_download) VALUES (?1, ?2, ?3, ?4, ?5)
                     ON CONFLICT(date, process_id) DO UPDATE SET
                     connection_count = connection_count + excluded.connection_count,
                     total_upload = total_upload + excluded.total_upload,
                     total_download = total_download + excluded.total_download",
                    rusqlite::params![
                        today,
                        process_id,
                        *count as i64,
                        *upload as i64,
                        *download as i64,
                    ],
                )?;
            }
            
            Ok::<_, crate::Error>(())
        }).await??;
        
        Ok(())
    }
}

fn parse_connection_time(time_str: &str) -> i64 {
    OffsetDateTime::parse(time_str, &time::format_description::well_known::Rfc3339)
        .map(|dt| dt.unix_timestamp())
        .unwrap_or_else(|_| OffsetDateTime::now_utc().unix_timestamp())
}

fn get_or_create_process(
    db: &SqliteConnection,
    process_name: &str,
    process_path: Option<&str>,
) -> rusqlite::Result<i64> {
    let mut stmt = db.prepare("SELECT id FROM processes WHERE process_name = ?1 AND process_path IS ?2")?;
    let mut rows = stmt.query(rusqlite::params![process_name, process_path])?;
    
    if let Some(row) = rows.next()? {
        return Ok(row.get(0)?);
    }
    
    db.execute(
        "INSERT INTO processes (process_name, process_path) VALUES (?1, ?2)",
        rusqlite::params![process_name, process_path],
    )?;
    
    Ok(db.last_insert_rowid())
}

fn get_or_create_source_ip(
    db: &SqliteConnection,
    ip: &str,
) -> rusqlite::Result<i64> {
    let mut stmt = db.prepare("SELECT id FROM source_ips WHERE ip = ?1")?;
    let mut rows = stmt.query(rusqlite::params![ip])?;
    
    if let Some(row) = rows.next()? {
        return Ok(row.get(0)?);
    }
    
    db.execute(
        "INSERT INTO source_ips (ip) VALUES (?1)",
        rusqlite::params![ip],
    )?;
    
    Ok(db.last_insert_rowid())
}

fn get_or_create_host(
    db: &SqliteConnection,
    host: &str,
) -> rusqlite::Result<i64> {
    let mut stmt = db.prepare("SELECT id FROM hosts WHERE host = ?1")?;
    let mut rows = stmt.query(rusqlite::params![host])?;
    
    if let Some(row) = rows.next()? {
        return Ok(row.get(0)?);
    }
    
    db.execute(
        "INSERT INTO hosts (host) VALUES (?1)",
        rusqlite::params![host],
    )?;
    
    Ok(db.last_insert_rowid())
}

fn get_or_create_chains(
    db: &SqliteConnection,
    chains: &str,
) -> rusqlite::Result<i64> {
    let mut stmt = db.prepare("SELECT id FROM chains WHERE chains = ?1")?;
    let mut rows = stmt.query(rusqlite::params![chains])?;
    
    if let Some(row) = rows.next()? {
        return Ok(row.get(0)?);
    }
    
    db.execute(
        "INSERT INTO chains (chains) VALUES (?1)",
        rusqlite::params![chains],
    )?;
    
    Ok(db.last_insert_rowid())
}
