#!/usr/bin/env python3
import sys
import os
import json
import html
from typing import List, Dict, Tuple, Set
from fuzzywuzzy import fuzz
from fuzzywuzzy import process

# Import our extractors
from rym_extractor import extract_rym_data
from lastfm_extractor import extract_lastfm_albums

try:
    from musicbrainz_client import MusicBrainzClient
    MUSICBRAINZ_AVAILABLE = True
except ImportError:
    MUSICBRAINZ_AVAILABLE = False

def normalize_string(s: str) -> str:
    """Normalize string for better matching."""
    if not s:
        return ""
    # Decode HTML entities (&amp; -> &, etc.)
    s = html.unescape(s)
    # Convert to lowercase, strip whitespace
    return s.lower().strip()

def normalize_title(title: str) -> str:
    """Normalize album title by removing common edition parentheticals."""
    if not title:
        return ""
    
    # Decode HTML entities first
    title = html.unescape(title)
    
    # Remove only common edition/version parentheticals
    import re
    
    # Separate patterns for readability
    patterns = [
        r'\s*\(.*?edition\)\s*',                    # Any "...edition" 
        r'\s*\((remaster(?:ed)?|\d{4}\s*remaster(?:ed)?)\)\s*',  # Remasters
        r'\s*\(deluxe\)\s*',                       # Deluxe (standalone)
        r'\s*\(expanded\)\s*',                     # Expanded (standalone)
        r'\s*\(demos.*?\)\s*',                     # Demos (with optional years/info)
        r'\s*\(explicit\)\s*',                     # Explicit
    ]
    
    for pattern in patterns:
        title = re.sub(pattern, '', title, flags=re.IGNORECASE)
    
    return title.strip().lower()

def extract_main_artist(artist_string: str) -> str:
    """Extract main artist from collaboration strings."""
    if not artist_string:
        return ""
    
    # Common collaboration patterns
    separators = [' & ', ' and ', ' feat. ', ' featuring ', ' ft. ', ' with ', ' x ', ' vs. ', ' vs ', ', ']
    
    artist_lower = artist_string.lower()
    for sep in separators:
        if sep in artist_lower:
            # Return the first artist (before separator)
            return artist_string.split(sep)[0].strip()
    
    return artist_string.strip()

def calculate_artist_match_score(lastfm_artist: str, rym_artist: str) -> float:
    """Calculate artist match score with collaboration handling."""
    if not lastfm_artist or not rym_artist:
        return 0.0
    
    # Direct fuzzy match
    direct_score = fuzz.ratio(lastfm_artist, rym_artist)
    
    # Extract main artists and compare
    lastfm_main = extract_main_artist(lastfm_artist)
    rym_main = extract_main_artist(rym_artist)
    main_score = fuzz.ratio(lastfm_main, rym_main)
    
    # Check if one artist is contained in the other (for collaborations)
    containment_score = 0
    if lastfm_main in rym_artist or rym_main in lastfm_artist:
        containment_score = 85  # High score for containment
    
    # Return the best score
    return max(direct_score, main_score, containment_score)

def load_blacklist(blacklist_path: str = "data/blacklist.json") -> List[Dict]:
    """Load blacklist of albums to exclude from recommendations."""
    if not os.path.exists(blacklist_path):
        return []
    
    try:
        with open(blacklist_path, 'r', encoding='utf-8') as f:
            blacklist = json.load(f)
        print(f"Loaded {len(blacklist)} blacklisted albums")
        return blacklist
    except (json.JSONDecodeError, FileNotFoundError):
        print(f"Could not load blacklist from {blacklist_path}")
        return []

def is_blacklisted(album: Dict, blacklist: List[Dict]) -> bool:
    """Check if an album matches any blacklist entry."""
    album_artist = normalize_string(album['artist'])
    album_title = normalize_title(album['title'])
    
    for blocked in blacklist:
        blocked_artist = normalize_string(blocked.get('artist', ''))
        blocked_title = normalize_title(blocked.get('title', ''))
        
        if album_artist == blocked_artist and album_title == blocked_title:
            return True
    
    return False

