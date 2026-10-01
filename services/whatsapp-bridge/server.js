import express from 'express';
import makeWASocket, { DisconnectReason, useMultiFileAuthState } from '@whiskeysockets/baileys';
import qrcodeTerminal from 'qrcode-terminal';
import QRCode from 'qrcode';
import pino from 'pino';

const app = express();
app.use(express.json());

const PORT = process.env.PORT || 3001;
const logger = pino({ level: 'silent' });

let sock = null;
let isConnected = false;
let currentQrDataUrl = null;

async function startWhatsApp() {
  const { state, saveCreds } = await useMultiFileAuthState('sessions');

  sock = makeWASocket({
    auth: state,
    logger,
    printQRInTerminal: false
  });

  sock.ev.on('connection.update', async (update) => {
    const { connection, lastDisconnect, qr } = update;

    if (qr) {
      currentQrDataUrl = await QRCode.toDataURL(qr, { width: 320, margin: 2 });
      console.log('\n======================================================');
      console.log('📲 SCAN THIS QR CODE WITH YOUR WHATSAPP (Linked Devices):');
      console.log(`🌐 OR OPEN IN BROWSER: http://localhost:${PORT}`);
      console.log('======================================================\n');
      qrcodeTerminal.generate(qr, { small: true });
      console.log('\nSteps: Open WhatsApp on phone -> Settings -> Linked Devices -> Link a Device\n');
    }

    if (connection === 'close') {
      isConnected = false;
      const statusCode = lastDisconnect?.error?.output?.statusCode;
      const shouldReconnect = statusCode !== DisconnectReason.loggedOut;
      console.log(`⚠️ Connection closed (code: ${statusCode}). Reconnecting: ${shouldReconnect}`);
      if (shouldReconnect) {
        setTimeout(startWhatsApp, 3000);
      } else {
        console.log('❌ Device logged out. Please restart and scan QR again.');
      }
    } else if (connection === 'open') {
      isConnected = true;
      currentQrDataUrl = null;
      console.log('✅ WhatsApp Bridge Connected! Ready to send SRE incident alerts.');
    }
  });

  sock.ev.on('creds.update', saveCreds);
}

// Visual Web UI for scanning QR Code
app.get('/', (req, res) => {
  if (isConnected) {
    return res.send(`
      <!DOCTYPE html>
      <html>
        <head>
          <title>Amber WhatsApp Bridge</title>
          <meta name="viewport" content="width=device-width, initial-scale=1">
          <style>
            body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #0a0a0c; color: #f4f4f5; display: flex; align-items: center; justify-content: center; height: 100vh; margin: 0; }
            .card { background: #18181b; border: 1px solid #27272a; border-radius: 16px; padding: 32px; text-align: center; max-width: 420px; box-shadow: 0 10px 30px rgba(0,0,0,0.5); }
            h2 { color: #22c55e; margin-top: 0; }
            p { color: #a1a1aa; line-height: 1.5; font-size: 14px; }
            .badge { display: inline-block; background: #14532d; color: #4ade80; padding: 6px 14px; border-radius: 999px; font-weight: 600; font-size: 13px; margin-bottom: 16px; }
          </style>
        </head>
        <body>
          <div class="card">
            <div class="badge">● ACTIVE</div>
            <h2>WhatsApp Bridge Connected</h2>
            <p>Amber is actively linked to your WhatsApp account.<br>Any P0/P1 infrastructure alerts will be automatically dispatched to your phone.</p>
          </div>
        </body>
      </html>
    `);
  }

  if (currentQrDataUrl) {
    return res.send(`
      <!DOCTYPE html>
      <html>
        <head>
          <title>Scan WhatsApp QR - Amber SRE</title>
          <meta name="viewport" content="width=device-width, initial-scale=1">
          <meta http-equiv="refresh" content="6">
          <style>
            body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #0a0a0c; color: #f4f4f5; display: flex; align-items: center; justify-content: center; height: 100vh; margin: 0; }
            .card { background: #18181b; border: 1px solid #27272a; border-radius: 20px; padding: 32px; text-align: center; max-width: 400px; box-shadow: 0 20px 40px rgba(0,0,0,0.6); }
            h2 { font-size: 20px; margin-top: 0; margin-bottom: 8px; }
            p { color: #a1a1aa; font-size: 13px; margin-bottom: 24px; line-height: 1.5; }
            .qr-wrapper { background: #ffffff; padding: 12px; border-radius: 12px; display: inline-block; box-shadow: 0 4px 12px rgba(0,0,0,0.3); }
            img { display: block; border-radius: 6px; }
            .steps { margin-top: 24px; text-align: left; background: #09090b; padding: 14px 18px; border-radius: 10px; font-size: 12px; color: #d4d4d8; line-height: 1.6; }
            .steps b { color: #f59e0b; }
          </style>
        </head>
        <body>
          <div class="card">
            <h2>Link Amber to WhatsApp</h2>
            <p>Scan this QR code with WhatsApp on your phone to enable instant on-call alerts.</p>
            <div class="qr-wrapper">
              <img src="${currentQrDataUrl}" width="280" height="280" alt="WhatsApp QR Code" />
            </div>
            <div class="steps">
              <b>1.</b> Open WhatsApp on your phone<br>
              <b>2.</b> Tap <b>Settings</b> &rarr; <b>Linked Devices</b><br>
              <b>3.</b> Tap <b>Link a Device</b> and point camera at screen
            </div>
          </div>
        </body>
      </html>
    `);
  }

  return res.send(`
    <!DOCTYPE html>
    <html>
      <head>
        <meta http-equiv="refresh" content="2">
        <style>body { background: #0a0a0c; color: #a1a1aa; font-family: sans-serif; display: flex; justify-content: center; align-items: center; height: 100vh; }</style>
      </head>
      <body>
        <p>⏳ Generating WhatsApp QR Code... Please wait.</p>
      </body>
    </html>
  `);
});

// JSON Status endpoint
app.get('/status', (req, res) => {
  res.json({
    status: isConnected ? 'connected' : 'waiting_for_qr',
    port: PORT
  });
});

// Endpoint called by Amber Backend
app.post('/send', async (req, res) => {
  const { to, message } = req.body;

  if (!isConnected || !sock) {
    return res.status(503).json({
      success: false,
      error: 'WhatsApp is not connected yet. Please scan the QR code first.'
    });
  }

  if (!to || !message) {
    return res.status(400).json({ success: false, error: 'Missing "to" or "message" in request.' });
  }

  try {
    let jid = to;
    if (!jid.includes('@')) {
      const cleanNumber = to.replace(/[^0-9]/g, '');
      jid = `${cleanNumber}@s.whatsapp.net`;
    }

    await sock.sendMessage(jid, { text: message });
    console.log(`[ALERT DISPATCHED] WhatsApp message sent to ${jid}`);
    return res.json({ success: true, delivered_to: jid });
  } catch (error) {
    console.error('Failed to send WhatsApp alert:', error);
    return res.status(500).json({ success: false, error: error.message });
  }
});

startWhatsApp();

app.listen(PORT, () => {
  console.log(`🚀 Amber WhatsApp Bridge listening on http://localhost:${PORT}`);
});
