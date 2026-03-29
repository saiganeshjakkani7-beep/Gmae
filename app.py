from __future__ import annotations

import json
import os
import re
import threading
from typing import Any

import requests
import yt_dlp
from flask import Flask, jsonify, render_template, request

app = Flask(__name__)

BASE_DIR = os.path.dirname(__file__)
DOWNLOAD_DIR = os.path.join(BASE_DIR, "downloads")
PLAYLIST_FILE = os.path.join(BASE_DIR, "playlists.json")
LIKED_FILE = os.path.join(BASE_DIR, "liked_songs.json")

os.makedirs(DOWNLOAD_DIR, exist_ok=True)

playlists_lock = threading.Lock()
likes_lock = threading.Lock()


VIDEO_ID_RE = re.compile(r"^[a-zA-Z0-9_-]{6,20}$")


def load_json(path: str, fallback: Any) -> Any:
    if not os.path.exists(path):
        return fallback
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return fallback


def save_json(path: str, data: Any) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def load_playlists() -> dict[str, list[dict[str, Any]]]:
    data = load_json(PLAYLIST_FILE, {})
    return data if isinstance(data, dict) else {}


def save_playlists(data: dict[str, list[dict[str, Any]]]) -> None:
    save_json(PLAYLIST_FILE, data)


def load_liked_songs() -> list[dict[str, Any]]:
    data = load_json(LIKED_FILE, [])
    return data if isinstance(data, list) else []


def save_liked_songs(data: list[dict[str, Any]]) -> None:
    save_json(LIKED_FILE, data)


def clean_title(title: str) -> str:
    title = re.sub(r"[\(\[].*?[\)\]]", "", title, flags=re.IGNORECASE)
    title = re.sub(
        r"\b(official|video|audio|lyrics|hd|4k|ft\.?|feat\.?|music)\b",
        "",
        title,
        flags=re.IGNORECASE,
    )
    return re.sub(r"\s+", " ", title).strip().lower()


def validate_video_id(video_id: str) -> bool:
    return bool(VIDEO_ID_RE.match(video_id or ""))


def yt_fetch(search_query: str, max_results: int = 15) -> list[dict[str, Any]]:
    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": True,
        "skip_download": True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(f"ytsearch{max_results}:{search_query}", download=False)
        return info.get("entries", []) or []


def normalize_entry(entry: dict[str, Any]) -> dict[str, Any] | None:
    video_id = entry.get("id")
    if not video_id or not validate_video_id(video_id):
        return None

    title = (entry.get("title") or "").strip()
    if not title:
        return None

    duration = entry.get("duration") or 0
    if duration and duration > 600:
        return None

    return {
        "id": video_id,
        "title": title,
        "duration": duration,
        "thumbnail": entry.get("thumbnail")
        or f"https://img.youtube.com/vi/{video_id}/mqdefault.jpg",
        "uploader": entry.get("uploader") or entry.get("channel", "Unknown"),
    }


@app.route("/")
def index() -> str:
    return render_template("index.html")


@app.route("/health")
def health() -> Any:
    return jsonify({"status": "ok"})


@app.route("/search")
def search() -> Any:
    query = request.args.get("q", "").strip()
    if not query:
        return jsonify([])

    seen_titles: set[str] = set()
    results: list[dict[str, Any]] = []

    def add_results(entries: list[dict[str, Any]]) -> None:
        for entry in entries:
            song = normalize_entry(entry)
            if not song:
                continue
            ct = clean_title(song["title"])
            if ct in seen_titles:
                continue
            seen_titles.add(ct)
            results.append(song)

    add_results(yt_fetch(query, 6))

    words = query.split()
    if len(words) >= 2:
        artist_guess = " ".join(words[:2])
        add_results(yt_fetch(f"{artist_guess} top songs", 8))

    add_results(yt_fetch(f"{query} similar songs", 8))

    return jsonify(results[:20])


@app.route("/recommendations")
def recommendations() -> Any:
    """Spotify-like 'radio' endpoint from a seed query/song title."""
    seed = request.args.get("seed", "").strip()
    if not seed:
        return jsonify({"error": "seed query required"}), 400

    entries = yt_fetch(f"{seed} mix playlist songs", max_results=20)
    songs: list[dict[str, Any]] = []
    seen: set[str] = set()
    for entry in entries:
        song = normalize_entry(entry)
        if not song or song["id"] in seen:
            continue
        seen.add(song["id"])
        songs.append(song)

    return jsonify(songs[:15])


