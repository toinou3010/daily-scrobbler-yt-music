import os
import re
import time
from datetime import datetime, timedelta, timezone

import pylast
import ytmusicapi

from ytmusicapi.continuations import get_continuations
from ytmusicapi.navigation import (
    SINGLE_COLUMN_TAB,
    SECTION_LIST,
    nav,
)
from ytmusicapi.parsers.playlists import parse_playlist_items


API_KEY = os.getenv("LASTFM_API_KEY")
API_SECRET = os.getenv("LASTFM_API_SECRET")
USERNAME = os.getenv("LASTFM_USERNAME")
PASSWORD = os.getenv("LASTFM_PASSWORD")


def get_full_history(ytmusic: ytmusicapi.YTMusic) -> list[dict]:
    """
    Récupère l'historique YouTube Music en suivant les continuations
    jusqu'à ce qu'il n'y en ait plus.
    """
    ytmusic._check_auth()

    body = {"browseId": "FEmusic_history"}
    endpoint = "browse"

    response = ytmusic._send_request(endpoint, body)

    # La structure de l'historique peut varier selon les réponses YT Music.
    results = nav(response, SINGLE_COLUMN_TAB + SECTION_LIST)

    if not results:
        return []

    history = []

    for section in results:
        shelf = section.get("musicShelfRenderer")
        if not shelf:
            continue

        contents = shelf.get("contents", [])
        if not contents:
            continue

        items = parse_playlist_items(contents)

        # get_history() ajoute normalement "played" à chaque item.
        # Sur les réponses de l'API, cette information peut se trouver
        # dans le subtitle de chaque renderer ; on conserve ce que le
        # parser a déjà fourni et essayons aussi de récupérer un libellé
        # au niveau de la shelf.
        shelf_title = (
            shelf.get("title", {})
            .get("runs", [{}])[0]
            .get("text", "")
        )

        for item in items:
            if not item.get("played") and shelf_title:
                item["played"] = shelf_title

        history.extend(items)

        if "continuations" in shelf:
            request_func = lambda additional_params: ytmusic._send_request(
                endpoint,
                body,
                additional_params,
            )

            more = get_continuations(
                shelf,
                "musicShelfContinuation",
                None,
                request_func,
                parse_playlist_items,
            )

            for item in more:
                if not item.get("played") and shelf_title:
                    item["played"] = shelf_title

            history.extend(more)

    return history


def played_to_timestamp(played: str) -> int:
    """
    Convertit l'indication relative de YouTube Music en timestamp.

    Comme get_history() n'expose pas l'heure exacte de lecture, on utilise
    midi UTC comme heure approximative pour la date indiquée.
    """
    now = datetime.now(timezone.utc)

    if not played:
        return int(now.timestamp())

    value = played.strip().lower()

    if value in {"today", "aujourd’hui", "aujourd'hui"}:
        date = now

    elif value in {"yesterday", "hier"}:
        date = now - timedelta(days=1)

    else:
        # Anglais : "2 days ago"
        match = re.search(r"(\d+)\s+days?\s+ago", value)

        # Français : "il y a 2 jours"
        if not match:
            match = re.search(r"il\s+y\s+a\s+(\d+)\s+jours?", value)

        if match:
            date = now - timedelta(days=int(match.group(1)))
        else:
            # Si YouTube Music renvoie une date que nous ne savons pas
            # interpréter, on utilise aujourd'hui.
            date = now

    date = date.replace(
        hour=12,
        minute=0,
        second=0,
        microsecond=0,
    )

    return int(date.timestamp())


def to_scrobble(entry: dict) -> dict:
    artists = ", ".join(
        artist["name"]
        for artist in (entry.get("artists") or [])
        if artist.get("name")
    )

    primary_artist = (
        entry["artists"][0]["name"]
        if entry.get("artists")
        else artists
    )

    album = (entry.get("album") or {}).get("name", "")

    duration_seconds = entry.get("duration_seconds") or 180

    timestamp = played_to_timestamp(
        entry.get("played", "")
    )

    return {
        "artist": artists or "Unknown Artist",
        "title": entry.get("title", "Unknown Title"),
        "timestamp": timestamp,
        "album": album,
        "duration": duration_seconds,
        "album_artist": primary_artist or artists or "Unknown Artist",
    }


def scrobble_tracks(network: pylast.LastFMNetwork, tracks: list):
    if not tracks:
        print("Aucun morceau à scrobbler.")
        return

    # Last.fm accepte les scrobbles par lots. pylast gère l'envoi.
    try:
        network.scrobble_many(tracks)
    except pylast.WSError as error:
        print(f"Erreur Last.fm pendant le scrobble : {error}")
        raise

    print(f"{len(tracks)} morceaux envoyés à Last.fm.")


def main():
    browser_json_path = "browser.json"
    browser_json_raw = os.getenv("BROWSER_JSON")

    if not browser_json_raw:
        raise RuntimeError("Le secret BROWSER_JSON est absent.")

    # Le secret GitHub devient toujours la source de browser.json.
    with open(browser_json_path, "w", encoding="utf-8") as file:
        file.write(browser_json_raw)

    ytmusic = ytmusicapi.YTMusic(browser_json_path)

    required = {
        "LASTFM_API_KEY": API_KEY,
        "LASTFM_API_SECRET": API_SECRET,
        "LASTFM_USERNAME": USERNAME,
        "LASTFM_PASSWORD": PASSWORD,
    }

    missing = [name for name, value in required.items() if not value]
    if missing:
        raise RuntimeError(
            "Variables d'environnement manquantes : "
            + ", ".join(missing)
        )

    lastfm = pylast.LastFMNetwork(
        api_key=API_KEY,
        api_secret=API_SECRET,
        username=USERNAME,
        password_hash=pylast.md5(PASSWORD),
    )

    print("Récupération de tout l'historique YouTube Music...")

    history = get_full_history(ytmusic)

    print(f"Historique récupéré : {len(history)} morceaux.")

    if not history:
        return

    # Aucun filtre "Yesterday" : tout l'historique récupéré est traité.
    scrobbles = [to_scrobble(entry) for entry in history]

    print(f"{len(scrobbles)} morceaux à scrobbler.")

    # Affichage de quelques exemples pour vérifier les dates approximatives.
    for entry, scrobble in list(zip(history, scrobbles))[:5]:
        played = entry.get("played", "")
        when = datetime.fromtimestamp(
            scrobble["timestamp"],
            timezone.utc,
        ).isoformat()
        print(
            f"  {entry.get('title', 'Unknown')} | "
            f"played={played!r} | timestamp={when}"
        )

    scrobble_tracks(lastfm, scrobbles)


if __name__ == "__main__":
    main()
