# 2_transverse_hscode_tree.py
import os
import json
from pathlib import Path
from typing import List, Dict, Tuple

from google import genai
from google.genai import types
from tenacity import retry, wait_random_exponential

from dotenv import load_dotenv

# --- Configuration ---
load_dotenv()

HS_TREE_PATH = Path("./data/hs_code_tree.json")

# --- Pydantic would be better here, but for simplicity we'll use dicts ---
JSON_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "best_choice_code": {"type": "string"},
        "justification": {"type": "string"},
        "confidence_score": {"type": "integer", "description": "A score from 0 to 100"}
    },
    "required": ["best_choice_code", "justification", "confidence_score"]
}

class HSCClassifier:
    def __init__(self, tree_path: Path):
        print("Loading HS Code tree...")
        if not tree_path.exists():
            raise FileNotFoundError(f"HS Code tree not found at {tree_path}. Please run build_hs_tree.py first.")
        with open(tree_path, 'r') as f:
            self.hs_tree = json.load(f)
        
        self.client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

        print("Classifier initialized.")

    @retry(wait=wait_random_exponential(multiplier=1, max=60))
    def _get_llm_choice(self, prompt: str) -> Dict:
        """Sends prompt to LLM and gets a structured choice back."""
        # In a real app, you would add error handling and retries here

        print(prompt)

        response = self.client.models.generate_content( 
            # model="gemini-2.5-pro",
            model="gemini-2.5-flash",
            contents=prompt,
            config={
                "response_mime_type": "application/json",
                "response_schema": JSON_RESPONSE_SCHEMA,
            })
        return json.loads(response.text)

    def classify_product(self, product_description: str) -> Dict:
        """
        Navigates the HS tree to classify a product.
        """
        print(f"\n--- Starting Classification for: '{product_description}' ---")
        
        classification_path = []
        current_node_dict = {"children": self.hs_tree} # Start at root
        current_path_str = "Start"

        while current_node_dict.get("children"):
            choices = []
            for code, data in current_node_dict["children"].items():
                lookahead = f"(has {len(data.get("children"))} sub-categories)" if data.get("children") else "(final item)"
                choices.append(f"- Code `{code}`: {data['description']} {lookahead}")
            
            choices_text = "\n".join(choices)
            parent_notes = current_node_dict.get("notes") or "None"

            prompt = f"""
            You are a world-class customs classification expert. Your task is to determine the correct Harmonized System (HS) code for a product by making a series of decisions.

            Product Description: "{product_description}"

            Current Classification Path: "{current_path_str}"

            Parent Node Legal Notes to Consider:
            ---
            {parent_notes}
            ---

            Please choose the single most appropriate option from the list below to continue the classification. Provide a justification for your choice.

            Choices:
            {choices_text}
            
            Return your response in a JSON object with the keys "best_choice_code", "justification", and "confidence_score".
            """
            
            response = self._get_llm_choice(prompt)
            chosen_code = response['best_choice_code']
            
            # Validation
            if chosen_code not in current_node_dict["children"]:
                print(f"ERROR: LLM chose an invalid code '{chosen_code}'. Aborting.")
                return {"error": "LLM hallucinated an invalid code."}

            # Update state for next iteration
            chosen_node_data = current_node_dict["children"][chosen_code]
            classification_path.append({
                "code": chosen_code,
                "description": chosen_node_data['description'],
                "justification": response['justification'],
                "confidence": response['confidence_score']
            })
            
            current_node_dict = chosen_node_data
            current_path_str = " > ".join([step['description'] for step in classification_path])

            print(f"\nStep {len(classification_path)}: Chose code {chosen_code} (Confidence: {response['confidence_score']}%)")
            print(f"Justification: {response['justification']}")

        print("\n--- Classification Complete ---")
        final_result = {
            "product_description": product_description,
            "full_path": classification_path,
            "final_hs_code": classification_path[-1]['code'],
            "tariff_details": {
                "import_rate": current_node_dict.get("import_rate"),
                "export_rate": current_node_dict.get("export_rate"),
                "sst_rate": current_node_dict.get("sst_rate"),
            }
        }
        return final_result


if __name__ == "__main__":
    classifier = HSCClassifier(HS_TREE_PATH)
    
    # --- Example Usage ---
    product1 = "Live pure-bred breeding horses"
    result1 = classifier.classify_product(product1)
    print("\nFinal Result:\n", json.dumps(result1, indent=2))

    product2 = "Frozen chicken thighs, cut, for human consumption"
    result2 = classifier.classify_product(product2)
    print("\nFinal Result:\n", json.dumps(result2, indent=2))

    product2 = "Frozen chicken thighs, cut, for animal consumption"
    result2 = classifier.classify_product(product2)
    print("\nFinal Result:\n", json.dumps(result2, indent=2))

    product2 = "B&W Bowers & Wilkins Px8"
    result2 = classifier.classify_product(product2)
    print("\nFinal Result:\n", json.dumps(result2, indent=2))