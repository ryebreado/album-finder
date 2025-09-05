#!/usr/bin/env python3
import requests
import sys
import json
import os
from datetime import datetime
from typing import List, Dict, Optional

try:
    from musicbrainz_client import MusicBrainzClient
    MUSICBRAINZ_AVAILABLE = True
except ImportError:
    MUSICBRAINZ_AVAILABLE = False

def get_cache_filename(username: str, period: str, limit: int, with_musicbrainz: bool = False) -> str:
    """Generate cache filename based on parameters."""
    mb_suffix = "_mb" if with_musicbrainz else ""
    return f"data/lastfm_{username}_{period}_{limit}{mb_suffix}.json"

def load_cached_data(cache_file: str) -> Optional[List[Dict[str, str]]]:
    """Load cached data if it exists."""
    if not os.path.exists(cache_file):
        return None
    
    try:
        with open(cache_file, 'r', encoding='utf-8') as f:
            cached = json.load(f)
        
        cached_time = datetime.fromisoformat(cached['timestamp'])
        print(f"Using cached data from {cached_time.strftime('%Y-%m-%d %H:%M')}")
        return cached['albums']
            
    except (json.JSONDecodeError, KeyError, ValueError):
        print("Cache file corrupted, fetching fresh data...")
        return None

def save_to_cache(albums: List[Dict[str, str]], cache_file: str):
    """Save albums data to cache with timestamp."""
    # Ensure data directory exists
    os.makedirs('data', exist_ok=True)
    
    cache_data = {
        'timestamp': datetime.now().isoformat(),
        'albums': albums
    }
    
    with open(cache_file, 'w', encoding='utf-8') as f:
        json.dump(cache_data, f, indent=2, ensure_ascii=False)
    
    print(f"Saved {len(albums)} albums to cache: {cache_file}")

def enrich_albums_with_musicbrainz(albums: List[Dict[str, str]]) -> List[Dict[str, str]]:
    """Enrich album data with MusicBrainz release type information."""
    if not MUSICBRAINZ_AVAILABLE:
        print("Warning: MusicBrainz client not available, skipping enrichment")
        return albums
        
    print(f"Enriching {len(albums)} albums with MusicBrainz data...")
    
    mb_client = MusicBrainzClient()
    enriched_albums = []
    
    for i, album in enumerate(albums):
        if i % 10 == 0:
            print(f"Processing album {i+1}/{len(albums)}...")
        
        # Create enriched album dict
        enriched_album = album.copy()
        
        # Try to get MusicBrainz release type
        mbid = album.get('mbid', '').strip()
        artist = album.get('artist', '')
        title = album.get('title', '')
        
        mb_data = mb_client.get_release_type(
            mbid=mbid if mbid else None,
            artist=artist,
            album=title
        )
        
        if mb_data:
            enriched_album.update({
                'mb_primary_type': mb_data.get('primary_type'),
                'mb_secondary_types': mb_data.get('secondary_types', []),
                'mb_confidence': mb_data.get('confidence', 0.0),
                'mb_id': mb_data.get('mbid')
            })
        else:
            enriched_album.update({
                'mb_primary_type': None,
                'mb_secondary_types': [],
                'mb_confidence': 0.0,
                'mb_id': None
            })
        
        enriched_albums.append(enriched_album)
    
    print(f"MusicBrainz enrichment complete!")
    return enriched_albums

