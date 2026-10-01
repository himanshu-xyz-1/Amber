import express from 'express';
import makeWASocket, { DisconnectReason, useMultiFileAuthState } from '@whiskeysockets/baileys';
import qrcode from 'qrcode-terminal';
import pino from 'pino';

const app = express();
app.use(express.json());

const PORT = process.env.PORT || 3001;
const logger = pino({ level: 'silent' });

let sock = null;
let isConnected = false;

async function startWhatsApp() {
  const { state, saveCreds } = await useMultiFileAuthState('sessions');

  sock = makeWASocket({
    auth: state,
    logger,
    printQRInTerminal: false
  });

  sock.ev.on('connection.update', (update) => {
    const { connection, lastDisconnect, qr } = update;

    if (qr) {
      console.log('\n======================================================');
      console.log('📲 SCAN THIS QR CODE WITH YOUR WHATSAPP (Linked Devices):');
      console.log('======================================================\n');
      qrcode.generate(qr, { small: true });
      console.log('\nSteps: Open WhatsApp -> Settings -> Linked Devices -> Link a Device\n');
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
      console.log('✅ WhatsApp Bridge Connected! Ready to send SRE incident alerts.');
    }
  });

  sock.ev.on('creds.update', saveCreds);
}

// Health check endpoint
app.get('/status', (req, res) => {
  res.json({
    status: isConnected ? 'connected' : 'waiting_for_qr_or_reconnecting',
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
    // Format recipient: WhatsApp requires digits followed by @s.whatsapp.net (or @g.us for groups)
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
