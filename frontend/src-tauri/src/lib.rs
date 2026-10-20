use std::sync::{Arc, Mutex};
use std::process::Child;
use tauri::{
    menu::{Menu, MenuItem, PredefinedMenuItem},
    tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent},
    Emitter, Manager, WindowEvent,
};
use tauri_plugin_autostart::{MacosLauncher, ManagerExt as AutostartExt};
use tauri_plugin_global_shortcut::{GlobalShortcutExt, Shortcut, ShortcutState};

// ---------------------------------------------------------------------------
// Backend process state
// ---------------------------------------------------------------------------

type BackendProcess = Arc<Mutex<Option<Child>>>;

/// Spawn the Python/uvicorn backend as a child process.
/// Looks for `backend/.venv/Scripts/python.exe` (Windows) relative to the
/// app's resource dir, falling back to the bare `python` / `python3` in PATH.
fn spawn_backend(app: &tauri::AppHandle) -> Option<Child> {
    // Try to resolve a portable venv Python next to the executable first.
    let candidates: Vec<std::path::PathBuf> = {
        let mut v: Vec<std::path::PathBuf> = vec![];

        // 1. Sidecar-style: <app_resource_dir>/backend/.venv/Scripts/python.exe
        if let Ok(resource_dir) = app.path().resource_dir() {
            v.push(resource_dir.join("backend").join(".venv").join("Scripts").join("python.exe"));
            v.push(resource_dir.join("backend").join(".venv").join("bin").join("python"));
        }

        // 2. Relative to the executable's parent (dev layout)
        if let Ok(exe) = std::env::current_exe() {
            if let Some(exe_dir) = exe.parent() {
                // In dev mode the exe is in frontend/src-tauri/target/debug/
                // Walk up to find the repo root heuristically.
                let mut dir = exe_dir.to_path_buf();
                for _ in 0..6 {
                    let candidate = dir.join("backend").join(".venv").join("Scripts").join("python.exe");
                    if candidate.exists() {
                        v.push(candidate.clone());
                    }
                    let candidate_unix = dir.join("backend").join(".venv").join("bin").join("python");
                    if candidate_unix.exists() {
                        v.push(candidate_unix);
                    }
                    match dir.parent() {
                        Some(p) => dir = p.to_path_buf(),
                        None => break,
                    }
                }
            }
        }

        // 3. Fall back to system python in PATH
        v.push(std::path::PathBuf::from("python"));
        v.push(std::path::PathBuf::from("python3"));
        v
    };

    // Resolve the backend/ directory for the working directory.
    let backend_dir: Option<std::path::PathBuf> = {
        let mut found = None;
        if let Ok(exe) = std::env::current_exe() {
            if let Some(exe_dir) = exe.parent() {
                let mut dir = exe_dir.to_path_buf();
                for _ in 0..6 {
                    let bd = dir.join("backend");
                    if bd.join("main.py").exists() {
                        found = Some(bd);
                        break;
                    }
                    match dir.parent() {
                        Some(p) => dir = p.to_path_buf(),
                        None => break,
                    }
                }
            }
        }
        found
    };

    for python in &candidates {
        if !python.exists() && python.to_string_lossy() != "python" && python.to_string_lossy() != "python3" {
            continue;
        }

        let mut cmd = std::process::Command::new(python);
        cmd.args(["-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", "8000"]);

        if let Some(ref bd) = backend_dir {
            cmd.current_dir(bd);
        }

        // Suppress console on Windows release builds
        #[cfg(windows)]
        {
            use std::os::windows::process::CommandExt;
            // CREATE_NO_WINDOW = 0x0800_0000
            cmd.creation_flags(0x0800_0000);
        }

        match cmd.spawn() {
            Ok(child) => {
                log::info!("Backend spawned with PID {}", child.id());
                return Some(child);
            }
            Err(e) => {
                log::warn!("Failed to spawn backend with {:?}: {}", python, e);
            }
        }
    }

    log::error!("Could not spawn backend process — tried all candidates");
    None
}

// ---------------------------------------------------------------------------
// Tauri commands
// ---------------------------------------------------------------------------

#[tauri::command]
fn show_window(app: tauri::AppHandle) {
    if let Some(window) = app.get_webview_window("main") {
        let _ = window.show();
        let _ = window.unminimize();
        let _ = window.set_focus();
    }
}

#[tauri::command]
fn hide_window(app: tauri::AppHandle) {
    if let Some(window) = app.get_webview_window("main") {
        let _ = window.hide();
    }
}

#[tauri::command]
fn quit_app(app: tauri::AppHandle) {
    app.exit(0);
}

#[tauri::command]
async fn is_autostart_enabled(app: tauri::AppHandle) -> Result<bool, String> {
    app.autolaunch().is_enabled().map_err(|e| e.to_string())
}

#[tauri::command]
async fn set_autostart(app: tauri::AppHandle, enable: bool) -> Result<bool, String> {
    if enable {
        app.autolaunch().enable().map_err(|e| e.to_string())?;
    } else {
        app.autolaunch().disable().map_err(|e| e.to_string())?;
    }
    app.autolaunch().is_enabled().map_err(|e| e.to_string())
}

