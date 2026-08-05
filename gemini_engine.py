import os
import time
from google import genai
from google.genai.errors import APIError
from dotenv import load_dotenv

load_dotenv()

# Initialize Gemini Client
api_key = os.getenv("GEMINI_API_KEY")
client = genai.Client(api_key=api_key)

def evaluate_spend_proposal(project_context, item_name, amount, justification):
    """
    Evaluates a purchase request using Gemini as an automated compliance guardrail.
    Uses gemini-1.5-flash with rate-limit error handling.
    """
    prompt = f"""
    You are BusiCash AI, an automated financial compliance guardrail for student joint ventures.
    
    Project Context: {project_context}
    Proposed Purchase: {item_name}
    Cost: ${amount}
    Student Justification: {justification}
    
    Analyze if this expense aligns with the project goals and budget.
    Return a clear verdict: APPROVED, REJECTED, or REQUIRES_COFOUNDER_VOTE.
    Provide a concise explanation (2-3 sentences) explaining your reasoning.
    """
    #creates a priority list of models to attempt
    candidate_models = [
        'gemini-2.0-flash',
        'gemini-2.0-flash-lite',
        'gemini-1.5-flash-8b',
        'gemini-1.5-pro'
    ]
    last_error = ""

    for model_name in candidate_models:
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
            )
            return response.text
        except APIError as e:
            last_error = str(e)
            continue
        except Exception as e:
            last_error = str(e)
            continue
            
    return f"⚠️ **Gemini API Notice**: Could not reach candidate models. Last error: {last_error}"