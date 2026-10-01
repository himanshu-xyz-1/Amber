# Amber Self-Hosted WhatsApp Bridge 🚀

A lightweight, zero-cost WhatsApp notification bridge for Amber SRE On-Call Alerts using the Baileys Multi-Device protocol.

## Why Self-Hosted?
- **Zero Cost**: No Twilio per-message fees.
- **Zero Third-Party Accounts**: No Meta Developer verification or business manager approvals.
- **Privacy & Ownership**: All alerts are routed directly through your WhatsApp account.

## Quick Start (Client Setup)

### 1. Install Dependencies
```bash
cd services/whatsapp-bridge
npm install
```

### 2. Start the Bridge
```bash
npm start
```

### 3. Scan the QR Code
1. Open WhatsApp on your phone (iOS or Android).
2. Go to **Settings** > **Linked Devices** > **Link a Device**.
3. Point your camera at the QR code printed in the terminal.
4. Once connected, your session is saved locally in `sessions/`. You only need to scan **once**!

### 4. Configure Amber `.env`
Add your phone number and bridge URL to your Amber `.env` file:
```env
WHATSAPP_BRIDGE_URL=http://localhost:3001
WHATSAPP_ALERT_TO=919876543210   # Your phone number with country code
```

Whenever an incident triggers, Amber automatically dispatches live SRE incident cards directly to your WhatsApp!
