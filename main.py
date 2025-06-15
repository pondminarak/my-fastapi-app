import os
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import qrcode
import io
import base64

app = FastAPI(title="PromptPay QR Generator", version="1.0.0")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files
app.mount("/static", StaticFiles(directory="app/static"), name="static")

class PromptPayRequest(BaseModel):
    id_value: str
    amount: Optional[float] = None

def format_promptpay_id(raw_id: str) -> str:
    """แปลงเบอร์โทรหรือบัตรประชาชนเป็น format พร้อมเพย์"""
    if raw_id.startswith("0") and len(raw_id) == 10:
        return "0066" + raw_id[1:]
    elif len(raw_id) == 13:
        return raw_id
    else:
        raise ValueError("รหัสพร้อมเพย์ไม่ถูกต้อง")

def calculate_crc(payload: str) -> str:
    """คำนวณ CRC16 สำหรับ QR payload"""
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
    """สร้าง payload สำหรับ QR Code พร้อมเพย์"""
    id_formatted = format_promptpay_id(id_value)
    gui = "A000000677010111"
    acc = f"0016{gui}0113{id_formatted}"

    payload = "000201"
    payload += "010212"
    payload += f"29{len(acc):02d}{acc}"
    payload += "5802TH"
    payload += "5303764"

    if amount is not None:
        amt = f"{amount:.2f}"
        payload += f"54{len(amt):02d}{amt}"

    payload += "6304"
    crc = calculate_crc(payload)
    payload += crc

    return payload

def create_promptpay_qr_base64(payload: str) -> str:
    """สร้าง QR Code และแปลงเป็น base64"""
    img = qrcode.make(payload)
    buffered = io.BytesIO()
    img.save(buffered, format="PNG")
    img_bytes = buffered.getvalue()
    return base64.b64encode(img_bytes).decode("utf-8")

@app.get("/")
async def read_index():
    """Serve หน้าแรก"""
    return FileResponse('app/static/index.html')

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy"}

@app.post("/qr_cre")
async def generate_qr(data: PromptPayRequest):
    """API สำหรับสร้าง QR Code พร้อมเพย์"""
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

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)