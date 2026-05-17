#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use futures_util::stream::SplitSink;
use futures_util::{SinkExt, StreamExt};
use serde::Serialize;
use serde_json::json;
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::{Arc, Mutex};
use tauri::{AppHandle, Emitter, Manager, State};
use tokio::net::TcpStream;
use tokio::sync::Mutex as AsyncMutex;
use tokio::time::{sleep, Duration};
use tokio_tungstenite::tungstenite::Message;
use tokio_tungstenite::{connect_async, MaybeTlsStream, WebSocketStream};

const WS_URL: &str = "ws://127.0.0.1:9741";
type WsWrite = SplitSink<WebSocketStream<MaybeTlsStream<TcpStream>>, Message>;

struct PythonSidecar {
    child: Mutex<Option<Child>>,
}

#[derive(Clone)]
struct WebSocketBridge {
    write: Arc<AsyncMutex<Option<WsWrite>>>,
}

impl Drop for PythonSidecar {
    fn drop(&mut self) {
        if let Ok(mut guard) = self.child.lock() {
            if let Some(child) = guard.as_mut() {
                let _ = child.kill();
            }
        }
    }
}

#[derive(Serialize)]
struct CommandAck {
    queued: bool,
}

fn looks_like_project_root(path: &Path) -> bool {
    let unix_py = path.join(".venv").join("bin").join("python");
    let win_py = path.join(".venv").join("Scripts").join("python.exe");
    (unix_py.exists() || win_py.exists()) && path.join("src").join("inercia").exists()
}

fn walk_for_project_root(start: &Path) -> Option<PathBuf> {
    let mut current = Some(start);
    while let Some(path) = current {
        if looks_like_project_root(path) {
            return Some(path.to_path_buf());
        }
        current = path.parent();
    }
    None
}

fn resolve_project_root(app: &AppHandle) -> Result<PathBuf, String> {
    let mut candidates: Vec<PathBuf> = Vec::new();
    if let Ok(resource_dir) = app.path().resource_dir() {
        candidates.push(resource_dir);
    }
    if let Ok(current_exe) = std::env::current_exe() {
        if let Some(parent) = current_exe.parent() {
            candidates.push(parent.to_path_buf());
        }
    }
    if let Ok(current_dir) = std::env::current_dir() {
        candidates.push(current_dir);
    }
    for candidate in candidates {
        if let Some(root) = walk_for_project_root(&candidate) {
            return Ok(root);
        }
    }
    Err(String::from(
        "failed to locate Inercia project root with .venv and src/inercia",
    ))
}

fn spawn_python_api(app: &AppHandle, state: &PythonSidecar) -> Result<(), String> {
    let cwd = resolve_project_root(app)?;
    let pythonpath = cwd.join("src");
    let unix_py = cwd.join(".venv").join("bin").join("python");
    let win_py = cwd.join(".venv").join("Scripts").join("python.exe");
    let python_bin = if unix_py.exists() {
        unix_py
    } else if win_py.exists() {
        win_py
    } else {
        std::path::PathBuf::from("python")
    };
    let mut command = Command::new(python_bin);
    command
        .current_dir(&cwd)
        .env("PYTHONPATH", pythonpath)
        .arg("-m")
        .arg("inercia")
        .arg("api")
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::inherit());
    let child = command
        .spawn()
        .map_err(|error| format!("failed to spawn Python API: {error}"))?;
    let mut guard = state
        .child
        .lock()
        .map_err(|_| String::from("failed to lock Python sidecar state"))?;
    *guard = Some(child);
    Ok(())
}

async fn bridge_websocket(app: AppHandle, bridge: WebSocketBridge) {
    loop {
        match connect_async(WS_URL).await {
            Ok((stream, _response)) => {
                let _ = app.emit("ws_status", json!({ "connected": true }));
                let (write, mut read) = stream.split();
                {
                    let mut guard = bridge.write.lock().await;
                    *guard = Some(write);
                }
                while let Some(message) = read.next().await {
                    match message {
                        Ok(Message::Text(text)) => {
                            let _ = app.emit("ws_message", text.to_string());
                        }
                        Ok(Message::Close(_)) => break,
                        Ok(_) => {}
                        Err(error) => {
                            let _ = app.emit("ws_error", error.to_string());
                            break;
                        }
                    }
                }
                {
                    let mut guard = bridge.write.lock().await;
                    *guard = None;
                }
                let _ = app.emit("ws_status", json!({ "connected": false }));
            }
            Err(error) => {
                let _ = app.emit("ws_error", error.to_string());
                sleep(Duration::from_secs(2)).await;
            }
        }
    }
}

async fn send_ws_message(
    payload: serde_json::Value,
    bridge: &WebSocketBridge,
) -> Result<CommandAck, String> {
    let mut guard = bridge.write.lock().await;
    let Some(write) = guard.as_mut() else {
        return Err(String::from("websocket bridge is not connected"));
    };
    write
        .send(Message::Text(payload.to_string().into()))
        .await
        .map_err(|error| format!("websocket send failed: {error}"))?;
    Ok(CommandAck { queued: true })
}

#[tauri::command]
async fn approve_proposal(
    proposal_id: i64,
    bridge: State<'_, WebSocketBridge>,
) -> Result<CommandAck, String> {
    send_ws_message(
        json!({ "type": "user_approved", "proposal_id": proposal_id }),
        &bridge,
    )
    .await
}

#[tauri::command]
async fn reject_proposal(
    proposal_id: i64,
    reason: Option<String>,
    bridge: State<'_, WebSocketBridge>,
) -> Result<CommandAck, String> {
    send_ws_message(
        json!({
            "type": "user_rejected",
            "proposal_id": proposal_id,
            "reason": reason
        }),
        &bridge,
    )
    .await
}

fn main() {
    tauri::Builder::default()
        .manage(PythonSidecar {
            child: Mutex::new(None),
        })
        .manage(WebSocketBridge {
            write: Arc::new(AsyncMutex::new(None)),
        })
        .setup(|app| {
            let handle = app.handle().clone();
            let sidecar = app.state::<PythonSidecar>();
            let bridge = app.state::<WebSocketBridge>().inner().clone();
            spawn_python_api(&handle, &sidecar)?;
            tauri::async_runtime::spawn(bridge_websocket(handle, bridge));
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![approve_proposal, reject_proposal])
        .run(tauri::generate_context!())
        .expect("error while running Inercia Tauri app");
}
