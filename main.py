from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from typing import Optional
from fastapi.middleware.cors import CORSMiddleware
import qrcode
import io
import base64
import os

app = FastAPI(title="PromptPay QR Generator", version="1.0.0")

# ตั้งค่า templates
templates = Jinja2Templates(directory="templates")

# CORS (สำหรับ production)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # ในการใช้งานจริง ควรระบุ domain ที่ชัดเจน
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

class PromptPayRequest(BaseModel):
    id_value: str
    amount: Optional[float] = None

def format_promptpay_id(raw_id: str) -> str:
    # ลบช่องว่างและตัวอักษรที่ไม่ใช่ตัวเลข
    clean_id = ''.join(filter(str.isdigit, raw_id))
    
    # เบอร์โทร (10 หลัก) -> แปลงเป็น format พร้อมเพย์
    if clean_id.startswith("0") and len(clean_id) == 10:
        return "0066" + clean_id[1:]
    elif len(clean_id) == 13:
        return clean_id  # บัตรประชาชน
    else:
        raise ValueError("รหัสพร้อมเพย์ไม่ถูกต้อง: ต้องเป็นเบอร์โทรศัพท์ 10 หลัก (เริ่มด้วย 0) หรือเลขบัตรประชาชน 13 หลัก")

def calculate_crc(payload: str) -> str:
    crc = 0xFFFF
    poly = 0x1021
    for byte in payload.encode('ascii'):
        crc ^= byte << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ poly) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return format(crc, '04X')

def generate_payload(id_value: str, amount: Optional[float] = None) -> str:
    id_formatted = format_promptpay_id(id_value)
    gui = "A000000677010111"
    acc = f"0016{gui}0113{id_formatted}"
    
    payload = "000201"          # Payload Format Indicator
    payload += "010212"         # Point of Initiation Method (Dynamic)
    
    payload += f"29{len(acc):02d}{acc}"  # Merchant Account Information
    
    payload += "5802TH"         # Country Code
    payload += "5303764"        # Currency (764 = THB)
    
    if amount is not None:
        amt = f"{amount:.2f}"
        payload += f"54{len(amt):02d}{amt}"  # Transaction amount
    
    payload += "6304"           # CRC Placeholder
    crc = calculate_crc(payload)
    payload += crc              # Append CRC
    
    return payload

def create_promptpay_qr_base64(payload: str) -> str:
    img = qrcode.make(payload)
    buffered = io.BytesIO()
    img.save(buffered, format="PNG")
    img_bytes = buffered.getvalue()
    return base64.b64encode(img_bytes).decode("utf-8")

# หน้าเว็บหลัก
@app.get("/", response_class=HTMLResponse)
async def show_index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/qr_cre")
async def generate_qr(data: PromptPayRequest):
    try:
        # ตรวจสอบข้อมูล
        if not data.id_value or not data.id_value.strip():
            raise HTTPException(status_code=400, detail="กรุณากรอกเบอร์โทรศัพท์หรือเลขบัตรประชาชน")
        
        if data.amount is not None and data.amount <= 0:
            raise HTTPException(status_code=400, detail="จำนวนเงินต้องมากกว่า 0")
            
        payload = generate_payload(data.id_value.strip(), data.amount)
        base64_img = create_promptpay_qr_base64(payload)
        
        return JSONResponse(content={
            "status": "success",
            "qr_code_base64": base64_img
        })
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail="ไม่สามารถสร้าง QR ได้: " + str(e))

# Health check endpoint สำหรับ deployment
@app.get("/health")
async def health_check():
    return {"status": "healthy", "message": "PromptPay QR Generator is running"}

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
