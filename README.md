# Album finder
Takes RYM ratings and Last.fm scrobbles and compares them to find albums you've listened to but not rated

## Setup

### Last.fm API Key
Set your Last.fm API key as an environment variable:
```bash
export LASTFM_API_KEY=your_api_key_here
```

### Dependencies
```bash
pip install pandas fuzzywuzzy python-Levenshtein
```

## Usage

### Album Matching

```bash
python album_matcher.py data/your-music-export.csv username [period] [limit]
```

**Example:**
```bash
python album_matcher.py data/nepeta-music-export.csv nitrification 1month 100
```

**Features:**
- **Smart fuzzy matching** handles artist collaborations and localized names
- **Prioritization** shows most-listened unrated albums first
- **Blacklist** for excluding stuff from the "to rate" for any reason

#### Blacklist
Create `data/blacklist.json` to exclude specific albums:
```json
[
  {
    "artist": "Artist Name",
    "title": "Album Title",
    "reason": "compilation/bootleg/etc"
  }
]
```
You will need to do this for anything which isn't an "album" on RYM (e.g., bootlegs) or has a weird release on spotify (e.g., released as a compilation). Or for whatever you don't want to see! 

### Individual Extractors

#### Extract RYM Data
Extract rated albums from your RYM CSV export:
```bash
python rym_extractor.py data/your-music-export.csv
```

The RYM CSV can be found by going to your RYM profile and scrolling all the way to the bottom and clicking "Export your music catalog," named `[username]-music-export.csv`. Save it in the `data/` directory.

Only albums with rating > 0 are included. Both regular and localized artist names are extracted for better matching. 

#### Extract Last.fm Data
Extract your top albums from Last.fm:
```bash
python lastfm_extractor.py username [period] [limit]
```

Examples:
- `python lastfm_extractor.py nitrification` - Get top 1000 albums overall
- `python lastfm_extractor.py nitrification 1month 50` - Get top 50 albums from last month
- `python lastfm_extractor.py nitrification overall 500` - Get top 500 albums overall

**Periods:** overall (default), 7day, 1month, 3month, 6month, 12month
**Limit:** Maximum number of albums (default: 1000)

**Caching:** Data is automatically cached in `data/` directory to avoid repeated API calls.