@app.route("/stream/<video_id>")
def stream(video_id: str) -> Any:
    if not validate_video_id(video_id):
        return jsonify({"error": "Invalid video id"}), 400

    ydl_opts = {
        "quiet": True,
        "format": "bestaudio/best",
        "no_warnings": True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(f"https://youtube.com/watch?v={video_id}", download=False)
        audio_url = info["url"]

    return jsonify(
        {
            "url": audio_url,
            "title": info.get("title"),
            "duration": info.get("duration"),
            "thumbnail": info.get("thumbnail"),
            "uploader": info.get("uploader"),
        }
    )


def do_download(video_id: str) -> None:
    if not validate_video_id(video_id):
        return

    for f in os.listdir(DOWNLOAD_DIR):
        if f.startswith(video_id):
            return

    ydl_opts = {
        "quiet": True,
        "format": "bestaudio/best",
        "outtmpl": os.path.join(DOWNLOAD_DIR, f"{video_id}.%(ext)s"),
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }
        ],
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([f"https://youtube.com/watch?v={video_id}"])


@app.route("/download/<video_id>")
def download(video_id: str) -> Any:
    if not validate_video_id(video_id):
        return jsonify({"error": "Invalid video id"}), 400

    t = threading.Thread(target=do_download, args=(video_id,), daemon=True)
    t.start()
    return jsonify({"status": "downloading"})


@app.route("/lyrics")
def lyrics() -> Any:
    query = request.args.get("q", "").strip()
    if not query:
        return jsonify({"lyrics": "No query provided."}), 400

    # Expected format: Artist - Song Name
    if " - " in query:
        artist, title = [p.strip() for p in query.split(" - ", 1)]
    else:
        parts = query.split(" ", 1)
        artist, title = (parts[0], parts[1]) if len(parts) == 2 else (query, query)

    try:
        resp = requests.get(f"https://api.lyrics.ovh/v1/{artist}/{title}", timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            return jsonify({"lyrics": data.get("lyrics", "Lyrics not found."), "artist": artist, "title": title})
    except requests.RequestException:
        pass

    return jsonify({"lyrics": "Lyrics not found. Try 'Artist - SongName'.", "artist": artist, "title": title})


@app.route("/liked", methods=["GET"])
def get_liked() -> Any:
    """Spotify-like 'Liked Songs'."""
    with likes_lock:
        return jsonify(load_liked_songs())


@app.route("/liked/add", methods=["POST"])
def add_liked() -> Any:
    payload = request.get_json(silent=True) or {}
    song = payload.get("song")
    if not isinstance(song, dict) or not validate_video_id(song.get("id", "")):
        return jsonify({"error": "Valid song object required"}), 400

    with likes_lock:
        liked = load_liked_songs()
        if not any(s.get("id") == song["id"] for s in liked):
            liked.append(song)
            save_liked_songs(liked)

    return jsonify({"status": "added"})


@app.route("/liked/remove", methods=["POST"])
def remove_liked() -> Any:
    payload = request.get_json(silent=True) or {}
    song_id = payload.get("id", "")
    if not validate_video_id(song_id):
        return jsonify({"error": "Valid id required"}), 400

    with likes_lock:
        liked = load_liked_songs()
        save_liked_songs([s for s in liked if s.get("id") != song_id])

    return jsonify({"status": "removed"})


@app.route("/playlists", methods=["GET"])
def get_playlists() -> Any:
    with playlists_lock:
        return jsonify(load_playlists())


@app.route("/playlists/create", methods=["POST"])
def create_playlist() -> Any:
    data = request.get_json(silent=True) or {}
    name = data.get("name", "").strip()
    if not name:
        return jsonify({"error": "Name required"}), 400

    with playlists_lock:
        playlists = load_playlists()
        if name not in playlists:
            playlists[name] = []
            save_playlists(playlists)

    return jsonify({"status": "created", "name": name})


@app.route("/playlists/<name>/add", methods=["POST"])
def add_to_playlist(name: str) -> Any:
    data = request.get_json(silent=True) or {}
    song = data.get("song")
    if not isinstance(song, dict) or not validate_video_id(song.get("id", "")):
        return jsonify({"error": "Valid song object required"}), 400

    with playlists_lock:
        playlists = load_playlists()
        if name not in playlists:
            return jsonify({"error": "Playlist not found"}), 404

        if not any(s.get("id") == song["id"] for s in playlists[name]):
            playlists[name].append(song)
            save_playlists(playlists)

    return jsonify({"status": "added"})


@app.route("/playlists/<name>/remove", methods=["POST"])
def remove_from_playlist(name: str) -> Any:
    data = request.get_json(silent=True) or {}
    song_id = data.get("id", "")
    if not validate_video_id(song_id):
        return jsonify({"error": "Valid id required"}), 400

    with playlists_lock:
        playlists = load_playlists()
        if name not in playlists:
            return jsonify({"error": "Playlist not found"}), 404

        playlists[name] = [s for s in playlists[name] if s.get("id") != song_id]
        save_playlists(playlists)

    return jsonify({"status": "removed"})


@app.route("/playlists/<name>/delete", methods=["POST"])
def delete_playlist(name: str) -> Any:
    with playlists_lock:
        playlists = load_playlists()
        playlists.pop(name, None)
        save_playlists(playlists)

    return jsonify({"status": "deleted"})


@app.route("/downloads")
def list_downloads() -> Any:
    files = sorted(os.listdir(DOWNLOAD_DIR))
    return jsonify(files)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
