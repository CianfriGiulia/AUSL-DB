from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
import mysql.connector
import requests

DB_CONFIG = {
    "host": "localhost",
    "port":3306,
    "user": "root",
    "password": "gennaio2000",
    "database": "ausl_tracker",
}



def fetch_players(url: str):
    print(f"\nFetching data from {url}...")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(user_agent="Mozilla/5.0")
        page.goto(url, wait_until="networkidle",timeout=30000)
        page.wait_for_selector("table tr",timeout=15000)
        html = page.content()
        browser.close()

    soup = BeautifulSoup(html, "html.parser")
    players_data = []


    url_parts = [p for p in url.lower().split("/") if p]
    url_team_hint = ""
    for slug in ["bandits","blaze","cascade","spark","talons","volts"]:
        if slug in url_parts:
            url_team_hint = slug
            break

    rows = soup.select("table tr")
    for row in rows:
        cols = [cell.get_text(" ", strip=True) for cell in row.find_all(["td", "th"])]
        if len(cols) >= 7 and cols[0].lower() != "athlete":
            raw_name = cols[0].split("#")[0].strip()
            team = cols[1].strip() or url_team_hint
            jersey_number = cols[2].strip() if len(cols) > 2 else ""
            position = cols[3].strip() if len(cols) > 3 else ""
            bats_throws = cols[4].strip() if len(cols) > 4 else ""
            college = cols[6].strip() if len(cols) > 6 else ""
            graduation_year = cols[7].strip() if len(cols) > 7 else ""
           
            players_data.append((
                raw_name,
                college,
                position,
                team,
                jersey_number,
                bats_throws,
                graduation_year,
            ))
           
    return players_data

def save_sql(players_data):
    conn = mysql.connector.connect(**DB_CONFIG)
    cursor = conn.cursor()

    cursor.execute("SELECT team_name, team_id FROM teams;")
    db_teams = cursor.fetchall()

    inserted = 0
    updated = 0

    for name, college, position, short_team, jersey_number, bats_throws, graduation_year in players_data:
        matched_team_id = None
        for full_team_name, tid in db_teams:
            if short_team and short_team.lower() in full_team_name.lower():
                matched_team_id = tid
                break

        cursor.execute("SELECT player_id FROM players WHERE full_name = %s;", (name,))
        existing = cursor.fetchone()

        if existing:
            cursor.execute(
                """
                UPDATE players
                SET college = %s,
                    position = %s,
                    team_2026_id = COALESCE(%s, team_2026_id),
                    jersey_number = %s,
                    bats_throws = %s,
                    graduation_year = %s
                WHERE player_id = %s;
                """,
                (
                    college,
                    position,
                    matched_team_id,
                    jersey_number,
                    bats_throws,
                    graduation_year,
                    existing[0]
                ),
            )
            updated += 1
        else:
            cursor.execute(
                """
                INSERT INTO players (
                    full_name,
                    college,
                    position,
                    team_2026_id,
                    jersey_number,
                    bats_throws,
                    graduation_year
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s);
                """,
                (
                    name,
                    college,
                    position,
                    matched_team_id,
                    jersey_number,
                    bats_throws,
                    graduation_year
                ),
            )
            inserted += 1

    conn.commit()
    cursor.close()
    conn.close()
    print(f"Saved! ({inserted} new players added, {updated} existing players updated)")

def main():
    print("=== AUSL Roster Importer ===")
    print("Paste a team roster URL and press Enter.")
    print("When you are finished with all teams, just press Enter on an empty line (or type 'done').")

    while True:
        url = input("\nPaste roster URL: ").strip()

        if not url or url.lower() in {"done", "exit", "quit"}:
            print("\nAll done! Closing importer.")
            break

        try:
            players = fetch_players(url)
            print(f"Found {len(players)} players on this page.")
            if players:
                save_sql(players)
            else:
                print("Warning: No table rows found—this page may load its roster dynamically with JavaScript.")
        except Exception as e:
            print(f"Error processing {url}: {e}")
            print("Let's keep going—you can try another URL or press Enter to stop.")

if __name__ == "__main__":
    main()