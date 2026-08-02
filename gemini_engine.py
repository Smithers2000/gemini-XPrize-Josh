import os
from google import genai
from dotenv import load_dotenv

load_dotenv()

# Initialize gemini Client
api_key = os.getenv("GEMINI_API_KEY")
client = genai.Client(api_key=api_key)

def evaluate_spend_proposal(project_content, item_name, amount, justification):
    """
    Evaluate a purchaser request using Gemini act as an automated compliance guardrail
    """

    prompt  = f"""
    you are a BusiCash Ai, an automated financial compliance guardrail for student join ventures.
    
    context: {project_context}
    proposed Purchase: {item_name}
    cost: ${amount}
    Student Justification: {justification}

    Analyze if this expense aligns with the project goals and budget.
    return a clear verdict: APPROVED, REJECTED or REQUIRES_COFOUNDER_VOTE.
    provide a concise explination (2-3 sentences) explaining your reasoning.
    """

    response = client.models.generate_content(
        model='gemini-2.5-flash',
        contents=prompt,
    )

    return response.txt