/// Check whether the backend is alive (returns true/false to JS).
#[tauri::command]
async fn backend_status() -> bool {
    let client = reqwest::Client::builder()
        .timeout(std::time::Duration::from_secs(2))
        .build()
        .unwrap_or_default();
    client
        .get("http://127.0.0.1:8000/health")
        .send()
        .await
        .map(|r| r.status().is_success())
        .unwrap_or(false)
}

// ---------------------------------------------------------------------------
// App entry point
// ---------------------------------------------------------------------------

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let backend_state: BackendProcess = Arc::new(Mutex::new(None));
    let backend_state_clone = backend_state.clone();

    tauri::Builder::default()
        .plugin(tauri_plugin_log::Builder::default().build())
        .plugin(tauri_plugin_global_shortcut::Builder::default().build())
        .plugin(tauri_plugin_autostart::init(
            MacosLauncher::LaunchAgent,
            Some(vec![]),
        ))
        .manage(backend_state)
        .invoke_handler(tauri::generate_handler![
            show_window,
            hide_window,
            quit_app,
            is_autostart_enabled,
            set_autostart,
            backend_status,
        ])
        .setup(move |app| {
            // --- Spawn backend ---
            {
                let child = spawn_backend(app.handle());
                let mut guard = backend_state_clone.lock().unwrap();
                *guard = child;
            }

            // 1. Build Tray Menu
            let open_i = MenuItem::with_id(app, "open", "Open AFSAR", true, None::<&str>)?;
            let hide_i = MenuItem::with_id(app, "hide", "Hide", true, None::<&str>)?;
            let sep1 = PredefinedMenuItem::separator(app)?;
            let settings_i = MenuItem::with_id(app, "settings", "Settings", true, None::<&str>)?;
            let sep2 = PredefinedMenuItem::separator(app)?;
            let quit_i = MenuItem::with_id(app, "quit", "Exit AFSAR", true, None::<&str>)?;

            let tray_menu = Menu::with_items(
                app,
                &[&open_i, &hide_i, &sep1, &settings_i, &sep2, &quit_i],
            )?;

            // 2. Build Tray Icon
            let icon = app.default_window_icon().cloned().expect("Default window icon missing");
            let _tray = TrayIconBuilder::with_id("main-tray")
                .icon(icon)
                .menu(&tray_menu)
                .show_menu_on_left_click(false)
                .tooltip("AFSAR Assistant")
                .on_menu_event(|app, event| {
                    match event.id.as_ref() {
                        "open" => {
                            if let Some(window) = app.get_webview_window("main") {
                                let _ = window.show();
                                let _ = window.unminimize();
                                let _ = window.set_focus();
                            }
                        }
                        "hide" => {
                            if let Some(window) = app.get_webview_window("main") {
                                let _ = window.hide();
                            }
                        }
                        "settings" => {
                            if let Some(window) = app.get_webview_window("main") {
                                let _ = window.show();
                                let _ = window.unminimize();
                                let _ = window.set_focus();
                                let _ = window.emit("open-settings", ());
                            }
                        }
                        "quit" => {
                            app.exit(0);
                        }
                        _ => {}
                    }
                })
                .on_tray_icon_event(|tray, event| {
                    if let TrayIconEvent::Click {
                        button: MouseButton::Left,
                        button_state: MouseButtonState::Up,
                        ..
                    } = event
                    {
                        let app = tray.app_handle();
                        if let Some(window) = app.get_webview_window("main") {
                            let visible = window.is_visible().unwrap_or(false);
                            if visible {
                                let _ = window.hide();
                            } else {
                                let _ = window.show();
                                let _ = window.unminimize();
                                let _ = window.set_focus();
                            }
                        }
                    }
                })
                .build(app)?;

            // 3. Register Global Keyboard Shortcut (Ctrl+Shift+Space)
            if let Ok(shortcut) = "CommandOrControl+Shift+Space".parse::<Shortcut>() {
                let app_handle = app.handle().clone();
                let _ = app.global_shortcut().on_shortcut(shortcut, move |_app, _sc, event| {
                    if event.state() == ShortcutState::Pressed {
                        if let Some(window) = app_handle.get_webview_window("main") {
                            let visible = window.is_visible().unwrap_or(false);
                            let focused = window.is_focused().unwrap_or(false);
                            if visible && focused {
                                let _ = window.hide();
                            } else {
                                let _ = window.show();
                                let _ = window.unminimize();
                                let _ = window.set_focus();
                            }
                        }
                    }
                });
            }

            Ok(())
        })
        .on_window_event(|window, event| {
            // Close-to-tray behavior: closing the window hides it rather than terminating
            if let WindowEvent::CloseRequested { api, .. } = event {
                api.prevent_close();
                let _ = window.hide();
            }
        })
        // Kill backend when app exits
        .on_menu_event(move |_app, _event| {
            // handled in tray menu above
        })
        .run(tauri::generate_context!())
        .expect("error while building tauri application");

    // Kill the backend child process on exit
    // (Tauri calls this after .run() returns on normal exit paths)
}
