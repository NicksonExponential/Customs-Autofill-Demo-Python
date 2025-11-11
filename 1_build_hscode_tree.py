# 1_build_hscode_tree.py
import pandas as pd
import json
from pathlib import Path
from tqdm import tqdm

INPUT_HS_CODE_CSV = Path("./master_data/jkdm-hs-explorer-pdk-2022.csv")
OUTPUT_TREE_JSON = Path("./data/hs_code_tree.json")
OUTPUT_NOTES_JSON = Path("./data/tariff_notes.json")

def parse_notes(df: pd.DataFrame) -> dict:
    """Parses Section and Chapter notes from the dataframe."""
    print("Parsing Section and Chapter notes...")
    chapter_notes = {}
    current_key = None
    current_text = []
    in_note_block = False

    for _, row in df.iterrows():
        desc = str(row['DESCRIPTION']).strip()
        header = str(row['HEADER']).strip()

        is_chapter_note_start = "Chapter Notes." in desc and len(header) >= 2
        
        if is_chapter_note_start:
            if current_key: # Save previous note
                chapter_notes[current_key] = "\n".join(current_text)
            
            in_note_block = True
            current_key = header[:2]
            current_text = [desc]
        elif in_note_block and pd.isna(row['HEADER']):
            current_text.append(desc)
        elif in_note_block:
            # End of note block
            if current_key:
                chapter_notes[current_key] = "\n".join(current_text)
            in_note_block = False
            current_key = None
            current_text = []

    if current_key: # Save the last note
        chapter_notes[current_key] = "\n".join(current_text)
    
    with open(OUTPUT_NOTES_JSON, 'w') as f:
        json.dump(chapter_notes, f, indent=2)
    print(f"Saved {len(chapter_notes)} chapter notes to {OUTPUT_NOTES_JSON}")
    return chapter_notes

def build_tree():
    """Converts the flat HS code CSV into a hierarchical JSON tree."""
    if OUTPUT_TREE_JSON.exists():
        print(f"Tree already exists at {OUTPUT_TREE_JSON}. Skipping build.")
        return

    df = pd.read_csv(INPUT_HS_CODE_CSV, dtype=str).fillna('')
    df.columns = df.columns.str.strip().str.upper().str.replace(' ', '_')

    chapter_notes = parse_notes(df)
    hs_tree = {}

    print("Building HS Code hierarchy tree...")
    for _, row in tqdm(df.iterrows(), total=df.shape[0]):
        header, sub, item = row['HEADER'], row['SUB'], row['ITEM']
        desc = str(row['DESCRIPTION']).strip()

        if not header or not desc or "Notes." in desc:
            continue

        # Create nodes in the tree if they don't exist
        chapter_code = header[:2]
        heading_code = header
        subheading_code = f"{header}{sub}"
        full_code = f"{header}{sub}{item}"

        # Chapter Node (Level 1)
        if chapter_code not in hs_tree:
            hs_tree[chapter_code] = {
                "description": "", # Will be filled by the chapter title row
                "notes": chapter_notes.get(chapter_code),
                "children": {}
            }

        # Heading Node (Level 2)
        if not sub and not item: # This is a heading title row
            if heading_code not in hs_tree[chapter_code]['children']:
                 hs_tree[chapter_code]['children'][heading_code] = {
                    "description": desc,
                    "notes": None,
                    "children": {}
                }
            else: # Update description if it was pre-created
                hs_tree[chapter_code]['children'][heading_code]['description'] = desc
            if len(desc) < len(hs_tree[chapter_code].get('description','z'*100)): # Chapter description is usually shorter
                hs_tree[chapter_code]['description'] = desc
            continue
        
        if heading_code not in hs_tree[chapter_code]['children']:
            hs_tree[chapter_code]['children'][heading_code] = {"description": "", "notes": None, "children": {}}

        # Subheading Node (Level 3)
        if not item: # This is a subheading title row
            if subheading_code not in hs_tree[chapter_code]['children'][heading_code]['children']:
                hs_tree[chapter_code]['children'][heading_code]['children'][subheading_code] = {
                    "description": desc,
                    "notes": None,
                    "children": {}
                }
            else:
                 hs_tree[chapter_code]['children'][heading_code]['children'][subheading_code]['description'] = desc
            continue

        if subheading_code not in hs_tree[chapter_code]['children'][heading_code]['children']:
            hs_tree[chapter_code]['children'][heading_code]['children'][subheading_code] = {"description": "", "notes": None, "children": {}}

        # Leaf Node (Final Item)
        hs_tree[chapter_code]['children'][heading_code]['children'][subheading_code]['children'][full_code] = {
            "description": desc,
            "import_rate": row['IMPORT_RATE'],
            "export_rate": row['EKSPORT_RATE'],
            "sst_rate": row['SST'],
            "children": {} # No further children
        }

    with open(OUTPUT_TREE_JSON, 'w') as f:
        json.dump(hs_tree, f, indent=2)
    print(f"Successfully built and saved HS tree to {OUTPUT_TREE_JSON}")

if __name__ == "__main__":
    build_tree()