def extract_lastfm_albums(username: str, api_key: str, period: str = 'overall', limit: int = 1000, 
                          enrich_with_musicbrainz: bool = False) -> List[Dict[str, str]]:
    """
    Extract album data from Last.fm user's top albums.
    
    Args:
        username: Last.fm username
        api_key: Last.fm API key
        period: Time period (overall, 7day, 1month, 3month, 6month, 12month)
        limit: Maximum number of albums to fetch
    
    Returns:
        List of albums with artist, title, and scrobbles.
    """
    # Check cache first
    cache_file = get_cache_filename(username, period, limit, with_musicbrainz=enrich_with_musicbrainz)
    cached_albums = load_cached_data(cache_file)
    if cached_albums is not None:
        return cached_albums
    
    albums = []
    page = 1
    per_page = 200  # Max allowed per page
    
    try:
        while len(albums) < limit:
            # Calculate how many to fetch this page
            to_fetch = min(per_page, limit - len(albums))
            
            url = "https://ws.audioscrobbler.com/2.0/"
            params = {
                'method': 'user.getTopAlbums',
                'user': username,
                'api_key': api_key,
                'format': 'json',
                'period': period,
                'limit': to_fetch,
                'page': page
            }
            
            response = requests.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            
            # Debug: print API URL and response on first page
            if page == 1:
                print(f"API URL: {response.url}")
                print(f"Response keys: {list(data.keys())}")
                top_albums_debug = data.get('topalbums', {})
                print(f"Topalbums keys: {list(top_albums_debug.keys())}")
                if 'album' in top_albums_debug:
                    print(f"Number of albums in response: {len(top_albums_debug['album']) if isinstance(top_albums_debug['album'], list) else 'Not a list'}")
                else:
                    print("No 'album' key in topalbums")
            
            # Check for API errors
            if 'error' in data:
                print(f"Last.fm API Error {data['error']}: {data['message']}")
                return []
            
            # Extract albums from response
            top_albums = data.get('topalbums', {})
            album_list = top_albums.get('album', [])
            
            # If no more albums, break
            if not album_list:
                break
            
            for i, album_data in enumerate(album_list):
                artist_data = album_data.get('artist', {})
                if isinstance(artist_data, dict):
                    artist_name = artist_data.get('name', artist_data.get('#text', ''))
                else:
                    artist_name = str(artist_data)
                
                album = {
                    'artist': str(artist_name).strip(),
                    'title': str(album_data.get('name', '')).strip(),
                    'scrobbles': str(album_data.get('playcount', '0')),
                    'mbid': str(album_data.get('mbid', '')).strip()
                }
                
                # Debug: print first album data on first page
                if page == 1 and i == 0:
                    print(f"Sample album data: {album_data}")
                    print(f"Parsed album: {album}")
                    print(f"Scrobbles check: {album['scrobbles']} > 0 = {int(album['scrobbles']) > 0}")
                
                # Only add if we have essential data
                if album['artist'] and album['title'] and int(album['scrobbles']) > 0:
                    albums.append(album)
                elif page == 1 and i < 3:  # Debug first few albums on first page
                    print(f"Filtered out album {i}: artist='{album['artist']}', title='{album['title']}', scrobbles={album['scrobbles']}")
                
                if len(albums) >= limit:
                    break
            
            page += 1
            
        # Enrich with MusicBrainz data if requested
        final_albums = albums[:limit]
        if enrich_with_musicbrainz and final_albums:
            final_albums = enrich_albums_with_musicbrainz(final_albums)
        
        # Save to cache before returning
        save_to_cache(final_albums, cache_file)
        return final_albums
        
    except requests.RequestException as e:
        print(f"Error making API request: {e}")
        return []
    except Exception as e:
        print(f"Error processing Last.fm data: {e}")
        return []

def main():
    # Check for API key in environment variable
    api_key = os.getenv('LASTFM_API_KEY')
    
    if len(sys.argv) < 2:
        print("Usage: python lastfm_extractor.py <username> [period] [limit]")
        print("Set LASTFM_API_KEY environment variable to avoid passing API key each time")
        print("Periods: overall (default), 7day, 1month, 3month, 6month, 12month")
        print("Limit: maximum number of albums (default: 1000)")
        sys.exit(1)
    
    username = sys.argv[1]
    
    # Parse arguments: username [period] [limit]
    if not api_key:
        print("Error: No API key found. Set environment variable:")
        print("export LASTFM_API_KEY=your_key_here")
        sys.exit(1)
    
    # Parse period and limit from remaining arguments
    period = 'overall'
    limit = 1000
    
    if len(sys.argv) > 2:
        # Check if second argument is a valid period
        if sys.argv[2] in ['overall', '7day', '1month', '3month', '6month', '12month']:
            period = sys.argv[2]
            if len(sys.argv) > 3:
                try:
                    limit = int(sys.argv[3])
                except ValueError:
                    print(f"Error: '{sys.argv[3]}' is not a valid number for limit")
                    sys.exit(1)
        else:
            # Second argument might be limit
            try:
                limit = int(sys.argv[2])
            except ValueError:
                print(f"Error: '{sys.argv[2]}' is not a valid period or limit")
                print("Valid periods: overall, 7day, 1month, 3month, 6month, 12month")
                sys.exit(1)
    
    print(f"Fetching top {limit} albums for {username} (period: {period})...")
    albums = extract_lastfm_albums(username, api_key, period, limit)
    
    print(f"\nExtracted {len(albums)} albums from Last.fm:")
    print("Note: Release dates are not available via Last.fm API")
    print()
    
    for album in albums:
        print(f"Artist: {album['artist']}")
        print(f"Title: {album['title']}")
        print(f"Scrobbles: {album['scrobbles']}")
        print("-" * 50)

if __name__ == "__main__":
    main()