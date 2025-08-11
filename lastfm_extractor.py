#!/usr/bin/env python3
import requests
import sys
import json
import os
from typing import List, Dict, Optional

def extract_lastfm_albums(username: str, api_key: str, period: str = 'overall', limit: int = 1000) -> List[Dict[str, str]]:
    """
    Extract album data from Last.fm user's top albums.
    
    Args:
        username: Last.fm username
        api_key: Last.fm API key
        period: Time period (overall, 7day, 1month, 3month, 6month, 12month)
        limit: Maximum number of albums to fetch
    
    Returns:
        List of albums with artist, title, and playcount.
        Note: Release dates are not available via Last.fm API.
    """
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
                    'playcount': str(album_data.get('playcount', '0')),
                    'release_date': ''  # Not available via Last.fm API
                }
                
                # Debug: print first album data on first page
                if page == 1 and i == 0:
                    print(f"Sample album data: {album_data}")
                    print(f"Parsed album: {album}")
                    print(f"Playcount check: {album['playcount']} > 0 = {int(album['playcount']) > 0}")
                
                # Only add if we have essential data
                if album['artist'] and album['title'] and int(album['playcount']) > 0:
                    albums.append(album)
                elif page == 1 and i < 3:  # Debug first few albums on first page
                    print(f"Filtered out album {i}: artist='{album['artist']}', title='{album['title']}', playcount={album['playcount']}")
                
                if len(albums) >= limit:
                    break
            
            page += 1
            
        return albums[:limit]
        
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
        print(f"Playcount: {album['playcount']}")
        print("-" * 50)

if __name__ == "__main__":
    main()