def should_filter_by_release_type(album: Dict, filter_config: Dict) -> bool:
    """Check if an album should be filtered out based on release type."""
    primary_type = album.get('mb_primary_type')
    secondary_types = album.get('mb_secondary_types', [])
    confidence = album.get('mb_confidence', 0.0)
    
    # If no MusicBrainz data or low confidence, don't filter
    if not primary_type or confidence < 0.7:
        return False
    
    # Filter singles if requested
    if filter_config.get('filter_singles', True) and primary_type and primary_type.lower() == 'single':
        return True
    
    # Filter EPs if requested
    if filter_config.get('filter_eps', False) and primary_type and primary_type.lower() == 'ep':
        return True
    
    # Filter compilations if requested (check secondary types case-insensitively)
    if filter_config.get('filter_compilations', True) and secondary_types:
        if any('compilation' in sec_type.lower() for sec_type in secondary_types):
            return True
    
    # Filter live albums if requested
    if filter_config.get('filter_live', False) and secondary_types:
        if any('live' in sec_type.lower() for sec_type in secondary_types):
            return True
    
    # Filter demos if requested
    if filter_config.get('filter_demos', True) and secondary_types:
        if any('demo' in sec_type.lower() for sec_type in secondary_types):
            return True
    
    # Filter mixtapes if requested
    if filter_config.get('filter_mixtapes', True) and secondary_types:
        if any('mixtape' in sec_type.lower() or 'street' in sec_type.lower() for sec_type in secondary_types):
            return True
    
    return False

def filter_albums_by_type(albums: List[Dict], filter_config: Dict, debug: bool = False) -> List[Dict]:
    """Filter albums based on release type preferences."""
    if not filter_config:
        return albums
    
    filtered = []
    filtered_count = 0
    
    # Open debug file for filtering if debug mode enabled
    debug_file = None
    if debug:
        os.makedirs('data', exist_ok=True)
        debug_file = open('data/debug_filtering.txt', 'w', encoding='utf-8')
        debug_file.write("MUSICBRAINZ FILTERING DEBUG OUTPUT\n")
        debug_file.write("=" * 60 + "\n\n")
    
    for album in albums:
        should_filter = should_filter_by_release_type(album, filter_config)
        
        if debug and debug_file:
            debug_file.write(f"ALBUM: {album['artist']} - {album['title']}\n")
            debug_file.write(f"Primary Type: {album.get('mb_primary_type', 'None')}\n")
            debug_file.write(f"Secondary Types: {album.get('mb_secondary_types', [])}\n")
            debug_file.write(f"MB Confidence: {album.get('mb_confidence', 0.0)}\n")
            debug_file.write(f"Action: {'FILTERED OUT' if should_filter else 'KEPT'}\n")
            if should_filter:
                primary_type = album.get('mb_primary_type')
                secondary_types = album.get('mb_secondary_types', [])
                reason = []
                if primary_type == 'single' and filter_config.get('filter_singles'):
                    reason.append('single')
                if primary_type == 'ep' and filter_config.get('filter_eps'):
                    reason.append('EP')
                if 'compilation' in secondary_types and filter_config.get('filter_compilations'):
                    reason.append('compilation')
                if 'live' in secondary_types and filter_config.get('filter_live'):
                    reason.append('live')
                if 'demo' in secondary_types and filter_config.get('filter_demos'):
                    reason.append('demo')
                if 'mixtape/street' in secondary_types and filter_config.get('filter_mixtapes'):
                    reason.append('mixtape')
                debug_file.write(f"Reason: {', '.join(reason) if reason else 'unknown'}\n")
            debug_file.write("\n")
        
        if should_filter:
            filtered_count += 1
        else:
            filtered.append(album)
    
    if debug_file:
        debug_file.close()
        print(f"MusicBrainz filtering debug written to data/debug_filtering.txt")
    
    if filtered_count > 0:
        print(f"Filtered out {filtered_count} albums by release type")
    
    return filtered


