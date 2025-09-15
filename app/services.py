# services.py (Corrected)

import httpx
import asyncio
from typing import Any, Dict, List
from sqlalchemy.orm import Session
from . import database, security

# --- Gemini API Config ---
GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-pro:generateContent"
GEMINI_API_KEY = "YOUR_GEMINI_API_KEY_HERE"
USE_GEMINI = False # Set to True after adding your API key

async def get_fraud_explanation_async(client: httpx.AsyncClient, transaction_details: Dict[str, Any]) -> str:
    """Asynchronously gets a single fraud explanation."""
    if not USE_GEMINI or not GEMINI_API_KEY:
        return f"ML Anomaly Detection: Transaction of ${transaction_details.get('amount', 0):.2f} flagged for review."
    
    try:
        prompt = (
            "Explain in simple terms why this credit card transaction might be fraudulent. Be concise. "
            f"Amount=${transaction_details.get('amount')}, Timestamp='{transaction_details.get('timestamp')}'"
        )
        headers = {"Content-Type": "application/json"}
        params = {"key": GEMINI_API_KEY}
        payload = {"contents": [{"parts": [{"text": prompt}]}]}
        
        resp = await client.post(GEMINI_API_URL, headers=headers, params=params, json=payload, timeout=25)
        resp.raise_for_status() # Raises an exception for 4xx/5xx responses
        
        data = resp.json()
        return data.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "No explanation provided.").strip()

    except httpx.RequestError as e:
        return f"Gemini API request failed: {e}"
    except Exception as e:
        return f"Gemini unavailable or error processing response: {str(e)}"

async def get_fraud_explanation_batch_async(transaction_details_list: List[Dict[str, Any]]) -> List[str]:
    """Asynchronously fetches explanations for a batch of transactions."""
    async with httpx.AsyncClient() as client:
        tasks = [get_fraud_explanation_async(client, details) for details in transaction_details_list]
        explanations = await asyncio.gather(*tasks, return_exceptions=True)
        # Handle cases where an exception was returned by gather
        return [str(exp) if isinstance(exp, Exception) else exp for exp in explanations]

def get_fraud_report_chunk(db: Session, page: int, page_size: int):
    """Fetches a paginated report of ONLY fraudulent transactions."""
    offset = (page - 1) * page_size
    
    # Corrected Query: Filter for is_fraud == 1
    query = db.query(database.Transaction).filter(database.Transaction.is_fraud == 1)
    
    total_fraudulent = query.count()
    total_transactions = db.query(database.Transaction).count()
    
    transactions = query.order_by(database.Transaction.timestamp.desc()).offset(offset).limit(page_size).all()

    results = []
    for tx in transactions:
        try:
            decrypted_card = security.decrypt_data(tx.card_number_encrypted)
            masked_card = security.mask_card_number(decrypted_card)
        except Exception:
            masked_card = "**** **** **** ????"

        results.append({
            "id": tx.id,
            "masked_card_number": masked_card,
            "amount": tx.amount,
            "timestamp": tx.timestamp.isoformat() if tx.timestamp else None,
            "explanation": tx.explanation or "Explanation not available",
        })
    
    # Build a summary object that the frontend can use
    summary = {
        "total_transactions": total_transactions,
        "fraudulent": total_fraudulent,
        "legit": total_transactions - total_fraudulent,
        "fraud_percentage": round((total_fraudulent / total_transactions) * 100, 2) if total_transactions > 0 else 0
    }

    return {"summary": summary, "fraud_cases": results, "page": page, "page_size": page_size}