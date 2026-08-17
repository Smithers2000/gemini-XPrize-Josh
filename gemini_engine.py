"""
Author: Joshua Smith
Project: busicash
Date: 8/1/2026
Description: this gemini engine.py to connect to the google gemini API and evaluate spend proposals for student joint ventures"""
import os
import time
from google import genai
from google.genai.errors import APIError
from dotenv import load_dotenv

load_dotenv()

# Initialize Gemini Client
api_key = os.getenv("GEMINI_API_KEY")
client = genai.Client(api_key=api_key)

def get_active_model():
    """
    Queries Google AI Studio to fetch currently available models for this API key
    and returns a live active model name.
    """
    """
    try:
        # Iterate through the Pager object returned by client.models.list()
        models = client.models.list()
        active_names = [m.name.replace("models/", "") for m in models]
        
        print("\n--- AVAILABLE MODELS FOR THIS API KEY ---")
        print(active_names)
        print("-----------------------------------------\n")
        
        # Pick the first available flash or pro model dynamically from live API list
        for name in active_names:
            if 'flash' in name or 'pro' in name:
                return name
                
        return active_names[0] if active_names else 'gemini-flash-latest'
        
    except Exception as e:
        print(f"Error fetching model list: {e}")
        return 'gemini-flash-latest'
    """
    # For now, return a hardcoded model name
    print("******** USING NEW GEMINI_ENGINE.PY ********")
    return "gemini-3.6-flash"

    """
    Evaluates a purchase request using Gemini as an automated compliance guardrail.
    """
def evaluate_spend_proposal(project_context, item_name, amount, justification):
    prompt = f"""
    You are BusiCash AI, an automated financial compliance guardrail for student joint ventures.
    
    Project Context: {project_context}
    Proposed Purchase: {item_name}
    Cost: ${amount}
    Student Justification: {justification}
    
    Analyze if this expense aligns with the project goals and budget.
    Return a clear verdict: APPROVED, REJECTED, or REQUIRES_COFOUNDER_VOTE.
    Provide a concise explanation (1-2 sentences) explaining your reasoning.
    """

    selected_model = get_active_model()
    print(f"Selected Model for Evaluation: {selected_model}")
    print("\n================ [GEMINI API REQUEST] ================")
    print(f"PAYLOAD SENT TO GEMINI:\n{prompt}")
    
    try:
        response = client.models.generate_content(
            model=selected_model,
            contents=prompt,
        )
        
        return response.text
    except APIError as e:
        return f"⚠️ **Gemini API Error ({selected_model})**: {str(e)}"
    except Exception as e:
        return f"⚠️ Unexpected Error: {str(e)}"
    