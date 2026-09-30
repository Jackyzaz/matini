# Matini — Local LLM Chat & NIST AI RMF Assessment

แอปแชทกับ **Local LLM (Ollama)** หน้าตาแบบแอปแชท AI ทั่วไป พร้อมระบบ **ประเมินจริยธรรม AI ตามกรอบ NIST AI RMF**
สถาปัตยกรรม Monorepo: **Poetry + FastAPI + Beanie (MongoDB) + Flask + Brython (Python in Browser)**

---

## Features

1. **Chat** (หน้าแรก `/`) — คุยหลายรอบ, คำตอบ stream ทีละ token, เลือกโมเดลได้จาก dropdown, ประวัติเก็บใน MongoDB
2. **Admin** (`/admin/`) — เพิ่ม/เปิด-ปิด/ลบ/ทดสอบ Local LLM (ตอนนี้รองรับ Ollama; Base URL ค่าเริ่มต้นมาจาก `.env`)
3. **NIST AI RMF Assessment** (`/assessment/<llm_id>`) — ประเมินโมเดล 12 เกณฑ์ด้วย LLM-as-judge รันเบื้องหลังพร้อม **progress bar**

> ระบบ Guardrail ถูกปิดไว้ (ไม่ได้ต่อเข้ากับแชท) แต่ยังเก็บโค้ดไว้ที่ `matini/api/services/guardrails.py`

---

## How to Run

ต้องมี **Python 3.12 หรือ 3.13** (Beanie ยังไม่รองรับ 3.14), **MongoDB** และ **Ollama**

```bash
poetry install
cp .env.example .env          # แล้วแก้ MONGODB_URI / OLLAMA_BASE_URL / OLLAMA_JUDGE_MODEL

docker run -d --name matini-mongo -p 27017:27017 mongo:7   # ถ้ายังไม่มี MongoDB

./scripts/run-api             # FastAPI  → http://127.0.0.1:8000  (Swagger: /docs)
./scripts/run-web             # Flask    → http://localhost:8080
```

จากนั้นเปิด `http://localhost:8080/admin/` เพื่อเพิ่ม LLM ตัวแรก (เช่น model tag `llama3.2:3b`) แล้วกลับไปแชทที่หน้าแรก

รายละเอียดการตั้งค่า Ollama (รวมกรณีรันคนละเครื่อง) และการใช้หน้าประเมิน: [matini/docs/nist-rmf-poc-guide.md](matini/docs/nist-rmf-poc-guide.md)

หลังแก้ template ให้ build Tailwind ใหม่: `./scripts/npm run tw`

---

## Testing

```bash
poetry run pytest
```

ชุดทดสอบฝั่ง API ใช้ MongoDB จริงที่ database `matinidb_test` (ตั้งค่าได้ด้วย `TEST_MONGODB_URI`; ชื่อ database ต้องลงท้าย `_test`)
และจะ skip อัตโนมัติถ้าเชื่อมต่อ MongoDB ไม่ได้ — การเรียก Ollama ในเทสต์ถูก mock ไว้ทั้งหมด
