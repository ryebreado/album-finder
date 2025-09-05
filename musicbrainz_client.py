#!/usr/bin/env python3
import requests
import json
import os
import time
from datetime import datetime
from typing import Dict, Optional, List
from urllib.parse import quote

class MusicBrainzClient:
    """
    MusicBrainz API client with rate limiting and caching.
    Respects MusicBrainz's 1 request/second rate limit.
    """
    
    def __init__(self, cache_dir: str = "data/musicbrainz_cache"):
        self.base_url = "https://musicbrainz.org/ws/2"
        self.cache_dir = cache_dir
        self.last_request_time = 0
        self.rate_limit_delay = 1.0  # 1 second between requests
        
        # Create cache directory
        os.makedirs(self.cache_dir, exist_ok=True)
        
        # User agent is required by MusicBrainz
        self.headers = {
            'User-Agent': 'album-finder/1.0 https://github.com/ryebreado/album-finder'
        }
    
    def _get_cache_path(self, cache_key: str) -> str:
        """Get cache file path for a given key."""
        safe_key = cache_key.replace('/', '_').replace('\\', '_')
        return os.path.join(self.cache_dir, f"{safe_key}.json")
    
    def _load_from_cache(self, cache_key: str) -> Optional[Dict]:
        """Load data from cache if it exists."""
        cache_path = self._get_cache_path(cache_key)
        if os.path.exists(cache_path):
            try:
                with open(cache_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except (json.JSONDecodeError, FileNotFoundError):
                pass
        return None
    
    def _save_to_cache(self, cache_key: str, data: Dict) -> None:
        """Save data to cache."""
        cache_path = self._get_cache_path(cache_key)
        try:
            with open(cache_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Warning: Could not save to cache: {e}")
    
    def _rate_limit(self) -> None:
        """Enforce rate limiting."""
        elapsed = time.time() - self.last_request_time
        if elapsed < self.rate_limit_delay:
            time.sleep(self.rate_limit_delay - elapsed)
        self.last_request_time = time.time()
    
    def _make_request(self, url: str, params: Dict) -> Optional[Dict]:
        """Make a rate-limited request to MusicBrainz API."""
        self._rate_limit()
        
        try:
            response = requests.get(url, params=params, headers=self.headers)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            # Only print error if it's not a common 404 (which is expected for stale MBIDs)
            if "404" not in str(e):
                print(f"MusicBrainz API error: {e}")
            return None
    
    def get_release_group_by_mbid(self, mbid: str) -> Optional[Dict]:
        """Get release group info by MusicBrainz ID."""
        if not mbid or mbid.strip() == "":
            return None
        
        cache_key = f"rg_{mbid}"
        
        # Check cache first
        cached = self._load_from_cache(cache_key)
        if cached:
            return cached
        
        # Make API request
        url = f"{self.base_url}/release-group/{mbid}"
        params = {'fmt': 'json'}
        
        data = self._make_request(url, params)
        if data:
            self._save_to_cache(cache_key, data)
        
        return data
    
    def search_release_groups(self, artist: str, album: str) -> Optional[List[Dict]]:
        """Search for release groups by artist and album name."""
        if not artist or not album:
            return None
        
        cache_key = f"search_{artist}_{album}"
        
        # Check cache first  
        cached = self._load_from_cache(cache_key)
        if cached:
            return cached.get('release-groups', [])
        
        # Build search query
        query = f'releasegroup:"{album}" AND artist:"{artist}"'
        
        url = f"{self.base_url}/release-group"
        params = {
            'query': query,
            'limit': 5,  # Only need top results
            'fmt': 'json'
        }
        
        data = self._make_request(url, params)
        if data:
            self._save_to_cache(cache_key, data)
            results = data.get('release-groups', [])
            
            # Filter results to find best match (prefer exact title matches)
            if results:
                album_lower = album.lower().strip()
                exact_matches = []
                partial_matches = []
                
                for result in results:
                    result_title = result.get('title', '').lower().strip()
                    if result_title == album_lower:
                        exact_matches.append(result)
                    elif album_lower in result_title or result_title in album_lower:
                        partial_matches.append(result)
                
                # Return exact matches first, then partial matches
                if exact_matches:
                    return exact_matches
                elif partial_matches:
                    return partial_matches
                else:
                    return results  # Return all if no good matches
            
            return results
        
        return []
    
    def get_release_type(self, mbid: str = None, artist: str = None, album: str = None) -> Optional[Dict]:
        """
        Get release type info for an album.
        
        Args:
            mbid: MusicBrainz ID if available
            artist: Artist name for search if no MBID
            album: Album name for search if no MBID
            
        Returns:
            Dict with primary_type, secondary_types, and confidence score
        """
        release_group = None
        confidence = 0.0
        
        if mbid:
            # Direct lookup by MBID
            release_group = self.get_release_group_by_mbid(mbid)
            if release_group:
                confidence = 1.0
            elif artist and album:
                # MBID failed, fall back to search
                print(f"MBID {mbid} failed for {artist} - {album}, trying search...")
                results = self.search_release_groups(artist, album)
                if results:
                    release_group = results[0]
                    confidence = 0.7  # Lower confidence for fallback search
                    print(f"Found via search: {release_group.get('title')} by {release_group.get('artist-credit', [{}])[0].get('name', 'Unknown')}")
                else:
                    print(f"Search also failed for {artist} - {album}")
        elif artist and album:
            # Search by artist/album name
            results = self.search_release_groups(artist, album)
            if results:
                # Take best match (first result from search)
                release_group = results[0]
                confidence = 0.8  # Lower confidence for search results
        
        if not release_group:
            return None
        
        return {
            'primary_type': release_group.get('primary-type'),
            'secondary_types': release_group.get('secondary-types', []),
            'confidence': confidence,
            'mbid': release_group.get('id'),
            'title': release_group.get('title'),
            'artist': release_group.get('artist-credit', [{}])[0].get('name') if release_group.get('artist-credit') else None
        }

def main():
    """Test the MusicBrainz client."""
    client = MusicBrainzClient()
    
    # Test with known MBID
    print("Testing with known MBID...")
    result = client.get_release_type(mbid="f5093c06-23e3-404f-aba8-fb382fabda2e")  # Random Access Memories
    if result:
        print(f"Primary type: {result['primary_type']}")
        print(f"Secondary types: {result['secondary_types']}")
        print(f"Confidence: {result['confidence']}")
    
    # Test search
    print("\nTesting search...")
    result = client.get_release_type(artist="Daft Punk", album="Random Access Memories")
    if result:
        print(f"Primary type: {result['primary_type']}")  
        print(f"Secondary types: {result['secondary_types']}")
        print(f"Confidence: {result['confidence']}")

if __name__ == "__main__":
    main()