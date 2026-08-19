import os
import time
import pylast
import ytmusicapi


API_KEY = os.getenv("LASTFM_API_KEY")
API_SECRET = os.getenv("LASTFM_API_SECRET")

username = os.getenv("LASTFM_USERNAME")
password_hash = pylast.md5(os.getenv("LASTFM_PASSWORD"))


def to_scrobble(entry: dict) -> dict:
    artists = ", ".join(a["name"] for a in entry.get("artists") if a.get("id") or [])
    primary_artist = entry["artists"][0]["name"] if entry.get("artists") else artists
    album = (entry.get("album") or {}).get("name", "")
    duration_seconds = entry.get("duration_seconds",180)
    return {
        "artist": artists,
        "title": entry["title"],
        "timestamp": int(time.time()),
        "album": album,
        "duration": duration_seconds,
        "album_artist": primary_artist,
    }


def scrobble_tracks(network: pylast.LastFMNetwork, tracks: list):
    try:
        network.scrobble_many(tracks)
    except pylast.WSError as e:
        print(f"Error scrobbling tracks: {e}")
        raise
    print(f"Scrobbled {len(tracks)} tracks to Last.fm")


def main():
    browser_json_path = "browser.json"
    browser_json_raw = os.getenv("BROWSER_JSON")
    if not os.path.exists(browser_json_path):
        with open(browser_json_path, "w") as f:
            f.write(browser_json_raw or "{}")

    ytmusic = ytmusicapi.YTMusic(browser_json_path)

    lastfm = pylast.LastFMNetwork(
        api_key=API_KEY,
        api_secret=API_SECRET,
        username=username,
        password_hash=password_hash,
    )

    history = ytmusic.get_history()

    history = [entry for entry in history if entry.get("played") == "Yesterday"]

    scrobbles = [to_scrobble(entry) for entry in history]

    print(f"{len(scrobbles)} tracks to scrobble")
    scrobble_tracks(lastfm, scrobbles)

if __name__ == "__main__":
    main()
