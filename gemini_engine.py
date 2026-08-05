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

    try:
        response = client.models.generate_content(
            model='gemini-1.5-flash',
            contents=prompt,
        )
        return response.text
    except APIError as e:
        if "429" in str(e):
            return "⚠️ **Rate limit hit (Quota 429)**: Gemini is temporarily cooling down. Please wait ~15-30 seconds and click evaluate again!"
        return f"⚠️ **Gemini API Notice**: {str(e)}"
    except Exception as e:
        return f"⚠️ an unexpected error occurred: {str(e)}"