# main.py

import os
import sys
import asyncio
import threading
import logging
from datetime import datetime
from typing import List, Dict
import pandas as pd
from io import StringIO

from fastapi import FastAPI, Depends, HTTPException, status, BackgroundTasks, Query
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel
from sqlalchemy.orm import Session
from starlette.staticfiles import StaticFiles

from app import database, security, services
from ml import model

# --- Fix Windows event loop issues ---
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# --- Logging Setup ---
logging.basicConfig(level=logging.INFO)

# --- FastAPI App ---
app = FastAPI(title="Fraud Detection API", version="11.0-BatchedProcessing")

# --- Task Management ---
task_lock = threading.Lock()
task_progress: Dict[str, any] = {"status": "idle", "processed": 0, "total": 0, "fraudulent": 0}

# --- Frontend Setup ---
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")
app.mount("/frontend", StaticFiles(directory=FRONTEND_DIR), name="frontend")

@app.get("/")
async def read_index():
    index_path = os.path.join(FRONTEND_DIR, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    raise HTTPException(status_code=404, detail="index.html not found in frontend folder")

# --- Auth Setup ---
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

def get_db():
    db = database.SessionLocal()
    try:
        yield db
    finally:
        db.close()

# --- Schemas ---
class UserCreate(BaseModel):
    username: str
    password: str

class UserInDB(BaseModel):
    username: str
    class Config:
        from_attributes = True

class TransactionIn(BaseModel):
    card_number: str
    amount: float

class TransactionBatch(BaseModel):
    transactions: List[TransactionIn]

class ModelName(BaseModel):
    model_name: str

def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid authentication credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = security.jwt.decode(token, security.SECRET_KEY, algorithms=[security.ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
    except security.JWTError:
        raise credentials_exception

    user = db.query(database.User).filter(database.User.username == username).first()
    if user is None:
        raise credentials_exception
    return UserInDB(username=user.username)

# --- Fraud Detection Background Task (High-Performance Batching) ---
def run_detection_in_background(db: Session, model_name: str):
    global task_progress
    try:
        total_unprocessed = db.query(database.Transaction).filter(database.Transaction.is_fraud == -1).count()
        task_progress.update({"status": "running", "processed": 0, "total": total_unprocessed, "fraudulent": 0})
        chunk_size = 50000

        while task_progress["processed"] < total_unprocessed:
            query = db.query(database.Transaction).filter(database.Transaction.is_fraud == -1).limit(chunk_size).statement
            df_batch = pd.read_sql(query, db.bind)
            if df_batch.empty:
                break

            df_batch['is_fraud'] = 0
            df_batch['explanation'] = "Transaction appears legitimate."

            # --- Rule-based detection ---
            df_batch.loc[df_batch['amount'] > 10000, ['is_fraud', 'explanation']] = (
                1, "Transaction flagged due to high value (> $10,000)."
            )

            # --- ML-based detection ---
            unflagged_mask = (df_batch['is_fraud'] == 0)
            if unflagged_mask.any():
                df_to_predict = df_batch.loc[unflagged_mask]
                ml_predictions = model.predict(df_to_predict, model_name=model_name)
                ml_fraud_indices = df_to_predict.index[ml_predictions == 1]

                df_batch.loc[ml_fraud_indices, 'is_fraud'] = 1

                if not ml_fraud_indices.empty:
                    gemini_details = df_batch.loc[ml_fraud_indices].apply(
                        lambda r: {"amount": r['amount'], "timestamp": r['timestamp'].strftime('%Y-%m-%d %H:%M:%S')},
                        axis=1
                    ).tolist()

                    async def fetch_all_explanations():
                        try:
                            return await services.get_fraud_explanation_batch_async(gemini_details)
                        except Exception as e:
                            logging.error(f"Error fetching explanations: {e}")
                            return ["Flagged by ML anomaly detection."] * len(gemini_details)

                    explanations = asyncio.run(fetch_all_explanations())
                    if len(explanations) == len(ml_fraud_indices):
                        df_batch.loc[ml_fraud_indices, 'explanation'] = explanations
                    else:
                        logging.error("Mismatch between ML fraud indices and explanations count.")

            update_mappings = df_batch[['id', 'is_fraud', 'explanation']].to_dict(orient='records')
            db.bulk_update_mappings(database.Transaction, update_mappings)
            db.commit()

            task_progress['processed'] += len(df_batch)
            task_progress['fraudulent'] += int(df_batch['is_fraud'].sum())
            logging.info(f"Processed chunk of {len(df_batch)}. Total processed: {task_progress['processed']}/{total_unprocessed}")

        task_progress["status"] = "completed"
        logging.info("✅ Fraud detection completed successfully.")

    except Exception as e:
        task_progress["status"] = "error"
        logging.error(f"❌ Error in background detection task: {e}")

    finally:
        if task_lock.locked():
            task_lock.release()
        db.close()

# --- App Events ---
@app.on_event("startup")
async def startup_event():
    model.load_models()
    database.create_db()
    logging.info("✅ Application startup: Models loaded and database ready.")

# --- API Endpoints ---

@app.post("/users/")
def create_user(user: UserCreate, db: Session = Depends(get_db)):
    if db.query(database.User).filter(database.User.username == user.username).first():
        raise HTTPException(status_code=400, detail="Username already registered")
    hashed_password = security.get_password_hash(user.password)
    db_user = database.User(username=user.username, hashed_password=hashed_password)
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return {"message": "User created successfully"}

@app.post("/token")
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(database.User).filter(database.User.username == form_data.username).first()
    if not user or not security.verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Incorrect username or password")
    token = security.create_access_token(data={"sub": user.username})
    return {"access_token": token, "token_type": "bearer"}

@app.post("/ingest_batch/")
def ingest_batch(batch: TransactionBatch, db: Session = Depends(get_db), current_user: UserInDB = Depends(get_current_user)):
    masked_response = []
    for tx in batch.transactions:
        encrypted_card = security.encrypt_data(tx.card_number)
        db_tx = database.Transaction(card_number_encrypted=encrypted_card, amount=tx.amount, is_fraud=-1)
        db.add(db_tx)
        masked_response.append({"masked_card": security.mask_card_number(tx.card_number), "amount": tx.amount})
    db.commit()
    db.add(database.AuditLog(username=current_user.username, action=f"Ingested {len(batch.transactions)} new transactions"))
    db.commit()
    return {"message": "Batch ingested successfully.", "transactions": masked_response}

@app.post("/transactions/clear")
def clear_transactions(db: Session = Depends(get_db), current_user: UserInDB = Depends(get_current_user)):
    num_deleted = db.query(database.Transaction).delete()
    db.add(database.AuditLog(username=current_user.username, action=f"Cleared {num_deleted} transactions"))
    db.commit()
    return {"message": f"Cleared {num_deleted} transactions."}

@app.post("/model/retrain")
def retrain_model(payload: ModelName, db: Session = Depends(get_db), current_user: UserInDB = Depends(get_current_user)):
    labeled_count = db.query(database.Transaction).filter(database.Transaction.is_fraud != -1).count()
    if payload.model_name != "IsolationForest" and labeled_count < 10:
        raise HTTPException(status_code=400, detail="Not enough labeled data. Run detection with IsolationForest first.")
    model.train_model(db, payload.model_name)
    db.add(database.AuditLog(username=current_user.username, action=f"Retrained model '{payload.model_name}'"))
    db.commit()
    return {"message": f"Model '{payload.model_name}' retrained successfully."}


@app.post("/detection/start")
def start_detection(
    payload: ModelName,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: UserInDB = Depends(get_current_user)
):
    if not task_lock.acquire(blocking=False):
        raise HTTPException(status_code=409, detail="Detection already running.")

    unprocessed_count = db.query(database.Transaction).filter(database.Transaction.is_fraud == -1).count()
    if unprocessed_count == 0:
        task_lock.release()
        raise HTTPException(status_code=404, detail="No unprocessed transactions.")

    # ✅ Safety: supervised models must be trained first
    if payload.model_name != "IsolationForest" and payload.model_name not in model._models:
        task_lock.release()
        raise HTTPException(
            status_code=400,
            detail=f"Model '{payload.model_name}' not trained yet. Retrain it first using /model/retrain."
        )

    global task_progress
    task_progress = {"status": "starting", "processed": 0, "total": unprocessed_count, "fraudulent": 0}

    db.add(database.AuditLog(
        username=current_user.username,
        action=f"Started detection for {unprocessed_count} txns using model '{payload.model_name}'"
    ))
    db.commit()

    db_session_for_task = database.SessionLocal()
    background_tasks.add_task(run_detection_in_background, db_session_for_task, payload.model_name)

    return {"message": f"Started fraud detection for {unprocessed_count} transactions."}


@app.get("/detection/progress")
def get_progress(current_user: UserInDB = Depends(get_current_user)):
    global task_progress
    current_status = "running" if task_lock.locked() else task_progress.get("status", "idle")
    return {**task_progress, "status": current_status}

@app.get("/fraud/report")
def fraud_report(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=1000),
    db: Session = Depends(get_db),
    current_user: UserInDB = Depends(get_current_user)
):
    return services.get_fraud_report_chunk(db, page, page_size)
@app.get("/fraud/report/download")
def download_fraud_report(db: Session = Depends(get_db), current_user: UserInDB = Depends(get_current_user)):
    fraud_cases = db.query(database.Transaction).filter(database.Transaction.is_fraud == 1).all()
    if not fraud_cases:
        raise HTTPException(status_code=404, detail="No fraudulent transactions found.")

    data = []
    for tx in fraud_cases:
        # Decrypt and mask the card number before adding to the report
        try:
            decrypted_card = security.decrypt_data(tx.card_number_encrypted)
            masked_card = security.mask_card_number(decrypted_card)
        except Exception:
            masked_card = "Decryption Error"
            
        data.append({
            "id": tx.id,
            "masked_card_number": masked_card, # Added this missing field
            "amount": tx.amount,
            "timestamp": tx.timestamp.isoformat(),
            "explanation": tx.explanation or "Explanation not available"
        })

    df = pd.DataFrame(data)
    stream = StringIO()
    df.to_csv(stream, index=False)

    response = StreamingResponse(iter([stream.getvalue()]), media_type="text/csv")
    response.headers["Content-Disposition"] = f"attachment; filename=fraud_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

    db.add(database.AuditLog(username=current_user.username, action="Downloaded fraud report"))
    db.commit()
    return response

@app.get("/audit_log/")
def audit_log(db: Session = Depends(get_db), current_user: UserInDB = Depends(get_current_user)):
    return db.query(database.AuditLog).order_by(database.AuditLog.timestamp.desc()).all()
