#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use serde_json::{json, Value};
use std::collections::HashMap;
use std::io::{BufRead, BufReader, Write};
use std::path::PathBuf;
use std::process::{Child, ChildStdin, Command, Stdio};
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::{mpsc, Arc, Mutex};
use std::time::Duration;
use tauri::{Emitter, Manager, State};

type PendingResult = Result<Value, String>;

struct Bridge {
    child: Mutex<Child>,
    stdin: Mutex<ChildStdin>,
    pending: Arc<Mutex<HashMap<u64, mpsc::SyncSender<PendingResult>>>>,
    next_id: AtomicU64,
}

impl Bridge {
    fn spawn(app: tauri::AppHandle) -> Result<Arc<Self>, String> {
        let python = std::env::var("ETHERCAT_WORKBENCH_PYTHON").unwrap_or_else(|_| "python".into());
        let mut command = Command::new(python);
        let source_root = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../src");
        let mut python_paths = vec![source_root];
        if let Some(existing) = std::env::var_os("PYTHONPATH") {
            python_paths.extend(std::env::split_paths(&existing));
        }
        let python_path = std::env::join_paths(python_paths)
            .map_err(|error| format!("无法配置 Python 模块路径：{error}"))?;
        command.env("PYTHONPATH", python_path);
        command
            .args(["-u", "-m", "ethercat_debug_tool.bridge"])
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped());
        #[cfg(windows)]
        {
            use std::os::windows::process::CommandExt;
            command.creation_flags(0x08000000);
        }
        let mut child = command
            .spawn()
            .map_err(|error| format!("无法启动 Python EtherCAT 桥接进程：{error}"))?;
        let stdin = child.stdin.take().ok_or("无法打开桥接进程 stdin")?;
        let stdout = child.stdout.take().ok_or("无法打开桥接进程 stdout")?;
        let stderr = child.stderr.take().ok_or("无法打开桥接进程 stderr")?;
        let pending: Arc<Mutex<HashMap<u64, mpsc::SyncSender<PendingResult>>>> =
            Arc::new(Mutex::new(HashMap::new()));

        let reader_pending = Arc::clone(&pending);
        let reader_app = app.clone();
        std::thread::spawn(move || {
            for line in BufReader::new(stdout).lines() {
                let Ok(line) = line else { break };
                let Ok(message) = serde_json::from_str::<Value>(&line) else {
                    let _ = reader_app.emit("bridge-log", format!("桥接协议无法解析：{line}"));
                    continue;
                };
                match message.get("type").and_then(Value::as_str) {
                    Some("response") => {
                        let id = message.get("id").and_then(Value::as_u64).unwrap_or(0);
                        let sender = reader_pending
                            .lock()
                            .ok()
                            .and_then(|mut map| map.remove(&id));
                        if let Some(sender) = sender {
                            let response =
                                if message.get("ok").and_then(Value::as_bool) == Some(true) {
                                    Ok(message.get("result").cloned().unwrap_or(Value::Null))
                                } else {
                                    Err(message
                                        .get("error")
                                        .and_then(Value::as_str)
                                        .unwrap_or("未知桥接错误")
                                        .to_owned())
                                };
                            let _ = sender.send(response);
                        }
                    }
                    Some("event") => {
                        let _ = reader_app.emit(
                            "bridge-event",
                            message.get("payload").cloned().unwrap_or(Value::Null),
                        );
                    }
                    _ => {
                        let _ = reader_app.emit("bridge-log", message);
                    }
                }
            }
            let _ = reader_app.emit("bridge-exited", "Python EtherCAT 桥接进程已退出");
        });

        std::thread::spawn(move || {
            for line in BufReader::new(stderr).lines().map_while(Result::ok) {
                let _ = app.emit("bridge-log", line);
            }
        });

        Ok(Arc::new(Self {
            child: Mutex::new(child),
            stdin: Mutex::new(stdin),
            pending,
            next_id: AtomicU64::new(1),
        }))
    }

    fn request(&self, method: String, params: Value) -> PendingResult {
        let id = self.next_id.fetch_add(1, Ordering::Relaxed);
        let (sender, receiver) = mpsc::sync_channel(1);
        self.pending
            .lock()
            .map_err(|_| "桥接请求表已损坏".to_owned())?
            .insert(id, sender);
        let request = json!({"id": id, "method": method, "params": params});
        let write_result = self
            .stdin
            .lock()
            .map_err(|_| "桥接 stdin 已损坏".to_owned())
            .and_then(|mut stdin| {
                writeln!(stdin, "{request}")
                    .and_then(|_| stdin.flush())
                    .map_err(|error| format!("发送桥接请求失败：{error}"))
            });
        if let Err(error) = write_result {
            if let Ok(mut pending) = self.pending.lock() {
                pending.remove(&id);
            }
            return Err(error);
        }
        receiver
            .recv_timeout(Duration::from_secs(180))
            .map_err(|_| "Python EtherCAT 桥接请求超时".to_owned())?
    }

    fn shutdown(&self) {
        let _ = self.request("shutdown".into(), Value::Object(Default::default()));
        if let Ok(mut child) = self.child.lock() {
            let _ = child.wait();
        }
    }
}

struct BridgeState(Arc<Bridge>);

#[tauri::command]
async fn bridge_request(
    state: State<'_, BridgeState>,
    method: String,
    params: Value,
) -> Result<Value, String> {
    let bridge = Arc::clone(&state.0);
    tauri::async_runtime::spawn_blocking(move || bridge.request(method, params))
        .await
        .map_err(|error| format!("桥接任务失败：{error}"))?
}

#[tauri::command]
fn reveal_path(path: String) -> Result<(), String> {
    let target = PathBuf::from(&path);
    if !target.exists() {
        return Err(format!("路径不存在：{path}"));
    }
    let argument = if target.is_file() {
        format!("/select,{}", target.display())
    } else {
        target.display().to_string()
    };
    Command::new("explorer.exe")
        .arg(argument)
        .spawn()
        .map_err(|error| format!("无法打开资源管理器：{error}"))?;
    Ok(())
}

#[tauri::command]
fn open_external(url: String) -> Result<(), String> {
    const ALLOWED_URLS: [&str; 2] = [
        "https://github.com/LINLin190/EtherCAT-Workbench",
        "https://github.com/LINLin190/EtherCAT-Workbench/issues",
    ];
    if !ALLOWED_URLS.contains(&url.as_str()) {
        return Err("不允许打开该外部链接".into());
    }
    Command::new("rundll32.exe")
        .arg("url.dll,FileProtocolHandler")
        .arg(&url)
        .spawn()
        .map_err(|error| format!("无法打开外部链接：{error}"))?;
    Ok(())
}

fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .setup(|app| {
            let bridge = Bridge::spawn(app.handle().clone()).map_err(std::io::Error::other)?;
            app.manage(BridgeState(bridge));
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            bridge_request,
            reveal_path,
            open_external
        ])
        .build(tauri::generate_context!())
        .expect("failed to build EtherCAT Workbench")
        .run(|app, event| {
            if let tauri::RunEvent::Exit = event {
                if let Some(state) = app.try_state::<BridgeState>() {
                    state.0.shutdown();
                }
            }
        });
}
