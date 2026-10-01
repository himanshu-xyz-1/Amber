import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pydantic import BaseModel
from typing import Optional
from fastapi import APIRouter, HTTPException, status
import logging

from backend.app.core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/contact", tags=["Contact"])

class ContactRequest(BaseModel):
    name: Optional[str] = None
    email: str
    phone: Optional[str] = None
    selectedPlan: Optional[str] = None
    selectedInfra: Optional[str] = None
    clusterScale: Optional[str] = None
    message: Optional[str] = None

@router.post("", status_code=status.HTTP_200_OK)
async def submit_contact(req: ContactRequest):
    gmail_user = settings.GMAIL_USER or "amber.incident@gmail.com"
    gmail_pass = settings.GMAIL_APP_PASSWORD

    if not gmail_pass:
        logger.warning("GMAIL_APP_PASSWORD is not set. Simulating contact dispatch.")
        return {
            "success": True,
            "simulated": True,
            "message": "Lead received (email delivery simulated in dev mode)"
        }

    msg = MIMEMultipart("alternative")
    msg["From"] = f"Amber Intake <{gmail_user}>"
    msg["To"] = gmail_user
    msg["Reply-To"] = req.email
    msg["Subject"] = f"🚨 New Amber Lead: {req.name + ' · ' if req.name else ''}{req.email} ({req.selectedPlan or 'Inquiry'})"

    plain_text = f"""
New Amber Lead Received
===============================================
Name:           {req.name or 'Not provided'}
Work Email:     {req.email}
Phone:          {req.phone or 'Not provided'}
Selected Tier:  {req.selectedPlan or 'General Inquiry'}
Infrastructure: {req.selectedInfra or 'AWS'} ({req.clusterScale or 'Not specified'})

Message:
-----------------------------------------------
{req.message or 'No additional message provided.'}
===============================================
Hit 'Reply' in your email client to directly reply to {req.email}.
    """.strip()

    html_content = f"""
    <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 580px; margin: 0 auto; background: #ffffff; border: 1px solid #e7e5e4; border-radius: 14px; padding: 24px;">
      <h2 style="color: #0c0a09; margin-top: 0;">New Client Inquiry Received</h2>
      <p><strong>Name:</strong> {req.name or 'Not provided'}</p>
      <p><strong>Work Email:</strong> <a href="mailto:{req.email}">{req.email}</a></p>
      <p><strong>Phone:</strong> {req.phone or 'Not provided'}</p>
      <p><strong>Selected Tier:</strong> {req.selectedPlan or 'General'}</p>
      <p><strong>Infrastructure:</strong> {req.selectedInfra or 'AWS'} ({req.clusterScale or 'N/A'})</p>
      <hr style="border: 0; border-top: 1px solid #e7e5e4; margin: 20px 0;" />
      <p><strong>Message:</strong><br/>{req.message or 'No message provided'}</p>
      <p style="color: #78716c; font-size: 12px; margin-top: 24px;">Click Reply in Gmail to respond directly to {req.email}.</p>
    </div>
    """

    msg.attach(MIMEText(plain_text, "plain"))
    msg.attach(MIMEText(html_content, "html"))

    try:
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(gmail_user, gmail_pass)
            server.send_message(msg)
        return {"success": True, "message": "Lead dispatched successfully"}
    except Exception as e:
        logger.error(f"Failed to send email via SMTP: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to dispatch email: {str(e)}"
        )
