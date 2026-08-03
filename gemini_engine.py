import os
from google import genai
from dotenv import load_dotenv

load_dotenv()

# Initialize gemini Client
api_key = os.getenv("GEMINI_API_KEY")
client = genai.Client(api_key=api_key)

def evaluate_spend_proposal(project_context, item_name, amount, justification):
    """
    Evaluate a purchaser request using Gemini act as an automated compliance guardrail
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

    response = client.models.generate_content(
        model='gemini-2.5-flash',
        contents=prompt,
    )

    return response.txt