// SPDX-License-Identifier: AGPL-3.0-or-later
// ClipForge / 星创映画（CreatorBox）· 桌面剪辑版
// 本文件为 ClipForge 独立编写，未复制自任何小程序项目。

use concat_core::time::Rational;
use concat_core::timeline::{Clip, MediaRef, Track, TrackKind};
use concat_core::{Project, Timeline};

/// 锁定的 Concat 版本信息（与 Cargo.toml 的 git rev 保持一致）
const CONCAT_REV: &str = "995b205492f2da908cc8aa8c83812008b10ae22f";
const CONCAT_TAG: &str = "v0.2.12";

/// 引擎自检 + 可选的视频探测。
///
/// 若传入一个存在的视频文件路径，则用 Concat 的 concat-media 引擎链接 FFmpeg
/// 真实打开并探测它（probe），返回编码、分辨率、时长等信息。
/// 若不传路径，则做基础自检：显示 FFmpeg 链接版本，并用 concat-core 创建
/// 一条真实时间线工程。
///
/// 能返回结果即证明 Concat 引擎运行时代码已被编译进同一个可执行文件并运行。
#[tauri::command]
fn probe_engine(video_path: Option<String>) -> serde_json::Value {
    // 1) 证明 FFmpeg 已被真正链接进引擎（来自 concat-media）
    let ffmpeg_version = concat_media::linked_version();

    // 2) 用引擎核心创建一条 1920x1080 / 30fps 时间线，加轨、放一段 5 秒素材
    let mut timeline = Timeline::hd();
    let track = timeline.add_track(Track::new("V1", TrackKind::Video));
    let clip = Clip::new(
        MediaRef::new("sample.mp4"),
        Rational::from_int(0),
        Rational::from_int(5),
    );
    let clip_added = timeline.add_clip(track, clip).is_some();
    let project = Project::new("ClipForge 验证工程", timeline);

    // 3) 若提供了视频路径且文件存在，用引擎真实探测该文件
    let mut media_probe = serde_json::Value::Null;
    if let Some(path) = video_path {
        if !path.trim().is_empty() && std::path::Path::new(&path).is_file() {
            match concat_media::probe(&path) {
                Ok(info) => {
                    let video = info.video.as_ref().map(|v| serde_json::json!({
                        "codec": v.codec,
                        "width": v.width,
                        "height": v.height,
                    }));
                    media_probe = serde_json::json!({
                        "ok": true,
                        "path": info.path.to_string_lossy(),
                        "duration_seconds": info.duration.map(|d| d.as_f64()),
                        "video": video,
                        "audio_streams": info.audio_streams.len(),
                    });
                }
                Err(e) => {
                    media_probe = serde_json::json!({ "ok": false, "error": e.to_string() });
                }
            }
        } else {
            media_probe = serde_json::json!({ "ok": false, "error": "文件不存在" });
        }
    }

    serde_json::json!({
        "ok": true,
        "engine": "Concat 引擎运行时核心",
        "tag": CONCAT_TAG,
        "rev": CONCAT_REV,
        "ffmpeg_linked_version": ffmpeg_version,
        "project_name": project.name,
        "track_count": project.timeline.track_ids().len(),
        "clip_count": project.timeline.clip_count(),
        "clip_added": clip_added,
        "timeline_duration_seconds": project.timeline.duration().as_f64(),
        "timeline_frames": project.timeline.frame_count(),
        "resolution": format!("{}x{}", project.timeline.width, project.timeline.height),
        "media_probe": media_probe
    })
}

/// 打开系统文件对话框，选择一个视频文件，返回其完整路径。
///
/// 用 spawn_blocking 调用阻塞式对话框，避免阻塞主线程/异步运行时。
/// 用户取消选择时返回 None。
#[tauri::command]
async fn pick_video(app: tauri::AppHandle) -> Option<String> {
    use tauri_plugin_dialog::DialogExt;
    tauri::async_runtime::spawn_blocking(move || {
        app.dialog()
            .file()
            .add_filter("视频文件", &["mp4", "mov", "mkv", "avi", "webm", "m4v", "flv", "wmv"])
            .add_filter("所有文件", &["*"])
            .blocking_pick_file()
            .and_then(|fp| fp.into_path().ok())
            .map(|p| p.to_string_lossy().to_string())
    })
    .await
    .ok()
    .flatten()
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .invoke_handler(tauri::generate_handler![probe_engine, pick_video])
        .run(tauri::generate_context!())
        .expect("启动 ClipForge 窗口失败");
}
