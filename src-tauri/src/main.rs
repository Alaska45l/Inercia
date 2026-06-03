#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use serde::Serialize;
use serde_json::json;
use std::fs;
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use tauri::{AppHandle, Emitter, Manager, State};
use tokio::net::TcpStream;
use tokio::time::{sleep, Duration};

struct PythonSidecar {
    child: Mutex<Option<Child>>,
}

impl Drop for PythonSidecar {
    fn drop(&mut self) {
        if let Ok(mut guard) = self.child.lock() {
            if let Some(child) = guard.as_mut() {
                let _ = child.kill();
                let _ = child.wait();
            }
        }
    }
}

impl PythonSidecar {
    fn stop(&self) -> Result<(), String> {
        let mut guard = self
            .child
            .lock()
            .map_err(|_| String::from("failed to lock Python sidecar state"))?;
        if let Some(mut child) = guard.take() {
            let _ = child.kill();
            let _ = child.wait();
        }
        Ok(())
    }
}

#[derive(Serialize)]
struct CommandAck {
    queued: bool,
}

#[derive(Serialize)]
struct SettingsSnapshot {
    ws_port: u16,
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

fn parse_ws_port(raw: &str) -> Option<u16> {
    let cleaned = raw.trim().trim_matches('"').trim_matches('\'');
    cleaned.parse::<u16>().ok().filter(|port| *port > 0)
}

fn read_ws_port(project_root: &Path) -> u16 {
    if let Ok(raw) = std::env::var("WS_PORT") {
        if let Some(port) = parse_ws_port(&raw) {
            return port;
        }
    }
    let env_path = project_root.join(".env");
    let Ok(contents) = fs::read_to_string(env_path) else {
        return 9741;
    };
    for raw_line in contents.lines() {
        let line = raw_line.trim();
        if line.is_empty() || line.starts_with('#') {
            continue;
        }
        let line = line.strip_prefix("export ").unwrap_or(line).trim();
        let Some((key, value)) = line.split_once('=') else {
            continue;
        };
        if key.trim() == "WS_PORT" {
            if let Some(port) = parse_ws_port(value) {
                return port;
            }
        }
    }
    9741
}

fn inject_ws_port(app: &AppHandle, ws_port: u16) {
    if let Some(window) = app.get_webview_window("main") {
        let script = format!(
            "window.__INERCIA_WS_PORT__ = \"{0}\"; window.__TAURI__ = Object.assign(window.__TAURI__ || {{}}, {{ inerciaWsPort: \"{0}\" }});",
            ws_port
        );
        let _ = window.eval(&script);
    }
}

async fn check_python_health(app: AppHandle, ws_port: u16) {
    let address = format!("127.0.0.1:{ws_port}");
    for _ in 0..20 {
        if TcpStream::connect(&address).await.is_ok() {
            return;
        }
        sleep(Duration::from_millis(500)).await;
    }
    let _ = app.emit(
        "python_failed",
        json!({ "message": "Python API did not open its WebSocket port", "ws_port": ws_port }),
    );
}

fn spawn_python_api(app: &AppHandle, state: &PythonSidecar) -> Result<u16, String> {
    let cwd = resolve_project_root(app)?;
    let ws_port = read_ws_port(&cwd);
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
    state.stop()?;
    let child = command
        .spawn()
        .map_err(|error| format!("failed to spawn Python API: {error}"))?;
    let mut guard = state
        .child
        .lock()
        .map_err(|_| String::from("failed to lock Python sidecar state"))?;
    *guard = Some(child);
    inject_ws_port(app, ws_port);
    let health_app = app.clone();
    tauri::async_runtime::spawn(check_python_health(health_app, ws_port));
    Ok(ws_port)
}

#[tauri::command]
async fn restart_python(app: AppHandle, sidecar: State<'_, PythonSidecar>) -> Result<CommandAck, String> {
    spawn_python_api(&app, sidecar.inner())?;
    Ok(CommandAck { queued: true })
}

#[tauri::command]
fn get_settings(app: AppHandle) -> Result<SettingsSnapshot, String> {
    let root = resolve_project_root(&app)?;
    Ok(SettingsSnapshot {
        ws_port: read_ws_port(&root),
    })
}

fn main() {
    tauri::Builder::default()
        .manage(PythonSidecar {
            child: Mutex::new(None),
        })
        .setup(|app| {
            let handle = app.handle().clone();
            let sidecar = app.state::<PythonSidecar>();
            spawn_python_api(&handle, sidecar.inner())?;
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![restart_python, get_settings])
        .run(tauri::generate_context!())
        .expect("error while running Inercia Tauri app");
}
