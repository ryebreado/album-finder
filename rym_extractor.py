#!/usr/bin/env python3
import pandas as pd
import sys
from typing import List, Dict

def extract_rym_data(csv_file_path: str) -> List[Dict[str, str]]:
    """
    Extract rated albums from RYM CSV export.
    
    Returns list of albums with title, artist, release_date, and rating.
    Only includes albums with rating > 0.
    """
    try:
        df = pd.read_csv(csv_file_path)
        
        # Filter out unrated albums (rating 0 or NaN)
        df = df[df['Rating'] > 0]
        
        # Use only Last Name for artist (ignore "The" prefix in First Name)
        df['artist'] = df['Last Name'].fillna('').str.strip()
        
        # Select and rename columns
        result_df = df[['Title', 'artist', 'Release_Date', 'Rating']].copy()
        result_df.columns = ['title', 'artist', 'release_date', 'rating']
        
        # Filter out rows with missing essential data
        result_df = result_df.dropna(subset=['title', 'artist'])
        result_df = result_df[(result_df['title'].str.strip() != '') & (result_df['artist'].str.strip() != '')]
        
        # Convert to list of dictionaries
        albums = result_df.to_dict('records')
        
        # Convert values to strings and strip whitespace
        for album in albums:
            for key, value in album.items():
                album[key] = str(value).strip() if pd.notna(value) else ''
        
        return albums
        
    except FileNotFoundError:
        print(f"Error: File '{csv_file_path}' not found.")
        return []
    except Exception as e:
        print(f"Error reading CSV: {e}")
        return []

def main():
    if len(sys.argv) != 2:
        print("Usage: python rym_extractor.py <csv_file_path>")
        sys.exit(1)
    
    csv_file = sys.argv[1]
    albums = extract_rym_data(csv_file)
    
    print(f"Extracted {len(albums)} rated albums from RYM data:")
    print()
    
    for album in albums:
        print(f"Title: {album['title']}")
        print(f"Artist: {album['artist']}")
        print(f"Release Date: {album['release_date']}")
        print(f"Rating: {album['rating']}")
        print("-" * 50)

if __name__ == "__main__":
    main()