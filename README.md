# Matini - AI Model Registry & Multi-Tier Guardrails Sandbox

ระบบจำลอง **AI Registry & Marketplace** พร้อมระบบตรวจสอบความปลอดภัย **Guardrail Verification Engine (Per-Model)** พัฒนาด้วยสถาปัตยกรรม Monorepo ตามแบบฉบับ `sahassanai` และ `sindhu` โดยใช้ **Poetry + FastAPI + Flask + Brython (Python in Browser)** ในรูปแบบ **White Theme (Clean & Modern)**

---

## 🌟 Key Features

1. **AI Model Marketplace (Registry):**
   - แสดงรายการโมเดล AI (Security, Coding, Finance, General) พร้อมสถานะ Guardrails และ Metrics
2. **Per-Model Guardrail Customization:**
   - **Layer 1: Rule-Based Keyword Filter** ตรวจจับคำต้องห้าม (Blacklist) อย่างรวดเร็ว (Latency < 2ms) เพิ่ม/ลบคำต้องห้ามได้อิสระ
   - **Layer 2: LLM-as-a-Judge Guardrail** จำลอง AI วิเคราะห์เจตนา (Prompt Injection / Safety Alignment) พร้อมเลือกระดับความเข้มงวด (Low / Medium / High)
3. **Sandboxed Interactive Console (Brython):**
   - เขียน Client Logic ด้วย **Python** 100% ผ่าน Brython (`model_chat.py`)
   - ระบบ **Real-Time Guardrail Inspection Log** แสดงผลการตรวจสอบทีละ Layer แบบสดๆ

---

## 🚀 How to Run

### 1. ติดตั้ง Dependencies
```bash
poetry install
```

### 2. รัน FastAPI Backend (Port 8000)
```bash
./scripts/run-api
# หรือ
poetry run matini-api
```
- Swagger API Docs: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

### 3. รัน Flask Web Frontend (Port 8080)
```bash
./scripts/run-web
# หรือ
poetry run matini-web
```
- เว็บไซต์หน้าบ้าน: [http://localhost:8080](http://localhost:8080)

---

## 🧪 Testing

รัน Automated Test Suite ทั้ง Backend และ Frontend:
```bash
poetry run pytest
```
