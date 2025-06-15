from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from typing import Optional
from fastapi.middleware.cors import CORSMiddleware
import qrcode
import io
import base64

app = FastAPI()

# ตั้งค่า templates
templates = Jinja2Templates(directory="templates")

# CORS (สำหรับ frontend ที่รันจาก origin อื่น เช่น 127.0.0.1:5500)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # ปรับให้ปลอดภัยหาก deploy จริง เช่น allow_origins=["http://localhost:5500"]
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class PromptPayRequest(BaseModel):
    id_value: str
    amount: Optional[float] = None

def format_promptpay_id(raw_id: str) -> str:
    # เบอร์โทร (10 หลัก) -> แปลงเป็น format พร้อมเพย์
    if raw_id.startswith("0") and len(raw_id) == 10:
        return "0066" + raw_id[1:]
    elif len(raw_id) == 13:
        return raw_id  # บัตรประชาชน
    else:
        raise ValueError("รหัสพร้อมเพย์ไม่ถูกต้อง")

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
        payload = generate_payload(data.id_value, data.amount)
        base64_img = create_promptpay_qr_base64(payload)
        return JSONResponse(content={
            "status": "success",
            "qr_code_base64": base64_img
        })
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail="ไม่สามารถสร้าง QR ได้: " + str(e))