def fuzzy_match_albums(rym_albums: List[Dict], lastfm_albums: List[Dict], 
                      artist_threshold: int = 85, title_threshold: int = 85, debug: bool = False) -> Tuple[List[Dict], List[Dict]]:
    """
    Find Last.fm albums that aren't rated on RYM.
    
    Args:
        rym_albums: List of RYM albums with ratings
        lastfm_albums: List of Last.fm albums with scrobbles
        artist_threshold: Minimum fuzzy match score for artist names
        title_threshold: Minimum fuzzy match score for album titles
    
    Returns:
        Tuple of (matched_albums, unrated_albums)
    """
    matched_albums = []
    unrated_albums = []
    
    print(f"Matching {len(lastfm_albums)} Last.fm albums against {len(rym_albums)} RYM albums...")
    
    # Open debug file if debug mode is enabled
    debug_file = None
    if debug:
        os.makedirs('data', exist_ok=True)
        debug_file = open('data/debug_output.txt', 'w', encoding='utf-8')
        debug_file.write("ALBUM MATCHER DEBUG OUTPUT\n")
        debug_file.write("=" * 60 + "\n\n")
    
    for lastfm_album in lastfm_albums:
        lastfm_artist = normalize_string(lastfm_album['artist'])
        lastfm_title = normalize_title(lastfm_album['title'])
        
        if debug and debug_file:
            debug_file.write(f"ALBUM: {lastfm_album['artist']} - {lastfm_album['title']}\n")
            debug_file.write(f"Scrobbles: {lastfm_album.get('scrobbles', 'N/A')}\n")
            
            # MusicBrainz information
            if lastfm_album.get('mbid'):
                debug_file.write(f"MBID: {lastfm_album['mbid']}\n")
            else:
                debug_file.write("MBID: None\n")
                
            if 'mb_primary_type' in lastfm_album:
                debug_file.write(f"MusicBrainz ID: {lastfm_album.get('mb_id', 'N/A')}\n")
                debug_file.write(f"Primary Type: {lastfm_album.get('mb_primary_type', 'N/A')}\n")
                debug_file.write(f"Secondary Types: {lastfm_album.get('mb_secondary_types', [])}\n")
                debug_file.write(f"MB Confidence: {lastfm_album.get('mb_confidence', 0.0)}\n")
            else:
                debug_file.write("MusicBrainz: Not enriched\n")
        
        if not lastfm_artist or not lastfm_title:
            if debug and debug_file:
                debug_file.write("SKIPPED: Missing artist or title\n\n")
            continue
            
        best_match = None
        best_score = 0
        best_match_info = None
        
        for rym_album in rym_albums:
            rym_artist = normalize_string(rym_album['artist'])
            rym_artist_loc = normalize_string(rym_album.get('artist_localized', ''))
            rym_title = normalize_title(rym_album['title'])
            
            if not rym_artist or not rym_title:
                continue
            
            # Try matching with both regular and localized artist names
            artist_scores = []
            if rym_artist:
                artist_scores.append(calculate_artist_match_score(lastfm_artist, rym_artist))
            if rym_artist_loc:
                artist_scores.append(calculate_artist_match_score(lastfm_artist, rym_artist_loc))
            
            if not artist_scores:
                continue
                
            best_artist_score = max(artist_scores)
            title_score = fuzz.ratio(lastfm_title, rym_title)
            
            # Combined score (weighted average)
            combined_score = (best_artist_score * 0.6 + title_score * 0.4)
            
            if combined_score > best_score:
                best_score = combined_score
                best_match_info = {
                    'rym_artist': rym_album['artist'],
                    'rym_title': rym_album['title'], 
                    'artist_score': best_artist_score,
                    'title_score': title_score,
                    'combined_score': combined_score
                }
                
                # Tiered thresholds: if artist match is perfect, be more lenient on title
                if best_artist_score >= 95:  # Near-perfect artist match
                    title_min = 60
                elif best_artist_score >= artist_threshold:  # Good artist match
                    title_min = title_threshold
                else:
                    title_min = 100  # Impossible - require perfect artist match
                
                if (best_artist_score >= artist_threshold and 
                    title_score >= title_min):
                    best_match = rym_album
        
        if best_match:
            if debug and debug_file:
                debug_file.write(f"MATCHED with RYM: {best_match['artist']} - {best_match['title']}\n")
                debug_file.write(f"RYM Rating: {best_match['rating']}/10\n")
                if best_match_info:
                    debug_file.write(f"Match Scores - Artist: {best_match_info['artist_score']:.1f}, Title: {best_match_info['title_score']:.1f}, Combined: {best_match_info['combined_score']:.1f}\n")
                debug_file.write("STATUS: Will not appear in recommendations (already rated)\n\n")
            
            matched_info = {
                **lastfm_album,
                'rym_rating': best_match['rating'],
                'rym_artist': best_match['artist'],
                'rym_artist_localized': best_match.get('artist_localized', ''),
                'rym_title': best_match['title'],
                'match_score': best_score
            }
            matched_albums.append(matched_info)
        else:
            if debug and debug_file:
                debug_file.write("NO RYM MATCH found\n")
                if best_match_info:
                    debug_file.write(f"Best attempt: {best_match_info['rym_artist']} - {best_match_info['rym_title']}\n")
                    debug_file.write(f"Best scores - Artist: {best_match_info['artist_score']:.1f}, Title: {best_match_info['title_score']:.1f}, Combined: {best_match_info['combined_score']:.1f}\n")
                debug_file.write("STATUS: Will appear in recommendations\n\n")
            
            # Add debugging info about best match attempt
            unrated_info = {
                **lastfm_album,
                'best_match': best_match_info
            }
            unrated_albums.append(unrated_info)
    
    # Close debug file if open
    if debug_file:
        debug_file.close()
        print(f"Debug information written to data/debug_output.txt")
    
    return matched_albums, unrated_albums

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='Find Last.fm albums not rated on RYM')
    parser.add_argument('rym_csv', help='Path to RYM CSV export')
    parser.add_argument('lastfm_username', help='Last.fm username')
    parser.add_argument('period', nargs='?', default='overall', 
                       help='Time period (overall, 7day, 1month, 3month, 6month, 12month)')
    parser.add_argument('limit', nargs='?', type=int, default=1000,
                       help='Maximum number of albums to fetch')
    
    # MusicBrainz filtering options
    parser.add_argument('--use-musicbrainz', action='store_true',
                       help='Enable MusicBrainz filtering (auto-filters singles/demos/mixtapes/compilations)')
    parser.add_argument('--filter-eps', action='store_true',
                       help='Also filter out EPs (requires --use-musicbrainz)')
    parser.add_argument('--filter-live', action='store_true',
                       help='Also filter out live albums (requires --use-musicbrainz)')
    parser.add_argument('--debug', action='store_true',
                       help='Write extended debug information to data/debug_output.txt')
    
    args = parser.parse_args()
    
    rym_csv_path = args.rym_csv
    lastfm_username = args.lastfm_username
    period = args.period
    limit = args.limit
    
    # Check MusicBrainz availability and user preferences
    use_musicbrainz = args.use_musicbrainz
    if use_musicbrainz and not MUSICBRAINZ_AVAILABLE:
        print("Error: MusicBrainz client not available")
        sys.exit(1)
    
    # Build filter configuration
    filter_config = None
    if use_musicbrainz:
        filter_config = {
            'filter_singles': True,  # Always filter singles
            'filter_eps': args.filter_eps,
            'filter_compilations': True,  # Always filter compilations
            'filter_live': args.filter_live,
            'filter_demos': True,  # Always filter demos
            'filter_mixtapes': True  # Always filter mixtapes
        }
    
    # Check if API key is set
    api_key = os.getenv('LASTFM_API_KEY')
    if not api_key:
        print("Error: LASTFM_API_KEY environment variable not set")
        sys.exit(1)
    
    print("=" * 60)
    print("ALBUM MATCHER - Find Last.fm albums not rated on RYM")
    print("=" * 60)
    
    # Load blacklist
    print(f"\n1. Loading blacklist...")
    blacklist = load_blacklist()
    
    # Extract RYM data
    print(f"\n2. Loading RYM data from {rym_csv_path}...")
    rym_albums = extract_rym_data(rym_csv_path)
    print(f"Found {len(rym_albums)} rated albums on RYM")
    
    # Extract Last.fm data
    print(f"\n3. Loading Last.fm data for {lastfm_username} ({period}, limit: {limit})...")
    lastfm_albums = extract_lastfm_albums(lastfm_username, api_key, period, limit, 
                                          enrich_with_musicbrainz=use_musicbrainz)
    print(f"Found {len(lastfm_albums)} albums on Last.fm")
    
    # Filter out blacklisted albums
    if blacklist:
        original_count = len(lastfm_albums)
        lastfm_albums = [album for album in lastfm_albums if not is_blacklisted(album, blacklist)]
        filtered_count = original_count - len(lastfm_albums)
        if filtered_count > 0:
            print(f"Filtered out {filtered_count} blacklisted albums")
    
    # Filter by release type if MusicBrainz data is available
    if use_musicbrainz and filter_config:
        lastfm_albums = filter_albums_by_type(lastfm_albums, filter_config, debug=args.debug)
    
    if not rym_albums or not lastfm_albums:
        print("Error: No data to compare")
        sys.exit(1)
    
    # Perform fuzzy matching
    print(f"\n4. Performing fuzzy matching...")
    matched_albums, unrated_albums = fuzzy_match_albums(rym_albums, lastfm_albums, debug=args.debug)
    
    # Display results
    print(f"\n" + "=" * 60)
    print("RESULTS")
    print("=" * 60)
    print(f"Total Last.fm albums: {len(lastfm_albums)}")
    print(f"Matched with RYM: {len(matched_albums)}")
    print(f"Not rated on RYM: {len(unrated_albums)}")
    print(f"Match rate: {len(matched_albums)/len(lastfm_albums)*100:.1f}%")
    
    if unrated_albums:
        print(f"\n ALBUMS TO RATE ({len(unrated_albums)}):")
        print("-" * 60)
        
        # Sort by scrobbles (descending)
        unrated_sorted = sorted(unrated_albums, 
                               key=lambda x: int(x.get('scrobbles', 0)), 
                               reverse=True)
        
        for album in unrated_sorted[:20]:  # Show top 20
            print(f"{album['scrobbles']} scrobbles")
            print(f"   {album['artist']} - {album['title']}")
            
            # Only show match scores in debug mode
            if args.debug and album.get('best_match'):
                best = album['best_match']
                print(f"   Best match: {best['rym_artist']} - {best['rym_title']}")
                print(f"   Scores: Artist {best['artist_score']:.1f} | Title {best['title_score']:.1f} | Combined {best['combined_score']:.1f}")
            elif args.debug and not album.get('best_match'):
                print(f"   No potential matches found")
            print()
    
    # if matched_albums:
    #     print(f"\nSAMPLE MATCHED ALBUMS ({min(10, len(matched_albums))}):")
    #     print("-" * 60)
        
    #     # Sort by match score (descending)
    #     matched_sorted = sorted(matched_albums, 
    #                            key=lambda x: x.get('match_score', 0), 
    #                            reverse=True)
        
    #     for album in matched_sorted[:10]:
    #         print(f"{album.get('rym_rating', 'N/A')}/10 | {album['scrobbles']} scrobbles | Match: {album.get('match_score', 0):.1f}")
    #         print(f"   Last.fm: {album['artist']} - {album['title']}")
    #         print(f"   RYM: {album.get('rym_artist', '')} - {album.get('rym_title', '')}")
    #         print()

if __name__ == "__main__":
    main()